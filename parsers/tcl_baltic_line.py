"""Auto-extracted from main.py.

Note: This module intentionally keeps the original parsing logic.
Output coercion to the canonical schema can be done via TariffSegment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from shared import (
    container_size_dict,
    currency_dict,
    get_country,
    get_country_for_port,
    port_dict,
    region_dict,
)


def parse_TCL_Baltic_Line(filepath: str, company_name: str = "TLC Baltic Line"):
    results = []

    # Russian port names mapping
    port_to_russian = {
        "Shanghai": "Шанхай",
        "Ningbo": "Нинбо",
        "Tianjin": "Тяньцзинь",
        "Xingang": "Синьган",
        "Dalian": "Далянь",
        "Qingdao": "Циндао",
        "Xiamen": "Сямынь",
        "Nansha": "Наньша",
        "Huangpu": "Хуанпу",
        "Fuzhou": "Фучжоу",
        "Shekou": "Шэкоу",
        "Busan": "Пусан",
        "Jakarta": "Джакарта",
        "Surabaya": "Сурабая",
        "Port Klang": "Порт-Кланг",
        "PortKlang": "Порт-Кланг",
        "Ho Chi Minh": "Хошимин",
        "Haiphong": "Хайфон",
        "Laem Chabang": "Лаем-Чабанг",
        "Bangkok": "Бангкок",
        "Kaohsiung": "Гаосюн",
        "Keelung": "Цзилун",
        "Taichung": "Тайчжун",
        "Colombo": "Коломбо",
        "Chittagong": "Читтагонг",
        "Chennai": "Ченнаи",
        "Cochin": "Кочин",
        "Nhava Sheva": "Нава-Шева",
        "Mundra": "Мундра",
        "Santos": "Сантус",
        "Rio Grande": "Рио-Гранде",
        "Vitoria": "Витория",
        "Buenos Aires": "Буэнос-Айрес",
        "Argentina": "Аргентина",
        "Rotterdam": "Роттердам",
    }

    # Override incorrect port_dict entries for this parser
    port_dict_override = {
        "Xiamen": "Сямынь",
        "Shekou": "Шэкоу", 
        "Haiphong": "Хайфон",
        "Keelung": "Цзилун",
        "Tianjin": "Тяньцзинь",
        "Laem Chabang": "Лаем-Чабанг",
    }

    def get_russian_port(english_name):
        # Remove parentheses like (Xingang) and handle "Port, Country" format
        clean_name = re.sub(r'\([^)]*\)', '', english_name).strip()
        # If contains comma, extract port part
        if "," in clean_name:
            clean_name = clean_name.split(",")[0].strip()
        
        # Check override first for specific ports
        if clean_name in port_dict_override:
            return port_dict_override[clean_name]
        
        # Check port_dict
        if clean_name in port_dict:
            return port_dict[clean_name]
        
        # Check our custom mapping
        return port_to_russian.get(clean_name, clean_name)

    # Extract dates from filename since PDF has encoding issues
    filename = Path(filepath).name
    date_match = re.search(r'(\d{1,2})[-–](\d{1,2})', filename)
    year_match = re.search(r'20\d{2}', filename)
    
    month = '02'  # Default - February
    
    valid_from = None
    valid_to = None
    if date_match and year_match:
        day1 = date_match.group(1).zfill(2)
        day2 = date_match.group(2).zfill(2)
        year = year_match.group(0)
        valid_from = f"{year}-{month}-{day1}"
        valid_to = f"{year}-{month}-{day2}"

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # Skip non-tariff pages
            if "НАЗЕМНАЯ" in text.upper() or "ЖЕЛЕЗНОДОРОЖН" in text.upper():
                continue
            if "УСЛОВИЯ" in text.upper() or "АКТИВЫ" in text.upper():
                continue

            # Combine multi-line entries - better handling
            lines = text.split('\n')
            combined_lines = []
            buffer = ""
            
            for line in lines:
                line = line.strip()
                # Skip header/footer lines
                if not line or 'КОММЕРЧЕСКОЕ' in line or 'ПРИМЕЧАНИЕ' in line:
                    continue
                if 'ПОЛИ' in line or 'POD' in line or 'Транзитное' in line:
                    continue
                if 'import@t-lc.ru' in line or 'www.t-lc.ru' in line:
                    continue
                if 'Дополнительные' in line or '*' in line:
                    continue
                    
                # If line starts with FI, start new entry
                if line.startswith('FI '):
                    if buffer:
                        combined_lines.append(buffer)
                    buffer = line
                # If line starts with / (like /Qingdao), it's continuation of POL list
                elif line.startswith('/'):
                    if buffer:
                        buffer = buffer + " " + line.lstrip('/').strip()
                # If line is just LO xxx, append to previous
                elif line.startswith('LO ') or line.startswith('Port'):
                    if buffer:
                        buffer = buffer + " " + line
                # If line starts with digits (cost), it's a continuation
                elif buffer and line and line[0].isdigit():
                    buffer = buffer + " " + line
                # Otherwise if we have a buffer, save it and start new
                elif buffer:
                    combined_lines.append(buffer)
                    buffer = line
            
            if buffer:
                combined_lines.append(buffer)

            for line in combined_lines:
                # Check for Rotterdam transshipment
                has_rotterdam = 'Роттердам' in line or 'Rotterdam' in line

                # Initialize variables
                pol_raw = ""
                pod_raw = "Saint-Petersburg"
                cost_20 = ""
                cost_40 = ""

                # Match various patterns:
                # 1. FI Shanghai/ Ningbo LO Saint-Petersburg 3 300 USD 4 500USD 45-55дней
                # 2. FI Tianjin(Xingang) / Dalian 3 300USD 4 500USD /Qingdao  
                # 3. FI Bangkok 3 550 USD 4 700USD 50-60дней
                # 4. FI Santos, Brazil LO Saint-Petersburg 3 750 USD 3700USD
                
                # Try pattern with LO first
                match = re.search(
                    r'FI\s+([A-Za-z,/\-()\s]+?)\s+LO\s+([A-Za-z,/\-]+(?:\s+[A-Za-z,/\-]+)?)\s+([\d\s]+)\s*USD?\s+([\d\s]+)\s*USD?',
                    line
                )
                
                if match:
                    pol_raw = match.group(1).strip() if match.group(1) else ""
                    pod_raw = match.group(2).strip() if match.group(2) else "Saint-Petersburg"
                    cost_20 = re.sub(r'[^\d]', '', match.group(3)) if match.group(3) else ""
                    cost_40 = re.sub(r'[^\d]', '', match.group(4)) if match.group(4) else ""
                else:
                    # Try pattern without LO (like Bangkok)
                    match2 = re.search(
                        r'FI\s+([A-Za-z,/\-()\s]+?)\s+([\d\s]+)\s*USD?\s+([\d\s]+)\s*USD?',
                        line
                    )
                    if match2:
                        pol_raw = match2.group(1).strip()
                        cost_20 = re.sub(r'[^\d]', '', match2.group(2))
                        cost_40 = re.sub(r'[^\d]', '', match2.group(3))
                        pod_raw = "Saint-Petersburg"
                    else:
                        continue

                if not pol_raw or not cost_20:
                    continue

                # Handle case where POL ports appear after costs (like "FI Tianjin(Xingang) / Dalian 3 300USD 4 500USD Qingdao")
                # Extract any remaining port names after the costs
                post_cost_match = re.search(r'USD\s+([A-Za-z,/\-()\s]+?)$', line)
                if post_cost_match:
                    post_cost_text = post_cost_match.group(1).strip()
                    # Remove transit days and extract port names
                    post_cost_text = re.sub(r'\d+[-–]?\d*\s*дней?', '', post_cost_text).strip()
                    if post_cost_text:
                        # Split by / and clean
                        extra_ports = [p.strip() for p in post_cost_text.split('/') if p.strip()]
                        for ep in extra_ports:
                            # Only add if it looks like a port name (not a number)
                            if ep and not ep.replace(' ', '').isdigit():
                                if pol_raw:
                                    pol_raw = pol_raw + " / " + ep
                                else:
                                    pol_raw = ep

                # Extract transit days
                transit_match = re.search(r'(\d+)[-–]?(\d+)?\s*дней?', line)
                transit_days = transit_match.group(0) if transit_match else ""

                pod_russian = "Санкт-Петербург"
                end_country = "Россия"

                # Split POL by "/" for multiple ports
                pol_list = [p.strip() for p in pol_raw.split('/') if p.strip()]

                for pol in pol_list:
                    pol_russian = get_russian_port(pol)
                    start_country = get_country_for_port(pol_russian)
                    pol_parent = start_country if start_country else pol_russian

                    duration_max = None
                    duration_min = None
                    if transit_days:
                        days_nums = re.findall(r'\d+', transit_days)
                        if len(days_nums) >= 2:
                            duration_max = int(days_nums[1])
                            duration_min = int(days_nums[0])
                        elif len(days_nums) == 1:
                            duration_max = int(days_nums[0])

                    for container_type, cost in [("20DC", cost_20), ("40HC", cost_40)]:
                        if not cost:
                            continue

                        conditions_parts = []
                        if transit_days:
                            conditions_parts.append(f"Transit: {transit_days}")
                        if has_rotterdam:
                            conditions_parts.append("Transshipment: Rotterdam")

                        record = {
                            "transport_type": "sea",
                            "start_point": f"{pol_russian}, {start_country}",
                            "end_point": f"{pod_russian}, {end_country}",
                            "final_destination": f"All, {end_country}",
                            "container_type": container_type,
                            "weight_limit": container_size_dict.get(container_type, ""),
                            "cost": cost,
                            "currency": "USD",
                            "departure_dates": {},
                            "company": company_name,
                            "customs": None,
                            "conditions": " | ".join(conditions_parts) if conditions_parts else None,
                            "duration_max_days": duration_max,
                            "duration_min_days": duration_min,
                            "departures": None,
                            "port_service_term": "FIFO",
                            "container_ownership": "COC",
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "border_location": "Роттердам" if has_rotterdam else None,
                            "border_location_type": "port" if has_rotterdam else None,
                            "start_location_type": "port",
                            "end_location_type": "port",
                            "parent_start_location": pol_russian,
                            "parent_start_location_type": "city",
                            "parent_end_location": pod_russian,
                            "parent_end_location_type": "city",
                        }
                        results.append(record)

    return results


def get_tables_pdf_TCL_Baltic_Line(url: str, path: str, company: str):
    pdf_path = Path(path)
    tables_data = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if table:
                    tables_data.append(table)
    return tables_data


# _segments_wrapper_for_parse_TCL_Baltic_Line
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_TCL_Baltic_Line_impl = parse_TCL_Baltic_Line


def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_TCL_Baltic_Line_impl(*args, **kwargs))
