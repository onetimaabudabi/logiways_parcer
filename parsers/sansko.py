"""Парсер ООО «Санско Рус Контейнер Лайн» (ТК Санско).

Структура файла:
  Стр.1 — Морской фрахт COC (POL → ВМТП/ВМРП/ПЛ/ВМПП, drop-off Москва/Новосибирск включён)
  Стр.2 — Морской фрахт SOC (POL → ВМТП/ВМРП/ПЛ/ВМПП)
  Стр.3 — ЖД (ВМТП/ВМРП/ПЛ/ВМПП → Москва/Новосибирск) + Авто (станции → склад получателя)

Особенности:
  - pdfplumber извлекает только заголовочные строки таблиц; данные берём из extract_text()
  - Цены в европейском формате: $1 850,00 и 175 000,00 ₽
"""
from __future__ import annotations

import re
from typing import Optional

import pdfplumber

from .models import TariffSegment
from shared import get_country, port_dict, container_size_dict

_COMPANY = "Sunsko"
_VLAD = "Владивосток"
_MSK_STATIONS = ["Раменское", "Селятино", "Купавна", "Электроугли", "Белый Раст", "Чехов", "Люберцы-2", "Ховрино"]
_NSK_STATIONS = ["Клещиха", "Иня-восточная"]

# city → (station_string, city_label) для ЖД секции
_RAIL_DESTS = {
    "Москва": (_MSK_STATIONS, "Москва"),
    "Новосибирск": (_NSK_STATIONS, "Новосибирск"),
}
# Строка морских данных: «POL  T/S  $x,xx  $x,xx  [$x,xx  $x,xx]»
# T/S — только «direct» или «Busan»; цены в формате "$1 850,00".
# Используем [ \t] вместо \s в классе POL — иначе regex пересекает строки
# и заголовки-страны ("Vietnam\nHo Chi Minh") сливаются с портами.
_SEA_ROW_4 = re.compile(
    r"^([\w][\w \t/\-]+?)[ \t]+(direct|Busan)[ \t]+"
    r"\$[ \t]*([\d ]+,\d{2})[ \t]+"
    r"\$[ \t]*([\d ]+,\d{2})[ \t]+"
    r"\$[ \t]*([\d ]+,\d{2})[ \t]+"
    r"\$[ \t]*([\d ]+,\d{2})",
    re.IGNORECASE | re.MULTILINE,
)
_SEA_ROW_2 = re.compile(
    r"^([\w][\w \t/\-]+?)[ \t]+(direct|Busan)[ \t]+"
    r"\$[ \t]*([\d ]+,\d{2})[ \t]+"
    r"\$[ \t]*([\d ]+,\d{2})",
    re.IGNORECASE | re.MULTILINE,
)
_RUB_PRICE = re.compile(r"([\d ]+,\d{2})\s*₽")


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def _valid_dates(text: str) -> tuple[Optional[str], Optional[str]]:
    # «с 16.05.2026 по 31.05.2026»
    m = re.search(
        r"(\d{2})\.(\d{2})\.(\d{4})\s+по\s+(\d{2})\.(\d{2})\.(\d{4})", text
    )
    if m:
        d1, mo1, y1, d2, mo2, y2 = m.groups()
        return f"{y1}-{mo1}-{d1}", f"{y2}-{mo2}-{d2}"
    # фолбэк: любые две даты через дефис/тире
    m = re.search(
        r"(\d{2})\.(\d{2})\.(\d{4})\s*[–—\-]{1,2}\s*(\d{2})\.(\d{2})\.(\d{4})", text
    )
    if m:
        d1, mo1, y1, d2, mo2, y2 = m.groups()
        return f"{y1}-{mo1}-{d1}", f"{y2}-{mo2}-{d2}"
    return None, None


def _eur(token: str) -> Optional[float]:
    """'1 850,00' → 1850.0; '175 000,00' → 175000.0"""
    s = re.sub(r"\s", "", token.strip()).replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _norm_pol(raw: str) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    first = re.split(r"/", name)[0].strip()
    return port_dict.get(first, first)


def _norm_ts(raw: str) -> Optional[str]:
    s = str(raw).strip()
    if not s or s.lower() in ("direct", "прямой", "-"):
        return None
    return port_dict.get(s, s)


def _geo(name: str, fallback_country: str = "") -> str:
    country = get_country(name) or fallback_country
    return f"{name}, {country}" if country else name


def _section(text: str, start: str, end: str) -> str:
    """Вырезает подстроку между двумя маркерами."""
    s = text.find(start)
    if s == -1:
        return ""
    s += len(start)
    e = text.find(end, s)
    return text[s:e] if e != -1 else text[s:]


# ---------------------------------------------------------------------------
# Парсинг секций
# ---------------------------------------------------------------------------

