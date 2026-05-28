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
    get_city_port,
    get_city_station,
    get_country,
    port_dict,
    region_dict,
)


def parse_GrandLog_xlsx(filepath: str):
    # Считываем весь Excel в DataFrame без заголовков
    df = pd.read_excel(filepath, header=None, sheet_name="ООО «ГрандЛог»")
    company = "GrandLog"
    # Найдем строки, где начинается новая таблица (по наличию "Станция отправления")
    header_rows = df.index[df.iloc[:, 0] == 'Станция отправления'].tolist()
    tables = []
    #print(header_rows)
    for i, start in enumerate(header_rows):
        # конец таблицы — перед следующей "Станция отправления" или конец файла
        end = header_rows[i + 1] if i + 1 < len(header_rows) else len(df)
        sub_df = df.iloc[start:end].reset_index(drop=True)
        sub_df.columns = sub_df.iloc[0]  # первая строка — это заголовки
        sub_df = sub_df.drop(0).reset_index(drop=True)
        tables.append(sub_df)

    # Объединяем все таблицы
    full_df = pd.concat(tables, ignore_index=True)
    # Преобразуем числовые столбцы
    for col in full_df.columns:
        if col not in ['Станция отправления', 'Станция назначения']:
            full_df[col] = (
                full_df[col]
                .astype(str)
                .str.replace(' ', '', regex=False)
                .str.replace(',', '.', regex=False)
                .astype(float)
            )

    # Группировка по станции отправления → список записей
    result = []
    for station_departure, group in full_df.groupby('Станция отправления'):
        records = group.drop(columns=['Станция отправления']).to_dict(orient="records")
        pol_port = get_city_station(station_departure)
        for record in records:
            station_destinations = record["Станция назначения"].replace(" - ",'-').strip()
            if "/" in station_destinations:
                station_destinations = station_destinations.strip().split("/")
            else:
                station_destinations = [station_destinations]
            for station_destination in station_destinations:
                pod_port = get_city_station(station_destination)
                container_types = ["40ф КТК до 28т","20ф КТК до 24т","20ф КТК с 24т до 28т"]
                for container_type in container_types:
                    result.append({
                        "transport_type": "rail",
                        "start_point": f"{pol_port}, {get_country(pol_port)}",
                        "end_point": f"{pod_port}, {get_country(pod_port)}",
                        "container_type": "20DC" if "20ф" in container_type else "40HC",
                        "weight_limit": container_size_dict.get("20DC") if "до 24т" in container_type else container_size_dict.get("40HC"),
                        "cost": record[container_type],
                        "currency": currency_dict.get("руб"),
                        "departure_dates": {},
                        "company": company,
                        "conditions": f"Станция отправления: {station_departure}.\nСтанция назначения: {station_destination},\nSOC",
                        "parent_start_location": station_departure,
                        "parent_start_location_type": "city",
                        "parent_end_location": station_destination,
                        "parent_end_location_type": "city",
                    })

    return pd.DataFrame(result)

#df_GrandLog = parse_GrandLog_xlsx("Транспортные компании.xlsx")
#with pd.ExcelWriter("tariff_analysis_GrandLog.xlsx") as writer:
#    df_GrandLog.to_excel(writer, sheet_name="Raw Data", index=False)

# =============================
# 8.2 Парсер «ГрандЛог»
# =============================


