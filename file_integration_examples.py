#!/usr/bin/env python3
"""
Примеры интеграции геокодирования с файлами (вместо БД)

Показывает как работать с:
- CSV файлами
- JSON файлами  
- Excel файлами (XLS, XLSX)
"""

import csv
import json
import pandas as pd
from send_api_New import LogiwaysClient
import os

# ============================================================================
# ПРИМЕР 1: CSV → Геокодирование → Отправка на сервер
# ============================================================================

def example_csv_input():
    """
    Читает CSV файл с локациями и геокодирует их.
    
    CSV формат:
    segment_id,location_name,country_code,region,description
    seg_1,Шанхай,CN,,Начало маршрута
    seg_1,Владивосток,RU,Приморский край,Конец маршрута
    """
    print("\n" + "="*70)
    print("CSV → Геокодирование → Отправка")
    print("="*70)
    
    csv_file = "routes_to_geocode.csv"
    client = LogiwaysClient()
    # client.tokens = ...  # Необходимо
    
    # Группируем локации по segment_id
    routes_data = {}
    
    try:
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
        for segment_id, locations in routes_data.items():
            print(f"\nОбработка {segment_id}...")
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id=segment_id,
                locations=locations
            )
            if result:
                print(f"✓ {segment_id} успешно обновлен")
    
    except FileNotFoundError:
        print(f"✗ Файл {csv_file} не найден")
        print("  Создайте CSV с колонками: segment_id,location_name,country_code,region,description")


# ============================================================================
# ПРИМЕР 2: JSON → Геокодирование → Отправка
# ============================================================================

def example_json_input():
    """
    Читает JSON файл с маршрутами и локациями.
    
    JSON формат:
    {
      "seg_1": {
        "locations": [
          {"name": "Шанхай", "country_code": "CN"}
        ]
      }
    }
    """
    print("\n" + "="*70)
    print("JSON → Геокодирование → Отправка")
    print("="*70)
    
    json_file = "routes.json"
    client = LogiwaysClient()
    # client.tokens = ...
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # data структура: {segment_id: {locations: [...]}}
        for segment_id, segment_data in data.items():
            locations = segment_data.get('locations', [])
            
            print(f"\nОбработка {segment_id}...")
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id=segment_id,
                locations=locations
            )
            
            if result:
                print(f"✓ {segment_id} успешно обновлен")
    
    except FileNotFoundError:
        print(f"✗ Файл {json_file} не найден")
        print("  Пример JSON структуры:")
        example = {
            "seg_1": {
                "locations": [
                    {"name": "Шанхай", "country_code": "CN"}
                ]
            }
        }
        print(json.dumps(example, indent=2, ensure_ascii=False))


# ============================================================================
# ПРИМЕР 3: Excel → Геокодирование → Отправка
# ============================================================================

def example_excel_input():
    """
    Читает Excel файл с маршрутами и локациями.
    Требует: pip install openpyxl pandas
    
    Excel колонки:
    | segment_id | location_name | country_code | region | description |
    |    seg_1   |    Шанхай     |      CN      |        |   Начало    |
    """
    print("\n" + "="*70)
    print("Excel → Геокодирование → Отправка")
    print("="*70)
    
    excel_file = "routes.xlsx"
    client = LogiwaysClient()
    # client.tokens = ...
    
    try:
        df = pd.read_excel(excel_file)
        
        # Группируем по segment_id
        for segment_id, group in df.groupby('segment_id'):
            print(f"\nОбработка {segment_id}...")
            
            # Форматируем локации
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
            
            # Геокодируем и отправляем
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id=segment_id,
                locations=locations
            )
            
            if result:
                print(f"✓ {segment_id} успешно обновлен ({len(locations)} локаций)")
    
    except FileNotFoundError:
        print(f"✗ Файл {excel_file} не найден")


# ============================================================================
# ПРИМЕР 4: Чтение из CSV и сохранение результатов
# ============================================================================

def example_csv_with_output():
    """
    Читает CSV, геокодирует, и сохраняет результаты с координатами.
    """
    print("\n" + "="*70)
    print("CSV → Геокодирование → Сохранение результатов")
    print("="*70)
    
    input_file = "routes_input.csv"
    output_file = "routes_with_coordinates.csv"
    
    client = LogiwaysClient()
    # client.tokens = ...
    
    try:
        # Читаем входной файл
        results = []
        
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                location_name = row.get('location_name')
                country_code = row.get('country_code')
                
                # Геокодируем
                coord = client.geocode_location(
                    location_name=location_name,
                    country_code=country_code
                )
                
                # Добавляем результаты
                result_row = dict(row)
                if coord:
                    result_row['latitude'] = coord.latitude
                    result_row['longitude'] = coord.longitude
                    result_row['found'] = 'YES'
                else:
                    result_row['latitude'] = ''
                    result_row['longitude'] = ''
                    result_row['found'] = 'NO'
                
                results.append(result_row)
        
        # Сохраняем результаты
        if results:
            fieldnames = list(results[0].keys())
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            
            print(f"✓ Результаты сохранены в {output_file}")
    
    except FileNotFoundError:
        print(f"✗ Файл {input_file} не найден")


