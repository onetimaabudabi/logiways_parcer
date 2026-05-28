"""Парсер ООО «Гарант Интермодал» — 5 типов тарифных файлов."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import (
    container_size_dict,
    get_city_port,
    get_city_station,
    get_country,
    port_dict,
)

_COMPANY = "Гарант Интермодал"

_RU_MONTHS = {
    "января": "01",
    "февраля": "02",
    "марта": "03",
    "апреля": "04",
    "мая": "05",
    "июня": "06",
    "июля": "07",
    "августа": "08",
    "сентября": "09",
    "октября": "10",
    "ноября": "11",
    "декабря": "12",
}


def _extract_valid_dates(text: str) -> tuple[str | None, str | None]:
    """Извлекает valid_from и valid_to из 'Срок действия: DD месяц YYYY г. – DD месяц YYYY г.'"""
    m = re.search(
        r"Срок действия:\s*(\d+)\s+(\w+)\s+(\d{4})\s*г\.\s*–\s*(\d+)\s+(\w+)\s+(\d{4})\s*г\.",
        text,
    )
    if not m:
        return None, None

    day1, month1_ru, year1, day2, month2_ru, year2 = (
        m.group(1),
        m.group(2).lower(),
        m.group(3),
        m.group(4),
        m.group(5).lower(),
        m.group(6),
    )

    month1 = _RU_MONTHS.get(month1_ru)
    month2 = _RU_MONTHS.get(month2_ru)

    valid_from = f"{year1}-{month1}-{day1.zfill(2)}" if month1 else None
    valid_to = f"{year2}-{month2}-{day2.zfill(2)}" if month2 else None

    return valid_from, valid_to


def _safe_str(val: any) -> str:
    """Безопасно преобразует значение в строку, обрабатывая None/NaN."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if s in ("None", "nan", "NaN", "<NA>"):
        return ""
    return s


