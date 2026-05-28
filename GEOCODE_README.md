# Функции геокодирования в send_api_New.py

Полное руководство по использованию функций для геокодирования локаций и отправки координат на сервер.

## 📋 Обзор

Добавлены три основные функции для работы с координатами маршрутных сегментов:

| Функция | Описание |
|---------|----------|
| `geocode_location()` | Геокодирует одну локацию через Yandex API |
| `update_route_segment_coordinates()` | Отправляет координаты на сервер (PUT) |
| `geocode_and_update_segment_coordinates()` | Комбинированная функция (геокод + отправка) |

## 🔧 Установка зависимостей

```bash
pip install requests pycountry Babel
```

## 🌍 Функция 1: `geocode_location()`

Геокодирует одну локацию через Yandex Geocoder API.

### Сигнатура

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

### Параметры

- **location_name** (str, обязательно): Название локации (город, порт, станция)
- **country_code** (str, опционально): ISO2 код страны (RU, CN, US и т.д.)
- **region** (str, опционально): Регион или область
- **yandex_api_key** (str, опционально): API ключ Yandex.
  - Если не указан, берется из переменной окружения `YANDEX_API_KEY` или `GEOCODER_API_KEY`
- **yandex_lang** (str): Язык ответа от Yandex API (по умолчанию `ru_RU`)

### Возвращаемое значение

- `RouteSegmentCoordinate`: Объект с полями:
  - `latitude: float` - Широта
  - `longitude: float` - Долгота
  - `order_position: int` - Порядковая позиция
  - `description: Optional[str]` - Описание (полное название от Yandex)

- `None`: Если локация не найдена или произошла ошибка

### Пример

```python
from send_api_New import LogiwaysClient
import os

client = LogiwaysClient(base_url="https://test.logiways.ru")
# client.tokens = ... (необходимо аутентифицироваться)

# Геокодируем локацию
coord = client.geocode_location(
    location_name="Шанхай",
    country_code="CN",
    yandex_api_key=os.getenv("YANDEX_API_KEY")
)

if coord:
    print(f"Найдено: {coord.description}")
    print(f"Координаты: {coord.latitude}, {coord.longitude}")
```

## 📤 Функция 2: `update_route_segment_coordinates()`

Отправляет координаты маршрутного сегмента на сервер через PUT запрос.

**Endpoint**: `PUT /admin/route-segments/{route_segment_id}/coordinates`

### Сигнатура

```python
def update_route_segment_coordinates(
    self, 
    route_segment_id: str, 
    coordinates: List[RouteSegmentCoordinate]
) -> Optional[Dict]
```

### Параметры

- **route_segment_id** (str): ID маршрутного сегмента
- **coordinates** (List[RouteSegmentCoordinate]): Список координат для отправки

### Возвращаемое значение

- `Dict`: Ответ сервера при успехе
- `None`: При ошибке

### Формат данных, отправляемый на сервер

```json
[
  {
    "latitude": 31.2304,
    "longitude": 121.4737,
    "order_position": 0,
    "description": "Шанхай (Китай)"
  },
  {
    "latitude": 43.1050,
    "longitude": 131.8855,
    "order_position": 1
  }
]
```

Поле `description` опционально и удаляется из payload если равно `None`.

### Пример

```python
from send_api_New import LogiwaysClient, RouteSegmentCoordinate

client = LogiwaysClient(base_url="https://test.logiways.ru")

coordinates = [
    RouteSegmentCoordinate(
        latitude=31.2304,
        longitude=121.4737,
        order_position=0,
        description="Шанхай"
    ),
    RouteSegmentCoordinate(
        latitude=43.1050,
        longitude=131.8855,
        order_position=1,
        description="Владивосток"
    ),
]

result = client.update_route_segment_coordinates(
    route_segment_id="seg_12345",
    coordinates=coordinates
)

if result:
    print("✓ Координаты успешно отправлены")
```

## 🔄 Функция 3: `geocode_and_update_segment_coordinates()`

Комбинированная функция: геокодирует список локаций и отправляет координаты на сервер.

### Сигнатура

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

### Параметры

- **route_segment_id** (str): ID маршрутного сегмента
- **locations** (List[Dict]): Список словарей с данными локаций:
  - `name` (обязательно): Название локации
  - `country_code` (опционально): ISO2 код страны
  - `region` (опционально): Регион
  - `description` (опционально): Описание для координаты
- **yandex_api_key** (str, опционально): API ключ Yandex
- **yandex_lang** (str): Язык ответа Yandex API
- **sleep_between_requests** (float): Пауза между запросами в секундах

### Возвращаемое значение

- `Dict`: Ответ сервера при успехе
- `None`: При ошибке

### Пример (РЕКОМЕНДУЕТСЯ)

```python
from send_api_New import LogiwaysClient
import os

client = LogiwaysClient(base_url="https://test.logiways.ru")

# Данные локаций
locations = [
    {
        "name": "Шанхай",
        "country_code": "CN",
        "description": "Начальный пункт"
    },
    {
        "name": "Владивосток",
        "country_code": "RU",
        "region": "Приморский край",
        "description": "Конечный пункт"
    },
    {
        "name": "Москва",
        "country_code": "RU"
    }
]

# Геокодируем и отправляем
result = client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_67890",
    locations=locations,
    yandex_api_key=os.getenv("YANDEX_API_KEY"),
    sleep_between_requests=0.3
)

if result:
    print("✓ Все координаты успешно обновлены")
```

