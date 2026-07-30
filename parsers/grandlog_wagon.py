"""Парсер ООО «ГрандЛог» (ПОВАГОНКА) — повагонные отправки КТК по ЖД, CY-FOR.

PDF-презентация: страницы 3-4 содержат тарифные таблицы
Угловая → станции РФ и Уссурийск → станции РФ.
Таблицы нарисованы без линий, поэтому колонки восстанавливаются
по координатам слов (`page.extract_words`), а не через `extract_tables()`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments

_COMPANY = "ГрандЛог"

# В проекте (railtrust.py, poseidon.py) ЖД-станция обозначается как "rail_station".
_STATION_TYPE = "rail_station"

# Параметры извлечения слов из PDF
_X_TOL = 1.5   # меньше дефолта: иначе "Станции московского" слипается в одно слово
_ROW_TOL = 3   # допуск группировки слов в строку по координате top
_COL_GAP = 25  # минимальный горизонтальный зазор между колонками заголовка

# Станция → родительский город
_STATION_CITY = {
    "Угловая": "Артём",
    "Уссурийск": "Уссурийск",
    "Омск-Восточный": "Омск",
    "Екатеринбург-Товарный": "Екатеринбург",
    "Батарейная": "Иркутск",
    "Чемской": "Новосибирск",
    "Мошково": "Мошково",
    "Блочная": "Пермь",
    "Войновка": "Тюмень",
    "Нижнекамск": "Нижнекамск",
    "Шушары": "Санкт-Петербург",
    "Челябинск-Грузовой": "Челябинск",
    "Базаиха": "Красноярск",
    "Ростов-Товарный": "Ростов-на-Дону",
    "Лагерная": "Казань",
    "Костариха": "Нижний Новгород",
    "Позимь": "Ижевск",
    "Станции московского узла": "Москва",
}

# Нормализация написаний из PDF
_STATION_ALIASES = {
    "Ростов - Товарный": "Ростов-Товарный",
    "Ростов Товарный": "Ростов-Товарный",
    "Станциимосковского узла": "Станции московского узла",
}

_CONDITIONS = (
    "CY-FOR, повагонная отправка КТК; в ставку включено: терминальная обработка "
    "на станции отправления, льготное хранение 14 суток, ЖД тариф и предоставление "
    "вагона, оформление документов; не включено: сбор за ВОХР и предоставление "
    "контейнера; НДС 22%"
)


def _price(val) -> Optional[float]:
    """'220 000,00' → 220000.0"""
    if val is None:
        return None
    s = str(val).replace("\u00a0", "").replace(" ", "")
    s = s.replace("₽", "").replace("руб.", "").replace("р.", "")
    s = re.sub(r",\d{1,2}$", "", s)          # отбрасываем копейки
    s = re.sub(r"[^\d]", "", s)
    return float(s) if s else None


def _norm_station(raw: str) -> str:
    """Чистит название станции и приводит к каноническому виду."""
    s = re.sub(r"\s+", " ", str(raw or "")).strip(" .,;")
    s = _STATION_ALIASES.get(s, s)
    # 'Ростов - Товарный' → 'Ростов-Товарный' (общий случай)
    s = re.sub(r"\s*-\s*", "-", s)
    return _STATION_ALIASES.get(s, s)


def _split_stations(raw: str) -> list[str]:
    """'Чемской/Мошково' → ['Чемской', 'Мошково']"""
    return [_norm_station(p) for p in str(raw).split("/") if p.strip()]


def _city_of(station: str) -> str:
    return _STATION_CITY.get(station, station)


def _parse_period(text: str) -> tuple[Optional[str], Optional[str]]:
    """'действительны с 15.02.2026 года по 28.02.2026' → ('2026-02-15', '2026-02-28')."""
    valid_from = valid_to = None
    m = re.search(r"с\s+(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        valid_from = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r"по\s+(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        valid_to = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return valid_from, valid_to


def _parse_col_header(header: str) -> Optional[tuple[str, Optional[int], Optional[int]]]:
    """'20ф КТК с 24т до 28т' → ('20DC', 24, 28); '40ф КТК до 28т' → ('40HC', None, 28)."""
    h = re.sub(r"\s+", " ", header).strip().lower()
    if re.match(r"^40\s*ф", h):
        ct = "40HC"
    elif re.match(r"^20\s*ф", h):
        ct = "20DC"
    else:
        return None

    min_t = max_t = None
    m = re.search(r"с\s*(\d+)\s*т", h)
    if m:
        min_t = int(m.group(1))
    m = re.search(r"до\s*(\d+)\s*т", h)
    if m:
        max_t = int(m.group(1))
    return ct, min_t, max_t


def _group_rows(words: list[dict]) -> list[list[dict]]:
    """Группирует слова страницы в строки по координате top."""
    buckets: dict[int, list[dict]] = {}
    for w in words:
        buckets.setdefault(round(w["top"] / _ROW_TOL), []).append(w)
    return [sorted(buckets[k], key=lambda w: w["x0"]) for k in sorted(buckets)]


def _cluster_header(row: list[dict]) -> list[tuple[float, float, str]]:
    """Склеивает слова строки заголовка в колонки по горизонтальным зазорам.

    Возвращает список (x0, x1, текст) по одному на колонку.
    """
    cols: list[tuple[float, float, list[str]]] = []
    for w in row:
        if cols and w["x0"] - cols[-1][1] <= _COL_GAP:
            x0, _, parts = cols[-1]
            parts.append(w["text"])
            cols[-1] = (x0, w["x1"], parts)
        else:
            cols.append((w["x0"], w["x1"], [w["text"]]))
    return [(x0, x1, " ".join(parts)) for x0, x1, parts in cols]


def _column_bounds(cols: list[tuple[float, float, str]]) -> list[float]:
    """Границы колонок — середины зазоров между соседними колонками заголовка."""
    return [(cols[i][1] + cols[i + 1][0]) / 2 for i in range(len(cols) - 1)]


def _row_to_cells(row: list[dict], bounds: list[float], n_cols: int) -> list[str]:
    """Раскладывает слова строки по колонкам согласно границам."""
    cells: list[list[str]] = [[] for _ in range(n_cols)]
    for w in row:
        center = (w["x0"] + w["x1"]) / 2
        idx = 0
        while idx < len(bounds) and center > bounds[idx]:
            idx += 1
        cells[min(idx, n_cols - 1)].append(w["text"])
    return [" ".join(c).strip() for c in cells]


def _parse_page(page) -> list[dict]:
    """Разбирает одну страницу с тарифной таблицей."""
    results: list[dict] = []
    page_text = page.extract_text() or ""
    if "Станция отправления" not in page_text.replace("  ", " "):
        return results

    valid_from, valid_to = _parse_period(page_text)

    rows = _group_rows(page.extract_words(x_tolerance=_X_TOL))

    header_cols: list[tuple[float, float, str]] = []
    bounds: list[float] = []
    col_specs: list[tuple[int, str, Optional[int], Optional[int]]] = []

    for row in rows:
        line = " ".join(w["text"] for w in row)

        # ── строка заголовка ──
        if "Станция" in line and "отправления" in line:
            header_cols = _cluster_header(row)
            bounds = _column_bounds(header_cols)
            col_specs = []
            for i, (_, _, title) in enumerate(header_cols):
                spec = _parse_col_header(title)
                if spec:
                    col_specs.append((i, *spec))
            continue

        if not col_specs:
            continue

        # ── служебные строки (условия, контакты) ──
        if re.search(r"Ставки указаны|@|\+7", line):
            continue

        cells = _row_to_cells(row, bounds, len(header_cols))
        origin_raw, dest_raw = cells[0], cells[1]
        if not origin_raw or not dest_raw:
            continue

        origins = _split_stations(origin_raw)
        destinations = _split_stations(dest_raw)
        if not origins or not destinations:
            continue

        for col_idx, ct, min_t, max_t in col_specs:
            cost = _price(cells[col_idx]) if col_idx < len(cells) else None
            if cost is None:
                continue

            for origin in origins:
                for dest in destinations:
                    results.append(
                        TariffSegment(
                            transport_type="rail",
                            start_point=f"{origin}, Россия",
                            end_point=f"{dest}, Россия",
                            container_type=ct,
                            weight_limit=str(max_t) if max_t else None,
                            min_weight_kg=min_t,
                            max_weight_kg=max_t,
                            cost=cost,
                            currency="RUB",
                            company=_COMPANY,
                            container_ownership="SOC",
                            conditions=_CONDITIONS,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            start_location_type=_STATION_TYPE,
                            end_location_type=_STATION_TYPE,
                            parent_start_location=_city_of(origin),
                            parent_start_location_type="city",
                            parent_end_location=_city_of(dest),
                            parent_end_location_type="city",
                        ).to_dict()
                    )

    return results


def parse_GrandLog_wagon(file_path: str | Path | None = None) -> list[dict]:
    """Парсит PDF «(ПОВАГОНКА) GrandLog ЖД».

    Каждая страница с тарифами: станция отправления (Угловая / Уссурийск)
    → станции назначения РФ, три весовые категории КТК, ставки в рублях.
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("*ПОВАГОНКА*GrandLog*.[pP][dD][fF]"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF ГрандЛог (повагонка) в директории data/. "
                "Ожидался файл по шаблону: (ПОВАГОНКА) GrandLog ЖД*.PDF"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    results: list[dict] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            results += _parse_page(page)

    if not results:
        raise ValueError(f"Не извлечено ни одной ставки из {file_path.name}")

    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_GrandLog_wagon(*args, **kwargs))
