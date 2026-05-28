# Парсер ТрансКонтейнер (Китай/Корея/Вьетнам)
import re

import pandas as pd
import pdfplumber

from shared import currency_dict, get_city_station, get_country, port_dict, get_city_port, stations_dist

from .models import TariffSegment


def _normalize_station_name(station_name: str) -> str:
    """Нормализует название станции для корректного поиска"""
    station_name = station_name.strip()
    for key, values in stations_dist.items():
        for value in values:
            if station_name.lower() == value.lower():
                return value
    return station_name


def parse_TransContainer_PDF(file_path: str) -> list[TariffSegment]:
    """Парсит тарифы из PDF файла ТрансКонтейнера (схема SEA+RAIL через Восточный)"""
    segments: list[TariffSegment] = []
    company = "ТрансКонтейнер"

    def _create_segments_for_rate(port_departure_ru, station_destination_ru, rate_20, rate_40):
        """Создает SEA и RAIL сегменты для одной пары порт-станция"""
        results = []
        port_vostochny = "Восточный"
        city_port_departure = get_city_port(port_departure_ru)
        if city_port_departure is None:
            city_port_departure = port_departure_ru

        city_station_destination = get_city_station(station_destination_ru)
        if city_station_destination is None:
            city_station_destination = station_destination_ru

        if rate_20 is not None:
            results.append(
                TariffSegment(
                    transport_type="sea",
                    start_point=port_departure_ru,
                    end_point=port_vostochny,
                    container_type="20DC",
                    weight_limit="24",
                    max_weight_kg="24",
                    cost=rate_20,
                    currency="RUB",
                    company=company,
                    container_ownership="COC",
                    end_location_type="port",
                    start_location_type="port",
                    parent_start_location=city_port_departure,
                    parent_start_location_type="city",
                    parent_end_location="Владивосток",
                    parent_end_location_type="city"
                )
            )
            results.append(
                TariffSegment(
                    transport_type="rail",
                    start_point=port_vostochny,
                    end_point=station_destination_ru,
                    container_type="20DC",
                    weight_limit="24",
                    max_weight_kg="24",
                    cost=rate_20,
                    currency="RUB",
                    company=company,
                    container_ownership="COC",
                    end_location_type="rail_station",
                    start_location_type="port",
                    parent_start_location="Владивосток",
                    parent_start_location_type="city",
                    parent_end_location=city_station_destination,
                    parent_end_location_type="city"
                )
            )

        if rate_40 is not None:
            results.append(
                TariffSegment(
                    transport_type="sea",
                    start_point=port_departure_ru,
                    end_point=port_vostochny,
                    container_type="40HC",
                    weight_limit="30",
                    max_weight_kg="30",
                    cost=rate_40,
                    currency="RUB",
                    company=company,
                    container_ownership="COC",
                    end_location_type="port",
                    start_location_type="port",
                    parent_start_location=city_port_departure,
                    parent_start_location_type="city",
                    parent_end_location="Владивосток",
                    parent_end_location_type="city"
                )
            )
            results.append(
                TariffSegment(
                    transport_type="rail",
                    start_point=port_vostochny,
                    end_point=station_destination_ru,
                    container_type="40HC",
                    weight_limit="30",
                    max_weight_kg="30",
                    cost=rate_40,
                    currency="RUB",
                    company=company,
                    container_ownership="COC",
                    end_location_type="rail_station",
                    start_location_type="port",
                    parent_start_location="Владивосток",
                    parent_start_location_type="city",
                    parent_end_location=city_station_destination,
                    parent_end_location_type="city"
                )
            )

        return results

    try:
        with pdfplumber.open(file_path) as pdf:
            all_rows = []

            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    start_row = 0
                    first_row_text = " ".join(str(h) or "" for h in table[0]).lower()

                    if "порт отправления" in first_row_text or "станция назначения" in first_row_text:
                        start_row = 2
                    else:
                        start_row = 1

                    for row in table[start_row:]:
                        if row and len(row) >= 4:
                            all_rows.append(row)

            current_port = None
            for row in all_rows:
                col0 = str(row[0]).strip() if row[0] else ""
                col1 = str(row[1]).strip() if row[1] else ""
                col2 = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                col3 = str(row[3]).strip() if len(row) > 3 and row[3] else ""

                col0 = re.sub(r'\s+', ' ', col0).strip()
                col1 = re.sub(r'\s+', ' ', col1).strip()

                if not col0 and not col1 and not col2:
                    continue

                if col0 and (not col1 or not col2 or not col3):
                    current_port = col0
                    continue

                port_departure = col0 if col0 else current_port
                station_destination = col1

                if not port_departure or not station_destination:
                    continue

                port_departure_ru = port_dict.get(port_departure, port_departure)
                station_destination_ru = _normalize_station_name(station_destination)

                rate_20 = None
                rate_40 = None

                if col2 and col2 not in ("nan", ""):
                    try:
                        rate_20 = int(col2.replace(" ", "").replace(",", "."))
                    except (ValueError, AttributeError):
                        pass

                if col3 and col3 not in ("nan", ""):
                    try:
                        rate_40 = int(col3.replace(" ", "").replace(",", "."))
                    except (ValueError, AttributeError):
                        pass

                if rate_20 is not None or rate_40 is not None:
                    new_segments = _create_segments_for_rate(port_departure_ru, station_destination_ru, rate_20, rate_40)
                    segments.extend(new_segments)
                    current_port = port_departure

    except Exception as e:
        print(f"Ошибка при парсинге PDF: {e}")

    return segments


