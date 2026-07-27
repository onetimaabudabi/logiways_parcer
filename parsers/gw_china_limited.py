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


def parse_GW_CHINA_LIMITED(file_path: str):
	company="G&W CHINA LIMITED"
	df = pd.read_excel(file_path, sheet_name=company)
	df = df.fillna("")

	results = []

	current_departure = ""
	current_destination = ""
	current_etd = ""
	current_tt = ""

	for _, row in df.iterrows():
		dep = str(row["Departure Station"]).strip()
		dest = str(row["Destination"]).strip()
		pickup = str(row["Pick-up City"]).strip()
		rate = str(row["Rate/40HQ(USD)"]).strip()
		tt = str(row["T/T"]).strip()

        # если в строке указано новое направление — обновляем контекст
		if dep:
			current_departure = dep
			# вычленяем дату ETD, если указано
			etd_match = re.search(r"ETD[:\s]*(.+)", dep, re.I)
			if etd_match:
				current_etd = etd_match.group(1).strip()
				current_departure = re.sub(r"ETD[:\s]*.+", "", dep, flags=re.I).strip()
			else:
				current_etd = ""

		if dest:
			current_destination = dest

		if tt:
			current_tt = tt

        # если есть ставка и pick-up — добавляем запись
		if rate and pickup:
			cost = re.sub(r"[^\d.]", "", rate)
			pol_port = port_dict.get(pickup.strip().title(), pickup.strip().title())
			current_destination_list = current_destination.split("Via")
			pod_port = region_dict.get(current_destination_list[0].strip().title(), current_destination_list[0].strip().title())
			entry = {
				"transport_type": "rail",
				"start_point": f"{pol_port}, {get_country(pol_port)}",
				"end_point": f"{pod_port}, {get_country(pod_port)}",
				"container_type": "40HQ",
				"weight_limit": container_size_dict.get("40HQ"),
				"cost": cost,
				"currency": currency_dict.get("$"),
				"departure_dates": {current_etd} if current_etd else {},
				"company": "GW CHINA LIMITED",
				"conditions": f"Via {current_destination_list[1].strip()},\n Transit time: {current_tt}" if current_tt else "",
			}
			results.append(entry)

	return pd.DataFrame(results)

# _segments_wrapper_for_parse_GW_CHINA_LIMITED
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_GW_CHINA_LIMITED_impl = parse_GW_CHINA_LIMITED

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_GW_CHINA_LIMITED_impl(*args, **kwargs))

