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


def normalize(v):
    return re.sub(r'[\n\r"]+', ' ', str(v)).strip() if v not in [None, "None", ''] else ""


def parse_MoroLogistics(pdf_tables: list, company_name="Moro Logistics"):
    results = []
    container_type_list = {
        "SOC": ['20GP', '40HQ', '20RF', '40RF'],
        "COC": ['20GP', '40HQ', '40RF']
    }
    table2=False
    for idx, df in enumerate(pdf_tables, 1):
        df = df.fillna("")
        rows = df.values.tolist()
        if not rows:
            continue

        # ищем строку с заголовками (содержит POL и POD)
        header_row_idx = None
        for i, row in enumerate(rows):
            row_ = [v for v in row if v!='' ]
            joined = " ".join(map(str, row_))
            if "POL" in joined and "POD" in joined:
                header_row_idx = i
                break
        if header_row_idx is None:
            print(f"⚠️ Таблица {idx}: не найдена строка с заголовками")
            continue

        headers_ = [normalize(c) for c in rows[header_row_idx] if normalize(c)]
        if len(headers_) < 3:
            print(f"⚠️ Таблица {idx}: мало колонок после очистки")
            continue
        headers = []
        for header in headers_:
            if header == "SOC" or header == "COC":
                for conteiner_type in container_type_list[header]:
                    headers.append(f"{header}_{conteiner_type}")
            else:
                headers.append(header)
        # данные ниже строки с заголовками
        #print(headers)
        data_rows = []
        CTSP = False
        NLE = False
        for r in rows[header_row_idx + 1:]:
            #print("R = ",r)
            clean = []
            if "SPB CTSP" in r:
                CTSP = True
            elif "Novorossiysk(NLE)" in r:
                NLE = True
            clean = [normalize(x) for x in r]
            if CTSP and not NLE:
                cleanV1 = clean[:3]
                #print(clean,cleanV1)
                for x in range(3, len(clean)):
                    if clean[x] not in [None, "None", '']:
                        cleanV1.append(clean[x])
                clean = cleanV1
            elif NLE:
                cleanV1 = clean[:2]
                #print(clean,cleanV1)
                cleanV1.append(clean[3])
                for x in range(4, len(clean)):
                    if clean[x] not in [None, "None", '']:
                        cleanV1.append(clean[x])
                clean = cleanV1
            #print(clean)
            if clean[0] == '':
                continue
            # выравниваем по длине заголовков
            if len(clean) < len(headers):
                clean += [""] * (len(headers) - len(clean))
            elif len(clean) > len(headers):
                clean = clean[:len(headers)]
            data_rows.append(clean)
        df_clean = pd.DataFrame(data_rows, columns=headers)
        df_clean = df_clean.replace("None", "").fillna("")
        #print(df_clean)
        # если столбцы названы странно — переименуем
        rename_map = {}
        for c in df_clean.columns:
            lc = c.lower()
            if "etd" in lc:
                rename_map[c] = "ETD"
            elif "pol" in lc:
                rename_map[c] = "POL"
            elif "pod" in lc:
                rename_map[c] = "POD"
            elif "carrier" in lc:
                rename_map[c] = "Carrier"
            elif "remark" in lc:
                rename_map[c] = "Remarks"
            elif "direct" in lc:
                rename_map[c] = "Direct"
            elif "free" in lc:
                rename_map[c] = "Free Time"
        df_clean.rename(columns=rename_map, inplace=True)

        # заполняем пустые значения POD и Carrier вниз
        for col in ["POD", "Carrier"]:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].replace("", pd.NA).ffill()
        
        # основной парсинг
        for _, row in df_clean.iterrows():
            #row = v for v in row_ if v!='' 
            pol = row.get("POL", "")
            pod = row.get("POD", "")
            carrier = row.get("Carrier", "")
            etd = row.get("ETD", "")
            remarks = row.get("Remarks", "")
            direct = row.get("Direct", "")
            free_time = row.get("Free Time", "")
            if pol == "POL":
                table2=True
                continue

            # собираем тарифы
            for soc_coc in container_type_list.keys():
                cont_types = container_type_list[soc_coc]
                for cont_type in cont_types:
                    soc_coc_=soc_coc
                    cont = f"{soc_coc}_{cont_type}"
                    if cont not in df_clean.columns:
                        continue
                    
                    cost_raw = str(row.get(cont, "")).strip()
                    if not cost_raw or cost_raw in ["/", "-", "—"]:
                        continue
                    try:
                        cost = int(cost_raw)
                    except Exception as e:
                        continue

                    for p in re.split(r"[,/]", pol):
                        p = p.strip()
                        if not p:
                            continue

                        pol_port = port_dict.get(p.title(), p.title())
                        pod_port = region_dict.get(pod.title(), pod.title())
                        start_country = get_country(pol_port)
                        end_country = get_country(pod_port)

                        if table2 and cont in ["SOC_40HQ", "SOC_20GP"]:
                            etd = row.get("SOC_20RF", "")
                            direct = row.get("SOC_40RF", "")
                            free_time = row.get("COC_20GP", "")
                            soc_coc_ = "COC"
                        elif table2:
                            continue

                        departures = {}
                        if carrier:
                            departures["vessel"] = carrier
                        if etd:
                            departures["ETD"] = etd

                        conditions_parts = [f"{soc_coc_}. {pod}"]
                        if direct:
                            conditions_parts.append(f"Маршрут: {direct}")
                        if free_time:
                            conditions_parts.append(f"Free time: {free_time}")
                        if remarks:
                            conditions_parts.append(f"Remarks: {remarks}")

                        results.append({
                            "transport_type": "sea",
                            "start_point": f"{pol_port}, {start_country}",
                            "end_point": f"{pod_port}, {end_country}",
                            "container_type": cont_type,
                            "weight_limit": container_size_dict.get(cont_type, ""),
                            "cost": cost,
                            "currency": currency_dict.get("$", "USD"),
                            "departure_dates": [],
                            "company": company_name,
                            "customs": None,
                            "conditions": " | ".join(conditions_parts),
                            "departures": departures if departures else None,
                            "start_location_type": "port",
                            "end_location_type": "port"
                        })

    return pd.DataFrame(results)


def get_tables_pdf_MoroLogistics(url, path, company):
    pdf_path = Path(path)

    tables_data = []
    table_str = list()
    len_page = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            len_page += 1
            for table in page.extract_tables():
                table_str += table
            text = page.extract_text()
            if text:
                text_list = text.split('\n')
                for line in text_list:
                    if len_page >= 3:
                        split_ = line.split()
                        if len(split_) >= 4:
                            try:
                                gp20 = int(split_[1])
                                hq40 = int(split_[2])
                                table_str += [[split_[0], None, None, None, None, split_[1], None, None, split_[2], None, split_[3], None, None, None, None, None, None, None, None]]
                            except Exception as e:
                                continue
        df = pd.DataFrame(table_str)
        tables_data.append(df)

    # Сохранение таблиц
    for i, df in enumerate(tables_data, 1):
        df.to_csv(f"tablets/table_{i}_{company}.csv", index=False)
    
    return tables_data

# _segments_wrapper_for_parse_MoroLogistics
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_MoroLogistics_impl = parse_MoroLogistics

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_MoroLogistics_impl(*args, **kwargs))

