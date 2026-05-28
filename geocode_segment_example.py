#!/usr/bin/env python3
"""
Примеры использования функций геокодирования в send_api_New.py

Функции для работы:
1. geocode_location() - геокодирует одну локацию
2. update_route_segment_coordinates() - отправляет координаты на сервер через PUT
3. geocode_and_update_segment_coordinates() - комбинированная функция (геокод + отправка)
"""

import os
from send_api_New import LogiwaysClient, RouteSegmentCoordinate

# ============================================================================
# Пример 1: Геокодирование одной локации
# ============================================================================
def example_1_geocode_single_location():
    """
    Геокодирует одну локацию через Yandex API
    и возвращает объект RouteSegmentCoordinate с координатами.
    """
    print("\n" + "="*70)
    print("ПРИМЕР 1: Геокодирование одной локации")
    print("="*70)
    
    # Инициализируем клиент
    client = LogiwaysClient(base_url="https://test.logiways.ru")
    
    # Аутентификация (предполагаем, что токены уже получены)
    # client.tokens = ... 
    
    # Геокодируем одну локацию
    coord = client.geocode_location(
        location_name="Шанхай",
        country_code="CN",
        yandex_api_key=os.getenv("YANDEX_API_KEY")
    )
    
    if coord:
        print(f"\n✓ Успешно найдены координаты:")
        print(f"  Локация: {coord.description}")
        print(f"  Широта: {coord.latitude}")
        print(f"  Долгота: {coord.longitude}")
        print(f"  Позиция: {coord.order_position}")
    else:
        print("\n✗ Координаты не найдены")


# ============================================================================
# Пример 2: Отправка координат на сервер (без геокодирования)
# ============================================================================
def example_2_update_coordinates_direct():
    """
    Отправляет уже известные координаты на сервер через PUT.
    Полезно если у вас уже есть координаты из другого источника.
    """
    print("\n" + "="*70)
    print("ПРИМЕР 2: Отправка координат на сервер напрямую")
    print("="*70)
    
    client = LogiwaysClient(base_url="https://test.logiways.ru")
    # client.tokens = ...
    
    # Создаем список координат вручную
    coordinates = [
        RouteSegmentCoordinate(
            latitude=31.2304,
            longitude=121.4737,
            order_position=0,
            description="Шанхай (Китай)"
        ),
        RouteSegmentCoordinate(
            latitude=43.1050,
            longitude=131.8855,
            order_position=1,
            description="Владивосток (Россия)"
        ),
    ]
    
    # Отправляем на сервер
    result = client.update_route_segment_coordinates(
        route_segment_id="seg_12345",  # ID маршрутного сегмента
        coordinates=coordinates
    )
    
    if result:
        print("\n✓ Координаты успешно обновлены")
        print(f"  Ответ сервера: {result}")
    else:
        print("\n✗ Ошибка при отправке координат")


# ============================================================================
# Пример 3: Полный процесс - геокодирование и отправка на сервер
# ============================================================================
def example_3_geocode_and_update():
    """
    Комбинированный процесс:
    1. Геокодирует список локаций через Yandex API
    2. Автоматически отправляет координаты на сервер
    
    Это самый удобный способ при работе с несколькими локациями.
    """
    print("\n" + "="*70)
    print("ПРИМЕР 3: Геокодирование и отправка координат (полный процесс)")
    print("="*70)
    
    client = LogiwaysClient(base_url="https://test.logiways.ru")
    # client.tokens = ...
    
    # Список локаций для геокодирования
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
            "description": "Промежуточный пункт"
        },
        {
            "name": "Москва",
            "country_code": "RU"
            # description не указан, будет установлено название из Yandex API
        }
    ]
    
    # Геокодируем и отправляем координаты
    result = client.geocode_and_update_segment_coordinates(
        route_segment_id="seg_67890",
        locations=locations,
        yandex_api_key=os.getenv("YANDEX_API_KEY"),
        yandex_lang="ru_RU",
        sleep_between_requests=0.2  # Пауза между запросами к Yandex API
    )
    
    if result:
        print("\n✓ Процесс завершен успешно")
        print(f"  Сервер вернул: {result}")
    else:
        print("\n✗ Ошибка при обработке")


# ============================================================================
# Пример 4: Обработка нескольких маршрутов
# ============================================================================
def example_4_process_multiple_routes():
    """
    Обрабатывает несколько маршрутов с геокодированием локаций.
    Демонстрирует как сделать это в цикле.
    """
    print("\n" + "="*70)
    print("ПРИМЕР 4: Обработка нескольких маршрутных сегментов")
    print("="*70)
    
    client = LogiwaysClient(base_url="https://test.logiways.ru")
    # client.tokens = ...
    
    # Несколько маршрутов
    routes = [
        {
            "segment_id": "seg_1001",
            "locations": [
                {"name": "Нинбо", "country_code": "CN"},
                {"name": "Владивосток", "country_code": "RU"},
                {"name": "Москва", "country_code": "RU"}
            ]
        },
        {
            "segment_id": "seg_1002",
            "locations": [
                {"name": "Шанхай", "country_code": "CN"},
                {"name": "Калининград", "country_code": "RU"}
            ]
        },
        {
            "segment_id": "seg_1003",
            "locations": [
                {"name": "Гавань Сямэнь", "country_code": "CN"},
                {"name": "Санкт-Петербург", "country_code": "RU"}
            ]
        }
    ]
    
    api_key = os.getenv("YANDEX_API_KEY")
    
    for route in routes:
        print(f"\nОбработка маршрута {route['segment_id']}...")
        
        result = client.geocode_and_update_segment_coordinates(
            route_segment_id=route["segment_id"],
            locations=route["locations"],
            yandex_api_key=api_key,
            sleep_between_requests=0.5
        )
        
        if result:
            print(f"  ✓ Маршрут {route['segment_id']} обновлен")
        else:
            print(f"  ✗ Ошибка при обработке маршрута {route['segment_id']}")


