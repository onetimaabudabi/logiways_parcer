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


def parse_MarmedContainer(file_path: str):
    xl = pd.ExcelFile(file_path)
    result = []
    company = "Мармед - Контейнерное Агенство"
    def parse_IMPORT_sheet_MarmedContainer(df, sheet_name):
        results = []

        # ищем строку с POL/POD
        header_row = None
        for i, row in df.iterrows():
            values = [str(cell).strip().upper() for cell in row if pd.notna(cell)]
            if "POL" in values and "POD" in values:
                header_row = i
                break
        if header_row is None:
            return results

        # следующая строка содержит контейнерные колонки
        container_row = header_row + 1
        headers = df.iloc[header_row].fillna("").astype(str).tolist()
        container_headers = df.iloc[container_row].fillna("").astype(str).tolist()

        # формируем карту колонок
        col_map = {}
        for idx, h in enumerate(headers):
            h_clean = h.strip()
            if h_clean:
                col_map[h_clean] = idx

        # добавляем контейнерные колонки
        for idx, h in enumerate(container_headers):
            if h.strip() in container_size_dict or h.strip().replace("`","") in container_size_dict:
                col_map[h.strip()] = idx

        tarif_filter = col_map["При оплате фрахта в рублях в РФ"]
        # идём по строкам после container_row
        for _, row in df.iloc[container_row+1:].iterrows():
            if pd.isna(row[col_map.get("POL", -1)]) or pd.isna(row[col_map.get("POD", -1)]):
                continue
            
            start_point_no_filter = str(row[col_map["POL"]]).strip()
            end_point_no_filter = str(row[col_map["POD"]]).strip()

            final_destination = str(row[col_map.get("Country", "")]).strip() if "Country" in col_map else ""
            conditions = str(row[col_map.get("TERMS", "")]).strip() if "TERMS" in col_map else ""
            SOC_COC = str(row[col_map.get("CNTR", "")]).strip()
            validity = str(row[col_map.get("Validity", "")]).strip()

            for key, idx in col_map.items():
                if key in container_size_dict or key.replace("`","") in container_size_dict:
                    tariff = row[idx] if idx >= tarif_filter else "None"
                    if pd.isna(tariff):
                        continue
                    container_type = key.replace("`","") if key.replace("`","") in container_size_dict else key
                    for start_p in start_point_no_filter.split("/"):
                        pol_port = port_dict.get(start_p.strip().title(), start_p.strip().title())
                        
                        for end_p in end_point_no_filter.split("/"):
                            pod_port = port_dict.get(end_p.strip().title(), end_p.strip().title())
                            for soc_coc in SOC_COC.split("/"):
                                results.append({
                                    "transport_type": "sea",
                                    "start_point": f"{pol_port}, {get_country(pol_port)}",
                                    "end_point": f"{pod_port}, {get_country(pod_port)}",
                                    "final_destination": f"All, {get_country(pod_port)}",
                                    "container_type": container_type,
                                    "weight_limit": container_size_dict[container_type],
                                    "cost": tariff,
                                    "currency": currency_dict.get("$", "$"),
                                    "departure_dates": "",
                                    "conditions": f"{conditions} {soc_coc} Validity:{validity}",
                                    "company": company
                                })
        return results

    def parse_EXPORT_sheet_MarmedContainer(df, sheet_name):
        results = []

        # ищем строку с POL/POD
        header_row = None
        for i, row in df.iterrows():
            values = [str(cell).strip().upper() for cell in row if pd.notna(cell)]
            if "POL" in values and "POD" in values:
                header_row = i
                break
        if header_row is None:
            return results

        # следующая строка содержит контейнерные колонки
        container_row = header_row + 1
        headers = df.iloc[header_row].fillna("").astype(str).tolist()
        container_headers = df.iloc[container_row].fillna("").astype(str).tolist()

        # формируем карту колонок
        col_map = {}
        for idx, h in enumerate(headers):
            h_clean = h.strip()
            if h_clean:
                col_map[h_clean] = idx

        # добавляем контейнерные колонки
        for idx, h in enumerate(container_headers):
            if h.strip() in container_size_dict or h.strip().replace("`","") in container_size_dict:
                col_map[h.strip()] = idx

        tarif_filter = col_map["При оплате фрахта в рублях в РФ"]
        # идём по строкам после container_row
        for _, row in df.iloc[container_row+1:].iterrows():
            if pd.isna(row[col_map.get("POL", -1)]) or pd.isna(row[col_map.get("POD", -1)]):
                continue
            
            start_point_no_filter = str(row[col_map["POL"]]).strip()
            end_point_no_filter = str(row[col_map["POD"]]).strip()

            final_destination = str(row[col_map.get("Country", "")]).strip() if "Country" in col_map else ""
            conditions = str(row[col_map.get("TERMS", "")]).strip() if "TERMS" in col_map else ""

            validity = str(row[col_map.get("Validity", "")]).strip()

            PICKUP_FEE = str(row[col_map.get("PICKUP FEE", "")]).strip()

            SOC_COC = str(row[col_map.get("SOC/COC", "")]).strip()

            for key, idx in col_map.items():
                if key in container_size_dict or key.replace("`","") in container_size_dict:
                    tariff = row[idx] if idx >= tarif_filter else "None"
                    if pd.isna(tariff):
                        continue
                    container_type = key.replace("`","") if key.replace("`","") in container_size_dict else key
                    
                    

                    for start_p in start_point_no_filter.split("/"):
                        pol_port = port_dict.get(start_p.strip().title(), start_p.strip().title())
                        
                        for end_p in end_point_no_filter.split("/"):
                            pod_port = port_dict.get(end_p.strip().title(), end_p.strip().title())
                            
                            for soc_coc in SOC_COC.split("/"):
                                if "/" in PICKUP_FEE and "20" in container_type:
                                    PICKUP_FEE = PICKUP_FEE.split("/")[0].strip()
                                elif "/" in PICKUP_FEE and "40" in container_type:
                                    PICKUP_FEE = PICKUP_FEE.split("/")[1].strip()
                                results.append({
                                    "transport_type": "sea",
                                    "start_point": f"{pol_port}, {get_country(pol_port)}",
                                    "end_point": f"{pod_port}, {get_country(pod_port)}",
                                    "final_destination": f"All, {get_country(pod_port)}",
                                    "container_type": container_type,
                                    "weight_limit": container_size_dict[container_type],
                                    "cost": tariff,
                                    "currency": currency_dict.get("$", "$"),
                                    "company": company,
                                    "conditions": f"{conditions} {soc_coc} Validity:{validity} PICKUP_FEE:{PICKUP_FEE}"
                                })
        return results

    for sheet in xl.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet, header=None)
        
        if "IMPORT" in sheet:
            result.extend(parse_IMPORT_sheet_MarmedContainer(df, sheet))
        elif "EXPORT" in sheet:
            result.extend(parse_EXPORT_sheet_MarmedContainer(df, sheet))
    
    return pd.DataFrame(result)


# _segments_wrapper_for_parse_MarmedContainer
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_MarmedContainer_impl = parse_MarmedContainer

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_MarmedContainer_impl(*args, **kwargs))

