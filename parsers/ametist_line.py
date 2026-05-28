"""Парсер «Ametist Line» — PDF тарифы February 2026 Rates."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import container_size_dict


_COMPANY = "Ametist Line"

# Mapping of PDF route headers to (origin_port, dest_port, dest_country, dest_city)
_EXPORT_ROUTES = {
    "EXPORT NOVO‐AMBARLI": ("Новороссийск", "Амбарли", "Турция", "Стамбул"),
    "EXPORT NOVO‐GEBZE": ("Новороссийск", "Гебзе", "Турция", "Стамбул"),
    "EXPORT NOVO‐IZMIR": ("Новороссийск", "Измир", "Турция", "Измир"),
    "EXPORT NOVO‐MERSIN/SANKO": ("Новороссийск", "Мерсин", "Турция", "Мерсин"),
    "EXPORT NOVO‐ALEXANDRIA": ("Новороссийск", "Александрия", "Египет", "Александрия"),
    "EXPORT NOVO‐ASHDOD/HAIFA": ("Новороссийск", "Ашдод", "Израиль", "Ашдод"),
    "EXPORT NOVO‐BEIRUT": ("Новороссийск", "Бейрут", "Ливан", "Бейрут"),
}

_IMPORT_ROUTES = {
    "IMPORT AMBARLI‐NOVO": ("Амбарли", "Новороссийск", "Турция", "Стамбул"),
    "IMPORT GEBZE‐NOVO": ("Гебзе", "Новороссийск", "Турция", "Стамбул"),
    "IMPORT IZMIR‐NOVO": ("Измир", "Новороссийск", "Турция", "Измир"),
    "IMPORT MERSIN/SANKO‐NOVO": ("Мерсин", "Новороссийск", "Турция", "Мерсин"),
    "IMPORT ALEXANDRIA‐NOVO": ("Александрия", "Новороссийск", "Египет", "Александрия"),
    "IMPORT ASHDOD/HAIFA‐NOVO": ("Ашдод", "Новороссийск", "Израиль", "Ашдод"),
    "IMPORT BEIRUT‐NOVO": ("Бейрут", "Новороссийск", "Ливан", "Бейрут"),
}

# Container type mapping
_CONTAINER_MAP = {
    "20'dv": "20DC",
    "20'hc": "40HC",
    "40'hc": "40HC",
    "40'reef plugged": "40RF",
    "20'tc": "20TC",
    "20'fr in‐gauge": "20FR",
    "20'fr in-gauge": "20FR",
    "40'ot in‐gauge": "40OT",
    "40'ot in-gauge": "40OT",
}

# Column mapping for export: Type, LIFO, LIFO(IMO), LIFO(SOC), LIFO(SOC-IMO)
_EXPORT_COLS = {
    "COC": 1,
    "COC_IMO": 2,
    "SOC": 3,
    "SOC_IMO": 4,
}

# Column mapping for import: Type, FIFO, FIFO(IMO), FIFO(SOC), FIFO(SOC-IMO)
_IMPORT_COLS = {
    "COC": 1,
    "COC_IMO": 2,
    "SOC": 3,
    "SOC_IMO": 4,
}


def _price(val) -> float | None:
    """Extract numeric price from a cell."""
    if val is None:
        return None
    s = str(val).strip().replace("\u00a0", "").replace(" ", "")
    s = s.replace("$", "").replace("₽", "").replace("р.", "").replace(",", "")
    if not s or s.lower() in ("n/a", "onrequest", "‐", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_validity(pdf) -> tuple[str | None, str | None]:
    """Extract valid_from and valid_to from PDF text like 'validity: 01‐28/02/2026'."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        m = re.search(r"validity[:\s]+(\d{2})[\-‐](\d{2})/(\d{2})/(\d{4})", text)
        if m:
            start_d, end_d, mo, y = m.group(1), m.group(2), m.group(3), m.group(4)
            return f"{y}-{mo}-{start_d}", f"{y}-{mo}-{end_d}"
    return None, None