def parse_GrandLog(filepath: str):
    """
    text_blocks — список строк как после PDF:
    [
        "ООО ...",  # инфо
        "Терминальные услуги...",
        "Станция отправления Станция назначения 40ф ...",
        "Угловая Омск-Восточный 180000 ...",
        ...
    ]
    """
    company = "GrandLog"
    tables, text_blocks = get_tables_pdf(None, filepath, company)
    # Объединяем всё в один "сырой" текст
    raw = "\n".join(text_blocks)

    # Находим все таблицы по триггеру "Станция отправления"
    table_chunks = re.split(r"(?=Станция отправления)", raw)

    tables = []

    for chunk in table_chunks:
        if "Станция отправления" not in chunk:
            continue

        lines = [l.strip() for l in chunk.split("\n") if l.strip()]

        # Первая строка — заголовки
        header_line = lines[0]
        headers = header_line.split()
        # Пример: ["Станция", "отправления", "Станция", "назначения", "40ф", "КТК", "до", "28т", ...]

        # Нормализуем заголовки
        normalized_headers = []
        i = 0
        while i < len(headers):
            word = headers[i]

            # Склеиваем составные заголовки
            if word == "Станция" and i + 1 < len(headers) and headers[i + 1] in ["отправления", "назначения"]:
                normalized_headers.append(f"{word} {headers[i+1]}")
                i += 2
                continue

            # Склеиваем "40ф КТК до 28т"
            if "ф" in word and i + 3 < len(headers) and headers[i+1] == "КТК" and headers[i+2] == "до":
                container_header = f"{word} {headers[i+1]} {headers[i+2]} {headers[i+3]}"
                normalized_headers.append(container_header)
                i += 4
                continue

            if "ф" in word and i + 5 < len(headers) and headers[i+1] == "КТК" and headers[i+2] == "с":
                container_header = f"{word} {headers[i+1]} {headers[i+2]} {headers[i+3]} {headers[i+4]} {headers[i+5]}"
                normalized_headers.append(container_header)
                i += 6
                continue
            normalized_headers.append(word)
            i += 1
        # Читаем строки данных
        data_rows = []
        for line in lines[1:]:

            parts = line.split()
            if "Ставки" in parts or "+7" in parts or "по" in parts:
                continue

            if len(parts) < 3:
                continue

            # Нормализуем строки, склеиваем станции
            station_from = parts[0]
            station_to = parts[1]
            indx_cost = 2
            if not parts[2].isdigit() and "," not in parts[2]:
                station_to += " " + parts[2]
                indx_cost = 3
            # Остальные значения — цены
            values = parts[indx_cost:]

            costs = []
            for index_cost in range(len(values)):
                cost = values[index_cost]
                cost = cost.replace(",",".")
                c_ = float(cost)
                if c_ == 0.0:
                    costs.append(values[index_cost-1]+values[index_cost])
                elif len(cost) >= 6:
                    costs.append(values[index_cost])

            row = [station_from, station_to] + costs
            data_rows.append(row)

        df = pd.DataFrame(data_rows, columns=normalized_headers)
        tables.append(df)

    # Объединяем все найденные таблицы
    full_df = pd.concat(tables, ignore_index=True)

    # Числовые поля приводим к float
    for col in full_df.columns:
        if "Станция" in col:
            continue
        full_df[col] = (
            full_df[col]
            .astype(str)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.replace(" ", "", regex=False)
        )
        full_df[col] = pd.to_numeric(full_df[col], errors="coerce")

    # ========================================================
    # Формируем итоговую структуру
    # ========================================================

    container_map = {
        "40ф КТК до 28т": ("40HC", "28"),
        "20ф КТК до 24т": ("20DC", "24"),
        "20ф КТК с 24т до 28т": ("20DC", "28"),
    }

    moscow_node_stations = [
        "Силикатная",
        "Белый Раст",
        "Чехов",
        "Ховрино",
        "Селятино",
        "Раменское",
        "Электроугли",
        "Тучково",
        "Купавна",
        "Люблино",
        "Люберцы",
        "Орехово-Зуево",
    ]

    result = []

    for _, row in full_df.iterrows():
        pods_ = row["Станция назначения"] + "/"
        for pod_ in pods_.split("/"):
            if pod_ == "" or pod_ == None:
                continue
            pol_rail_station = row["Станция отправления"]
            pod_rail_station = pod_
            pol_city = get_city_station(pol_rail_station)

            # Если это Станциимосковского узла, развернуть в список дочерних станций
            if "Станциимосковского узла" in pod_rail_station:
                destination_stations = moscow_node_stations
            else:
                destination_stations = [pod_rail_station]

            for destination in destination_stations:
                pod_city = get_city_port(destination) or get_city_station(destination)

                for container_header, (ctype, weight) in container_map.items():
                    if container_header not in full_df.columns:
                        continue

                    cost = row[container_header]
                    if pd.isna(cost):
                        continue

                    result.append(TariffSegment(
                        transport_type= "rail",
                        start_point= f"{pol_rail_station}, {get_country(pol_city)}",
                        end_point= f"{destination}, {get_country(pod_city)}",
                        start_location_type="rail_station",
                        end_location_type="rail_station",
                        parent_end_location=pod_city,
                        parent_start_location=pol_city,
                        parent_end_location_type="city",
                        parent_start_location_type="city",
                        container_type= ctype,
                        weight_limit= weight,
                        min_weight_kg="24" if weight=="28" and ctype=="20DC" else None,
                        max_weight_kg="28" if weight=="28" else "24",
                        cost= cost,
                        currency= "RUB",
                        company= company,
                        container_ownership= "SOC"
                    ))

    return pd.DataFrame(result)

