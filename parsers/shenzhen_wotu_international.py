"""Auto-extracted from main.py.

Note: This module intentionally keeps the original parsing logic.
Output coercion to the canonical schema can be done via TariffSegment.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pdfplumber

from get_tables_sites import get_shedule_EuroSib, get_tables_pdf
from shared import (
    border_dict,
    container_size_dict,
    convert_date,
    country_dict,
    currency_dict,
    get_city_station,
    get_country,
    port_dict,
    region_dict,
)


def parse_Shenzhen_Wotu_International(file_path: str):
    df = pd.read_excel(file_path, header=None, sheet_name = "Shenzhen Wotu International")
    lines = [str(x).strip() for x in df.values.flatten() if str(x).strip()]
    results = []

    combined = []
    buffer = ""
    for line in lines:
        # если строка начинается с R/F, добавляем к предыдущей
        if re.match(r"^R/?F[:：]", line, re.IGNORECASE):
            buffer += " " + line
        # если строка начинается с FOB — новая запись
        elif re.match(r"^FOB", line, re.IGNORECASE):
            if buffer:
                combined.append(buffer.strip())
            buffer = line
        else:
            # если просто дополнительная строка (редкий случай)
            buffer += " " + line
    if buffer:
        combined.append(buffer.strip())

    for block in combined:
        # Извлекаем части маршрута: FOB ... - station - border - destination
        match_route = re.search(
            r"FOB\s+([^-]+)-\s*([^-]+station)\s*-\s*([^-]+border)\s*-\s*([\w\s()]+)",
            block,
            re.IGNORECASE
        )
        if not match_route:
            continue
        pol_raw, station, border, dest = [x.strip(" -") for x in match_route.groups()]

        # Извлекаем R/F часть
        match_rf = re.search(r"R/?F[:：]\s*USD\s*([\d,./]+)\s*/?\s*([^\s]+)?", block, re.IGNORECASE)
        cost = match_rf.group(1).replace(",", "").replace("/40",'').strip() if match_rf else ""
        container_type = "40HQ"
        if match_rf and match_rf.group(2):
            container_type = "40HQ" if "40" in match_rf.group(1) else "20GP"

        # Извлекаем ETD и Cut off
        etd = re.search(r"ETD[:：]?\s*([A-Za-z0-9/.\-]+)", block)
        etd_val = etd.group(1) if etd else ""

        cutoff = re.search(r"Cut[ -]?off[:：]?\s*([A-Za-z0-9/.\-]+)", block)
        cutoff_val = cutoff.group(1) if cutoff else ""

        # Извлекаем спец. пометки
        note = ""
        if "(" in block:
            note_match = re.search(r"\(([^)]+)\)", block)
            if note_match:
                note = note_match.group(1)

        # Разбиваем POL на города
        pol_list = re.split(r"[/,]", pol_raw)
        dest_port = dest.split()[0].strip()

        for pol in pol_list:
            pol = pol.strip()
            if not pol:
                continue

            pol_port = port_dict.get(pol.title(), pol.title())
            pod_port = region_dict.get(dest_port.title(), dest_port.title())
            start_country = get_country(pol_port)
            end_country = get_country(pod_port)
            record = {
                "transport_type": "rail",
                "start_point": f"{pol_port}, {start_country}",
                "end_point": f"{pod_port}, {end_country}",
                "final_destination": f"All, {end_country}",
                "container_type": container_type,
                "weight_limit": container_size_dict.get(container_type, ""),
                "cost": cost,
                "currency": currency_dict.get("$", "USD"),
                "departure_dates": {},
                "company": "Shenzhen Wotu International",
                "conditions": (
                    f"Станция: {station}\n"
                    f"Граница: {border}\n"
                    f"Cut-off: {cutoff_val}\n"
                    f"Примечание: {note}"
                    f"FOB, COC, {note or ''}".strip(", ")
                ),
                "departures": {"ETD": etd_val, "CUTOFF": cutoff_val} if etd_val or cutoff_val else None,
                "start_location_type": "port",
                "end_location_type": "rail_station"
            }
            results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_Shenzhen_Wotu_International
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Shenzhen_Wotu_International_impl = parse_Shenzhen_Wotu_International

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Shenzhen_Wotu_International_impl(*args, **kwargs))

