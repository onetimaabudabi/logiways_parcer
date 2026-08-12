"""Парсер «Ametist Line» — фрахтовые ставки (LIFO/FIFO) и THC.

Файл: data/Июль-Август 2026.pdf

Структура PDF (2 страницы, стр. 1 — июль, стр. 2 — август):
каждая страница разбита на блоки «Service: Novorossiysk-<порт>-Novorossiysk»,
в каждом блоке:
  * слева  — таблица «EXPORT NOVO-<ПОРТ>»   (условия LIFO)
  * справа — таблица «IMPORT <ПОРТ>-NOVO»   (условия FIFO)
  * ниже   — таблицы «THC Rates» (DTHC/OTHC по портам)
  * сноски с «validity: 01-31/08/2026»

Колонки ставок: LIFO | LIFO (IMO) | LIFO (SOC) | LIFO (SOC-IMO)
    без пометки SOC → контейнер линии (COC), с пометкой IMO → опасный груз.

THC выгружается как услуга (transport_type="service"): маршрута нет,
start_point == end_point == порт оказания услуги.

Цены в PDF «рассыпаны» пробелами ($ 4 70 = 470, 5 9 200 ₽ = 59 200),
поэтому _parse_price оставляет только цифры.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import container_size_dict, get_country, port_dict

_COMPANY = "Ametist Line"

# Типы транспорта
_TT_SEA = "sea"
_TT_SERVICE = "service"

# Все виды тире, встречающиеся в заголовках маршрутов, приводим к обычному дефису
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")

# Типы контейнеров из колонки «Type» таблиц ставок
_CONTAINER_MAP = {
    "20'DV": "20DC",
    "20'DC": "20DC",
    "40'HC": "40HC",
    "40'REEF PLUGGED": "40RF",
    "40'REEF": "40RF",
    "20'TC": "20TC",
    "20'FR IN-GAUGE": "20FR",
    "40'OT IN-GAUGE": "40OT",
}

# Заголовки колонок THC → типы контейнеров.
# «OOG /non standard» отдельного кода не имеет: тариф распространяется
# на негабарит, т.е. на 20'FR и 40'OT из таблицы ставок.
_OOG_TYPES = ("20FR", "40OT")

# Города-«родители» для портов (в port_city_dict их нет).
# Амбарли и Гебзе привязаны к Стамбулу — так же, как в parsers/ametist_line.py.
_PARENT_CITY = {
    "Амбарли": "Стамбул",
    "Гебзе": "Стамбул",
}

# Строки-заголовки внутри таблиц THC, которые не являются названием порта
_THC_SERVICE_ROWS = {"DTHC", "DTHC IMO", "OTHC", "OTHC IMO"}

_SERVICE_RU = {
    "DTHC": "DTHC — терминальный сбор в порту назначения",
    "OTHC": "OTHC — терминальный сбор в порту отправления",
}

_VALIDITY_RE = re.compile(r"validity[:\s]+(\d{2})\s*-\s*(\d{2})\s*/\s*(\d{2})\s*/\s*(\d{4})")


# ─────────────────────────── Вспомогательные функции ───────────────────────────


def _parse_price(val) -> Optional[float]:
    """'1 550' → 1550.0; '$ 4 70' → 470.0; '5 9 200 ₽' → 59200.0; 'n/a' → None."""
    if val is None:
        return None
    s = str(val).replace("\xa0", "").strip()
    if not s or s.lower() in {"n/a", "na", "on request", "-", "–", "—"}:
        return None
    digits = re.sub(r"[^\d]", "", s)
    return float(digits) if digits else None


def _currency(val) -> str:
    """Валюта определяется по символу в ячейке."""
    s = str(val or "")
    if "₽" in s or "RUB" in s.upper():
        return "RUB"
    return "USD"


def _translate_port(raw: str) -> str:
    """Английское название порта → русское через shared.port_dict."""
    raw = re.sub(r"\s*\bport\b\s*", " ", str(raw or ""), flags=re.IGNORECASE).strip()
    raw = re.sub(r"\*+", "", raw).strip()
    for key in (raw, raw.upper(), raw.title()):
        if key in port_dict:
            return port_dict[key]
    return raw


def _point(port_ru: str) -> str:
    """'Амбарли' → 'Амбарли, Турция'."""
    country = get_country(port_ru) or ""
    return f"{port_ru}, {country}".rstrip(", ")


def _parent_city(port_ru: str) -> str:
    return _PARENT_CITY.get(port_ru, port_ru)


def _split_ports(raw: str) -> list[str]:
    """'MERSIN/SANKO' → ['Мерсин', 'Санко']; 'Ambarli/Gebze' → ['Амбарли', 'Гебзе']."""
    parts = [p.strip() for p in str(raw or "").split("/") if p.strip()]
    out: list[str] = []
    for part in parts:
        port_ru = _translate_port(part)
        if port_ru and port_ru not in out:
            out.append(port_ru)
    return out


def _norm(text) -> str:
    """Нормализация ячейки: тире → дефис, схлопывание пробелов."""
    return re.sub(r"\s+", " ", str(text or "").translate(_DASHES)).strip()


# ─────────────────────────── Разбор заголовков ───────────────────────────


def _parse_route_header(cell: str) -> Optional[tuple[str, list[str], list[str]]]:
    """
    'EXPORT NOVO-MERSIN/SANKO' → ('export', ['Новороссийск'], ['Мерсин', 'Санко'])
    'IMPORT ASHDOD/HAIFA-NOVO' → ('import', ['Ашдод', 'Хайфа'], ['Новороссийск'])
    """
    text = _norm(cell).upper()
    m = re.match(r"^(EXPORT|IMPORT)\s+(.+)$", text)
    if not m:
        return None
    direction, route = m.group(1).lower(), m.group(2)

    if direction == "export":
        origin_raw, _, dest_raw = route.partition("-")
    else:
        origin_raw, _, dest_raw = route.rpartition("-")
    if not origin_raw or not dest_raw:
        return None

    origins, dests = _split_ports(origin_raw), _split_ports(dest_raw)
    if not origins or not dests:
        return None
    return direction, origins, dests


def _parse_rate_columns(row: list) -> list[tuple[int, str, bool, str]]:
    """
    Из строки ['Type', 'LIFO', 'LIFO (IMO)', 'LIFO (SOC)', 'LIFO (SOC-IMO)']
    получает [(индекс, ownership, is_imo, port_service_term), ...].
    """
    specs: list[tuple[int, str, bool, str]] = []
    for idx, cell in enumerate(row[1:], start=1):
        header = _norm(cell).upper()
        term = next((t for t in ("LIFO", "FIFO", "LILO", "FILO") if t in header), "")
        if not term:
            continue
        ownership = "SOC" if "SOC" in header else "COC"
        specs.append((idx, ownership, "IMO" in header, term))
    return specs


def _thc_container_types(header: str) -> list[str]:
    """
    "20DC, 20'TC"           → ['20DC', '20TC']
    '40HREF'                → ['40RF']
    'IG/ OOG /non standard' → ['20FR', '40OT']
    """
    text = _norm(header).upper().replace("'", "")
    if not text:
        return []
    if "OOG" in text or "NON STANDARD" in text:
        return list(_OOG_TYPES)

    types: list[str] = []
    for size, kind in re.findall(r"(20|40)\s*(DC|GP|HC|TC|HREF|REEF|RF|FR|OT)", text):
        code = {
            "DC": "DC", "GP": "DC", "HC": "HC", "TC": "TC",
            "HREF": "RF", "REEF": "RF", "RF": "RF", "FR": "FR", "OT": "OT",
        }[kind]
        ct = f"{size}{code}"
        if ct not in types:
            types.append(ct)
    return types


def _parse_validity(text: str) -> tuple[Optional[str], Optional[str]]:
    """'validity: 01-31/08/2026' → ('2026-08-01', '2026-08-31')."""
    m = _VALIDITY_RE.search(_norm(text))
    if not m:
        return None, None
    day_from, day_to, month, year = m.groups()
    return f"{year}-{month}-{day_from}", f"{year}-{month}-{day_to}"


# ─────────────────────────── Разбор таблиц ───────────────────────────


def _parse_rate_table(table: list, valid_from, valid_to) -> list[dict]:
    """Таблица ставок: заголовок маршрута → строка 'Type' → строки контейнеров."""
    results: list[dict] = []
    route: Optional[tuple[str, list[str], list[str]]] = None
    columns: list[tuple[int, str, bool, str]] = []

    for row in table:
        if not row:
            continue
        cell0 = _norm(row[0])
        if not cell0:
            continue

        parsed_route = _parse_route_header(cell0)
        if parsed_route:
            route, columns = parsed_route, []
            continue

        if cell0.lower() == "type":
            columns = _parse_rate_columns(row)
            continue

        container_type = _CONTAINER_MAP.get(cell0.upper())
        if not container_type or not route or not columns:
            continue

        _direction, origins, dests = route
        for idx, ownership, is_imo, term in columns:
            if idx >= len(row):
                continue
            price = _parse_price(row[idx])
            if price is None:
                continue

            for origin in origins:
                for dest in dests:
                    results.append(
                        TariffSegment(
                            transport_type=_TT_SEA,
                            start_point=_point(origin),
                            end_point=_point(dest),
                            container_type=container_type,
                            cost=price,
                            currency="USD",
                            company=_COMPANY,
                            container_ownership=ownership,
                            port_service_term=term,
                            conditions="IMO" if is_imo else None,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            start_location_type="port",
                            end_location_type="port",
                            parent_start_location=_parent_city(origin),
                            parent_start_location_type="city",
                            parent_end_location=_parent_city(dest),
                            parent_end_location_type="city",
                            weight_limit=container_size_dict.get(container_type),
                        ).to_dict()
                    )
    return results


def _parse_thc_table(table: list, valid_from, valid_to) -> list[dict]:
    """Таблица «THC Rates»: строка порта задаёт колонки, строки DTHC/OTHC — цены."""
    results: list[dict] = []
    ports: list[str] = []
    columns: list[tuple[int, str, list[str]]] = []

    for row in table:
        if not row:
            continue
        cell0 = _norm(row[0])
        if not cell0 or cell0.lower() == "thc rates":
            continue

        service = cell0.upper()
        if service not in _THC_SERVICE_ROWS:
            # строка с названием порта и заголовками колонок
            ports = _split_ports(cell0)
            columns = []
            for idx, cell in enumerate(row[1:], start=1):
                types = _thc_container_types(cell)
                if types:
                    columns.append((idx, _norm(cell), types))
            continue

        if not ports or not columns:
            continue

        base = _SERVICE_RU[service.split()[0]]
        is_imo = "IMO" in service

        for idx, label, types in columns:
            if idx >= len(row):
                continue
            price = _parse_price(row[idx])
            if price is None:
                continue
            currency = _currency(row[idx])

            conditions = base
            if is_imo:
                conditions += "; IMO"
            conditions += f"; колонка: {label}"

            for port_ru in ports:
                point = _point(port_ru)
                for container_type in types:
                    results.append(
                        TariffSegment(
                            transport_type=_TT_SERVICE,
                            start_point=point,
                            end_point=point,
                            container_type=container_type,
                            cost=price,
                            currency=currency,
                            company=_COMPANY,
                            conditions=conditions,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            start_location_type="port",
                            end_location_type="port",
                            parent_start_location=_parent_city(port_ru),
                            parent_start_location_type="city",
                            parent_end_location=_parent_city(port_ru),
                            parent_end_location_type="city",
                            weight_limit=container_size_dict.get(container_type),
                        ).to_dict()
                    )
    return results


def _table_text(table: list) -> str:
    return " ".join(_norm(c) for row in table or [] for c in row or [] if c)


def _parse_page(page) -> tuple[list[dict], list[dict]]:
    """Возвращает (ставки, THC) одной страницы."""
    tables = page.find_tables()
    extracted = [(t.bbox[1], t.extract()) for t in tables]

    # Сроки действия: сноска «validity:» стоит ниже своего блока таблиц
    validities: list[tuple[float, tuple[Optional[str], Optional[str]]]] = []
    for top, data in extracted:
        text = _table_text(data)
        if "validity" in text.lower():
            valid = _parse_validity(text)
            if valid[0]:
                validities.append((top, valid))
    validities.sort()

    def validity_for(top: float) -> tuple[Optional[str], Optional[str]]:
        for v_top, valid in validities:
            if v_top >= top - 1:
                return valid
        return validities[-1][1] if validities else (None, None)

    rates: list[dict] = []
    thc: list[dict] = []
    for top, data in extracted:
        if not data:
            continue
        first = _norm(data[0][0] if data[0] else "")
        valid_from, valid_to = validity_for(top)

        if first.lower() == "thc rates":
            thc += _parse_thc_table(data, valid_from, valid_to)
        elif _parse_route_header(first):
            rates += _parse_rate_table(data, valid_from, valid_to)

    return rates, thc


def _dedupe(records: list[dict]) -> list[dict]:
    """THC для Новороссийска повторяется в каждом сервисном блоке — убираем дубли."""
    seen: set[tuple] = set()
    unique: list[dict] = []
    for rec in records:
        key = (
            rec["start_point"], rec["end_point"], rec["container_type"],
            rec["cost"], rec["currency"], rec["conditions"],
            rec["valid_from"], rec["valid_to"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(rec)
    return unique


# ─────────────────────────── Точка входа ───────────────────────────


def _select_period(records: list[dict], on_date: str) -> list[dict]:
    """Оставляет тарифы ровно одного периода — актуального на дату on_date.

    Загрузчик (send_api_New.build_segments_from_excel) ключует тариф кортежем
    (сегмент, container_type, container_ownership, port_service_term) — БЕЗ дат.
    Если отдать июль и август сразу, на сервер уйдёт только первый встретившийся
    период, и августовская ставка станет невидимой в витрине. Поэтому наружу
    отдаём один период: действующий на on_date, иначе ближайший будущий,
    иначе последний истёкший.
    """
    undated = [r for r in records if not r["valid_from"]]
    dated = [r for r in records if r["valid_from"]]
    if not dated:
        return records

    spans = sorted({(r["valid_from"], r["valid_to"]) for r in dated})

    current = [s for s in spans if s[0] <= on_date and (not s[1] or s[1] >= on_date)]
    upcoming = [s for s in spans if s[0] > on_date]
    if current:
        chosen = max(current)          # самый свежий из действующих
    elif upcoming:
        chosen = min(upcoming)         # ближайший будущий
        print(f"[ametist_freight] ВНИМАНИЕ: на {on_date} действующих ставок нет, "
              f"беру ближайший период {chosen[0]}")
    else:
        chosen = max(spans)            # всё истекло — последний известный
        print(f"[ametist_freight] ВНИМАНИЕ: на {on_date} все периоды истекли, "
              f"беру последний {chosen[0]}")

    return undated + [r for r in dated if (r["valid_from"], r["valid_to"]) == chosen]


def _check_period_collisions(records: list[dict]) -> None:
    """Предупреждает, если один ключ тарифа получил несколько сроков действия."""
    periods: dict[tuple, set] = {}
    for r in records:
        key = (
            r["transport_type"], r["start_point"], r["end_point"],
            r["container_type"], r["container_ownership"],
            r["port_service_term"], r["conditions"],
        )
        periods.setdefault(key, set()).add((r["valid_from"], r["valid_to"]))

    clashes = {k: v for k, v in periods.items() if len(v) > 1}
    if clashes:
        key, spans = next(iter(clashes.items()))
        print(f"[ametist_freight] ВНИМАНИЕ: {len(clashes)} ключ(ей) тарифа имеют "
              f"несколько сроков действия — витрина покажет только один. "
              f"Например {key[1]} → {key[2]} {key[3]}: {sorted(spans)}")


def parse_AmetistFreight(
    file_path: str | Path | None = None,
    on_date: str | None = None,
    include_expired: bool = False,
) -> list[dict]:
    """Парсит PDF фрахтовых ставок Ametist Line.

    on_date        — дата в формате YYYY-MM-DD, на которую нужны ставки
                     (по умолчанию сегодня);
    include_expired — True вернёт все периоды из файла, включая истёкшие.
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = sorted(data_dir.glob("*Август*.pdf"))
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF ставок Ametist Line в data/. "
                "Ожидался файл по шаблону: Июль-Август 2026.pdf"
            )
        file_path = matches[0]
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    rates: list[dict] = []
    thc: list[dict] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_rates, page_thc = _parse_page(page)
            rates += page_rates
            thc += page_thc

    thc = _dedupe(thc)
    results = rates + thc

    all_periods = sorted({r["valid_from"] for r in results if r["valid_from"]})
    if not include_expired and results:
        today = on_date or date.today().isoformat()
        before = len(results)
        results = _select_period(results, today)
        dropped = before - len(results)
        if dropped:
            print(f"[ametist_freight] отброшено на {today}: {dropped} сегм. "
                  f"неактуальных периодов (в файле: {', '.join(all_periods)})")

    _check_period_collisions(results)

    rates_out = sum(1 for r in results if r["transport_type"] == _TT_SEA)
    periods = sorted({r["valid_from"] for r in results if r["valid_from"]})
    print(
        f"[ametist_freight] сегментов: {len(results)} "
        f"(ставки: {rates_out}, THC: {len(results) - rates_out}); "
        f"периоды: {', '.join(periods) or '—'}"
    )
    return results


def parse(*args, **kwargs) -> list[TariffSegment]:
    """Точка входа парсера."""
    return _to_segments(parse_AmetistFreight(*args, **kwargs))
