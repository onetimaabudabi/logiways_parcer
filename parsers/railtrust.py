"""Парсер «Рейл Траст» — PDF тарифы COC."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import port_dict, get_country


_COMPANY = "Рейл Траст"

# Destinations for sea+rail through rates (Table 0 columns after Владивосток)
_INLAND_DESTINATIONS = [
    ("Москва", "Москва", "city"),
    ("Санкт-Петербург", "Санкт-Петербург", "city"),
    ("Екатеринбург", "Екатеринбург", "city"),
    ("Новосибирск", "Новосибирск", "city"),
]

# Rail-only destinations (Table 1)
_RAIL_DESTINATIONS = [
    ("Москва", "Москва"),
    ("Новосибирск", "Новосибирск"),
    ("Екатеринбург", "Екатеринбург"),
    ("Санкт-Петербург", "Санкт-Петербург"),
]

# Weight categories for rail table (Table 1):
# Col 0 = destination, Col 1 = 20" до 24т, Col 2 = 20" 24-28т,
# Col 3 = 40" до 28т, Col 4 = охрана 20", Col 5 = охрана 40"
_RAIL_WEIGHT_CATS = [
    ("20DC", None, 24, 1, 4),
    ("20DC", 24, 28, 2, 4),
    ("40HC", None, 28, 3, 5),
]

# Sea table (Table 0) column layout:
# Col 0 = port, Col 1-2 = Владивосток (20/40),
# Col 3-4 = Москва (20/40), Col 5-6 = СПб (20/40),
# Col 7-8 = Екб (20/40), Col 9-10 = Нск (20/40)
_SEA_DEST_COLS = [
    ("Владивосток", 1, 2),
    ("Москва", 3, 4),
    ("Санкт-Петербург", 5, 6),
    ("Екатеринбург", 7, 8),
    ("Новосибирск", 9, 10),
]

def _extract_valid_from(file_path: Path) -> str | None:
    """Extract valid_from from filename like 'Прайс Рейл Траст с 01.03.26.pdf'."""
    m = re.search(r"с\s+(\d{2})\.(\d{2})\.(\d{2,4})", file_path.name)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{mo}-{d}"
    return None


def _price(val) -> float | None:
    """Extract numeric price from a cell."""
    if val is None:
        return None
    s = str(val).strip().replace("\u00a0", "").replace(" ", "")
    s = s.replace("$", "").replace("₽", "").replace("р.", "").replace(",00", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _resolve_port_name(en_name: str) -> str:
    """Convert English port name to Russian using shared port_dict."""
    # Try direct lookup
    ru = port_dict.get(en_name)
    if ru:
        return ru
    # Try title case
    ru = port_dict.get(en_name.title())
    if ru:
        return ru
    # Fallback: return as-is (title-cased)
    return en_name.title()


def _make_sea_segment(
    *,
    start_port_ru: str,
    start_country: str,
    end_point: str,
    end_country: str,
    container_type: str,
    cost: float,
    valid_from: str | None,
    parent_start_location: str | None,
    parent_start_location_type: str | None,
    parent_end_location: str | None,
    parent_end_location_type: str | None,
    end_location_type: str,
    dropoff_location: str | None,
    dropoff_location_type: str | None,
    dropoff_location_country: str | None
) -> dict:
    return TariffSegment(
        transport_type="sea",
        start_point=f"{start_port_ru}, {start_country}",
        end_point=f"{end_point}, {end_country}",
        container_type=container_type,
        weight_limit="24" if container_type == "20DC" else "28",
        cost=cost,
        currency="USD",
        company=_COMPANY,
        container_ownership="COC",
        port_service_term="FILO",
        valid_from=valid_from,
        valid_to=None,
        start_location_type="port",
        end_location_type=end_location_type,
        parent_start_location=parent_start_location,
        parent_start_location_type=parent_start_location_type,
        parent_end_location=parent_end_location,
        parent_end_location_type=parent_end_location_type,
        dropoff_location=dropoff_location,
        dropoff_location_type=dropoff_location_type,
        dropoff_location_country=dropoff_location_country
    ).to_dict()


def _make_rail_segment(
    *,
    start_point: str,
    end_point: str,
    container_type: str,
    min_weight_kg: int | None,
    max_weight_kg: int | None,
    cost: float,
    security: float | None,
    valid_from: str | None,
    parent_start_location: str | None,
    parent_start_location_type: str | None,
    parent_end_location: str | None,
    parent_end_location_type: str | None,
) -> dict:
    sec_str = f" + охрана {security:.0f}р." if security else ""
    return TariffSegment(
        transport_type="rail",
        start_point=start_point,
        end_point=end_point,
        container_type=container_type,
        weight_limit="24" if container_type == "20DC" and max_weight_kg and max_weight_kg <= 24 else "28",
        min_weight_kg=min_weight_kg,
        max_weight_kg=max_weight_kg,
        cost=cost,
        currency="RUB",
        company=_COMPANY,
        container_ownership="COC",
        conditions=f"{container_type}{sec_str}",
        valid_from=valid_from,
        valid_to=None,
        start_location_type="port",
        end_location_type="rail_station",
        parent_start_location=parent_start_location,
        parent_start_location_type=parent_start_location_type,
        parent_end_location=parent_end_location,
        parent_end_location_type=parent_end_location_type,
    ).to_dict()


def parse_RailTrust(file_path: str | Path | None = None) -> list[dict]:
    """Парсит PDF «Прайс Рейл Траст».

    Table 0 — морской фрахт: порты Китая/Вьетнама → Владивосток + through rates до inland городов.
    Table 1 — ЖД ставки: Владивосток → inland города (RUB).
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("Прайс Рейл Траст*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF Рейл Траст в директории data/. "
                "Ожидался файл по шаблону: Прайс Рейл Траст*.pdf"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    valid_from = _extract_valid_from(file_path)
    results: list[dict] = []

    with pdfplumber.open(file_path) as pdf:
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables())

    if len(all_tables) < 2:
        raise ValueError("Ожидалось минимум 2 таблицы в PDF")

    # ────────────────────── Table 0: Sea freight ──────────────────────
    sea_table = all_tables[0]

    current_country: str | None = None

    for row in sea_table:
        if not row or len(row) < 11:
            continue

        cell0 = str(row[0]).strip() if row[0] else ""

        # Country header row (e.g. "CHINA", "VIETNAM")
        if cell0.isupper() and len(cell0.split()) <= 2 and not cell0[0].isdigit():
            country_map = {"CHINA": "Китай", "VIETNAM": "Вьетнам", "Thailand": "Таиланд"}
            current_country = country_map.get(cell0, cell0.title())
            continue

        # Skip header rows
        if any(kw in cell0.lower() for kw in ("порт", "стоимость", "условия")):
            continue
        if not cell0:
            continue
        _points = {
            "Владивосток": {
                "type": "port",
                "parent": "Владивосток",
                "parent_type": "city"
            },
            "Восточный порт": {
                "type": "port",
                "parent": "Находка",
                "parent_type": "city"
            }
        }
        # Port row — resolve Russian name
        if "," in cell0:
            # If cell contains comma, assume it's "Port Name, Country"
            port_name_part = cell0.split(",")
        else:
            port_name_part = [cell0.strip()]
        for i in range(len(port_name_part)):
            part = port_name_part[i].strip()
            if part in port_dict:
                port_ru = _resolve_port_name(part)
                start_country = get_country(port_ru) or current_country or "Китай"

                for dest_name, col_20, col_40 in _SEA_DEST_COLS:
                    price_20 = _price(row[col_20]) if len(row) > col_20 else None
                    price_40 = _price(row[col_40]) if len(row) > col_40 else None
                    
                    for ep_name, ep_info in _points.items():
                        end_country = "Россия"
                        end_point = f"{ep_name}"
                        parent_end = ep_info["parent"]
                        parent_end_type = ep_info["parent_type"]
                        end_loc_type = ep_info["type"]
                        
                        if price_20 is not None:
                            results.append(_make_sea_segment(
                                start_port_ru=port_ru,
                                start_country=start_country,
                                end_point=end_point,
                                end_country=end_country,
                                container_type="20DC",
                                cost=price_20,
                                valid_from=valid_from,
                                parent_start_location=port_ru,
                                parent_start_location_type="city",
                                parent_end_location=parent_end,
                                parent_end_location_type=parent_end_type,
                                end_location_type=end_loc_type,
                                dropoff_location=dest_name,
                                dropoff_location_type="city",
                                dropoff_location_country="Россия"
                            ))

                        if price_40 is not None:
                            results.append(_make_sea_segment(
                                start_port_ru=port_ru,
                                start_country=start_country,
                                end_point=end_point,
                                end_country=end_country,
                                container_type="40HC",
                                cost=price_40,
                                valid_from=valid_from,
                                parent_start_location=port_ru,
                                parent_start_location_type="city",
                                parent_end_location=parent_end,
                                parent_end_location_type=parent_end_type,
                                end_location_type=end_loc_type,
                                dropoff_location=dest_name,
                                dropoff_location_type="city",
                                dropoff_location_country="Россия"
                            ))

    # ────────────────────── Table 1: Rail rates ──────────────────────
    rail_table = all_tables[1]

    # Rail from Vladivostok ports to inland destinations
    vlad_ports = ["Владивосток", "Восточный порт"]

    for row in rail_table:
        if not row or len(row) < 6:
            continue

        cell0 = str(row[0]).strip() if row[0] else ""

        # Skip header rows
        if any(kw in cell0.lower() for kw in ("направление", "стоимость", "вес")):
            continue
        if not cell0:
            continue

        dest_city = cell0
        end_country = "Россия"

        for ep_name, ep_info in _points.items():
            port_full = ep_name #_PORT_FULL_NAMES.get(port_short, port_short)
            end_country = "Россия"
            start_point = f"{ep_name}, {end_country}"
            parent_start = ep_info["parent"]
            parent_start_type = ep_info["parent_type"]
            start_loc_type = ep_info["type"]
            end_point = f"{dest_city}, Россия"

            for ct, min_w, max_w, cost_col, sec_col in _RAIL_WEIGHT_CATS:
                cost = _price(row[cost_col]) if len(row) > cost_col else None
                sec = _price(row[sec_col]) if len(row) > sec_col else None

                if cost is None:
                    continue

                results.append(_make_rail_segment(
                    start_point=start_point,
                    end_point=end_point,
                    container_type=ct,
                    min_weight_kg=min_w,
                    max_weight_kg=max_w,
                    cost=cost,
                    security=sec,
                    valid_from=valid_from,
                    parent_start_location=parent_start,
                    parent_start_location_type=parent_start_type,
                    parent_end_location=dest_city,
                    parent_end_location_type="city",
                ))

    return results


