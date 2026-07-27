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


def parse_Shenzhen_Eagleway_Supply_Chain_Management(file_path: str):
	company = "Shenzhen Eagleway Supply Chain Management"
	df = pd.read_excel(file_path, sheet_name = "Shenzhen Eagleway Supply Chain ")
	df = df.fillna("")

	results = []

	current_departure = ""
	current_border = ""
	current_unloading = ""
	current_etd = ""

	for _, row in df.iterrows():
		loading_city = str(row.get("Loading City", "")).strip()
		departure = str(row.get("Departure", "")).strip()
		border = str(row.get("CN BORDER", "")).strip()
		unloading = str(row.get("Unloading", "")).strip()
		rate = str(row.get("USD / 40HQ", "")).strip()
		etd = str(row.get("ETD", "")).strip()

		# Если в строке указано новое направление — обновляем контекст
		if departure:
			current_departure = departure
		if border:
			current_border = border
		if unloading:
			current_unloading = unloading
		if etd:
			current_etd = etd

		# Если есть ставка и город погрузки — добавляем запись
		if rate and loading_city:
			cost = re.sub(r"[^\d.]", "", rate)
			loading_city = loading_city.replace("FOB", '').strip()
			pol_port = port_dict.get(loading_city.strip().title(), loading_city.strip().title())
			current_unloading_list = current_unloading.split("(")
			pod_port = region_dict.get(current_unloading_list[0].strip().title(), current_unloading_list[0].strip().title())
			station = current_unloading_list[1].split("--")[0].strip()
			entry = {
					"transport_type": "rail",
					"start_point": f"{pol_port}, {get_country(pol_port)}",
					"end_point": f"{pod_port}, {get_country(pod_port)}",
					"container_type": "40HQ",
					"weight_limit": container_size_dict.get("40HQ"),
					"cost": cost,
					"currency": currency_dict.get("$"),
					"departure_dates": {},
					"company": "Shenzhen Eagleway Supply Chain Management",
					"conditions": (
						f"Via: {current_border}.\n"
						f"Станция назначения: {station}"
                        f"ETD: {current_etd}" if current_etd else ""
					),
					"departures": {"ETD": current_etd} if current_etd else None,
					"start_location_type": "port",
					"end_location_type": "rail_station"
				}
			results.append(entry)
	return pd.DataFrame(results)

# _segments_wrapper_for_parse_Shenzhen_Eagleway_Supply_Chain_Management
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Shenzhen_Eagleway_Supply_Chain_Management_impl = parse_Shenzhen_Eagleway_Supply_Chain_Management

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Shenzhen_Eagleway_Supply_Chain_Management_impl(*args, **kwargs))

