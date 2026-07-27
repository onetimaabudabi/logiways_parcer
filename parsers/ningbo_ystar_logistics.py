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


def parse_NingBo_YSTAR_Logistics(file_path: str):
    """
    Парсер тарифов компании NingBo Y-STAR Logistics.
    Обрабатывает многостраничную таблицу с несколькими блоками Carrier/POL/POD.
    Возвращает pd.DataFrame, готовый к объединению в main.py.
    """

    # читаем всё без заголовков (так как они повторяются)
    df = pd.read_excel(file_path, header=None, sheet_name = "NingBo Y-STAR Logistics")
    df = df.fillna("")

    results = []

    current_carrier = ""
    current_pod = ""

    # заголовки таблицы (чтобы определять начало нового блока)
    header_pattern = re.compile(r"(?i)carrier\s*")

    # преобразуем всё в список строк
    rows = df.values.tolist()

    # найдём индексы начала новых таблиц
    table_starts = [i for i, r in enumerate(rows) if any(header_pattern.search(str(c)) for c in r)]
    table_starts.append(len(rows))
    free_time_set = {}
    for t in range(len(table_starts) - 1):
        start = table_starts[t] + 1
        end = table_starts[t + 1]
        block = pd.DataFrame(rows[start:end])
        block.columns = [
            "Carrier", "POL", "POD", "20GP (USD)", "40HQ (USD)",
            "TERM", "Free time", "ETD", "V/V"
        ][:len(block.columns)]
        block = block.fillna("")

        for _, row in block.iterrows():
            carrier = str(row.get("Carrier", "")).strip()
            pol = str(row.get("POL", "")).strip()
            pod = str(row.get("POD", "")).strip()
            rate_20 = str(row.get("20GP (USD)", "")).strip()
            rate_40 = str(row.get("40HQ (USD)", "")).strip()
            term = str(row.get("TERM", "")).strip()
            free_time = str(row.get("Free time", "")).strip()
            etd = str(row.get("ETD", "")).strip()
            vv = str(row.get("V/V", "")).strip()
            if carrier not in free_time_set.keys():
                free_time_set[carrier] = {}
            free_time_set[carrier]["vv"] = vv if vv else free_time_set.get(carrier).get('vv')
            free_time_set[carrier]["term"] = vv if vv else free_time_set.get(carrier).get('term')
            free_time_set[carrier]["free_time"] = free_time if free_time else free_time_set.get(carrier).get("free_time")
            # Наследуем carrier и pod если они пустые
            if carrier:
                current_carrier = carrier
            else:
                carrier = current_carrier
            if pod:
                current_pod = pod
            else:
                pod = current_pod

            # если нет POL — пропускаем
            if not pol:
                continue

            currency = currency_dict.get("$", "USD")
            if "(" in pol:
                pol_list = pol.split("(")
                pol = pol_list[0]
            pol_port = port_dict.get(pol.title(), pol.title())
            pod_port = port_dict.get(pod.title(), pod.title())

            start_country = get_country(pol_port)
            end_country = get_country(pod_port)

            for container_type, rate in [("20GP", rate_20), ("40HQ", rate_40)]:
                if not rate or rate == "*":
                    continue
                for cost in re.split(r"[ /]+", rate):
                    cost = re.sub(r"[^\d.]", "", cost)
                    if not cost:
                        continue

                    free_time_val = free_time_set.get(carrier).get('free_time', '')
                    term_val = free_time_set.get(carrier).get('term', '')
                    vv_val = free_time_set.get(carrier).get('vv', '')

                    departures = {}
                    if etd:
                        departures["ETD"] = etd
                    if vv_val:
                        departures["vessel"] = vv_val
                    if vv_val and '/' in vv_val:
                        parts = vv_val.split('/')
                        departures["vessel"] = parts[0].strip()
                        departures["voyage_no"] = parts[1].strip() if len(parts) > 1 else ''

                    conditions_parts = []
                    if term_val:
                        conditions_parts.append(term_val.replace("\n", " "))
                    if free_time_val:
                        conditions_parts.append(f"Free time: {free_time_val}")

                    record = {
                        "transport_type": "sea",
                        "start_point": f"{pol_port}, {start_country}",
                        "end_point": f"{pod_port}, {end_country}",
                        "container_type": container_type,
                        "weight_limit": container_size_dict.get(container_type, ""),
                        "cost": cost,
                        "currency": currency,
                        "departure_dates": {},
                        "company": "NingBo Y-STAR Logistics",
                        "customs": None,
                        "conditions": " | ".join(conditions_parts) if conditions_parts else None,
                        "departures": departures if departures else None,
                        "start_location_type": "port",
                        "end_location_type": "port"
                    }
                    results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_NingBo_YSTAR_Logistics
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_NingBo_YSTAR_Logistics_impl = parse_NingBo_YSTAR_Logistics

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_NingBo_YSTAR_Logistics_impl(*args, **kwargs))

