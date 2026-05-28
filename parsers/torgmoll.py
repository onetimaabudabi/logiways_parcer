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
from .models import TariffSegment


def parse_CNR_SPB_sheet_Torgmoll(df, sheet_name):
    """Парсит лист КНР-СПБ"""
    result = []
    company = "Torgmoll"
    # Ищем строку с заголовками (строка 2)
    header_row = 2
    charges_peter = False
    charges_peter_i = 0
    charges_kalin = False
    charges_kalin_i = 0
    # Обрабатываем данные начиная со строки 3
    for i in range(3, len(df)):
        row = df.iloc[i].astype(str).tolist()
        
        # Пропускаем пустые строки
        if all(pd.isna(cell) or str(cell).strip() == 'nan' for cell in row):
            continue
        if "St. Petersburg Import Charges" in str(row[0]):
            charges_peter = True
            continue
        if "KALININGRAD Import Charges" in str(row[0]):
            charges_kalin = True
            charges_peter_i = 0
            charges_peter = False
            continue
        # Ищем строки с портами и тарифами
        if (not charges_peter and not charges_kalin) and row[0] and str(row[0]).strip() not in ['nan', '']:
            pol = str(row[0]).strip()
            pod_list = str(row[1]).strip().split("(")
            #pod = pod_list[0].strip()
            pod = port_dict.get(str(row[1]).strip().replace('\n', ''),str(row[1]).strip().replace('\n', ''))
            # Проверяем, есть ли тарифы в строке
            for col_idx in range(1, len(row)):
                if row[col_idx] and str(row[col_idx]).strip() not in ['nan', '']:
                    tariff = str(row[col_idx]).strip() if row[col_idx] != "/" and row[col_idx] != "—" else None
                    
                    # Определяем тип контейнера по заголовку колонки
                    container_type = get_container_type_from_header(df.iloc[header_row, col_idx])
                    
                    if container_type and tariff:
                        if "/" in pol:
                            for pol_item in pol.split("/"):
                                pol_item = pol_item.strip()
                                pol_port = port_dict.get(pol_item, pol_item)
                                result.append({
                                    "transport_type": "sea",
                                    "start_point": f"{pol_port}, {get_country(pol_port)}",
                                    "end_point": f"{pod}, Россия",
                                    "final_destination": "All, Россия",
                                    "container_type": container_type,
                                    "weight_limit": container_size_dict.get(container_type,""),
                                    "cost": tariff,
                                    "currency": currency_dict.get("$","$"),
                                    "departure_dates": "",
                                    "company": company,
                                    "conditions": ("FI-FO COC." if "COC" in str(df.iloc[header_row, col_idx]) else "FI-FO SOC.")
                                    + f" Терминал: {pod_list[1].replace(')','')}",
                                    "start_location_type": "port",
                                    "end_location_type": "port"
                                })
                        else:
                            pol_port = port_dict.get(pol, pol)
                            result.append({
                                "transport_type": "sea",
                                "start_point": f"{pol_port}, {get_country(pol_port)}",
                                "end_point": f"{pod}, Россия",
                                "final_destination": "All, Россия",
                                "container_type": container_type,
                                "weight_limit": container_size_dict.get(container_type,""),
                                "cost": tariff,
                                "currency": currency_dict.get("$","$"),
                                "departure_dates": "",
                                "company": company,
                                "conditions": ("FI-FO COC." if "COC" in str(df.iloc[header_row, col_idx]) else "FI-FO SOC.")
                                + f" Терминал: {pod_list[1].replace(')','')}",
                                "start_location_type": "port",
                                "end_location_type": "port"
                            })

        if charges_peter and "CHARGE" in str(row[0]):
            charges_peter_i = i
            continue
        
        if charges_kalin and "CHARGE" in str(row[0]):
            charges_kalin_i = i
            continue
        
        if charges_peter_i != 0 or charges_kalin_i !=0:
            for col_idx in range(2, len(row)):
                if row[col_idx] and str(row[col_idx]).strip() not in ['nan', '']:
                    container_types = get_container_type_from_header(df.iloc[charges_peter_i if charges_peter_i !=0 else charges_kalin_i, col_idx]).replace(" ","") + "/"
                    for container_type in container_types.split("/"):
                        for res in result:
                            if res["container_type"] == container_type:
                                if "Калининград" in res["end_point"] and charges_kalin_i !=0:
                                    res["conditions"] += f"\n{str(row[0]).strip()}: {str(row[col_idx]).strip()}."
                                elif "Санкт-Петербург" in res["end_point"] and charges_peter_i !=0:
                                    res["conditions"] += f"\n{str(row[0]).strip()}: {str(row[col_idx]).strip()}."
        
        if "Примечание" in str(row[0]):
            charges_kalin = False 
            charges_kalin_i = 0
            for res in result:
                res["conditions"] += f"\n{str(row[0])}"


    return result


