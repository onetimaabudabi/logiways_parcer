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
    get_city_port
)

def parse_Mohill(file_path: str):
    """
    Парсит Mohill.xlsx (листы: 'SPB ', 'NOVO', 'VVO+Railway') в унифицированный DataFrame.

    Выходные столбцы:
      - type_route         — тип маршрута ("Морской фрахт" / "ЖД")
      - pol                — порт/город отправления
      - pod                — порт/город выгрузки
      - transshipment      — (не используется здесь, оставляем None)
      - destination        — конечный пункт (для моря = POD/терминал; для ЖД = FOR)
      - container          — тип контейнера ("20GP" / "40HQ")
      - type_container     — дублирует container (для совместимости)
      - size               — "до 24т" для 20GP, "до 28т" для 40HQ
      - tarif              — ставка (число)
      - currency           — "$" или "руб"
      - security           — "ВОХР" при наличии в Remarks (иначе None)
      - SOC/COC / own      — "COC"
      - carrier            — перевозчик/оператор из столбца Carrier
      - sheet              — имя листа (для трассировки)
    """
    xl = pd.ExcelFile(file_path)
    rows = []
    company = "Mohill Rus"
    def _clean_num(val):
        if pd.isna(val):
            return None
        if isinstance(val, (int, float, np.integer, np.floating)):
            return float(val)
        s = str(val)
        m = re.search(r'(\d+(?:[.,]\d+)?)', s.replace(' ', ''))
        return float(m.group(1).replace(',', '.')) if m else None

    def _contains_vohr(text: str) -> bool:
        if not text:
            return False
        t = str(text).upper()
        return ("ВОХР" in t) or ("VOHR" in t)

    def _extract_usd_rub(text):
        """Разбирает строку вида '1200USD + 215000RUB' -> (1200.0, 215000.0)."""
        if text is None or (isinstance(text, float) and np.isnan(text)):
            return (None, None)
        t = str(text).upper().replace(' ', '')
        m_usd = re.search(r'(\d+(?:[.,]\d+)?)USD', t)
        m_rub = re.search(r'(\d+(?:[.,]\d+)?)RUB', t)
        usd = float(m_usd.group(1).replace(',', '.')) if m_usd else None
        rub = float(m_rub.group(1).replace(',', '.')) if m_rub else None
        return usd, rub

    for sheet in xl.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet)

        # Листы СПб/Новороссийск: первая строка — легенда размеров ("20GP", "40HQ")
        if sheet.strip() in ("SPB", "NOVO"):
            if len(df) == 0:
                continue
            df = df.iloc[1:].reset_index(drop=True)  # пропускаем строку-легенду
            if 'Carrier' in df.columns:
                df['Carrier'] = df['Carrier'].ffill()
            for _, row in df.iterrows():
                pol_raw = str(row.get('POL') or '').strip()
                pod = str(row.get('POD') or '').strip()
                if not pol_raw:
                    continue
                carrier = (str(row.get('Carrier') or '').strip()) or None
                remarks = (str(row.get('Remarks') or '').strip()) or None
                route = (str(row.get('Route') or '').strip()) or None
                time = (str(row.get('V/V ETD') or '').strip()) or None
                security = "ВОХР" if _contains_vohr(remarks) else None

                ETD = None
                vessel = None
                voyage_no = None
                time_list = time.split()
                if (len(time_list) != 3 and len(time_list) != 1):
                    ETD = convert_date(f"{time_list[0]} {time_list[1]}")
                    if len(time_list)>2:
                        vessel = " ".join(time_list[2:-1])
                        voyage_no = time_list[-1]

                t20 = _clean_num(row.get('COC'))          # 20GP
                t40 = _clean_num(row.get('Unnamed: 4'))   # 40HQ

                # Если POL содержит несколько портов — делим
                pol_list = [p.strip() for p in pol_raw.split('/') if p and p.strip()]

                for pol in pol_list:
                    pol_port = port_dict.get(pol, pol)
                    pod_port = port_dict.get(pod.split()[0] if "SPB" in pod or "NOVO" in pod else pod, pod)
                    departures = None
                    if ETD is not None and vessel is not None:
                        departures={
                            "vessel": vessel,
                            "voyage_no": voyage_no,
                            "ETD": ETD
                        }
                    elif ETD is not None:
                        departures={
                            "ETD": ETD
                        }
                    if t20 is not None:
                        rows.append(TariffSegment(
                            transport_type= "sea",
                            start_point= f"{pol_port}, {get_country(pol_port)}",
                            end_point= f"{pod_port}, {get_country(pod_port)}",
                            container_type= "20GP",
                            weight_limit= "24",
                            max_weight_kg="24",
                            cost= t20,
                            departures=departures,
                            currency= currency_dict.get("$","$"),
                            company= company,
                            end_location_type="port",
                            start_location_type="port",
                            port_service_term="FILO",
                            conditions= f"Route:{route}, Remarks:{remarks}, POD:{pod}",
                            container_ownership="COC",
                            parent_start_location=pol_port,
                            parent_start_location_type="city",
                            parent_end_location=pod_port,
                            parent_end_location_type="city"
                        ))
                    if t40 is not None:
                        rows.append(TariffSegment(
                            transport_type= "sea",
                            start_point= f"{pol_port}, {get_country(pol_port)}",
                            end_point= f"{pod_port}, {get_country(pod_port)}",
                            container_type= "40HQ",
                            weight_limit= "28",
                            max_weight_kg="28",
                            cost= t40,
                            departures=departures,
                            end_location_type="port",
                            start_location_type="port",
                            port_service_term="FILO",
                            currency= currency_dict.get("$","$"),
                            company= company,
                            conditions= f"Route:{route}, Remarks:{remarks}, POD:{pod}",
                            container_ownership="COC",
                            parent_start_location=pol_port,
                            parent_start_location_type="city",
                            parent_end_location=pod_port,
                            parent_end_location_type="city"
                        ))

        # Лист Владивосток + ЖД (делим на 2 плеча)
        elif sheet.strip() == "VVO+Railway":
            break
            if len(df) == 0:
                continue
            df = df.iloc[1:].reset_index(drop=True)  # аналогично: часто есть служебная строка
            if 'Carrier' in df.columns:
                df['Carrier'] = df['Carrier'].ffill()

            for _, row in df.iterrows():
                fob_raw = str(row.get('FOB') or '').strip()
                if not fob_raw:
                    continue
                cy = (str(row.get('CY') or '').strip()) or None
                for_dest = (str(row.get('FOR') or '').strip()) or None
                carrier = (str(row.get('Carrier') or '').strip()) or None
                remarks = (str(row.get('Remarks') or '').strip()) or None
                validity = (str(row.get('Validity') or '').strip()) or None
                time = (str(row.get('V/V ETD') or '').strip()) or None
                security = "ВОХР" if _contains_vohr(remarks) else None
                usd, rub = _extract_usd_rub(row.get('COC'))

                # Плечо 1: море до Владивостока (40HQ)
                if usd is not None:
                    for pol in [p.strip() for p in fob_raw.split('/') if p and p.strip()]:
                        pol_port = port_dict.get(pol, pol)
                        rows.append(TariffSegment(
                            transport_type= "sea",
                            start_point= f"{pol_port}, {get_country(pol_port)}",
                            end_point= "Владивосток, Россия",
                            final_destination= cy or "Владивосток",
                            container_type= "40HQ",
                            port_service_term="FILO",
                            weight_limit= "28",
                            cost= usd,
                            currency= currency_dict.get("$","$"),
                            departure_dates= time,
                            company= company,
                            conditions= f"Remarks:{remarks}",
                            container_ownership= "COC"
                        ))

                # Плечо 2: ЖД Владивосток → FOR (40HQ)
                if rub is not None and for_dest:
                    pod_port = region_dict.get(for_dest, for_dest)
                    rows.append(TariffSegment(
                        transport_type= "rail",
                        start_point= "Владивосток, Россия",
                        end_point= f"{pod_port}, {get_country(region_dict.get(pod_port,pod_port))}",
                        final_destination= f"All, {get_country(region_dict.get(pod_port,pod_port))}",
                        container_type= "40HQ",
                        weight_limit= "28",
                        port_service_term="FILO",
                        cost= rub,
                        currency= currency_dict.get("руб","руб"),
                        departure_dates= time,
                        company= company,
                        conditions= f"Remarks:{remarks}",
                        container_ownership= "COC"
                    ))

        # Если появятся новые листы — аккуратно игнорируем или можно добавить сюда ветку парсинга

    df_out = pd.DataFrame(rows)

    # приведение типов/пробелов
    if not df_out.empty:
        df_out["start_point"] = df_out["start_point"].str.strip()
        df_out["end_point"] = df_out["end_point"].str.strip()
        # сортировка для стабильности
        '''df_out = df_out[
            ["transport_type","start_point","end_point","final_destination",
             "container_type","weight_limit","cost","currency",
             "conditions"]
        ]'''
    return df_out

# _segments_wrapper_for_parse_Mohill
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Mohill_impl = parse_Mohill

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Mohill_impl(*args, **kwargs))

