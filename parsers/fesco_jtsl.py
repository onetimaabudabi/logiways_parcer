"""FESCO — JTSL (Japan Trans Siberian Line): Япония ↔ Владивосток.

Файл: data/jtsl.pdf, срок действия с 01.08.2026 (даты окончания в прайсе нет).

Страница 1 — направление W/B (Япония → Владивосток), две таблицы:
    «DESTINATION TO VVO (LOCAL DELIVERY)»       → МОРСКИЕ сегменты
    «DESTINATION TO INLAND USING RAILWAY»       → ЖЕЛЕЗНОДОРОЖНЫЕ сегменты
Страницы 2–4 — направление E/B (Владивосток → Иокогама/Кобе, Нагоя,
    Тояма), морские сегменты.

ВАЖНО про ЖД-часть. Во второй таблице колонки FREIGHT и DTHC повторяют
первую таблицу — это то же морское плечо. Отличается только колонка ONC
(railway delivery acceptance): 750 USD за 20', 1000 USD за 40'. Именно она
и берётся как стоимость железнодорожного сегмента Владивосток → Москва,
иначе стоимость морского плеча задвоилась бы. У SOC-строк в колонке ONC
стоит прочерк — для них ЖД-сегмент не создаётся.

В самом прайсе станция назначения не названа («ALL CITIES»), Москва взята
по договорённости; при необходимости меняется в константе _RAIL_DESTINATION.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import fesco_common as _c

_FILE = "jtsl.pdf"

# Пункт назначения ЖД-плеча: в прайсе указано «ALL CITIES», конкретной
# станции нет.
_RAIL_DESTINATION = "Москва"

_SEA_WB_CONDITIONS = (
    "JTSL, импорт Япония – Владивосток, местная выдача; в сумму включён "
    "DTHC в порту выгрузки; не включено: OTHC в порту погрузки "
    "(JPY 40 000/20', JPY 55 000/40'), seal fee JPY 2 000, doc fee JPY 8 800/BL, "
    "надбавка за опасный груз 250–1000 USD"
)
_SEA_EB_CONDITIONS = (
    "JTSL, экспорт Владивосток – Япония, прямой и трансшипмент; в сумму "
    "включён OTHC; ставки включают LSS, российский THC и BAF; "
    "не включено: THC в порту выгрузки, бункерная надбавка 25/50 USD, "
    "надбавка за опасный груз 250–1000 USD"
)
_RAIL_CONDITIONS = (
    "JTSL, ЖД-плечо (ONC — railway delivery acceptance); оплачивается вместе "
    "с DTHC грузополучателем; в прайсе станция назначения не конкретизирована "
    "(ALL CITIES)"
)


def _column_index(header: list) -> dict:
    """Номера колонок по ключевым словам, а не по точному совпадению.

    На страницах E/B шапка побита при извлечении («ne 202P6OL» вместо «POL»),
    поэтому ищем вхождение слова, а не равенство.
    """
    idx: dict = {}
    for i, cell in enumerate(header):
        name = _c.text(cell).upper()
        if "TOTAL" in name and "FREIGHT" in name:
            idx.setdefault("TOTAL", i)
        elif "ONC" in name:
            idx.setdefault("ONC", i)
        elif "CONTAINER" in name:
            idx.setdefault("CONTAINER", i)
        elif "POD" in name:
            idx.setdefault("POD", i)
        elif re.search(r"P\d*O\d*L", name):
            # «P6OL»: в шапку вклеился номер страницы («Valid from 25th of
            # June 2026» + «POL» → «ne 202P6OL»), поэтому цифры допускаются.
            idx.setdefault("POL", i)

    # Запасной вариант: POL — колонка слева от POD.
    if "POL" not in idx and idx.get("POD", 0) > 0:
        idx["POL"] = idx["POD"] - 1
    return idx


def _parse_rate_rows(table: list, header: list | None = None) -> list[dict]:
    """Собирает строки таблицы: POL, POD, тип, принадлежность, суммы.

    Если header передан отдельно, вся таблица считается строками данных:
    на страницах E/B шапка лежит в отдельной таблице, а данные — в следующей.
    """
    if header is None:
        header, body = table[0], table[1:]
    else:
        body = table
    idx = _column_index(header)
    rows: list[dict] = []
    pols: list[tuple[str, str]] = []
    pods: list[tuple[str, str]] = []

    for row in body:
        cells = [_c.text(c) for c in row]
        if len(cells) < 5:
            continue
        # POL и POD заполнены только в первой строке блока
        if idx.get("POL") is not None and cells[idx["POL"]]:
            found = _c.split_ports(cells[idx["POL"]])
            if found:
                pols = found
        if idx.get("POD") is not None and cells[idx["POD"]]:
            # POD тоже может содержать несколько портов: «Yokohama/ Kobe»
            found = _c.split_ports(cells[idx["POD"]])
            if found:
                pods = found
        if not pols or not pods:
            continue

        container_cell = cells[idx["CONTAINER"]] if idx.get("CONTAINER") is not None else ""
        container_type = _c.normalize_container(container_cell)
        ownership = _c.normalize_ownership(container_cell)
        if not container_type or not ownership:
            continue

        rows.append({
            "pols": pols, "pods": pods,
            "container_type": container_type, "ownership": ownership,
            "total": (_c.parse_price(cells[idx["TOTAL"]])
                      if idx.get("TOTAL") is not None and idx["TOTAL"] < len(cells) else None),
            "onc": (_c.parse_price(cells[idx["ONC"]])
                    if idx.get("ONC") is not None and idx["ONC"] < len(cells) else None),
        })
    return rows


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс JTSL и возвращает список сегментов."""
    path = _c.resolve_path(file_path) if file_path else _c.find_file(_FILE)
    if path is None or not Path(path).exists():
        print(f"  [FESCO JTSL] файл не найден: {file_path or _FILE}")
        return []

    with pdfplumber.open(path) as pdf:
        pages = [((pg.extract_text() or ""), pg.extract_tables()) for pg in pdf.pages]

    full_text = "\n".join(t for t, _ in pages)
    valid_from, valid_to = _c.parse_validity(full_text)

    results: list[dict] = []
    for page_text, tables in pages:
        inland = "INLAND USING RAILWAY" in page_text.upper()
        local = "LOCAL DELIVERY" in page_text.upper()

        pending_header = None
        for table in tables:
            if not table:
                continue
            head_line = " ".join(_c.text(c).upper() for c in table[0])
            is_header_only = (len(table) == 1
                              and "CONTAINER" in head_line and "FREIGHT" in head_line)
            if is_header_only:
                # Шапка лежит отдельной таблицей — запоминаем для следующей
                pending_header = table[0]
                continue

            if pending_header is not None:
                header_cells, rows_source = pending_header, table
                pending_header = None
            elif "CONTAINER" in head_line and "FREIGHT" in head_line and len(table) > 1:
                header_cells, rows_source = None, table
            else:
                continue

            head_text = " ".join(_c.text(c).upper() for c in (header_cells or table[0]))
            is_rail_table = "ONC" in head_text
            for row in _parse_rate_rows(rows_source, header_cells):
                if is_rail_table:
                    # ЖД-сегмент: стоимость — только ONC, без морского фрахта
                    if row["onc"] is None:
                        continue
                    results.append(_c.make_rail(
                        start_point="Владивосток", start_city="Владивосток",
                        end_point=_RAIL_DESTINATION, end_city=_RAIL_DESTINATION,
                        container_type=row["container_type"],
                        ownership=row["ownership"], cost=row["onc"],
                        currency="USD", conditions=_RAIL_CONDITIONS,
                        valid_from=valid_from, valid_to=valid_to,
                    ))
                    continue

                if row["total"] is None:
                    continue
                # Направление уже задано колонками POL/POD, менять местами
                # ничего не нужно: на W/B слева японские порты, на E/B —
                # Владивосток. Флаг нужен только для текста условий.
                eastbound = row["pols"][0][1] == "Россия"
                conditions = _SEA_EB_CONDITIONS if eastbound else _SEA_WB_CONDITIONS
                for (start, start_c) in row["pols"]:
                    for (end, end_c) in row["pods"]:
                        results.append(_c.make_sea(
                            start_point=start, start_country=start_c,
                            end_point=end, end_country=end_c,
                            container_type=row["container_type"],
                            ownership=row["ownership"], cost=row["total"],
                            term="FILO", conditions=conditions,
                            valid_from=valid_from, valid_to=valid_to,
                        ))

    sea = sum(1 for r in results if r["transport_type"] == "sea")
    print(f"  [FESCO JTSL] сегментов: {len(results)} (море {sea}, ЖД {len(results)-sea}), "
          f"период {valid_from}..{valid_to}")
    return _to_segments(results)
