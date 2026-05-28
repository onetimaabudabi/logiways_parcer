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
    clean
)


def parse_UnknownCompany2(filepath:str):
    company="Неизвестная_компания_2"
    tables, text_blocks = get_tables_pdf(None, filepath, company)
    text = "\n".join(text_blocks)

    # --- 1. Найти блок маршрута ---
    route_match = re.search(r"Route:\s*(.+?)\s*ETD:", text, re.I | re.S)
    if not route_match:
        return pd.DataFrame([])

    route = route_match.group(1).strip()

    # Нормализация разделителей
    # Chongqing – Manzhouli – Shushary → ['Chongqing','Manzhouli','Shushary']
    route_points = re.split(r"\s*[–-]\s*", route)
    start_point = route_points[0]
    end_point = route_points[-1]

    # --- 2. Найти ETD ---
    etd_match = re.search(r"ETD:\s*([A-Za-z]+\s*\d+)", text)
    etd = etd_match.group(1).strip() if etd_match else ""

    # --- 3. Найти блок цен ---
    # Город: 3300 USD/40HQ
    rate_pattern = re.compile(
        r"([A-Za-z]+)\s*:\s*(\d+)\s*USD\s*/\s*(\d+\w+)",
        re.I
    )

    results = []

    for city, price, container_type in rate_pattern.findall(text):
        pol_port = port_dict.get(city.title(), city)
        pod_port = region_dict.get(end_point.title(), end_point)
        results.append({
            "transport_type": "rail",
            "start_point": f"{pol_port}, {get_country(pol_port)}",
            "end_point": f"{pod_port}, {get_country(pod_port)}",

            "final_destination": f"All, {get_country(pod_port)}",

            "container_type": container_type,
            "weight_limit": container_size_dict.get(container_type, ""),

            "cost": price,
            "currency": "USD",

            "departure_dates": etd if etd else [],

            "company": company,

            "conditions": f"All-in Rate. Route: {route}",

            "start_location_type": "port",
            "end_location_type": "rail_station"
        })

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_UnknownCompany2
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_UnknownCompany2_impl = parse_UnknownCompany2

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_UnknownCompany2_impl(*args, **kwargs))

