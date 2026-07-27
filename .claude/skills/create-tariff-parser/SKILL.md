---
name: create-tariff-parser
description: >
  Creates a Python tariff parser for a new transport/logistics company (ТК).
  Use this skill whenever the user provides a tariff file (PDF, Excel/XLSX, DOCX, TXT)
  and wants to extract tariff data from it — even if they don't say "parser" explicitly.
  Triggers: "создай парсер", "напиши парсер", "добавь парсер", "разбери тарифы",
  "распарси файл", "create parser", "parse tariff", "добавь компанию", any mention of
  parsing a logistics/freight/transport company file. When the user uploads or references
  a tariff file and asks to process it — always use this skill.
---

# create-tariff-parser

Автоматически создаёт Python-парсер тарифов для новой транспортной компании.
На вход — один или несколько файлов (PDF/XLSX/DOCX/TXT) одной ТК.
На выход — готовый `parsers/<name>.py`, интегрированный в `main.py`, проверенный через `tariff_analysis_TEST.xlsx`.

---

## Шаг 0 — Прочитай контекст проекта

Перед началом прочитай эти файлы (они дадут тебе всё необходимое):

```
parsers/models.py   — структура TariffSegment (все поля с типами)
shared.py           — словари: port_dict, region_dict, country_dict,
                      container_size_dict, stations_dist, port_city_dict
                      + функции get_country(), get_city_port(), get_city_station()
parsers/panda.py    — эталонный парсер (ОБЯЗАТЕЛЬНО изучи подход)
parsers/utils.py    — to_segments(), segments_to_df()
main.py             — как подключаются парсеры
```

**Ключевые знания из panda.py (чтобы не читать каждый раз):**

```python
# Паттерн парсера
from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import port_dict, container_size_dict, get_country

def _parse_price(val) -> Optional[float]:
    if val is None: return None
    s = re.sub(r"[^\d]", "", str(val).replace("\xa0", ""))
    return float(s) if s else None

def _translate_port(raw: str) -> str:
    raw = re.sub(r"\*+", "", raw).strip()
    if raw in port_dict: return port_dict[raw]
    base = re.sub(r"\s*\(.*?\)", "", raw).strip()
    return port_dict.get(base, raw)

def parse(file_path: str) -> list[TariffSegment]:
    results: list[dict] = []
    results += _parse_something(str(file_path))
    return _to_segments(results)
```

---

## Шаг 1 — Изучи входной файл

Определи формат и прочитай содержимое:

| Формат | Инструмент |
|--------|-----------|
| PDF | `pdfplumber` — `page.extract_text()`, `page.extract_tables()` |
| Excel/XLSX | `pandas` — `pd.read_excel()` или `openpyxl` для сложных случаев |
| DOCX | `python-docx` — `Document(path).tables`, `.paragraphs` |
| TXT/CSV | встроенный `open()` или `csv` |

Извлеки из файла:
- **Название ТК** (заголовок, шапка документа)
- **Маршруты**: откуда → куда (порты, станции, терминалы)
- **Типы контейнеров**: 20DC, 40HC, 20GP, 40GP и т.д.
- **Цены** и **валюту** (USD, RUB, CNY)
- **Даты действия**: "valid from", "действует с/по", "с X по Y"
- **Тип транспорта**: sea (морской), rail (ЖД), truck (авто)
- **Ownership**: SOC (shipper owned) или COC (carrier owned)
- **Service term**: FILO, FIFO, LIFO, LILO
- **Пересадочные порты** (transshipment, via)
- **Время в пути** (transit time, дней)

---

## Шаг 2 — Правила использования shared.py

```python
from shared import port_dict, container_size_dict, get_country, region_dict, port_city_dict
```

**Переводы названий:**
- Английское → русское: `port_dict.get("Shanghai", "Shanghai")` → `"Шанхай"`
- Определить страну: `get_country("Шанхай")` → `"Китай"`
- Весовой лимит: `container_size_dict.get("20DC")` → `"24"`

**Если названия нет в словаре** — сначала добавь его в `shared.py`:
```python
# В port_dict:
"NewPortEn": "НовыйПортРу",
# В country_dict["Китай"]:
"НовыйПортРу",
```

**Типы локаций:**
| Объект | `*_location_type` |
|--------|------------------|
| Морской порт | `"port"` |
| ЖД станция | `"station"` |
| Терминал | `"terminal"` |
| Город (только для parent_*) | `"city"` |

---

## Шаг 3 — Структура TariffSegment

**Обязательные поля** (пустые — ошибка):
```python
transport_type   # "sea" | "rail" | "truck"
start_point      # "Шанхай, Китай"  ← НЕ тип city!
end_point        # "Владивосток, Россия" ← НЕ тип city!
container_type   # "20DC", "40HC", "20GP", "40GP" и т.д.
```

