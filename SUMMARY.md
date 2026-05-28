# 📦 Резюме: Функции геокодирования для send_api_New.py

## ✅ Что было добавлено

### 1. **Новый Dataclass** (`RouteSegmentCoordinate`)
```python
@dataclass
class RouteSegmentCoordinate:
    latitude: float              # Широта
    longitude: float             # Долгота
    order_position: int          # Порядковая позиция
    description: Optional[str] = None  # Описание (опционально)
```

Структура для передачи координат маршрутного сегмента.

---

### 2. **Три новых метода в `LogiwaysClient`**

#### 📍 `geocode_location()`
Геокодирует одну локацию через Yandex API.

**Сигнатура:**
```python
def geocode_location(
    self,
    location_name: str,
    country_code: Optional[str] = None,
    region: Optional[str] = None,
    yandex_api_key: Optional[str] = None,
    yandex_lang: str = "ru_RU"
) -> Optional[RouteSegmentCoordinate]
```

**Использование:**
```python
coord = client.geocode_location(
    location_name="Шанхай",
    country_code="CN"
)
print(f"Найдено: {coord.latitude}, {coord.longitude}")
```

---

#### 📤 `update_route_segment_coordinates()`
Отправляет координаты на сервер через PUT запрос.

**Endpoint:** `PUT /admin/route-segments/{route_segment_id}/coordinates`

**Сигнатура:**
```python
def update_route_segment_coordinates(
    self, 
    route_segment_id: str, 
    coordinates: List[RouteSegmentCoordinate]
) -> Optional[Dict]
```

**JSON Payload:**
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

**Использование:**
```python
coords = [
    RouteSegmentCoordinate(31.23, 121.47, 0, "Шанхай"),
    RouteSegmentCoordinate(43.11, 131.89, 1, "Владивосток")
]
result = client.update_route_segment_coordinates(
    route_segment_id="seg_123",
    coordinates=coords
)
```

---

#### 🔄 `geocode_and_update_segment_coordinates()` ⭐ **ОСНОВНАЯ**
Комбинированная функция: геокодирует локации и отправляет координаты на сервер.

**Сигнатура:**
```python
def geocode_and_update_segment_coordinates(
    self,
    route_segment_id: str,
    locations: List[Dict[str, str]],
    yandex_api_key: Optional[str] = None,
    yandex_lang: str = "ru_RU",
    sleep_between_requests: float = 0.2
) -> Optional[Dict]
```

**Использование (РЕКОМЕНДУЕТСЯ):**
```python
locations = [
    {"name": "Шанхай", "country_code": "CN"},
    {"name": "Владивосток", "country_code": "RU"},
    {"name": "Москва", "country_code": "RU"}
]

result = client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_123",
    locations=locations
)
```

---

## 📁 Созданные файлы

| Файл | Описание |
|------|---------|
| [send_api_New.py](send_api_New.py) | **Основной файл с добавленными функциями** |
| [GEOCODE_README.md](GEOCODE_README.md) | Полная документация |
| [QUICKSTART.md](QUICKSTART.md) | Быстрый старт |
| [geocode_segment_example.py](geocode_segment_example.py) | 6 примеров использования |
| [test_geocoding.py](test_geocoding.py) | Тесты функций |

---

## 🚀 Быстрый старт (3 шага)

### 1. Установите зависимости
```bash
pip install requests pycountry Babel openpyxl pandas
```

### 2. Установите API ключ
```bash
# Windows PowerShell
$env:YANDEX_API_KEY = 'ваш_ключ'

# Linux/Mac
export YANDEX_API_KEY='ваш_ключ'
```

### 3. Используйте в коде
```python
from send_api_New import LogiwaysClient

client = LogiwaysClient()

locations = [
    {"name": "Шанхай", "country_code": "CN"},
    {"name": "Москва", "country_code": "RU"}
]

result = client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_123",
    locations=locations
)
```

---

## 📊 Интеграция с вашим парсером

### Пример 1: CSV файл
```python
import csv

locations_by_segment = {}
with open("locations.csv") as f:
    for row in csv.DictReader(f):
        segment_id = row['segment_id']
        if segment_id not in locations_by_segment:
            locations_by_segment[segment_id] = []
        locations_by_segment[segment_id].append({
            'name': row['location_name'],
            'country_code': row['country_code']
        })

for segment_id, locations in locations_by_segment.items():
    client.geocode_and_update_segment_coordinates(segment_id, locations)
```

### Пример 2: Excel файл
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

