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


def parse_UnknownCompany4(file_path: str, company_name="Неизвестная_компания_4"):
    df = pd.read_excel(file_path, sheet_name = company_name)
    results = []
    df = df.fillna("")

    # Вся вторая ячейка — многострочный текст
    full_text = ""
    for row in df.values:
        for cell in row:
            cell = clean(cell)
            if cell and ("FOB" in cell or "R/F" in cell):
                full_text += "\n" + cell

    if not full_text.strip():
        print("⚠ Нет данных FOB/RF — таблица пуста")
        return pd.DataFrame()

    # Разделяем записи по FOB-блокам
    blocks = re.split(r'(?=FOB )', full_text)
    blocks = [b.strip() for b in blocks if b.strip()]

    for block in blocks:

        # -----------------------------
        # 1. POL список (FOB Shanghai/Wuxi/Suzhou...)
        # -----------------------------
        m_pol = re.search(r"FOB\s+([A-Za-z0-9' /.-]+?)\s+-", block)
        if not m_pol:
            continue
        pol_list_raw = m_pol.group(1)
        pol_cities = [p.strip() for p in pol_list_raw.split("/")]

        # -----------------------------
        # 2. Departure station
        # -----------------------------
        m_dep = re.search(r"-\s*([A-Za-z0-9' ]+?) station", block)
        departure_station = clean(m_dep.group(1) if m_dep else "")

        # -----------------------------
        # 3. Border
        # -----------------------------
        m_border = re.search(r"station\s*-\s*([A-Za-z0-9' /]+?)\s*-\s*", block)
        border = clean(m_border.group(1) if m_border else "")

        # -----------------------------
        # 4. POD (последняя часть)
        # -----------------------------
        m_pod = re.search(r"-\s*([A-Za-z0-9' ]+?)\s*(?:\n|R/F:|$)", block)
        pod_city = clean(m_pod.group(1) if m_pod else "")

        # -----------------------------
        # 5. COST
        # могут быть варианты:
        # USD4050/40'HQ
        # USD5000/5100/5000/5000 --- 40'HQ
        # -----------------------------
        m_cost = re.search(r"R/F:\s*USD\s*([\d/]+)", block, re.I)
        if m_cost:
            rate_values = m_cost.group(1).split("/")
            cost = re.sub(r"[^\d]", "", rate_values[0])
        else:
            cost = ""

        # -----------------------------
        # 6. Container type (40HQ)
        # -----------------------------
        m_ct = re.search(r"(40'?HQ)", block, re.I)
        container_type = m_ct.group(1).upper().replace("'", "") if m_ct else "40HQ"

        # -----------------------------
        # 7. ETD
        # -----------------------------
        m_etd = re.search(r"ETD:\s*([0-9A-Za-z/.-]+)", block)
        etd = clean(m_etd.group(1) if m_etd else "")

        # -----------------------------
        # 8. CUT OFF
        # -----------------------------
        m_cut = re.search(r"Cut ?off:\s*(.+?)(?:$|\s{2,})", block, re.I)
        cutoff = clean(m_cut.group(1).split('"')[0] if m_cut else "")

        # -----------------------------
        # 9. Генерация записей для каждого POL
        # -----------------------------
        for pol in pol_cities:

            pol_port = port_dict.get(pol.title(), pol.title())
            pod_port = region_dict.get(pod_city.title(), pod_city)

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

                "departure_dates": [etd] if etd else [],
                "company": company_name,

                "border_point": border,
                "departures": {"cutoff": cutoff} if cutoff else None,

                "conditions": f"FOB COC. Departure station: {departure_station}",

                "start_location_type": "port",
                "end_location_type": "rail_station"
            }

            results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_UnknownCompany4
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_UnknownCompany4_impl = parse_UnknownCompany4

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_UnknownCompany4_impl(*args, **kwargs))

