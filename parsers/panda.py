"""Парсер Panda Express Line — морские тарифы Азия ↔ Владивосток/Находка."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import port_dict, container_size_dict, get_country

_COMPANY = "Panda Express Line"

_EN_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}
_RU_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}
_COUNTRY_EN_RU = {
    "China": "Китай", "Korea": "Корея", "Vietnam": "Вьетнам",
    "Taiwan": "Тайвань", "Thailand": "Таиланд", "Malaysia": "Малайзия",
    "Indonesia": "Индонезия", "Japan": "Япония", "India": "Индия",
}

# Аббревиатуры российских портов из PDF Panda: (имя_порта_ru, город_ru)
_RU_PORT_MAP = {
    "VMPP": ("Владивостокский морской порт «Первомайский»", "Владивосток"),
    "PL": ("Терминал Пасифик Лоджистик", "Владивосток"),
    "Vrangel": ("Терминал Врангель", "Находка"),
    "Terminal Vrangel": ("Терминал Врангель", "Находка"),
    "Nakhodka": ("Терминал Врангель", "Находка"),
}

# Порты по умолчанию для направления Азия→Россия (если POD не распознан)
_DEFAULT_RU_PODS = [
    ("Владивостокский морской порт «Первомайский»", "Владивосток"),
    ("Терминал Пасифик Лоджистик", "Владивосток"),
    ("Терминал Врангель", "Находка"),
]


def _parse_price(val) -> Optional[float]:
    if val is None:
        return None
    s = re.sub(r"[^\d]", "", str(val).replace("\xa0", ""))
    return float(s) if s else None


def _translate_port(raw: str) -> str:
    """Переводит английское название порта в русское через shared.port_dict."""
    raw = re.sub(r"\*+", "", raw).strip()
    if raw in port_dict:
        return port_dict[raw]
    # Убираем уточнение в скобках: "Shenzhen (Yantian)" → "Shenzhen"
    base = re.sub(r"\s*\(.*?\)", "", raw).strip()
    if base in port_dict:
        return port_dict[base]
    return raw


def _split_ports(raw: str) -> list[str]:
    """Разбивает строку портов, разделённых / или переносами строк."""
    normalized = raw.replace("\n", " / ")
    return [p.strip() for p in normalized.split("/") if p.strip()]


def _parse_col_header(header: str) -> Optional[tuple[str, str, str]]:
    """
    Из заголовка колонки извлекает (container_type, ownership, service_term).
    Пример: '20 SOC\\nFILO' → ('20DC', 'SOC', 'FILO')
    """
    h = header.replace("\n", " ").upper().strip()
    h_nospace = h.replace(" ", "")
    if "20DC" in h:
        ct = "20DC"
    elif "20" in h:
        ct = "20DC"
    elif "40HC" in h or "40HQ" in h:
        ct = "40HC"
    elif "40" in h:
        ct = "40HC"
    else:
        return None
    ownership = "SOC" if "SOC" in h else ("COC" if "COC" in h else None)
    if not ownership:
        return None
    service_term = next((t for t in ("FILO", "FIFO", "LIFO", "LILO") if t in h or t in h_nospace), "")
    return (ct, ownership, service_term)


def _extract_doc_year(text: str) -> str:
    # (?<!\d) исключает "9110" из "129110 г. Москва"
    m = re.search(r"(?<!\d)(\d{4})\s*г\.", text)
    return m.group(1) if m else str(datetime.now().year)


def _extract_valid_from_en(text: str, doc_year: str) -> Optional[str]:
    """Извлекает дату начала из английского текста: 'valid from 1st April'."""
    m = re.search(r"valid from\s+(\d+)(?:st|nd|rd|th)?\s+(\w+)", text, re.IGNORECASE)
    if m:
        month = _EN_MONTHS.get(m.group(2).lower())
        if month:
            return f"{doc_year}-{month}-{m.group(1).zfill(2)}"
    return None


def _extract_valid_from_ru(text: str) -> Optional[str]:
    """Извлекает дату из русского текста: '1 февраля 2026 г.'"""
    m = re.search(
        r"(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
        r"\s+(\d{4})\s+г\.",
        text,
    )
    if m:
        month = _RU_MONTHS.get(m.group(2).lower())
        if month:
            return f"{m.group(3)}-{month}-{m.group(1).zfill(2)}"
    return None


def _resolve_russian_pods(raw: str) -> list[tuple[str, str]]:
    """
    Разбирает поле POD для направления Азия→Россия.
    Пример: 'VMPP / PL /\\nNakhodka —\\nTerminal Vrangel'
    Возвращает список (port_name_ru, city_ru).
    """
    # Нормализуем разделители
    raw = raw.replace("—", "/").replace("–", "/").replace("\n", " / ")
    parts = [p.strip() for p in raw.split("/") if p.strip()]

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for part in parts:
        for key, val in _RU_PORT_MAP.items():
            if key.lower() in part.lower():
                if val[0] not in seen:
                    result.append(val)
                    seen.add(val[0])
                break

    return result if result else _DEFAULT_RU_PODS


def _parse_import_table(pdf_path: str) -> list[dict]:
    """
    Страница 1: тарифы Азия → Владивосток/Находка.
    Колонки: Origin Country | Port of Loading | Port of Discharge | 20 SOC FILO | 20 COC FILO | 40 SOC FILO | 40 COC FILO
    Заголовок двухстрочный: строка 0 содержит "20 SOC", строка 1 содержит "FILO".
    """
    results: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        doc_year = _extract_doc_year(text)
        valid_from = _extract_valid_from_en(text, doc_year)

        tables = page.extract_tables()
        if not tables:
            return results

        table = tables[0]
        if len(table) < 3:
            return results

        # Двухстрочный заголовок: объединяем строки 0 и 1
        row0, row1 = table[0], table[1]
        width = max(len(row0), len(row1))
        combined_header = [
            f"{row0[j] or ''} {row1[j] or ''}".strip() if j < len(row0) and j < len(row1)
            else str((row0[j] if j < len(row0) else row1[j]) or "")
            for j in range(width)
        ]
        col_specs: list[tuple[int, str, str, str]] = []
        for i, h in enumerate(combined_header):
            spec = _parse_col_header(h)
            if spec:
                col_specs.append((i, *spec))

        last_country_ru = ""
        last_pod_ports: list[tuple[str, str]] = []

        for row in table[2:]:
            if not row:
                continue

            country_raw = str(row[0] or "").strip()
            pol_raw = str(row[1] or "").strip() if len(row) > 1 else ""
            pod_raw = str(row[2] or "").strip() if len(row) > 2 else ""

            # Прямая заливка: страна и POD — объединённые ячейки
            if country_raw:
                last_country_ru = _COUNTRY_EN_RU.get(country_raw, country_raw)
            if pod_raw:
                last_pod_ports = _resolve_russian_pods(pod_raw)

            if not pol_raw:
                continue

            pol_names_en = _split_ports(pol_raw)

            for col_idx, ct, ownership, service_term in col_specs:
                if col_idx >= len(row):
                    continue
                price = _parse_price(row[col_idx])
                if not price:
                    continue

                for pol_en in pol_names_en:
                    pol_ru = _translate_port(pol_en)
                    pol_country = get_country(pol_ru) or last_country_ru

                    for pod_name, pod_city in last_pod_ports:
                        results.append(
                            TariffSegment(
                                transport_type="sea",
                                start_point=f"{pol_ru}, {pol_country}",
                                end_point=f"{pod_name}, Россия",
                                container_type=ct,
                                cost=price,
                                currency="USD",
                                company=_COMPANY,
                                container_ownership=ownership,
                                port_service_term=service_term,
                                valid_from=valid_from,
                                start_location_type="port",
                                end_location_type="port",
                                parent_start_location=pol_ru,
                                parent_start_location_type="city",
                                parent_end_location=pod_city,
                                parent_end_location_type="city",
                                weight_limit=container_size_dict.get(ct),
                            ).to_dict()
                        )

    return results


def _find_table(page, min_rows: int = 3) -> Optional[list]:
    """
    Пробует несколько стратегий извлечения таблицы со страницы.
    Возвращает таблицу с наибольшим числом строк или None.
    """
    for strat in (
        None,
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "lines_strict", "horizontal_strategy": "lines_strict"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    ):
        try:
            tables = page.extract_tables(table_settings=strat) if strat else page.extract_tables()
        except Exception:
            continue
        if not tables:
            continue
        candidates = [t for t in tables if len(t) >= min_rows and len(t[0]) >= 4]
        if candidates:
            return max(candidates, key=len)
    return None


def _detect_col_specs(table: list) -> tuple[list, int]:
    """
    Ищет строку заголовка в первых 10 строках таблицы.
    Поддерживает однострочный и двухстрочный заголовок.
    Возвращает (col_specs, первый индекс строки с данными).
    """
    for i in range(min(len(table), 10)):
        row = table[i]
        specs = []
        for j, h in enumerate(row):
            spec = _parse_col_header(str(h or ""))
            if spec:
                specs.append((j, *spec))
        if specs:
            return specs, i + 1

        # Пробуем объединить текущую и следующую строку
        if i + 1 < len(table):
            next_row = table[i + 1]
            width = max(len(row), len(next_row))
            combined = [
                f"{row[j] or ''} {next_row[j] or ''}".strip()
                if j < len(row) and j < len(next_row)
                else str(row[j] if j < len(row) else next_row[j] or "")
                for j in range(width)
            ]
            specs = []
            for j, h in enumerate(combined):
                spec = _parse_col_header(h)
                if spec:
                    specs.append((j, *spec))
            if specs:
                return specs, i + 2

    return [], 0


def _parse_export_table(pdf_path: str) -> list[dict]:
    """
    Тарифы Владивосток/Находка → Азия.
    Ищет страницу по маркеру «LIFO»/«LILO», пробует несколько стратегий извлечения.
    """
    results: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            page_text_nospace = page_text.replace(" ", "")
            if "LIFO" not in page_text_nospace and "LILO" not in page_text_nospace:
                continue

            valid_from = _extract_valid_from_ru(page_text)
            table = _find_table(page)
            if not table:
                continue

            col_specs, start_row = _detect_col_specs(table)
            if not col_specs:
                continue

            # Ищем колонку Port of Transshipment в строках заголовка
            transship_col_idx = -1
            for i in range(min(start_row, len(table))):
                for j, cell in enumerate(table[i] or []):
                    if cell and "transship" in str(cell).lower():
                        transship_col_idx = j
                        break
                if transship_col_idx >= 0:
                    break

            last_pol_raw = ""
            for row in table[start_row:]:
                if not row:
                    continue

                pol_raw = str(row[0] or "").strip()
                pod_raw = str(row[1] or "").strip() if len(row) > 1 else ""

                if pol_raw:
                    last_pol_raw = pol_raw
                if not pod_raw or not last_pol_raw:
                    continue

                pol_info: Optional[tuple[str, str]] = None
                for key, val in _RU_PORT_MAP.items():
                    if key.lower() in last_pol_raw.lower():
                        pol_info = val
                        break
                if not pol_info:
                    continue

                pol_name, pol_city = pol_info
                pod_names_en = _split_ports(pod_raw)

                # Пересадочный порт (одинаков для всех контейнеров в строке)
                transship_raw = ""
                if transship_col_idx >= 0 and transship_col_idx < len(row):
                    transship_raw = str(row[transship_col_idx] or "").strip()
                transship_ru = _translate_port(transship_raw) if transship_raw else None
                transship_country = get_country(transship_ru) if transship_ru else None

                for col_idx, ct, ownership, service_term in col_specs:
                    if col_idx >= len(row):
                        continue
                    price = _parse_price(row[col_idx])
                    if not price:
                        continue

                    for pod_en in pod_names_en:
                        pod_ru = _translate_port(pod_en)
                        pod_country = get_country(pod_ru) or "Китай"

                        results.append(
                            TariffSegment(
                                transport_type="sea",
                                start_point=f"{pol_name}, Россия",
                                end_point=f"{pod_ru}, {pod_country}",
                                container_type=ct,
                                cost=price,
                                currency="USD",
                                company=_COMPANY,
                                container_ownership=ownership,
                                port_service_term=service_term,
                                valid_from=valid_from,
                                valid_to=None,
                                start_location_type="port",
                                end_location_type="port",
                                parent_start_location=pol_city,
                                parent_start_location_type="city",
                                parent_end_location=pod_ru,
                                parent_end_location_type="city",
                                stopovers_location=transship_ru,
                                stopovers_location_type="port" if transship_ru else None,
                                stopovers_location_country=transship_country,
                                parent_stopovers_location=transship_ru,
                                parent_stopovers_location_type="city" if transship_ru else None,
                                weight_limit=container_size_dict.get(ct),
                            ).to_dict()
                        )

            if results:
                break

    return results


def parse(file_path: str) -> list[TariffSegment]:
    """Точка входа: парсит PDF Panda Express Line."""
    results: list[dict] = []
    results += _parse_import_table(str(file_path))
    results += _parse_export_table(str(file_path))
    return _to_segments(results)
