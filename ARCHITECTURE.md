# 🏗️ Архитектура системы геокодирования

## Общая схема

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ваш парсер                               │
│  (CSV, Excel, БД, API)                                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
        ┌──────────────────────────────┐
        │  Список локаций              │
        │  [                           │
        │    {                         │
        │      "name": "Шанхай",       │
        │      "country_code": "CN"    │
        │    }                         │
        │  ]                           │
        └────────┬─────────────────────┘
                 │
                 ↓
    ┌────────────────────────────────────────────┐
    │  LogiwaysClient                            │
    │  .geocode_and_update_segment_coordinates() │
    └────┬───────────────────────────────────────┘
         │
         ├──→ Для каждой локации:
         │    .geocode_location()
         │         │
         │         ├──→ YandexGeocoder API
         │         │    (запрос по названию)
         │         │
         │         ←──  RouteSegmentCoordinate
         │             (широта, долгота)
         │
         └──→ Сборка координат
              │
              ↓
         ┌─────────────────────────────┐
         │  List[RouteSegmentCoordinate]
         │  [                          │
         │    {                        │
         │      "latitude": 31.23,     │
         │      "longitude": 121.47,   │
         │      "order_position": 0,   │
         │      "description": "..."   │
         │    }                        │
         │  ]                          │
         └────────┬────────────────────┘
                  │
                  ↓
      ┌───────────────────────────────────┐
      │  .update_route_segment_coordinates()
      │  PUT /admin/route-segments/      │
      │      {id}/coordinates            │
      └────────┬────────────────────────────┘
               │
               ↓
      ┌──────────────────────────────┐
      │  Logiways Server             │
      │  (Сохраняет координаты)      │
      └──────────────────────────────┘
               │
               ↓
          ✓ Готово!
```

---

## Компоненты системы

### 1️⃣ **Входные данные** (Ваш парсер)
```
CSV / Excel / БД / API
    ↓
Список локаций:
  - name (обязательно)
  - country_code (рекомендуется)
  - region (опционально)
  - description (опционально)
```

### 2️⃣ **Yandex Geocoder API**
```
YandexGeocoder
  │
  ├─ Поиск по названию
  ├─ Уточнение по стране/регону
  ├─ Кеширование результатов
  └─ Повторные попытки при ошибках
```

### 3️⃣ **LogiwaysClient**
```
LogiwaysClient
  │
  ├─ geocode_location()
  │   Уникальная локация → Координата
  │
  ├─ update_route_segment_coordinates()
  │   Список координат → PUT на сервер
  │
  └─ geocode_and_update_segment_coordinates()
      (Комбинация выше) ← ОСНОВНОЙ МЕТОД
```

### 4️⃣ **Выходные данные**
```
Logiways Server
  │
  ├─ /admin/route-segments/{id}/coordinates
  ├─ Сохранено в БД
  └─ Доступно в API
```

---

## Структуры данных

### Input: Локация
```python
{
    "name": str,                    # "Шанхай"
    "country_code": str | None,     # "CN"
    "region": str | None,           # "Провинция"
    "description": str | None       # "Морской порт"
}
```

### Processing: RouteSegmentCoordinate
```python
@dataclass
class RouteSegmentCoordinate:
    latitude: float              # 31.23
    longitude: float             # 121.47
    order_position: int          # 0, 1, 2...
    description: str | None      # "Шанхай, Китай"
```

### Output: JSON Payload (PUT)
```json
[
  {
    "latitude": 31.23,
    "longitude": 121.47,
    "order_position": 0,
    "description": "Шанхай"
  }
]
```

---

## Поток данных в картинках

### Вариант 1: Одна локация
```
geocode_location()
┌──────────────┐
│ "Шанхай", CN │
└──────┬───────┘
       │
       ├─ Yandex API: "Шанхай, CN"
       │
       ├─ Парсим JSON ответ
       │
       └─→ RouteSegmentCoordinate
           (31.23, 121.47, 0, "Шанхай...")
```

### Вариант 2: Несколько локаций (ОБЫЧНЫЙ)
```
geocode_and_update_segment_coordinates()
┌─────────────────────────┐
│ [Шанхай, Владивосток]   │
└────────┬────────────────┘
         │
         ├─→ geocode_location("Шанхай")
         │   ├─ Yandex API
         │   └─→ (31.23, 121.47)
         │
         ├─→ geocode_location("Владивосток")
         │   ├─ Yandex API
         │   └─→ (43.11, 131.89)
         │
         ├─→ Собираем список координат
         │
         └─→ update_route_segment_coordinates()
             └─ PUT /admin/route-segments/{id}/coordinates
