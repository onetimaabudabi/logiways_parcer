import requests
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import json
import pandas as pd
import time
import hashlib
import os
from datetime import datetime

# ──────────────────────────────────────────────────────
# Паузы между запросами (секунды) — настроить при необходимости
# ──────────────────────────────────────────────────────
SLEEP_BETWEEN_REQUESTS = 0.5    # общий запрос (локации, тарифы и т.д.)
SLEEP_AFTER_REPLACE_SEGMENTS = 2.0   # после замены сегментов (бэкенду нужно время)
SLEEP_AFTER_TARIFF_CREATE = 0.5      # после создания тарифа

def convert_to_iso_date(date_input):
    """
    Преобразует дату в формат YYYY-MM-DD.

    Args:
        date_input: строка с датой, объект datetime или другой формат.

    Returns:
        Строка в формате YYYY-MM-DD или None при ошибке.
    """
    # Если уже объект datetime
    if isinstance(date_input, datetime):
        return date_input.strftime('%Y-%m-%d')

    # Если строка
    if isinstance(date_input, str):
        # Список возможных форматов для парсинга
        formats = [
            '%Y-%m-%d',      # 2026-03-11
            '%d.%m.%Y',      # 11.03.2026
            '%d/%m/%Y',      # 11/03/2026
            '%m/%d/%Y',      # 03/11/2026 (американский)
            '%Y.%m.%d',     # 2026.03.11
            '%d-%m-%Y',      # 11-03-2026
        ]

        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_input.strip(), fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue

    return None  # Если формат не распознан

def build_segment_key(
    company_id: str,
    transport_type: str,
    start_location_id: str,
    end_location_id: str,
):
    raw = "|".join([
        str(company_id or ""),
        str(transport_type or ""),
        str(start_location_id or ""),
        str(end_location_id or ""),
    ])
    return hashlib.md5(raw.encode()).hexdigest()


def normalize_country_code(country_code: Optional[str]) -> Optional[str]:
    """Нормализует код страны в ISO2 (RU, CN, MY и т.п.)."""
    if country_code is None:
        return None

    code = str(country_code).strip()
    if not code:
        return None

    # уже ISO2
    if len(code) == 2 and code.isalpha():
        return code.upper()

    # enum культурная похвальная: русские названия
    for cc in CountryCodeType:
        if cc.name.upper() == code.upper() or cc.value.lower() == code.lower():
            return cc.name

    # дополнительные англ названия, если передано
    english_map = {
        "RUSSIA": "RU", "BELARUS": "BY", "USA": "US", "CANADA": "CA",
        "CHINA": "CN", "JAPAN": "JP", "KOREA": "KR", "TAIWAN": "TW",
        "SINGAPORE": "SG", "AUSTRALIA": "AU", "THAILAND": "TH", "INDONESIA": "ID",
        "MALAYSIA": "MY", "VIETNAM": "VN", "ALGERIA": "DZ", "EGYPT": "EG",
        "TURKEY": "TR", "LIBYA": "LY", "SPAIN": "ES", "LEBANON": "LB",
        "SYRIA": "SY", "SAUDI ARABIA": "SA", "INDIA": "IN", "PAKISTAN": "PK",
        "BANGLADESH": "BD", "CAMBODIA": "KH", "MYANMAR": "MM", "ISRAEL": "IL",
        "UAE": "AE", "MONGOLIA": "MN", "BRAZIL": "BR"
    }
    normalized = english_map.get(code.strip().upper())
    if normalized:
        return normalized

    print(f"⚠ Не удалось нормализовать country_code='{country_code}'")
    return None


# --- Типизация на основе OpenAPI ---
class TransportType(str, Enum):
    RAIL = "rail"
    AIR = "air"
    SEA = "sea"
    AUTO = "auto"

class CountryCodeType(str, Enum):
    RU = "Россия"
    BY = "Белорусь"
    US = "США"
    CA = "Канада"
    CN = "Китай"
    JP = "Япония"
    KR = "Корея"
    TW = "Тайвань"
    SG = "Сингапур"
    AU = "Австралия"
    TH = "Таиланд"
    ID = "Индонезия"
    MY = "Малайзия"
    VN = "Вьетнам"
    DZ = "Алжирская Народная Демократическая Республика"
    EG = "Египет"
    TR = "Турция"
    LY = "Ливия"
    ES = "Испания"
    LB = "Ливан"
    SY = "Сирия"
    SA = "Саудовская Аравия"
    IN = "Индия"
    PK = "Пакистан"
    BD = "Бангладеш"
    KH = "Камбоджа"
    MM = "Мьянма"
    IL = "Израиль"
    AE = "Объединённые Арабские Эмираты"
    MN = "Монголия"
    BR = "Бразилия"
    PH = "Филиппины"
    LK = "Шри-Ланка"
    HK = "Гонконг"

class PortServiceTermType(str, Enum):
    FILO = "FILO"
    FIFO = "FIFO"
    LILO = "LILO"
    LIFO = "LIFO"

class ContainerType(str, Enum):
    DC20 = "20DC"
    GP20 = "20GP"
    RF20 = "20RF"
    TK20 = "20TK"
    HC40 = "40HC"
    HQ40 = "40HQ"
    RF40 = "40RF"
    TC20 = "20TC"
    FR20 = "20FR"

class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"
    KZT = "KZT"
    UZS = "UZS"
    KGS = "KGS"

class LocationType(str, Enum):
    PORT = "port"
    RAIL_STATION = "rail_station"
    CITY = "city"
    WAREHOUSE = "warehouse"
    TERMINAL = "terminal"
    BORDER = "border"
    DROPOFF = "dropoff"
    CUSTIMS = "customs"

class ChargeUnit(str, Enum):
    PER_CONTAINER = "per_container"
    PER_TEU = "per_teu"
    PER_BL = "per_bl"
    PER_DAY = "per_day"
    PER_HOUR = "per_hour"
    PERCENT = "percent"
    PER_TON = "per_ton"

class ContainerOwnership(str, Enum):
    SOC = "SOC"
    COC = "COC"
    ANY = "ANY"

@dataclass
class Departure:
    rate_status: str
    cut_off_date: Optional[str] = None
    etd_date: Optional[str] = None
    eta_date: Optional[str] = None
    vessel: Optional[str] = None
    voyage: Optional[str] = None
    capacity_status: Optional[str] = None
    source_row: Optional[dict] = field(default_factory=dict)

@dataclass
class Tokens:
    refresh_token: str
    access_token: str
    token_type: str = "Bearer"

# --- Новые структуры для транспортных компаний ---
@dataclass
class TransportCompaniesCreate:
    name: str
    contact_first_name: str
    contact_last_name: str
    phone: str
    email: str
    logo_url: Optional[str] = None
    contact_middle_name: Optional[str] = None
    languages: Optional[List[str]] = None
    is_active: bool = True

# --- Cтруктура для локаций---
@dataclass
class LocationsCreate:
    location_type: LocationType
    name: str
    country_code: Optional[str] = None
    region: Optional[str] = None
    parent_location_id: Optional[str] = None
    latitude: Optional[int] = None
    longitude: Optional[int] = None
    external_codes: Optional[dict] = field(default_factory=dict)

@dataclass
class RouteSegmentCreate:
    """Создание сегмента маршрута (используется внутри bulk)"""
    transport_type: TransportType
    start_location_id: str
    end_location_id: str
    border_location_id: Optional[str] = None
    customs_location_id: Optional[str] = None
    duration_min_days: Optional[int] = None
    duration_max_days: Optional[int] = None
    segment_key: Optional[str]= None
    departure_dates: Optional[dict] = field(default_factory=dict)
    conditions: Optional[str] = None

@dataclass
class RouteSegmentCreateBulk:
    """Массовое создание сегментов для замены всех сегментов компании"""
    transport_company_id: str
    segments: List[RouteSegmentCreate]
    organization_id: Optional[str] = None

@dataclass
class Сharge:
    charge_code: str
    unit: str
    amount: int
    currency: Optional[str] = None
    description: Optional[str] = None
    is_mandatory: Optional[bool] = True
    applies_when: Optional[dict] = field(default_factory=dict)

@dataclass
class ContainerPolicy:
    free_storage_days: Optional[int] = None
    free_container_use_days: Optional[int] = None
    drop_off_rules: Optional[dict] = field(default_factory=dict)
    penalties: Optional[dict] = field(default_factory=dict)
    notes: Optional[str] = None

@dataclass
class WeightBand:
    base_amount: int
    currency: str
    overweight_surcharge_per_ton: Optional[int] = None
    min_weight_kg: Optional[int] = None
    max_weight_kg: Optional[int] = None
    overweight_surcharge_currency: Optional[str] = None

@dataclass
class DropoffLocationCreate:
    location_id: str
    rule_kind: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    included: Optional[bool] = True
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_default: Optional[bool] = False
    notes: Optional[str] = None


@dataclass
class TariffCreate:
    price_kind: str
    container_type: ContainerType
    container_ownership: ContainerOwnership
    customs_included: Optional[bool] = False
    customs_location_id: Optional[str] = None
    destination_station_id: Optional[str] = None
    is_active: Optional[bool] = True
    vat_rate: Optional[int] = None
    vat_status: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    valid_from: Optional[str] = None #"2026-03-10"
    valid_to: Optional[str] = None
    incoterm: Optional[str] = None
    port_service_term: Optional[str] = None
    source_row: Optional[dict] = field(default_factory=dict)
    weight_bands: List[WeightBand] = field(default_factory=list)
    charges: List[Сharge] = field(default_factory=list)
    container_policy: Optional[ContainerPolicy] = None
    drop_off_locations: List[DropoffLocationCreate] = field(default_factory=list)

@dataclass
class TariffUpdate:
    id: str
    price_kind: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    charges: Optional[Сharge] = None

@dataclass
class RouteSegmentCoordinate:
    """Координата для маршрутного сегмента"""
    latitude: float
    longitude: float
    order_position: int
    description: Optional[str] = None