def parse_YUVA_sheet_Torgmoll(df, sheet_name):
    """Парсит лист ЮВА (+BUSAN) - КНР - СПБ"""
    result = []
    
    # Ищем строку с заголовками (строка 1)
    header_row = 1
    
    # Обрабатываем данные начиная со строки 3
    for i in range(3, len(df)):
        row = df.iloc[i].astype(str).tolist()
        #print(row)
        # Пропускаем пустые строки
        if all(pd.isna(cell) or str(cell).strip() == 'nan' for cell in row):
            continue
        
        # Ищем строки с портами и тарифами
        if row[0] and str(row[0]).strip() not in ['nan', '']:
            pol = str(row[0]).strip()
            transshipment = str(row[1]).strip() if len(row) > 1 and str(row[1]).strip() not in ['nan', ''] else None
            
            # Проверяем тарифы для 20GP и 40HC
            if len(row) > 2 and row[2] and str(row[2]).strip() not in ['nan', '']:
                tariff_20gp = str(row[2]).strip() if row[2] != "/" and row[2] != "—" else None
                if tariff_20gp:
                    result.append({
                        "transport_type": "sea",
                        "start_point": pol.title(),
                        "end_point": "Санкт-Петербург",
                        "final_destination": "All, Россия",
                        "container_type": "20GP",
                        "weight_limit": container_size_dict.get("20GP",""),
                        "cost": tariff_20gp,
                        "currency": currency_dict.get("$","$"),
                        "conditions": "COC"
                    })
            
            if len(row) > 3 and row[3] and str(row[3]).strip() not in ['nan', '']:
                tariff_40hc = str(row[3]).strip() if row[3] != "/" and row[3] != "—" else None
                if tariff_40hc:
                    result.append({
                        "transport_type": "sea",
                        "start_point": pol,
                        "end_point": "Санкт-Петербург", 
                        "final_destination": "All, Россия",
                        "container_type": "40HC",
                        "weight_limit": container_size_dict.get("40HC",""),
                        "cost": tariff_40hc,
                        "currency": currency_dict.get("$","$"),
                        "conditions": "COC"
                    })
    
    return result


def parse_Detention_sheet_Torgmoll(df, sheet_name):
    """Парсит лист Detention"""
    result = []
    
    # Этот лист содержит информацию о демередже и детеншене
    # Обычно это не тарифы на перевозку, а дополнительные сборы
    # Поэтому возвращаем пустой список или можно добавить специальную обработку
    
    return result

def get_container_type_from_header(header_cell):
    """Определяет тип контейнера из заголовка колонки"""
    header = str(header_cell).lower()
    
    if '20gp' in header or '20 gp' in header:
        return '20GP'
    elif '40hc' in header or '40 hc' in header:
        return '40HC'
    elif '20rf' in header or '20 rf' in header:
        return '20RF'
    elif '40rf' in header or '40 rf' in header:
        return '40RF'
    elif '20tank' in header or '20 tank' in header:
        return '20TK'
    elif len(header.split()) == 1:
        return header.upper()
    else:
        return None


def parse_Torgmoll(file_path: str):
    xl = pd.ExcelFile(file_path)
    result = []
    company = "Torgmoll"
    for sheet in xl.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet, header=None)
        
        if "КНР-СПБ" in sheet and "BUSAN" not in sheet:
            result.extend(parse_CNR_SPB_sheet_Torgmoll(df, sheet))
        '''elif "BUSAN" in sheet:
            result.extend(parse_YUVA_sheet_Torgmoll(df, sheet))'''
        '''elif sheet == "Detention":
            result.extend(parse_Detention_sheet_Torgmoll(df, sheet))'''
    
    return pd.DataFrame(result)

# _segments_wrapper_for_parse_Torgmoll
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Torgmoll_impl = parse_Torgmoll

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Torgmoll_impl(*args, **kwargs))

