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
from .models import TariffSegment
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


def parse_tariff_matrix_to_json(df: str, output_json: str = None):
    """
    Парсит таблицы вида:
    - Колонка 0: Пункт отправления (origin), может быть заполнена только в первой строке группы
    - Колонка 1: Станция назначения (destination)
    - Далее несколько колонок тарифов с многострочными заголовками (например: 20'DC (<24т брутто груза), (>24т брутто груза), 40'HC (<28т брутто груза))

    Возвращает список маршрутов с ценами:
    [
        {
            "origin": str,
            "destination": str,
            "prices": { normalized_header: int|None, ... },
            "raw_headers": { normalized_header: original_header_text, ... }
        }
    ]
    """

    def normalize_header(text: str) -> str:
        if not text:
            return ""
        t = str(text)
        t = re.sub(r"\s+", " ", t).strip()
        # нормализация контейнеров и веса
        t = t.replace("'", "'")
        t = t.replace('"', '"').replace('"', '"')
        lower = t.lower()
        # ключи
        is_20dc = "20'dc" in lower or "20dc" in lower
        is_40hc = "40'hc" in lower or "40hc" in lower
        lt_24 = "<24" in lower
        gt_24 = ">24" in lower
        lt_28 = "<28" in lower
        if is_20dc and lt_24:
            return "20DC_lt24t"
        if is_20dc and gt_24:
            return "20DC_gt24t"
        if is_40hc and lt_28:
            return "40HC_lt28t"
        # fallback по явным названиям
        if is_20dc:
            return "20DC"
        if is_40hc:
            return "40HC"
        return ''
        #return re.sub(r"[^A-Za-zА-Яа-я0-9_]+", "_", lower).strip("_") or "col"

    def normalize_price(val):
        if pd.isna(val):
            return None
        s = str(val)
        # вытащим числа
        digits = re.sub(r"[^0-9]", "", s)
        if not digits:
            return None
        try:
            return int(digits)
        except Exception:
            return None

    results = []

    # находим строку базовых заголовков (содержит "Пункт отправления" и/или "Станция назначения")
    base_header_row = 0
    for ridx in range(min(20, len(df))):
        row_vals = df.iloc[ridx, :].astype(str).str.strip().tolist()
        joined = " ".join(row_vals).lower()
        if "пункт отправления" in joined or "станция назначения" in joined:
            base_header_row = ridx
            break
    if base_header_row is None:
        raise ValueError("Не удалось найти строку заголовков тарифной таблицы.")

    # соберём многострочные заголовки: возьмём базовую строку и 3 строки ниже/выше для конкатенации
    header_rows = list(range(max(0, base_header_row - 2), min(df.shape[0], base_header_row + 3)))
    headers_concat = []
    for c in range(df.shape[1]):
        parts = []
        for r in header_rows:
            val = df.iat[r, c]
            if pd.notna(val) and str(val).strip():
                parts.append(str(val).strip())
        headers_concat.append(" ".join(parts).strip())

    # определим начало данных
    data_start = base_header_row + 1

    # нормализуем заголовки и карту оригиналов
    normalized_keys = {}

    for c, h in enumerate(headers_concat):
        key = normalize_header(h)
        if key:
            normalized_keys[c] = key

    # ожидаем, что первые две колонки — origin/destination
    origin_col = 0
    destination_col = 1
    price_cols = [i for i in range(2, df.shape[1])]


    current_origin = None
    for ridx in range(data_start, df.shape[0]):
        row = df.iloc[ridx, :]
        # обновляем origin, если заполнен
        ov = row.iat[origin_col] if origin_col < len(row) else None
        if pd.notna(ov) and str(ov).strip():
            current_origin = str(ov).strip()
        # читаем destination
        dv = row.iat[destination_col] if destination_col < len(row) else None
        destination = str(dv).strip() if pd.notna(dv) and str(dv).strip() else None
        # соберём цены
        prices = {}
        any_price = False
        for c in price_cols:
            val = row.iat[c] if c < len(row) else None
            price = normalize_price(val)
            key = normalized_keys.get(c, None) or normalized_keys.get(c+1)
            if price is not None:
                prices[key] = price
                any_price = True
        # если есть хоть одна цена и задана destination — фиксируем запись
        if any_price and destination:
            results.append({
                "origin": current_origin.replace("\n",' '),
                "destination": destination.replace("\n",''),
                "prices": prices,
                #"raw_headers": {k: raw_by_key.get(k) for k in prices.keys()},
            })

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    return results


