# 📑 Индекс файлов геокодирования

## 📂 Структура файлов

```
d:\Logiways\parser\
│
├─ 🔴 ОСНОВНЫЕ ФАЙЛЫ (ИЗМЕНЕННЫЕ)
│
├─ send_api_New.py ⭐
│  └─ Основной файл с добавленными функциями
│     ├─ import: os (добавлен)
│     ├─ @dataclass RouteSegmentCoordinate (новый)
│     ├─ LogiwaysClient.geocode_location() (новый метод)
│     ├─ LogiwaysClient.update_route_segment_coordinates() (новый метод)
│     └─ LogiwaysClient.geocode_and_update_segment_coordinates() (новый метод)
│
├─ 🟢 ДОКУМЕНТАЦИЯ
│
├─ SUMMARY.md ⭐ (НАЧНИТЕ ОТСЮДА)
│  └─ Резюме: что добавлено, быстрый старт, примеры использования
│
├─ QUICKSTART.md
│  └─ Минимал для начала работы: установка, пример, 3 способа использования
│
├─ GEOCODE_README.md
│  └─ Полная документация: все функции, параметры, примеры, troubleshooting
│
├─ ARCHITECTURE.md
│  └─ Архитектура системы: диаграммы, структуры данных, интеграция
│
├─ 📚 ПРИМЕРЫ КОДА
│
├─ geocode_segment_example.py
│  └─ 6 готовых примеров:
│     ├─ Пример 1: Одна локация
│     ├─ Пример 2: Известные координаты
│     ├─ Пример 3: Полный цикл (РЕКОМЕНДУЕТСЯ)
│     ├─ Пример 4: Несколько маршрутов
│     ├─ Пример 5: CSV файл
│     └─ Пример 6: Excel файл
│
├─ test_geocoding.py
│  └─ Тесты функций (7 тестов):
│     ├─ Тест импортов
│     ├─ Тест создания клиента
│     ├─ Тест DataClass
│     ├─ Тест API ключа
│     ├─ Тест методов
│     ├─ Тест геокодирования
│     └─ Тест формата данных
│
├─ 📦 ИСХОДНЫЕ ФАЙЛЫ (ИСПОЛЬЗОВАННЫЕ)
│
├─ geocode_locations_yandex_toponyms.py
│  └─ Модуль геокодирования (используется параллельно)
│     ├─ YandexGeocoder (class)
│     ├─ GeocodeResult (dataclass)
│     ├─ geocode() метод
│     └─ Кеширование в JSON
│
└─ 📋 ЭТОТ ФАЙЛ
   └─ INDEX.md (Вы здесь)
```

---

## 🎯 Как начать работу

### Шаг 1: Прочитайте
```
1. SUMMARY.md          ← 5 минут (обзор)
2. QUICKSTART.md       ← 10 минут (быстрый старт)
3. GEOCODE_README.md   ← 20 минут (полная информация)
```

### Шаг 2: Установите
```bash
pip install requests pycountry Babel openpyxl pandas
$env:YANDEX_API_KEY = 'ваш_ключ'
```

### Шаг 3: Тестируйте
```bash
python test_geocoding.py
```

### Шаг 4: Используйте
Скопируйте нужный пример из `geocode_segment_example.py` или напишите свой код.

---

## 📚 Справочная таблица

| Нужно | Файл | Раздел |
|------|------|--------|
| **Быстро подсказка** | SUMMARY.md | "Быстрый старт" |
| **Минимум кода** | QUICKSTART.md | "Быстрый пример" |
| **Полная информация** | GEOCODE_README.md | Все разделы |
| **Примеры кода** | geocode_segment_example.py | 6 примеров |
| **Тестирование** | test_geocoding.py | Запустите и читайте |
| **Архитектура** | ARCHITECTURE.md | Диаграммы, схемы |
| **API ключ** | QUICKSTART.md | "Настройка API" |
| **CSV/Excel** | geocode_segment_example.py | Пример 5-6 |
| **Много локаций** | geocode_segment_example.py | Пример 4 |
| **Обработка ошибок** | GEOCODE_README.md | "Troubleshooting" |