# --- Клиент API для test.logiways.ru ---
class LogiwaysClient:
    def __init__(self, base_url: str = "https://test.logiways.ru"):
        self.base_url = base_url.rstrip("/")
        self.tokens: Optional[Tokens] = None
        self.session = requests.Session()
        # Отключаем проверку SSL для тестового стенда (как в оригинале)
        self.session.verify = False
        # Подавляем предупреждения о SSL
        requests.packages.urllib3.disable_warnings()

    def _headers(self) -> Dict[str, str]:
        """Формирование заголовков с токеном авторизации."""
        headers = {
            "accept": "application/json"
        }
        if self.tokens:
            headers["authorization"] = f"{self.tokens.access_token}"
        return headers

    def _handle_401(self, func, *args, **kwargs):
        """Обработка 401 ошибки с попыткой обновить токен."""
        if not self.refresh_token():
            print("Не удалось обновить токен.")
            return None
        # Повторяем исходный запрос с новым токеном
        return func(*args, **kwargs)

    # --- Методы аутентификации (без изменений, но URL теперь ведут на test.) ---
    def signup(self, first_name: str, last_name: str, phone: str, middle_name: Optional[str] = None) -> Optional[Tokens]:
        url = f"{self.base_url}/api/users/signup"
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "middle_name": middle_name
        }
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            self.tokens = Tokens(**data)
            return self.tokens
        except requests.exceptions.RequestException as e:
            print(f"Ошибка регистрации: {e}")
            return None

    def request_sms(self, phone: str) -> Optional[Dict]:
        url = f"{self.base_url}/api/users/request-sms"
        payload = {"phone": phone, "test": True}
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка запроса SMS: {e}")
            return None

    def verify_sms(self, phone_number: str, code: str) -> Optional[Tokens]:
        url = f"{self.base_url}/api/users/verify-sms"
        payload = {"phone_number": phone_number, "code": code}
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            self.tokens = Tokens(**data)
            return self.tokens
        except requests.exceptions.RequestException as e:
            print(f"Ошибка верификации SMS: {e}")
            return None

    def refresh_token(self) -> Optional[Tokens]:
        if not self.tokens or not self.tokens.refresh_token:
            print("Нет refresh_token для обновления")
            return None
        url = f"{self.base_url}/api/users/refresh-token"
        payload = {"refresh_token": self.tokens.refresh_token}
        try:
            response = self.session.post(url, json=payload)
            if response.status_code == 401:
                print("refresh_token недействителен")
                return None
            response.raise_for_status()
            data = response.json()
            self.tokens = Tokens(**data)
            return self.tokens
        except requests.exceptions.RequestException as e:
            print(f"Ошибка обновления токена: {e}")
            return None

    # --- Создание транспортной компании ---
    def create_transport_companies(self, transport_companies: TransportCompaniesCreate) -> Optional[Dict]:
        """
        Создает организацию (бывшую транспортную компанию).
        POST /admin/transport-companies
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/transport-companies"
        payload = asdict(transport_companies)
        try:
            response = self.session.post(url, json=payload, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.create_transport_companies, transport_companies)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка создания организации: {e}")
            if response:
                print(f"Ответ сервера: {response.text}")
            return None

    # --- Создание локации ---
    def create_locations(self, location: LocationsCreate) -> str:
        """
        Создает организацию (бывшую транспортную компанию).
        POST /admin/locations
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/locations"
        payload = asdict(location)
        payload = {
            k: v.value if hasattr(v, 'value') else v
            for k, v in payload.items()
        }
        try:
            response = self.session.post(url, json=payload, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.create_locations, location)
            response.raise_for_status()
            res = response.json()
            loc_id = res.get("id", None)
            #print(f"✅ create_locations: {location.name} ({location.location_type}, {location.country_code}) -> id={loc_id}")
            return loc_id
        except requests.exceptions.RequestException as e:
            print(f"Ошибка создания локации: {e}")
            if 'response' in locals() and response is not None:
                print(f"Ответ сервера: {response.status_code} {response.text}")
            return None

    # --- Получение организации по ID ---
    def get_transport_company_by_name(self, company_search: str) -> str:
        """
        Поиск транспортной организации по названию.
        GET /admin/transport-companies
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        company_search = str(company_search or "").strip()
        company_search_clean = company_search.strip()
        url = f"{self.base_url}/admin/transport-companies?search={company_search_clean}"
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_transport_company_by_name, company_search)
            if response.status_code == 404:
                print(f"  Компания '{company_search}' не найдена (404).")
                return None
            response.raise_for_status()
            res = response.json()
            items = res.get("items",[])

            # Точное совпадение
            for item in items:
                if item.get("name","").strip() == company_search_clean:
                    print(f"  ✓ Найдена компания: {item.get('name')} (ID={item['id'][:8]}...)")
                    return item["id"]

            # Если точного совпадения нет, ищем частичное (игнорируя регистр)
            company_lower = company_search_clean.lower()
            for item in items:
                if company_lower in item.get("name","").lower():
                    print(f"  ✓ Найдена компания (partial match): {item.get('name')} (ID={item['id'][:8]}...)")
                    return item["id"]

            # Ничего не найдено
            if items:
                print(f"  ✗ Компания '{company_search}' не найдена. Доступные компании:")
                for item in items[:5]:
                    print(f"    - {item.get('name')}")
            else:
                print(f"  ✗ Компания '{company_search}' не найдена (поиск вернул пустой результат).")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Ошибка поиска компании '{company_search}': {e}")
            return None

    # --- Получение организации по ID ---
    def get_companies(self, company_id: str) -> Optional[Dict]:
        """
        Получает информацию об организации по ID.
        GET /admin/transport-companies/{companies_id}
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/transport-companies/{company_id}"
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_companies, company_id)
            if response.status_code == 404:
                print(f"Организация {company_id} не найдена.")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения организации: {e}")
            return None

    # --- Ищет ID локации по имени ---
    def find_location_id_by_name(self, location_name: str, location_type: str, country_code: str, parent_location_id: str = None) -> str:
        """
        Ищет ID локации по имени и типу. Если не нашёл — создаёт.
        Для level-2 (порт/станция) parent_location_id = ID города.
        Для города (level-1) parent_location_id = None, country_code обязателен.
        """
        if not self.tokens:
            print("  LOC [FIND] Требуется аутентификация")
            return None

        normalized_cc = normalize_country_code(country_code)
        print(f"  LOC [FIND] name='{location_name}' type='{location_type}' country='{country_code}' -> cc='{normalized_cc}' parent='{parent_location_id}'")

        # Поиск по имени+тип+страна (не по стране одной!)
        url = f"{self.base_url}/admin/locations?search={location_name}&limit=500"
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.find_location_id_by_name, location_name, location_type, country_code, parent_location_id)
            response.raise_for_status()
            res = response.json()
            locations = res.get("items", [])
            print(f"  LOC [SEARCH] Нашёл {len(locations)} по запросу '{location_name}'")

            for loc in locations:
                loc_name = loc.get('name', '').lower()
                loc_type = loc.get('location_type', '').lower()
                loc_parent = loc.get('parent_location_id')
                loc_cc = loc.get('country_code')

                # Проверяем совпадение имени И типа локации
                if loc_name != location_name.lower():
                    print(f"    SKIP '{loc.get('name')}' name mismatch")
                    continue

                if loc_type != location_type.lower():
                    print(f"    SKIP '{loc.get('name')}' type mismatch: expected '{location_type}', got '{loc_type}'")
                    continue

                # Проверяем parent и country_code
                cc_match = (loc_cc == normalized_cc)
                parent_match = (parent_location_id is None or loc_parent == parent_location_id)
                print(f"    MATCH '{loc.get('name')}' type='{loc_type}' parent={loc_parent} cc={loc_cc} -> cc_match={cc_match} parent_match={parent_match}")
                if cc_match and parent_match:
                    print(f"  LOC [FOUND] id={loc['id']}")
                    return loc['id']

            # Не нашли — создаём
            print(f"  LOC [CREATE] name='{location_name}' type='{location_type}' country='{normalized_cc}' parent='{parent_location_id}'")
            loc_obj = LocationsCreate(
                name=location_name,
                country_code=normalized_cc,
                location_type=location_type,
                parent_location_id=parent_location_id
            )
            loc_id = self.create_locations(loc_obj)
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            return loc_id
        except requests.exceptions.RequestException as e:
            print(f"  LOC [ERROR] {e}")
            if 'response' in locals() and response is not None:
                print(f"  LOC [ERROR] Ответ: {response.status_code} {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Ошибка поиска/создания страны-города {country_name}: {e}")
            return None
    
    def get_route_segments(self, transport_company_id: str) -> Optional[List[Dict]]:
        """
        Получает сегменты маршрутов компании.
        GET /admin/route-segments
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None

        url = f"{self.base_url}/admin/route-segments?transport_company_id={transport_company_id}"

        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_route_segments, transport_company_id)
            response.raise_for_status()
            res = response.json()
            return res.get("items", [])
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения сегментов: {e}")
            return None

    def ensure_route_segment_id(self, transport_company_id: str, local_segment_key: str, known_segment_id: str = None, retries: int = 5, sleep_seconds: float = 1.0) -> Optional[str]:
        """
        Проверяет существование сегмента и возвращает актуальный ID.

        Если сегмент не находится по известному ID, пробуем найти его по segment_key
        через GET /admin/route-segments. Это помогает при задержках после replace_route_segments.
        """
        if not transport_company_id:
            return None

        for attempt in range(retries):
            segments = self.get_route_segments(transport_company_id)
            if segments is None:
                print(f"Попытка {attempt + 1}/{retries}: не удалось получить сегменты для компании {transport_company_id}")
                time.sleep(sleep_seconds)
                continue

            # Сначала проверка известного ID сегмента
            if known_segment_id:
                for seg in segments:
                    if seg.get("id") == known_segment_id:
                        return known_segment_id

            # Ищем по local_segment_key
            for seg in segments:
                if seg.get("segment_key") == local_segment_key:
                    if seg.get("id"):
                        return seg.get("id")

            print(f"Попытка {attempt + 1}/{retries}: сегмент {local_segment_key} не найден в компании {transport_company_id}")
            time.sleep(sleep_seconds)

        return None

    def get_segment_by_key(self, transport_company_id: str, segment_key: str):
        segments = self.get_route_segments(transport_company_id)
        if not segments:
            return None
        
        for seg in segments:
            if seg.get("segment_key") == segment_key:
                return seg
        return None

    def create_stopovers(self, segment_id: str, stopovers_location_id: str, sequence: int = 0, wait_min_days: int = 0, wait_max_days: int = 0):
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/route-segments/{segment_id}/stopovers"
        headers = self._headers()
        payload = {
            "location_id": stopovers_location_id,
            "sequence": sequence,
            "wait_min_days": wait_min_days,
            "wait_max_days": wait_max_days,
            "stopover_kind": "transshipment"
        }
        try:
            response = self.session.put(url, json=payload, headers=headers)
            if response.status_code == 401:
                return self._handle_401(self.create_stopovers, payload)
            if response.status_code == 403:
                print("Ошибка 403: Недостаточно прав. Убедитесь, что у пользователя есть роль администратора.")
                print(f"Ответ сервера: {response.text}")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка создания stopovers: {e}")
            if 'response' in locals() and response:
                print(f"Ответ сервера: {response.text}")
            return None
    
    def create_departures(self, segment_id: str, departures: List[Departure]):
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/route-segments/{segment_id}/departures"
        headers = self._headers()
        payload = [asdict(d) for d in departures]
        #payload = [asdict(departures)]
        try:
            response = self.session.put(url, json=payload, headers=headers)
            if response.status_code == 401:
                return self._handle_401(self.create_departures, segment_id, departures)
            if response.status_code == 403:
                print("Ошибка 403: Недостаточно прав. Убедитесь, что у пользователя есть роль администратора.")
                print(f"Ответ сервера: {response.text}")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка создания departures: {e}")
            if 'response' in locals() and response is not None:
                print(f"Ответ сервера: {response.text}")
            return None
    # --- Создание сегментов маршрута ---
    def replace_route_segments(self, segments_bulk: Dict) -> Optional[List[Dict]]:
        """
        Заменяет (массово создает/обновляет) сегменты для транспортной компании.
        POST /admin/route-segments
        ВНИМАНИЕ: этот метод заменяет ВСЕ существующие сегменты компании на новые.
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/route-segments"
        headers = self._headers()

        company_id = segments_bulk.get("transport_company_id", "UNKNOWN")
        num_segments = len(segments_bulk.get("segments", []))
        print(f"[DEBUG] Отправка {num_segments} сегментов для ТК: {company_id}")

        try:
            response = self.session.post(url, json=segments_bulk, headers=headers)
            if response.status_code == 401:
                return self._handle_401(self.replace_route_segments, segments_bulk)
            if response.status_code == 403:
                print("Ошибка 403: Недостаточно прав. Убедитесь, что у пользователя есть роль администратора.")
                print(f"Ответ сервера: {response.text}")
                return None
            if response.status_code == 422:
                print(f"[ERR 422] Ошибка валидации при загрузке сегментов для ТК {company_id}")
                print(f"[ERR 422] Количество сегментов: {num_segments}")
                print(f"[ERR 422] Ответ сервера:")
                try:
                    err_data = response.json()
                    import json
                    print(json.dumps(err_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print(f"[ERR 422] Отправленные данные (первый сегмент для примера):")
                if num_segments > 0:
                    import json
                    print(json.dumps(segments_bulk["segments"][0], indent=2, ensure_ascii=False))
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Ошибка создания сегментов для ТК {company_id}: {e}")
            print(f"[ERR] Статус код: {response.status_code if response else 'No response'}")
            if response:
                print(f"[ERR] Ответ сервера:")
                try:
                    err_data = response.json()
                    import json
                    print(json.dumps(err_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
            return None
    
    def create_tariffs(self, segment_id: str, tariffs: TariffCreate) -> Optional[Dict]:
        """
        Создает тарифы для сегмента.

        POST /admin/route-segments/{segment_id}/tariffs
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None

        url = f"{self.base_url}/admin/route-segments/{segment_id}/tariffs"
        payload = asdict(tariffs)

        # Удаляем поля, которые не нужны или не должны передаваться
        payload.pop("drop_off_location_id", None)

        # Убираем пустые значения, чтобы не ломать бэкенд в неожиданных кейсах.
        payload = {
            k: v for k, v in payload.items()
            if v is not None
            and not (isinstance(v, (list, dict)) and len(v) == 0)
        }

        # Рекурсивно чистим null внутри вложенных списков (weight_bands и т.д.)
        for key, val in payload.items():
            if isinstance(val, list):
                payload[key] = [
                    {k: v for k, v in item.items() if v is not None}
                    if isinstance(item, dict) else item
                    for item in val
                ]

        try:
            response = self.session.post(url, json=payload, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.create_tariffs, segment_id, tariffs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка создания тарифов: {e}")
            if 'response' in locals() and response is not None:
                print(response.text)
            return None
        
    def get_segment_tariffs(self, segment_id: str):
        url = f"{self.base_url}/admin/route-segments/{segment_id}/tariffs"
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_segment_tariffs, segment_id)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения тарифов: {e}")
            return None
    
    def update_tariff(self, tariff: TariffUpdate):
        url = f"{self.base_url}/admin/tariffs/{tariff.id}"
        payload = asdict(tariff)
        try:
            response = self.session.patch(
                url,
                json=payload,
                headers=self._headers()
            )
            if response.status_code == 401:
                return self._handle_401(self.update_tariff, tariff)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка обновления тарифа: {e}")
            return None

    def update_tariff_dropoff_locations(self, tariff_id: str, dropoffs: List[dict]) -> Optional[List[Dict]]:
        """PUT /admin/tariffs/{tariff_id}/dropoff-locations — полная замена drop-off локаций тарифа."""
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/tariffs/{tariff_id}/dropoff-locations"
        headers = self._headers()
        try:
            response = self.session.put(url, json=dropoffs, headers=headers)
            if response.status_code == 401:
                return self._handle_401(self.update_tariff_dropoff_locations, tariff_id, dropoffs)
            if response.status_code == 404:
                print(f"Тариф {tariff_id} не найден.")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка обновления drop-off локаций: {e}")
            if 'response' in locals() and response is not None:
                print(f"Ответ сервера: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Ошибка обновления тарифа: {e}")
            return None

    def update_route_segment_coordinates(
        self, 
        route_segment_id: str, 
        coordinates: List[RouteSegmentCoordinate]
    ) -> Optional[Dict]:
        """
        Обновляет координаты маршрутного сегмента через PUT запрос.
        
        PUT /admin/route-segments/{route_segment_id}/coordinates
        
        Args:
            route_segment_id: ID маршрутного сегмента
            coordinates: Список объектов RouteSegmentCoordinate с координатами и позициями
        
        Returns:
            Ответ от сервера или None при ошибке
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None

        url = f"{self.base_url}/admin/route-segments/{route_segment_id}/coordinates"
        
        # Преобразуем dataclass объекты в словари
        payload = []
        for coord in coordinates:
            coord_dict = asdict(coord)
            # Удаляем None значения для необязательных полей
            if coord_dict.get('description') is None:
                del coord_dict['description']
            payload.append(coord_dict)
        
        try:
            response = self.session.put(
                url,
                json=payload,
                headers=self._headers()
            )
            if response.status_code == 401:
                return self._handle_401(self.update_route_segment_coordinates, route_segment_id, coordinates)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка обновления координат сегмента: {e}")
            if 'response' in locals() and response.text:
                print(f"Ответ сервера: {response.text}")
            return None

    def get_route_segment_coordinates(self, route_segment_id: str) -> Optional[List[Dict]]:
        """
        Получает существующие координаты маршрутного сегмента через GET запрос.
        
        GET /admin/route-segments/{route_segment_id}/coordinates
        
        Args:
            route_segment_id: ID маршрутного сегмента
        
        Returns:
            Список координат или None при ошибке
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None

        url = f"{self.base_url}/admin/route-segments/{route_segment_id}/coordinates"
        
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_route_segment_coordinates, route_segment_id)
            if response.status_code == 404:
                print(f"Координаты для сегмента {route_segment_id} не найдены (404)")
                return []
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения координат сегмента: {e}")
            if 'response' in locals() and response.text:
                print(f"Ответ сервера: {response.text}")
            return None

    # Маппинг ISO2 → названия стран для Yandex Geocoder
    _COUNTRY_NAME_MAP: Dict[str, str] = {
        "RU": "Россия",
        "CN": "Китай",
        "AE": "ОАЭ",
        "TR": "Турция",
        "US": "США",
        "IN": "Индия",
        "KZ": "Казахстан",
        "UZ": "Узбекистан",
        "BY": "Беларусь",
        "KR": "Южная Корея",
        "JP": "Япония",
        "TH": "Таиланд",
        "VN": "Вьетнам",
        "MY": "Малайзия",
        "SG": "Сингапур",
        "ID": "Индонезия",
        "SA": "Саудовская Аравия",
        "EG": "Египет",
        "IL": "Израиль",
        "GB": "Великобритания",
        "DE": "Германия",
        "FR": "Франция",
        "IT": "Италия",
        "ES": "Испания",
        "BR": "Бразилия",
        "MN": "Монголия",
        "GE": "Грузия",
        "UA": "Украина",
        "KP": "Северная Корея",
        "TW": "Тайвань",
        "HK": "Гонконг",
    }

    def _iso2_to_country_name(self, country_code: str) -> str:
        """Преобразует ISO2 код страны в название для Yandex Geocoder."""
        code = country_code.strip().upper()
        return self._COUNTRY_NAME_MAP.get(code, country_code)

    def geocode_location(
        self,
        location_name: str,
        country_code: Optional[str] = None,
        region: Optional[str] = None,
        yandex_api_key: Optional[str] = None,
        yandex_lang: str = "ru_RU"
    ) -> Optional[RouteSegmentCoordinate]:
        """
        Геокодирует локацию через Yandex Geocoder API.
        Возвращает первую найденную координату.

        Args:
            location_name: Название локации (город, порт, станция и т.д.)
            country_code: ISO2 код страны (RU, CN и т.д.) или название страны — опционально
            region: Регион/область - опционально
            yandex_api_key: API ключ Yandex. Если не указан, берется из ENV YANDEX_API_KEY
            yandex_lang: Язык ответа (ru_RU или en_US)

        Returns:
            RouteSegmentCoordinate с координатами или None если не найдено
        """
        try:
            from geocode_locations_yandex_toponyms import YandexGeocoder
        except ImportError:
            print("Ошибка: необходимо установить зависимости для геокодирования")
            print("pip install requests pycountry Babel")
            return None

        if not yandex_api_key:
            yandex_api_key = os.getenv("YANDEX_API_KEY") or os.getenv("GEOCODER_API_KEY")

        if not yandex_api_key:
            print("⚠ API ключ не найден в ENV, использую ключ по умолчанию")
            yandex_api_key = "86ed004b-4bda-4f02-91ea-6a19db02e31a"

        if not yandex_api_key:
            print("Ошибка: не указан API ключ Yandex. Передайте yandex_api_key или установите ENV переменную YANDEX_API_KEY")
            return None

        # Логируем ключ (первые 8 символов) для отладки
        key_preview = yandex_api_key[:8] + "..." if len(yandex_api_key) > 8 else "***"
        print(f"  Yandex API ключ: {key_preview}")

        try:
            geocoder = YandexGeocoder(api_key=yandex_api_key, lang=yandex_lang)

            # Преобразуем ISO2 код страны в название для Yandex
            country_name = self._iso2_to_country_name(country_code) if country_code else None

            # Строим поисковый запрос: "порт Шанхай, Китай"
            query_parts = [location_name]
            if region:
                query_parts.append(region)
            if country_name:
                query_parts.append(country_name)

            query = ", ".join(query_parts)

            print(f"Геокодирование: {query}")
            result = geocoder.geocode(query=query)

            if result:
                print(f"[OK] Найдено: {result.display_name} ({result.latitude}, {result.longitude})")
                return RouteSegmentCoordinate(
                    latitude=result.latitude,
                    longitude=result.longitude,
                    order_position=0,
                    description=result.display_name
                )
            else:
                print(f"[ERR] Не найдено координат для: {query}")
                return None

        except Exception as e:
            print(f"Ошибка геокодирования: {e}")
            return None

    # --- Получение локации по ID ---
    def get_location_by_id(self, location_id: str) -> Optional[Dict]:
        """
        Получает информацию о локации по ID.
        GET /admin/locations/{location_id}
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None
        url = f"{self.base_url}/admin/locations/{location_id}"
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_location_by_id, location_id)
            if response.status_code == 404:
                print(f"Локация {location_id} не найдена.")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения локации: {e}")
            return None

    # --- Получение всех локаций (пагинированный список) ---
    def get_all_locations(self, limit: int = 500) -> List[Dict]:
        """
        Получает список всех локаций.
        GET /admin/locations?limit={limit}
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return []
        url = f"{self.base_url}/admin/locations?limit={limit}"
        all_items = []
        try:
            response = self.session.get(url, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.get_all_locations, limit)
            response.raise_for_status()
            res = response.json()
            all_items = res.get("items", [])
            return all_items
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения списка локаций: {e}")
            return []

    # --- Обновление координат локации ---
    def update_location_coordinates(self, location_id: str, latitude: float, longitude: float) -> Optional[Dict]:
        """
        Обновляет координаты конкретной локации.
        PUT /admin/locations/{location_id}

        Логика определения координат:
        1. Если передали координаты - используем их
        2. Если нет (или None) - пытаемся взять у родителя
        3. Если нет родителя или у него нет координат - используем переданные
        4. Дочерние не-города получат эти же координаты в отдельном запросе
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None

        url = f"{self.base_url}/admin/locations/{location_id}"
        existing = self.get_location_by_id(location_id)
        if not existing:
            print(f"Не удалось получить данные локации {location_id} для обновления координат")
            return None

        # Определяем финальные координаты
        final_latitude = latitude
        final_longitude = longitude
        loc_name = existing.get("name", "")
        loc_type = existing.get("location_type", "").upper()

        # Если координаты не переданы - пытаемся взять у родителя
        if (latitude is None or longitude is None) or (latitude == 0 and longitude == 0):
            parent_id = existing.get("parent_location_id")
            if parent_id:
                parent = self.get_location_by_id(parent_id)
                if parent:
                    parent_lat = parent.get("latitude")
                    parent_lon = parent.get("longitude")
                    if parent_lat is not None and parent_lon is not None:
                        final_latitude = parent_lat
                        final_longitude = parent_lon
                        print(f"  [COORD] '{loc_name}' ({loc_type}) → координаты с родителя")

        payload = {
            "name": existing.get("name"),
            "location_type": existing.get("location_type"),
            "latitude": final_latitude,
            "longitude": final_longitude,
        }
        # Добавляем необязательные поля, если они есть
        for field in ("country_code", "region", "parent_location_id", "external_codes"):
            if existing.get(field) is not None:
                payload[field] = existing[field]

        try:
            response = self.session.put(url, json=payload, headers=self._headers())
            if response.status_code == 401:
                return self._handle_401(self.update_location_coordinates, location_id, latitude, longitude)
            response.raise_for_status()
            result = response.json()

            # Если это город с координатами - применяем координаты всем дочерним не-городам
            if loc_type == "CITY" and final_latitude is not None and final_longitude is not None:
                self._propagate_coordinates_to_children(location_id, final_latitude, final_longitude)

            return result
        except requests.exceptions.RequestException as e:
            print(f"Ошибка обновления координат локации {location_id}: {e}")
            if 'response' in locals() and response is not None:
                print(f"Ответ сервера: {response.status_code} {response.text}")
            return None

    def _propagate_coordinates_to_children(self, parent_id: str, latitude: float, longitude: float) -> None:
        """
        Применяет координаты родителя ко всем дочерним не-городам (портам, станциям и т.д.)
        """
        try:
            all_locations = self.get_all_locations()
            if not all_locations:
                return

            children = [loc for loc in all_locations
                       if loc.get("parent_location_id") == parent_id
                       and loc.get("location_type", "").upper() != "CITY"]

            for child in children:
                child_id = child.get("id")
                child_name = child.get("name", "")
                child_type = child.get("location_type", "")
                if child_id:
                    self.update_location_coordinates(child_id, latitude, longitude)
                    print(f"  [COORD] '{child_name}' ({child_type}) ← унаследованы от родителя")
        except Exception as e:
            print(f"Ошибка при распространении координат на дочерние локации: {e}")

    def geocode_and_update_segment_coordinates(
        self,
        route_segment_id: str,
        locations: List[Dict[str, str]],
        yandex_api_key: Optional[str] = None,
        yandex_lang: str = "ru_RU",
        sleep_between_requests: float = 0.2,
        force_update: bool = False
    ) -> Optional[Dict]:
        """
        Геокодирует список локаций и обновляет координаты маршрутного сегмента.
        Проверяет существующие координаты, чтобы избежать лишних вызовов API геокодирования.
        
        Args:
            route_segment_id: ID маршрутного сегмента
            locations: Список словарей с полями:
                - name: Название локации (обязательно)
                - country_code: ISO2 код страны (опционально)
                - region: Регион (опционально)
                - description: Описание для координаты (опционально)
            yandex_api_key: API ключ Yandex
            yandex_lang: Язык ответа
            sleep_between_requests: Пауза между запросами в секундах
            force_update: Принудительно обновить координаты, даже если они уже существуют
        
        Returns:
            Ответ от сервера при успехе или None при ошибке
        
        Example:
            locations = [
                {"name": "Шанхай", "country_code": "CN", "description": "Начальная точка"},
                {"name": "Владивосток", "country_code": "RU", "region": "Приморский край"},
                {"name": "Москва", "country_code": "RU"}
            ]
            result = client.geocode_and_update_segment_coordinates(
                route_segment_id="seg_123",
                locations=locations
            )
        """
        if not self.tokens:
            print("Требуется аутентификация")
            return None

        # Проверяем существующие координаты
        if not force_update:
            existing_coordinates = self.get_route_segment_coordinates(route_segment_id)
            if existing_coordinates is not None and len(existing_coordinates) > 0:
                print(f"[OK] Координаты для сегмента {route_segment_id} уже существуют ({len(existing_coordinates)} точек). Пропускаем геокодирование.")
                print("Используйте force_update=True для принудительного обновления.")
                return {"status": "coordinates_already_exist", "count": len(existing_coordinates)}
            elif existing_coordinates is None:
                print("Не удалось проверить существующие координаты. Продолжаем с геокодированием...")

        coordinates = []
        
        for order_pos, location in enumerate(locations):
            location_name = location.get("name")
            if not location_name:
                print(f"Ошибка: локация #{order_pos} не содержит 'name'")
                continue
            
            coord = self.geocode_location(
                location_name=location_name,
                country_code=location.get("country_code"),
                region=location.get("region"),
                yandex_api_key=yandex_api_key,
                yandex_lang=yandex_lang
            )
            
            if coord:
                # Переопределяем description если указан в location
                if location.get("description"):
                    coord.description = location.get("description")
                
                coord.order_position = order_pos
                coordinates.append(coord)
            
            # Пауза между запросами к Yandex API
            time.sleep(sleep_between_requests)
        
        if not coordinates:
            print("Ошибка: не удалось геокодировать ни одну локацию")
            return None
        
        print(f"\nОтправка {len(coordinates)} координат на сервер...")
        return self.update_route_segment_coordinates(route_segment_id, coordinates)

def fill_location_coordinates(
    client: LogiwaysClient,
    location_ids: Optional[List[str]] = None,
    yandex_api_key: Optional[str] = None,
    sleep_between_requests: float = 0.3,
    force_update: bool = False,
    country_filter: Optional[str] = None,
    limit: Optional[int] = None,
    prefer_parent_coords: bool = True,
) -> Dict[str, Any]:
    """
    Проверяет, есть ли у локаций координаты в БД.
    Если координат нет — использует координаты родителя или запрашивает через Yandex Geocoder.

    Args:
        client: Инициализированный и аутентифицированный LogiwaysClient
        location_ids: Конкретные ID локаций для проверки. Если None — проверяет все локации
        yandex_api_key: API ключ Yandex Geocoder. Если None, берётся из ENV
        sleep_between_requests: Пауза между запросами к Yandex API (секунды)
        force_update: Если True — обновляет координаты даже если они уже есть
        country_filter: ISO2 код страны для фильтрации (например 'RU')
        limit: Максимальное количество локаций для обработки
        prefer_parent_coords: Если True — использует координаты родителя для не-городов.
                             Только если у родителя нет координат — запрашивает у Яндекса

    Returns:
        Словарь со статистикой: {processed, resolved, skipped, errors, unresolved}

    Example:
        client = LogiwaysClient("https://test.logiways.ru")
        # ... аутентификация ...
        result = fill_location_coordinates(client, country_filter="RU", limit=50, prefer_parent_coords=True)
        print(result)
    """
    if not client.tokens:
        print("Ошибка: клиент не аутентифицирован. Выполните вход перед вызовом.")
        return {"processed": 0, "resolved": 0, "skipped": 0, "errors": 0, "unresolved": 0}

    # --- Определяем список локаций для обработки ---
    if location_ids is not None:
        # Получаем конкретные локации по ID
        locations = []
        for loc_id in location_ids:
            loc_data = client.get_location_by_id(loc_id)
            if loc_data:
                locations.append(loc_data)
            time.sleep(sleep_between_requests)
    else:
        # Получаем все локации
        locations = client.get_all_locations()
        if country_filter:
            locations = [loc for loc in locations if loc.get("country_code", "").upper() == country_filter.upper()]
        if limit:
            locations = locations[:limit]

    if not locations:
        print("Нет локаций для обработки.")
        return {"processed": 0, "resolved": 0, "skipped": 0, "errors": 0, "unresolved": 0}

    print(f"\n=== Заполнение координат локаций ===")
    print(f"Всего локаций для проверки: {len(locations)}")

    stats = {"processed": 0, "resolved": 0, "skipped": 0, "errors": 0, "unresolved": 0}
    unresolved_list = []

    for loc in locations:
        loc_id = loc.get("location_id") or loc.get("id")
        loc_name = loc.get("name", "unknown")
        loc_type = loc.get("location_type", "unknown")
        loc_cc = loc.get("country_code")
        loc_region = loc.get("region")
        loc_parent_id = loc.get("parent_location_id")

        if not loc_id:
            print(f"  SKIP: локация без ID — {loc_name}")
            stats["skipped"] += 1
            continue

        stats["processed"] += 1

        # --- Проверяем, есть ли уже координаты ---
        lat = loc.get("latitude")
        lon = loc.get("longitude")

        has_coords = (
            lat is not None and lon is not None
            and str(lat).strip() != "" and str(lon).strip() != ""
        )
        if has_coords and force_update:
            print(f"  [{stats['processed']}/{len(locations)}] OVERWRITE {loc_type} | {loc_name} | старые координаты ({lat}, {lon})")
        
        if has_coords and not force_update:
            print(f"  [{stats['processed']}/{len(locations)}] SKIP {loc_type} | {loc_name} | уже есть координаты ({lat}, {lon})")
            stats["skipped"] += 1
            continue

        # --- Получаем имя родителя для более точного запроса ---
        parent_name = None
        parent_lat = None
        parent_lon = None
        if loc_parent_id:
            parent_data = client.get_location_by_id(loc_parent_id)
            if parent_data:
                parent_name = parent_data.get("name")
                parent_lat = parent_data.get("latitude", None)
                parent_lon = parent_data.get("longitude", None)
            time.sleep(sleep_between_requests)

        # --- Геокодируем ---
        query_parts = []
        # Добавляем тип локации для точности
        type_labels = {
            "city": "город",
            "port": "порт",
            "rail_station": "станция",
            "terminal": "терминал",
            "warehouse": "склад",
            "border": "граница",
            "dropoff": "пункт выдачи",
            "customs": "таможня",
        }
        type_label = type_labels.get(loc_type, "")
        if type_label:
            query_parts.append(f"{type_label} {loc_name}")
        else:
            query_parts.append(loc_name)

        if parent_name:
            query_parts.append(parent_name)
        if loc_region:
            query_parts.append(loc_region)

        query = ", ".join(query_parts)

        print(f"  [{stats['processed']}/{len(locations)}] GEOCODE {loc_type} | {loc_name} | query='{query}'")

        # Определяем источник координат
        coord = None

        # Если нужно предпочитать координаты родителя и они есть
        if (prefer_parent_coords and parent_lat is not None and parent_lon is not None
            and loc_type.lower() != "city" and loc_parent_id):
            print(f"    [COORD] Берём координаты родителя '{parent_name}': ({parent_lat}, {parent_lon})")
            coord = RouteSegmentCoordinate(
                latitude=parent_lat,
                longitude=parent_lon,
                order_position=0,
                description=f"Унаследованы от родителя: {parent_name}"
            )

        # Если координаты родителя не подходят — запрашиваем у Яндекса
        if not coord:
            print(f"    [GEOCODE] Запрос к Yandex Geocoder...")
            coord = client.geocode_location(
                location_name=loc_name,
                country_code=loc_cc,
                region=loc_region,
                yandex_api_key=yandex_api_key,
                yandex_lang="ru_RU"
            )
        time.sleep(sleep_between_requests)

        if coord:
            print(f"    [OK] Найдено: {coord.latitude}, {coord.longitude} | {coord.description}")
            result = client.update_location_coordinates(loc_id, coord.latitude, coord.longitude)
            if result:
                print(f"    [OK] Координаты сохранены в БД")
                stats["resolved"] += 1
            else:
                print(f"    [ERR] Ошибка сохранения координат в БД")
                stats["errors"] += 1
        else:
            print(f"    [ERR] Не удалось найти координаты")
            stats["unresolved"] += 1
            unresolved_list.append({
                "id": loc_id,
                "name": loc_name,
                "type": loc_type,
                "country_code": loc_cc,
                "region": loc_region,
            })

        time.sleep(sleep_between_requests)

    print(f"\n=== Итого ===")
    print(f"  Обработано:  {stats['processed']}")
    print(f"  Найдено:     {stats['resolved']}")
    print(f"  Пропущено:   {stats['skipped']}")
    print(f"  Не найдено:  {stats['unresolved']}")
    print(f"  Ошибки:      {stats['errors']}")

    if unresolved_list:
        print(f"\nНе удалось геокодировать {len(unresolved_list)} локаций:")
        for u in unresolved_list:
            print(f"  - {u['name']} ({u['type']}, {u['country_code']})")

    return stats


def build_charges(row):
    return []

def build_weight_band(row):

    min_weight = row.get("min_weight_kg")
    max_weight = row.get("max_weight_kg")

    surcharge = row.get("overweight_surcharge_per_ton")
    surcharge_currency = row.get("overweight_surcharge_currency")
    if str(row["cost"]) == "-":
        return None
    return WeightBand(
        min_weight_kg=int(min_weight) if pd.notna(min_weight) else None,
        max_weight_kg=int(max_weight) if pd.notna(max_weight) else None,
        base_amount=int(row["cost"]),
        currency=row["currency"],
        overweight_surcharge_per_ton=str(surcharge) if pd.notna(surcharge) else None,
        overweight_surcharge_currency=surcharge_currency if pd.notna(surcharge_currency) else None
    )


def sync_child_locations_coordinates(
    client: LogiwaysClient,
    country_filter: Optional[str] = None,
    sleep_between_requests: float = 0.3,
) -> Dict[str, Any]:
    """
    Обновляет координаты всех не-городов (портов, станций и т.д.) на координаты их родителей.
    Если родитель имеет координаты - дочерняя локация получает те же координаты.
    """
    if not client.tokens:
        print("Ошибка: клиент не аутентифицирован.")
        return {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}

    print(f"\n=== Синхронизация координат дочерних локаций с родителями ===")

    all_locations = client.get_all_locations()
    if not all_locations:
        print("Нет локаций для обработки.")
        return {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}

    if country_filter:
        all_locations = [loc for loc in all_locations
                        if loc.get("country_code", "").upper() == country_filter.upper()]

    locations_map = {loc.get("id"): loc for loc in all_locations}
    child_locations = [
        loc for loc in all_locations
        if loc.get("location_type", "").upper() != "CITY"
        and loc.get("parent_location_id") is not None
    ]

    print(f"Всего локаций: {len(all_locations)}")
    print(f"Не-городов с родителями: {len(child_locations)}")

    stats = {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}

    for child_loc in child_locations:
        stats["processed"] += 1
        child_id = child_loc.get("id")
        child_name = child_loc.get("name", "unknown")
        child_type = child_loc.get("location_type", "unknown")
        parent_id = child_loc.get("parent_location_id")

        parent = locations_map.get(parent_id)
        if not parent:
            parent = client.get_location_by_id(parent_id)
            time.sleep(sleep_between_requests)

        if not parent:
            print(f"  [{stats['processed']}] SKIP {child_type} | {child_name} | родитель не найден")
            stats["skipped"] += 1
            continue

        parent_name = parent.get("name", "unknown")
        parent_lat = parent.get("latitude")
        parent_lon = parent.get("longitude")

        if parent_lat is None or parent_lon is None:
            print(f"  [{stats['processed']}] SKIP {child_type} | {child_name} | нет координат у родителя '{parent_name}'")
            stats["skipped"] += 1
            continue

        try:
            result = client.update_location_coordinates(child_id, parent_lat, parent_lon)
            if result:
                print(f"  [{stats['processed']}] ✓ {child_type} | {child_name} | ({parent_lat}, {parent_lon}) от '{parent_name}'")
                stats["updated"] += 1
            else:
                print(f"  [{stats['processed']}] ✗ {child_type} | {child_name} | ошибка обновления")
                stats["errors"] += 1
        except Exception as e:
            print(f"  [{stats['processed']}] ✗ {child_type} | {child_name} | {str(e)}")
            stats["errors"] += 1

        time.sleep(sleep_between_requests)

    print(f"\n=== Итого: обновлено {stats['updated']}, пропущено {stats['skipped']}, ошибок {stats['errors']} ===")
    return stats


def build_segments_from_excel_OLD(df, client, company_id):
    segments = []
    tariffs_by_segment = {}

    for _, row in df.iterrows():
        start_point = row["start_point"].split(",")
        end_point = row["end_point"].split(",")
        
        start_location = start_point[0]
        end_location = end_point[0]
        
        start_id = client.find_location_id_by_name(start_location)
        end_id = client.find_location_id_by_name(end_location)
        
        start_location_type = row.get("start_location_type", LocationType.CITY)
        end_location_type = row.get("end_location_type", LocationType.CITY)
        
        if start_loc_id is None:
            start_loc_obj = LocationsCreate(
                name=start_location,
                country_code=CountryCodeType(start_point[1]),
                location_type=start_location_type
            )
            start_loc_id = client.create_locations(start_loc_obj)
            
        if end_loc_id is None:
            end_loc_obj = LocationsCreate(
                name=end_location,
                country_code=CountryCodeType(end_point[1]),
                location_type=end_location_type
            )
            end_loc_id = client.create_locations(end_loc_obj)
        
        
        segment_key = build_segment_key(
            company_id,
            row["transport_type"],
            start_id,
            end_id
        )
        
        if not start_loc_id or not end_loc_id:
            print(f"Не удалось найти|создать ID локаций для строки {_}: {row.get('start_point')} -> {row.get('end_point')}. Пропускаем.")
            continue

        segment = RouteSegmentCreate(
            start_location_id=start_loc_id,
            end_location_id=end_loc_id,
            border_location_id=None,
            customs_location_id=None,
            transport_type=TransportType(row["transport_type"]),
            conditions=row.get('conditions', None),
            segment_key=segment_key
        )

        segments.append(segment)
        conditions = row["conditions"].replace("-","")
        
        container_ownership = ContainerOwnership.COC if "COC" in conditions \
                            else ContainerOwnership.SOC if "SOC" in conditions \
                            else ContainerOwnership.ANY
        
        port_service_term = PortServiceTermType.FIFO if "FIFO" in conditions \
                            else PortServiceTermType.FILO if "FILO" in conditions \
                            else PortServiceTermType.LIFO if "LIFO" in conditions \
                            else PortServiceTermType.LILO if "LILO" in conditions \
                            else None

        tariff = TariffCreate(
            container_type=ContainerType(row["container_type"]),
            container_ownership=container_ownership,
            port_service_term=port_service_term,
            price_kind="exact",
            charges=build_charges(row)
        )

        if segment_key not in tariffs_by_segment:
            tariffs_by_segment[segment_key] = []

        tariffs_by_segment[segment_key].append(tariff)

    return segments, tariffs_by_segment

# Допустимые container_type на сервере
_VALID_CONTAINER_TYPES = {"20DC", "20GP", "20RF", "20TK", "40HC", "40HQ", "40RF", "20TC", "20FR", "40OT"}

def get_value(value, default):
    if pd.isna(value):
        return default
    return value

def build_segments_from_excel(df, client, company_id_dict=None):
    """
    Построение сегментов (start + end + ТК), тарифов и dropoff-локаций.
    Dropoff-locations собираются из строк с полем `dropoff_location`.
    Stopovers-locations собираются из строк с полем `stopovers_location`.
    """
    segments = {}
    tariffs_by_segment = {}
    departures_by_segment = {}
    dropoffs_by_tariff_key = {}  # (segment_key, container_type, container_ownership, port_service_term) -> list
    stopovers_by_segment = {}  # segment_key -> list of {"location_id": ..., "sequence": ...}
    if company_id_dict is None:
        company_id_dict = {}
    location_cache = {}

    # Статистика
    rows_total = len(df)
    rows_processed = 0
    rows_skipped = 0
    companies_found = set()

    for index, row in df.iterrows():

        start_point = row["start_point"].split(",")
        end_point = row["end_point"].split(",")
        company_name = row["company"].strip()

        if company_name not in company_id_dict:
            company_id_dict[company_name] = client.get_transport_company_by_name(company_name)

        company_id = company_id_dict[company_name]

        # КРИТИЧНО: Пропускаем строки если компания не найдена в системе
        if company_id is None:
            rows_skipped += 1
            continue

        rows_processed += 1
        companies_found.add(company_name)

        start_location = start_point[0].strip()
        end_location = end_point[0].strip()

        start_country_code = normalize_country_code(start_point[1].strip()) if len(start_point) > 1 else None
        end_country_code = normalize_country_code(end_point[1].strip()) if len(end_point) > 1 else None

        parent_start_location = get_value(row.get("parent_start_location", None), None)
        parent_end_location = get_value(row.get("parent_end_location", None), None)

        parent_start_location_type = LocationType(get_value(row.get("parent_start_location_type", "city"), "city")).value
        parent_end_location_type = LocationType(get_value(row.get("parent_end_location_type", "city"), "city")).value

        start_location_type = LocationType(get_value(row.get("start_location_type", "city"), "city")).value
        end_location_type = LocationType(get_value(row.get("end_location_type", "city"), "city")).value

        # --- Dropoff location fields ---
        dropoff_loc = get_value(row.get("dropoff_location", None), None)
        dropoff_loc_type = get_value(row.get("dropoff_location_type", None), None)
        dropoff_loc_country = get_value(row.get("dropoff_location_country", None), None)

        # --- Stopovers location fields ---
        stopovers_loc = get_value(row.get("stopovers_location", None), None)
        stopovers_loc_type = get_value(row.get("stopovers_location_type", None), None)
        stopovers_loc_country = get_value(row.get("stopovers_location_country", None), None)
        stopovers_loc_sequence = get_value(row.get("sequence", 0), 0)
        parent_stopovers_loc = get_value(row.get("parent_stopovers_location", None), None)
        parent_stopovers_loc_type = LocationType(get_value(row.get("parent_stopovers_location_type", "city"), "city")).value

        parent_start_loc_id = None
        parent_end_loc_id = None

        # --- LOCATION CACHE (ключ = (name, type)) ---
        def cache_key(name, loc_type):
            return (name, loc_type)

        if parent_start_location is not None and cache_key(parent_start_location, parent_start_location_type) not in location_cache:
            parent_start_loc_id = client.find_location_id_by_name(parent_start_location, parent_start_location_type, start_country_code)
            location_cache[cache_key(parent_start_location, parent_start_location_type)] = parent_start_loc_id

        if parent_end_location is not None and cache_key(parent_end_location, parent_end_location_type) not in location_cache:
            parent_end_loc_id = client.find_location_id_by_name(parent_end_location, parent_end_location_type, end_country_code)
            location_cache[cache_key(parent_end_location, parent_end_location_type)] = parent_end_loc_id

        if cache_key(start_location, start_location_type) not in location_cache:
            if parent_start_location is not None:
                parent_start_loc_id = location_cache[cache_key(parent_start_location, parent_start_location_type)]
            start_loc_id = client.find_location_id_by_name(start_location, start_location_type, start_country_code, parent_start_loc_id)
            location_cache[cache_key(start_location, start_location_type)] = start_loc_id

        if cache_key(end_location, end_location_type) not in location_cache:
            if parent_end_location is not None:
                parent_end_loc_id = location_cache[cache_key(parent_end_location, parent_end_location_type)]
            end_loc_id = client.find_location_id_by_name(end_location, end_location_type, end_country_code, parent_end_loc_id)
            location_cache[cache_key(end_location, end_location_type)] = end_loc_id

        start_loc_id = location_cache[cache_key(start_location, start_location_type)]
        end_loc_id = location_cache[cache_key(end_location, end_location_type)]

        # Dropoff location resolution
        dropoff_loc_id = None
        if dropoff_loc:
            dropoff_cc = normalize_country_code(dropoff_loc_country) if dropoff_loc_country else None
            dropoff_type = LocationType(get_value(dropoff_loc_type, "dropoff")).value
            if cache_key(dropoff_loc, dropoff_type) not in location_cache:
                dropoff_loc_id = client.find_location_id_by_name(dropoff_loc, dropoff_type, dropoff_cc)
                location_cache[cache_key(dropoff_loc, dropoff_type)] = dropoff_loc_id
            else:
                dropoff_loc_id = location_cache[cache_key(dropoff_loc, dropoff_type)]

        # Stopovers location resolution
        stopovers_loc_id = None
        if stopovers_loc:
            stopovers_cc = normalize_country_code(stopovers_loc_country) if stopovers_loc_country else None
            parent_stopovers_loc_id = None
            # Resolve parent first
            if parent_stopovers_loc and cache_key(parent_stopovers_loc, parent_stopovers_loc_type) not in location_cache:
                parent_stopovers_loc_id = client.find_location_id_by_name(
                    parent_stopovers_loc, parent_stopovers_loc_type, stopovers_cc
                )
                location_cache[cache_key(parent_stopovers_loc, parent_stopovers_loc_type)] = parent_stopovers_loc_id
            elif parent_stopovers_loc:
                parent_stopovers_loc_id = location_cache[cache_key(parent_stopovers_loc, parent_stopovers_loc_type)]

            # Resolve stopovers location with parent
            if cache_key(stopovers_loc, stopovers_loc_type) not in location_cache:
                stopovers_loc_id = client.find_location_id_by_name(
                    stopovers_loc, stopovers_loc_type, stopovers_cc, parent_stopovers_loc_id
                )
                location_cache[cache_key(stopovers_loc, stopovers_loc_type)] = stopovers_loc_id
            else:
                stopovers_loc_id = location_cache[cache_key(stopovers_loc, stopovers_loc_type)]

        # --- SEGMENT KEY (simplified) ---
        transport_type_value = TransportType(row["transport_type"]).value

        duration_min_days = get_value(row.get("duration_min_days", None), None)
        duration_max_days = get_value(row.get("duration_max_days", None), None)
        if duration_min_days is not None:
            try:
                duration_min_days = int(duration_min_days)
            except (ValueError, TypeError):
                duration_min_days = None
        if duration_max_days is not None:
            try:
                duration_max_days = int(duration_max_days)
            except (ValueError, TypeError):
                duration_max_days = None

        segment_key = build_segment_key(
            company_id,
            transport_type_value,
            start_loc_id,
            end_loc_id,
        )

        segment = RouteSegmentCreate(
            start_location_id=start_loc_id,
            end_location_id=end_loc_id,
            transport_type=transport_type_value,
            duration_min_days=duration_min_days if duration_min_days is not None else 7,
            duration_max_days=duration_max_days if duration_max_days is not None else 10,
            conditions=get_value(row.get("conditions", None), None),
            segment_key=segment_key
        )

        if segment_key not in segments:
            segments[segment_key] = {
                "segments": [segment],
                "company_id": company_id
            }
        elif segment not in segments[segment_key]["segments"]:
            segments[segment_key]["segments"].append(segment)

        container_ownership = get_value(row.get("container_ownership", "ANY"), "ANY")
        if container_ownership is not None:
            container_ownership = ContainerOwnership(container_ownership).value

        port_service_term = get_value(row.get("port_service_term", None), None)
        if port_service_term is not None:
            port_service_term = PortServiceTermType(port_service_term).value

        weight_band = build_weight_band(row)
        if weight_band is None:
            continue

        # Пропускаем неподдерживаемые сервером container_type
        container_type_raw = row["container_type"]
        if container_type_raw not in _VALID_CONTAINER_TYPES:
            continue

        tariff_key = (
            segment_key,
            row["container_type"],
            container_ownership,
            port_service_term
        )

        if tariff_key not in tariffs_by_segment:
            tariffs_by_segment[tariff_key] = TariffCreate(
                container_type=container_type_raw,
                container_ownership=container_ownership,
                port_service_term=port_service_term,
                price_kind="exact",
                weight_bands=[]
            )

        tariffs_by_segment[tariff_key].weight_bands.append(weight_band)

        # Collect dropoff location for this tariff (deduplicate by location_id)
        if dropoff_loc and dropoff_loc_id:
            if tariff_key not in dropoffs_by_tariff_key:
                dropoffs_by_tariff_key[tariff_key] = {}
            if dropoff_loc_id not in dropoffs_by_tariff_key[tariff_key]:
                dropoffs_by_tariff_key[tariff_key][dropoff_loc_id] = {
                    "location_id": dropoff_loc_id,
                    "rule_kind": "included",
                    "included": True,
                    "notes": dropoff_loc,
                }

        # Collect stopovers for this segment
        if stopovers_loc and stopovers_loc_id:
            if segment_key not in stopovers_by_segment:
                stopovers_by_segment[segment_key] = {
                    "location_id": stopovers_loc_id,
                    "sequence": stopovers_loc_sequence,
                }

        departure = get_value(row.get("departures", None), None)

        if departure is not None:
            departure = eval(departure)
            departure_obj = Departure(
                rate_status="active",
                cut_off_date=convert_to_iso_date(departure.get("CUTOFF", None)),
                etd_date=convert_to_iso_date(departure.get("ETD", None)),
                eta_date=convert_to_iso_date(departure.get("ETA", None)),
                vessel=departure.get("vessel", None),
                voyage=departure.get("voyage_no", None),
                capacity_status=departure.get("capacity_status", None),
                source_row={}
            )

            if segment_key not in departures_by_segment:
                departures_by_segment[segment_key] = []

            if departure_obj not in departures_by_segment[segment_key]:
                departures_by_segment[segment_key].append(departure_obj)

    # Выводим статистику
    print(f"\n=== Статистика обработки Excel ===")
    print(f"  Всего строк: {rows_total}")
    print(f"  Обработано: {rows_processed}")
    print(f"  Пропущено: {rows_skipped}")
    print(f"  Компаний обработано: {len(companies_found)}")
    if companies_found:
        for company in sorted(companies_found):
            print(f"    - {company}")

    return segments, tariffs_by_segment, departures_by_segment, dropoffs_by_tariff_key, stopovers_by_segment


def upload_segments(client, segments):
    segments_by_company: Dict[str, List[RouteSegmentCreate]] = {}

    for local_segment_key, item in segments.items():
        company_id = str(item["company_id"])
        segments_by_company.setdefault(company_id, [])

        for seg in item.get("segments", []):
            segments_by_company[company_id].append(seg)

    seg_map: Dict[str, str] = {}

    for company_id, segs in segments_by_company.items():
        print(f"[STAGE3] Загрузка сегментов для ТК: {company_id}, количество: {len(segs)}")

        # Проверка на дублирующиеся segment_key и их дедупликация
        segment_keys_check = {}
        deduplicated_segs = []

        for s in segs:
            sk = s.segment_key
            if sk not in segment_keys_check:
                segment_keys_check[sk] = []
                deduplicated_segs.append(s)  # Берём первый сегмент для этого segment_key
            segment_keys_check[sk].append(s)

        duplicates = {k: v for k, v in segment_keys_check.items() if len(v) > 1}
        if duplicates:
            print(f"[WARN] Найдены дублирующиеся segment_key для ТК {company_id} (будут объединены):")
            for dup_key, dup_segs in duplicates.items():
                print(f"  segment_key: {dup_key}")
                for i, seg in enumerate(dup_segs, 1):
                    marker = "✓ ИСПОЛЬЗУЕТСЯ" if i == 1 else "✗ УДАЛЕН (дубликат)"
                    print(f"    [{i}] {marker} | transport={seg.transport_type}, start={seg.start_location_id}, end={seg.end_location_id}, conditions={seg.conditions}")

        seg_dicts: List[Dict[str, Any]] = []
        for s in deduplicated_segs:
            d = asdict(s)
            d.pop("segment_key", None)
            # Убираем None и пустые dict — сервер возвращает 422
            d = {k: v for k, v in d.items() if v is not None and not (isinstance(v, dict) and len(v) == 0)}
            seg_dicts.append(d)

        payload = {"transport_company_id": company_id, "segments": seg_dicts}
        created_segments = client.replace_route_segments(payload) or []

        if created_segments:
            print(f"[STAGE3] ✓ Успешно загружено {len(created_segments)} сегментов для ТК {company_id}")
        else:
            print(f"[STAGE3] ✗ Ошибка при загрузке сегментов для ТК {company_id}")

        for created in created_segments:
            created_id = created.get("id")
            if not created_id:
                print(f"[ERR] Сегмент не имеет ID в ответе сервера")
                continue

            recalc_segment_key = build_segment_key(
                company_id,
                created.get("transport_type"),
                created.get("start_location_id"),
                created.get("end_location_id")
            )

            if recalc_segment_key in segments:
                seg_map[recalc_segment_key] = created_id
                #print(f"[OK] Маппирован segment: {recalc_segment_key[:8]}... -> ID {created_id}")
            else:
                print(f"[ERR] Не найден segment_key в исходном словаре (calc={recalc_segment_key[:8]}...)")

    missing = [k for k in segments.keys() if k not in seg_map]
    if missing:
        for company_id in segments_by_company.keys():
            all_segments = client.get_route_segments(company_id) or []
            for created in all_segments:
                created_id = created.get("id")
                if not created_id:
                    continue
                recalc_segment_key = build_segment_key(
                    company_id,
                    created.get("transport_type"),
                    created.get("start_location_id"),
                    created.get("end_location_id")
                )

                if recalc_segment_key in segments:
                    seg_map[recalc_segment_key] = created_id
                    #print(f"[OK] Маппирован segment (fallback): {recalc_segment_key[:8]}... -> ID {created_id}")

    for segment_key, known_segment_id in list(seg_map.items()):
        company_id = segments.get(segment_key, {}).get("company_id")
        if not company_id:
            continue

        resolved_id = client.ensure_route_segment_id(company_id, segment_key, known_segment_id=known_segment_id)
        if resolved_id is None:
            print(f"[ERR] Сегмент {segment_key[:8]} не найден после проверки на бэкенде. Он будет пропущен.")
            seg_map.pop(segment_key, None)
            continue

        if resolved_id != known_segment_id:
            #print(f"↪ Обновляем ID сегмента {segment_key[:8]}: {known_segment_id} -> {resolved_id}")
            seg_map[segment_key] = resolved_id

    return seg_map

def upload_departures(client, segment_map, departures_by_segment, segments=None):
    for segment_key, segment_id in list(segment_map.items()):
        departures = departures_by_segment.get(segment_key)
        if not departures:
            continue

        company_id = None
        if segments and segment_key in segments:
            company_id = segments[segment_key].get("company_id")

        if company_id:
            segment_id_verified = client.ensure_route_segment_id(company_id, segment_key, known_segment_id=segment_id)
            if segment_id_verified is None:
                print(f"[ERR] Не удалось подтвердить сегмент {segment_key[:8]} для departure. Пропускаем")
                continue
            if segment_id_verified != segment_id:
                segment_id = segment_id_verified
                segment_map[segment_key] = segment_id_verified

        #print(f"upload_departures: segment_key={segment_key[:8]}..., segment_id={segment_id}, departures={len(departures)}")
        res = client.create_departures(segment_id, departures)
        if res is not None:
            continue

        time.sleep(SLEEP_AFTER_REPLACE_SEGMENTS)
        client.create_departures(segment_id, departures)

        time.sleep(SLEEP_BETWEEN_REQUESTS)


def upload_tariffs(client, segment_map, tariffs_by_segment, segments=None, dropoffs_by_tariff_key=None):
    if dropoffs_by_tariff_key is None:
        dropoffs_by_tariff_key = {}

    # Статистика по ТК: company_id -> {segments, tariffs, dropoffs, errors}
    company_stats: Dict[str, Dict[str, int]] = {}

    def _ensure_company_stat(cid):
        if cid not in company_stats:
            company_stats[cid] = {"segments": 0, "tariffs_createded": 0, "dropoffs_updated": 0, "errors": 0}

    for tariff_key, tariffs in tariffs_by_segment.items():
        segment_key, container_type, container_ownership, port_service_term = tariff_key
        segment_id = segment_map.get(segment_key)
        if not segment_id:
            continue

        company_id = None
        if segments and segment_key in segments:
            company_id = segments[segment_key].get("company_id")

        if company_id:
            segment_id_verified = client.ensure_route_segment_id(company_id, segment_key, known_segment_id=segment_id)
            if segment_id_verified is None:
                print(f"[ERR] Не удалось подтвердить сегмент {segment_key[:8]} для тарифов. Пропускаем")
                _ensure_company_stat(company_id)
                company_stats[company_id]["errors"] += 1
                continue
            if segment_id_verified != segment_id:
                segment_id = segment_id_verified
                segment_map[segment_key] = segment_id_verified

        _ensure_company_stat(company_id)

        #print(f"🔧 upload_tariffs: segment_key={segment_key[:8]}..., segment_id={segment_id}, company_id={company_id}, tariffs_weight_bands={len(tariffs.weight_bands) if hasattr(tariffs, 'weight_bands') else 'N/A'}")
        res = client.create_tariffs(segment_id, tariffs)
        if res is None:
            # Ретрай: иногда сегмент ещё не доступен сразу по ID, пробуем обновить из списка
            if company_id:
                segment_id_verified = client.ensure_route_segment_id(company_id, segment_key, known_segment_id=segment_id, retries=3, sleep_seconds=1.0)
                if segment_id_verified is None:
                    print(f"[ERR] Тарифы: сегмент {segment_key[:8]} всё еще не найден, пропускаем")
                    company_stats[company_id]["errors"] += 1
                    continue
                if segment_id_verified != segment_id:
                    segment_id = segment_id_verified
                    segment_map[segment_key] = segment_id_verified

            time.sleep(SLEEP_BETWEEN_REQUESTS)
            res = client.create_tariffs(segment_id, tariffs)
            if res is None:
                print(f"[ERR] Не удалось создать тарифы для сегмента {segment_id} ({segment_key[:8]}) после повторного запроса")
                company_stats[company_id]["errors"] += 1
                continue
        company_stats[company_id]["tariffs_createded"] += 1
        time.sleep(SLEEP_AFTER_TARIFF_CREATE)

        # Upload dropoff locations for each created tariff
        # Try to get tariffs from response, or fetch them from server
        created_tariffs = []
        if isinstance(res, list) and len(res) > 0:
            created_tariffs = res
        else:
            # Fetch tariffs from server for this segment
            try:
                url = f"{client.base_url}/admin/route-segments/{segment_id}/tariffs"
                resp = client.session.get(url, headers=client._headers())
                if resp.status_code == 200:
                    created_tariffs = resp.json()
            except Exception:
                pass

        for created_tariff in created_tariffs:
            t_id = created_tariff.get("id")
            if not t_id:
                continue
            # Match by container_type and container_ownership
            t_container = created_tariff.get("container_type")
            t_ownership = created_tariff.get("container_ownership")
            t_port_service = created_tariff.get("port_service_term")
            # Build matching key
            match_key = (segment_key, t_container, t_ownership, t_port_service)
            if match_key in dropoffs_by_tariff_key:
                # Конвертируем dict -> list (deduplication)
                dropoffs = list(dropoffs_by_tariff_key[match_key].values())
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                result = client.update_tariff_dropoff_locations(t_id, dropoffs)
                if result is not None:
                    #print(f"  [OK] Dropoff привязан к тарифу {t_id[:8]}... ({t_container}/{t_ownership})")
                    company_stats[company_id]["dropoffs_updated"] += 1
                else:
                    company_stats[company_id]["errors"] += 1

    # Печатаем сводку по ТК
    _print_company_summary(client, company_stats, segments)


def _print_company_summary(client, company_stats, segments):
    """Выводит сводную статистику по каждой ТК."""
    # Считаем уникальные сегменты по company_id
    seg_count_by_company: Dict[str, int] = {}
    if segments:
        for item in segments.values():
            cid = item.get("company_id")
            if cid:
                cid = str(cid)
                seg_count_by_company[cid] = seg_count_by_company.get(cid, 0) + 1

    print(f"\n{'='*60}")
    print(f"СВОДКА ПО ТРАНСПОРТНЫМ КОМПАНИЯМ")
    print(f"{'='*60}")
    for cid, stats in company_stats.items():
        # Попробуем найти имя ТК
        tk_name = cid
        try:
            info = client.get_companies(cid)
            if info and info.get("name"):
                tk_name = info["name"]
        except Exception:
            pass
        n_segments = seg_count_by_company.get(cid, 0)
        print(f"\n  ТК: {tk_name} (ID: {cid[:8]}...)")
        print(f"    Сегментов:       {n_segments}")
        print(f"    Тарифов создано: {stats['tariffs_createded']}")
        print(f"    Drop-off обновлений: {stats['dropoffs_updated']}")
        print(f"    Ошибок:          {stats['errors']}")
    print(f"{'='*60}")


def print_segment_details(client, segment_map, limit=5):
    """Выводит подробную информацию по первым N сегментам."""
    print(f"\n{'='*80}")
    print(f"ПОДРОБНАЯ ИНФОРМАЦИЯ ПО СЕГМЕНТАМ (первые {limit})")
    print(f"{'='*80}")

    shown = 0
    for segment_key, segment_id in segment_map.items():
        if shown >= limit:
            break

        # Получаем данные сегмента с сервера
        seg_data = None
        try:
            url = f"{client.base_url}/admin/route-segments/{segment_id}"
            resp = client.session.get(url, headers=client._headers())
            if resp.status_code == 200:
                seg_data = resp.json()
        except Exception:
            pass

        if not seg_data:
            continue
        if seg_data.get('transport_type') == "rail":
            shown += 1
        print(f"\n--- Сегмент #{shown} ---")
        print(f"  Segment ID:    {segment_id}")
        print(f"  Transport:     {seg_data.get('transport_type')}")
        print(f"  Conditions:    {seg_data.get('conditions')}")

        # Start location
        start_loc = seg_data.get('start_location', {})
        print(f"  Start:         {start_loc.get('name')} (type={start_loc.get('location_type')}, cc={start_loc.get('country_code')})")
        print(f"  Start ID:      {start_loc.get('id')}")
        if start_loc.get('parent_location_id'):
            print(f"  Start Parent:  {start_loc.get('parent_location_id')}")

        # End location
        end_loc = seg_data.get('end_location', {})
        print(f"  End:           {end_loc.get('name')} (type={end_loc.get('location_type')}, cc={end_loc.get('country_code')})")
        print(f"  End ID:        {end_loc.get('id')}")
        if end_loc.get('parent_location_id'):
            print(f"  End Parent:    {end_loc.get('parent_location_id')}")

        # Tariffs
        try:
            url = f"{client.base_url}/admin/route-segments/{segment_id}/tariffs"
            resp = client.session.get(url, headers=client._headers())
            if resp.status_code == 200:
                tariffs = resp.json()
                print(f"  Tariffs:       {len(tariffs)}")
                for t in tariffs[:3]:
                    wb = t.get('weight_bands', [])
                    costs = ', '.join([f"{w.get('base_amount')} {w.get('currency')}" for w in wb[:2]])
                    print(f"    - {t.get('container_type')} / {t.get('container_ownership')} / {t.get('port_service_term')} | cost: {costs} | tariff_id={t.get('id')}")
                    if t.get('valid_from'):
                        print(f"      valid: {t.get('valid_from')} — {t.get('valid_to')}")
        except Exception:
            pass

        # Dropoff locations
        try:
            url = f"{client.base_url}/admin/route-segments/{segment_id}/dropoff-locations"
            resp = client.session.get(url, headers=client._headers())
            if resp.status_code == 200:
                dropoffs = resp.json()
                if dropoffs:
                    for d in dropoffs:
                        print(f"  Dropoff:       {d.get('location', {}).get('name')} (type={d.get('location', {}).get('location_type')})")
        except Exception:
            pass

    print(f"\n{'='*80}")


def upload_stopovers(client, segment_map, stopovers_by_segment):
    """Создание stopover-локаций для сегментов."""
    if not stopovers_by_segment:
        return
    for segment_key, stopover_info in stopovers_by_segment.items():
        segment_id = segment_map.get(segment_key)
        if not segment_id:
            continue
        loc_id = stopover_info["location_id"]
        sequence = stopover_info["sequence"]
        print(f"upload_stopovers: segment_key={segment_key[:8]}..., loc_id={loc_id}, seq={sequence}")
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        client.create_stopovers(segment_id, loc_id, sequence)

def start_download_coordinates(client):
    result = fill_location_coordinates(client, yandex_api_key="94d3a1a8-fe5b-40ac-b063-62170967a277")

    #print(result)
    result = sync_child_locations_coordinates(client)

    print(f"Обновлено: {result['updated']}")
    print(f"Пропущено: {result['skipped']}")
    print(f"Ошибок: {result['errors']}")
    
# --- Пример использования для test.logiways.ru ---
if __name__ == "__main__":
    # Инициализация клиента для тестового стенда
    client = LogiwaysClient(base_url="https://logiways.ru")

    # --- Аутентификация (как в исходном коде, но с тестовым номером) ---
    print("\n=== Запрос SMS-кода ===")
    # Используйте тестовый номер, который есть в системе test.logiways.ru
    test_phone = "+79617811422"
    sms_response = client.request_sms(phone=test_phone)
    if not sms_response:
        print("Не удалось запросить SMS-код! Возможно, номер не зарегистрирован.")
        print("Попробуйте сначала выполнить signup с этим номером.")
        # exit(1) # Раскомментируйте для остановки, если нужно
    else:
        print(f"SMS запрошено. Статус: {sms_response.get('status')}, TTL: {sms_response.get('ttl')} сек")

    # На практике здесь нужно ввести код из SMS
    sms_code = "777777"

    print("\n=== Верификация SMS-кода ===")
    verified_tokens = client.verify_sms(
        phone_number=test_phone,
        code=sms_code
    )
    if not verified_tokens:
        exit(0)

    print(f"Верификация успешна. Access_token: {verified_tokens.access_token[:20]}...")

    #result = fill_location_coordinates(client, country_filter="RU", limit=1, yandex_api_key="94d3a1a8-fe5b-40ac-b063-62170967a277")
    
    #для координат
    #start_download_coordinates(client)
    #exit(0)
    
    try:
        companies = json.load(open('companies.json', encoding='utf-8'))
    except FileNotFoundError:
        print("Файл companies.json не найден. Создаем пустой список.")
        companies = []

    companiess_ids = {}
    for trans_company in companies:
        trans_company_id = client.get_transport_company_by_name(trans_company["name"])
        if trans_company_id is None:
            print("\n=== Создание новой организации ===")
            new_org = TransportCompaniesCreate(
                name=trans_company["name"],
                contact_first_name=trans_company["contact_first_name"],
                contact_last_name=trans_company["contact_last_name"],
                phone=trans_company["phone"],
                email=trans_company["email"],
                languages=trans_company["languages"],
                is_active=True
            )
            created_org = client.create_transport_companies(new_org)
            if created_org:
                trans_company_id = created_org.get('id')
                print(f"Организация создана. ID: {trans_company_id}")
            else:
                print("Не удалось создать организацию.", trans_company["name"])
        companiess_ids[trans_company["name"]] = trans_company_id

    
    df = pd.read_excel("tariff_analysis_TEST.xlsx")#tariff_analysis_ALL_NEW

    print("\n=== ЭТАП 1: Загрузка локаций ===")
    print(f"Всего строк в Excel: {len(df)}")

    # Убеждаемся, что у нас есть все необходимые компании
    unique_companies = df['company'].unique()
    print(f"Уникальных компаний в Excel: {len(unique_companies)}")
    for company_name in unique_companies:
        if company_name not in companiess_ids:
            print(f"⚠ Компания не инициализирована: {company_name}")
            companiess_ids[company_name] = client.get_transport_company_by_name(company_name)
            if companiess_ids[company_name]:
                print(f"  ✓ Найдена в системе: ID={companiess_ids[company_name][:8]}...")
            else:
                print(f"  ✗ НЕ НАЙДЕНА в системе. Пропускаем.")

    print("\n=== ЭТАП 2: Подготовка сегментов и тарифов ===")
    segments, tariffs_by_segment, departure_by_segment, dropoffs_by_tariff, stopovers_by_seg = build_segments_from_excel(
        df,
        client,
        company_id_dict=companiess_ids
    )
    print(f"✓ Подготовлено сегментов: {len(segments)}")
    print(f"✓ Подготовлено тарифов: {len(tariffs_by_segment)}")
    print(f"✓ Подготовлено отправлений: {len(departure_by_segment)}")

    print("\n=== ЭТАП 3: Загрузка сегментов ===")
    segment_map = upload_segments(
        client,
        segments
    )
    print(f"✓ Успешно загружено сегментов: {len(segment_map)}")

    print("\n=== ЭТАП 4: Загрузка отправлений ===")
    upload_departures(
        client,
        segment_map,
        departure_by_segment,
        segments=segments
    )

    print("\n=== ЭТАП 5: Загрузка тарифов и drop-off локаций ===")
    upload_tariffs(
        client,
        segment_map,
        tariffs_by_segment,
        segments=segments,
        dropoffs_by_tariff_key=dropoffs_by_tariff
    )
    # stopovers пока отключены — endpoint 422, нужно разобраться
    # print("Выполняется создание stopover-локаций")
    # upload_stopovers(client, segment_map, stopovers_by_seg)

    # Вывод подробной информации по первым 5 сегментам
    #print_segment_details(client, segment_map, limit=5)

    print("Все успешно выполнено")
