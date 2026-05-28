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


def parse_Amethyst(file_path: str):
    """
    Парсер таблицы Amethyst (BAF rates).
    Поддерживает маршруты с несколькими портами через '/'.
    Возвращает pd.DataFrame и печатает списки городов, стран и портов.
    """

    df = pd.read_excel(file_path, header=None, sheet_name="Аметист")
    df = df.fillna("")
    results = []

    for _, row in df.iterrows():
        line = " ".join(str(x).strip() for x in row if str(x).strip() != "")
        if not line or "<->" not in line:
            continue

        # Основной шаблон: (XX) Port(s) <-> (YY) Port(s) $ value
        match = re.search(
            r"\((\w{2})\)\s*([^<]+)<->\s*\((\w{2})\)\s*([^\$]+)\$?\s*([\d.,]+)",
            line
        )
        if not match:
            continue

        pol_cc, pol_ports_raw, pod_cc, pod_ports_raw, cost = match.groups()
        cost = re.sub(r"[^\d.]", "", cost)

        # Разбиваем множественные порты (через / или ,)
        pol_ports = re.split(r"[/,]", pol_ports_raw)
        pod_ports = re.split(r"[/,]", pod_ports_raw)

        for pol in pol_ports:
            pol = pol.strip()
            if not pol:
                continue
            for pod in pod_ports:
                pod = pod.strip()
                if not pod:
                    continue

                container_type = "20DC"
                currency = currency_dict.get("$", "USD")

                # Получаем переводы
                pol_port = port_dict.get(pol.title(), pol.title())
                pod_port = port_dict.get(pod.title(), pod.title())

                start_country = get_country(pol_port)
                end_country = get_country(pod_port)

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
                    "company": "Amethyst",
                    "conditions": "BAF per TEU"
                }
                results.append(record)

    return pd.DataFrame(results)

# _segments_wrapper_for_parse_Amethyst
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Amethyst_impl = parse_Amethyst

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Amethyst_impl(*args, **kwargs))