# ============================================================================
# Пример 5: Обработка CSV файла с локациями
# ============================================================================
def example_5_process_csv_file():
    """
    Читает CSV файл с локациями и геокодирует их.
    Ожидаемый формат CSV:
        segment_id,location_name,country_code,region,description
        seg_1,Шанхай,CN,,Начало
        seg_1,Владивосток,RU,Приморский край,Конец
        seg_2,Нинбо,CN,,Начало
        seg_2,Москва,RU,,Конец
    """
    print("\n" + "="*70)
    print("ПРИМЕР 5: Обработка CSV файла с локациями")
    print("="*70)
    
    import csv
    
    client = LogiwaysClient(base_url="https://test.logiways.ru")
    # client.tokens = ...
    
    csv_file = "locations_to_geocode.csv"
    
    try:
        # Читаем CSV и группируем по segment_id
        routes_data = {}
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                segment_id = row.get('segment_id')
                
                if segment_id not in routes_data:
                    routes_data[segment_id] = []
                
                location = {
                    'name': row.get('location_name'),
                    'country_code': row.get('country_code'),
                }
                
                if row.get('region'):
                    location['region'] = row.get('region')
                if row.get('description'):
                    location['description'] = row.get('description')
                
                routes_data[segment_id].append(location)
        
        # Обрабатываем каждый маршрут
        api_key = os.getenv("YANDEX_API_KEY")
        
        for segment_id, locations in routes_data.items():
            print(f"\nОбработка сегмента {segment_id}...")
            
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id=segment_id,
                locations=locations,
                yandex_api_key=api_key,
                sleep_between_requests=0.3
            )
            
            if result:
                print(f"  ✓ Сегмент {segment_id} успешно обновлен")
            else:
                print(f"  ✗ Ошибка при обработке сегмента {segment_id}")
    
    except FileNotFoundError:
        print(f"✗ Файл {csv_file} не найден")


# ============================================================================
# Пример 6: Обработка Excel файла (используя pandas)
# ============================================================================
def example_6_process_excel_file():
    """
    Читает Excel файл и геокодирует локации.
    Требует: pip install openpyxl pandas
    """
    print("\n" + "="*70)
    print("ПРИМЕР 6: Обработка Excel файла с локациями")
    print("="*70)
    
    try:
        import pandas as pd
    except ImportError:
        print("✗ Требуется установить pandas: pip install pandas openpyxl")
        return
    
    client = LogiwaysClient(base_url="https://test.logiways.ru")
    # client.tokens = ...
    
    excel_file = "routes_to_geocode.xlsx"
    
    try:
        # Читаем Excel файл
        df = pd.read_excel(excel_file)
        
        # Группируем по segment_id
        grouped = df.groupby('segment_id')
        
        api_key = os.getenv("YANDEX_API_KEY")
        
        for segment_id, group in grouped:
            print(f"\nОбработка сегмента {segment_id}...")
            
            locations = []
            for _, row in group.iterrows():
                location = {
                    'name': row.get('location_name'),
                    'country_code': row.get('country_code'),
                }
                
                if pd.notna(row.get('region')):
                    location['region'] = row.get('region')
                if pd.notna(row.get('description')):
                    location['description'] = row.get('description')
                
                locations.append(location)
            
            # Отправляем координаты на сервер
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id=segment_id,
                locations=locations,
                yandex_api_key=api_key
            )
            
            if result:
                print(f"  ✓ Сегмент {segment_id} обновлен ({len(locations)} локаций)")
            else:
                print(f"  ✗ Ошибка при обработке сегмента {segment_id}")
    
    except FileNotFoundError:
        print(f"✗ Файл {excel_file} не найден")
    except Exception as e:
        print(f"✗ Ошибка: {e}")


# ============================================================================
# БЫСТРЫЙ СТАРТ
# ============================================================================

if __name__ == "__main__":
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " Примеры использования функций геокодирования      ".center(68) + "║")
    print("║" + " send_api_New.py  ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    # Выберите какой пример запустить (раскомментируйте нужный)
    
    # example_1_geocode_single_location()          # Пример 1
    # example_2_update_coordinates_direct()         # Пример 2
    # example_3_geocode_and_update()                # Пример 3 (рекомендуется)
    # example_4_process_multiple_routes()           # Пример 4
    # example_5_process_csv_file()                  # Пример 5
    # example_6_process_excel_file()                # Пример 6
    
    print("\n✓ Примеры готовы! Раскомментируйте нужный пример внизу файла и запустите.")
    print("\nДля работы нужна переменная окружения YANDEX_API_KEY:")
    print("  export YANDEX_API_KEY='ваш_ключ'  # На Unix/Linux/Mac")
    print("  $env:YANDEX_API_KEY='ваш_ключ'   # На Windows PowerShell")
    print("\nТакже требуется аутентификация в LogiwaysClient (tokens)")
    print("\n")