def parse_TransContainer(file_path: str) -> list[TariffSegment]:
    xl = pd.ExcelFile(file_path)
    segments: list[TariffSegment] = []
    company = "ТрансКонтейнер"

    def normalize_container(header_text: str) -> str | None:
        text = str(header_text).lower()
        if "40" in text and ("hc" in text or "hq" in text or "40ф" in text):
            return "40HC"
        if ("20" in text and "28" in text) or ("20ф" in text and "28" in text):
            return "20DC_28"
        if "20" in text or "20ф" in text:
            return "20DC"
        return None

    def normalize_port(cell_text: str) -> str:
        text = str(cell_text)
        if "(" in text and ")" in text:
            inside = text[text.find("(") + 1 : text.find(")")].strip()
            if inside:
                return inside
        return text.strip()

    for sheet_name in xl.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_ports_row_idx = None
        header_container_row_idx = None
        sea_rate_row_idx = None

        for i in range(min(len(df), 200)):
            row_vals = df.iloc[i].astype(str).tolist()
            row_join = " ".join([v for v in row_vals if v and v != "nan"]).lower()
            if header_ports_row_idx is None and ("shanghai" in row_join or "шанхай" in row_join):
                header_ports_row_idx = i
                for k in range(1, 6):
                    r = i + k
                    if r >= len(df):
                        break
                    probe = df.iloc[r].astype(str).str.lower().tolist()
                    score = sum(1 for v in probe if ("20" in v or "40" in v or "20ф" in v))
                    if score >= 3:
                        header_container_row_idx = r
                        break
                continue
            if sea_rate_row_idx is None and (
                "ставка до границы рф" in row_join or "ставка до границы" in row_join
            ):
                sea_rate_row_idx = i
                continue

        if header_ports_row_idx is None or header_container_row_idx is None or sea_rate_row_idx is None:
            continue

        col_to_port: dict[int, str] = {}
        col_to_container: dict[int, str] = {}
        ports_row = df.iloc[header_ports_row_idx].tolist()
        containers_row = df.iloc[header_container_row_idx].tolist()
        for col_idx in range(len(ports_row)):
            port_cell = ports_row[col_idx]
            cont_cell = containers_row[col_idx] if col_idx < len(containers_row) else None
            if str(port_cell) != "nan":
                normalized_port = normalize_port(port_cell)
                col_to_port[col_idx] = normalized_port
                col_to_port[col_idx + 1] = normalized_port
                col_to_port[col_idx + 2] = normalized_port
            if str(cont_cell) != "nan":
                cont_norm = normalize_container(cont_cell)
                if cont_norm:
                    col_to_container[col_idx] = cont_norm

        sea_row = df.iloc[sea_rate_row_idx].tolist()
        for col_idx, value in enumerate(sea_row):
            if col_idx not in col_to_port or col_idx not in col_to_container:
                continue
            if pd.isna(value):
                continue
            try:
                tariff = float(value)
            except Exception:
                continue

            container_norm = col_to_container[col_idx]
            weight_limit = (
                "24" if container_norm == "20DC" else ("28" if container_norm == "20DC_28" else "30")
            )
            pol = col_to_port[col_idx] + "/"
            for pol_item in pol.split("/"):
                if not pol_item:
                    continue
                pol_port = port_dict.get(pol_item, pol_item).strip()
                pod_port = port_dict.get("ВМКТ", "ВМКТ").strip()
                segments.append(
                    TariffSegment(
                        transport_type="sea",
                        start_point=f"{pol_port}, {get_country(pol_port)}",
                        end_point=f"{pod_port}, {get_country(pod_port)}",
                        container_type="20DC" if container_norm in ("20DC", "20DC_28") else "40HC",
                        weight_limit=weight_limit,
                        max_weight_kg=weight_limit,
                        cost=tariff,
                        currency=currency_dict.get("$", "$"),
                        company=company,
                        container_ownership="COC",
                        port_service_term="FILO",
                        end_location_type="port",
                        start_location_type="port",
                        parent_start_location=pol_port,
                        parent_start_location_type="city",
                        parent_end_location=get_city_port(pod_port),
                        parent_end_location_type="city" if get_city_port(pod_port) is not None else None
                    )
                )

        pattern = re.compile(
            r"НАЗНАЧЕНИЕМ НА СТАНЦИЮ\s+([А-Яа-яA-Z0-9\- ]+?)(?:\s+в составе КП|\s*\(|$).*?\(входная станция\s+([А-Яа-яA-Za-z0-9\- ]+)"
        )
        for i in range(sea_rate_row_idx + 1, len(df)):
            row = df.iloc[i].tolist()
            first_cell = str(row[0]) if len(row) > 0 else "nan"
            second_cell = str(row[1]) if len(row) > 1 else "nan"
            if first_cell.startswith("НАЗНАЧЕНИЕМ НА СТАНЦИЮ") and "Ставка жд перевозки" in second_cell:
                match = pattern.search(first_cell)
                destination_station = None
                entrance = None
                if match:
                    station_to, station_from = match.groups()
                    destination_station = station_to.title().strip()
                    entrance = station_from.title().strip()

                for col_idx in range(2, len(row)):
                    if col_idx not in col_to_container:
                        continue
                    value = row[col_idx]
                    if pd.isna(value):
                        continue
                    try:
                        tariff = float(value)
                    except Exception:
                        continue

                    container_norm = col_to_container[col_idx]
                    pol_port = port_dict.get("ВМКТ", "ВМКТ")
                    city_station_to = get_city_station(destination_station)
                    city_station_from = get_city_station(entrance)
                    segments.append(
                        TariffSegment(
                            transport_type="rail",
                            start_point=f"{entrance}, {get_country(city_station_from)}",
                            end_point=f"{destination_station}, {get_country(city_station_to)}",
                            container_type="20DC" if container_norm in ("20DC", "20DC_28") else "40HC",
                            weight_limit="24"
                            if container_norm == "20DC"
                            else ("28" if container_norm == "20DC_28" else "30"),
                            cost=tariff,
                            max_weight_kg="24"
                            if container_norm == "20DC"
                            else ("28" if container_norm == "20DC_28" else "30"),
                            currency=currency_dict.get("руб", "руб"),
                            company=company,
                            container_ownership="COC",
                            port_service_term="FILO",
                            end_location_type="rail_station",
                            start_location_type="rail_station",
                            parent_start_location=city_station_from,
                            parent_start_location_type="city" if city_station_from else None,
                            parent_end_location=city_station_to,
                            parent_end_location_type="city" if city_station_to else None
                        )
                    )

    return segments

# _segments_wrapper_for_parse_TransContainer
from .models import TariffSegment
from .utils import to_segments as _to_segments

def _parse_TransContainer_impl(file_path: str) -> list[TariffSegment]:
    """Выбирает нужный парсер в зависимости от расширения файла"""
    if file_path.lower().endswith(".pdf"):
        return parse_TransContainer_PDF(file_path)
    else:
        return parse_TransContainer(file_path)

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_TransContainer_impl(*args, **kwargs))