**Важные опциональные поля:**
```python
cost                         # float — числовая цена
currency                     # "USD" | "RUB" | "CNY"
valid_from / valid_to        # "YYYY-MM-DD"
company                      # название ТК
container_ownership          # "SOC" | "COC"
port_service_term            # "FILO" | "FIFO" | "LIFO" | "LILO"
weight_limit                 # container_size_dict.get(ct)

start_location_type          # "port" | "station" | "terminal"
end_location_type            # "port" | "station" | "terminal"
parent_start_location        # родительский город (str)
parent_start_location_type   # "city"
parent_end_location          # родительский город (str)
parent_end_location_type     # "city"

final_destination            # конечный пункт (если есть)
final_destination_location_type  # тип конечного пункта

stopovers_location           # промежуточный порт/пересадка
stopovers_location_type      # "port" | "terminal"
stopovers_location_country   # страна пересадки
parent_stopovers_location    # город пересадки
parent_stopovers_location_type  # "city"

duration_min_days / duration_max_days  # int — время в пути
departures                   # расписание (str)
sequence                     # int — порядковый номер сегмента
```

---

## Шаг 4 — Шаблон парсера

```python
"""Парсер [Company Name] — [краткое описание маршрутов]."""

from __future__ import annotations

import re
from typing import Optional

# Для PDF:
import pdfplumber
# Для Excel:
import pandas as pd
# Для DOCX:
# from docx import Document

from .models import TariffSegment
from .utils import to_segments as _to_segments
from shared import port_dict, container_size_dict, get_country

_COMPANY = "[Company Name]"


def _parse_price(val) -> Optional[float]:
    if val is None:
        return None
    s = re.sub(r"[^\d]", "", str(val).replace("\xa0", ""))
    return float(s) if s else None


def _translate_port(raw: str) -> str:
    raw = re.sub(r"\*+", "", raw).strip()
    if raw in port_dict:
        return port_dict[raw]
    base = re.sub(r"\s*\(.*?\)", "", raw).strip()
    return port_dict.get(base, raw)


def _parse_table(file_path: str) -> list[dict]:
    results: list[dict] = []
    
    # --- здесь логика чтения и обхода таблиц/строк ---
    
    # Пример формирования сегмента:
    results.append(
        TariffSegment(
            transport_type="sea",          # обязательно
            start_point=f"{port_ru}, {country}",   # обязательно
            end_point=f"{dest_ru}, Россия",         # обязательно
            container_type=ct,             # обязательно
            cost=price,
            currency="USD",
            company=_COMPANY,
            valid_from=valid_from,         # "YYYY-MM-DD" или None
            valid_to=valid_to,
            start_location_type="port",    # НИКОГДА "city"
            end_location_type="port",      # НИКОГДА "city"
            parent_start_location=city_ru,
            parent_start_location_type="city",
            parent_end_location=end_city,
            parent_end_location_type="city",
            weight_limit=container_size_dict.get(ct),
        ).to_dict()
    )
    
    return results


def parse(file_path: str) -> list[TariffSegment]:
    """Точка входа парсера."""
    results: list[dict] = []
    results += _parse_table(str(file_path))
    return _to_segments(results)
```

---

## Шаг 5 — Интеграция в main.py

**Добавь импорт** (после существующих импортов парсеров):
```python
import parsers.<module_name> as <alias>_parser
```

**Добавь вызов** (рядом со строкой `segments += panda_parser.parse(...)`):
```python
segments += <alias>_parser.parse("<путь_к_файлу>")
```

**Для тестирования** закомментируй все остальные парсеры в `parse_all()`, оставь только новый:
```python
def parse_all(paths=None):
    segments = []
    # остальные парсеры закомментированы
    segments += new_parser.parse("data/файл.pdf")
    return segments_to_df(segments)
```

---

## Шаг 6 — Проверка результата

1. Запусти `python main.py`
2. Открой `tariff_analysis_TEST.xlsx` и проверь:

| Колонка | Что проверить |
|---------|--------------|
| `transport_type` | не пустая, значения: sea/rail/truck |
| `start_point` | не пустая, на русском, формат "Город, Страна" |
| `end_point` | не пустая, на русском, формат "Город, Страна" |
| `container_type` | не пустая, стандартный код (20DC, 40HC и т.д.) |
| `start_location_type` | НЕ "city" — только port/station/terminal |
| `end_location_type` | НЕ "city" — только port/station/terminal |
| `cost` | числовое значение |
| `currency` | USD/RUB/CNY |
| `valid_from` / `valid_to` | формат YYYY-MM-DD (если есть в файле) |
| `company` | заполнено для всех строк |
| Кол-во строк | соответствует числу тарифов в файле |

3. **Если есть ошибки** — исправь парсер и повтори с шага 6. Итерируй до полного успеха.

---

## Шаг 7 — Финализация

После успешной проверки сообщи пользователю:
- Сколько сегментов (строк) извлечено
- Какие маршруты покрыты (откуда → куда)
- Какие типы контейнеров найдены
- Даты действия тарифов (если есть)

---

## Критические правила (никогда не нарушай)

1. `start_point` и `end_point` — **НИКОГДА тип "city"**, только "port", "station", "terminal"
2. Все названия — **только на русском** (через port_dict, region_dict из shared.py)
3. Если названия нет в словаре — **сначала добавь в shared.py**, потом используй
4. `weight_limit` — **всегда** `container_size_dict.get(container_type)`
5. Даты — **формат "YYYY-MM-DD"**
6. Тестировать — **только новый парсер**, остальные закомментировать
7. **Не останавливайся** пока все тарифы не извлечены корректно