def _parse_price(val) -> int | None:
    """Парсит цену из строки."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace("\xa0", "").replace(" ", "").replace("rub", "").replace("руб", "")
    if not s or s in ("-", "По запросу"):
        return None
    try:
        s = re.sub(r"[^\d]", "", s)
        return int(s) if s else None
    except (ValueError, TypeError):
        return None


def _normalize_pol_name(name: str) -> str:
    """Нормализует названия портов отправления."""
    name = name.strip().replace("(прямой)", "").replace("(", "").replace(")", "").strip()
    return port_dict.get(name, name)


def parse_type1_moscow_only(pdf_path: str, text: str) -> list[dict]:
    """Тип 1: Все порты → ЖД Москва (FOR+FOT). Files 1, 4."""
    results = []
    valid_from, valid_to = _extract_valid_dates(text)

    with pdfplumber.open(pdf_path) as pdf:
        page_tables = pdf.pages[0].extract_tables()

        # Sea table
        sea_df = pd.DataFrame(page_tables[0][1:], columns=page_tables[0][0])
        pod_name = port_dict.get("ВМРП", "ВМРП")
        pod_city = get_city_port(port_dict.get("ВМРП", "ВМРП")) or "Находка"

        for idx, row in sea_df.iterrows():
            pol = _normalize_pol_name(str(row.iloc[0]).strip()).title()
            pol_country = get_country(pol) or "Китай"
            prices_str = str(row.iloc[2]).strip()

            if "/" in prices_str:
                parts = prices_str.split("/")
                price_20 = _parse_price(parts[0])
                price_40 = _parse_price(parts[1])
            else:
                price_20 = _parse_price(row.iloc[2])
                price_40 = _parse_price(row.iloc[3]) if len(row) > 3 else None
            if price_20:
                results.append(TariffSegment(
                    transport_type="sea", start_point=f"{pol}, {pol_country}",
                    end_point=f"{pod_name}, Россия", container_type="20DC",
                    cost=price_20, currency="USD", company=_COMPANY, container_ownership="SOC",
                    port_service_term="FILO", valid_from=valid_from, valid_to=valid_to,
                    parent_start_location=pol, parent_start_location_type="city",
                    parent_end_location=pod_city, parent_end_location_type="city",
                    start_location_type="port", end_location_type="port",
                    weight_limit=container_size_dict.get("20DC"),
                ).to_dict())

            if price_40:
                results.append(TariffSegment(
                    transport_type="sea", start_point=f"{pol}, {pol_country}",
                    end_point=f"{pod_name}, Россия", container_type="40HC",
                    cost=price_40, currency="USD", company=_COMPANY, container_ownership="SOC",
                    port_service_term="FILO", valid_from=valid_from, valid_to=valid_to,
                    parent_start_location=pol, parent_start_location_type="city",
                    parent_end_location=pod_city, parent_end_location_type="city",
                    start_location_type="port", end_location_type="port",
                    weight_limit=container_size_dict.get("40HC"),
                ).to_dict())

        # Rail table 1 - таблица 1 с разреженной структурой
        if len(page_tables) > 1:
            rail_table1 = page_tables[1]
            # Sparse format: columns [1, 4, 7, 10, 13, 16] contain data
            for row_idx in range(1, len(rail_table1)):
                row = rail_table1[row_idx]
                port = _safe_str(row[1])  # Column 1: port name

                if not port:
                    continue

                port_name = port_dict.get(port, port)
                port_city = get_city_port(port_dict.get(port, port))

                p20_24 = _parse_price(row[4] if len(row) > 4 else None)
                p20_28 = _parse_price(row[7] if len(row) > 7 else None)
                p40 = _parse_price(row[13] if len(row) > 13 else None)

                if p20_24:
                    results.append(TariffSegment(
                        transport_type="rail", start_point=f"{port_name}, Россия",
                        end_point="Москва, Россия", container_type="20DC", cost=p20_24,
                        currency="RUB", company=_COMPANY, container_ownership="SOC",
                        valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=port_city,
                        parent_start_location_type="city", parent_end_location="Москва",
                        parent_end_location_type="city", start_location_type="port",
                        end_location_type="rail_station", weight_limit=container_size_dict.get("20DC"),
                        max_weight_kg=24,
                    ).to_dict())

                if p20_28:
                    results.append(TariffSegment(
                        transport_type="rail", start_point=f"{port_name}, Россия",
                        end_point="Москва, Россия", container_type="20DC", cost=p20_28,
                        currency="RUB", company=_COMPANY, container_ownership="SOC",
                        valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=port_city,
                        parent_start_location_type="city", parent_end_location="Москва",
                        parent_end_location_type="city", start_location_type="port",
                        end_location_type="rail_station", weight_limit="28",
                        min_weight_kg=24, max_weight_kg=28,
                    ).to_dict())

                if p40:
                    results.append(TariffSegment(
                        transport_type="rail", start_point=f"{port_name}, Россия",
                        end_point="Москва, Россия", container_type="40HC", cost=p40,
                        currency="RUB", company=_COMPANY, container_ownership="SOC",
                        valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=port_city,
                        parent_start_location_type="city", parent_end_location="Москва",
                        parent_end_location_type="city", start_location_type="port",
                        end_location_type="rail_station", weight_limit=container_size_dict.get("40HC"),
                        max_weight_kg=28,
                    ).to_dict())

        # Rail table 2 - таблица 2 со стандартной структурой
        if len(page_tables) > 2:
            rail_table2 = page_tables[2]
            # Standard format: [Port, 20DC до 24т, 20DC от 24т до 28т, Охрана, 40HC, Охрана]
            for row_idx in range(1, len(rail_table2)):
                row = rail_table2[row_idx]
                port = _safe_str(row[0])

                if not port:
                    continue

                port_name = port_dict.get(port, port)
                port_city = get_city_port(port_dict.get(port, port))

                p20_24 = _parse_price(row[1] if len(row) > 1 else None)
                p20_28 = _parse_price(row[2] if len(row) > 2 else None)
                p40 = _parse_price(row[4] if len(row) > 4 else None)

                if p20_24:
                    results.append(TariffSegment(
                        transport_type="rail", start_point=f"{port_name}, Россия",
                        end_point="Москва, Россия", container_type="20DC", cost=p20_24,
                        currency="RUB", company=_COMPANY, container_ownership="SOC",
                        valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=port_city,
                        parent_start_location_type="city", parent_end_location="Москва",
                        parent_end_location_type="city", start_location_type="port",
                        end_location_type="rail_station", weight_limit=container_size_dict.get("20DC"),
                        max_weight_kg=24,
                    ).to_dict())

                if p20_28:
                    results.append(TariffSegment(
                        transport_type="rail", start_point=f"{port_name}, Россия",
                        end_point="Москва, Россия", container_type="20DC", cost=p20_28,
                        currency="RUB", company=_COMPANY, container_ownership="SOC",
                        valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=port_city,
                        parent_start_location_type="city", parent_end_location="Москва",
                        parent_end_location_type="city", start_location_type="port",
                        end_location_type="rail_station", weight_limit="28",
                        min_weight_kg=24, max_weight_kg=28,
                    ).to_dict())

                if p40:
                    results.append(TariffSegment(
                        transport_type="rail", start_point=f"{port_name}, Россия",
                        end_point="Москва, Россия", container_type="40HC", cost=p40,
                        currency="RUB", company=_COMPANY, container_ownership="SOC",
                        valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=port_city,
                        parent_start_location_type="city", parent_end_location="Москва",
                        parent_end_location_type="city", start_location_type="port",
                        end_location_type="rail_station", weight_limit=container_size_dict.get("40HC"),
                        max_weight_kg=28,
                    ).to_dict())

    return results


def parse_type2_coc_stations(pdf_path: str, text: str) -> list[dict]:
    """Тип 2: COC Shanghai/Busan → Vrangle → Stations. File 2."""
    results = []
    valid_from, valid_to = _extract_valid_dates(text)

    with pdfplumber.open(pdf_path) as pdf:
        page_tables = pdf.pages[0].extract_tables()

        # Sea table
        pod_name = port_dict.get("Терминал Врангель")
        pod_city = get_city_port(port_dict.get("Терминал Врангель")) or "Находка"

        sea_df = pd.DataFrame(page_tables[0][1:], columns=page_tables[0][0])
        for idx, row in sea_df.iterrows():
            pol = _normalize_pol_name(str(row.iloc[0]).strip()).title()
            pol_country = get_country(pol)
            prices = str(row.iloc[2]).strip().split("/")
            p20, p40 = _parse_price(prices[0]), _parse_price(prices[1]) if len(prices) > 1 else None

            if p20:
                results.append(TariffSegment(
                    transport_type="sea", start_point=f"{pol}, {pol_country}",
                    end_point=f"{pod_name}, Россия", container_type="20DC", cost=p20,
                    currency="USD", company=_COMPANY, container_ownership="COC",
                    port_service_term="FILO", valid_from=valid_from, valid_to=valid_to,
                    parent_start_location=pol, parent_start_location_type="city",
                    parent_end_location=pod_city, parent_end_location_type="city",
                    start_location_type="port", end_location_type="port",
                    weight_limit=container_size_dict.get("20DC"),
                ).to_dict())

            if p40:
                results.append(TariffSegment(
                    transport_type="sea", start_point=f"{pol}, {pol_country}",
                    end_point=f"{pod_name}, Россия", container_type="40HC", cost=p40,
                    currency="USD", company=_COMPANY, container_ownership="COC",
                    port_service_term="FILO", valid_from=valid_from, valid_to=valid_to,
                    parent_start_location=pol, parent_start_location_type="city",
                    parent_end_location=pod_city, parent_end_location_type="city",
                    start_location_type="port", end_location_type="port",
                    weight_limit=container_size_dict.get("40HC"),
                ).to_dict())

        # Rail tables - на всех страницах
        for page_num in range(len(pdf.pages)):
            page_tables = pdf.pages[page_num].extract_tables()
            if page_num == 0 and page_tables and len(page_tables) > 1:
                tables = page_tables[1:]  # Skip sea table on page 0
            elif page_num == 0:
                continue
            else:
                tables = page_tables if page_tables else []

            if not tables:
                continue

            for rail_table in tables:
                if not rail_table or len(rail_table) < 2:
                    continue

                # Check if this is a rail table by inspecting header
                header = rail_table[0]
                if not any("Станция" in str(h) for h in header):
                    continue

                # Determine station column index based on header length
                if len(header) <= 7:
                    # Standard format: Station is at column 1
                    station_col_idx = 1
                else:
                    # Sparse format (File 2): Station is at column 0 despite header[1] saying "Станция назначения"
                    station_col_idx = 0

                for row_idx in range(1, len(rail_table)):
                    row = rail_table[row_idx]
                    station_raw = _safe_str(row[station_col_idx] if len(row) > station_col_idx else "")
                    if not station_raw or "Станция" in station_raw:
                        continue

                    # Remove parenthetical notes first
                    if "(" in station_raw:
                        station_raw = station_raw.split("(")[0].strip()

                    # Extract station name
                    if "," in station_raw:
                        station = station_raw.split(",")[1].strip()
                    else:
                        station = station_raw.strip()
                    if " -" in station:
                        station = station.split(" -")[0].strip()
                    city = get_city_station(station) or station

                    # Find price columns
                    # Check header length to determine format
                    if len(header) <= 7:
                        # Standard structure: [Port, Station, 20DC до 24т, 20DC от 24т до 28т, Охрана, 40 HC, Охрана]
                        p20_24 = _parse_price(row[2] if len(row) > 2 else None)
                        p20_28 = _parse_price(row[3] if len(row) > 3 else None)
                        p40 = _parse_price(row[5] if len(row) > 5 else None)
                    else:
                        # Sparse format with empty columns: File 2
                        p20_24 = _parse_price(row[3] if len(row) > 3 else None)
                        p20_28 = _parse_price(row[6] if len(row) > 6 else None)
                        p40 = _parse_price(row[12] if len(row) > 12 else None)

                    for p, w_min, w_max, ct in [(p20_24, None, 24, "20DC"), (p20_28, 24, 28, "20DC"), (p40, None, 28, "40HC")]:
                        if p:
                            rail_pod_name = port_dict.get("Терминал Врангель")
                            rail_pod_city = get_city_port(port_dict.get("Терминал Врангель"))
                            results.append(TariffSegment(
                                transport_type="rail", start_point=f"{rail_pod_name}, Россия",
                                end_point=f"{station}, Россия", container_type=ct, cost=p,
                                currency="RUB", company=_COMPANY, container_ownership="COC",
                                valid_from=valid_from, valid_to=valid_to,
                                parent_start_location=rail_pod_city, parent_start_location_type="city",
                                parent_end_location=city, parent_end_location_type="city",
                                start_location_type="port", end_location_type="rail_station",
                                weight_limit=container_size_dict.get(ct),
                                min_weight_kg=w_min, max_weight_kg=w_max,
                            ).to_dict())

    return results


def parse_type3_vmrp_stations(pdf_path: str, text: str) -> list[dict]:
    """Тип 3: SOC Shanghai/Busan → ВМРП → Stations. File 3."""
    results = []
    valid_from, valid_to = _extract_valid_dates(text)

    with pdfplumber.open(pdf_path) as pdf:
        page_tables = pdf.pages[0].extract_tables()

        # Sea table
        sea_df = pd.DataFrame(page_tables[0][1:], columns=page_tables[0][0])
        for idx, row in sea_df.iterrows():
            pol = _normalize_pol_name(str(row.iloc[0]).strip()).title()
            pol_country = get_country(pol) or "Азия"
            p20 = _parse_price(row.iloc[2])
            p40 = _parse_price(row.iloc[3])

            for p, ct in [(p20, "20DC"), (p40, "40HC")]:
                if p:
                    port_name = port_dict.get("ВМРП", "ВМРП")
                    port_city = get_city_port(port_dict.get("ВМРП", "ВМРП"))
                    results.append(TariffSegment(
                        transport_type="sea", start_point=f"{pol}, {pol_country}",
                        end_point=f"{port_name}, Россия", container_type=ct, cost=p,
                        currency="USD", company=_COMPANY, container_ownership="SOC",
                        port_service_term="FILO", valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=pol, parent_start_location_type="city",
                        parent_end_location=port_city, parent_end_location_type="city",
                        start_location_type="port", end_location_type="port",
                        weight_limit=container_size_dict.get(ct),
                    ).to_dict())

        # Rail tables - могут быть на разных страницах
        for page_num in range(len(pdf.pages)):
            tables = pdf.pages[page_num].extract_tables()
            if not tables:
                continue

            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue

                # Skip sea tables - check if this is a rail table by header
                header = table[0]
                if not any("Станция" in str(h) for h in header):
                    continue

                rail_df = pd.DataFrame(table[1:], columns=table[0])
                for idx, row in rail_df.iterrows():
                    station_raw = _safe_str(row.iloc[1]) if len(row) > 1 else ""
                    if not station_raw or "Станция" in station_raw:
                        continue
                    
                    # Extract station name
                    if ":" in station_raw:
                        station = station_raw.split(":")[1].strip()
                    elif "," in station_raw:
                        station = station_raw.split(",")[1].strip()
                    else:
                        if "(" in station_raw:
                            station_raw = station_raw.split("(")[0].strip()
                        station = station_raw.strip()
                    if " -" in station:
                        station = station.split(" -")[0].strip()
                    city = get_city_station(station) or station

                    p20_24 = _parse_price(row.iloc[2]) if len(row) > 2 else None
                    p20_28 = _parse_price(row.iloc[3]) if len(row) > 3 else None
                    p40 = _parse_price(row.iloc[5]) if len(row) > 5 else None

                    for p, w_min, w_max, ct in [(p20_24, None, 24, "20DC"), (p20_28, 24, 28, "20DC"), (p40, None, 28, "40HC")]:
                        if p:
                            port_name = port_dict.get("ВМРП", "ВМРП").title()
                            port_city = get_city_port(port_dict.get("ВМРП", "ВМРП"))
                            results.append(TariffSegment(
                                transport_type="rail", start_point=f"{port_name}, Россия",
                                end_point=f"{station}, Россия", container_type=ct, cost=p,
                                currency="RUB", company=_COMPANY, container_ownership="SOC",
                                valid_from=valid_from, valid_to=valid_to,
                                parent_start_location=port_city, parent_start_location_type="city",
                                parent_end_location=city, parent_end_location_type="city",
                                start_location_type="port", end_location_type="rail_station",
                                weight_limit=container_size_dict.get(ct),
                                min_weight_kg=w_min, max_weight_kg=w_max,
                            ).to_dict())

    return results


def parse_type4_vrangle_stations(pdf_path: str, text: str) -> list[dict]:
    """Тип 4: SOC Many POLs → Vrangle → Stations. File 5."""
    results = []
    valid_from, valid_to = _extract_valid_dates(text)

    with pdfplumber.open(pdf_path) as pdf:
        page_tables = pdf.pages[0].extract_tables()

        # Sea table
        pod_name = port_dict.get("Терминал Врангель")
        pod_city = get_city_port(port_dict.get("Терминал Врангель", "Терминал Врангель")) or "Находка"

        sea_df = pd.DataFrame(page_tables[0][1:], columns=page_tables[0][0])
        for idx, row in sea_df.iterrows():
            pol = _normalize_pol_name(str(row.iloc[0]).strip())
            pol_country = get_country(pol) or "Азия"
            p20 = _parse_price(row.iloc[2])
            p40 = _parse_price(row.iloc[3])

            for p, ct in [(p20, "20DC"), (p40, "40HC")]:
                if p:
                    results.append(TariffSegment(
                        transport_type="sea", start_point=f"{pol}, {pol_country}",
                        end_point=f"{pod_name}, Россия", container_type=ct, cost=p,
                        currency="USD", company=_COMPANY, container_ownership="SOC",
                        port_service_term="FILO", valid_from=valid_from, valid_to=valid_to,
                        parent_start_location=pol, parent_start_location_type="city",
                        parent_end_location=pod_city, parent_end_location_type="city",
                        start_location_type="port", end_location_type="port",
                        weight_limit=container_size_dict.get(ct),
                    ).to_dict())

        # Rail tables - на разных страницах
        for page_num in range(len(pdf.pages)):
            tables = pdf.pages[page_num].extract_tables()
            if page_num == 0 and tables and len(tables) > 1:
                tables = tables[1:]  # Skip sea table on page 0

            if not tables:
                continue

            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Skip non-rail tables - check header for "Станция"
                header = table[0]
                if not any("Станция" in str(h) for h in header):
                    continue

                rail_df = pd.DataFrame(table[1:], columns=table[0])
                for idx, row in rail_df.iterrows():
                    station_raw = _safe_str(row.iloc[1]) if len(row) > 1 else ""
                    if not station_raw or "Станция" in station_raw:
                        continue

                    # Remove parenthetical notes first
                    if "(" in station_raw:
                        station_raw = station_raw.split("(")[0].strip()

                    # Extract station name
                    if ":" in station_raw:
                        station = station_raw.split(":")[1].strip()
                    elif "," in station_raw:
                        station = station_raw.split(",")[1].strip()
                    else:
                        station = station_raw.strip()
                    if " -" in station:
                        station = station.split(" -")[0].strip()
                    city = get_city_station(station)

                    p20_24 = _parse_price(row.iloc[2]) if len(row) > 2 else None
                    p20_28 = _parse_price(row.iloc[3]) if len(row) > 3 else None
                    p40 = _parse_price(row.iloc[5]) if len(row) > 5 else None

                    for p, w_min, w_max, ct in [(p20_24, None, 24, "20DC"), (p20_28, 24, 28, "20DC"), (p40, None, 28, "40HC")]:
                        if p:
                            rail_pod_name = port_dict.get("Терминал Врангель")
                            rail_pod_city = get_city_port(port_dict.get("Терминал Врангель")) or "Находка"
                            results.append(TariffSegment(
                                transport_type="rail", start_point=f"{rail_pod_name}, Россия",
                                end_point=f"{station}, Россия", container_type=ct, cost=p,
                                currency="RUB", company=_COMPANY, container_ownership="SOC",
                                valid_from=valid_from, valid_to=valid_to,
                                parent_start_location=rail_pod_city, parent_start_location_type="city",
                                parent_end_location=city, parent_end_location_type="city",
                                start_location_type="port", end_location_type="rail_station",
                                weight_limit=container_size_dict.get(ct),
                                min_weight_kg=w_min, max_weight_kg=w_max,
                            ).to_dict())

    return results


def detect_file_type(text: str) -> str:
    """Определяет тип файла по содержанию."""
    # Check for station-based routes first
    if "Станция назначения" in text:
        if "через ВМРП" in text:
            return "vmrp_stations"
        elif "Терминал Врангель" in text:
            return "coc_vrangle_stations"
        else:
            return "vrangle_stations"
    # Otherwise check for Moscow-only routes
    elif "FOR Москва" in text and "FOT Москва" in text:
        return "moscow_only"
    return "unknown"


def parse(file_path: str) -> list[TariffSegment]:
    """Автоматическое определение типа файла и парсинг."""
    file_path = str(file_path)

    with pdfplumber.open(file_path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    file_type = detect_file_type(text)

    if file_type == "moscow_only":
        results = parse_type1_moscow_only(file_path, text)
    elif file_type == "coc_vrangle_stations":
        results = parse_type2_coc_stations(file_path, text)
    elif file_type == "vmrp_stations":
        results = parse_type3_vmrp_stations(file_path, text)
    elif file_type == "vrangle_stations":
        results = parse_type4_vrangle_stations(file_path, text)
    else:
        results = []

    return _to_segments(results)
