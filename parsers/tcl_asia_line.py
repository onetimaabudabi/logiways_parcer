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


def parse_TCL_Asia_Line(filepath: str, company_name: str = "TLC Baltic Line"):
    results = []

    # Russian port names mapping
    port_to_russian = {
        "Shanghai": "Шанхай",
        "Ningbo": "Нинбо",
        "Qingdao": "Циндао",
        "Tianjin": "Тяньцзинь",
        "Xingang": "Синьган",
        "Nansha": "Наньша",
        "Xiamen": "Сямынь",
        "Shekou": "Шэкоу",
        "Yantian": "Яньтянь",
        "Dalian": "Далянь",
        "Busan": "Пусан",
        "san LO": "Пусан",
        "Bangkok": "Бангкок",
        "Jakarta": "Джакарта",
        "Laem Chabang": "Лаем-Чабанг",
        "Port Klang": "Порт-Кланг",
        "Kaohsiung": "Гаосюн",
        "Keelung": "Цзилун",
        "Ho Chi Minh": "Хошимин",
        "Haiphong": "Хайфон",
        "Mundra": "Мундра",
        "Nhava Sheva": "Нава-Шева",
        "Chennai": "Ченнаи",
        "Cochin": "Кочин",
        "VMPP": "Владивостокский морской рыбный порт",
        "ВМРП": "Владивостокский морской рыбный порт",
    }

    def get_russian_port(english_name):
        cleaned_name = re.sub(r'\d+', '', english_name).strip()
        if cleaned_name in port_to_russian:
            return port_to_russian[cleaned_name]
        if english_name in port_dict:
            return port_dict[english_name]
        if cleaned_name in port_dict:
            return port_dict[cleaned_name]
        for k, v in port_dict.items():
            if v == english_name or english_name in k:
                return k
        return port_to_russian.get(english_name, port_to_russian.get(cleaned_name, english_name))

    # Extract dates from PDF text
    valid_from = None
    valid_to = None

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            date_match = re.search(r'Сроки действия тарифов\s+с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+([а-яА-ЯёЁ]+)\s*(\d{4})', text)
            if date_match:
                day1 = date_match.group(1).zfill(2)
                day2 = date_match.group(2).zfill(2)
                month_name = date_match.group(3)
                year = date_match.group(4)
                month_map = {
                    'январ': '01', 'феврал': '02', 'март': '03', 'апрел': '04',
                    'мая': '05', 'июн': '06', 'июл': '07', 'август': '08',
                    'сентябр': '09', 'октябр': '10', 'ноябр': '11', 'декабр': '12'
                }
                month = month_map.get(month_name.lower()[:6], '02')
                valid_from = f"{year}-{month}-{day1}"
                valid_to = f"{year}-{month}-{day2}"
                break

    # Parse SEA section (pages 1-2)
    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages[:2]):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith('КОММЕРЧЕСКОЕ') or line.startswith('МОРСКАЯ') or line.startswith('Просим'):
                    continue
                if 'ПОЛИ' in line or 'POD' in line:
                    continue
                if 'import@t-lc.ru' in line or 'www.t-lc.ru' in line:
                    continue

                match = re.search(
                    r'FI\s*([A-Za-z()\s/]+?)\s+LO\s+([^\s]+)\s+([\d\s]+)USD\s+([\d\s]+)USD',
                    line
                )
                if not match:
                    match = re.search(
                        r'([A-Za-z][A-Za-z\s/()]+?)\s+([А-Яа-яёЁ]+)\s+([\d\s]+)\s*USD?\s+([\d\s]+)\s*USD?',
                        line
                    )

                if not match:
                    continue

                pol_raw = match.group(1).strip() if match.group(1) else ""
                pod_raw = match.group(2).strip() if match.group(2) else "ВМРП"
                cost_20 = re.sub(r'[^\d]', '', match.group(3)) if match.group(3) else ""
                cost_40 = re.sub(r'[^\d]', '', match.group(4)) if match.group(4) else ""

                if not pol_raw or not cost_20:
                    continue

                pod_vmrp = port_dict.get("ВМРП", "Владивостокский морской рыбный порт")
                pod_parent = "Владивосток"
                end_country = "Россия"

                pol_list = [p.strip() for p in pol_raw.split('/') if p.strip()]

                for pol in pol_list:
                    pol_russian = get_russian_port(pol)
                    start_country = get_country_for_port(pol_russian)
                    # parent_start = город порта (порт сам по себе, нужен родитель-город)
                    pol_parent = start_country if start_country else pol_russian

                    for container_type, cost in [("20DC", cost_20), ("40HC", cost_40)]:
                        if not cost:
                            continue

                        record = {
                            "transport_type": "sea",
                            "start_point": f"{pol_russian}, {start_country}",
                            "end_point": f"{pod_vmrp}, {end_country}",
                            "container_type": container_type,
                            "weight_limit": container_size_dict.get(container_type, ""),
                            "cost": cost,
                            "currency": "USD",
                            "departure_dates": {},
                            "company": company_name,
                            "customs": None,
                            "conditions": None,
                            "duration_max_days": None,
                            "departures": None,
                            "port_service_term": "FIFO",
                            "container_ownership": "COC",
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "parent_start_location": pol_russian,
                            "parent_start_location_type": "city",
                            "parent_end_location": pod_parent,
                            "parent_end_location_type": "city",
                            "start_location_type": "port",
                            "end_location_type": "port"
                        }
                        results.append(record)

    # Parse RAIL section (page 3)
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            if 'НАЗЕМНАЯ ПЕРЕВОЗКА' not in text and '20DC(RUB)' not in text:
                continue

            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or 'Станция' in line or 'Терминал' in line or 'FOR' not in line:
                    continue
                if 'import@t-lc.ru' in line or 'www.t-lc.ru' in line:
                    continue

                city_match = re.match(r'([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)*)\s+FOR', line)
                if not city_match:
                    continue
                dest_city = city_match.group(1).strip()

                numbers_part = line.split('FOR')[1].strip()
                numbers_part_fixed = numbers_part
                while re.search(r'(\d)\s+(\d)', numbers_part_fixed):
                    numbers_part_fixed = re.sub(r'(\d)\s+(\d)', r'\1\2', numbers_part_fixed)

                total_digits = len(numbers_part_fixed)
                if total_digits == 18:
                    numbers = [numbers_part_fixed[i:i+6] for i in range(0, 18, 6)]
                elif total_digits == 15:
                    numbers = [numbers_part_fixed[i:i+5] for i in range(0, 15, 5)]
                else:
                    part_size = total_digits // 3
                    numbers = [numbers_part_fixed[i:i+part_size] for i in range(0, total_digits, part_size)]

                if len(numbers) < 3:
                    continue

                cost_20_le24 = numbers[0]
                cost_20_gt24 = numbers[1]
                cost_40 = numbers[2]

                city_map = {
                    "Санкт-Петербург": "Санкт-Петербург",
                    "Москва": "Москва",
                    "Новосибирск": "Новосибирск",
                    "Тольятти": "Тольятти",
                }
                pod_russian = city_map.get(dest_city, dest_city)

                pol_vmrp = port_dict.get("ВМРП", "Владивостокский морской рыбный порт")

                for container_type, cost, weight_note, min_w, max_w in [
                    ("20DC", cost_20_le24, "≤24т", 0, 24),
                    ("20DC", cost_20_gt24, ">24т, ≤28т", 24, 28),
                    ("40HC", cost_40, "≤26т", 0, 26)
                ]:
                    record = {
                        "transport_type": "rail",
                        "start_point": f"{pol_vmrp}, Россия",
                        "end_point": f"{pod_russian}, Россия",
                        "container_type": container_type,
                        "weight_limit": container_size_dict.get(container_type, ""),
                        "min_weight_kg": min_w,
                        "max_weight_kg": max_w,
                        "cost": cost,
                        "currency": "RUB",
                        "departure_dates": {},
                        "company": company_name,
                        "customs": None,
                        "conditions": f"Ж/Д перевозка из ВМРП ({weight_note})",
                        "duration_max_days": None,
                        "departures": None,
                        "port_service_term": None,
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                        "start_location_type": "port",
                        "parent_start_location": "Владивосток",
                        "parent_start_location_type": "city",
                        "parent_end_location": pod_russian,
                        "parent_end_location_type": "city",
                        "end_location_type": "rail_station"
                    }
                    results.append(record)

    return results


def get_tables_pdf_TCL_Asia_Line(url: str, path: str, company: str):
    pdf_path = Path(path)
    tables_data = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if table:
                    tables_data.append(table)
    return tables_data


# _segments_wrapper_for_parse_TCL_Asia_Line
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_TCL_Asia_Line_impl = parse_TCL_Asia_Line


def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_TCL_Asia_Line_impl(*args, **kwargs))