### Пример 3: Прямая отправка известных координат
```python
from send_api_New import RouteSegmentCoordinate

coords = [
    RouteSegmentCoordinate(31.23, 121.47, 0, "Шанхай"),
    RouteSegmentCoordinate(55.75, 37.62, 1, "Москва")
]

client.update_route_segment_coordinates(
    route_segment_id="seg_123",
    coordinates=coords
)
```

---

## 🔑 Три способа использования

| Способ | Когда использовать | Пример |
|--------|-------------------|--------|
| **geocode_location()** | Одна локация | `client.geocode_location("Москва", country_code="RU")` |
| **update_route_segment_coordinates()** | Уже известные координаты | Отправка из другого источника |
| **geocode_and_update_segment_coordinates()** | **Обычно это** ✅ | Список локаций → Геокод → Отправка |

---

## ⚙️ Настройки

### Параметры геокодирования
- `yandex_lang`: Язык ответа (`ru_RU` или `en_US`)
- `sleep_between_requests`: Пауза между запросами (сек)
- Кеширование: Встроено в `geocode_locations_yandex_toponyms.py`

### Переменные окружения
```bash
YANDEX_API_KEY          # API ключ Yandex (обязательно)
GEOCODER_API_KEY        # Альтернатива
```

---

## 🧪 Тестирование

Проверьте что всё работает:
```bash
python test_geocoding.py
```

Выведет результаты 7 тестов:
- ✓ Импорты
- ✓ Создание клиента
- ✓ Dataclass
- ✓ API ключ
- ✓ Методы
- ✓ Геокодирование (реальный запрос)
- ✓ Формат данных (JSON)

---

## 📚 Документация

### Полная документация
[GEOCODE_README.md](GEOCODE_README.md) - подробное описание всех функций, параметров, обработка ошибок

### Быстрый старт
[QUICKSTART.md](QUICKSTART.md) - минимально необходимое для начала работы

### Примеры кода
[geocode_segment_example.py](geocode_segment_example.py) - 6 готовых примеров:
1. Геокодирование одной локации
2. Отправка известных координат
3. Полный процесс (геокод + отправка)
4. Несколько маршрутов
5. CSV файл
6. Excel файл

---

## ✨ Особенности

✅ **Автоматическое кеширование** - результаты сохраняются в JSON  
✅ **Встроенная обработка ошибок** - 404, 401, rate limiting  
✅ **Поддержка разных языков** - русские и английские названия  
✅ **Интеллектуальный поиск** - уточнение по стране, региону  
✅ **Пауза между запросами** - соблюдение rate limits Yandex API  
✅ **Опциональные параметры** - description можно не передавать  

---

## ⚠️ Важно

1. **Аутентификация** обязательна перед использованием
   ```python
   client.tokens = ...  # Получите через verify_sms()
   ```

2. **Для работы необходим API ключ Yandex**
   ```bash
   export YANDEX_API_KEY='ваш_ключ'
   ```

3. **Функции работают асинхронно с пережидаием**
   - Между Yandex запросами: 0.2 сек (по умолчанию)
   - При rate limiting автоматический retry

4. **Точность координат лучше когда:**
   - Указана страна (country_code)
   - Указан регион
   - Используются русские названия

---

## 🔗 Связанные файлы

- [geocode_locations_yandex_toponyms.py](geocode_locations_yandex_toponyms.py) - модуль геокодирования (используется)
- [send_api_New.py](send_api_New.py) - основной клиент API (содержит новые методы)

---

## 💡 Типичный workflow

```
Ваши данные
    ↓
├─ CSV / Excel
├─ База данных
└─ API

    ↓ (Форматирование)

Список локаций
{name, country_code, region, description}

    ↓

geocode_and_update_segment_coordinates()
    ├─ geocode_location() × N (для каждой локации)
    └─ update_route_segment_coordinates() (отправка на сервер)

    ↓

Сервер получает координаты
PUT /admin/route-segments/{id}/coordinates

    ↓

✓ Координаты обновлены
```

---

## 📞 Контакты

Если возникают проблемы:

1. Проверьте тесты: `python test_geocoding.py`
2. Читайте логи консоли (информативные сообщения об ошибках)
3. Проверьте примеры: [geocode_segment_example.py](geocode_segment_example.py)
4. Полная документация: [GEOCODE_README.md](GEOCODE_README.md)

---

## 📝 Версия

- **Добавлено:** 31 марта 2026
- **Версия API:** Yandex Geocoder v1
- **Python:** 3.7+
