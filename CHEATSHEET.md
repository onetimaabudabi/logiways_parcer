# 📋 Шпаргалка: Геокодирование в send_api_New.py

**Копи-паст шпаргалка для быстрого использования**

## ⚡ Самый быстрый пример (3 строки)

```python
from send_api_New import LogiwaysClient

client = LogiwaysClient()
client.geocode_and_update_segment_coordinates(
    "seg_123",
    [{"name": "Шанхай", "country_code": "CN"}]
)
```

---

## 🔧 Полная настройка

```python
import os
from send_api_New import LogiwaysClient

# 1. Установить API ключ
os.environ['YANDEX_API_KEY'] = 'ваш_ключ'

# 2. Создать клиент
client = LogiwaysClient(base_url="https://test.logiways.ru")

# 3. Аутентифицироваться
# client.tokens = ... 

# 4. Использовать
result = client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_123",
    locations=[
        {"name": "Шанхай", "country_code": "CN"},
        {"name": "Владивосток", "country_code": "RU"}
    ]
)
```

---

## 📍 Одна локация

```python
coord = client.geocode_location(
    location_name="Москва",
    country_code="RU"
)

if coord:
    print(f"{coord.latitude}, {coord.longitude}")
```

---

## 📤 Известные координаты

```python
from send_api_New import RouteSegmentCoordinate

coords = [
    RouteSegmentCoordinate(55.75, 37.62, 0, "Москва"),
    RouteSegmentCoordinate(31.23, 121.47, 1, "Шанхай"),
]

client.update_route_segment_coordinates(
    route_segment_id="seg_123",
    coordinates=coords
)
```

---

## 📊 CSV → Координаты

```python
import csv

lines = []
with open("locations.csv") as f:
    for row in csv.DictReader(f):
        result = client.geocode_location(
            location_name=row['name'],
            country_code=row['country_code']
        )
        row['latitude'] = result.latitude if result else ''
        row['longitude'] = result.longitude if result else ''
        lines.append(row)

with open("out.csv", 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=lines[0].keys())
    writer.writeheader()
    writer.writerows(lines)
```

---

## 📊 Excel → Координаты

```python
import pandas as pd

df = pd.read_excel("routes.xlsx")

for segment_id, group in df.groupby('segment_id'):
    locations = group[[
        'location_name', 
        'country_code', 
        'region'
    ]].to_dict('records')
    
    client.geocode_and_update_segment_coordinates(
        segment_id,
        locations
    )
```

---

## 📄 JSON → Координаты

```python
import json

with open("routes.json") as f:
    data = json.load(f)

for segment_id, seg_data in data.items():
    client.geocode_and_update_segment_coordinates(
        segment_id,
        seg_data['locations']
    )
```

---

## 🔄 Цикл по маршрутам

```python
routes = [
    {"segment_id": "seg_1", "locations": [...]},
    {"segment_id": "seg_2", "locations": [...]},
]

for route in routes:
    result = client.geocode_and_update_segment_coordinates(
        route['segment_id'],
        route['locations']
    )
    
    if result:
        print(f"✓ {route['segment_id']}")
    else:
        print(f"✗ {route['segment_id']}")
```

---

## 🛠️ Обработка ошибок

```python
try:
    result = client.geocode_and_update_segment_coordinates(
        route_segment_id="seg_123",
        locations=locations
    )
    
    if result:
        print("✓ Успех")
    else:
        print("✗ Ошибка")
        
except Exception as e:
    print(f"✗ Исключение: {e}")
```

---

## 📝 Структура данных

### Входных локаций
```python
{
    "name": "Шанхай",                 # обязательно
    "country_code": "CN",             # рекомендуется  
    "region": "Провинция",            # опционально
    "description": "Описание"         # опционально
}
```

### Вывода координат
```python
RouteSegmentCoordinate(
    latitude=31.23,         # float
    longitude=121.47,       # float
    order_position=0,       # int
    description="..."       # str | None
)
```

---

## 🔑 Три способа окружения

