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


def parse_LCL(file_path: str):
	"""
	Robust LCL parser v2.
	- Объединяет все ячейки строки в одну строку.
	- Пробует несколько regex-шаблонов и fallback-стратегий.
	- Пишет debug CSV с исходной строкой и извлечёнными полями.
	Возвращает pd.DataFrame со стандартными полями.
	"""
	df_raw = pd.read_excel(file_path, header=None, dtype=str, sheet_name = "LCL").fillna("")
	results = []
	debug_rows = []

	# helper funcs
	def norm_amount(s):
		if not s:
			return ""
		s = str(s)
		s = s.replace("\u00A0", "").replace(" ", "")
		m = re.search(r"(\d+(?:[.,]\d+)?)", s)
		if not m:
			return ""
		return m.group(1).replace(",", ".")

	def norm_currency(s):
		if not s:
			return ""
		s = str(s).upper()
		if "$" in s or "USD" in s or "US$" in s:
			return "USD"
		if "РБ" in s or "RUB" in s or "РУБ" in s:
			return "RUB"
		if "€" in s or "EUR" in s:
			return "EUR"
		return ""

	# Patterns: several attempts with decreasing strictness
	patterns = [
		# full pattern: FOB start to end R/F: USD 4400 /40HQ
		re.compile(
			r"""^\s*FOB\s+
				(?P<start>.+?)\s+to\s+
				(?P<end>.+?)\s+
				(?:R/?F[:\s]*)?
				(?:(?P<cur>USD|US\$|\$|EUR|€|RUB|руб)\s*)?
				(?P<amount>[\d\s,\.]+)?
				(?:\s*(?:/|per)?\s*(?P<cont>40HQ|40HC|20GP|20DC|40FT|40'))?
				\s*$""",
			flags=re.I | re.X,
		),
		# simpler: FOB start to end ... USD 4400
		re.compile(r"^\s*FOB\s+(?P<start>.+?)\s+to\s+(?P<end>.+?)\b.*?(?P<cur>USD|\$|EUR|€|RUB|руб)?\s*(?P<amount>\d{3,6}(?:[.,]\d+)?)", flags=re.I),
		# fallback: start after FOB, everything before R/F or price is route
		re.compile(r"^\s*FOB\s+(?P<route>.+?)\s+(?:R/?F[:\s]*)?(?P<cur>USD|\$|EUR|€|RUB|руб)?\s*(?P<amount>\d{3,6}(?:[.,]\d+)?)", flags=re.I),
	]

	for idx, row in df_raw.iterrows():
		# join cells into single line (preserve order). filter empty cells.
		parts = [str(x).strip() for x in row.tolist() if str(x).strip() != ""]
		if not parts:
			continue
		line = " ".join(parts)
		line = re.sub(r"\s+", " ", line).strip()

		# Some rows might be header-like or unrelated; only process lines that contain "FOB" or "R/F"
		if not re.search(r"\bFOB\b", line, flags=re.I):
			# still keep debug row for visibility
			debug_rows.append({"idx": idx, "line": line, "matched": False, "reason": "no FOB"})
			continue

		start_point = ""
		end_point = ""
		amount = ""
		currency = ""
		container = ""
		used_pattern = None

		# Try patterns in order
		for p in patterns:
			m = p.search(line)
			if not m:
				continue
			used_pattern = p
			gd = m.groupdict()
			# Map possible groups
			if gd.get("start"):
				start_point = gd.get("start", "") or ""
			if gd.get("end"):
				end_point = gd.get("end", "") or ""
			# route style: may contain "X/Y to Z"
			if not start_point and gd.get("route"):
				# try split route 'A to B' inside route
				route = gd.get("route", "")
				m2 = re.search(r"(.+?)\s+to\s+(.+)", route, flags=re.I)
				if m2:
					start_point = m2.group(1).strip()
					end_point = m2.group(2).strip()
				else:
					# maybe 'Shanghai/Suzhou to Selyatino' already in route - try splitting by 'to'
					parts_route = route.split(" to ")
					if len(parts_route) >= 2:
						start_point = parts_route[0].strip()
						end_point = parts_route[1].strip()
					else:
						start_point = route.strip()

			# amount/currency/container
			amount_raw = gd.get("amount") or ""
			if amount_raw:
				amount = norm_amount(amount_raw)
			cur_raw = gd.get("cur") or ""
			if cur_raw:
				currency = norm_currency(cur_raw)
			cont_raw = gd.get("cont") or ""
			if cont_raw:
				container = cont_raw.upper().replace("'", "").replace("FT", "HQ")

			# break at first successful
			if start_point or amount:
				break

		# Additional heuristics if not enough extracted:
		if not end_point:
			# try to find " to <END> R/F" positions
			m_to = re.search(r"\bto\s+([A-Za-zА-Яа-я0-9/\-\s()]+?)(?:\s+R/?F\b|\s+\$|\s+\d{3})", line, flags=re.I)
			if m_to:
				end_point = m_to.group(1).strip()

			if not start_point:
				m_start = re.search(r"FOB\s+(.+?)\s+(?:to\b|R/?F\b|\$|\d{3})", line, flags=re.I)
				if m_start:
					start_point = m_start.group(1).strip()

		if not amount:
			# search for price after 'R/F' or any number
			m_price = re.search(r"(?:R/?F[:\s]*)?(?:USD|US\$|\$|EUR|€|RUB|руб)?\s*([0-9]{3,6}(?:[ ,\.][0-9]{3})*(?:[.,][0-9]+)?)", line, flags=re.I)
			if m_price:
				amount = norm_amount(m_price.group(1))
				# try find currency near number
				left_context = line[:m_price.start()+10]
				m_cur = re.search(r"(USD|US\$|\$|EUR|€|RUB|руб)", left_context, flags=re.I)
				if not m_cur:
					m_cur = re.search(r"(USD|US\$|\$|EUR|€|RUB|руб)", line, flags=re.I)
				if m_cur:
					currency = norm_currency(m_cur.group(1))

		if not container:
			m_cont = re.search(r"(40HQ|40HC|20GP|20DC|40FT|40')", line, flags=re.I)
			if m_cont:
				container = m_cont.group(1).upper().replace("'", "").replace("FT", "HQ")

		# defaults
		if not container:
			container = "40HQ"
			if not currency:
				# default to USD if line contains $ or USD, else blank
				if re.search(r"\$|USD", line, flags=re.I):
					currency = "USD"
				else:
					currency = ""

		# Clean start/end: remove leading "FOB" remnants
		start_points = re.sub(r"^FOB\s*", "", start_point, flags=re.I).strip()+"/"
		# strip trailing phrases like 'R/F' or rates
		end_point = re.sub(r"\s+R/?F[:\s\S]*$", "", end_point, flags=re.I).strip()
		for start_point in start_points.split("/"):
			if not start_point:
				continue
			pol_port = port_dict.get(start_point.strip().title(), start_point.strip().title())
			pod_port = region_dict.get(end_point.strip().title(), end_point.strip().title())
					
			record = {
				"transport_type": "rail",
				"start_point": f"{pol_port}, {get_country(pol_port)}",
				"end_point": f"{pod_port}, {get_country(pod_port)}",
				"final_destination": f"All, {get_country(pod_port)}",
				"container_type": container,
				"weight_limit": container_size_dict.get(container, ""),
				"cost": amount,
				"currency": currency,
				"departure_dates": {},
				"company": "LCL",
				"conditions": f"R/F: {container}\nFOB"
			}
			results.append(record)

	return pd.DataFrame(results)

# _segments_wrapper_for_parse_LCL
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_LCL_impl = parse_LCL

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_LCL_impl(*args, **kwargs))

