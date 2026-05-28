"""Парсер ООО «ПОСЕЙДОН» — DOCX тарифы на прием/отправку из портов."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import port_dict

_COMPANY = "Посейдон"

# Порт-группы из Table 1 (прием из портов)
_PORT_GROUPS_RECEIVE = [
    {"name": "ВМТП", "parent_city": "Владивосток"},
    {"name": "ВМКТ", "parent_city": "Владивосток"},
    {"name": "SOLLERS / ВМПП", "parent_city": "Владивосток"},
]

# Table 2 — отправка в порты (все порты объединены)
_PORT_GROUPS_SEND = [
    {"name": "ВМТП / ВМКТ / SOLLERS / ВМПП", "parent_city": "Владивосток"},
]

# Весовые категории: (container_type, min_kg, max_kg, cost_col, sec_col)
# Col 0 = destination, Col 1 = 20DC, Col 2 = 20DC тяж, Col 3 = 40HC,
# Col 4 = охрана 20DC, Col 5 = охрана 40HC
_WEIGHT_CATS = [
    ("20DC", None, 24, 1, 4),
    ("20DC", 24, 28, 2, 4),   # 20DC тяж — до 28т (скобки не учитываем)
    ("40HC", None, 28, 3, 5),
]


def _extract_valid_dates(file_path: Path) -> tuple[str | None, str | None]:
    """Extract valid_from / valid_to from filename like
    'Прием и отправка из портов с 15.03.2026 по 31.03.2026НДС 0%.docx'."""
    m = re.search(r"с\s+(\d{2})\.(\d{2})\.(\d{4})\s+по\s+(\d{2})\.(\d{2})\.(\d{4})", file_path.name)
    if m:
        d1, mo1, y1 = m.group(1), m.group(2), m.group(3)
        d2, mo2, y2 = m.group(4), m.group(5), m.group(6)
        return f"{y1}-{mo1}-{d1}", f"{y2}-{mo2}-{d2}"
    return None, None


def _price(val) -> float | None:
    """Extract numeric price from a cell like '163 000 ₽ '."""
    if val is None:
        return None
    s = str(val).strip().replace("\u00a0", "").replace(" ", "")
    s = s.replace("₽", "").replace("р.", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean_destination(raw: str) -> str:
    """Remove parentheses (English abbreviations) from destination.
    'Москва (MSK)' -> 'Москва'."""
    return re.sub(r"\s*\([^)]*\)", "", raw).strip()


def _port_group_name_to_list(name: str) -> list[str]:
    """Split port group name into individual ports.
    'SOLLERS / ВМПП' -> ['SOLLERS', 'ВМПП']
    'ВМТП' -> ['ВМТП']"""
    return [p.strip() for p in name.split("/") if p.strip()]


_PORT_FULL_NAMES = {
    "ВМТП": "Владивостокский морской торговый порт",
    "ВМКТ": "Владивостокский морской контейнерный терминал",
    "SOLLERS": "Терминал Пасифик Лоджистик",
    "ВМПП": "Владивостокский морской порт «Первомайский»",
}


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
    valid_to: str | None,
    parent_start_location: str | None,
    parent_start_location_type: str | None,
    parent_end_location: str | None,
    parent_end_location_type: str | None,
    start_location_type: str,
    end_location_type: str,
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
        valid_to=valid_to,
        start_location_type=start_location_type,
        end_location_type=end_location_type,
        parent_start_location=parent_start_location,
        parent_start_location_type=parent_start_location_type,
        parent_end_location=parent_end_location,
        parent_end_location_type=parent_end_location_type,
    ).to_dict()


def parse_Poseidon(file_path: str | Path | None = None) -> list[dict]:
    """Парсит DOCX «Прием и отправка из портов» ООО ПОСЕЙДОН.

    Table 1 — прием из портов (rail: порт -> город назначения).
    Table 2 — отправка в порты (rail: город назначения -> порт).
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("Прием и отправка из портов*.docx"))
        if not matches:
            raise FileNotFoundError(
                "Не найден DOCX ПОСЕЙДОН в директории data/. "
                "Ожидался файл по шаблону: Прием и отправка из портов*.docx"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    valid_from, valid_to = _extract_valid_dates(file_path)

    doc = Document(str(file_path))
    tables = doc.tables
    if len(tables) < 3:
        raise ValueError("Ожидалось минимум 3 таблицы в DOCX")

    results: list[dict] = []

    # ────────────────────── Table 1: прием из портов ──────────────────────
    table1 = tables[1]
    # Walk rows, detect port-group headers and destination rows
    current_group: dict | None = None

    for row in table1.rows:
        cells = [cell.text.strip() for cell in row.cells]
        cell0 = cells[0] if cells else ""

        # Detect port-group header row (col 0-3 have same port name, col 4-5 = "Охрана")
        if len(cells) >= 6 and cells[4] == "Охрана" and cells[5] == "Охрана":
            # Check if this is a port group header (col 0-3 same or col 0 non-empty destination-like)
            # Port group rows: col 0 has port name, col 1-3 repeat it or are empty
            # But destination rows also have col 4/5 as "Охрана" — need to distinguish
            # Port group header: col 0 contains port name (ВМТП, ВМКТ, SOLLERS), NOT a city
            # Destination row: col 0 contains city (Москва, Екатеринбург...)
            # Check if col 0 is a known port keyword
            is_port_header = any(kw in cell0 for kw in ("ВМТП", "ВМКТ", "SOLLERS", "ВМПП"))
            if is_port_header:
                # Find matching port group
                for pg in _PORT_GROUPS_RECEIVE:
                    if pg["name"] in cell0 or cell0 in pg["name"]:
                        current_group = pg
                        break
                continue

        # Destination row
        if current_group is None:
            continue

        dest_raw = cell0
        if not dest_raw or dest_raw.lower() in ("", "пункт назначения"):
            continue

        dest = _clean_destination(dest_raw)
        if not dest:
            continue

        # Parse prices
        prices = {}
        for ct, min_w, max_w, cost_col, sec_col in _WEIGHT_CATS:
            cost = _price(cells[cost_col]) if len(cells) > cost_col else None
            sec = _price(cells[sec_col]) if len(cells) > sec_col else None
            if cost is not None:
                prices[(ct, min_w, max_w)] = (cost, sec)

        # Create segments for each port in the group
        port_names = _port_group_name_to_list(current_group["name"])
        parent_city = current_group["parent_city"]

        for port_short in port_names:
            port_full = port_dict.get(port_short, port_short)
            start_point = f"{port_full}, Россия"
            end_point = f"{dest}, Россия"

            for (ct, min_w, max_w), (cost, sec) in prices.items():
                results.append(_make_rail_segment(
                    start_point=start_point,
                    end_point=end_point,
                    container_type=ct,
                    min_weight_kg=min_w,
                    max_weight_kg=max_w,
                    cost=cost,
                    security=sec,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    parent_start_location=parent_city,
                    parent_start_location_type="city",
                    parent_end_location=dest,
                    parent_end_location_type="city",
                    start_location_type="port",
                    end_location_type="rail_station",
                ))

    # ────────────────────── Table 2: отправка в порты ОПАСНЫЕ ГРУЗЫ─────────────────────
    '''
    table2 = tables[2]

    for row in table2.rows:
        cells = [cell.text.strip() for cell in row.cells]
        cell0 = cells[0] if cells else ""

        # Skip header rows
        if not cell0 or "20DC" in cell0 or "Охрана" in cell0:
            continue
        if any(kw in cell0 for kw in ("ВМТП", "ВМКТ", "SOLLERS", "ВМПП")):
            continue

        dest_raw = cell0
        dest = _clean_destination(dest_raw)
        if not dest:
            continue

        prices = {}
        for ct, min_w, max_w, cost_col, sec_col in _WEIGHT_CATS:
            cost = _price(cells[cost_col]) if len(cells) > cost_col else None
            sec = _price(cells[sec_col]) if len(cells) > sec_col else None
            if cost is not None:
                prices[(ct, min_w, max_w)] = (cost, sec)

        # For send table, all ports are combined: ВМТП / ВМКТ / SOLLERS / ВМПП
        port_names = _port_group_name_to_list("ВМТП / ВМКТ / SOLLERS / ВМПП")
        parent_city = "Владивосток"

        for port_short in port_names:
            port_full = _PORT_FULL_NAMES.get(port_short, port_short)
            start_point = f"{dest}, Россия"
            end_point = f"{port_full}, Россия"

            for (ct, min_w, max_w), (cost, sec) in prices.items():
                results.append(_make_rail_segment(
                    start_point=start_point,
                    end_point=end_point,
                    container_type=ct,
                    min_weight_kg=min_w,
                    max_weight_kg=max_w,
                    cost=cost,
                    security=sec,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    parent_start_location=dest,
                    parent_start_location_type="city",
                    parent_end_location=parent_city,
                    parent_end_location_type="city",
                    start_location_type="rail_station",
                    end_location_type="port",
                ))
    '''

    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_Poseidon(*args, **kwargs))
