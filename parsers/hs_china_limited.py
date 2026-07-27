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


def add_tariff_entry_HS_CHINA_LIMITED(result, region, pod, pol, rate, validity, route, remark):
    """Добавляет записи тарифов в результат"""
    if not pod or not rate:
        return
    company = "HS CHINA LIMITED"
    # Разбираем тариф (формат "1700/2000" или "3800/4300")
    rates = str(rate).split('/')
    
    # Определяем типы контейнеров
    container_types = []
    if len(rates) >= 2:
        container_types = ['20DC', '40HC']
    elif len(rates) == 1:
        container_types = ['20DC']  # По умолчанию
    
    # Разбираем POL (порт отправления)
    pol_ports = []
    if pol and '/' in str(pol):
        pol_ports = [p.strip() for p in str(pol).split('/')]
    elif pol:
        pol_ports = [str(pol).strip()]
    
    # Разбираем REMARK (SOC/COC)
    soc_coc_options = []  # По умолчанию
    if remark and '/' in str(remark):
        soc_coc_options = [r.strip() for r in str(remark).split('/')]
    elif remark:
        soc_coc_options.append(str(remark).strip())
    
    # Создаем записи для каждого порта отправления и типа контейнера
    for pol_port in pol_ports:
        for i, container_type in enumerate(container_types):
            if i < len(rates):
                tariff_value = rates[i]
                pol_r = port_dict.get(pol_port, pol_port)
                pod_r = port_dict.get(pod, pod)
                for soc_coc in soc_coc_options:
                    result.append({
                        "transport_type": "sea",
                        "start_point": f"{pol_r}, {get_country(pol_r)}",  # Порт отправления
                        "end_point": f"{pod_r}, {region_dict.get(region,region)}",      # Порт назначения
                        "container_type": container_type,
                        "weight_limit": container_size_dict.get(container_type,""),
                        "cost": tariff_value,
                        "currency": currency_dict.get("$","$"),
                        "departure_dates": "",
                        "company": company,
                        "conditions": f"{soc_coc} Route:{route} Validity:{validity}"
                    })

def parse_HS_CHINA_LIMITED(file_path: str):
    df = pd.read_excel(file_path, header=None)
    result = []
    #print(df.columns.tolist())
    # Ищем строку с заголовками (обычно строка 1)
    
    header_row = None
    for i in range(min(10, len(df))):
        row = df.iloc[i].astype(str).str.strip().tolist()
        if 'POD' in row and ('POL' in row or 'POL(FOB)' in row) and 'RATE' in row:
            header_row = i
            break
    
    if header_row is None:
        print("Не найдена строка с заголовками")
        return pd.DataFrame()
    
    # Обрабатываем данные начиная со строки после заголовков
    current_region = None
    current_pol = None
    current_rate = None
    current_validity = None
    current_route = None
    current_remark = None
    
    for i in range(header_row + 1, len(df)):
        row = df.iloc[i].astype(str).tolist()
        # Пропускаем пустые строки
        if all(pd.isna(cell) or str(cell).strip() == 'nan' for cell in row):
            continue
        
        # Определяем тип данных в строке
        if row[0] and str(row[0]).strip() not in ['nan', '']:
            # Это регион (USWC, USEC, USGC, CANADA)
            current_region = str(row[0]).strip()
            current_pol = str(row[2]).strip() if len(row) > 2 and str(row[2]).strip() not in ['nan', ''] else None
            current_rate = str(row[3]).strip() if len(row) > 3 and str(row[3]).strip() not in ['nan', ''] else None
            current_validity = str(row[4]).strip() if len(row) > 4 and str(row[4]).strip() not in ['nan', ''] else None
            current_route = str(row[5]).strip() if len(row) > 5 and str(row[5]).strip() not in ['nan', ''] else None
            current_remark = str(row[6]).strip() if len(row) > 6 and str(row[6]).strip() not in ['nan', ''] else None
            # Если есть порт в колонке 1, добавляем запись
            if row[1] and str(row[1]).strip() not in ['nan', '']:
                pod = str(row[1]).strip()
                if "/" in pod:
                    for pod_item in pod.split("/"):
                        add_tariff_entry_HS_CHINA_LIMITED(result, current_region, pod_item, current_pol, current_rate, 
                               current_validity, current_route, current_remark)
                else:
                    add_tariff_entry_HS_CHINA_LIMITED(result, current_region, pod, current_pol, current_rate, 
                               current_validity, current_route, current_remark)
        
        elif row[1] and str(row[1]).strip() not in ['nan', '']:
            # Это порт назначения в колонке 1
            pod = str(row[1]).strip()
            
            # Проверяем, есть ли тариф в этой строке
            rate_in_row = str(row[3]).strip() if len(row) > 3 and str(row[3]).strip() not in ['nan', ''] else None
            
            add_tariff_entry_HS_CHINA_LIMITED(result, current_region, pod, current_pol, 
                           rate_in_row or current_rate, current_validity, current_route, current_remark)
    
    return pd.DataFrame(result)

# _segments_wrapper_for_parse_HS_CHINA_LIMITED
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_HS_CHINA_LIMITED_impl = parse_HS_CHINA_LIMITED

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_HS_CHINA_LIMITED_impl(*args, **kwargs))