# ────────────────────── Сквозной тариф ──────────────────────

_SKVOZ_DEST_COLS = [
    ("Москва", 1, 2),
    ("Екатеринбург", 3, 4),
    ("Новосибирск", 5, 6),
]

_SKVOZ_RAIL_WEIGHT_CATS = [
    ("20DC", None, 24, 1, 4),
    ("20DC", 24, 28, 2, 4),
    ("40HC", None, 28, 3, 5),
]

_SKVOZ_PORTS = {
    "Shanghai": "Шанхай",
    "Ningbo": "Нинбо",
}


def _extract_skvoznoy_valid_from(file_path: Path) -> str | None:
    """Extract valid_from from filename like 'Прайс Рейл Траст сквозной с 10.03.2026.pdf'."""
    m = re.search(r"с\s+(\d{2})\.(\d{2})\.(\d{4})", file_path.name)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo}-{d}"
    return None


def _make_skvoznoy_sea_segment(
    *,
    start_port_ru: str,
    container_type: str,
    cost: float,
    valid_from: str | None,
    free_days: int | None,
) -> dict:
    return TariffSegment(
        transport_type="sea",
        start_point=f"{start_port_ru}, Китай",
        end_point="Находкинский морской рыбный порт, Россия",
        container_type=container_type,
        weight_limit="24" if container_type == "20DC" else "28",
        cost=cost,
        currency="USD",
        company=_COMPANY,
        container_ownership="COC",
        port_service_term="FILO",
        valid_from=valid_from,
        valid_to=None,
        start_location_type="port",
        end_location_type="port",
        parent_start_location=start_port_ru,
        parent_start_location_type="city",
        parent_end_location="Находка",
        parent_end_location_type="city",
        conditions=f"free time: {free_days} дн." if free_days else None,
    ).to_dict()