```

---

## Интеграция в парсер

```
Ваш основной парсер
│
├─ Читаете данные (CSV, Excel, БД)
│
├─ Форматируете списки локаций
│
├─ Инициализируете LogiwaysClient
│
├─ Для каждого маршрута:
│  │
│  └─→ client.geocode_and_update_segment_coordinates(
│        route_segment_id,
│        locations
│     )
│
└─ Результаты сохраняются на сервере
```

### Пример в контексте вашего кода:

```
# send_api_New.py

def your_parser_function(df):
    client = LogiwaysClient()
    
    for segment_id, group in df.groupby('segment_id'):
        locations = [...]  # Форматируем
        
        # ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
        result = client.geocode_and_update_segment_coordinates(
            route_segment_id=segment_id,
            locations=locations
        )
        
        if result:
            print(f"✓ {segment_id} обновлен")
```

---

## Кеширование

```
Yandex API запрос
        │
        ├─ Генерируем cache_key
        │  "yandex|CN||0|Шанхай, Китай"
        │
        ├─ Проверяем yandex_geocode_cache.json
        │
        ├─ Если есть в кеше → используем
        │
        └─ Если нет → Yandex API → кешируем
```

---

## Обработка ошибок

```
geocode_and_update_segment_coordinates()
    │
    ├─ Локация не найдена
    │  └─→ Логируем, продолжаем со следующей
    │
    ├─ Нет токенов (не аутентифицирован)
    │  └─→ Ошибка + сообщение
    │
    ├─ HTTP 401 (токен истек)
    │  └─→ refresh_token() → повтор
    │
    ├─ HTTP 429 (rate limit)
    │  └─→ sleep(2 сек) → повтор
    │
    ├─ Нет API ключа
    │  └─→ Ошибка + инструкция
    │
    └─ PUT ошибка
       └─→ Логируем ответ сервера
```

---

## Временная шкала операции

```
Начало: geocode_and_update_segment_coordinates()
    │
    ├─ 0ms:   Проверка токенов
    │
    ├─ 10ms:  Для локации #1:
    │  │      ├─ geocode_location()
    │  │      ├─ Yandex API запрос    (200ms)
    │  │      └─ Парсинг результата    (5ms)
    │  │
    │  └─ Sleep 200-300ms
    │
    ├─ 520ms: Для локации #2:
    │  │      ├─ geocode_location()
    │  │      ├─ Yandex API запрос    (200ms)
    │  │      └─ Парсинг результата    (5ms)
    │  │
    │  └─ Sleep 200-300ms
    │
    ├─ 1030ms: Собираем координаты
    │
    ├─ 1050ms: update_route_segment_coordinates()
    │  │       ├─ Формируем JSON payload
    │  │       ├─ PUT запрос на сервер  (100ms)
    │  │       └─ Парсим ответ          (5ms)
    │
    └─ 1155ms: Завершено ✓

Итого: ~1.2 сек для 2 локаций
```

---

## Пример вывода консоли

```
Геокодирование: Шанхай, CN
✓ Найдено: Шанхай, Шанхайский муниципалитет, Китай (31.23, 121.47)

Геокодирование: Владивосток, Приморский край, RU
✓ Найдено: Владивосток, Приморский край, Россия (43.11, 131.89)

Отправка 2 координат на сервер...
✓ Координаты успешно обновлены
```

---

## Проверочный лист интеграции

- [ ] Установлены зависимости (`pip install ...`)
- [ ] Установлена переменная `YANDEX_API_KEY`
- [ ] Клиент инициализирован и аутентифицирован
- [ ] Тесты пройдены (`python test_geocoding.py`)
- [ ] Интегрирована функция в парсер
- [ ] Выполнена на тестовых данных
- [ ] Проверены результаты на сервере
- [ ] Готово к production ✅

---

## Связи между компонентами

```
geocode_locations_yandex_toponyms.py
    │
    ├─ YandexGeocoder (class)
    │  ├─ Работает с Yandex API
    │  └─ Возвращает GeocodeResult
    │
    └─ [используется в]
       │
       send_api_New.py
       │
       └─ LogiwaysClient
          │
          ├─ geocode_location()
          │  └─ создает YandexGeocoder
          │  └─ возвращает RouteSegmentCoordinate
          │
          ├─ update_route_segment_coordinates()
          │  └─ отправляет PUT запрос
          │
          └─ geocode_and_update_segment_coordinates()
             └─ комбинирует оба метода выше
```

---

## Тестирование архитектуры

```
test_geocoding.py
    │
    ├─ Тест 1: Проверка импортов
    ├─ Тест 2: Создание клиента
    ├─ Тест 3: Dataclass RouteSegmentCoordinate
    ├─ Тест 4: Поиск API ключа
    ├─ Тест 5: Наличие методов
    ├─ Тест 6: Реальное геокодирование
    └─ Тест 7: Формат JSON payload
```

---

🎯 **Все готово к использованию!**