# _segments_wrapper_for_parse_GrandLog
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_GrandLog_impl = parse_GrandLog

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_GrandLog_impl(*args, **kwargs))


# =====================================================================
# Парсер коммерческого предложения ГрандЛог (PDF морские+жд ставки)
# =====================================================================

_OFFER_RU_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

# Нормализация названий портов отгрузки из PDF → каноническое русское название
_OFFER_POL_NORMALIZE = {
    "Циндао": "Циндао",
    "Нингбо": "Нинбо",
    "Шанхай": "Шанхай",
    "Нанша": "Наньша",
    "Сямынь": "Сямынь",
}

# Нормализация городов назначения из PDF
_OFFER_CITY_NORMALIZE = {
    "С.-Петербург": "Санкт-Петербург",
    "С- Петербург": "Санкт-Петербург",
    "C.-Петербург": "Санкт-Петербург",
    "С -Петербург": "Санкт-Петербург",
}


def _offer_price(s: str) -> float | None:
    if not s:
        return None
    # Обрабатываем форматы "180 530,00" и "$2 040,00"
    # Удаляем пробелы (тысячный разделитель), заменяем запятую на точку
    cleaned = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    # Оставляем только цифры и точку
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    try:
        return int(float(cleaned)) if cleaned else None
    except ValueError:
        return None


def _offer_valid_to(text: str) -> str | None:
    m = re.search(r"действительны до\s+(\d+)\s+(\w+)\s+(\d{4})", text, re.I)
    if not m:
        return None
    day, month_ru, year = m.group(1), m.group(2).lower(), int(m.group(3))
    mon = _OFFER_RU_MONTHS.get(month_ru)
    if not mon:
        return None
    return f"{year}-{mon}-{day.zfill(2)}"


def _offer_dep_date(raw: str, year: int = 2026) -> str | None:
    raw = raw.replace("\n", " ").strip()
    m = re.search(r"(\d+)\s+(\w+)", raw)
    if not m:
        return None
    day = m.group(1)
    month_word = m.group(2).lower()

    # Ищем месяц по началу слова (так как может быть "апреля" вместо "апрель")
    mon = _OFFER_RU_MONTHS.get(month_word)
    if not mon:
        # Пробуем найти по префиксу
        for key in _OFFER_RU_MONTHS:
            if month_word.startswith(key[:3]):
                mon = _OFFER_RU_MONTHS[key]
                break

    if not mon:
        return None
    return f"{day.zfill(2)}.{mon}.{year}"


def parse_GrandLog_offer(filepath: str) -> list[TariffSegment]:
    """
    Парсит PDF коммерческого предложения ГрандЛог на морские перевозки.

    Извлекает:
    - ставки морского фрахта (POL Китай → Врангель + Drop Off по городам РФ)
    - ставки ж/д отправок CY-FOR (Врангель → города РФ, 3 типоразмера + охрана)
    - срок действия ставок (valid_to)
    """
    company = "GrandLog"
    result: list[TariffSegment] = []

    with pdfplumber.open(filepath) as pdf:
        full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    valid_to = _offer_valid_to(full_text)

    _parse_offer_from_text(full_text, company, valid_to, result)

    return result


