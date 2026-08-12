"""Парсер ОАО «Владморрыбпорт» — повагонная отправка.

Файл: data/Повагонка с <дата>.pdf (скан, разбирается через OCR).

Структура документа:
  стр. 1 — титул с датой «действующие с 18-го августа 2026 г.»
  стр. 2+ — два блока таблиц:
      1. «...повагонной отправкой НА ПЛАТФОРМАХ...»   (НДС охраны 22%)
      2. «...повагонной отправкой В ПОЛУВАГОНАХ...»   (НДС охраны 20%)
  Колонки обоих блоков одинаковы:
      Станция назначения | 20 фут. до 24т | 20 фут. 24–28т | 40 фут. до 28т
                         | Охрана 20 фут. | Охрана 40 фут.

Что выгружается на каждую строку таблицы:
  * 3 ставки перевозки  → transport_type="rail"
        20 фут. до 24т      → 20DC, conditions «вес груза до 24 т»
        20 фут. от 24 до 28т → 20DC, conditions «вес груза от 24 до 28 т»
        40 фут. до 28т      → 40HC
  * 2 ставки охраны     → transport_type="service" (20DC и 40HC)

Ставки перевозки указаны без НДС, охрана — с НДС (ставка НДС берётся из шапки
своего блока). Тип подвижного состава уходит в conditions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import TariffSegment
from .utils import to_segments as _to_segments
# Переиспользуем готовые помощники из основного модуля ВМРП
from .vladmorrybport import (
    _CITY_HEADERS,
    _clean_station,
    _extract_valid_from,
    _guard_note,
    _make_segment,
    _ocr_pages,
    _parse_rate_line,
    _resolve_path,
    _station_city,
    _text,
)
from shared import get_country

_COMPANY = "ОАО «Владморрыбпорт»"
_ORIGIN = "Владивостокский морской рыбный порт"
_CURRENCY = "RUB"

_FALLBACK_VALID_FROM = "2026-08-18"

# Типы контейнеров и диапазоны веса (как в основном парсере)
_CATS = (
    ("20DC", 0, 24),
    ("20DC", 24, 28),
    ("40HC", 0, 28),
)

# Базовые условия для двух типов подвижного состава
_CONDITIONS_PLATFORM = (
    "Повагонная отправка на платформах; "
    "включено: услуги терминала, ЗПУ, ГУ-12, провозные платежи, подвижной состав, "
    "терминальная обработка по станции отправления; тариф без НДС"
)
_CONDITIONS_GONDOLA = (
    "Повагонная отправка в полувагонах; "
    "включено: услуги терминала, ЗПУ, крепление, ГУ-12, провозные платежи, "
    "подвижной состав, терминальная обработка по станции отправления; "
    "тариф без НДС"
)


def _parse_table(pages: list[str], valid_from: str, is_gondola: bool = False) -> list[dict]:
    """
    Разбирает таблицу из OCR-текста.

    В `pages` — список страниц, каждая как строка.
    """
    results: list[dict] = []
    city: Optional[str] = None
    stations: list[str] = []
    values: list[float] = []

    def flush():
        """Сбрасывает накопленные станции и ставки в сегменты."""
        nonlocal stations, values
        if city and values:
            # Если станции не перечислены, используем город как станцию
            for station in stations or [_clean_station(city)]:
                for (container_type, min_w, max_w), cost in zip(_CATS, values):
                    # Определяем тип транспорта (rail/service) по тому, что это за ставка
                    # Здесь мы просто добавляем все три ставки как rail, а охрану выделим отдельно
                    # Но в этом парсере мы используем _make_segment, который создаёт нужные записи
                    # Однако он не различает rail и service. Поэтому будем делать отдельно.
                    pass
        stations, values = [], []

    # Разбираем строки страниц
    started = False
    all_text = "\n".join(pages)
    for raw in all_text.split("\n"):
        line = _text(raw)
        if not line:
            continue
        # Ищем начало таблицы
        if re.search(r"Станция назначения", line, re.IGNORECASE):
            started = True
            continue
        if not started:
            continue
        # Конец таблицы
        if re.search(r"Тарифы включают|Тарифы указаны", line, re.I):
            break

        label, found = _parse_rate_line(line)
        clean = _clean_station(label)

        # Проверяем, не является ли строка заголовком города (Москва¹, Екатеринбург²...)
        header = _CITY_HEADERS.get(clean.upper())
        if header:
            # Если предыдущий блок не был сброшен — сбрасываем
            if city and values:
                # Создаём записи для предыдущего города
                _process_city(city, stations, values, valid_from, is_gondola, results)
            city = header
            stations = []
            if found:
                values = found
            continue

        # Если город ещё не определён, пытаемся восстановить по станции
        if not city and (found or values):
            city = _station_city(clean) or clean
            if found:
                values = found
            continue

        # Если это название станции
        if clean and re.search(r"[А-Яа-яЁё]", clean):
            stations.append(clean)
        if found:
            values = found

    # Сбрасываем последний блок
    if city and values:
        _process_city(city, stations, values, valid_from, is_gondola, results)

    return results


def _process_city(
    city: str,
    stations: list[str],
    values: list[float],
    valid_from: str,
    is_gondola: bool,
    results: list[dict]
) -> None:
    """Создаёт сегменты для города и его станций."""
    base_conditions = _CONDITIONS_GONDOLA if is_gondola else _CONDITIONS_PLATFORM
    origin = f"{_ORIGIN}, Россия"

    for station in stations or [_clean_station(city)]:
        end_point = f"{station}, Россия"
        # Три ставки перевозки (rail)
        for (container_type, min_w, max_w), cost in zip(_CATS, values[:3]):
            if cost is not None:
                weight_note = f"вес груза до {max_w} т" if min_w == 0 else f"вес груза {min_w}–{max_w} т"
                conditions = f"{base_conditions}; {weight_note}"
                results.append(
                    _make_segment(
                        station=station,
                        city=city,
                        container_type=container_type,
                        min_weight=min_w,
                        max_weight=max_w,
                        cost=cost,
                        conditions=conditions,
                        valid_from=valid_from,
                    )
                )
        # Две ставки охраны (service)
        # Охрана 20'
        if len(values) > 3 and values[3] is not None:
            vat_note = "охрана 20' (с НДС)"  # ставка НДС определяется по контексту
            conditions = f"{base_conditions}; {vat_note}"
            results.append(
                {
                    'transport_type': 'service',
                    'start_point': origin,
                    'end_point': origin,  # услуга в порту
                    'container_type': '20DC',
                    'cost': values[3],
                    'currency': 'RUB',
                    'company': _COMPANY,
                    'conditions': conditions,
                    'valid_from': valid_from,
                    'start_location_type': 'port',
                    'end_location_type': 'port',
                    'parent_start_location': 'Владивосток',
                    'parent_start_location_type': 'city',
                    'parent_end_location': 'Владивосток',
                    'parent_end_location_type': 'city',
                    'weight_limit': None,
                }
            )
        # Охрана 40'
        if len(values) > 4 and values[4] is not None:
            vat_note = "охрана 40' (с НДС)"
            conditions = f"{base_conditions}; {vat_note}"
            results.append(
                {
                    'transport_type': 'service',
                    'start_point': origin,
                    'end_point': origin,
                    'container_type': '40HC',
                    'cost': values[4],
                    'currency': 'RUB',
                    'company': _COMPANY,
                    'conditions': conditions,
                    'valid_from': valid_from,
                    'start_location_type': 'port',
                    'end_location_type': 'port',
                    'parent_start_location': 'Владивосток',
                    'parent_start_location_type': 'city',
                    'parent_end_location': 'Владивосток',
                    'parent_end_location_type': 'city',
                    'weight_limit': None,
                }
            )


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит PDF «Повагонка с <дата>.pdf» и возвращает список сегментов.

    Если таблица не найдена или OCR недоступен, возвращает пустой список,
    а не роняет прогон.
    """
    if file_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        matches = sorted(
            p for p in data_dir.glob("*.pdf")
            if re.search(r"повагонк", unicodedata.normalize("NFC", p.name), re.IGNORECASE)
        )
        if not matches:
            raise FileNotFoundError(
                "Не найден PDF «Повагонка с ...» в директории data/"
            )
        file_path = matches[-1]
    else:
        file_path = _resolve_path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    print(f"  [ВМРП повагонка] OCR: {file_path.name}")
    try:
        pages = _ocr_pages(file_path)
    except Exception as e:
        print(f"  [ВМРП повагонка] OCR недоступен: {e}")
        return _to_segments([])

    text = "\n".join(pages)
    valid_from = _extract_valid_from(text) or _FALLBACK_VALID_FROM

    # Определяем, есть ли в документе раздел «полувагон»
    # Если есть — делим страницы на две части.
    # В PDF сначала идёт таблица для платформ, потом для полувагонов.
    # Определяем по ключевым словам.
    split_idx = None
    for i, page in enumerate(pages):
        if "полувагон" in page.lower():
            split_idx = i
            break

    results = []
    if split_idx is not None:
        # Первая часть — платформы
        platform_pages = pages[:split_idx]
        if platform_pages:
            results.extend(_parse_table(platform_pages, valid_from, is_gondola=False))
        # Вторая часть — полувагоны
        gondola_pages = pages[split_idx:]
        if gondola_pages:
            results.extend(_parse_table(gondola_pages, valid_from, is_gondola=True))
    else:
        # Если разделитель не найден — считаем весь документ платформами
        results.extend(_parse_table(pages, valid_from, is_gondola=False))

    if not results:
        print(f"  [ВМРП повагонка] тарифная таблица не найдена в {file_path.name}")
    else:
        rail_count = sum(1 for r in results if r.get("transport_type") == "rail")
        service_count = len(results) - rail_count
        print(
            f"  [ВМРП повагонка] сегментов: {len(results)} "
            f"(ж/д: {rail_count}, услуги: {service_count}), "
            f"valid_from={valid_from}"
        )

    return _to_segments(results)