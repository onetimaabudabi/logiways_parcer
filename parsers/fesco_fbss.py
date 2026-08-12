"""FESCO — FBSS: Shanghai/Ningbo/Haiphong/Hochiminh → Новороссийск.

Файл: data/fbss.pdf
Сервис FBSS (FESCO Baltic/Black Sea Service), импорт, только COC, FIOS.
Ставка одна на все четыре порта отгрузки: 20'DC $5300, 40'HC $7500.
Срок действия: 01.08.2026 – 31.08.2026.

Экспортных ставок в файле нет — только импорт, как и указано в задании.
Разделы Demurrage/Detention и локальные сборы в порту Новороссийск
сегментами не становятся: это допрасходы, они уходят в conditions.
"""

from __future__ import annotations

import re

from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import fesco_common as _c

_FILE = "fbss.pdf"

_CONDITIONS = (
    "FBSS, импорт FIOS, контейнер линии (COC); ставка применяется на дату "
    "погрузки; надбавка за тяжёлый контейнер (HWS) 300 USD за 20DC свыше 20 т "
    "брутто; включено 10 суток Detention/Demurrage COC в Китае; "
    "не включено: THC и локальные сборы в порту Новороссийск, "
    "сбор за отмену букинга 500 USD/TEU, COD 200 USD/контейнер; "
    "опасные грузы к перевозке не принимаются"
)


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс FBSS и возвращает список сегментов."""
    path = _c.resolve_path(file_path) if file_path else _c.find_file(_FILE)
    if path is None or not Path(path).exists():
        print(f"  [FESCO FBSS] файл не найден: {file_path or _FILE}")
        return []

    with pdfplumber.open(path) as pdf:
        full_text = "\n".join(pg.extract_text() or "" for pg in pdf.pages)
        tables = [t for pg in pdf.pages for t in pg.extract_tables()]

    valid_from, valid_to = _c.parse_validity(full_text)

    # Порт назначения указан в заголовке («... to Novorossiysk»), в самой
    # таблице его нет — берём из текста, чтобы не хардкодить.
    pod = _c.translate_port("Novorossiysk")

    results: list[dict] = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [_c.text(c).upper() for c in table[0]]
        if "DIRECTION" not in header or "FIOS, USD" not in " ".join(header):
            continue

        pols: list[tuple[str, str]] = []
        ownership = "COC"
        for row in table[1:]:
            cells = [_c.text(c) for c in row]
            if len(cells) < 5:
                continue
            # Направление и принадлежность заполнены только в первой строке
            if cells[0]:
                # Ячейка направления: «Shanghai Ningbo Haiphong Hochiminh
                # to Novorossiysk» — всё после «to» относится к порту
                # назначения и в порты отгрузки попадать не должно.
                origin_part = re.split(r"\bto\b", cells[0], maxsplit=1)[0]
                found = _c.split_ports(origin_part)
                if found:
                    pols = found
            found_own = _c.normalize_ownership(cells[2])
            if found_own:
                ownership = found_own

            container_type = _c.normalize_container(cells[3])
            cost = _c.parse_price(cells[4])
            if not pols or not container_type or cost is None:
                continue

            for port_ru, country in pols:
                results.append(_c.make_sea(
                    start_point=port_ru, start_country=country,
                    end_point=pod[0], end_country=pod[1],
                    container_type=container_type, ownership=ownership,
                    cost=cost, term="FIOS", conditions=_CONDITIONS,
                    valid_from=valid_from, valid_to=valid_to,
                ))

    print(f"  [FESCO FBSS] сегментов: {len(results)}, период {valid_from}..{valid_to}")
    return _to_segments(results)
