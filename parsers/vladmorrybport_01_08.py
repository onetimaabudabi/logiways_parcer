"""Парсер ОАО «Владморрыбпорт» — «Тарифы укп с 01.08.2026.pdf».

Отдельный модуль под один прайс. Существующий `parsers/vladmorrybport.py`
не изменяется — отсюда переиспользуются только его вспомогательные функции
(OCR, разбор строк таблицы, справочник станций).

ВАЖНО: файл — СКАН без текстового слоя (`extract_text()` возвращает пустую
строку, `extract_tables()` — ноль таблиц), поэтому используется OCR.
Требуются tesseract-ocr, языковой пакет rus и poppler-utils:
    apt install tesseract-ocr tesseract-ocr-rus poppler-utils

Структура таблицы (страница 2):
    Станция назначения | 20 фут. (до 24т) | 20 фут. (24–28т) | 40 фут. (до 28т)
                       | Охрана 20 фут.   | Охрана 40 фут.
Города-заголовки со сносками, под ними станции:
    Москва¹        — Белый Раст, Электроугли, Селятино, Ворсино,
                     Люберцы 2, Раменское
    Екатеринбург²  — Екатеринбург-Товарный
    Новосибирск³   — Клещиха
    Санкт-Петербург⁴ — Шушары, Заневский Пост
    Тольятти⁵      — Тольятти
Ставки охраны в отдельные сегменты не выносятся: это доплата, она уходит
в conditions.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from .models import TariffSegment
from .utils import to_segments as _to_segments
# Переиспользуем готовые помощники основного модуля ВМРП, чтобы не плодить
# копии логики OCR и разбора строк.
from .vladmorrybport import (
    _CATS,
    _CITY_HEADERS,
    _clean_station,
    _extract_valid_from,
    _guard_note,
    _make_segment,
    _ocr_pages,
    _parse_rate_line,
    _resolve_path,
    _station_city,
    _text,
)

# Год в имени файла есть, но дату берём из текста («действующие с 01 августа
# 2026 г.»); имя файла — запасной вариант.
_FALLBACK_VALID_FROM = "2026-08-01"

# Замены артефактов OCR в названиях станций.
_OCR_STATION_FIX = {
    "Екатеринбург-Говарный": "Екатеринбург-Товарный",
    "Екатеринбург-Говарньй": "Екатеринбург-Товарный",
}


def _fix_station(name: str) -> str:
    """Чинит типичные ошибки OCR и мусорные хвосты в названии станции."""
    clean = _OCR_STATION_FIX.get(name, name)
    # «Люберцы 2 -» → «Люберцы 2»: висячий дефис/точка после названия
    clean = re.sub(r"[\s\-–—.,;:]+$", "", clean).strip()
    return clean


def _is_garbage(name: str) -> bool:
    """True для нечитаемых OCR-заголовков вроде «ый» вместо «Тольятти»."""
    if not name:
        return True
    return (
        len(name) <= 3
        or bool(re.fullmatch(r"(.)\1*", name, re.IGNORECASE))
        or not re.search(r"[аеёиоуэюяaeiouy]", name, re.IGNORECASE)
    )


_CONDITIONS = (
    "УКП для контейнеров, прибывших с моря на терминал ОАО «Владморрыбпорт»; "
    "включено: услуги склада при выдаче на ЖД, ЗПУ, оформление ГУ-12 и "
    "перевозочных документов, провозные платежи, подвижной состав, "
    "терминальная обработка по станции отправления; тариф без НДС"
)


def _valid_from_file_name(file_name: str) -> Optional[str]:
    """'Тарифы укп с 01.08.2026.pdf' → '2026-08-01'."""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", unicodedata.normalize("NFC", file_name))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _parse_table(pages: list[str], valid_from: Optional[str]) -> list[dict]:
    """Разбирает таблицу: город-заголовок, под ним станции, ставки в строке."""
    results: list[dict] = []
    city: Optional[str] = None
    stations: list[str] = []
    values: list[float] = []
    pending_garbage = False

    def flush():
        nonlocal stations, values
        if city and values:
            for station in stations or [_fix_station(city)]:
                for (container_type, min_w, max_w), cost in zip(_CATS, values):
                    results.append(
                        _make_segment(
                            station=station,
                            city=city,
                            container_type=container_type,
                            min_weight=min_w,
                            max_weight=max_w,
                            cost=cost,
                            conditions=_CONDITIONS + _guard_note(values),
                            valid_from=valid_from,
                        )
                    )
        stations, values = [], []

    started = False
    for raw in "\n".join(pages).split("\n"):
        line = _text(raw)
        if not line:
            continue
        if re.search(r"Станция назначения", line, re.IGNORECASE):
            started = True
            continue
        if not started:
            continue
        if re.search(r"Тарифы включают|Тарифы указаны|Отправка в режиме", line, re.I):
            break

        label, found = _parse_rate_line(line)
        clean = _clean_station(label)
        # Сноски OCR читает как «Екатеринбург”», «Новосибирск°» — сравниваем
        # по «голому» названию без хвоста.
        bare = re.sub(r"[^А-ЯЁA-Z -]", "", clean.upper()).strip()
        header = _CITY_HEADERS.get(clean.upper()) or _CITY_HEADERS.get(bare)

        if header:
            # Если предыдущей строкой был нечитаемый заголовок, её ставки
            # относятся к ЭТОМУ блоку («ый | 185 000 …» + «ст. Тольятти»),
            # поэтому flush() здесь обнулил бы их и Тольятти терялся.
            if pending_garbage and values and not found:
                city, pending_garbage = header, False
                continue
            flush()
            city = header
            if found:
                values = found
            continue

        # Нечитаемый заголовок («ый» вместо «Тольятти») закрывает предыдущий
        # блок: без этого его ставки перезаписали бы ставки Санкт-Петербурга.
        if _is_garbage(clean):
            saved = found or values
            flush()
            city, values, pending_garbage = None, saved, True
            continue

        if not city:
            # Заголовок города OCR не прочитал — восстанавливаем по станции.
            if clean and (found or values or pending_garbage):
                city = _station_city(clean) or clean
                pending_garbage = False
                if found:
                    values = found
            continue

        if clean and re.search(r"[А-Яа-яЁё]", clean):
            stations.append(_fix_station(clean))
        if found:
            values = found

    flush()
    return results


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит PDF «Тарифы укп с 01.08.2026» и возвращает список сегментов.

    Если таблица не найдена или OCR недоступен, возвращает пустой список,
    а не роняет прогон.
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = sorted(
            p for p in data_dir.glob("*.pdf")
            if re.search(r"тарифы\s+укп\s+с\s+01\.08",
                         unicodedata.normalize("NFC", p.name), re.IGNORECASE)
        )
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF «Тарифы укп с 01.08.2026.pdf» в директории data/"
            )
        file_path = matches[-1]
    else:
        file_path = _resolve_path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    print(f"  [ВМРП 01.08] OCR: {file_path.name}")
    try:
        pages = _ocr_pages(file_path)
    except Exception as e:
        print(f"  [ВМРП 01.08] OCR недоступен: {e}")
        return _to_segments([])

    text = "\n".join(pages)
    valid_from = (
        _extract_valid_from(text)
        or _valid_from_file_name(file_path.name)
        or _FALLBACK_VALID_FROM
    )

    results = _parse_table(pages, valid_from)
    if not results:
        print(f"  [ВМРП 01.08] тарифная таблица не найдена в {file_path.name}")
    else:
        print(f"  [ВМРП 01.08] сегментов: {len(results)}, valid_from={valid_from}")
    return _to_segments(results)
