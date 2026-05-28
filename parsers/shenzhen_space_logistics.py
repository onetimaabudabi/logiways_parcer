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


def parse_Shenzhen_Space_logistics(file_path: str):
	company = "Shenzhen Space logistics"
	raw = pd.read_excel(file_path, sheet_name = company, header=None)
	raw = raw.fillna("")

	# Находим строку, где начинается таблица (где встречается 'Pickup' или 'Border')
	header_row = None
	for i, row in raw.iterrows():
		joined = " ".join(str(v).lower() for v in row)
		if "pickup" in joined and ("border" in joined or "destination" in joined):
			header_row = i
			break

	if header_row is None:
		raise ValueError("Не удалось найти строку заголовков (header)")

	# Читаем файл снова, теперь с корректной строкой заголовков
	df = pd.read_excel(file_path, header=header_row, sheet_name = company,)
	df = df.fillna("")

	# Стандартизируем названия колонок
	df.columns = [str(c).strip().lower() for c in df.columns]

	# Попытка найти подходящие колонки по смыслу
	pickup_col = next((c for c in df.columns if "pickup" in c), None)
	border_col = next((c for c in df.columns if "border" in c), None)
	dest_col = next((c for c in df.columns if "dest" in c), None)
	rate_col = next((c for c in df.columns if "rate" in c or "foB" in c), None)
	tt_col = next((c for c in df.columns if "t/t" in c), None)
	etd_col = next((c for c in df.columns if "etd" in c), None)

	results = []
	current_border = ""
	current_destination = ""
	current_tt = ""
	current_etd = ""

	for _, row in df.iterrows():
		pickup = str(row.get(pickup_col, "")).strip()
		border = str(row.get(border_col, "")).strip()
		destination = str(row.get(dest_col, "")).strip()
		rate = str(row.get(rate_col, "")).strip()
		tt = str(row.get(tt_col, "")).strip()
		etd = str(row.get(etd_col, "")).strip()

		if border:
			current_border = border
		if destination:
			current_destination = destination
		if tt:
			current_tt = tt
		if etd:
			current_etd = etd

		if rate and pickup:
			cost = re.sub(r"[^\d.]", "", rate)
			pickups = (pickup.replace("area",'').strip()+"/").split("/")
			for pickup in pickups:
				if pickup:
					pol_port = port_dict.get(pickup.strip().title(), pickup.strip().title())
					pod_port = region_dict.get(current_destination.strip().title(), current_destination.strip().title())
					
					entry = {
						"transport_type": "rail",
						"start_point": f"{pol_port}, {get_country(pol_port)}",
						"end_point": f"{pod_port}, {get_country(pod_port)}",
						"final_destination": f"All, {get_country(pod_port)}",
						"container_type": "40HQ",
						"weight_limit": container_size_dict.get("40HQ"),
						"cost": cost,
						"currency": currency_dict.get("$"),
						"departure_dates": {},
						"company": "Shenzhen Space Logistics",
						"conditions": (
							f"Via: {current_border}"
                            f"Transit time: {current_tt}" if current_tt else ""
						),
						"departures": {"ETD": current_etd} if current_etd else None,
						"start_location_type": "port",
						"end_location_type": "rail_station"
					}
					results.append(entry)

	return pd.DataFrame(results)

# _segments_wrapper_for_parse_Shenzhen_Space_logistics
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_Shenzhen_Space_logistics_impl = parse_Shenzhen_Space_logistics

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_Shenzhen_Space_logistics_impl(*args, **kwargs))