def _parse_offer_from_text(text: str, company: str, valid_to: str | None, out: list) -> None:
    """Парсит предложение из текстового представления PDF (extract_text)."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # ---- Морские ставки ----
    # Формат: "POL Vrangel TRANSIT_DAYS"
    # Затем: города и ставки, дата разбита между линиями

    pol_names = set(_OFFER_POL_NORMALIZE.keys())

    # Найти все POL линии (POL Vrangel транзит)
    pol_lines = []
    for i, line in enumerate(lines):
        for p in pol_names:
            if p in line and "vrangel" in line.lower():
                numbers = re.findall(r'\d+', line)
                transit = int(numbers[-1]) if numbers else None
                pol_lines.append((i, p, transit))
                break

    if not pol_lines:
        return

    # Обработать города для каждого POL
    for pol_idx, (pol_line_idx, pol, transit) in enumerate(pol_lines):
        # Определить диапазон строк с городами для этого POL
        if pol_idx == 0:
            # Для первого POL: города между началом (после заголовка) и первой POL линией
            city_start = 5  # Первая строка с городом
        else:
            # Для последующих POL: города между предыдущей POL линией и текущей
            city_start = pol_lines[pol_idx - 1][0] + 1

        city_end = pol_line_idx

        # Собрать города в этом диапазоне
        pol_block_lines = []
        for city_idx in range(city_start, city_end):
            if city_idx < len(lines):
                pol_block_lines.append(lines[city_idx])

        # Ищем дату в блоке POL
        # Дата разбита между строками: дата часто находится в первой строке после города
        # или после цен, месяц в том же месте
        cur_date = ""

        # Поиск месяца в первой строке блока
        month_match = None
        day_match = None

        if pol_block_lines:
            # Дата обычно находится в конце первой строки блока
            # Например: "Санкт-Петербург $1 900,00 $2 810,00 апреля"
            # или на следующей строке может быть день
            first_line = pol_block_lines[0]

            # Ищем месяц в первой строке
            months_pattern = r'\b([а-яА-Я]{3,10}(?:я|ь)?)\b'
            for m in re.finditer(months_pattern, first_line):
                candidate = m.group(1).lower()
                for month_key in _OFFER_RU_MONTHS:
                    if candidate.startswith(month_key[:3]):
                        month_match = month_key
                        break
                if month_match:
                    break

            # Ищем день в конце первой строки или в начале строки POL
            # День может быть перед или после месяца
            day_in_first = re.findall(r'\b([2-3]\d)\b', first_line)
            if day_in_first:
                for day in day_in_first:
                    d = int(day)
                    if 20 <= d <= 31:
                        day_match = day
                        break

            # Если дня нет в первой строке, ищем в остальных строках блока
            if not day_match:
                # Ищем все числа 20-31 в остальных строках блока
                for bl in pol_block_lines[1:]:
                    day_in_line = re.findall(r'\b([2-3]\d)\b', bl)
                    if day_in_line:
                        for day in day_in_line:
                            d = int(day)
                            if 20 <= d <= 31:
                                day_match = day
                                break
                    if day_match:
                        break

        if day_match and month_match:
            cur_date = f"{day_match} {month_match}"

        # Теперь парсим города из блока
        for line in pol_block_lines:
            # Пытаемся распарсить линию как данные города
            city_name = None
            for cn in _OFFER_CITY_NORMALIZE.keys():
                if cn in line:
                    city_name = cn
                    break
            if not city_name:
                # Ищем известные города в начале линии
                for known_city in ["Москва", "Новосибирск", "Екатеринбург", "Санкт-Петербург"]:
                    if line.startswith(known_city):
                        city_name = known_city
                        break

            if city_name:
                # Парсим ставки из этой линии
                remaining = line[len(city_name):].strip()
                # Ищем цены (формат: $2 040,00 или 180 530,00 ₽)
                prices = re.findall(r'\$[\d\s,]+', remaining)

                if len(prices) >= 2:
                    p20 = _offer_price(prices[0])
                    p40 = _offer_price(prices[1])

                    city = _OFFER_CITY_NORMALIZE.get(city_name, city_name)
                    pol_ru = _OFFER_POL_NORMALIZE.get(pol, pol)
                    pol_country = get_country(pol_ru) or "Китай"
                    pod_ru = "Терминал Врангель"
                    pod_city = get_city_port(pod_ru) or "Находка"
                    pod_country = get_country(pod_city) or "Россия"
                    city_country = get_country(city) or "Россия"

                    dep_date = _offer_dep_date(cur_date) if cur_date else None

                    base = dict(
                        transport_type="sea",
                        start_point=f"{pol_ru}, {pol_country}",
                        end_point=f"{pod_ru}, {pod_country}",
                        start_location_type="port",
                        end_location_type="port",
                        parent_start_location=pol_ru,
                        parent_start_location_type="city",
                        parent_end_location=pod_city,
                        parent_end_location_type="city",
                        dropoff_location=city,
                        dropoff_location_type="city",
                        dropoff_location_country=city_country,
                        currency="USD",
                        company=company,
                        duration_max_days=transit,
                        valid_to=valid_to,
                        #departure_dates=dep_date,
                    )

                    if p20 is not None:
                        out.append(TariffSegment(
                            container_type="20DC",
                            weight_limit=container_size_dict.get("20DC", "24"),
                            max_weight_kg=container_size_dict.get("20DC", "24"),
                            cost=p20,
                            **base,
                        ))
                    if p40 is not None:
                        out.append(TariffSegment(
                            container_type="40HC",
                            weight_limit=container_size_dict.get("40HC", "28"),
                            max_weight_kg=container_size_dict.get("40HC", "28"),
                            cost=p40,
                            **base,
                        ))

    # ---- Ж/д ставки ----
    # Ищем "Ставки на жд отправки CY – FOR" или "город прибытия"
    rail_start = None
    for i, line in enumerate(lines):
        if "город прибытия" in line.lower() or ("жд отправк" in line.lower()):
            rail_start = i
            break

    if rail_start is None:
        return

    # Парсим ж/д таблицу
    # Формат: "Москва 180 530,00 ₽ 210 530,00 ₽ 263 530,00 ₽ 4 704,00 ₽ 9 435,00 ₽"

    pol_ru = "Терминал Врангель"
    pol_city = get_city_port(pol_ru) or "Находка"
    pol_country = get_country(pol_city) or "Россия"

    for i in range(rail_start + 1, len(lines)):
        line = lines[i]

        # Ищем город (начинается с известного города)
        city = None
        for known_city in ["Москва", "Новосибирск", "Санкт-Петербург", "С.-Петербург", "Екатеринбург"]:
            if line.startswith(known_city):
                city = known_city
                break

        if not city:
            continue

        city = _OFFER_CITY_NORMALIZE.get(city, city)
        city_country = get_country(city) or "Россия"

        # Извлекаем все цены из линии (в рублях)
        prices = re.findall(r'(\d[\d\s,]*?\d)\s*₽', line)

        if len(prices) < 3:
            continue

        p20_24 = _offer_price(prices[0]) if len(prices) > 0 else None
        p20_28 = _offer_price(prices[1]) if len(prices) > 1 else None
        p40 = _offer_price(prices[2]) if len(prices) > 2 else None
        охрана_20 = _offer_price(prices[3]) if len(prices) > 3 else None
        охрана_40 = _offer_price(prices[4]) if len(prices) > 4 else None

        if p20_24 is None and p20_28 is None and p40 is None:
            continue

        охрана_parts = []
        if охрана_20:
            охрана_parts.append(f"Охрана 20': {prices[3]}")
        if охрана_40:
            охрана_parts.append(f"Охрана 40': {prices[4]}")
        cond = " ".join(охрана_parts) if охрана_parts else None

        rail_base = dict(
            transport_type="rail",
            start_point=f"{pol_ru}, {pol_country}",
            end_point=f"{city}, {city_country}",
            start_location_type="port",
            end_location_type="rail_station",
            parent_start_location=pol_city,
            parent_start_location_type="city",
            parent_end_location=city,
            parent_end_location_type="city",
            currency="RUB",
            company=company,
            conditions=cond,
            valid_to=valid_to,
        )

        if p20_24 is not None:
            out.append(TariffSegment(
                container_type="20DC",
                weight_limit=container_size_dict.get("20DC", "24"),
                max_weight_kg="24",
                cost=p20_24,
                **rail_base,
            ))
        if p20_28 is not None:
            out.append(TariffSegment(
                container_type="20DC",
                weight_limit="28",
                min_weight_kg="24",
                max_weight_kg="28",
                cost=p20_28,
                **rail_base,
            ))
        if p40 is not None:
            out.append(TariffSegment(
                container_type="40HC",
                weight_limit=container_size_dict.get("40HC", "28"),
                max_weight_kg="28",
                cost=p40,
                **rail_base,
            ))