def _parse_coc(page_text: str, vf: Optional[str], vt: Optional[str]) -> list[TariffSegment]:
    """Стр.1 — COC: POL → Владивосток, drop-off Москва/Новосибирск в ставке."""
    segs = []
    for m in _SEA_ROW_4.finditer(page_text):
        pol = _norm_pol(m.group(1))
        ts = _norm_ts(m.group(2))
        prices = [_eur(m.group(i)) for i in (3, 4, 5, 6)]

        for (ct, dest), cost in zip(
            [
                ("20DC", "Москва"),
                ("40HC", "Москва"),
                ("20DC", "Новосибирск"),
                ("40HC", "Новосибирск"),
            ],
            prices,
        ):
            if cost is None:
                continue
            segs.append(
                TariffSegment(
                    transport_type="sea",
                    start_point=_geo(pol),
                    end_point=_geo(_VLAD, "Россия"),
                    container_type=ct,
                    container_ownership="COC",
                    dropoff_location=dest,
                    dropoff_location_type="city",
                    weight_limit=float(container_size_dict.get(ct, 0)) or None,
                    max_weight_kg=float(container_size_dict.get(ct, 0)) or None,
                    cost=cost,
                    currency="USD",
                    stopovers_location=ts,
                    stopovers_location_type="port" if ts else None,
                    stopovers_location_country=get_country(ts) if ts else None,
                    parent_stopovers_location=ts,
                    parent_stopovers_location_type="city" if ts else None,
                    start_location_type="port",
                    parent_start_location=pol,
                    parent_start_location_type="city",
                    end_location_type="port",
                    parent_end_location=_VLAD,
                    parent_end_location_type="city",
                    company=_COMPANY,
                    valid_from=vf,
                    valid_to=vt,
                )
            )
    return segs


def _parse_soc(page_text: str, vf: Optional[str], vt: Optional[str]) -> list[TariffSegment]:
    """Стр.2 — SOC: POL → Владивосток."""
    segs = []
    for m in _SEA_ROW_2.finditer(page_text):
        pol = _norm_pol(m.group(1))
        ts = _norm_ts(m.group(2))
        for ct, idx in (("20DC", 3), ("40HC", 4)):
            cost = _eur(m.group(idx))
            if cost is None:
                continue
            segs.append(
                TariffSegment(
                    transport_type="sea",
                    start_point=_geo(pol),
                    end_point=_geo(_VLAD, "Россия"),
                    container_type=ct,
                    container_ownership="SOC",
                    weight_limit=float(container_size_dict.get(ct, 0)) or None,
                    max_weight_kg=float(container_size_dict.get(ct, 0)) or None,
                    cost=cost,
                    currency="USD",
                    stopovers_location=ts,
                    stopovers_location_type="port" if ts else None,
                    stopovers_location_country=get_country(ts) if ts else None,
                    parent_stopovers_location=ts,
                    parent_stopovers_location_type="city" if ts else None,
                    start_location_type="port",
                    parent_start_location=pol,
                    parent_start_location_type="city",
                    end_location_type="port",
                    parent_end_location=_VLAD,
                    parent_end_location_type="city",
                    company=_COMPANY,
                    valid_from=vf,
                    valid_to=vt,
                )
            )
    return segs


def _parse_rail(section_text: str, vf: Optional[str], vt: Optional[str]) -> list[TariffSegment]:
    """Стр.3 — ЖД: Владивосток → станции Москвы/Новосибирска."""
    segs = []
    for city_marker, (stations, city_label) in _RAIL_DESTS.items():
        pos = section_text.find(city_marker)
        if pos == -1:
            continue
        prices = _RUB_PRICE.findall(section_text[pos:])[:3]
        if len(prices) < 3:
            continue
        for (ct, min_t, max_t), price_str in zip(
            [("20DC", None, 24), ("20DC", 24, 28), ("40HC", None, 28)],
            prices,
        ):
            cost = _eur(price_str)
            if cost is None:
                continue
            for station in stations:
                segs.append(
                    TariffSegment(
                        transport_type="rail",
                        start_point=_geo(_VLAD, "Россия"),
                        end_point=_geo(station, "Россия"),
                        container_type=ct,
                        cost=cost,
                        currency="RUB",
                        min_weight_kg=min_t,
                        max_weight_kg=max_t,
                        weight_limit=max_t,
                        start_location_type="port",
                        parent_start_location=_VLAD,
                        parent_start_location_type="city",
                        end_location_type="rail_station",
                        parent_end_location=city_label,
                        parent_end_location_type="city",
                        company=_COMPANY,
                        valid_from=vf,
                        valid_to=vt,
                    )
                )
    return segs


# ---------------------------------------------------------------------------
# Основная точка входа
# ---------------------------------------------------------------------------

def parse(file_path: str) -> list[TariffSegment]:
    """Разбирает PDF тарифов Санско и возвращает список TariffSegment."""
    with pdfplumber.open(file_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]

    full_text = "\n".join(pages)
    vf, vt = _valid_dates(full_text)

    segs: list[TariffSegment] = []

    # Страница 1: COC
    if pages:
        segs += _parse_coc(pages[0], vf, vt)

    # Страница 2: SOC
    if len(pages) > 1:
        segs += _parse_soc(pages[1], vf, vt)

    # Страница 3: ЖД + Авто
    if len(pages) > 2:
        p3 = pages[2]
        rail_text = _section(p3, "Станция назначения 20DC", "Тариф ЖД")
        segs += _parse_rail(rail_text, vf, vt)

    return segs
