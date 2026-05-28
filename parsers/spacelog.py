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


def parse_Spacelog(file_path: str):
    df = pd.read_excel(file_path, sheet_name = "Spacelog", header = None)
    df = df.fillna("")

    results = []
    dest_old = ''
    tt_old = ''
    etd_old = ''
    for _, row in df.iterrows():
        pickup = str(row.get("Pickup city", "") or row[0]).strip()
        border = str(row.get("Border", "") or row[2]).strip()
        dest = str(row.get("Destination station", "") or row[3]).strip()
        rate = str(row.get("FOB R/F rate", "") or row[4]).strip()
        tt = str(row.get("T/T", "") or row[5]).strip()
        etd = str(row.get("ETD", "") or row[6]).strip()
        # если нет pickup или ставки — пропускаем
        if not pickup or not rate:
            continue

        # обработка ставки
        cost_match = re.search(r"([\d,.]+)", rate)
        if not cost_match:
            continue
        cost = re.sub(r"[^\d.]", "", rate)
        currency = currency_dict.get("$", "USD")

        # контейнер
        container_type = "40HQ"
        if not dest_old or dest:
            dest_old = dest
        if not etd_old or etd:
            etd_old = etd
        if not tt_old or tt:
            tt_old = tt
        # Обработка многочастных значений
        pickup_ports = re.split(r"[/,]", pickup)
        borders = re.split(r"[/,]", border) if border else [""]
        destinations = re.split(r"[/,]", dest) if dest else [dest_old]

        for pol_raw in pickup_ports:
            pol = pol_raw.strip()
            if not pol:
                continue
            pol = pol.replace(" area","")
            for border_name in borders:
                border_name = border_name.strip()
                for pod_raw in destinations:
                    pod = pod_raw.strip() if pod_raw else "Москва"

                    pol_port = port_dict.get(pol.title(), pol.title())
                    pod_port = region_dict.get(pod.title(), pod.title())

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
                        "currency": currency,
                        "departure_dates": {etd_old} if etd_old else {},
                        "company": "Spacelog",
                        "conditions": (
                            f"Пограничный переход: {border_name}\n"
                            f"Время в пути: {tt_old}\n"
                            f"Отправление: {etd_old}"
                            "FOB, железнодорожная перевозка"
                        )
                    }
                    results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_Spacelog
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Spacelog_impl = parse_Spacelog

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Spacelog_impl(*args, **kwargs))

