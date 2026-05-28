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


def parse_UnknownCompany3(file_path: str, company_name="Неизвестная_компания_3"):
    df = pd.read_excel(file_path, sheet_name = company_name)
    results = []
    df = df.fillna("")

    # ============================================
    # 1. Собрать весь текст в одну строку
    # ============================================
    full_text = ""
    for row in df.values:
        for cell in row:
            #cell = clean(cell)
            if cell:
                full_text += '\n' + cell

    if not full_text.strip():
        return pd.DataFrame()

    # ============================================
    # 2. Разбить на смысловые блоки
    # блоки отделяются кавычками
    # ============================================
    blocks = full_text.split('\n') #re.split(r'"', full_text)
    blocks = [b.strip() for b in blocks if b.strip()]
    # ============================================
    # 3. Вспомогательная функция
    # ============================================
    def add_record(pol, pod, border, etd, cost, container, mode, customs, route_note=""):
        pol_port = port_dict.get(pol.title(), pol)
        pod_port = region_dict.get(pod.title(), pod)

        start_country = get_country(pol_port)
        end_country = get_country(pod_port)

        border_clean = border.replace("border", "").strip() if border else ""
        border_russian = border_dict.get(border_clean.lower(), border_clean)

        return {
            "transport_type": mode,
            "start_point": f"{pol_port}, {start_country}",
            "end_point": f"{pod_port}, {end_country}",
            "final_destination": f"All, {end_country}",

            "container_type": container,
            "weight_limit": container_size_dict.get(container, ""),

            "cost": cost,
            "currency": "USD",

            "departure_dates": etd if etd else [],
            "company": company_name,

            "customs": None,
            "conditions": route_note.strip() or None,
            "border_point": border_russian if border_russian else None,
            "departures": {"ETD": etd} if etd else None,
            "start_location_type": "port",
            "end_location_type": "rail_station" if mode == "rail" else ("port" if mode == "sea" else None)
        }

    # ============================================
    # 4. Парсим каждый блок
    # ============================================
    for block in blocks:
        text = block.strip()

        # ----------------------------------------
        # 🔵 TRAIN LINES
        # ----------------------------------------
        if "train" in text.lower():

            # Пример блока:
            # 'Tianjin train-- Erlianu border--Bely rast ETD:8.14/8.21 FOB Tianjin USD3850/40HC;'

            # 1. Выделяем начало маршрута
            m = re.search(
                r"(\w+)\s*train.*?--\s*([\w/]+)\s*border?\s*--\s*([\w ]+)",
                text,
                re.I
            )
            if not m:
                continue

            dep_city = m.group(1)
            border = m.group(2)
            pod = m.group(3).replace("ETD","").strip()

            # 2. ETD — может быть несколько дат
            etd_match = re.search(r"ETD[: ]*([0-9./A-Za-z]+)", text)
            etd = etd_match.group(1).split("/") if etd_match else []

            # 3. FOB указания (их может быть много)
            # пример:
            # FOB Tianjin USD3850/40HC
            # FOB Guangzhou/Shenzhen USD4350/40HC
            fobs = re.finditer(
                r"FOB\s+.*",
                text,
                re.I
            )
            
            for f in fobs:
                container = "40HC" if "40HC" in f.group(0) else ""
                fo_fobs = f.group(0).split(";")
                for fo_fob in fo_fobs:
                    if fo_fob:
                        fo_ = fo_fob.split()
                        pol_list = fo_[1].split("/")
                        cost = fo_[2].split("/")[0] if "/" in fo_[2] else fo_[2]

                        for pol in pol_list:
                            results.append(add_record(
                                pol=pol,
                                pod=pod,
                                border=border,
                                etd=etd,
                                cost=cost.replace("USD", ""),
                                container=container,
                                mode="rail",
                                customs=text,
                                route_note=f"Train: {pol} - {border} - {pod}"
                            ))

        # ----------------------------------------
        # 🔵 TRUCK LINES (обычный автотранспорт)
        # ----------------------------------------
        if "/Truck" in text:
            continue
            # Пример:
            # FOB Qingdao/Tianjin/Cangzhou to Moscow USD9500/Truck

            fobs = re.finditer(
                r"FOB\s+([A-Za-z/]+)\s+to\s+([A-Za-z ]+)\s+USD(\d+)/Truck",
                text
            )
            for f in fobs:
                pol_list = f.group(1).split("/")
                pod = f.group(2)
                cost = f.group(3)

                for pol in pol_list:
                    results.append(add_record(
                        pol=pol,
                        pod=pod,
                        border="Truck",
                        etd="",
                        cost=cost,
                        container="TRUCK",
                        mode="truck",
                        customs=text,
                        route_note=f"Truck: {pol} - {pod}"
                    ))

        # ----------------------------------------
        # 🔵 SEA (море)
        # ----------------------------------------
        if "SEA" in text.upper():

            # Пример строки:
            # FOB China main port - St Peterburg by SEA USD3800-4550/20GP ...

            m = re.search(
                r"FOB\s+China.*?St\s*peterburg.*?USD([\d-]+)/20GP.*?USD([\d-]+)/40HQ.*?ETD[: ]*([0-9.\-A-Za-z/]+)",
                text,
                re.I
            )
            if m:
                cost20 = m.group(1).split("-")[0]
                cost40 = m.group(2).split("-")[0]
                etd = m.group(3)

                results.append(add_record(
                    pol="China main port",
                    pod="St Petersburg",
                    border="Sea",
                    etd=etd,
                    cost=cost20,
                    container="20GP",
                    mode="sea",
                    customs=text,
                    route_note="Sea freight: China main port - St Petersburg"
                ))
                results.append(add_record(
                    pol="China main port",
                    pod="St Petersburg",
                    border="Sea",
                    etd=etd,
                    cost=cost40,
                    container="40HQ",
                    mode="sea",
                    customs=text,
                    route_note="Sea freight: China main port - St Petersburg"
                ))

        # ----------------------------------------
        # 🔵 TIR SERVICE (FTL)
        # ----------------------------------------
        if "FTL" in text.upper() or "TIR SERVICE" in text.upper():
            continue
            # Пример:
            # MOSCOW --MANZHOULIA--TIANJIN USD4950/FTL

            ftl_matches = re.finditer(
                r"MOSCOW\s*--\s*MANZHOULIA\s*--\s*([A-Za-z/]+)\s*USD(\d+)/FTL",
                text,
                re.I
            )
            for f in ftl_matches:
                pod = f.group(1)
                cost = f.group(2)

                results.append(add_record(
                    pol="Moscow",
                    pod=pod,
                    border="Manzhouli",
                    etd="",
                    cost=cost,
                    container="FTL",
                    mode="tir",
                    customs=text,
                    route_note=f"TIR: Moscow - Manzhouli - {pod}"
                ))

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_UnknownCompany3
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_UnknownCompany3_impl = parse_UnknownCompany3

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_UnknownCompany3_impl(*args, **kwargs))

