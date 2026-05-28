# 🚀 Быстрый старт: Геокодирование координат

Минимальный пример для быстрого старта.

## 1️⃣ Установка

```bash
pip install requests pycountry Babel openpyxl pandas
```

## 2️⃣ Настройка API ключа

**PowerShell (Windows):**
```powershell
$env:YANDEX_API_KEY = 'ваш_api_ключ'
```

**Bash (Linux/Mac):**
```bash
export YANDEX_API_KEY='ваш_api_ключ'
```

## 3️⃣ Быстрый пример

```python
from send_api_New import LogiwaysClient
import os

# Создаем клиент
client = LogiwaysClient(base_url="https://test.logiways.ru")

# Аутентифицируемся (или используем существующие токены)
# client.tokens = ...

# Список локаций
locations = [
    {"name": "Шанхай", "country_code": "CN"},
    {"name": "Владивосток", "country_code": "RU"},
    {"name": "Москва", "country_code": "RU"}
]

# Геокодируем и отправляем на сервер
result = client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_123",
    locations=locations,
    yandex_api_key=os.getenv("YANDEX_API_KEY")
)

if result:
    print("✓ Готово!")
else:
    print("✗ Ошибка")
```

## 4️⃣ Обработка Excel файла

```python
import pandas as pd
from send_api_New import LogiwaysClient

df = pd.read_excel("routes.xlsx")
client = LogiwaysClient()
# client.tokens = ...

for segment_id, group in df.groupby('segment_id'):
    locations = group[[
        'location_name', 
        'country_code', 
        'region'
    ]].to_dict('records')
    
    client.geocode_and_update_segment_coordinates(
        route_segment_id=segment_id,
        locations=locations
    )
```

## 5️⃣ Отправка уже известных координат

```python
from send_api_New import LogiwaysClient, RouteSegmentCoordinate

client = LogiwaysClient()

# Если у вас уже есть координаты
coords = [
    RouteSegmentCoordinate(31.23, 121.47, 0, "Шанхай"),
    RouteSegmentCoordinate(43.11, 131.89, 1, "Владивосток"),
]

result = client.update_route_segment_coordinates(
    route_segment_id="seg_123",
    coordinates=coords
)
```

## 📊 Структура данных локации

```python
{
    "name": "Шанхай",           # ✅ Обязательно
    "country_code": "CN",       # ❓ Опционально (но рекомендуется)
    "region": "Провинция",      # ❓ Опционально
    "description": "Морской порт" # ❓ Опcionально
}
```

## 🔑 Три способа передать API ключ

1. **Переменная окружения** (рекомендуется):
   ```python
   # Автоматически подберется из YANDEX_API_KEY
   coord = client.geocode_location("Шанхай")
   ```

2. **Параметром функции**:
   ```python
   coord = client.geocode_location(
       "Шанхай",
       yandex_api_key="МОЙ_КЛЮЧ"
   )
   ```

3. **В коде**:
   ```python
   import os
   os.environ['YANDEX_API_KEY'] = 'МОЙ_КЛЮЧ'
   ```

## 📝 Три основные функции

| Функция | Когда использовать |
|---------|-------------------|
| `geocode_location()` | Нужна одна координата |
| `update_route_segment_coordinates()` | У вас уже есть координаты |
| `geocode_and_update_segment_coordinates()` | **Обычно это** ✅ |

## 🎯 Типичный workflow

```
CSV/Excel файл
    ↓
Читаем LocalStorage
    ↓
Форматируем список локаций
    ↓
geocode_and_update_segment_coordinates()
    ↓
Отправляем координаты на сервер
    ↓
✓ Готово
```

## ❓ Частые вопросы

**Q: Как узнать, что у меня есть координаты в локации?**
```python
segment = client.get_route_segments("company_id")[0]
has_coords = segment.get('latitude') and segment.get('longitude')
```

**Q: Сколько видов локаций?**
```python
from send_api_New import LocationType
# port, rail_station, city, warehouse, terminal, border, dropoff, customs
```

**Q: Как задать пользовательское описание?**
```python
locations = [
    {"name": "Шанхай", "description": "Начало маршрута"},
]
```

**Q: Можно ли отправить координаты без геокодирования?**
```python
# Да! Используйте update_route_segment_coordinates()
coords = [RouteSegmentCoordinate(lat, lon, 0)]
client.update_route_segment_coordinates(segment_id, coords)
```

## 🔗 Дополнительно

- [Полная документация](GEOCODE_README.md)
- [Примеры кода](geocode_segment_example.py)
- [Исходный модуль](geocode_locations_yandex_toponyms.py)
