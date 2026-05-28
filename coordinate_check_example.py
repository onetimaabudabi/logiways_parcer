"""
Пример использования проверки существующих координат
"""

from send_api_New import LogiwaysClient

# Создаем клиент (требуется аутентификация для реального использования)
client = LogiwaysClient()

# Пример данных для геокодирования
locations = [
    {"name": "Москва", "country_code": "RU"},
    {"name": "Санкт-Петербург", "country_code": "RU"},
    {"name": "Владивосток", "country_code": "RU"}
]

# ID сегмента маршрута (пример)
segment_id = "example_segment_123"

print("=== Проверка существующих координат ===")

# Первый вызов - проверит координаты и если они есть, пропустит геокодирование
result1 = client.geocode_and_update_segment_coordinates(
    route_segment_id=segment_id,
    locations=locations,
    yandex_api_key="YOUR_YANDEX_API_KEY"  # Замените на реальный ключ
)

print(f"Результат первого вызова: {result1}")

print("\n=== Принудительное обновление ===")

# Второй вызов с force_update=True - выполнит геокодирование независимо от существующих координат
result2 = client.geocode_and_update_segment_coordinates(
    route_segment_id=segment_id,
    locations=locations,
    yandex_api_key="YOUR_YANDEX_API_KEY",  # Замените на реальный ключ
    force_update=True
)

print(f"Результат второго вызова: {result2}")