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


def parse_SHENZHEN_INTERRAIL_LOGISTICS(filepath: str):
    company = "SHENZHEN INTERRAIL LOGISTICS"
    pattern = r'''
        ^                           # Начало строки
        ([\w/]+)                 # Loading place (FOB) — может быть с / (например, Guangzhou/Shenzhen)
        \s+                       # Пробелы
        ([\w]+)                   # Departure station
        \s+                     # Пробелы
        ([\w\s]+)               # Via — может включать пробелы (например, Qisumu Manzhouli)
        \s+                     # Пробелы
        \$([\d,]+?)             # Moscow (стоимость без $)
        \s+                     # Пробелы
        (\d{1,2}-[A-Za-z]{3}|Mid-[A-Za-z]+|\w+-[A-Za-z]+)  # ETD — дата или словесное обозначение
        $                       # Конец строки
    '''

    # Компилируем с флагом re.VERBOSE (чтобы можно было комментировать)
    regex = re.compile(pattern, re.VERBOSE)
    tables, text_blocks = get_tables_pdf(None, filepath, company)
    text_all = "\n".join(text_blocks)
    text = text_all.replace("\r", "\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    data_rail = []
    
    for line in lines:
        if not line:
            continue
        
        match = regex.match(line)
        if match:
            loading_place = match.group(1) + "/"
            departure_station = match.group(2)
            via = match.group(3).strip()
            moscow_price = int(match.group(4).replace(',', ''))  # Убираем запятые и в int
            etd = match.group(5)
            for pol in loading_place.split("/"):
                if not pol:
                    continue
                pol_port = port_dict.get(pol, pol)
                pod_port = region_dict.get("Moscow","Moscow")
                border_point = border_dict.get(via, via)
                container_type = "40HQ"
                start_country = get_country(pol_port)
                end_country = get_country(pod_port)
                data_rail.append({
                    "transport_type": "rail",
                    "start_point": f"{pol_port}, {start_country}",
                    "end_point": f"{pod_port}, {end_country}",
                    "final_destination": f"All, {end_country}",
                    "container_type": container_type,
                    "weight_limit": container_size_dict.get(container_type, ""),
                    "cost": moscow_price,
                    "currency": currency_dict.get("$", "USD"),
                    "departure_dates": etd,
                    "company": company,
                    "conditions": "COC",
                    "border_point": border_point,
                    "start_location_type": "port",
                    "end_location_type": "rail_station"
                })
    
    return pd.DataFrame(data_rail)

# _segments_wrapper_for_parse_SHENZHEN_INTERRAIL_LOGISTICS
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_SHENZHEN_INTERRAIL_LOGISTICS_impl = parse_SHENZHEN_INTERRAIL_LOGISTICS

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_SHENZHEN_INTERRAIL_LOGISTICS_impl(*args, **kwargs))

