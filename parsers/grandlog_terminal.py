"""Парсер ООО «ГрандЛог» — прайс складского комплекса (таможенный склад / открытая площадка).

PDF-презентация: стр. 3-7 содержат таблицы услуг в двух форматах шапки:
  A) Услуга | Ед. изм. | 20ф КТК (руб.) | 40ф КТК (руб.) | 45ф КТК (руб.)
  B) Услуга | Ед. изм. | Стоимость (руб.)

Таблицы нарисованы без линий (`extract_tables()` возвращает пусто), поэтому строки
собираются по координатам слов. Название услуги переносится на 2-3 строки, которые
расположены вокруг строки с ценой, — они склеиваются по вертикальной близости.

ВАЖНО: это прайс на услуги, а не на перевозку. Маршрута нет, поэтому
start_point == end_point == площадка ГрандЛог. Настраивается константами ниже.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments

_COMPANY = "ГрандЛог"

# ─────────────────────────── Настройки под схему проекта ───────────────────────────

# Тип транспорта. По умолчанию единый для всех строк прайса.
# Если нужно разделять хранение и ПРР — поставьте _TT_HANDLING = "terminal".
_TT_STORAGE = "warehouse"
_TT_HANDLING = "warehouse"

# container_type — обязательное поле, но у части услуг контейнера нет
# (тариф за м², шт, пал, час, ед). Для них подставляется эта заглушка.
_NON_CONTAINER_TYPE = "услуга"

# Тип локации. В skill разрешены port/station/terminal — берём terminal.
_LOCATION_TYPE = "terminal"

# Город площадки в PDF НЕ указан. По повагонному прайсу ГрандЛог работает
# со станций Угловая (Артём) и Уссурийск. Проставьте фактический город,
# иначе parent_* останутся пустыми.
_TERMINAL_CITY: Optional[str] = None

# Названия площадок из заголовков страниц
_SECTIONS = {
    "ТАМОЖЕННЫЙ СКЛАД": "Таможенный склад ГрандЛог",
    "ОТКРЫТАЯ ПЛОЩАДКА": "Открытая площадка ГрандЛог",
}

_VAT = "НДС 22%"

# ─────────────────────────── Параметры извлечения ───────────────────────────

_X_TOL = 1.5      # меньше дефолта: иначе соседние слова слипаются
_ROW_TOL = 3      # допуск группировки слов в строку по координате top
# Минимальный зазор между колонками. На стр. 4 колонки «40ф»/«45ф» разделены 23 pt,
# при этом внутри колонки зазоры ≤ 3 pt, а между ячейками данных ≥ 32 pt.
_COL_GAP = 12
_NAME_MAX_DY = 14 # макс. вертикальный отрыв переноса названия от строки с ценой

# Единицы измерения из колонки «Ед. изм.»
_UNITS = {
    "ктк": "ктк",
    "ед": "ед",
    "шт": "шт",
    "пал": "пал",
    "час": "час",
    "м2": "м²",
    "м²": "м²",
}

# Тип контейнера проставляется, только если услуга тарифицируется за контейнер
_CONTAINER_UNITS = {"ктк"}

_COL_CONTAINER = {
    "20": "20DC",
    "40": "40HC",
    "45": "45HC",
}

# Строки, которые не являются ни услугой, ни заголовком
_NOISE_RE = re.compile(
    r"^\s*\*+"                      # сноски: *, **
    r"|@|\+7\s*\("                  # контакты
    r"|по\s+запросу"                # «— по запросу», цены нет
    r"|Ставки\s+указаны"            # футер про НДС
    r"|Расчет\s+от\s+занимаемой",
    re.IGNORECASE,
)


# ─────────────────────────── Вспомогательные функции ───────────────────────────


def _price(val) -> Optional[float]:
    """'1 100,00' → 1100.0; '-' и '/' → None (услуга не оказывается)."""
    if val is None:
        return None
    s = str(val).replace("\u00a0", "").replace(" ", "").strip()
    if not s or s in {"-", "–", "—", "/"}:
        return None
    s = s.replace("₽", "").replace("руб.", "").replace("р.", "")
    s = re.sub(r",\d{1,2}$", "", s)      # копейки
    s = re.sub(r"[^\d]", "", s)
    return float(s) if s else None


def _price_variants(cell: str) -> list[float]:
    """'6 600,00/8 800,00' → [6600.0, 8800.0]; '1 100,00' → [1100.0]."""
    parts = [p for p in str(cell or "").split("/") if p.strip()]
    return [p for p in (_price(part) for part in parts) if p is not None]


def _variant_labels(service: str, n: int) -> list[Optional[str]]:
    """Достаёт подписи вариантов из названия: 'стандартного/усиленного щита' → 2 метки."""
    if n < 2:
        return [None]
    for word in service.split():
        parts = [p for p in word.split("/") if p]
        if len(parts) == n:
            return parts
    return [f"вариант {i + 1}" for i in range(n)]


def _norm_text(raw: str) -> str:
    return re.sub(r"\s+", " ", str(raw or "")).strip()


def _clean_service(raw: str) -> str:
    """Чистит название услуги от сносок и висячих пробелов."""
    s = _norm_text(raw)
    s = re.sub(r"\*+", "", s)                 # сноски ** в конце
    s = re.sub(r"\s+([,.;)])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s.strip(" .;")


def _weights_from_name(service: str) -> tuple[Optional[int], Optional[int]]:
    """'... до 24 т.' → (None, 24); '... более 24 т.' → (24, None). В тоннах."""
    min_t = max_t = None
    m = re.search(r"более\s+(\d+)\s*т", service, re.IGNORECASE)
    if m:
        min_t = int(m.group(1))
    m = re.search(r"до\s+(\d+)\s*т\b", service, re.IGNORECASE)
    if m:
        max_t = int(m.group(1))
    return min_t, max_t


def _group_rows(words: list[dict]) -> list[list[dict]]:
    """Группирует слова страницы в строки по координате top."""
    buckets: dict[int, list[dict]] = {}
    for w in words:
        buckets.setdefault(round(w["top"] / _ROW_TOL), []).append(w)
    return [sorted(buckets[k], key=lambda w: w["x0"]) for k in sorted(buckets)]


def _cluster(row: list[dict], gap: float = _COL_GAP) -> list[tuple[float, float, str]]:
    """Склеивает слова строки в группы по горизонтальным зазорам → (x0, x1, текст)."""
    cols: list[tuple[float, float, list[str]]] = []
    for w in row:
        if cols and w["x0"] - cols[-1][1] <= gap:
            x0, _, parts = cols[-1]
            parts.append(w["text"])
            cols[-1] = (x0, w["x1"], parts)
        else:
            cols.append((w["x0"], w["x1"], [w["text"]]))
    return [(x0, x1, " ".join(parts)) for x0, x1, parts in cols]


def _is_header(line: str) -> bool:
    return "Услуга" in line and "Ед" in line and "изм" in line


def _price_columns(header_cols: list[tuple[float, float, str]]) -> list[tuple[float, Optional[str], str]]:
    """Из шапки достаёт ценовые колонки → (центр_x, container_type, подпись).

    Формат A: '20ф КТК (руб.)' → ('20DC'); формат B: 'Стоимость (руб.)' → (None).
    """
    out: list[tuple[float, Optional[str], str]] = []
    for x0, x1, title in header_cols[2:]:          # 0 = Услуга, 1 = Ед. изм.
        center = (x0 + x1) / 2
        m = re.match(r"(\d{2})\s*ф", title)
        ct = _COL_CONTAINER.get(m.group(1)) if m else None
        out.append((center, ct, _norm_text(title)))
    return out


def _find_unit(row: list[dict]) -> Optional[int]:
    """Индекс слова с единицей измерения ('1 ктк' → индекс 'ктк'). None, если строка не тарифная."""
    for i in range(1, len(row)):
        if not re.fullmatch(r"\d+", row[i - 1]["text"]):
            continue
        unit = row[i]["text"].strip().lower().rstrip(".")
        if unit in _UNITS:
            return i
    return None


# ─────────────────────────── Разбор страницы ───────────────────────────


def _parse_page(page, section: Optional[str]) -> tuple[list[dict], Optional[str]]:
    """Разбирает одну страницу. Возвращает (сегменты, актуальный раздел)."""
    results: list[dict] = []
    rows = _group_rows(page.extract_words(x_tolerance=_X_TOL))

    # ── 1. Классификация строк ──
    lines: list[dict] = []
    for row in rows:
        text = _norm_text(" ".join(w["text"] for w in row))
        if not text:
            continue
        kind = "text"
        if text.upper() in _SECTIONS:
            kind = "section"
        elif _NOISE_RE.search(text):
            kind = "noise"
        elif _is_header(text):
            kind = "header"
        elif _find_unit(row) is not None:
            kind = "tariff"
        lines.append({"row": row, "text": text, "top": row[0]["top"], "kind": kind})

    # ── 2. Проход по строкам: шапки задают колонки, тарифные строки дают услуги ──
    header_cols: list[tuple[float, float, str]] = []
    price_cols: list[tuple[float, Optional[str], str]] = []
    subsection: Optional[str] = None

    for idx, line in enumerate(lines):
        if line["kind"] == "section":
            section = _SECTIONS[line["text"].upper()]
            continue

        if line["kind"] == "header":
            header_cols = _cluster(line["row"])
            price_cols = _price_columns(header_cols)
            # Подзаголовок = ближайшая свободная текстовая строка выше шапки
            for prev in reversed(lines[:idx]):
                if prev["kind"] in ("tariff", "header", "section"):
                    break
                if prev["kind"] == "text" and not _is_orphan_fragment(lines, prev):
                    subsection = prev["text"]
                    break
            continue

        if line["kind"] != "tariff" or not price_cols:
            continue

        results += _parse_tariff_line(lines, idx, price_cols, section, subsection)

    return results, section


def _is_orphan_fragment(lines: list[dict], line: dict) -> bool:
    """True, если текстовая строка — перенос названия услуги (близко к тарифной строке)."""
    return any(
        other["kind"] == "tariff" and abs(other["top"] - line["top"]) <= _NAME_MAX_DY
        for other in lines
    )


def _collect_service_name(lines: list[dict], idx: int, unit_i: int) -> str:
    """Склеивает название услуги: переносы сверху + левая часть тарифной строки + переносы снизу."""
    anchor = lines[idx]
    own = " ".join(w["text"] for w in anchor["row"][: unit_i - 1])
    parts: list[tuple[float, str]] = [(anchor["top"], own)] if own else []

    for other in lines:
        if other is anchor or other["kind"] != "text":
            continue
        if abs(other["top"] - anchor["top"]) > _NAME_MAX_DY:
            continue
        # перенос принадлежит ближайшей тарифной строке
        nearest = min(
            (l for l in lines if l["kind"] == "tariff"),
            key=lambda l: abs(l["top"] - other["top"]),
        )
        if nearest is anchor:
            parts.append((other["top"], other["text"]))

    parts.sort(key=lambda p: p[0])
    return _clean_service(" ".join(p[1] for p in parts))


def _parse_tariff_line(
    lines: list[dict],
    idx: int,
    price_cols: list[tuple[float, Optional[str], str]],
    section: Optional[str],
    subsection: Optional[str],
) -> list[dict]:
    """Строит сегменты по одной тарифной строке (одна услуга × ценовые колонки)."""
    row = lines[idx]["row"]
    unit_i = _find_unit(row)
    if unit_i is None:
        return []

    unit = _UNITS[row[unit_i]["text"].strip().lower().rstrip(".")]
    service = _collect_service_name(lines, idx, unit_i)
    if not service:
        return []

    # Ячейки цен: всё правее единицы измерения, сгруппированное по зазорам
    cells = _cluster(row[unit_i + 1:])
    if not cells:
        return []

    min_t, max_t = _weights_from_name(service)
    is_storage = bool(subsection and "хранени" in subsection.lower())
    transport_type = _TT_STORAGE if is_storage else _TT_HANDLING
    point = f"{section}, Россия" if section else f"Терминал {_COMPANY}, Россия"

    out: list[dict] = []
    for cx, x1, cell_text in cells:
        center = (cx + x1) / 2
        # Ценовая колонка — ближайшая по центру
        col_center, container_type, col_title = min(
            price_cols, key=lambda c: abs(c[0] - center)
        )
        # Тип контейнера имеет смысл только при тарификации за ктк.
        # Поле обязательное, поэтому в остальных случаях ставим заглушку.
        is_container = unit in _CONTAINER_UNITS and container_type is not None
        col_is_container = bool(re.match(r"\d{2}\s*ф", col_title))
        if not is_container:
            container_type = _NON_CONTAINER_TYPE

        prices = _price_variants(cell_text)
        labels = _variant_labels(service, len(prices))

        for price, label in zip(prices, labels):
            cond = [service]
            if label:
                cond.append(label)
            cond.append(f"ед. изм.: 1 {unit}")
            if not is_container and col_is_container:
                cond.append(f"колонка: {col_title}")
            if subsection:
                cond.append(subsection)
            cond.append(_VAT)

            out.append(
                TariffSegment(
                    transport_type=transport_type,
                    start_point=point,
                    end_point=point,
                    container_type=container_type,
                    min_weight_kg=min_t,
                    max_weight_kg=max_t,
                    cost=price,
                    currency="RUB",
                    company=_COMPANY,
                    conditions="; ".join(cond),
                    start_location_type=_LOCATION_TYPE,
                    end_location_type=_LOCATION_TYPE,
                    parent_start_location=_TERMINAL_CITY,
                    parent_start_location_type="city" if _TERMINAL_CITY else None,
                    parent_end_location=_TERMINAL_CITY,
                    parent_end_location_type="city" if _TERMINAL_CITY else None,
                ).to_dict()
            )

    return out


# ─────────────────────────── Точка входа ───────────────────────────


_REQUIRED_FIELDS = ("transport_type", "start_point", "end_point", "container_type")


def _validate(results: list[dict]) -> None:
    """Ловит пустые обязательные поля до того, как упадёт TariffSegment."""
    for i, seg in enumerate(results):
        missing = [f for f in _REQUIRED_FIELDS if not seg.get(f)]
        if missing:
            raise ValueError(
                f"Сегмент #{i} без обязательных полей {missing}: "
                f"{seg.get('conditions', '')[:120]}"
            )


def parse_GrandLog_terminal(file_path: str | Path | None = None) -> list[dict]:
    """Парсит PDF «GrandLog Тамож. склад» — услуги склада и терминала."""
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("GrandLog*клад*.[pP][dD][fF]"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF ГрандЛог (склад) в директории data/. "
                "Ожидался файл по шаблону: GrandLog Тамож. склад*.pdf"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    results: list[dict] = []
    section: Optional[str] = None
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_results, section = _parse_page(page, section)
            results += page_results

    if not results:
        raise ValueError(f"Не извлечено ни одной ставки из {file_path.name}")

    _validate(results)
    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_GrandLog_terminal(*args, **kwargs))
