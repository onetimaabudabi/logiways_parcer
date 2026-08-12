"""Общие хелперы для парсеров FESCO (август 2026).

Модуль вспомогательный: сами парсеры лежат в четырёх отдельных файлах
    fesco_fbss.py         — Shanghai/Ningbo/Haiphong/Hochiminh → Новороссийск
    fesco_jtsl.py         — Япония ↔ Владивосток (море + ЖД)
    fesco_fcdl.py         — Китай ↔ Владивосток
    fesco_ftbs_gebze.py   — Турция ↔ Новороссийск

Здесь собрано то, что во всех четырёх одинаково: чтение файлов, разбор цен,
период действия, справочники и сборка TariffSegment.

Существующий parsers/fesco.py (прайс FESCO Shuttles THROUGH) не затрагивается.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from .models import TariffSegment
from shared import container_size_dict, currency_dict, get_country, port_dict

COMPANY = "FESCO"

# Российские порты: в port_dict их английских названий нет.
RU_PORTS = {
    "VLADIVOSTOK": ("Владивосток", "Владивосток"),
    "VVO": ("Владивосток", "Владивосток"),
    "NOVOROSSIYSK": ("Новороссийск", "Новороссийск"),
    "NOVORO": ("Новороссийск", "Новороссийск"),
    "MOSCOW": ("Москва", "Москва"),
}

# Написания портов, отличающиеся от ключей shared.port_dict.
PORT_ALIASES = {
    "TOYAMASHINKO": "Toyama",
    "HO CHI MINH": "Hochiminh",
    "HOCHIMINH": "Hochiminh",
    "AMBARLI": "Ambarli",
    "GEBZE": "Gebze",
}

# Типы контейнеров: код в прайсе -> код, принятый в проекте.
# 45'HCPW в TransportType/ContainerType проекта отсутствует, поэтому
# такие строки пропускаются (см. normalize_container).
CONTAINER_MAP = {
    "20": "20DC", "20'": "20DC", "20'DC": "20DC", "20DC": "20DC",
    "20' DRY": "20DC", "20'DRY": "20DC", "20'DC/TC": "20DC", "20DC/TC": "20DC",
    "40": "40HC", "40'HC": "40HC", "40HC": "40HC", "40'&HC": "40HC",
    "40'&HC": "40HC", "40' DRY": "40HC", "40'DRY": "40HC", "40'DC": "40HC",
}
UNSUPPORTED_CONTAINERS = {"45'HCPW", "45HCPW", "45'HC"}

MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def text(val) -> str:
    return "" if val is None else re.sub(r"\s+", " ", str(val).replace("\xa0", " ")).strip()


def parse_price(val) -> Optional[float]:
    """'US$ 3 400,00' → 3400.0, '5 300' → 5300.0, '-' → None.

    Копейки после запятой отбрасываются: без этого «,00» приклеилось бы
    к сумме и 3 400,00 превратилось бы в 340000.
    """
    s = text(val)
    if not s or s in ("-", "—", "–") or re.fullmatch(r"n/?a\.?", s, re.IGNORECASE):
        return None
    if not re.search(r"\d", s):
        return None
    s = re.sub(r"[,.]\d{2}\s*$", "", s)
    digits = re.sub(r"\D", "", s)
    return float(digits) if digits else None


def normalize_container(val) -> Optional[str]:
    """\"20' Dry\" → '20DC'; \"40'&HC\" → '40HC'; \"45'HCPW\" → None."""
    raw = text(val).upper().replace("’", "'").replace("`", "'")
    compact = re.sub(r"\s+", "", raw)
    if compact in UNSUPPORTED_CONTAINERS or "45" in compact:
        return None
    for key in (compact, raw):
        if key in CONTAINER_MAP:
            return CONTAINER_MAP[key]
    m = re.search(r"\b(20|40)\b", compact)
    if not m:
        return None
    return "20DC" if m.group(1) == "20" else "40HC"


def normalize_ownership(val) -> Optional[str]:
    """'COC' / 'SOC' из произвольной строки."""
    upper = text(val).upper()
    if "COC" in upper:
        return "COC"
    if "SOC" in upper:
        return "SOC"
    return None


def translate_port(raw: str) -> Optional[tuple[str, str]]:
    """'Yokohama' → ('Иокогама', 'Япония'); 'Vladivostok' → ('Владивосток', 'Россия')."""
    name = re.sub(r"\*+", "", text(raw)).strip(" .,")
    if not name:
        return None

    ru_key = name.upper()
    if ru_key in RU_PORTS:
        port, _city = RU_PORTS[ru_key]
        return port, "Россия"

    key = PORT_ALIASES.get(ru_key, name)
    for variant in (key, key.title(), key.upper(), key.capitalize()):
        if variant in port_dict:
            ru = port_dict[variant]
            return ru, get_country(ru) or ""
    return None


