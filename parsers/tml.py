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


def parse_TML(filepath: str):
	# Считываем весь Excel в DataFrame без заголовков
	company="TML"
	df = pd.read_excel(filepath, header=None, sheet_name=company)
	
	result = []
	data = df.iloc[0,0].split('===')
	sea_rail = data[0].split("\n")
	direct_railway_lines = data[1].split("\n")
	for line in range(0,len(sea_rail)-1,3):
		if "FOB" in sea_rail[line]:
			d = sea_rail[line].split(" - ")
			pol_list = d[0].replace("FOB",'').replace("/"," /").strip().split(" / ")
			pod_cost = d[1].split(" = ")
			pod_container_type = pod_cost[0].split()
			pod = pod_container_type[1]
			container_type = pod_container_type[2]
			cost = pod_cost[1]
			drop_off = sea_rail[line+1].split(" -")
			pol_jd = drop_off[0].replace("CY ", "").strip().title()
			pod_jd = drop_off[1].split(" = ")[0].replace("FOR",'').strip().title()
			cost_jd = float(drop_off[1].split(" = ")[1].replace(" ",'').strip())
			pod_jd = region_dict.get(pod_jd, pod_jd)
			pol_jd = port_dict.get(pol_jd, pol_jd)
			for pol in pol_list:
				pol_port = port_dict.get(pol.strip().title(), pol.strip().title())
				pod_port = port_dict.get(pod.strip().title(), pod.strip().title())
				
				result.append({
					"transport_type": "sea",
					"start_point": f"{pol_port}, {get_country(pol_port)}",
					"end_point": f"{pod_port}, {get_country(pod_port)}",
					"final_destination": f"{pod_jd}, {get_country(pod_port)}",
					"container_type": container_type.strip(),
					"weight_limit": container_size_dict.get(container_type.strip()),
					"cost": cost.split()[0].strip(),
					"currency": currency_dict.get("$") if "USD" in cost else currency_dict.get("руб"),
					"departure_dates": "",
					"company": company,
					"conditions": f"FOB, порт: {pod.strip().title()}"
				})
			result.append({
					"transport_type": "rail",
					"start_point": f"{pol_jd}, {get_country(pol_jd)}",
					"end_point": f"{pod_jd}, {get_country(pod_jd)}",
					"final_destination": f"{pod_jd}, {get_country(pod_port)}",
					"container_type": container_type.strip(),
					"weight_limit": container_size_dict.get(container_type.strip()),
					"cost": cost_jd,
					"currency": currency_dict.get("руб"),
					"departure_dates": "",
					"company": company,
					"conditions": ""
				})
	for line in direct_railway_lines:
		if "FOB" in line:
			d = line.replace("FOB", "").strip().split(":")
			pol_pod_list = d[0].split("-")
			cost_container_type = d[1].split("/")
			pol_jd = port_dict.get(pol_pod_list[0].strip().title(), pol_pod_list[0].strip().title())
			pod_jd = region_dict.get(pol_pod_list[-1].strip().title(), pol_pod_list[-1].strip().title())
			container_type = cost_container_type[1].strip()
			cost_jd = cost_container_type[0].replace("USD",'').replace("RUB",'')
			result.append({
					"transport_type": "rail",
					"start_point": f"{pol_jd}, {get_country(pol_jd)}",
					"end_point": f"{pod_jd}, {get_country(pod_jd)}",
					"final_destination": f"All, {get_country(pod_port)}",
					"container_type": container_type,
					"weight_limit": container_size_dict.get(container_type),
					"cost": cost_jd,
					"currency": currency_dict.get("$") if "USD" in cost_container_type[0] else currency_dict.get("руб"),
					"departure_dates": "",
					"company": company,
					"conditions": d[0]
				})


	#print(result)
	return pd.DataFrame(result)

# _segments_wrapper_for_parse_TML
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_TML_impl = parse_TML

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_TML_impl(*args, **kwargs))

