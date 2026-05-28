"""Парсер «Логопер» — PDF интермодальные тарифы CY-FOR."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import (
    port_dict,
    country_dict,
    port_city_dict,
    container_size_dict,
    get_city_port,
)

_COMPANY = "Логопер"

# Маппинг английских названий стран из PDF
_COUNTRY_MAP = {
    "China": "Китай",
    "Korea": "Корея",
    "Vietnam": "Вьетнам",
    "Taiwan": "Тайвань",
    "Thailand": "Таиланд",
    "Malaysia": "Малайзия",
    "Indonesia": "Индонезия",
    "Japan": "Япония",
    "India": "Индия",
}


# Маппинг терминалов назначения ЖД в (rail_station, parent_city)
# rail_station — полное название терминала для end_point
# parent_city — город для parent_end
_RAIL_DEST_TERMINAL_MAP = {
    "Электроугли": ("Электроугли", "Москва"),
    "Сибирский": ("Сибирская", "Новосибирск"),
    "ОТК": ("Среднеуральск", "Екатеринбург"),
    "Уральский": ("Аппаратная", "Екатеринбург"),
    "ВОСХОД": ("Шушары", "Санкт-Петербург"),
    "ЕТТ": ("Аппаратная", "Екатеринбург"),
    "ОТТ": ("Екатеринбург-Товарный", "Екатеринбург"),
    "НТТ": ("Сибирская", "Новосибирск"),
    "ЦТ": ("Екатеринбург-Товарный", "Екатеринбург"),
    "СЕВЕРНЫЙ": ("Среднеуральск", "Екатеринбург"),
}

def _resolve_rail_dest_terminal(cell_text: str) -> list[tuple[str, str]]:
    """Извлекает из ячейки PDF известные терминалы назначения.
    Возвращает список (rail_station, parent_city) для каждого найденного.
    """
    results = []
    for key, (station, city) in _RAIL_DEST_TERMINAL_MAP.items():
        if key in cell_text:
            results.append((station, city))
    return results


def _price(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace("\u00a0", "").replace(" ", "")
    s = s.replace("$", "").replace(",", "").replace("руб.", "")
    if not s or s.lower() in ("n/a", "‐", "-", "0"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_valid_from(text: str) -> str | None:
    m = re.search(r"с\s*(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def _translate_port(port_en: str) -> str:
    """Переводит название порта через shared.port_dict."""
    cleaned = port_en.replace("**", "").replace("*", "")

    # Точное совпадение
    if cleaned in port_dict:
        return port_dict[cleaned]

    # Совпадение без учёта регистра
    for key, val in port_dict.items():
        if key.lower() == cleaned.lower():
            return val

    # Совпадение с пробелами: PortKlang → Port Klang
    for key, val in port_dict.items():
        key_no_space = key.replace(" ", "")
        if key_no_space.lower() == cleaned.lower():
            return val

    # Локальный fallback для японских портов (нет в shared.py)
    local_ports = {
        "Osaka": "Осака",
        "Tokyo": "Токио",
        "Yokohama": "Иокогама",
        "Nagoya": "Нагоя",
        "Kawasaki": "Кавасаки",
        "Toyama": "Тояма",
        "Hakata": "Хаката",
        "Niigata": "Ниигата",
        "Tomakomai": "Томакомай",
        "Shimizu": "Симидзу",
        "Kobe": "Кобе",
        "Chiba": "Тиба",
    }
    if cleaned in local_ports:
        return local_ports[cleaned]

    return port_en


def _get_parent_city_for_terminal(terminal_: str) -> str | None:
    """Определяет родительский город для терминала через shared.port_city_dict."""
    terminal = get_city_port(terminal_)
    if terminal:
        return terminal
    # Специальные случаи
    if "Врангель" in terminal_ or "Терминал Врангель" in terminal_:
        return "Находка"
    if "ПЛ" in terminal_ or "Pacific" in terminal_:
        return "Владивосток"
    if "ВМПП" in terminal_:
        return "Владивосток"
    return None


def _make_segment(
    *,
    transport_type: str,
    start_point: str,
    end_point: str,
    container_type: str,
    cost: float,
    currency: str,
    container_ownership: str | None = None,
    min_weight_kg: int | None = None,
    max_weight_kg: int | None = None,
    port_service_term: str | None = None,
    conditions: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    parent_start_location: str | None = None,
    parent_start_location_type: str | None = None,
    parent_end_location: str | None = None,
    parent_end_location_type: str | None = None,
    start_location_type: str | None = None,
    end_location_type: str | None = None,
    weight_limit: str | None = None,
    dropoff_location: str | None = None,
    dropoff_location_type: str | None = None,
    dropoff_location_country: str | None = None,
) -> dict:
    return TariffSegment(
        transport_type=transport_type,
        start_point=start_point,
        end_point=end_point,
        container_type=container_type,
        cost=cost,
        currency=currency,
        company=_COMPANY,
        container_ownership=container_ownership,
        port_service_term=port_service_term,
        conditions=conditions,
        valid_from=valid_from,
        valid_to=valid_to,
        start_location_type=start_location_type,
        end_location_type=end_location_type,
        parent_start_location=parent_start_location,
        parent_start_location_type=parent_start_location_type,
        parent_end_location=parent_end_location,
        parent_end_location_type=parent_end_location_type,
        weight_limit=weight_limit,
        dropoff_location=dropoff_location,
        dropoff_location_type=dropoff_location_type,
        dropoff_location_country=dropoff_location_country,
    ).to_dict()


def _parse_ports(port_str: str) -> list[str]:
    """Разбивает строку портов на список."""
    raw = port_str.replace("**", "").replace("*", "")
    # Убираем Dropoff-суффиксы вида "(DropoffVladivostok,Nakhodka)" или "(Drop off Vladivostok, Nakhodka)"
    raw = re.sub(r"\(Drop\s*off[^)]*\)", "", raw, flags=re.IGNORECASE)
    parts = raw.split("/")
    result = []
    for p in parts:
        p = p.strip().rstrip(")").lstrip("(")
        if not p:
            continue
        if "(" in p:
            main = p.split("(")[0].strip()
            variant = p.split("(")[1].rstrip(")").strip()
            if main:
                result.append(main)
            if variant:
                result.append(variant)
        else:
            result.append(p)
    return result


_DROP_OFF_CITY_MAP = {
    "Vladivostok": "Владивосток",
    "Nakhodka": "Находка",
}


def _extract_dropoff_cities(text: str) -> list[str]:
    """Извлекает города dropoff из текста вида '(DropoffVladivostok,Nakhodka)' или '(Drop off Vladivostok, Nakhodka)'."""
    m = re.search(r"Drop\s*off\s*([A-Za-z,\s]+)", text, flags=re.IGNORECASE)
    if not m:
        return []
    cities_raw = m.group(1).split(",")
    result = []
    for c in cities_raw:
        c = c.strip()
        if c:
            ru = _DROP_OFF_CITY_MAP.get(c, c)
            if ru not in result:
                result.append(ru)
    return result


def _parse_rail_city(cell_text: str) -> str | None:
    """Извлекает город назначения из первой ячейки ЖД-строки через shared.country_dict."""
    for city in country_dict.get("Россия", []):
        if city in cell_text:
            return city
    return None


def _parse_rail_ownership(cell_text: str) -> list[str]:
    if "COC" in cell_text and "SOC" in cell_text:
        return ["COC", "SOC"]
    if "COC" in cell_text:
        return ["COC"]
    if "SOC" in cell_text:
        return ["SOC"]
    return []


def parse_Logoper(file_path: str | Path | None = None) -> list[dict]:
    """Парсит PDF «ИНТЕРМОДАЛЬНЫЕ тарифы ЛОГОПЕР CY-FOR»."""
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = list(data_dir.glob("ИНТЕРМОДАЛЬНЫЕ тарифы ЛОГОПЕР*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF Логопер в директории data/. "
                "Ожидался файл по шаблону: ИНТЕРМОДАЛЬНЫЕ тарифы ЛОГОПЕР*.pdf"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    results: list[dict] = []
    valid_from = None

    with pdfplumber.open(file_path) as pdf:
        # Extract validity from full text
        all_text = ""
        for page in pdf.pages:
            all_text += (page.extract_text() or "") + "\n"
        valid_from = _extract_valid_from(all_text)

        # ── Sea segments: dynamically parse table rows ──
        sea_table = pdf.pages[0].extract_tables()[0]

        last_country = "Китай"
        for row in sea_table[1:]:  # skip header row
            if not row or len(row) < 7:
                continue

            country_raw = row[0]
            ports_raw = row[1]
            dest_raw = row[2]

            if not ports_raw:
                continue

            ports_str = str(ports_raw).replace("\n", " ").strip()
            country_str = str(country_raw).strip() if country_raw else ""
            dest_str = str(dest_raw).strip().replace("\n", " ") if dest_raw else ""

            # Track country from first column
            if country_str and country_str != "None":
                last_country = _COUNTRY_MAP.get(country_str, country_str)
            country = last_country

            # Detect dropoff и извлекаем города
            combined_text = ports_str + " " + dest_str
            is_dropoff = re.search(r"Drop\s*off", combined_text, flags=re.IGNORECASE) is not None
            dropoff_cities = _extract_dropoff_cities(combined_text) if is_dropoff else []

            # Destination terminals — always the same set
            terminals = ["Терминал Врангель", "ВМПП", "ПЛ"]

            # Parse ports
            ports = _parse_ports(ports_str)

            # Read prices dynamically
            prices = {
                "20SOC": _price(row[3]),
                "20COC": _price(row[4]),
                "40SOC": _price(row[5]),
                "40COC": _price(row[6]),
            }

            for port_en in ports:
                port_ru = _translate_port(port_en)
                start_point = f"{port_ru}, {country}"

                # Parent city for start — через shared
                parent_start = get_city_port(port_ru)
                if not parent_start:
                    parent_start = port_ru

                for terminal in terminals:
                    terminal = port_dict.get(terminal, terminal)  # ensure terminal is translated if possible
                    end_point = f"{terminal}, Россия"

                    # Parent city for end — через shared.port_city_dict
                    parent_end = _get_parent_city_for_terminal(terminal)
                    if not parent_end:
                        parent_end = "Владивосток"

                    for key, price in prices.items():
                        if price is None:
                            continue
                        ct = key[:2] + ("DC" if "20" in key else "HC")
                        # Нормализуем container_type
                        if key == "20SOC":
                            ct = "20DC"
                        elif key == "20COC":
                            ct = "20DC"
                        elif key == "40SOC":
                            ct = "40HC"
                        elif key == "40COC":
                            ct = "40HC"

                        own = "SOC" if "SOC" in key else "COC"

                        # Если есть dropoff-города — создаём отдельный сегмент для каждого
                        if dropoff_cities:
                            for city in dropoff_cities:
                                results.append(_make_segment(
                                    transport_type="sea",
                                    start_point=start_point,
                                    end_point=end_point,
                                    container_type=ct,
                                    cost=price,
                                    weight_limit=container_size_dict.get(ct,None),
                                    currency="USD",
                                    container_ownership=own,
                                    port_service_term="FILO",
                                    valid_from=valid_from,
                                    parent_start_location=parent_start,
                                    parent_start_location_type="city",
                                    parent_end_location=parent_end,
                                    parent_end_location_type="city",
                                    start_location_type="port",
                                    end_location_type="port",
                                    dropoff_location=city,
                                    dropoff_location_type="city",
                                    dropoff_location_country="Россия",
                                ))
                        else:
                            results.append(_make_segment(
                                transport_type="sea",
                                start_point=start_point,
                                end_point=end_point,
                                container_type=ct,
                                cost=price,
                                weight_limit=container_size_dict.get(ct,None),
                                currency="USD",
                                container_ownership=own,
                                port_service_term="FILO",
                                valid_from=valid_from,
                                parent_start_location=parent_start,
                                parent_start_location_type="city",
                                parent_end_location=parent_end,
                                parent_end_location_type="city",
                                start_location_type="port",
                                end_location_type="port",
                            ))

        # ── Rail segments: dynamically parse page 1 table ──
        rail_table = pdf.pages[1].extract_tables()[0]

        # Терминалы отправления: Терминал Врангель / ВМПП / ПЛ
        rail_start_terminals = ["Терминал Врангель", "ВМПП", "ПЛ"]

        for row in rail_table[2:]:  # skip 2 header rows
            if not row or len(row) < 8:
                continue

            city_raw = row[0]
            ownership_raw = row[1]
            terminal_raw = row[2]

            if not city_raw:
                continue

            city_text = str(city_raw).replace("\n", " ").strip()
            ownership_text = str(ownership_raw).replace("\n", " ").strip()
            terminal_text = str(terminal_raw).replace("\n", " ").strip()

            # Город назначения — dropoff
            city = _parse_rail_city(city_text)
            if not city:
                continue

            ownerships = _parse_rail_ownership(ownership_text)
            if not ownerships:
                continue

            # Извлекаем известные терминалы назначения из текста ячейки
            dest_mappings = _resolve_rail_dest_terminal(terminal_text)
            if not dest_mappings:
                continue  # пропускаем неизвестные терминалы

            # Read rates dynamically
            rate_20_lt24 = _price(row[3])
            rate_20_gt24 = _price(row[4])
            rate_40_lt28 = _price(row[5])

            # Для каждого терминала отправления
            for start_terminal in rail_start_terminals:
                # Расшифровываем через port_dict: ПЛ → Терминал Pacific Logistic и т.д.
                start_expanded = port_dict.get(start_terminal, start_terminal)
                start_point = f"{start_expanded}, Россия"

                # Parent city для start — через port_city_dict
                parent_start = get_city_port(start_expanded)
                if not parent_start:
                    if "Врангель" in start_terminal:
                        parent_start = "Находка"
                    else:
                        parent_start = "Владивосток"

                # Для каждого терминала назначения
                for rail_station, parent_city in dest_mappings:
                    end_point = f"{rail_station}, Россия"

                    for own in ownerships:
                        if rate_20_lt24 is not None:
                            results.append(_make_segment(
                                transport_type="rail",
                                start_point=start_point,
                                end_point=end_point,
                                container_type="20DC",
                                cost=rate_20_lt24,
                                currency="RUB",
                                container_ownership=own,
                                valid_from=valid_from,
                                parent_start_location=parent_start,
                                parent_start_location_type="city",
                                parent_end_location=parent_city,
                                parent_end_location_type="city",
                                dropoff_location=city,
                                dropoff_location_type="city",
                                dropoff_location_country="Россия",
                                start_location_type="port",
                                end_location_type="rail_station",
                                weight_limit=container_size_dict.get("20DC"),
                                max_weight_kg=24
                            ))

                        if rate_20_gt24 is not None:
                            results.append(_make_segment(
                                transport_type="rail",
                                start_point=start_point,
                                end_point=end_point,
                                container_type="20DC",
                                cost=rate_20_gt24,
                                currency="RUB",
                                container_ownership=own,
                                valid_from=valid_from,
                                parent_start_location=parent_start,
                                parent_start_location_type="city",
                                parent_end_location=parent_city,
                                parent_end_location_type="city",
                                dropoff_location=city,
                                dropoff_location_type="city",
                                dropoff_location_country="Россия",
                                start_location_type="port",
                                end_location_type="rail_station",
                                weight_limit=container_size_dict.get("20DC"),
                                min_weight_kg=24
                            ))

                        if rate_40_lt28 is not None:
                            results.append(_make_segment(
                                transport_type="rail",
                                start_point=start_point,
                                end_point=end_point,
                                container_type="40HC",
                                cost=rate_40_lt28,
                                currency="RUB",
                                container_ownership=own,
                                valid_from=valid_from,
                                parent_start_location=parent_start,
                                parent_start_location_type="city",
                                parent_end_location=parent_city,
                                parent_end_location_type="city",
                                dropoff_location=city,
                                dropoff_location_type="city",
                                dropoff_location_country="Россия",
                                start_location_type="port",
                                end_location_type="rail_station",
                                weight_limit=container_size_dict.get("40HC"),
                                max_weight_kg=28
                            ))

    return results


def parse(*args, **kwargs) -> list:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_Logoper(*args, **kwargs))
