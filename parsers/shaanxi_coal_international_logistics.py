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

def parse_Shaanxi_Coal_International_Logistics(file_path: str, company_name="Shaanxi Coal International Logistics"):
    df = pd.read_excel(file_path, sheet_name = "Shaanxi Coal International Logi")
    df = df.fillna("")
    df.columns = [clean(c) for c in df.columns]

    results = []
    cargo_type_old = ''
    for _, row in df.iterrows():
        dep_raw = clean(row.get("Departure Station", ""))
        border = clean(row.get("Border", ""))
        destination = clean(row.get("Destination", ""))
        rate_raw = clean(row.get("Rate (40HQ)", ""))
        cargo_type = clean(row.get("Cargoes", ""))
        if cargo_type:
            cargo_type_old = cargo_type
        if not dep_raw or not destination or not rate_raw:
            continue

        # -----------------------------
        # 1. POL (из строки типа "FOB Shanghai" или "FOB Shenzhen/Dongguan")
        # -----------------------------
        pol_match = re.findall(r"FOB\s+(.+)", dep_raw, flags=re.I)
        if not pol_match:
            continue
        pol_full = pol_match[0].strip()+"/"

        # -----------------------------
        # 2. Border — может быть "Erlian/Alashankou"
        # -----------------------------
        borders = [b.strip() for b in border.split("/") if b.strip()]

        # -----------------------------
        # 3. Destination — Electrougli, Moscow, etc.
        # -----------------------------
        pod_city = destination.split("/")[0].strip()

        # -----------------------------
        # 4. Cost
        # -----------------------------
        cost = re.sub(r"[^\d]", "", rate_raw)
        if not cost:
            continue

        # -----------------------------
        # 5. Перевод городов и стран
        # -----------------------------
        for pol_city_ in pol_full.split("/"):
            if pol_city_ == '':
                continue
            for border in borders:
                pol_city = pol_city_.strip()
                pol_port = port_dict.get(pol_city.title(), pol_city.title())
                pod_port = region_dict.get(pod_city.title(), pod_city.title())

                start_country = get_country(pol_port)
                end_country = get_country(pod_port)

                border_russian = border_dict.get(border.lower(), border)

                # -----------------------------
                # 6. Создание записи
                # -----------------------------
                record = {
                    "transport_type": "rail",
                    "start_point": f"{pol_port}, {start_country}",
                    "end_point": f"{pod_port}, {end_country}",

                    "container_type": "40HQ",
                    "weight_limit": container_size_dict.get("40HQ", ""),

                    "cost": cost,
                    "currency": currency_dict.get("$", "USD"),

                    "departure_dates": [],
                    "company": company_name,

                    "customs": None,

                    "conditions": f"FOB. Cargo: {cargo_type_old}" if cargo_type_old else "FOB",

                    "border_point": border_russian,
                    "start_location_type": "port",
                    "end_location_type": "rail_station"
                }

                results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_Shaanxi_Coal_International_Logistics
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Shaanxi_Coal_International_Logistics_impl = parse_Shaanxi_Coal_International_Logistics

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Shaanxi_Coal_International_Logistics_impl(*args, **kwargs))