# ============================================================================
# ПРИМЕР 5: Excel с множественными листами
# ============================================================================

def example_excel_multiple_sheets():
    """
    Читает Excel файл с несколькими листами, каждый - маршрут.
    """
    print("\n" + "="*70)
    print("Excel (несколько листов) → Геокодирование")
    print("="*70)
    
    excel_file = "routes_by_company.xlsx"
    client = LogiwaysClient()
    # client.tokens = ...
    
    try:
        # Читаем все листы
        excel_file_obj = pd.ExcelFile(excel_file)
        
        for sheet_name in excel_file_obj.sheet_names:
            print(f"\nОбработка листа '{sheet_name}'...")
            
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # sheet_name обычно = segment_id
            segment_id = sheet_name
            
            locations = []
            for _, row in df.iterrows():
                location = {
                    'name': row.get('location_name'),
                    'country_code': row.get('country_code'),
                }
                
                if pd.notna(row.get('region')):
                    location['region'] = row.get('region')
                
                locations.append(location)
            
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id=segment_id,
                locations=locations
            )
            
            if result:
                print(f"  ✓ {len(locations)} локаций отправлено")
    
    except FileNotFoundError:
        print(f"✗ Файл {excel_file} не найден")


# ============================================================================
# ПРИМЕР 6: JSON с структурой по компаниям
# ============================================================================

def example_json_structured():
    """
    JSON структура с компаниями и маршрутами.
    
    Пример:
    {
      "company_1": {
        "segments": {
          "seg_1": {
            "locations": [...]
          }
        }
      }
    }
    """
    print("\n" + "="*70)
    print("JSON (структурированный) → Геокодирование")
    print("="*70)
    
    json_file = "companies_routes.json"
    client = LogiwaysClient()
    # client.tokens = ...
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Обходим компании
        for company_name, company_data in data.items():
            print(f"\nОбработка компании '{company_name}'...")
            
            segments = company_data.get('segments', {})
            
            # Обходим сегменты
            for segment_id, segment_data in segments.items():
                locations = segment_data.get('locations', [])
                
                result = client.geocode_and_update_segment_coordinates(
                    route_segment_id=segment_id,
                    locations=locations
                )
                
                if result:
                    print(f"  ✓ {segment_id}: {len(locations)} локаций")
    
    except FileNotFoundError:
        print(f"✗ Файл {json_file} не найден")


# ============================================================================
# ПРИМЕР 7: CSV → CSV (добавить координаты)
# ============================================================================

def example_csv_enrich():
    """
    Читает CSV с локациями, добавляет координаты, сохраняет в новый CSV.
    """
    print("\n" + "="*70)
    print("CSV (обогащение) → добавить координаты")
    print("="*70)
    
    input_file = "locations.csv"
    output_file = "locations_with_coords.csv"
    
    client = LogiwaysClient()
    api_key = os.getenv("YANDEX_API_KEY")
    
    try:
        rows = []
        
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames + ['latitude', 'longitude', 'status']
            
            for row in reader:
                coord = client.geocode_location(
                    location_name=row.get('name'),
                    country_code=row.get('country_code'),
                    region=row.get('region'),
                    yandex_api_key=api_key
                )
                
                row['latitude'] = coord.latitude if coord else ''
                row['longitude'] = coord.longitude if coord else ''
                row['status'] = 'OK' if coord else 'NOT_FOUND'
                
                rows.append(row)
        
        # Сохраняем результаты
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✓ Результаты сохранены в {output_file}")
        
        # Статистика
        ok_count = sum(1 for r in rows if r['status'] == 'OK')
        print(f"  Успешно: {ok_count}/{len(rows)}")
    
    except FileNotFoundError:
        print(f"✗ Файл {input_file} не найден")


# ============================================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================================

def main():
    """Main menu for running examples"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " Примеры работы с файлами  ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    examples = [
        ("CSV → Геокодирование → Отправка", example_csv_input),
        ("JSON → Геокодирование → Отправка", example_json_input),
        ("Excel → Геокодирование → Отправка", example_excel_input),
        ("CSV с сохранением результатов", example_csv_with_output),
        ("Excel с несколькими листами", example_excel_multiple_sheets),
        ("JSON структурированный", example_json_structured),
        ("CSV обогащение координатами", example_csv_enrich),
    ]
    
    print("\nДоступные примеры:\n")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    try:
        choice = input("\nВыберите номер примера (или Enter для выхода): ").strip()
        
        if not choice:
            print("\nСпасибо за использование!")
            return
        
        choice_num = int(choice) - 1
        
        if 0 <= choice_num < len(examples):
            name, func = examples[choice_num]
            print(f"\nЗапуск: {name}")
            func()
        else:
            print(f"\n✗ Номер должен быть от 1 до {len(examples)}")
    
    except ValueError:
        print("\n✗ Пожалуйста, введите номер")
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")


if __name__ == "__main__":
    main()