def _make_segment(
    *,
    transport_type: str,
    start_point: str,
    end_point: str,
    container_type: str,
    cost: float,
    currency: str,
    company: str,
    container_ownership: str,
    port_service_term: str,
    is_imo: bool,
    valid_from: str | None,
    valid_to: str | None,
    parent_start_location: str | None,
    parent_end_location: str | None,
) -> dict:
    conditions = "IMO" if is_imo else None
    return TariffSegment(
        transport_type=transport_type,
        start_point=start_point,
        end_point=end_point,
        container_type=container_type,
        cost=cost,
        weight_limit=container_size_dict.get(container_type, None),
        currency=currency,
        company=company,
        container_ownership=container_ownership,
        port_service_term=port_service_term,
        conditions=conditions,
        valid_from=valid_from,
        valid_to=valid_to,
        start_location_type="port",
        end_location_type="port",
        parent_start_location=parent_start_location,
        parent_start_location_type="city",
        parent_end_location=parent_end_location,
        parent_end_location_type="city",
    ).to_dict()


def parse_AmetistLine(file_path: str | Path | None = None) -> list[dict]:
    """Парсит PDF «February 2026 Rates» Ametist Line.

    Export: Novorossiysk → foreign ports (LIFO terms)
    Import: foreign ports → Novorossiysk (FIFO terms)
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("February 2026 Rates*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF Ametist Line в директории data/. "
                "Ожидался файл по шаблону: February 2026 Rates*.pdf"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    results: list[dict] = []

    with pdfplumber.open(file_path) as pdf:
        valid_from, valid_to = _extract_validity(pdf)
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables())

        # Track current route context
        current_export_route = None
        current_import_route = None

        for table in all_tables:
            if not table:
                continue

            for row in table:
                if not row or len(row) < 2:
                    continue

                cell0 = str(row[0]).strip() if row[0] else ""

                # Check for EXPORT route header (can appear mid-table)
                found_export = False
                for header, (origin, dest, dest_country, dest_city) in _EXPORT_ROUTES.items():
                    if header in cell0:
                        current_export_route = (origin, dest, dest_country, dest_city)
                        current_import_route = None
                        found_export = True
                        break

                if found_export:
                    continue

                # Check for IMPORT route header
                found_import = False
                for header, (origin, dest, origin_country, origin_city) in _IMPORT_ROUTES.items():
                    if header in cell0:
                        current_import_route = (origin, dest, origin_country, origin_city)
                        current_export_route = None
                        found_import = True
                        break

                if found_import:
                    continue

                # Skip non-rate tables
                if "THC" in cell0 or "Contacts" in cell0 or "validity" in cell0.lower():
                    current_export_route = None
                    current_import_route = None
                    continue

                # Skip header rows
                if cell0.lower() == "type":
                    continue

                if not current_export_route and not current_import_route:
                    continue

                # Container type row
                container_type = _CONTAINER_MAP.get(cell0.lower())
                if not container_type:
                    continue

                if len(row) < 5:
                    continue

                # ── Export route ──
                if current_export_route:
                    origin, dest, dest_country, dest_city = current_export_route
                    start_point = f"{origin}, Россия"
                    end_point = f"{dest}, {dest_country}"

                    for ownership_key, col_idx in _EXPORT_COLS.items():
                        price = _price(row[col_idx]) if len(row) > col_idx else None
                        if price is None:
                            continue

                        is_coc = "COC" in ownership_key
                        is_imo = "IMO" in ownership_key
                        ownership = "COC" if is_coc else "SOC"

                        results.append(_make_segment(
                            transport_type="sea",
                            start_point=start_point,
                            end_point=end_point,
                            container_type=container_type,
                            cost=price,
                            currency="USD",
                            company=_COMPANY,
                            container_ownership=ownership,
                            port_service_term="LIFO",
                            is_imo=is_imo,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            parent_start_location="Новороссийск",
                            parent_end_location=dest_city,
                        ))

                # ── Import route ──
                elif current_import_route:
                    origin, dest, origin_country, origin_city = current_import_route
                    start_point = f"{origin}, {origin_country}"
                    end_point = f"{dest}, Россия"

                    for ownership_key, col_idx in _IMPORT_COLS.items():
                        price = _price(row[col_idx]) if len(row) > col_idx else None
                        if price is None:
                            continue

                        is_coc = "COC" in ownership_key
                        is_imo = "IMO" in ownership_key
                        ownership = "COC" if is_coc else "SOC"

                        results.append(_make_segment(
                            transport_type="sea",
                            start_point=start_point,
                            end_point=end_point,
                            container_type=container_type,
                            cost=price,
                            currency="USD",
                            company=_COMPANY,
                            container_ownership=ownership,
                            port_service_term="FIFO",
                            is_imo=is_imo,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            parent_start_location=origin_city,
                            parent_end_location="Новороссийск",
                        ))

    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_AmetistLine(*args, **kwargs))
