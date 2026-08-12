"""«Гарант Интермодал» — SOC Шанхай/Пусан, местная выдача (август 2026).

Файл: data/01.08.-31.08-SOC-Шанхай-Пусан-Местная-выдача.pdf

Блоки:
    1) Импорт FILO (SOC):  Шанхай / Пусан → ВМРП и Терминал Врангель, USD.
    2) Экспорт LIFO (SOC): Владивостокский рыбный порт / Терминал Врангель
                           → Шанхай и Пусан, USD.

POD в импорте записан как «ВМРП/Терминал Врангель» — одна ставка на оба
терминала, поэтому создаётся отдельный сегмент на каждый: иначе морское
плечо не состыкуется с железнодорожным из соседних прайсов.
"""

from __future__ import annotations

from pathlib import Path

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import garant_intermodal_common as _c

_PATTERN = r"01\.08.*Местная[- ]выдача"

_IMPORT_CONDITIONS = (
    "Импорт FILO, SOC; включено: GRI, EBS, THC в порту выгрузки; "
    "не включено: OWS 200 USD за 20' при VGM свыше 21т, документальный сбор "
    "50 USD/BL, конвертация 3%, надбавка за опасный груз 500 USD, "
    "сборы на стороне отправления"
)
_EXPORT_CONDITIONS = (
    "Экспорт LIFO, SOC; включено: бункерная надбавка, THC в порту погрузки; "
    "не включено: документальный сбор 50 USD/BL, конвертация 3%, "
    "надбавка за опасный груз 500 USD, сборы на стороне прибытия; "
    "надбавка за тяжёлый контейнер не применяется"
)


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс местной выдачи и возвращает список сегментов."""
    full_text, tables = _c.read_pdf(file_path, _PATTERN)
    if not tables:
        return []

    valid_from, valid_to = _c.parse_period(full_text)
    results: list[dict] = []

    for table in tables:
        if not table or len(table) < 2:
            continue
        header = " ".join(_c.text(c) for c in table[0]).upper()
        if "POL" not in header or "POD" not in header:
            continue

        # Импорт и экспорт различаются тем, с какой стороны иностранный порт.
        first_pol = _c.text(table[1][0]) if len(table[1]) else ""
        is_export = bool(_c.split_ru_ports(first_pol))

        results += _c.parse_sea_table(
            table,
            ownership="SOC",
            term="LIFO" if is_export else "FILO",
            conditions=_EXPORT_CONDITIONS if is_export else _IMPORT_CONDITIONS,
            valid_from=valid_from, valid_to=valid_to,
            foreign_side="end" if is_export else "start",
        )

    print(f"  [Гарант SOC местная выдача] сегментов: {len(results)}, "
          f"период {valid_from}..{valid_to}")
    return _to_segments(results)
