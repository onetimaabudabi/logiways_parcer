"""Auto-extracted from main.py.

Note: This module intentionally keeps the original parsing logic.
Output coercion to the canonical schema can be done via TariffSegment.
"""

from __future__ import annotations

import re

import docx
import pandas as pd

from shared import (
    container_size_dict,
    currency_dict,
    get_city_port,
    get_country,
    port_dict,
    region_dict,
)


def _cell(cell) -> str:
    return cell.text.replace('\xa0', ' ').replace('\n', ' ').strip()


def _price(val: str) -> int | None:
    if not val or val.strip() in ('-', '', '—', 'н/д'):
        return None
    digits = re.sub(r'[^\d]', '', val)
    return int(digits) if digits else None


def _table_text(table) -> str:
    return ' '.join(_cell(c) for row in table.rows for c in row.cells)


def _find_header_row(table, *keywords):
    """Return index of first row whose joined text contains all keywords (case-insensitive)."""
    for i, row in enumerate(table.rows):
        text = ' '.join(_cell(c) for c in row.cells).lower()
        if all(kw.lower() in text for kw in keywords):
            return i
    return None


def parse_Khasan(filepath: str):
    company = "KHASAN"
    all_data = []

    doc = docx.Document(filepath)

    sea_table = rail_table = sched_table = None
    for t in doc.tables:
        txt = _table_text(t)
        if sea_table is None and 'СКВОЗНОЙ СЕРВИС' in txt and 'Drop-off' in txt:
            sea_table = t
        elif rail_table is None and 'ПЕРЕВОЗКА С ТЕРМИНАЛА ПОРТА' in txt and 'Пункт отправления' in txt:
            rail_table = t
        elif sched_table is None and 'Vessel' in txt and 'Voyage' in txt and 'ETD' in txt:
            sched_table = t

    # ---- Schedule ----
    schedules = []
    if sched_table:
        hdr_idx = _find_header_row(sched_table, 'vessel', 'voyage')
        if hdr_idx is not None:
            hdrs = [_cell(c) for c in sched_table.rows[hdr_idx].cells]
            col_vessel = next((i for i, h in enumerate(hdrs) if h.lower() == 'vessel'), None)
            col_voyage = next((i for i, h in enumerate(hdrs) if h.lower() == 'voyage'), None)
            col_cutoff = next((i for i, h in enumerate(hdrs) if h.lower() == 'cutoff'), None)
            etd_cols = [i for i, h in enumerate(hdrs) if h.upper() == 'ETD']
            col_etd = etd_cols[0] if etd_cols else None
            col_etd_pod = etd_cols[1] if len(etd_cols) > 1 else None

            for row in sched_table.rows[hdr_idx + 1:]:
                cells = [_cell(c) for c in row.cells]
                vessel = cells[col_vessel] if col_vessel is not None and col_vessel < len(cells) else ''
                voyage = cells[col_voyage] if col_voyage is not None and col_voyage < len(cells) else ''
                if not vessel and not voyage:
                    continue
                schedules.append({
                    'vessel_name': vessel,
                    'voyage_no': voyage,
                    'cutoff': cells[col_cutoff] if col_cutoff is not None and col_cutoff < len(cells) else '',
                    'ETD': cells[col_etd] if col_etd is not None and col_etd < len(cells) else '',
                    'ETA': cells[col_etd_pod] if col_etd_pod is not None and col_etd_pod < len(cells) else '',
                })

    sched_iter = schedules if schedules else [{}]

    # ---- Sea / Through-service rates ----
    transit_days = None

    if sea_table:
        hdr_idx = _find_header_row(sea_table, 'drop-off', '20dc')
        if hdr_idx is None:
            hdr_idx = _find_header_row(sea_table, '20dc', '40hc')

        if hdr_idx is not None:
            hdrs = [_cell(c) for c in sea_table.rows[hdr_idx].cells]

            col_pol = next((i for i, h in enumerate(hdrs) if 'порт отгрузки' in h.lower()), None)
            col_pod = next((i for i, h in enumerate(hdrs) if 'порт прибытия' in h.lower()), None)
            col_drop = next((i for i, h in enumerate(hdrs) if 'drop' in h.lower()), None)
            col_20dc = next((i for i, h in enumerate(hdrs) if '20dc' in h.lower()), None)
            col_40hc = next((i for i, h in enumerate(hdrs) if '40hc' in h.lower()), None)

            # Determine ownership and service term from column header
            coc_ownership = 'COC'
            service_term = None
            if col_20dc is not None:
                h_upper = hdrs[col_20dc].upper()
                # Latin SOC → SOC; Cyrillic COC/any other → COC
                if 'SOC' in h_upper and 'СОС' not in hdrs[col_20dc]:
                    coc_ownership = 'SOC'
                if 'FILO' in h_upper:
                    service_term = 'FILO'
                elif 'FIFO' in h_upper:
                    service_term = 'FIFO'

            # First pass: extract SOC prices and transit days from footer
            soc_prices: dict[str, int] = {}
            for row in sea_table.rows[hdr_idx + 1:]:
                cells = [_cell(c) for c in row.cells]
                row_str = ' '.join(cells)

                if 'транзит' in row_str.lower():
                    m = re.search(r'~?\s*(\d{1,3})\s*дн', row_str, re.I)
                    if m:
                        transit_days = int(m.group(1))

                for m in re.finditer(r'SOC\s+(\w+)\s*[—\-]+\s*(\d[\d\s]*)\$', row_str):
                    soc_prices[m.group(1).upper()] = int(re.sub(r'\s', '', m.group(2)))

            # Second pass: create segments
            seen = set()
            for row in sea_table.rows[hdr_idx + 1:]:
                cells = [_cell(c) for c in row.cells]
                row_str = ' '.join(cells)

                pol_raw = cells[col_pol] if col_pol is not None and col_pol < len(cells) else ''
                if not pol_raw:
                    continue
                # Skip header/note rows
                if any(skip in pol_raw.lower() for skip in ('порт', 'транзит', 'ставка', 'без', 'soc')):
                    continue

                pod_raw = cells[col_pod] if col_pod is not None and col_pod < len(cells) else ''
                drop_raw = cells[col_drop] if col_drop is not None and col_drop < len(cells) else ''

                row_key = (pol_raw, pod_raw, drop_raw)
                if row_key in seen:
                    continue
                seen.add(row_key)

                p20 = _price(cells[col_20dc]) if col_20dc is not None and col_20dc < len(cells) else None
                p40 = _price(cells[col_40hc]) if col_40hc is not None and col_40hc < len(cells) else None
                if p20 is None and p40 is None:
                    continue

                # Resolve POL
                pol_en = pol_raw.upper()
                pol_ru = port_dict.get(pol_raw.title(), port_dict.get(pol_en, pol_raw.title()))
                start_country = get_country(pol_ru) or 'Китай'

                # Resolve POD terminal
                pod_upper = pod_raw.upper()
                pod_ru = port_dict.get(pod_upper, port_dict.get(pod_raw.title(), pod_raw))
                pod_city = get_city_port(pod_ru) or 'Владивосток'
                end_country = get_country(pod_ru) or get_country(pod_city) or 'Россия'

                # Drop-off cities (may be comma-separated)
                drop_cities = [d.strip() for d in drop_raw.split(',') if d.strip()] or [None]

                for drop_city in drop_cities:
                    dropoff_loc = None
                    dropoff_country = None
                    if drop_city:
                        city_ru = region_dict.get(drop_city, region_dict.get(drop_city.title(), drop_city.title()))
                        dropoff_country = get_country(city_ru) or 'Россия'
                        dropoff_loc = city_ru

                    base = dict(
                        transport_type='sea',
                        start_point=f'{pol_ru}, {start_country}',
                        end_point=f'{pod_ru}, {end_country}',
                        start_location_type='port',
                        end_location_type='port',
                        parent_start_location=pol_ru,
                        parent_start_location_type='city',
                        parent_end_location=pod_city,
                        parent_end_location_type='city',
                        dropoff_location=dropoff_loc,
                        dropoff_location_type='city' if dropoff_loc else None,
                        dropoff_location_country=dropoff_country,
                        currency=currency_dict.get('$', 'USD'),
                        company=company,
                        duration_max_days=transit_days,
                        port_service_term=service_term,
                    )

                    for sched in sched_iter:
                        if p20:
                            all_data.append(TariffSegment(
                                container_type='20DC',
                                weight_limit=container_size_dict.get('20DC', '24'),
                                max_weight_kg=container_size_dict.get('20DC', '24'),
                                cost=p20,
                                container_ownership=coc_ownership,
                                departures=sched or None,
                                **base,
                            ))
                            # SOC variant for same drop-off
                            if '20DC' in soc_prices:
                                all_data.append(TariffSegment(
                                    container_type='20DC',
                                    weight_limit=container_size_dict.get('20DC', '24'),
                                    max_weight_kg=container_size_dict.get('20DC', '24'),
                                    cost=soc_prices['20DC'],
                                    container_ownership='SOC',
                                    departures=sched or None,
                                    **base,
                                ))
                        if p40:
                            all_data.append(TariffSegment(
                                container_type='40HC',
                                weight_limit=container_size_dict.get('40HC', '28'),
                                max_weight_kg=container_size_dict.get('40HC', '28'),
                                cost=p40,
                                container_ownership=coc_ownership,
                                departures=sched or None,
                                **base,
                            ))
                            # SOC variant for same drop-off
                            if '40HC' in soc_prices:
                                all_data.append(TariffSegment(
                                    container_type='40HC',
                                    weight_limit=container_size_dict.get('40HC', '28'),
                                    max_weight_kg=container_size_dict.get('40HC', '28'),
                                    cost=soc_prices['40HC'],
                                    container_ownership='SOC',
                                    departures=sched or None,
                                    **base,
                                ))

    # ---- Rail rates ----
    if rail_table:
        hdr_idx = _find_header_row(rail_table, 'пункт отправления', 'пункт прибытия')

        if hdr_idx is not None:
            hdrs = [_cell(c) for c in rail_table.rows[hdr_idx].cells]

            col_pol = next((i for i, h in enumerate(hdrs) if 'пункт отправления' in h.lower()), None)
            col_pod = next((i for i, h in enumerate(hdrs) if 'пункт прибытия' in h.lower()), None)
            col_20dc = None
            col_20dc_28 = None
            col_40hc = None

            for i, h in enumerate(hdrs):
                h_lower = h.lower()
                if '40hc' in h_lower:
                    col_40hc = i
                elif '20dc' in h_lower and 'более 24' in h_lower:
                    col_20dc_28 = i
                elif '20dc' in h_lower:
                    col_20dc = i
                elif 'более 24' in h_lower and col_20dc is not None:
                    col_20dc_28 = i
                elif 'до 24' in h_lower and col_20dc is None:
                    col_20dc = i

            for row in rail_table.rows[hdr_idx + 1:]:
                cells = [_cell(c) for c in row.cells]
                pol_raw = cells[col_pol] if col_pol is not None and col_pol < len(cells) else ''
                if not pol_raw:
                    continue
                if any(skip in pol_raw.lower() for skip in ('ставка', 'при', 'пункт')):
                    continue

                pod_raw = cells[col_pod] if col_pod is not None and col_pod < len(cells) else ''
                if not pod_raw:
                    continue

                p20 = _price(cells[col_20dc]) if col_20dc is not None and col_20dc < len(cells) else None
                p20_28 = _price(cells[col_20dc_28]) if col_20dc_28 is not None and col_20dc_28 < len(cells) else None
                p40 = _price(cells[col_40hc]) if col_40hc is not None and col_40hc < len(cells) else None

                if p20 is None and p20_28 is None and p40 is None:
                    continue

                # Resolve departure point
                pol_upper = pol_raw.upper()
                pol_ru = port_dict.get(pol_upper, port_dict.get(pol_raw.title(), pol_raw.title()))
                start_country = get_country(pol_ru) or 'Россия'
                pol_city = get_city_port(pol_ru) or pol_ru

                # Resolve destination
                pod_city = region_dict.get(pod_raw, region_dict.get(pod_raw.title(), pod_raw.title()))
                end_country = get_country(pod_city) or 'Россия'

                rail_base = dict(
                    transport_type='rail',
                    start_point=f'{pol_ru}, {start_country}',
                    end_point=f'{pod_city}, {end_country}',
                    start_location_type='rail_station',
                    end_location_type='rail_station',
                    parent_start_location=pol_city,
                    parent_start_location_type='city',
                    parent_end_location=pod_city,
                    parent_end_location_type='city',
                    currency=currency_dict.get('руб', 'RUB'),
                    company=company,
                    container_ownership='COC',
                )

                if p20:
                    all_data.append(TariffSegment(
                        container_type='20DC',
                        weight_limit=container_size_dict.get('20DC', '24'),
                        max_weight_kg=container_size_dict.get('20DC', '24'),
                        cost=p20,
                        **rail_base,
                    ))
                if p20_28:
                    all_data.append(TariffSegment(
                        container_type='20DC',
                        weight_limit='28',
                        min_weight_kg='24',
                        max_weight_kg='28',
                        cost=p20_28,
                        **rail_base,
                    ))
                if p40:
                    all_data.append(TariffSegment(
                        container_type='40HC',
                        weight_limit=container_size_dict.get('40HC', '28'),
                        max_weight_kg=container_size_dict.get('40HC', '28'),
                        cost=p40,
                        **rail_base,
                    ))

    return all_data


from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Khasan_impl = parse_Khasan


def parse(*args, **kwargs) -> list[TariffSegment]:
    result = _parse_Khasan_impl(*args, **kwargs)
    if isinstance(result, pd.DataFrame):
        return _to_segments(result)
    return result