```bash
# 1. PowerShell
$env:YANDEX_API_KEY = 'key'

# 2. Bash  
export YANDEX_API_KEY='key'

# 3. Python
import os
os.environ['YANDEX_API_KEY'] = 'key'
```

---

## ⚙️ Настройки

```python
# Язык ответа
client.geocode_location(
    "Москва",
    yandex_lang="en_US"  # или "ru_RU"
)

# Пауза между запросами
client.geocode_and_update_segment_coordinates(
    "seg_123",
    locations,
    sleep_between_requests=1.0  # сек
)
```

---

## 🧪 Тестирование

```bash
# Запустить все тесты
python test_geocoding.py

# Проверить импорты
python -c "from send_api_New import LogiwaysClient; print('OK')"
```

---

## 📦 Импорты

```python
# Основное
from send_api_New import LogiwaysClient, RouteSegmentCoordinate

# Файлы
import csv
import json
import pandas as pd

# Утилиты
import os
import time
```

---

## 🐛 Частые ошибки

### "Требуется аутентификация"
```python
client.verify_sms(phone_number="+7...", code="777777")
# client.tokens будет установлен
```

### "не указан API ключ"
```python
os.environ['YANDEX_API_KEY'] = 'your_key'
# или
client.geocode_location("Москва", yandex_api_key='key')
```

### "Координаты не найдены"
```python
# Добавьте параметры
coord = client.geocode_location(
    "Москва",
    country_code="RU",
    yandex_lang="ru_RU"
)
```

### "HTTP 429 rate limit"
```python
# Увеличьте паузу
client.geocode_and_update_segment_coordinates(
    segment_id,
    locations,
    sleep_between_requests=2.0
)
```

---

## 📊 Встроенная статистика

```python
# Информация в консоли
# ✓ Найдено: ...
# ✗ Не найдено: ...
# ✗ Ошибка: ...

# Отслеживание результатов
results = []
for loc in locations:
    coord = client.geocode_location(loc['name'])
    results.append({
        'location': loc['name'],
        'found': coord is not None,
        'coords': (coord.latitude, coord.longitude) if coord else None
    })

for r in results:
    status = "✓" if r['found'] else "✗"
    print(f"{status} {r['location']}")
```

---

## 🎯 Чек-лист перед production

- [ ] Установлены зависимости: `pip install requests pycountry Babel`
- [ ] Переменная `YANDEX_API_KEY` установлена
- [ ] Тесты пройдены: `python test_geocoding.py`
- [ ] Проверены примеры на своих данных
- [ ] Обработка ошибок добавлена
- [ ] Логирование добавлено
- [ ] Пауза между запросами установлена
- [ ] Готово к запуску

---

## 📚 Ссылки в коде

```python
# Основной файл
send_api_New.py
  ├─ LogiwaysClient.geocode_location()
  ├─ LogiwaysClient.update_route_segment_coordinates()
  └─ LogiwaysClient.geocode_and_update_segment_coordinates()

# Примеры
geocode_segment_example.py (6 примеров)
file_integration_examples.py (работа с файлами)

# Тесты
test_geocoding.py

# Документация
SUMMARY.md
QUICKSTART.md
GEOCODE_README.md
```

---

## ⏱️ Временные затраты

```
Одна локация:      ~250ms  (200ms API + overhead)
10 локаций:       ~2.5сек  (с паузами)
100 локаций:      ~25сек   (с паузами)
Из кеша:          ~10ms    (без API запроса)
```

---

## 🎓 Обучающий путь (быстрый)

```
1. Читай эту шпаргалку      (2 мин)
2. Скопируй пример          (1 мин)
3. Установи API ключ        (1 мин)
4. Запусти код              (1 мин)
5. Смотри результаты        (1 мин)

Итого: ~5 минут
```

---

## 💡 Советы

1. **Начните с примера 3** из `geocode_segment_example.py`
2. **Используйте print для отладки** - выводы информативны
3. **Проверьте кеш** если медленно: `yandex_geocode_cache.json`
4. **Группируйте запросы** для разных маршрутов
5. **Тестируйте на малой выборке** перед production

---

**Успехов! 🚀**
