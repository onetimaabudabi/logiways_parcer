"""«Гарант Интермодал» — SOC Шанхай/Пусан → ВМРП + станции (август 2026).

Файл: data/01.08.-31.08.-SOC-Шанхай-Пусан-ВМРП[- ]Станц-SOC.pdf

Блоки:
    1) Импорт FILO (SOC): Шанхай / Пусан → Терминал Врангель, USD.
    2) ЖД от Терминала Врангель до 26 станций назначения, RUB.
       Колонки охраны пропускаются — это доплата, а не тариф перевозки.

Названия станций записаны как «Город, Станция» («Новосибирск, Клещиха»)
либо одним словом («Тольятти», «Екатеринбург-товарный»); город
восстанавливается в garant_intermodal_common.split_station().
"""

from __future__ import annotations

from pathlib import Path

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import garant_intermodal_common as _c

_PATTERN = r"01\.08.*ВМРП[- ]Станц"

_SEA_CONDITIONS = (
    "Импорт FILO, SOC; включено: GRI, EBS, THC в порту выгрузки; "
    "не включено: OWS 200 USD за 20' при VGM свыше 21т, документальный сбор "
    "50 USD/BL, конвертация 3%, надбавка за опасный груз 500 USD"
)
_RAIL_CONDITIONS = (
    "ЖД от ВМРП до станции назначения; "
    "тариф применяется на дату отгрузки контейнера на ж/д; "
    "охрана оплачивается отдельно"
)


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс ВМРП + станции и возвращает список сегментов."""
    full_text, tables = _c.read_pdf(file_path, _PATTERN)
    if not tables:
        return []

    valid_from, valid_to = _c.parse_period(full_text)
    results: list[dict] = []

    for table in tables:
        if not table or len(table) < 2:
            continue
        first = _c.text(table[0][0]).lower()

        if first == "pol":
            results += _c.parse_sea_table(
                table, ownership="SOC", term="FILO",
                conditions=_SEA_CONDITIONS,
                valid_from=valid_from, valid_to=valid_to, foreign_side="start",
            )
        elif first == "порт":
            results += _c.parse_station_table(
                table, _RAIL_CONDITIONS, valid_from, valid_to,
            )

    sea = sum(1 for r in results if r["transport_type"] == "sea")
    print(f"  [Гарант SOC ВМРП+станции] сегментов: {len(results)} "
          f"(море {sea}, ЖД {len(results) - sea}), период {valid_from}..{valid_to}")
    return _to_segments(results)
