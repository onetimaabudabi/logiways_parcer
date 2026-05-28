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


def parse_Shenzhen_Wotu_International_Logistics(filepath: str):
    """
    Парсит текст с предложениями по перевозке грузов и возвращает список словарей с полями:
    - origin: точка отправления
    - destination: точка прибытия
    - price: цена
    - currency: валюта (обычно USD)
    - terms: условия (например, 40'HQ COC)
    - route: маршрут (через какие станции/границы)
    - timestamp: дата и время, если указаны
    """
    company = "Shenzhen Wotu International Logistics"
    tables, text_blocks = get_tables_pdf(None, filepath, company)
    text_all = "\n".join(text_blocks)
    text = text_all.replace("\r", "\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    data_rail = []

    fob_pattern = re.compile(
        r'^FOB\s+(.+?)\s*-\s*(.+?)\s*-\s*([\w\s]+?)\s+([40\'[A-Z]+\s+(?:COC|SOC))',
        re.IGNORECASE
    )

    # Шаблон для цены: ищем USD<число> или USD<пробел><число>
    price_pattern = re.compile(r'USD\s*(\d+)', re.IGNORECASE)

    current_route = None
    current_destination = None
    current_terms = None
    timestamp = None
    border_part = None
    currency = ""
    container_type = "40HQ"
    for line in lines:
        # Ищем маршрут FOB ... – ... – ...
        route_match = fob_pattern.search(line)
        if route_match:
            origin_part = route_match.group(1).strip()
            middle_part = route_match.group(2).strip()
            destination_part = route_match.group(3).strip()
            border_part = middle_part
            current_route = f"{origin_part} – {middle_part} – {destination_part}"
            current_destination = destination_part
            current_terms = None  # сбрасываем, т.к. может быть новый terms
            continue

        # Ищем цены
        price_match = price_pattern.search(line)
        if price_match:
            
            if "USD" in price_match.group(0):
                currency = "USD"
            else:
                currency = "руб"
            price_str = price_match.group(1)
            
            city_part = re.sub(r'[A-Z]{3}\d+|\d+', '', line).strip()
            city_part = re.sub(r'-\s*', '', city_part).strip() + "/"
            for pol_ in city_part.split("/"):
                if pol_ and price_str:
                    pol = pol_.title()
                    pod = current_destination.title()
                    pol_port = port_dict.get(pol, pol)
                    pod_port = region_dict.get(pod, pod)
                    border_point = border_dict.get(border_part, border_part)
                    start_country = get_country(pol_port)
                    end_country = get_country(pod_port)
                    data_rail.append(TariffSegment(
                        transport_type= "rail",
                        start_point= f"{pol_port}, {start_country}",
                        end_point= f"{pod_port}, {end_country}",
                        final_destination= f"All, {end_country}",
                        container_type= container_type,
                        weight_limit= container_size_dict.get(container_type, ""),
                        cost= price_str,
                        currency= currency_dict.get(currency, "USD"),
                        company= company,
                        end_location_type="city",
                        start_location_type="city",
                        container_ownership= "COC",
                        border_point= border_point
                    ))
    return pd.DataFrame(data_rail)

# _segments_wrapper_for_parse_Shenzhen_Wotu_International_Logistics
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Shenzhen_Wotu_International_Logistics_impl = parse_Shenzhen_Wotu_International_Logistics

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Shenzhen_Wotu_International_Logistics_impl(*args, **kwargs))