---

## 🔑 Три основных функции в send_api_New.py

### 1️⃣ geocode_location()
**Файл:** send_api_New.py, строки ~740-790  
**Назначение:** Геокодировать одну локацию  
**Входные данные:** location_name, country_code, region, api_key  
**Выход:** RouteSegmentCoordinate или None  
**Пример:** [geocode_segment_example.py:21-45](geocode_segment_example.py#L21-L45)  

### 2️⃣ update_route_segment_coordinates()
**Файл:** send_api_New.py, строки ~710-740  
**Назначение:** Отправить координаты на сервер (PUT)  
**Входные данные:** route_segment_id, List[RouteSegmentCoordinate]  
**Выход:** Dict или None  
**Пример:** [geocode_segment_example.py:62-87](geocode_segment_example.py#L62-L87)  

### 3️⃣ geocode_and_update_segment_coordinates()
**Файл:** send_api_New.py, строки ~790-850  
**Назначение:** Геокодировать + отправить (ОСНОВНАЯ)  
**Входные данные:** route_segment_id, locations, api_key  
**Выход:** Dict или None  
**Пример:** [geocode_segment_example.py:104-140](geocode_segment_example.py#L104-L140)  
**⭐ РЕКОМЕНДУЕТСЯ**

---

## 🔗 Связи между файлами

```
test_geocoding.py (НАЧНИТЕ С ЭТОГО)
    │
    ├─ импортирует send_api_New.py
    └─ тестирует все функции

geocode_segment_example.py
    │
    ├─ импортирует send_api_New.py
    └─ показывает 6 примеров использования

send_api_New.py ⭐
    │
    ├─ импортирует geocode_locations_yandex_toponyms.py
    │  (в функции geocode_location())
    │
    ├─ содержит новый @dataclass RouteSegmentCoordinate
    │
    ├─ содержит 3 новых метода LogiwaysClient
    │
    └─ используется в вашем парсере

geocode_locations_yandex_toponyms.py
    │
    ├─ содержит YandexGeocoder (используется в geocode_location)
    ├─ содержит GeocodeResult (преобразуется в RouteSegmentCoordinate)
    ├─ работает с Yandex API
    └─ кеширует результаты в yandex_geocode_cache.json
```

---

## 📊 Размеры файлов

| Файл | Строк | Описание |
|------|-------|---------|
| send_api_New.py | 1406 | Основной файл (добавлено ~150 строк) |
| geocode_locations_yandex_toponyms.py | 459 | Модуль геокодирования |
| geocode_segment_example.py | 320 | Примеры (новый файл) |
| test_geocoding.py | 240 | Тесты (новый файл) |
| SUMMARY.md | 280 | Резюме (новый файл) |
| QUICKSTART.md | 180 | Быстрый старт (новый файл) |
| GEOCODE_README.md | 420 | Полная документация (новый файл) |
| ARCHITECTURE.md | 380 | Архитектура (новый файл) |

---

## ⚡ Быстрые ссылки

### Читать документацию
- 📄 [Обзор (SUMMARY.md)](SUMMARY.md)
- 🚀 [Быстрый старт (QUICKSTART.md)](QUICKSTART.md)
- 📖 [Полная документация (GEOCODE_README.md)](GEOCODE_README.md)
- 🏗️ [Архитектура (ARCHITECTURE.md)](ARCHITECTURE.md)

### Просмотреть примеры
- 💻 [Примеры кода (geocode_segment_example.py)](geocode_segment_example.py)
- 🧪 [Тесты (test_geocoding.py)](test_geocoding.py)

### Использовать в коде
```python
# Необходимый импорт
from send_api_New import LogiwaysClient, RouteSegmentCoordinate

# Инициализация
client = LogiwaysClient(base_url="https://test.logiways.ru")

# Основной метод (РЕКОМЕНДУЕТСЯ)
result = client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_123",
    locations=[
        {"name": "Шанхай", "country_code": "CN"},
        {"name": "Москва", "country_code": "RU"}
    ]
)
```

---

## 🧪 Тестирование

### Запустить все тесты
```bash
python test_geocoding.py
```

### Запустить примеры
```bash
python geocode_segment_example.py
```

---

## 🐛 Troubleshooting

| Проблема | Решение | Файл |
|----------|---------|------|
| ModuleNotFoundError | pip install ... | QUICKSTART.md |
| API ключ не установлен | $env:YANDEX_API_KEY | QUICKSTART.md |
| Координаты не найдены | Добавьте country_code | GEOCODE_README.md |
| Требуется аутентификация | client.tokens = ... | GEOCODE_README.md |
| HTTP 429 (rate limit) | Увеличьте sleep_between_requests | GEOCODE_README.md |

---

## 💾 Изменения в send_api_New.py

```
Было:                          Добавлено:
─────────────────────────────────────────────────────
import requests        →        + import os
from typing import ... →        (без изменений)
...                   →        + @dataclass RouteSegmentCoordinate
class LogiwaysClient: →        + geocode_location() (метод)
                       →        + update_route_segment_coordinates() (метод)
                       →        + geocode_and_update_segment_coordinates() (метод)
```

---

## 🔐 Безопасность

- ✅ API ключ НЕ хранится в коде
- ✅ Используется переменная окружения YANDEX_API_KEY
- ✅ SSL проверка отключена только для test.logiways.ru
- ✅ Работает с существующей аутентификацией (tokens)

---

## 📈 Производительность

### Примерные времена
- **Одна локация:** ~250ms (200ms Yandex API + overhead)
- **N локаций:** ~250ms × N + 100ms (PUT запрос)
- **Кеш попадание:** ~10ms (без API запроса)

---

## 🎓 Обучающий путь

```
1. Читаете SUMMARY.md           (5 мин)
   └─ Понимаете что добавлено

2. Читаете QUICKSTART.md        (10 мин)
   └─ Устанавливаете зависимости
   └─ Устанавливаете API ключ

3. Запускаете test_geocoding.py  (2 мин)
   └─ Проверяете что всё работает

4. Исследуете примеры            (15 мин)
   └─ geocode_segment_example.py (6 примеров)

5. Читаете GEOCODE_README.md     (30 мин)
   └─ Понимаете все детали

6. Читаете ARCHITECTURE.md       (20 мин)
   └─ Понимаете устройство

7. Интегрируете в свой код       (60+ мин)
   └─ Используете в парсере
```

**Итого:** ~2 часа от нуля до интеграции

---

## 📝 Чек-лист готовности

### Перед началом
- [ ] Прочитан SUMMARY.md
- [ ] Прочитан QUICKSTART.md
- [ ] Установлены зависимости
- [ ] Установлена переменная YANDEX_API_KEY
- [ ] Пройдены тесты (test_geocoding.py)

### Перед использованием
- [ ] Инициализирован LogiwaysClient
- [ ] Получены токены (через verify_sms)
- [ ] Подготовлены данные локаций
- [ ] Проверен формат входных данных

### После использования
- [ ] Проверены результаты на сервере
- [ ] Логи показывают успешную отправку
- [ ] Координаты видны в API
- [ ] Готово к production

---

## 🆘 Получить помощь

1. **Быстрый ответ:** QUICKSTART.md
2. **Не распирается:** GEOCODE_README.md → Troubleshooting
3. **Непонимаю поток:** ARCHITECTURE.md
4. **Нужны примеры:** geocode_segment_example.py
5. **Тестирование:** test_geocoding.py

---

**Хорошей работы! 🚀**
