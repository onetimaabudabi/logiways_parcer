"""Парсер FESCO Shuttles THROUGH — PDF тарифы COC RUR."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import port_dict as _PORT_DICT


# ──────────────────────────── helpers ────────────────────────────

def _price(val) -> float | None:
    """Extract numeric price from a cell (e.g. '$2 750' or '185 000р.')."""
    if val is None:
        return None
    s = str(val).strip().replace(" ", "")
    s = s.replace("$", "").replace("р.", "").replace(",", "")
    if not s or s.lower() == "n/a":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_valid_from(file_path: Path) -> str | None:
    """Extract valid_from date from PDF filename like 'FESCO Shuttles THROUGH from 01.02.2026 ...'."""
    m = re.search(r"from\s+(\d{2}\.\d{2}\.\d{4})", file_path.name)
    if m:
        d, mo, y = m.group(1).split(".")
        return f"{y}-{mo}-{d}"
    return None


_CTR_TITLE = {
    "ОАЭ": "Объединённые Арабские Эмираты",
}


def _parse_port_name(cell) -> tuple[str | None, str | None]:
    """Return (ru_port_name, country_name) from a sea port cell.

    Only processes cells that look like sea port rows (not rail station rows).
    """
    if cell is None:
        return None, None
    text = str(cell).strip()
    if not text or text == "nan":
        return None, None

    # Skip rail station cells — they have (city)digit or (city)* at end.
    # Use \d+ (one or more digits), NOT \d*, because \d* also matches zero digits
    # which would incorrectly match port names like "Джебель-Али (Дубаи)" or "Inchon (FOT)".
    if re.search(r"\([^)]*\)(?:\d+|\*)$", text):
        return None, None

    # country group header: all caps, few words
    if text.isupper() and len(text.split()) <= 4:
        title = _CTR_TITLE.get(text, text.title())
        return None, title

    # Determine port name and country
    # Support both " / " (with spaces) and "/" (without spaces like "Colombo/ Коломбо")
    if " / " in text:
        parts = text.split(" / ")
    elif "/" in text:
        parts = text.split("/")
    else:
        parts = None

    # First remove PRD prefix (works for "PRD порты: " and "PRD ports: ")
    prd_removed = re.sub(r"^.*?(?:ports?|порты)\s*:\s*", "", text, flags=re.IGNORECASE)

    # Determine port name
    # Support both " / " (with spaces) and "/" (without spaces like "Colombo/ Коломбо")
    if " / " in prd_removed:
        parts = prd_removed.split(" / ")
    elif "/" in prd_removed:
        parts = prd_removed.split("/")
    else:
        parts = None

    # Split into english and russian parts
    eng_part = None
    ru_part = None
    if parts is not None and len(parts) >= 2:
        for p in parts:
            p_clean = re.sub(r"\s*\([^)]*\)", "", p).strip()
            if re.search(r"[а-яА-ЯЁё]", p_clean):
                ru_part = p_clean
            elif re.search(r"[a-zA-Z]", p_clean):
                eng_part = p_clean
    else:
        ru_part = re.sub(r"\s*\([^)]*\)", "", prd_removed).strip()

    # Prefer port_dict translation of english name for consistency across parsers
    if eng_part and eng_part in _PORT_DICT:
        return _PORT_DICT[eng_part], None

    # Fallback: use russian part from PDF
    if ru_part:
        return ru_part, None

    # Last resort: translate english through port_dict or return as-is
    if eng_part:
        return _PORT_DICT.get(eng_part, eng_part), None

    return None, None


# ──────────────────────────── section 1: sea ────────────────────

def _extract_sea_tables(page_tables) -> list[dict]:
    """Parse sea-freight tables (col 0: port, col 1: 20DC, col 4: 40HC).
    Only processes tables with 7 columns — ignores 13-column rail tables.
    """
    results = []
    current_country = None

    for t in page_tables:
        # Skip rail tables (13 columns)
        ncols = len(t[0]) if t else 0
        if ncols > 10:
            continue

        for row in t:
            cell0 = row[0]
            ru_name, country_hdr = _parse_port_name(cell0)

            if country_hdr:
                current_country = country_hdr
                continue

            if ru_name is None:
                continue

            price_20 = _price(row[1]) if len(row) > 1 else None
            price_40 = _price(row[4]) if len(row) > 4 else None

            if price_20 is None and price_40 is None:
                continue

            if price_20 is not None:
                results.append({
                    "port": ru_name,
                    "country": current_country or "",
                    "container_type": "20DC",
                    "cost": price_20,
                })
            if price_40 is not None:
                results.append({
                    "port": ru_name,
                    "country": current_country or "",
                    "container_type": "40HC",
                    "cost": price_40,
                })

    return results


# ──────────────────────── section 2: rail ────────────────────────

def _extract_rail_table(page_tables) -> list[dict]:
    """Parse rail tables from pages 3-4.

    Column layout (13 cols):
     0  — station(city)
     1  — 20'DC ≤24т  (ТЭУ)
     3  — 20'DC >24т ≤28т  (ТЭУ)
     6  — 40'HC ≤28т  (ТЭУ)
     9  — security 20'
     11 — security 40'
    """
    results = []
    for t in page_tables:
        is_rail = False
        for r_idx in range(min(4, len(t))):
            cell_text = str(t[r_idx][0] or "")
            if any(kw in cell_text for kw in ("Станция и город", "Пункт назначения")):
                is_rail = True
                break
        if not is_rail:
            continue

        for row in t:
            cell0 = row[0]
            if cell0 is None:
                continue
            cell0_str = str(cell0).strip()
            if any(kw in cell0_str.lower() for kw in ("станция", "пункт", "тэу", "груз")):
                continue

            cost_24 = _price(row[1]) if len(row) > 1 else None
            cost_28 = _price(row[3]) if len(row) > 3 else None
            cost_40 = _price(row[6]) if len(row) > 6 else None
            sec_20 = _price(row[9]) if len(row) > 9 else None
            sec_40 = _price(row[11]) if len(row) > 11 else None

            if cost_24 is None and cost_40 is None:
                continue

            # Parse "station(city)footnote" or "station1 / station2 / station3(city)fn"
            joined = cell0_str.replace("\n", " ")
            # Also handle "Иркутск-Сортировочный\n(Иркутск)*"
            joined = joined.replace("*", "")

            # Extract city from parentheses
            city_match = re.search(r"\(([^)]+)\)", joined)
            city = city_match.group(1).strip() if city_match else ""
            city = re.sub(r"\d+$", "", city)

            # Get station(s): remove parentheses+footnote part, then split by /
            station_part = re.sub(r"\s*\([^)]*\)\d*$", "", joined).strip()
            station_part = re.sub(r"\d+$", "", station_part).strip()

            # Split by "/" and strip whitespace
            stations = [s.strip() for s in station_part.split("/") if s.strip()]

            for station in stations:
                results.append({
                    "station": station,
                    "city": city,
                    "cost_20_lt24": cost_24,
                    "cost_20_gt24": cost_28,
                    "cost_40": cost_40,
                    "security_20": sec_20,
                    "security_40": sec_40,
                })

    return results


def _extract_kaliningrad_table(page_tables) -> dict | None:
    """Parse the Kaliningrad / Baltic port table."""
    for t in page_tables:
        is_klg = False
        for r_idx in range(min(3, len(t))):
            cell0 = str(t[r_idx][0] or "")
            if "Пункт назначения" in cell0 or "Калининград" in cell0:
                is_klg = True
                break
        if not is_klg:
            continue

        for row in t:
            cell0 = row[0]
            if cell0 is None:
                continue
            cell0_str = str(cell0).strip()
            if any(kw in cell0_str.lower() for kw in ("пункт", "тэу", "груз")):
                continue
            if "Калининград" not in cell0_str:
                continue

            cost_24 = _price(row[1]) if len(row) > 1 else None
            cost_28 = _price(row[3]) if len(row) > 3 else None
            cost_40 = _price(row[6]) if len(row) > 6 else None
            sec_20 = _price(row[9]) if len(row) > 9 else None
            sec_40 = _price(row[11]) if len(row) > 11 else None

            return {
                "cost_20_lt24": cost_24,
                "cost_20_gt24": cost_28,
                "cost_40": cost_40,
                "security_20": sec_20,
                "security_40": sec_40,
            }
    return None


# ──────────────────── factory: create TariffSegment dicts ───────

_PORT_VLAD = "Владивостокский морской торговый порт"


def _make_sea_segment(port: str, country: str, ct: str, cost: float, valid_from: str | None) -> dict:
    return TariffSegment(
        transport_type="sea",
        start_point=f"{port}, {country}",
        end_point=f"{_PORT_VLAD}, Россия",
        final_destination="All, Россия",
        container_type=ct,
        weight_limit="24" if ct == "20DC" else "28",
        cost=cost,
        currency="USD",
        company="FESCO",
        container_ownership="COC",
        port_service_term="FILO",
        valid_from=valid_from,
        valid_to=None,
        end_location_type="port",
        start_location_type="port",
        parent_start_location=port,
        parent_start_location_type="city",
        parent_end_location="Владивосток",
        parent_end_location_type="city"
    ).to_dict()


def _make_rail_segment(
    station: str, city: str, cost: float, ct: str, wdesc: str,
    security: float | None, valid_from: str | None
) -> dict:
    security_str = f" + охрана {security:.0f}р." if security else ""

    # Weight limits
    if "<=24т" in wdesc:
        min_w = None
        max_w = 24
    elif ">24т" in wdesc:
        min_w = 24
        max_w = 28
    else:
        min_w = None
        max_w = 28

    return TariffSegment(
        transport_type="rail",
        start_point=f"{_PORT_VLAD}, Россия",
        end_point=f"{station}, Россия",
        container_type=ct,
        weight_limit="24" if ct == "20DC" else "28",
        min_weight_kg=min_w,
        max_weight_kg=max_w,
        cost=cost,
        currency="RUB",
        departure_dates=None,
        company="FESCO",
        customs=None,
        conditions=f"{ct} ({wdesc}), FOR{security_str}",
        duration_max_days=None,
        duration_min_days=None,
        departures=None,
        container_ownership="COC",
        valid_from=valid_from,
        valid_to=None,
        final_destination_location_type=None,
        end_location_type="rail_station",
        start_location_type="port",
        parent_start_location="Владивосток",
        parent_start_location_type="city",
        parent_end_location=city,
        parent_end_location_type="city",
        parent_final_destination_location=None,
        parent_final_destination_location_type=None,
        stopovers_location=None,
        stopovers_location_type=None,
        stopovers_location_country=None,
        sequence=0,
        border_point=None,
        border_location=None,
        border_location_type=None,
    ).to_dict()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────


def parse_Fesco(
    file_path: str | Path | None = None,
) -> list[dict]:
    """
    Парсит PDF «FESCO Shuttles THROUGH».

    Args:
        file_path: Путь к PDF файлу. Если None, ищет в data/ по шаблону.

    Returns:
        Список dict-ов (TariffSegment.to_dict()).
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("FESCO Shuttles THROUGH*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF FESCO в директории data/. "
                "Ожидался файл по шаблону: FESCO Shuttles THROUGH*.pdf"
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

    # ── Sea rates ──
    sea_data = _extract_sea_tables(all_tables)
    for sd in sea_data:
        results.append(_make_sea_segment(
            sd["port"], sd["country"], sd["container_type"], sd["cost"], valid_from
        ))

    # ── Rail rates ──
    rail_data = _extract_rail_table(all_tables)
    kaliningrad = _extract_kaliningrad_table(all_tables)

    # Remove Kaliningrad from rail_data — it's handled separately
    if kaliningrad:
        rail_data = [r for r in rail_data if r["station"] != "Калининград"]

    weight_cats = [
        ("20DC", "≤24т", "cost_20_lt24", "security_20"),
        ("20DC", ">24т, ≤28т", "cost_20_gt24", "security_20"),
        ("40HC", "≤28т", "cost_40", "security_40"),
    ]

    for rd in rail_data:
        for ct, wdesc, cost_key, sec_key in weight_cats:
            cost = rd.get(cost_key)
            if cost is None:
                continue
            results.append(_make_rail_segment(
                station=rd["station"],
                city=rd["city"],
                cost=cost,
                ct=ct,
                wdesc=wdesc,
                security=rd.get(sec_key),
                valid_from=valid_from,
            ))

    if kaliningrad:
        for ct, wdesc, cost_key, sec_key in weight_cats:
            cost = kaliningrad.get(cost_key)
            if cost is None:
                continue

            if "<=24т" in wdesc:
                min_w, max_w = None, 24
            elif ">24т" in wdesc:
                min_w, max_w = 24, 28
            else:
                min_w, max_w = None, 28

            security_str = f" + охрана {kaliningrad[sec_key]:.0f}р." if kaliningrad[sec_key] else ""

            results.append(TariffSegment(
                transport_type="rail",
                start_point=f"{_PORT_VLAD}, Россия",
                end_point="Балтийск, Россия",
                container_type=ct,
                weight_limit="24" if ct == "20DC" else "28",
                min_weight_kg=min_w,
                max_weight_kg=max_w,
                cost=cost,
                currency="RUB",
                departure_dates=None,
                company="FESCO",
                customs=None,
                conditions=f"{ct} ({wdesc}), CY Владивосток -> Автово -> Балтийск{security_str}",
                duration_max_days=None,
                duration_min_days=None,
                departures=None,
                container_ownership="COC",
                valid_from=valid_from,
                valid_to=None,
                final_destination_location_type=None,
                end_location_type="port",
                start_location_type="port",
                parent_start_location="Владивосток",
                parent_start_location_type="city",
                parent_end_location="Калининград",
                parent_end_location_type="city",
                stopovers_location="Автово",
                stopovers_location_type="port",
                stopovers_location_country="Россия",
                parent_stopovers_location="Санкт-Петербург",
                parent_stopovers_location_type="city",
                sequence=0,
                border_point=None,
                border_location=None,
                border_location_type=None,
            ).to_dict())

    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_Fesco(*args, **kwargs))