def split_ports(raw: str) -> list[tuple[str, str]]:
    """'Ningbo/Shanghai/ Wenzhou' → список (русское имя, страна).

    Разделителем может быть «/», запятая ИЛИ перенос строки: в fbss.pdf
    порты записаны столбиком внутри одной ячейки («Shanghai\nNingbo\n...»),
    и после схлопывания пробелов они склеиваются в одну строку. Поэтому
    режем ещё и по пробелу, а нераспознанные куски просто отбрасываем.
    """
    result: list[tuple[str, str]] = []
    for chunk in re.split(r"\s*[/,]\s*|\s+", text(raw)):
        port = translate_port(chunk)
        if port and port not in result:
            result.append(port)
    return result


def parse_validity(full_text: str) -> tuple[Optional[str], Optional[str]]:
    """Разбирает срок действия в трёх встречающихся форматах.

    'Valid from 01st of August till 31st of August 2026' → (01.08, 31.08)
    'Valid from 1st of August 2026'                     → (01.08, None)
    '1/8 - 31/8/2026'                                   → (01.08, 31.08)
    """
    src = text(full_text)

    m = re.search(
        r"from\s+(\d{1,2})\w*\s+of\s+([A-Za-z]+)\s+till\s+(\d{1,2})\w*\s+of\s+([A-Za-z]+)\s+(\d{4})",
        src, re.IGNORECASE,
    )
    if m:
        m1 = MONTHS_EN.get(m.group(2).lower())
        m2 = MONTHS_EN.get(m.group(4).lower())
        if m1 and m2:
            return (f"{m.group(5)}-{m1:02d}-{int(m.group(1)):02d}",
                    f"{m.group(5)}-{m2:02d}-{int(m.group(3)):02d}")

    m = re.search(r"(\d{1,2})/(\d{1,2})\s*[-–]\s*(\d{1,2})/(\d{1,2})/(\d{4})", src)
    if m:
        return (f"{m.group(5)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}",
                f"{m.group(5)}-{int(m.group(4)):02d}-{int(m.group(3)):02d}")

    m = re.search(r"from\s+(\d{1,2})\w*\s+of\s+([A-Za-z]+)\s+(\d{4})", src, re.IGNORECASE)
    if m:
        month = MONTHS_EN.get(m.group(2).lower())
        if month:
            return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}", None

    return None, None


def resolve_path(file_path: str | Path) -> Path:
    """Находит файл, устойчиво к нормализации Unicode в имени (NFD/NFC)."""
    path = Path(file_path)
    if path.exists():
        return path
    target = unicodedata.normalize("NFC", path.name)
    if path.parent.is_dir():
        for candidate in path.parent.iterdir():
            if unicodedata.normalize("NFC", candidate.name) == target:
                return candidate
    return path


def find_file(name: str) -> Optional[Path]:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    candidate = data_dir / name
    return candidate if candidate.exists() else None


def make_sea(
    *, start_point: str, start_country: str, end_point: str, end_country: str,
    container_type: str, ownership: str, cost: float, term: Optional[str],
    conditions: str, valid_from, valid_to,
) -> dict:
    return TariffSegment(
        transport_type="sea",
        start_point=f"{start_point}, {start_country}".rstrip(", "),
        end_point=f"{end_point}, {end_country}".rstrip(", "),
        container_type=container_type,
        weight_limit=container_size_dict.get(container_type),
        max_weight_kg=int(container_size_dict.get(container_type, 28)),
        cost=cost,
        currency=currency_dict.get("$", "USD"),
        company=COMPANY,
        container_ownership=ownership,
        port_service_term=term,
        conditions=conditions,
        valid_from=valid_from,
        valid_to=valid_to,
        sequence=1,
        start_location_type="port",
        end_location_type="port",
        parent_start_location=start_point,
        parent_start_location_type="city",
        parent_end_location=end_point,
        parent_end_location_type="city",
    ).to_dict()


def make_rail(
    *, start_point: str, start_city: str, end_point: str, end_city: str,
    container_type: str, ownership: str, cost: float, currency: str,
    conditions: str, valid_from, valid_to,
) -> dict:
    return TariffSegment(
        transport_type="rail",
        start_point=f"{start_point}, Россия",
        end_point=f"{end_point}, {get_country(end_city) or 'Россия'}",
        container_type=container_type,
        weight_limit=container_size_dict.get(container_type),
        max_weight_kg=int(container_size_dict.get(container_type, 28)),
        cost=cost,
        currency=currency,
        company=COMPANY,
        container_ownership=ownership,
        conditions=conditions,
        valid_from=valid_from,
        valid_to=valid_to,
        sequence=2,
        start_location_type="port",
        end_location_type="rail_station",
        parent_start_location=start_city,
        parent_start_location_type="city",
        parent_end_location=end_city,
        parent_end_location_type="city",
    ).to_dict()