def _make_skvoznoy_rail_segment(
    *,
    dropoff_city: str,
    container_type: str,
    min_weight_kg: int | None,
    max_weight_kg: int | None,
    cost: float,
    security: float | None,
    valid_from: str | None,
    free_days: int | None,
) -> dict:
    sec_str = f" + охрана {security:.0f}р." if security else ""
    return TariffSegment(
        transport_type="rail",
        start_point="Находкинский морской рыбный порт, Россия",
        end_point=f"{dropoff_city}, Россия",
        container_type=container_type,
        weight_limit="24" if container_type == "20DC" and max_weight_kg and max_weight_kg <= 24 else "28",
        min_weight_kg=min_weight_kg,
        max_weight_kg=max_weight_kg,
        cost=cost,
        currency="RUB",
        company=_COMPANY,
        container_ownership="COC",
        conditions=f"{container_type}{sec_str}" + (f", free time: {free_days} дн." if free_days else ""),
        valid_from=valid_from,
        valid_to=None,
        start_location_type="port",
        end_location_type="rail_station",
        parent_start_location="Находка",
        parent_start_location_type="city",
        parent_end_location=dropoff_city,
        parent_end_location_type="city",
        dropoff_location=dropoff_city,
        dropoff_location_type="city",
    ).to_dict()


