"""FESCO — FCDL: Китай ↔ Владивосток.

Файл: data/fcdl.pdf, срок действия с 01.08.2026 (даты окончания в прайсе нет).

Страницы 1–4 — ИМПОРТ, четыре группы портов Китая → Владивосток, FILO:
    Ningbo / Shanghai / Wenzhou
    Xingang / Rizhao
    Dalian / Lianyungang
    Yantian / Xiamen / Nansha / Shantou
Страницы 5–7 — ЭКСПОРТ, Владивосток → те же группы портов, LIFO.

В каждой таблице по 4 строки: COC и SOC × 20'DC и 40'&HC. В сегмент идёт
итоговая сумма (FILO/LIFO), включающая фрахт и терминальный сбор, —
колонки FREIGHT и DTHC/OTHC отдельно не разносятся, иначе одна ставка
превратилась бы в три.

Задание касалось только импорта, но экспортные страницы в файле есть,
и они разбираются тоже — иначе половина прайса потерялась бы.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import fesco_common as _c

_FILE = "fcdl.pdf"

_IMPORT_CONDITIONS = (
    "FCDL, импорт FILO, прямой сервис; сумма включает фрахт и DTHC в порту "
    "выгрузки; включено 10 суток Detention/Demurrage COC в Китае; "
    "не включено: бункерная надбавка, локальные сборы на стороне отправления"
)
_EXPORT_CONDITIONS = (
    "FCDL, экспорт LIFO, прямой сервис; сумма включает фрахт и OTHC в порту "
    "погрузки; ставки включают российский THC и 15 суток пользования "
    "контейнером линии; не включено: бункерная надбавка 25/50 USD"
)


def _parse_table(table: list, direction: str, valid_from, valid_to) -> list[dict]:
    """Разбирает таблицу вида «DIRECTION | STATUS | OWNER | TYPE | ... | FILO».

    Ячейка направления объединена по вертикали, поэтому порты и
    принадлежность запоминаются и переносятся на следующие строки.
    """
    # Строка заголовка не всегда первая: на экспортных страницах перед ней
    # идёт «Bi-lateral Cargo», и table[0] — пустая шапка.
    head_row = next(
        (i for i, row in enumerate(table)
         if "DIRECTION" in " ".join(_c.text(c).upper() for c in row)),
        None,
    )
    if head_row is None:
        return []

    total_idx = None
    for i, cell in enumerate(table[head_row]):
        name = _c.text(cell).upper().replace(" ", "")
        if name.startswith(("FILO", "LIFO")):
            total_idx = i
            break
    if total_idx is None:
        return []

    # Направление собираем по ВСЕЙ таблице заранее: ячейка разбита на
    # несколько строк («Vladivostok -» / «Shanghai/Xingang/Rizhao/»), причём
    # порты появляются ниже строк COC. Разбор построчно терял бы их.
    direction_text = " ".join(
        _c.text(row[0]) for row in table[head_row + 1:]
        if row and _c.text(row[0]) and not _c.text(row[0]).startswith("General")
    )
    parts = re.split(r"\s+[-–]\s*", direction_text, maxsplit=1)
    china_part = parts[1] if direction == "export" and len(parts) > 1 else parts[0]
    ports = [p for p in _c.split_ports(china_part) if p[1] != "Россия"]

    results: list[dict] = []
    ownership = "COC"

    for row in table[head_row + 1:]:
        cells = [_c.text(c) for c in row]
        if len(cells) <= total_idx:
            continue

        found_own = _c.normalize_ownership(cells[2]) if len(cells) > 2 else None
        if found_own:
            ownership = found_own

        container_type = _c.normalize_container(cells[3]) if len(cells) > 3 else None
        cost = _c.parse_price(cells[total_idx])
        if not ports or not container_type or cost is None:
            continue

        for port_ru, country in ports:
            if direction == "import":
                kw = dict(start_point=port_ru, start_country=country,
                          end_point="Владивосток", end_country="Россия")
                term, conditions = "FILO", _IMPORT_CONDITIONS
            else:
                kw = dict(start_point="Владивосток", start_country="Россия",
                          end_point=port_ru, end_country=country)
                term, conditions = "LIFO", _EXPORT_CONDITIONS
            results.append(_c.make_sea(
                container_type=container_type, ownership=ownership, cost=cost,
                term=term, conditions=conditions,
                valid_from=valid_from, valid_to=valid_to, **kw,
            ))
    return results


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс FCDL и возвращает список сегментов."""
    path = _c.resolve_path(file_path) if file_path else _c.find_file(_FILE)
    if path is None or not Path(path).exists():
        print(f"  [FESCO FCDL] файл не найден: {file_path or _FILE}")
        return []

    with pdfplumber.open(path) as pdf:
        pages = [((pg.extract_text() or ""), pg.extract_tables()) for pg in pdf.pages]

    full_text = "\n".join(t for t, _ in pages)
    valid_from, valid_to = _c.parse_validity(full_text)

    results: list[dict] = []
    for page_text, tables in pages:
        # Направление определяем по заголовку страницы: «service from
        # Vladivostok to ...» — экспорт, иначе импорт.
        head = page_text[:200].upper()
        direction = "export" if re.search(r"FROM\s+VLADIVOSTOK", head) else "import"

        for table in tables:
            if not table or len(table) < 2:
                continue
            flat = " ".join(_c.text(c).upper() for row in table for c in row)
            if "DIRECTION" not in flat:
                continue
            results += _parse_table(table, direction, valid_from, valid_to)

    imp = sum(1 for r in results if r["end_point"].startswith("Владивосток"))
    print(f"  [FESCO FCDL] сегментов: {len(results)} "
          f"(импорт {imp}, экспорт {len(results)-imp}), период {valid_from}..{valid_to}")
    return _to_segments(results)
