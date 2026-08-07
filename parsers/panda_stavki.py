"""Парсер «Panda Express Line» — прайс `data/stavki.pdf` (сайт pandexline.com).

Структура файла (4 страницы):
    стр. 1 — импорт FILO: страна / порты погрузки / порт выгрузки
             + 4 колонки цен (20 SOC, 20 COC, 40 SOC, 40 COC), USD;
    стр. 2 — «Приоритетное размещение» (надбавка $1000 за рейс) и
             «Условия Drop off для сервиса Port-Port» (сбор за сдачу
             порожнего по городам), USD;
    стр. 3 — экспорт: порт погрузки (VMPP / Врангель / ПЛ) → порты Азии,
             колонки 20DC SOC LIFO, 40HC SOC LIFO, 40HC SOC LILO
             + порт перевалки;
    стр. 4 — примечания.

Порт выгрузки в импортной таблице записан одной ячейкой
«VMPP / PL / Nakhodka — Terminal Врангель»: ставка действует для любого
из трёх терминалов, поэтому создаётся отдельный сегмент на каждый —
иначе морское плечо не состыкуется с железнодорожным из других прайсов.

Отличие от существующего parsers/panda.py: тот разбирает обе тарифные
таблицы (проверено — цены совпадают), но не берёт блок drop off со
страницы 2. Здесь он разбирается тоже.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

import pdfplumber

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import container_size_dict, currency_dict, get_country, port_dict, region_dict

_COMPANY = "Panda Express Line"

# Российские терминалы: в port_dict их англоязычных сокращений нет.
_RU_TERMINALS = {
    "VMPP": ("Владивостокский морской порт «Первомайский»", "Владивосток"),
    "PL": ("Терминал Пасифик Лоджистик", "Владивосток"),
    "NAKHODKA": ("Терминал Врангель", "Находка"),
    "TERMINAL ВРАНГЕЛЬ": ("Терминал Врангель", "Находка"),
    "ВРАНГЕЛЬ": ("Терминал Врангель", "Находка"),
    # В экспортной таблице терминал подписан просто «Vrangel» — без этого
    # ключа второй блок ставок ошибочно приписывался к VMPP.
    "VRANGEL": ("Терминал Врангель", "Находка"),
    "VRANGEL BAY": ("Терминал Врангель", "Находка"),
}

# Написания портов, отличающиеся от ключей shared.port_dict.
# Порт в скобках — терминал внутри города. Берём название города, как это
# делают остальные парсеры проекта (panda.py, khasan_docx.py): в справочнике
# локаций на стенде уже заведены «Гуанчжоу» и «Шэньчжэнь», и терминальные
# имена создали бы дубли. Сам терминал сохраняется в conditions.
_PORT_ALIASES = {
    "TIANJIN (XINGANG)": "Xingang",       # Синганг — самостоятельный порт
    "SHENZHEN (YANTIAN)": "Shenzhen",
    "GUANGZHOU (NANSHA)": "Guangzhou",
}

# Колонки импортной таблицы: (индекс, тип контейнера, принадлежность).
_IMPORT_COLUMNS = [(5, "20DC", "SOC"), (6, "20DC", "COC"),
                   (7, "40HC", "SOC"), (8, "40HC", "COC")]

# Колонки экспортной таблицы: (индекс, тип контейнера, термин).
_EXPORT_COLUMNS = [(2, "20DC", "LIFO"), (3, "40HC", "LIFO"), (4, "40HC", "LILO")]

# Города в таблице «Условия Drop off для сервиса Port-Port» — по порядку колонок.
_DROPOFF_CITIES = ["Москва", "Екатеринбург", "Новосибирск", "Красноярск",
                   "Иркутск", "Омск", "Владивосток", "Находка"]

# ВНИМАНИЕ: в проекте transport_type принимает только sea/rail/auto/truck.
# Drop off — сбор за сдачу порожнего, а не перевозка, поэтому "service"
# (то же значение в ametist_dropoff.py и railtrust_sinokor.py).
_SERVICE_TYPE = "service"

# Страны из колонки Origin Country: в country_dict есть не все порты
# (например, Хаката), поэтому английское название страны переводим здесь.
_COUNTRY_EN_RU = {
    "CHINA": "Китай", "KOREA": "Корея", "VIETNAM": "Вьетнам",
    "TAIWAN": "Тайвань", "THAILAND": "Таиланд", "MALAYSIA": "Малайзия",
    "INDONESIA": "Индонезия", "JAPAN": "Япония", "INDIA": "Индия",
    "HONG KONG": "Гонконг", "SINGAPORE": "Сингапур",
}

_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "мая": 5, "май": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10,
    "ноябр": 11, "декабр": 12,
}


def _text(val) -> str:
    return "" if val is None else re.sub(r"\s+", " ", str(val).replace("\xa0", " ")).strip()


def _parse_price(val) -> Optional[float]:
    """'$1 700' → 1700.0, '-' → None, '$0' → 0.0."""
    s = _text(val)
    if not s or s in ("-", "—", "–"):
        return None
    if not re.search(r"\d", s):
        return None
    digits = re.sub(r"\D", "", s)
    return float(digits) if digits else None


def _translate_port(raw: str) -> Optional[str]:
    """'Shenzhen (Yantian)' → 'Яньтянь'. None, если это не порт."""
    name = re.sub(r"\*+", "", _text(raw)).strip()
    if not name:
        return None
    key = _PORT_ALIASES.get(name.upper(), name)
    for variant in (key, key.title(), key.upper()):
        if variant in port_dict:
            return port_dict[variant]
    # 'Tianjin (Xingang)' без алиаса → пробуем содержимое скобок, затем базу
    inner = re.search(r"\((.+?)\)", name)
    if inner:
        for variant in (inner.group(1).strip(), inner.group(1).strip().title()):
            if variant in port_dict:
                return port_dict[variant]
    base = re.sub(r"\s*\(.*?\)", "", name).strip()
    for variant in (base, base.title()):
        if variant in port_dict:
            return port_dict[variant]
    return None


def _split_ports(raw: str) -> list[str]:
    """'Shanghai / Tianjin (Xingang) / Rizhao* / Qingdao / Ningbo' → 5 портов.

    Слэш внутри скобок разделителем не считается.
    """
    text = _text(raw)
    parts, buf, depth = [], "", 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "/" and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)

    result: list[str] = []
    for part in parts:
        port = _translate_port(part)
        if port and port not in result:
            result.append(port)
    return result


def _split_terminals(raw: str) -> list[tuple[str, str]]:
    """'VMPP / PL / Nakhodka — Terminal Врангель' → три терминала выгрузки."""
    text = _text(raw)
    result: list[tuple[str, str]] = []
    for chunk in re.split(r"\s*[/—–-]\s*", text):
        key = chunk.strip().upper()
        if not key:
            continue
        info = _RU_TERMINALS.get(key)
        if info is None:
            info = next((v for k, v in _RU_TERMINALS.items() if k in key), None)
        if info and info not in result:
            result.append(info)
    return result


def _extract_dates(full_text: str) -> tuple[Optional[str], Optional[str]]:
    """'Дата: 27 июля 2026 г.' → ('2026-07-27', None).

    Срока окончания в прайсе нет: «Срок действия тарифов до последующего
    уведомления», поэтому valid_to остаётся пустым.
    """
    m = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s*г", full_text, re.IGNORECASE)
    if not m:
        return None, None
    stem = m.group(2).lower()
    month = next((v for k, v in _MONTHS.items() if stem.startswith(k)), None)
    if month is None:
        return None, None
    return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}", None


def _make_sea(
    *, start_point: str, start_country: str, start_city: str,
    end_point: str, end_country: str, end_city: str,
    container_type: str, ownership: str, term: str, cost: float,
    conditions: str, valid_from, valid_to,
    stopovers: Optional[str] = None,
) -> dict:
    return TariffSegment(
        transport_type="sea",
        start_point=f"{start_point}, {start_country}".rstrip(", "),
        end_point=f"{end_point}, {end_country}".rstrip(", "),
        container_type=container_type,
        weight_limit=container_size_dict.get(container_type),
        max_weight_kg=int(container_size_dict.get(container_type, 28)),
        cost=cost,
        currency=currency_dict.get("$", "USD"),
        company=_COMPANY,
        container_ownership=ownership,
        port_service_term=term,
        conditions=conditions,
        valid_from=valid_from,
        valid_to=valid_to,
        sequence=1,
        start_location_type="port",
        end_location_type="port",
        parent_start_location=start_city,
        parent_start_location_type="city",
        parent_end_location=end_city,
        parent_end_location_type="city",
        stopovers_location=stopovers,
        stopovers_location_type="port" if stopovers else None,
    ).to_dict()


# ─────────────────────────── Импорт (страница 1) ───────────────────────────


_IMPORT_CONDITIONS = (
    "Импорт FILO из Юго-Восточной Азии через Владивосток и Находку; "
    "не включено: выпуск оригинала коносамента 70 USD, корректировка "
    "документов после CUT OFF, надбавка за опасный груз 500 USD/20', "
    "сбор за отмену и перенос букинга; "
    "drop off: Москва, Екатеринбург, Новосибирск, Омск, Красноярск, "
    "Иркутск, Владивосток, Находка"
)


def _parse_import(table: list, valid_from, valid_to) -> list[dict]:
    results: list[dict] = []
    country = ""
    terminals: list[tuple[str, str]] = []

    for row in table:
        cells = [_text(c) for c in row]
        if len(cells) < 9:
            continue
        if cells[0].lower() in ("origin", "country") or "port of loading" in cells[1].lower():
            continue
        # Примечания в подвале: текст в первой ячейке, цен нет.
        if not any(_parse_price(cells[i]) is not None for i, *_ in _IMPORT_COLUMNS):
            continue

        if cells[0]:
            country = cells[0]
        # Ячейка с терминалами заполнена только в первой строке блока.
        if len(cells) > 2 and cells[2]:
            found = _split_terminals(cells[2])
            if found:
                terminals = found
        if not terminals:
            terminals = [("Владивостокский морской порт «Первомайский»", "Владивосток")]

        for port_ru in _split_ports(cells[1]):
            start_country = (get_country(port_ru)
                             or _COUNTRY_EN_RU.get(country.upper(), country))
            for col, container_type, ownership in _IMPORT_COLUMNS:
                cost = _parse_price(cells[col])
                if cost is None:
                    continue
                for term_name, term_city in terminals:
                    results.append(_make_sea(
                        start_point=port_ru, start_country=start_country,
                        start_city=port_ru, end_point=term_name,
                        end_country="Россия", end_city=term_city,
                        container_type=container_type, ownership=ownership,
                        term="FILO", cost=cost, conditions=_IMPORT_CONDITIONS,
                        valid_from=valid_from, valid_to=valid_to,
                    ))
    return results


# ─────────────────────────── Экспорт (страница 3) ───────────────────────────


_EXPORT_CONDITIONS = (
    "Экспорт из Владивостока и Находки в порты Юго-Восточной Азии; "
    "приём спецоборудования (реф-, танк-контейнеры) по согласованию с портом"
)


def _parse_export(table: list, valid_from, valid_to) -> list[dict]:
    results: list[dict] = []
    origin: Optional[tuple[str, str]] = None

    for row in table:
        cells = [_text(c) for c in row]
        if len(cells) < 5:
            continue
        if "port of loading" in cells[0].lower() or "port of discharge" in cells[1].lower():
            continue
        if not any(_parse_price(cells[i]) is not None for i, *_ in _EXPORT_COLUMNS):
            continue

        # Порт погрузки заполнен только в первой строке блока.
        if cells[0]:
            found = _split_terminals(cells[0])
            if found:
                origin = found[0]
        if origin is None:
            continue

        dest = _translate_port(cells[1])
        if not dest:
            continue
        transship = _translate_port(cells[5]) if len(cells) > 5 else None

        for col, container_type, term in _EXPORT_COLUMNS:
            cost = _parse_price(cells[col])
            if cost is None:
                continue
            results.append(_make_sea(
                start_point=origin[0], start_country="Россия", start_city=origin[1],
                end_point=dest, end_country=get_country(dest) or "",
                end_city=dest, container_type=container_type, ownership="SOC",
                term=term, cost=cost, conditions=_EXPORT_CONDITIONS,
                valid_from=valid_from, valid_to=valid_to, stopovers=transship,
            ))
    return results


# ────────────────────────── Drop off (страница 2) ──────────────────────────


def _parse_dropoff(tables: list, page_text: str, valid_from, valid_to) -> list[dict]:
    """Разбирает оба блока со страницы 2.

    Приоритетное размещение — надбавка за отправку на выбранном рейсе.
    Port-Port — сбор за сдачу порожнего контейнера в городе.
    Таблицы читаются по тексту: в extract_tables колонки съезжают
    (пустые ячейки между значениями), и города не совпадают со ставками.
    """
    results: list[dict] = []

    for line in page_text.split("\n"):
        stripped = _text(line)

        # Блок 1: «Москва $1000 $1000 $1000 $1000»
        m = re.match(r"^([А-ЯЁ][А-Яа-яЁё\- ]+?)\s+((?:\$[\d ]+\s*){4})$", stripped)
        if m:
            city = region_dict.get(m.group(1).strip(), m.group(1).strip())
            amounts = [_parse_price(x) for x in re.findall(r"\$[\d ]+", m.group(2))]
            for (container_type, ownership), cost in zip(
                [("20DC", "SOC"), ("20DC", "COC"), ("40HC", "SOC"), ("40HC", "COC")], amounts
            ):
                if cost is None:
                    continue
                results.append(_make_service(
                    city=city, container_type=container_type, ownership=ownership,
                    cost=cost, valid_from=valid_from, valid_to=valid_to,
                    conditions=(
                        "Приоритетное размещение и отправка на определённом рейсе "
                        "(не менее чем за 7 дней до прихода судна в порт отправления); "
                        "в ставку включена приоритетная выдача контейнера"
                    ),
                ))
            continue

        # Блок 2: «20 СОС $300 $300 $300 - - - $300 -»
        m = re.match(r"^(20|40)\s*[СC]О[СC]\s+(.+)$", stripped)
        if m:
            container_type = "20DC" if m.group(1) == "20" else "40HC"
            tokens = re.findall(r"\$[\d ]+|-", m.group(2))
            for city, token in zip(_DROPOFF_CITIES, tokens):
                cost = _parse_price(token)
                if cost is None:      # прочерк — услуга не оказывается
                    continue
                results.append(_make_service(
                    city=city, container_type=container_type, ownership="SOC",
                    cost=cost, valid_from=valid_from, valid_to=valid_to,
                    conditions="Drop off (сдача порожнего контейнера), сервис Port-Port",
                ))
    return results


def _make_service(*, city: str, container_type: str, ownership: str, cost: float,
                  conditions: str, valid_from, valid_to) -> dict:
    return TariffSegment(
        transport_type=_SERVICE_TYPE,
        start_point="Владивосток, Россия",
        end_point=f"{city}, {get_country(city) or 'Россия'}",
        container_type=container_type,
        weight_limit=container_size_dict.get(container_type),
        cost=cost,
        currency=currency_dict.get("$", "USD"),
        company=_COMPANY,
        container_ownership=ownership,
        conditions=conditions,
        valid_from=valid_from,
        valid_to=valid_to,
        start_location_type="port",
        end_location_type="city",
        parent_start_location="Владивосток",
        parent_start_location_type="city",
        parent_end_location=city,
        parent_end_location_type="city",
        dropoff_location=city,
        dropoff_location_type="city",
        dropoff_location_country=get_country(city) or "Россия",
    ).to_dict()


# ──────────────────────────────── Точка входа ────────────────────────────────


def _resolve_path(file_path: str | Path) -> Path:
    """Находит файл, устойчиво к нормализации Unicode в имени (NFD/NFC)."""
    path = Path(file_path)
    if path.exists():
        return path
    target = unicodedata.normalize("NFC", path.name)
    if path.parent.is_dir():
        for candidate in path.parent.iterdir():
            if unicodedata.normalize("NFC", candidate.name) == target:
                return candidate
    return path


def parse_Panda_stavki(file_path: str | Path | None = None) -> list[dict]:
    """Парсит `stavki.pdf` Panda Express Line и возвращает список сегментов."""
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        candidate = data_dir / "stavki.pdf"
        if not candidate.exists():
            raise FileNotFoundError(
                "Не найден data/stavki.pdf (прайс Panda Express Line)."
            )
        file_path = candidate
    else:
        file_path = _resolve_path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    with pdfplumber.open(file_path) as pdf:
        pages = [(page.extract_text() or "", page.extract_tables()) for page in pdf.pages]

    # Дата документа берётся с первой страницы, где она есть: на странице
    # с блоком drop off своей даты нет, и без этого сегменты уходили
    # с пустым valid_from.
    doc_from = doc_to = None
    for page_text, _ in pages:
        found_from, found_to = _extract_dates(page_text)
        if found_from:
            doc_from, doc_to = found_from, found_to
            break

    results: list[dict] = []
    for page_text, tables in pages:
        valid_from, valid_to = _extract_dates(page_text)
        if not valid_from:
            valid_from, valid_to = doc_from, doc_to
        for table in tables:
            if not table:
                continue
            flat = " ".join(_text(c) for row in table for c in row)
            if "Port of Loading" in flat and "20 SOC" in flat:
                results += _parse_import(table, valid_from, valid_to)
            elif "Port of Discharge" in flat and "LIFO" in flat:
                results += _parse_export(table, valid_from, valid_to)
        if "Drop off" in page_text:
            results += _parse_dropoff(tables, page_text, valid_from, valid_to)

    sea = sum(1 for r in results if r["transport_type"] == "sea")
    print(f"  [Panda stavki] сегментов: {len(results)} "
          f"(море {sea}, drop off {len(results) - sea})")
    return results


def parse(*args, **kwargs) -> list[TariffSegment]:
    """Обёртка для единообразия с другими парсерами."""
    return _to_segments(parse_Panda_stavki(*args, **kwargs))