def parse_RailTrust_skvoznoy(file_path: str | Path | None = None) -> list[dict]:
    """Парсит PDF «Прайс Рейл Траст сквозной».

    Table 0 — сквозные тарифы (sea+rail): Shanghai/Ningbo → Москва/Екатеринбург/Новосибирск (USD).
    Table 1 — ЖД ставки: Владивосток → inland города (RUB).
    Table 2 — свободный период (дни).
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("Прайс Рейл Траст сквозной*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден сквозной PDF Рейл Траст в директории data/. "
                "Ожидался файл по шаблону: Прайс Рейл Траст сквозной*.pdf"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    valid_from = _extract_skvoznoy_valid_from(file_path)
    results: list[dict] = []

    with pdfplumber.open(file_path) as pdf:
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables())

    if len(all_tables) < 3:
        raise ValueError("Ожидалось минимум 3 таблицы в сквозном PDF")

    # ── Table 2: Free days ──
    free_days_map: dict[str, int] = {}
    for row in all_tables[2]:
        if not row or len(row) < 2:
            continue
        city = str(row[0]).strip() if row[0] else ""
        days = row[1]
        if city and days is not None:
            try:
                free_days_map[city] = int(str(days).strip())
            except ValueError:
                pass

    # ── Table 0: Sea+Rail through rates ──
    sea_table = all_tables[0]

    for row in sea_table:
        if not row or len(row) < 7:
            continue

        cell0 = str(row[0]).strip() if row[0] else ""
        if not cell0 or cell0.lower() in ("порт погрузки",):
            continue
        if cell0 in ("20 COC", "40 COC"):
            continue

        # Port row
        port_ru = _SKVOZ_PORTS.get(cell0, cell0)

        for dest_name, col_20, col_40 in _SKVOZ_DEST_COLS:
            price_20 = _price(row[col_20]) if len(row) > col_20 else None
            price_40 = _price(row[col_40]) if len(row) > col_40 else None
            free_days = free_days_map.get(dest_name)

            if price_20 is not None:
                results.append(_make_skvoznoy_sea_segment(
                    start_port_ru=port_ru,
                    container_type="20DC",
                    cost=price_20,
                    valid_from=valid_from,
                    free_days=free_days,
                ))

            if price_40 is not None:
                results.append(_make_skvoznoy_sea_segment(
                    start_port_ru=port_ru,
                    container_type="40HC",
                    cost=price_40,
                    valid_from=valid_from,
                    free_days=free_days,
                ))

    # ── Table 1: Rail rates ──
    rail_table = all_tables[1]

    for row in rail_table:
        if not row or len(row) < 6:
            continue

        cell0 = str(row[0]).strip() if row[0] else ""
        if not cell0 or cell0.lower() in ("направление",):
            continue

        dest_city = cell0
        free_days = free_days_map.get(dest_city)

        for ct, min_w, max_w, cost_col, sec_col in _SKVOZ_RAIL_WEIGHT_CATS:
            cost = _price(row[cost_col]) if len(row) > cost_col else None
            sec = _price(row[sec_col]) if len(row) > sec_col else None

            if cost is None:
                continue

            results.append(_make_skvoznoy_rail_segment(
                dropoff_city=dest_city,
                container_type=ct,
                min_weight_kg=min_w,
                max_weight_kg=max_w,
                cost=cost,
                security=sec,
                valid_from=valid_from,
                free_days=free_days,
            ))

    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_RailTrust(*args, **kwargs))


def parse_skvoznoy(*args, **kwargs) -> list:
    """Обёртка для сквозного тарифа."""
    return _to_segments(parse_RailTrust_skvoznoy(*args, **kwargs))