## 📊 Dataclass: `RouteSegmentCoordinate`

Структура данных для одной координаты маршрутного сегмента.

```python
@dataclass
class RouteSegmentCoordinate:
    latitude: float              # Широта (обязательно)
    longitude: float             # Долгота (обязательно)
    order_position: int          # Порядковая позиция (обязательно)
    description: Optional[str] = None  # Описание (опционально)
```

### Пример использования

```python
coord = RouteSegmentCoordinate(
    latitude=55.7558,
    longitude=37.6173,
    order_position=0,
    description="Москва"
)
```

## 🔑 Переменные окружения

### `YANDEX_API_KEY` или `GEOCODER_API_KEY`

API ключ для Yandex Geocoder API. Можно установить двумя способами:

**Linux/Mac:**
```bash
export YANDEX_API_KEY='ваш_ключ'
python script.py
```

**Windows PowerShell:**
```powershell
$env:YANDEX_API_KEY='ваш_ключ'
python script.py
```

**В коде Python:**
```python
import os
os.environ['YANDEX_API_KEY'] = 'ваш_ключ'
```

## ⚙️ Настройки Yandex API

При создании `LogiwaysClient`, геокодер использует настройки Yandex:

| Параметр | По умолчанию | Описание |
|----------|--------------|---------|
| `lang` | `ru_RU` | Язык ответа API |
| `timeout` | 30 сек | Timeout для запроса |
| `retries` | 3 | Количество повторных попыток при ошибке |
| `sleep` | 0.2 сек | Пауза между запросами |

Все эти параметры можно переопределить при вызове функций.

## 📑 Примеры использования

Полные примеры можно найти в файле `geocode_segment_example.py`:

1. **Пример 1**: Геокодирование одной локации
2. **Пример 2**: Отправка известных координат на сервер
3. **Пример 3**: Полный цикл (геокод + отправка) ✅ **РЕКОМЕНДУЕТСЯ**
4. **Пример 4**: Обработка нескольких маршрутов
5. **Пример 5**: Чтение из CSV файла
6. **Пример 6**: Чтение из Excel файла

Запуск примеров:

```bash
python geocode_segment_example.py
```

## 🚨 Обработка ошибок

Все функции выводят информацию об ошибках в консоль. Примеры:

```python
# Функция возвращает None при ошибке
result = client.geocode_location(location_name="...")

if result is None:
    print("Ошибка при геокодировании")
else:
    print(f"Найдено: {result.description}")
```

## 📝 Логирование

При обработке локаций выводятся информационные сообщения:

```
Геокодирование: Шанхай, CN
✓ Найдено: Шанхай, Шанхайский муниципалитет, Китай (31.23, 121.47)

Геокодирование: Владивосток, Приморский край, RU
✓ Найдено: Владивосток, Приморский край, Россия (43.11, 131.89)

Отправка 2 координат на сервер...
✓ Координаты успешно обновлены
```

## 🔗 Интеграция с pandas (Excel)

```python
import pandas as pd
from send_api_New import LogiwaysClient

df = pd.read_excel("routes.xlsx")
client = LogiwaysClient()

for segment_id, group in df.groupby('segment_id'):
    locations = group[['location_name', 'country_code', 'region']].to_dict('records')
    client.geocode_and_update_segment_coordinates(
        route_segment_id=segment_id,
        locations=locations
    )
```

## ⚠️ Важные замечания

1. **Аутентификация**: Перед использованием функций необходимо получить токены через `verify_sms()` или `refresh_token()`

2. **Rate Limiting**: Yandex API имеет ограничение на количество запросов. По умолчанию между запросами устанавливается пауза 0.2 сек

3. **Кеширование**: `geocode_locations_yandex_toponyms.py` кеширует результаты в JSON файл. Это ускоряет повторную обработку

4. **Точность координат**: Координаты - это центр найденного объекта. Для большей точности добавляйте `region` или `country_code`

5. **Язык запроса**: Используются русские названия городов для лучшего поиска. Можно менять через `yandex_lang`

## 🆘 Troubleshooting

### "Ошибка: не указан API ключ Yandex"

```python
# Решение: установите переменную окружения или передайте параметром
result = client.geocode_location(
    location_name="Шанхай",
    yandex_api_key="ВАШ_КЛЮЧ"
)
```

### "Координаты не найдены"

```python
# Решение: добавьте страну и регион для уточнения поиска
result = client.geocode_location(
    location_name="Москва",
    country_code="RU",
    region="Московская область"
)
```

### "HTTP 429: rate limit exceeded"

```python
# Решение: увеличьте паузу между запросами
client.geocode_and_update_segment_coordinates(
    route_segment_id="seg_123",
    locations=locations,
    sleep_between_requests=1.0  # Увеличьте до 1 секунды
)
```

## 📚 Дополнительно

- [Документация Yandex Geocoder API](https://yandex.ru/dev/maps/geocoder/)
- [geocode_locations_yandex_toponyms.py](geocode_locations_yandex_toponyms.py) - модуль геокодирования
- [send_api_New.py](send_api_New.py) - основной клиент API
