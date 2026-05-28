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


def parse_Hesion_Global_Logistics(file_path: str):
    """
    Парсер тарифов Hesion Global Logistics.
    Возвращает pd.DataFrame в унифицированном формате для main.py.
    """
    df = pd.read_excel(file_path, sheet_name = "Hesion-globallogistics")
    df = df.fillna("")

    results = []

    current_carrier = ""
    current_pod = ""

    for _, row in df.iterrows():
        carrier = str(row.get("CARRIER", "")).strip()
        pol = str(row.get("POL", "")).strip()
        pod = str(row.get("POD", "")).strip()
        rate_20 = str(row.get("20GP", "")).strip()
        rate_40 = str(row.get("40HQ", "")).strip()
        etd = str(row.get("ETD", "")).strip()
        remark = str(row.get("REMARK", "")).strip()
        route = str(row.get("Route", "")).strip()

        # Наследуем предыдущие значения, если пустые
        if carrier:
            current_carrier = carrier
        else:
            carrier = current_carrier

        if pod:
            current_pod = pod
        else:
            pod = current_pod

        # Определяем валюту
        currency = currency_dict.get("$", "USD")
        pod_list = pod.split()
        pod = pod

        # Базовые преобразования портов
        pol_port = port_dict.get(pol.title(), pol.title())
        pod_port = region_dict.get(pod, pod.title())

        start_country = get_country(pol_port)
        end_country = get_country(pod_port)

        # Создаём записи по типам контейнеров
        for container_type, rate in [("20GP", rate_20), ("40HQ", rate_40)]:
            if not rate:
                continue
            # возможны значения вроде 4250/4550 — делим на 2 ставки
            rates = re.split(r"[ /]+", rate)
            for cost in rates:
                cost = re.sub(r"[^\d.]", "", cost)
                if not cost:
                    continue

                record = {
                    "transport_type": "sea",
                    "start_point": f"{pol_port}, {start_country}",
                    "end_point": f"{pod_port}, {end_country}",
                    "final_destination": f"All, {end_country}",
                    "container_type": container_type,
                    "weight_limit": container_size_dict.get(container_type, ""),
                    "cost": cost,
                    "currency": currency,
                    "departure_dates": {},
                    "company": "Hesion Global Logistics",
                    "conditions": (
                        f"Перевозчик: {carrier}\n"
                        f"Порт отправления: {pol_port}\n"
                        f"Порт назначения: {pod_port} {pod_list[1]}\n"
                        f"Комментарий: {remark}"
                        f"{route}".replace("，", ",").strip()
                    ),
                    "departures": {"ETD": etd} if etd else None,
                    "start_location_type": "port",
                    "end_location_type": "port",
                    "parent_end_location": get_city_port(pod_port),
                    "parent_end_location_type": "city" if get_city_port(pod_port) is not None else None
                }
                results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_Hesion_Global_Logistics
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Hesion_Global_Logistics_impl = parse_Hesion_Global_Logistics

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Hesion_Global_Logistics_impl(*args, **kwargs))

