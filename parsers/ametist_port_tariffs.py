"""Парсер «Ametist Line» — каталог портовых тарифов (услуги терминалов).

Файл: data/Ametists_port_tariffs_catalog_08042026_incl_Isr.pdf

Одна страница = один порт. Заголовок страницы:
    March 2026 / Version 1.5
    Russia, Novorossiysk,
    NLE (Novoroslesexport) – Port tariff

Разделы страницы: Terminal Handling Charge, Storage Tariffs, Demurrage Tariffs,
Detention Tariffs, Demurrage/ Detention Tariffs. Направление берётся либо из
подписи «Export:» / «Import storage Tariffs:», либо из скобок в названии
раздела — «Storage Tariffs (export)».

Это прайс на услуги, а не на перевозку: маршрута нет, поэтому
transport_type = "service", а start_point == end_point == порт.
Название услуги, период и терминал уходят в conditions.

Таблицы свёрстаны в две колонки, а pdfplumber при extract() «съезжает»
по объединённым ячейкам и иногда теряет значения. Поэтому содержимое берётся
не из extract(), а из слов внутри bbox таблицы: слова группируются в строки,
строки — в ячейки по горизонтальным зазорам, а заголовки колонок (они бывают
разбиты на 2-3 строки, например «IMO surcharge 20 DC») привязываются к колонкам
по координате X.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import container_size_dict, get_country, port_dict

_COMPANY = "Ametist Line"
_TT_SERVICE = "service"
_LOCATION_TYPE = "port"

# Параметры разбора координат
_ROW_TOL = 3.0    # допуск группировки слов в строку по координате top
_COL_GAP = 8.0    # минимальный зазор между ячейками (внутри ячейки ≈ 2.8 pt)

_MONTHS_EN = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Заголовки разделов (сравнение по строке без пробелов, в нижнем регистре).
# «Demurrag e Tariffs» на стр. Новороссийска — не опечатка, так извлекается PDF.
_SECTIONS = (
    ("demurrage/detentiontariffs", "Демередж/детеншн"),
    ("terminalhandlingcharge", "THC (терминальная обработка)"),
    ("storagetariffs", "Хранение"),
    ("demurragetariffs", "Демередж"),
    ("detentiontariffs", "Детеншн"),
)

_SUBLABEL_RE = re.compile(r"^(export|import)\b.*:$", re.IGNORECASE)
_HEADER_NOISE_RE = re.compile(r"^(period|service)$", re.IGNORECASE)

# Ячейка со значением: 'free', '-', '150 USD', '2 540 RUB', '37,50 USD'
_VALUE_RE = re.compile(
    r"^(free|-|–|—|\d[\d\s.,]*\s*(?:USD|RUB|EUR))$", re.IGNORECASE
)

_CURRENCY_RE = re.compile(r"\b(USD|RUB|EUR)\b", re.IGNORECASE)

_KIND_CODES = {
    "DC": ["DC"], "GP": ["DC"], "HC": ["HC"], "TC": ["TC"],
    "REEF": ["RF"], "RF": ["RF"],
    "OOG": ["FR", "OT"], "OT/FR": ["OT", "FR"], "FR/OT": ["FR", "OT"],
    "OT": ["OT"], "FR": ["FR"],
}
_KIND_RE = re.compile(r"(20|40)\s*(DC|GP|HC|TC|REEF|RF|OOG|OT/FR|FR/OT|OT|FR)")

_ALL_OOG = ["20FR", "20OT", "40FR", "40OT"]

# Города-«родители» для портов (в shared.port_city_dict их нет).
# Амбарли и Гебзе привязаны к Стамбулу — как в parsers/ametist_line.py.
_PARENT_CITY = {
    "Амбарли": "Стамбул",
    "Гебзе": "Стамбул",
}


# ─────────────────────────── Вспомогательные функции ───────────────────────────


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _key(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _parse_price(val) -> Optional[float]:
    """'2 540 RUB' → 2540.0; '37,50 USD' → 37.5; 'free' → 0.0; '-' → None."""
    s = _norm(val)
    if not s or s in {"-", "–", "—"}:
        return None
    if s.lower() == "free":
        return 0.0
    body = re.sub(r"[A-Za-z]", "", s).replace(" ", "").replace("\xa0", "")
    body = body.replace(",", ".")
    if body.count(".") > 1:  # разделитель тысяч, а не дробная часть
        body = body.replace(".", "")
    try:
        return float(body)
    except ValueError:
        return None


def _currency(val) -> str:
    s = _norm(val).upper()
    for code in ("RUB", "EUR", "USD"):
        if code in s:
            return code
    return "USD"


def _translate_port(raw: str) -> str:
    raw = _norm(raw)
    for key in (raw, raw.title(), raw.upper()):
        if key in port_dict:
            return port_dict[key]
    return raw


def _point(port_ru: str) -> str:
    country = get_country(port_ru) or ""
    return f"{port_ru}, {country}".rstrip(", ")


_PERIOD_RE = re.compile(r"\d|\bday\b|\bdays\b|\bover\b|\beta\b", re.IGNORECASE)


def _is_period(label: str) -> bool:
    """Отличает подпись периода ('8-14 days') от названия услуги ('THC IMO')."""
    return bool(_PERIOD_RE.search(label or ""))


def _period_ru(raw: str) -> str:
    """'Over 30 days' → 'свыше 30 дней'; 'From 1st day' → 'с 1-го дня'."""
    text = _norm(raw)
    text = re.sub(r"^From 1st day$", "с 1-го дня", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOver\b", "свыше", text, flags=re.IGNORECASE)
    text = re.sub(r"\bbefore ETA\b", "до ETA", text, flags=re.IGNORECASE)
    text = re.sub(r"\bdays?\b", "дней", text, flags=re.IGNORECASE)
    return text


def _container_types(label: str) -> tuple[list[str], list[str]]:
    """
    Заголовок колонки → (типы контейнеров, пометки для conditions).

    '20 DC'                    → (['20DC'], [])
    '20 OT/FR'                 → (['20OT', '20FR'], [])
    'IMO surcharge 40 HC'      → (['40HC'], ['IMO', 'надбавка'])
    '40 REEF/special equipment'→ (['40RF'], ['спецоборудование'])
    'Empties'                  → (['20DC', '40HC'], ['порожний контейнер'])
    """
    text = _norm(label).upper()
    notes: list[str] = []

    if "EMPTIES" in text:
        return ["20DC", "40HC"], ["порожний контейнер"]
    if "IMO" in text:
        notes.append("IMO")
        text = text.replace("IMO", " ")
    if "SURCHARGE" in text:
        notes.append("надбавка")
        text = text.replace("SURCHARGE", " ")
    if "SPECIAL EQUIPMENT" in text:
        notes.append("спецоборудование")
        text = text.replace("SPECIAL EQUIPMENT", " ")

    types: list[str] = []
    for size, kind in _KIND_RE.findall(text):
        for code in _KIND_CODES[kind]:
            ct = f"{size}{code}"
            if ct not in types:
                types.append(ct)

    if not types:
        if "REEF" in text and ("FR" in text or "OT" in text):
            # колонка «REEF/ FR/OT» — единая ставка на рефы и негабарит
            types = ["20RF", "40RF"] + _ALL_OOG
        elif "OOG" in text:
            types = list(_ALL_OOG)
        elif "надбавка" in notes:
            # одиночная колонка «IMO surcharge» без указания типа
            types = ["20DC", "40HC"]

    return types, notes


# ─────────────────────────── Чтение слов и ячеек ───────────────────────────


def _lines(container) -> list[list[dict]]:
    """Слова области → строки (группировка по top, сортировка по x0)."""
    words = container.extract_words(x_tolerance=1.5)
    words.sort(key=lambda w: (w["top"], w["x0"]))

    rows: list[list[dict]] = []
    for word in words:
        if rows and abs(word["top"] - rows[-1][0]["top"]) <= _ROW_TOL:
            rows[-1].append(word)
        else:
            rows.append([word])
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    return rows


def _cells(row: list[dict]) -> list[dict]:
    """Слова строки → ячейки: новая ячейка начинается после зазора _COL_GAP."""
    cells: list[dict] = []
    for word in row:
        if cells and word["x0"] - cells[-1]["x1"] < _COL_GAP:
            cells[-1]["text"] += " " + word["text"]
            cells[-1]["x1"] = word["x1"]
        else:
            cells.append({"text": word["text"], "x0": word["x0"], "x1": word["x1"]})
    return cells


def _split_row(row: list[dict]) -> Optional[tuple[str, list[dict]]]:
    """Строка данных → (подпись периода/услуги, ячейки со значениями)."""
    cells = _cells(row)
    values = [c for c in cells if _VALUE_RE.match(_norm(c["text"]))]
    if not values:
        return None
    # значения всегда идут сплошным блоком справа
    first_value = cells.index(values[0])
    label = " ".join(c["text"] for c in cells[:first_value])
    return _norm(label), cells[first_value:]


def _column_headers(header_rows: list[list[dict]], values: list[dict]) -> list[str]:
    """
    Привязывает слова заголовка к колонкам по X.

    Границы колонок — середины между центрами ячеек-значений; слова левее
    первой границы («Service», «Period», «Export:») отбрасываются.
    """
    centers = [(c["x0"] + c["x1"]) / 2 for c in values]
    if len(centers) > 1:
        half = min(centers[i + 1] - centers[i] for i in range(len(centers) - 1)) / 2
    else:
        half = max(values[0]["x1"] - values[0]["x0"], 30.0)
    left, right = centers[0] - half, centers[-1] + half

    parts: list[list[str]] = [[] for _ in centers]
    for row in header_rows:
        for word in row:
            text = _norm(word["text"])
            if _HEADER_NOISE_RE.match(text) or _SUBLABEL_RE.match(text):
                continue
            center = (word["x0"] + word["x1"]) / 2
            if center < left or center > right:
                continue
            idx = min(range(len(centers)), key=lambda i: abs(centers[i] - center))
            parts[idx].append(text)

    return [" ".join(p) for p in parts]


# ─────────────────────────── Контекст страницы ───────────────────────────


def _page_context(page) -> dict:
    """Порт, страна, терминал и дата версии каталога со шапки страницы."""
    text = page.extract_text() or ""
    lines = [_norm(l) for l in text.split("\n") if _norm(l)]

    port_ru, terminal = None, None
    for i, line in enumerate(lines[:8]):
        m = re.match(r"^([A-Za-z]+),\s*([A-Za-z][A-Za-z\s]*),$", line)
        if m:
            port_ru = _translate_port(m.group(2))
            if i + 1 < len(lines):
                terminal = re.sub(r"\s*[–-]\s*Port tariff.*$", "", lines[i + 1]).strip()
            break

    valid_from = None
    m = re.search(r"\b([A-Za-z]+)\s+(\d{4})\b", text)
    if m and m.group(1).lower() in _MONTHS_EN:
        valid_from = f"{m.group(2)}-{_MONTHS_EN[m.group(1).lower()]}-01"

    return {"port": port_ru, "terminal": terminal, "valid_from": valid_from}


def _page_markers(page) -> tuple[list[dict], list[dict]]:
    """Заголовки разделов и подписи «Export:/Import:» с координатами."""
    sections: list[dict] = []
    sublabels: list[dict] = []

    for row in _lines(page):
        # Подписи «Export storage Tariffs:» и «Import storage Tariffs:» стоят
        # на одной визуальной строке, поэтому разбираем строку по ячейкам.
        for cell in _cells(row):
            text = _norm(cell["text"])
            top, x0 = row[0]["top"], cell["x0"]

            if _SUBLABEL_RE.match(text):
                sublabels.append({"top": top, "x0": x0,
                                  "direction": text.split()[0].rstrip(":").lower()})
                continue

            key = _key(text)
            for marker, name in _SECTIONS:
                if marker in key:
                    scope = re.search(r"\(([^)]*)\)", text)
                    sections.append({
                        "top": top,
                        "name": name,
                        "scope": _norm(scope.group(1)) if scope else "",
                    })
                    break

    sections.sort(key=lambda s: s["top"])
    return sections, sublabels


def _direction_ru(raw: str) -> Optional[str]:
    raw = (raw or "").lower()
    if "export" in raw and "import" in raw:
        return "экспорт/импорт"
    if "export" in raw:
        return "экспорт"
    if "import" in raw:
        return "импорт"
    return None


def _context_for(table, sections: list[dict], sublabels: list[dict]) -> tuple[str, Optional[str], str]:
    """(название раздела, направление, уточнение в скобках) для таблицы."""
    x0, top, x1, _bot = table.bbox
    above = [s for s in sections if s["top"] < top + 4]
    section = above[-1] if above else None
    if not section:
        return "", None, ""

    scope = section["scope"]
    direction = _direction_ru(scope)
    extra = "" if direction else scope   # уточнение вида «(Damietta)», «(AICT)»

    candidates = [s for s in sublabels if section["top"] < s["top"] < top + 4]
    if candidates:
        last_top = max(s["top"] for s in candidates)
        same_line = [s for s in candidates if abs(s["top"] - last_top) <= _ROW_TOL]
        chosen = min(same_line, key=lambda s: abs(s["x0"] - x0))
        direction = _direction_ru(chosen["direction"]) or direction

    return section["name"], direction, extra


# ─────────────────────────── Разбор таблицы ───────────────────────────


def _parse_table(page, table, context: dict, section: str,
                 direction: Optional[str], extra: str) -> list[dict]:
    x0, top, x1, bot = table.bbox
    crop = page.crop((
        max(0, x0 - 2), max(0, top - 2),
        min(page.width, x1 + 2), min(page.height, bot + 2),
    ))

    rows = _lines(crop)
    parsed = [(row, _split_row(row)) for row in rows]

    # Валюта таблицы: у ячеек «free» её нет, берём из первой ставки с суммой
    table_currency = "USD"
    priced = [
        c["text"] for _row, split in parsed if split
        for c in split[1] if _CURRENCY_RE.search(c["text"])
    ]
    if priced:
        table_currency = _currency(priced[0])

    port_ru = context["port"]
    point = _point(port_ru)
    parent = _PARENT_CITY.get(port_ru, port_ru)

    results: list[dict] = []
    header_rows: list[list[dict]] = []
    headers: list[str] = []
    columns_width = 0

    for row, split in parsed:
        if split is None:
            # строка заголовка: сбрасываем колонки, если это новая шапка
            text = _norm(" ".join(w["text"] for w in row))
            if _HEADER_NOISE_RE.match(text) or not headers:
                if _key(text).startswith(("period", "service")) and headers:
                    header_rows, headers = [], []
                header_rows.append(row)
            elif re.match(r"^(period|service)\b", text, re.IGNORECASE):
                header_rows, headers = [row], []
            else:
                header_rows.append(row)
            continue

        label, values = split

        # шапка «Period ...» может стоять в одной строке с названиями колонок
        if headers and len(values) != columns_width:
            headers = []
        if not headers:
            rows_for_header = header_rows + ([row] if label else [])
            headers = _column_headers(rows_for_header, values)
            columns_width = len(values)
            header_rows = []

        for header, cell in zip(headers, values):
            price = _parse_price(cell["text"])
            if price is None:
                continue
            types, notes = _container_types(header)
            if not types:
                print(f"[ametist_port_tariffs] не распознан тип контейнера: "
                      f"{port_ru} / {section} / {header!r}")
                continue

            conditions = [section]
            if direction:
                conditions.append(direction)
            if extra:
                conditions.append(extra)
            if _is_period(label):
                conditions.append(f"период: {_period_ru(label)}")
            else:
                # строка THC-таблицы: 'THC' или 'THC IMO'
                rest = re.sub(r"^(THC|Service)\b", "", label, flags=re.IGNORECASE).strip()
                if rest and rest.upper() != "IMO":
                    conditions.append(rest)
            if "IMO" in label.upper() and "IMO" not in notes:
                notes = notes + ["IMO"]
            conditions += notes
            if context["terminal"]:
                conditions.append(f"терминал: {context['terminal']}")

            currency = _currency(cell["text"]) if _CURRENCY_RE.search(cell["text"]) \
                else table_currency

            for container_type in types:
                results.append(
                    TariffSegment(
                        transport_type=_TT_SERVICE,
                        start_point=point,
                        end_point=point,
                        container_type=container_type,
                        cost=price,
                        currency=currency,
                        company=_COMPANY,
                        conditions="; ".join(conditions),
                        valid_from=context["valid_from"],
                        start_location_type=_LOCATION_TYPE,
                        end_location_type=_LOCATION_TYPE,
                        parent_start_location=parent,
                        parent_start_location_type="city",
                        parent_end_location=parent,
                        parent_end_location_type="city",
                        weight_limit=container_size_dict.get(container_type),
                    ).to_dict()
                )

    return results


def _parse_page(page) -> list[dict]:
    context = _page_context(page)
    if not context["port"]:
        return []

    sections, sublabels = _page_markers(page)

    results: list[dict] = []
    for table in page.find_tables():
        section, direction, extra = _context_for(table, sections, sublabels)
        if not section:
            continue
        results += _parse_table(page, table, context, section, direction, extra)
    return results


# ─────────────────────────── Точка входа ───────────────────────────


def parse_AmetistPortTariffs(file_path: str | Path | None = None) -> list[dict]:
    """Парсит каталог портовых тарифов Ametist Line."""
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = sorted(data_dir.glob("Ametist*port_tariffs*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF портовых тарифов Ametist Line в data/. Ожидался файл "
                "по шаблону: Ametists_port_tariffs_catalog_*.pdf"
            )
        file_path = matches[-1]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    results: list[dict] = []
    ports: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_results = _parse_page(page)
            if page_results:
                port = page_results[0]["start_point"].split(",")[0]
                if port not in ports:
                    ports.append(port)
            results += page_results

    print(
        f"[ametist_port_tariffs] сегментов: {len(results)}; "
        f"портов: {len(ports)} ({', '.join(ports)})"
    )
    print(
        "[ametist_port_tariffs] ПРИМЕЧАНИЕ: send_api_New.py пропускает строки с "
        "transport_type='service' (NON_TRANSPORT_TYPES) — на сервер как сегменты "
        "маршрута они не уйдут; это прайс услуг для выгрузки в charges/policies."
    )
    return results


def parse(*args, **kwargs) -> list[TariffSegment]:
    """Точка входа парсера."""
    return _to_segments(parse_AmetistPortTariffs(*args, **kwargs))
