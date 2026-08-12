"""«Гарант Интермодал» — COC импорт/экспорт с Drop Off (август 2026).

Файл: data/01.08.-31.08.-СОС-импортэкспорт.pdf

Блоки:
    1)   Импорт FILO (COC) с Drop Off: Шанхай → ВМРП / Терминал Врангель, USD.
         Колонки различаются местом сдачи порожнего контейнера:
             COC 20 DC                       — «По запросу», сегмента нет
             Drop Off Moscow COC 40 HC (сквозной сервис)
             Drop Off Moscow COC 40 HC
             Drop Off ВМРП COC 40 HC
         Место сдачи пишется в dropoff_location, а end_point остаётся портом
         выгрузки — иначе морское плечо не состыкуется с железнодорожным.
    2)   Наземная составляющая, ДВЕ таблицы, RUB:
             CY ВМРП/Терминал Врангель – FOR Москва (до станции назначения)
             CY ВМРП/Терминал Врангель – FOT Москва (в пределах МКАД)
         В каждой по строке на ВМРП и на Терминал Врангель.
         Колонки охраны пропускаются — это доплата.
    3)   Экспорт LIFO (COC): ВМРП / Терминал Врангель → Шанхай, USD.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import garant_intermodal_common as _c

_PATTERN = r"01\.08.*(СОС|SOC).*импорт"

_IMPORT_CONDITIONS = (
    "Импорт FILO, COC; включено: GRI, EBS, THC в порту выгрузки; "
    "не включено: OWS 200 USD за 20' при VGM свыше 21т, документальный сбор "
    "50 USD/BL, конвертация 3%, сборы на стороне отправления; "
    "free time Drop Off Москва 35 суток, ВМРП/Врангель 14 суток"
)
_EXPORT_CONDITIONS = (
    "Экспорт LIFO, COC; не включено: документальный сбор 50 USD/BL, "
    "конвертация 3%, сборы на стороне прибытия; "
    "free time pick up 10 суток, Шанхай 7 суток"
)
_RAIL_CONDITIONS_FOR = (
    "Наземная составляющая, CY порт – FOR Москва (до станции назначения); "
    "тариф применяется на дату отгрузки контейнера на ж/д; "
    "охрана оплачивается отдельно"
)
_RAIL_CONDITIONS_FOT = (
    "Наземная составляющая, CY порт – FOT Москва (доставка в пределах МКАД); "
    "тариф применяется на дату отгрузки контейнера на ж/д; "
    "охрана оплачивается отдельно"
)

# Колонки импортной таблицы: (индекс, тип контейнера, место сдачи порожнего).
# Первая колонка («COC 20 DC») в этом выпуске — «По запросу», цены нет.
_IMPORT_COLUMNS = [
    (2, "20DC", None),
    (3, "40HC", "Москва"),
    (4, "40HC", "Москва"),
    (5, "40HC", "Владивосток"),
]


def _parse_import(table: list, valid_from, valid_to) -> list[dict]:
    """Импортная таблица с четырьмя колонками Drop Off."""
    results: list[dict] = []
    if len(table) < 2:
        return results

    for row in table[1:]:
        cells = [_c.text(c) for c in row]
        if len(cells) < 3 or not cells[0]:
            continue
        foreign = _c.translate_foreign(cells[0])
        ru_ports = _c.split_ru_ports(cells[1]) if len(cells) > 1 else []
        if not foreign or not ru_ports:
            continue

        for col, container_type, dropoff in _IMPORT_COLUMNS:
            cost = _c.parse_price(cells[col]) if col < len(cells) else None
            if cost is None:          # «По запросу» — сегмент не создаём
                continue
            through = "сквозной" in _c.text(table[0][col]).lower() if col < len(table[0]) else False
            for ru_name, ru_city in ru_ports:
                conditions = _IMPORT_CONDITIONS
                if dropoff:
                    conditions += f"; сдача порожнего: {dropoff}"
                if through:
                    conditions += "; сквозной сервис"
                segment = _c.make_sea(
                    start_point=foreign[0], start_country=foreign[1],
                    start_city=foreign[0], end_point=ru_name,
                    end_country="Россия", end_city=ru_city,
                    container_type=container_type, ownership="COC", cost=cost,
                    term="FILO", conditions=conditions,
                    valid_from=valid_from, valid_to=valid_to,
                )
                if dropoff:
                    segment["dropoff_location"] = dropoff
                    segment["dropoff_location_type"] = "city"
                    segment["dropoff_location_country"] = "Россия"
                results.append(segment)
    return results


def _parse_rail(table: list, conditions: str, valid_from, valid_to) -> list[dict]:
    """Таблица «Порт | 20DC до 24т | 20DC 24-28т | Охрана | 40HC | Охрана».

    Пустые колонки, которые pdfplumber добавляет между данными, отбрасываются:
    иначе индексы тарифных колонок разъезжаются.
    """
    results: list[dict] = []
    for row in table[1:]:
        cells = [_c.text(c) for c in row if _c.text(c)]
        if len(cells) < 4:
            continue
        ports = _c.split_ru_ports(cells[0])
        if not ports:
            continue
        port_name, port_city = ports[0]

        amounts = [_c.parse_price(c) for c in cells[1:]]
        amounts = [a for a in amounts if a is not None]
        # Порядок в строке: 20DC≤24, 20DC 24-28, охрана20, 40HC, охрана40
        if len(amounts) < 5:
            continue
        rates = [amounts[0], amounts[1], amounts[3]]

        for (container_type, min_w, max_w), cost in zip(_c.RAIL_CATS, rates):
            results.append(_c.make_rail(
                port_name=port_name, port_city=port_city,
                station="Москва", city="Москва",
                container_type=container_type, min_weight=min_w, max_weight=max_w,
                cost=cost, conditions=conditions,
                valid_from=valid_from, valid_to=valid_to,
            ))
    return results


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс COC импорт/экспорт и возвращает список сегментов."""
    full_text, tables = _c.read_pdf(file_path, _PATTERN)
    if not tables:
        return []

    valid_from, valid_to = _c.parse_period(full_text)
    results: list[dict] = []
    rail_seen = 0

    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [_c.text(c) for c in table[0]]
        head_line = _c._latin(" ".join(header).upper())

        if head_line.startswith("POL") and "DROP OFF" in head_line:
            results += _parse_import(table, valid_from, valid_to)
        elif head_line.startswith("POL"):
            # Экспортная таблица: POL — российский порт, POD — Шанхай.
            results += _c.parse_sea_table(
                table, ownership="COC", term="LIFO",
                conditions=_EXPORT_CONDITIONS,
                valid_from=valid_from, valid_to=valid_to, foreign_side="end",
            )
        elif _c.text(header[0]).lower() == "порт" or "Порт" in header:
            # Две ЖД-таблицы идут подряд: сначала FOR, затем FOT.
            conditions = _RAIL_CONDITIONS_FOR if rail_seen == 0 else _RAIL_CONDITIONS_FOT
            added = _parse_rail(table, conditions, valid_from, valid_to)
            if added:
                rail_seen += 1
                results += added

    sea = sum(1 for r in results if r["transport_type"] == "sea")
    print(f"  [Гарант COC импорт/экспорт] сегментов: {len(results)} "
          f"(море {sea}, ЖД {len(results) - sea}), период {valid_from}..{valid_to}")
    return _to_segments(results)
