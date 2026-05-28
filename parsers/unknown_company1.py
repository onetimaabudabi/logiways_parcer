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


def parse_UnknownCompany1(file_path: str):
    df = pd.read_excel(file_path, header=None, sheet_name = "Неизвестная компания_1")
    text = " ".join(str(x) for x in df.values.flatten() if str(x).strip())
    text = re.sub(r"\s+", " ", text).strip()

    results = []

    # Извлекаем маршрут
    route_match = re.search(r"Маршрут[:：]?\s*(.+?)Расчет", text, re.IGNORECASE)
    route = route_match.group(1).strip() if route_match else ""
    # Пример: "станция Чанша -- граница Маньчжурии -- Белый Раст"
    parts = re.split(r"--|–|-", route)
    pol_route = parts[0].strip() if parts else "Китай"
    pod_route = parts[-1].strip() if len(parts) > 1 else "Россия"

    # Извлекаем все POL и ставки
    pol_rates = re.findall(r"POL[:：]?\s*([^\d]+)\s*([\d]+)", text)

    # Доп. инфа
    extra = ""
    if "Разрешена" in text:
        extra = re.search(r"(Разрешена[^.]+[.]?)", text)
        extra = extra.group(1) if extra else ""

    # Контейнер
    container_type = "40HQ"
    currency = currency_dict.get("$", "USD")

    for pol_raw, cost in pol_rates:
        pol_ = pol_raw.strip().strip(":：") + "/"
        cost = cost.strip()
        for pol in pol_.split("/"):
            if pol:       
                pol_port = port_dict.get(pol.title(), pol.title())
                pod_port = region_dict.get(pod_route.title(), pod_route.title())

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
                    "currency": currency,
                    "departure_dates": {},
                    "company": "UnknownCompany1",
                    "conditions": (
                        f"Маршрут: {route}\n"
                        f"Порт отправления: {pol_port}\n"
                        f"Порт назначения: {pod_port}\n"
                        f"{extra}"
                        "FOB, разрешена перевозка батарей"
                    ),
                    "start_location_type": "port",
                    "end_location_type": "rail_station"
                }
                results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_UnknownCompany1
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_UnknownCompany1_impl = parse_UnknownCompany1

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_UnknownCompany1_impl(*args, **kwargs))

