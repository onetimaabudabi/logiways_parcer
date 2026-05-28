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


def split_etd(etd):
    """
    Превращает значения типа:
    '19/26.Aug'  → ['19.Aug', '26.Aug']
    '14/17/20.Aug' → ['14.Aug','17.Aug','20.Aug']
    """
    etd = etd.strip()
    if not etd:
        return []
    month = ""
    if "." in etd:
        month = etd.split(".")[-1]
    dates = etd.replace("." + month, "")
    parts = dates.split("/")
    return [f"{p}.{month}" for p in parts]


def parse_Transforever_International_Forwarding(file_path: str, company_name="Transforever International Forwarding"):
    df = pd.read_excel(file_path, sheet_name = "Transforever International Forw")
    # Нормализация колонок
    df.columns = [clean(c) for c in df.columns]

    # ffill загрузочного города
    df["Loading place"] = df["Loading place"].replace("", pd.NA).ffill().fillna("")

    results = []

    for _, row in df.iterrows():
        loading_place = clean(row["Loading place"])
        pol = clean(row["POL Station"])
        border = clean(row["Border"])
        pod_station = clean(row["POD Station"])
        etd_raw = clean(row["ETD"])
        ttdays = clean(row["TT/days"])
        fob = clean(row["FOB COC"])
        exw = clean(row["EXW COC"])
        note = clean(row["Note"]) or ""

        # пропускаем пустые строки
        if not pol or not pod_station:
            continue

        # разбор ETD — может быть несколько дат
        etd_list = split_etd(etd_raw)
        cost_list = []
        # ставка (FOB)
        if fob and fob.isdigit():
            cost_list.append(fob)
        if exw and exw.isdigit():
            cost_list.append(exw)


        # определение стран и переводов
        start_city = pol.split("/")[0].strip()
        start_point = port_dict.get(start_city.title(), start_city.title())
        end_city_list = pod_station.split("/")
        

        start_country = get_country(start_point)
        

        # каждая дата → отдельная запись
        etd_final = etd_list if etd_list else [etd_raw]

        #for etd in etd_final:
        for cost in range(len(cost_list)):
            for end_city in end_city_list:
                end_point = region_dict.get(end_city.title(), end_city.title())
                if end_point == end_city.title() and len(end_city.split(" ", 1)) >= 2:
                    end_point = region_dict.get(end_city.split(" ", 1)[1].title(), end_city.split(" ", 1)[1].title())
                end_country = get_country(end_point)
                record = {
                    "transport_type": "rail",
                    "start_point": f"{start_point}, {start_country}",
                    "end_point": f"{end_point}, {end_country}",
                    "final_destination": f"All, {end_country}",
                    "container_type": "40HQ",
                    "weight_limit": container_size_dict.get("40HQ", "40HQ"),
                    "cost": cost_list[cost],
                    "currency": "USD",
                    "departure_dates": etd_final,
                    "company": company_name,
                    "border_point": border,
                    "duration_max_days": int(ttdays) if ttdays and ttdays.isdigit() else None,
                    "conditions": ("FOB COC" if cost == 0 else "EXW COC")
                    + (f". Loading place: {loading_place}" if loading_place else "")
                    + (f". Note: {note}" if note else "")
                    + (f". POD Station: {pod_station}" if pod_station else "")
                }

                results.append(record)
    return pd.DataFrame(results)

# _segments_wrapper_for_parse_Transforever_International_Forwarding
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Transforever_International_Forwarding_impl = parse_Transforever_International_Forwarding

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Transforever_International_Forwarding_impl(*args, **kwargs))