def parse_EuroSib():
    company = "EuroSib"
    tables, extra_info = get_tables_pdf(url="https://cont.eurosib.biz/files/shipping/sea%20line%20tariffs.pdf", path="download/sea_line_tariffs.pdf", company="EuroSib")
    shedule_json = get_shedule_EuroSib("https://cont.eurosib.biz/download-freight-shedule", "download/download-freight-shedule.xlsx")
    results_table_A1 = []
    rows_table_A1 = []
    rows_table_A2 = []
    rows_table_JD = []
    for table in tables[:2]:
        if not table.empty:
            rows_table_A1 += table.to_dict(orient="records")
    for table in tables[2:3]:
        if not table.empty:

            rows_table_A2 += table.to_dict(orient="records")
    for table in tables[3:7]:
        if not table.empty and len(table.to_dict(orient="records")) > 4:
            #print(table.to_dict(orient="records"))
            rows_table_JD += table.to_dict(orient="records")

    json_table_JD = parse_tariff_matrix_to_json(pd.DataFrame(rows_table_JD))
    pods = {"Владивосток": "Морской порт «Первомайский»", "Находка": "Терминал Астафьева", "Владивосток ВМРП": "Владивостокский морской рыбный порт"}
    pods_end = {"Морской порт «Первомайский»": "Владивосток", "Терминал Астафьева": "Находка", "Владивостокский морской рыбный порт": "Владивосток"}

    def get_ETD(port, transshipment):
        results = []
        for key, item in shedule_json.items():
            if port in key or transshipment in key:
                for sydno in item:
                    if sydno.get("ETD", None):
                        results.append(sydno)
        return results

    def get_data_table_A1_A2(rows_table, COC_SOC):
        results_table_A1 = []
        for row in rows_table:
            if "Порт отгрузки" == row[0] :
                continue
            n_none = 0
            n_rows = len(row.keys())
            for key, value in row.items():
                if value == None:
                    n_none += 1
            if (n_rows - n_none) <= 3:
                continue
            fo = "FOB" if "FOB" in row[0] else "FOT" if "FOT" in row[0] else ""
            pol_ports = row[0].replace('\n',' ').replace("1", '').replace("FOT", '').replace("FOB", '').strip().split(" / ")
            transshipment = row[1] or row[2]
            dc_20 = row[2] if row[2] and ("$" in row[2] or "По запросу" in row[2]) else row[3]
            if len(row)>=5:
                hc_40 = row[4] if row[4] and ("$" in row[4] or "По запросу" in row[4]) else row[3] if "$" in row[3] or "По запросу" in row[3] else row[5]
            else:
                hc_40 = row[3] if row[3] and ("$" in row[3] or "По запросу" in row[3]) else ''
            currency = "$"
            costs = [dc_20.replace(currency, '').replace(" ", '').strip(), hc_40.replace(currency, '').replace(" ", '').strip()]
            for pol_port_i in pol_ports:
                for i in range(2):
                    if costs[i] == "Позапросу" or fo == "FOT":
                        continue
                    for pod_port, pod in pods_end.items():
                        pol_port_i = pol_port_i.replace("/", '').strip()
                        pol_port = port_dict.get(pol_port_i, pol_port_i)

                        transshipment = port_dict.get(transshipment, transshipment)
                        shedules = get_ETD(pol_port, transshipment)
                        for shedule in shedules:
                            if costs[i] == "-":
                                 continue
                            # parent_start: город порта отправления
                            pol_city = get_country(pol_port)
                            results_table_A1.append(
                                TariffSegment(
                                    transport_type="sea",
                                    start_point=f"{pol_port}, {pol_city}",
                                    end_point=f"{pod_port}, {get_country(pod)}",
                                    container_type="20DC" if i == 0 else "40HC",
                                    weight_limit=container_size_dict.get("20DC")
                                    if i == 0
                                    else container_size_dict.get("40HC"),
                                    cost=costs[i],
                                    currency=currency_dict.get(currency, "$"),
                                    departure_dates={},
                                    company="EuroSib",
                                    customs=None,
                                    departures={
                                        "vessel": shedule["vessel"],
                                        "voyage_no": shedule["voyage_no"],
                                        "CUTOFF": shedule["CUTOFF"],
                                        "ETA": shedule["ETA"],
                                        "ETD": shedule["ETD"],
                                        "terminal": shedule["terminal"],
                                    },
                                    container_ownership=COC_SOC,
                                    port_service_term="FILO",
                                    end_location_type="port",
                                    start_location_type="port",
                                    parent_start_location=pol_port,
                                    parent_start_location_type="city",
                                    parent_end_location=pod,
                                    parent_end_location_type=None
                                    if pods_end.get(pod_port, None) is None
                                    else "city",
                                    stopovers_location=transshipment if transshipment != "direct" else None,
                                    stopovers_location_type="port" if transshipment != "direct" else None,
                                    stopovers_location_country=get_country(transshipment) if transshipment != "direct" else None,
                                    parent_stopovers_location=transshipment if transshipment != "direct" else None,
                                    parent_stopovers_location_type="city" if transshipment != "direct" else None,
                                    sequence=0,
                                    conditions=fo,
                                ).to_dict()
                            )
        return results_table_A1

    def get_data_table_JD(rows_table):
        results_table = []
        for item in rows_table:
            pol_ports = item.get("origin").split("//")
            destination = item.get("destination")
            if "Станция отправления" == destination:
                continue
            if ":" in destination:
                destination = item.get("destination").split(":")
            pod_ports = destination[1].split("/")
            pod_port = destination[0].strip()
            pol_port = ''
            for port in pol_ports:
                pol_port = ''
                for key,value in pods.items():

                    if value == port.strip():
                        pol_port = key
                        break
                prices = item.get("prices")
                if pol_port == '':
                    continue
                for container_type, cost in prices.items():
                    if not container_type:
                        continue
                    for pod in pod_ports:
                        results_table.append(
                            TariffSegment(
                                transport_type="rail",
                                start_point=f"{pods[pol_port]}, {get_country(pol_port)}",
                                end_point=f"{pod.replace('*','').strip()}, {get_country(pod_port)}",
                                container_type="20DC" if "20DC" in container_type else "40HC",
                                weight_limit=container_size_dict.get("20DC")
                                if "lt24t" in container_type
                                else "28"
                                if "gt24t" in container_type
                                else container_size_dict.get("40HC"),
                                cost=cost,
                                currency=currency_dict.get("руб"),
                                departure_dates="",
                                company="EuroSib",
                                customs=None,
                                conditions=f"Станции назначения: {pod.replace('*','').strip()}",
                                end_location_type="rail_station",
                                departures=None,
                                start_location_type="port",
                                parent_start_location=pol_port if "Находка" == pol_port else "Владивосток",
                                parent_start_location_type="city",
                                parent_end_location=pod_port,
                                parent_end_location_type="city",
                                container_ownership="ANY",
                                port_service_term="FILO",
                                stopovers_location=None,
                                stopovers_location_type=None,
                                stopovers_location_country=None,
                                sequence=0,
                            ).to_dict()
                        )

        return results_table

    rows_A1 = pd.DataFrame(get_data_table_A1_A2(rows_table_A1, "COC"))
    rows_A2 = pd.DataFrame(get_data_table_A1_A2(rows_table_A2, "SOC"))
    rows_JD = pd.DataFrame(get_data_table_JD(json_table_JD))
    rows_all = pd.concat([rows_A1, rows_A2,rows_JD], ignore_index=True)
    return rows_all

from .utils import to_segments as _to_segments

_parse_EuroSib_impl = parse_EuroSib

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_EuroSib_impl(*args, **kwargs))
