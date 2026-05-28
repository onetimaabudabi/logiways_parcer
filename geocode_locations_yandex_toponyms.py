#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Optional

import requests

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Install dependencies first: pip install psycopg2-binary requests", file=sys.stderr)
    raise

try:
    import pycountry
except ImportError:
    print("Install dependencies first: pip install pycountry", file=sys.stderr)
    raise

try:
    from babel import Locale
except ImportError:
    print("Install dependencies first: pip install Babel", file=sys.stderr)
    raise


TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

RU_LOCALE = Locale.parse("ru")
EN_LOCALE = Locale.parse("en")

# Небольшой слой полезных коротких/часто используемых названий поверх pycountry/Babel.
# Это не ручные алиасы для городов/портов, а только более удобные формы стран.
COUNTRY_ALIAS_OVERRIDES: dict[str, list[str]] = {
    "RU": ["Россия", "Russian Federation", "Russia"],
    "CN": ["Китай", "КНР", "China", "PRC"],
    "KP": ["КНДР", "Северная Корея", "North Korea"],
    "KR": ["Южная Корея", "South Korea", "Republic of Korea"],
    "TW": ["Тайвань", "Taiwan", "Chinese Taipei"],
    "HK": ["Гонконг", "Hong Kong"],
    "MO": ["Макао", "Macau"],
    "GB": ["Великобритания", "United Kingdom", "UK", "Great Britain"],
    "US": ["США", "Соединенные Штаты", "United States", "USA"],
    "AE": ["ОАЭ", "United Arab Emirates", "UAE"],
    "TR": ["Турция", "Türkiye", "Turkey"],
    "EG": ["Египет", "Egypt"],
    "IN": ["Индия", "India"],
    "MY": ["Малайзия", "Malaysia"],
    "MN": ["Монголия", "Mongolia"],
    "GE": ["Грузия", "Georgia"],
    "KZ": ["Казахстан", "Kazakhstan"],
    "UZ": ["Узбекистан", "Uzbekistan"],
    "BY": ["Беларусь", "Belarus"],
    "UA": ["Украина", "Ukraine"],
}


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    query: str
    display_name: Optional[str] = None
    precision: Optional[str] = None
    raw_country_code: Optional[str] = None
    raw: Optional[dict] = None


class GeocoderError(Exception):
    pass


class YandexGeocoder:
    base_url = "https://geocode-maps.yandex.ru/v1"

    def __init__(
        self,
        api_key: str,
        lang: str = "ru_RU",
        results: int = 1,
        timeout: int = 30,
        retries: int = 3,
        user_agent: str = "logiways-location-geocoder/1.0",
    ):
        if not api_key:
            raise GeocoderError("Yandex API key is required. Pass --api-key or set YANDEX_API_KEY.")
        self.api_key = api_key
        self.lang = lang
        self.results = results
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def geocode(
        self,
        query: str,
        *,
        bbox: Optional[str] = None,
        rspn: Optional[int] = None,
    ) -> Optional[GeocodeResult]:
        params: Dict[str, Any] = {
            "apikey": self.api_key,
            "geocode": query,
            "lang": self.lang,
            "format": "json",
            "results": self.results,
        }
        if bbox:
            params["bbox"] = bbox
        if rspn is not None:
            params["rspn"] = int(rspn)

        last_error = None
        for attempt in range(1, self.retries + 1):
            # Подготовка PreparedRequest для получения итогового URL с параметрами
            req = requests.Request('GET', self.base_url, params=params)
            prepared = self.session.prepare_request(req)
            print(f"  Yandex URL: {prepared.url}")

            response = self.session.get(self.base_url, params=params, timeout=self.timeout)
            if response.status_code == 429:
                last_error = GeocoderError("HTTP 429: rate limit exceeded")
                time.sleep(min(2 ** attempt, 10))
                continue
            if response.status_code >= 400:
                raise GeocoderError(f"HTTP {response.status_code}: {response.text[:500]}")

            data = response.json()
            members = (
                data.get("response", {})
                .get("GeoObjectCollection", {})
                .get("featureMember", [])
            )
            if not members:
                return None

            item = members[0].get("GeoObject") or {}
            pos = ((item.get("Point") or {}).get("pos") or "").split()
            if len(pos) != 2:
                return None

            meta = ((item.get("metaDataProperty") or {}).get("GeocoderMetaData") or {})
            address = meta.get("Address") or {}
            return GeocodeResult(
                latitude=float(pos[1]),
                longitude=float(pos[0]),
                query=query,
                display_name=meta.get("text") or address.get("formatted"),
                precision=meta.get("precision"),
                raw_country_code=(address.get("country_code") or "").upper() or None,
                raw=item,
            )

        if last_error:
            raise last_error
        return None



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill latitude/longitude in PostgreSQL using Yandex Geocoder API and ISO-country toponym variants")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL DSN or URL. Can also come from DATABASE_URL")
    parser.add_argument("--table", default="public.locations", help="Target table, e.g. public.locations")
    parser.add_argument("--api-key", default=os.getenv("YANDEX_API_KEY") or os.getenv("GEOCODER_API_KEY"), help="Yandex API key")
    parser.add_argument("--lang", default=os.getenv("YANDEX_LANG", "ru_RU"), help="Yandex response locale, e.g. ru_RU or en_US")
    parser.add_argument("--results", type=int, default=int(os.getenv("YANDEX_RESULTS", "1")), help="How many Yandex results to request; script uses the first one")
    parser.add_argument("--bbox", default=os.getenv("YANDEX_BBOX"), help="Optional Yandex bbox: lon1,lat1~lon2,lat2")
    parser.add_argument("--rspn", type=int, choices=[0, 1], default=(int(os.getenv("YANDEX_RSPN")) if os.getenv("YANDEX_RSPN") is not None else None), help="Use with --bbox: 1 to restrict search to the bbox")
    parser.add_argument("--user-agent", default=os.getenv("GEOCODER_USER_AGENT", "logiways-location-geocoder/1.0"))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("GEOCODER_TIMEOUT", "30")))
    parser.add_argument("--retries", type=int, default=int(os.getenv("GEOCODER_RETRIES", "3")))
    parser.add_argument("--sleep", type=float, default=float(os.getenv("GEOCODER_SLEEP", "0.20")), help="Pause between requests, seconds")
    parser.add_argument("--country-alias-limit", type=int, default=int(os.getenv("COUNTRY_ALIAS_LIMIT", "6")), help="Max number of country-name variants to add to each query")
    parser.add_argument("--limit", type=int, default=0, help="Max number of rows to process in this run")
    parser.add_argument("--dry-run", action="store_true", help="Do not update DB")
    parser.add_argument("--allow-overwrite", action="store_true", help="Also update rows that already have coordinates")
    parser.add_argument("--only-country", help="Process only one ISO2 country code, e.g. RU")
    parser.add_argument("--commit-every", type=int, default=20)
    parser.add_argument("--cache-file", default="yandex_geocode_cache.json")
    parser.add_argument("--unresolved-csv", default="unresolved_locations_yandex.csv")
    return parser.parse_args()



def validate_table_name(table: str) -> str:
    if not TABLE_RE.match(table):
        raise ValueError("Unsafe table name. Use schema.table or table with letters/numbers/_ only.")
    return table



def load_cache(cache_file: str) -> Dict[str, dict]:
    if not cache_file or not os.path.exists(cache_file):
        return {}
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)



def save_cache(cache_file: str, cache: Dict[str, dict]) -> None:
    if not cache_file:
        return
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)



def normalize_space(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())



def normalize_name(name: str) -> str:
    name = normalize_space(name)
    return name.replace("«", '"').replace("»", '"')



def safe_country_name_from_babel(code: str, locale_obj: Locale) -> Optional[str]:
    try:
        return locale_obj.territories.get(code.upper())
    except Exception:
        return None



def country_aliases(country_code: Optional[str], limit: int = 6) -> list[str]:
    code = normalize_space(country_code).upper()
    if not code:
        return []

    candidates: list[str] = []
    candidates.extend(COUNTRY_ALIAS_OVERRIDES.get(code, []))

    ru_name = safe_country_name_from_babel(code, RU_LOCALE)
    en_name = safe_country_name_from_babel(code, EN_LOCALE)
    if ru_name:
        candidates.append(ru_name)
    if en_name:
        candidates.append(en_name)

    record = pycountry.countries.get(alpha_2=code)
    if record:
        for attr in ("name", "official_name", "common_name"):
            value = getattr(record, attr, None)
            if value:
                candidates.append(value)

    # Дополнительно оставляем сам код в конце как последний, наименее полезный вариант.
    candidates.append(code)

    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        value = normalize_space(str(item))
        if not value:
            continue
        value = value.replace("(", "").replace(")", "")
        if value not in seen:
            seen.add(value)
            result.append(value)
        if len(result) >= limit:
            break
    return result



def with_country_variants(base_query: str, country_code: Optional[str], limit: int) -> Iterable[str]:
    base_query = normalize_space(base_query.strip(" ,"))
    if not base_query:
        return

    yield base_query

    for alias in country_aliases(country_code, limit=limit):
        yield f"{base_query}, {alias}"
        yield f"{base_query} {alias}"



def build_queries(row: Dict[str, Any], country_alias_limit: int) -> Iterable[str]:
    name = normalize_name(row["name"])
    parent_name = normalize_space(row.get("parent_name"))
    region = normalize_space(row.get("region"))
    location_type = row.get("location_type")
    country_code = normalize_space(row.get("country_code"))

    labels_ru = {
        "city": "город",
        "port": "порт",
        "rail_station": "станция",
        "terminal": "терминал",
        "sea_terminal": "морской терминал",
        "dry_port": "сухой порт",
    }

    base_queries = [
        ", ".join(filter(None, [name, parent_name, region])),
        ", ".join(filter(None, [name, parent_name])),
        ", ".join(filter(None, [name, region])),
        name,
    ]

    type_label = labels_ru.get(location_type)
    if type_label:
        base_queries.insert(0, ", ".join(filter(None, [f"{type_label} {name}", parent_name, region])))
        base_queries.insert(1, ", ".join(filter(None, [f"{type_label} {name}", parent_name])))
        base_queries.insert(2, ", ".join(filter(None, [f"{type_label} {name}", region])))
        base_queries.insert(3, f"{type_label} {name}")

    seen = set()
    for base_query in base_queries:
        for query in with_country_variants(base_query, country_code, limit=country_alias_limit):
            query = normalize_space(query)
            if query and query not in seen:
                seen.add(query)
                yield query



def country_matches(expected: Optional[str], actual: Optional[str]) -> bool:
    if not expected or not actual:
        return True
    return expected.upper() == actual.upper()



def fetch_rows(conn, table: str, allow_overwrite: bool, only_country: Optional[str], limit: int):
    where_parts = ["COALESCE(l.deleted, false) = false"]
    if not allow_overwrite:
        where_parts.append("(l.latitude IS NULL OR l.longitude IS NULL)")
    if only_country:
        where_parts.append("l.country_code = %s")
    where_sql = " AND ".join(where_parts)
    limit_sql = f"LIMIT {int(limit)}" if limit and limit > 0 else ""

    sql = f"""
        SELECT
            l.location_id,
            l.location_type,
            l.name,
            l.country_code,
            l.region,
            l.parent_location_id,
            l.latitude,
            l.longitude,
            p.name AS parent_name,
            p.country_code AS parent_country_code,
            p.location_type AS parent_type
        FROM {table} l
        LEFT JOIN {table} p ON p.location_id = l.parent_location_id
        WHERE {where_sql}
        ORDER BY l.location_type, l.country_code, l.name
        {limit_sql}
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if only_country:
            cur.execute(sql, (only_country.upper(),))
        else:
            cur.execute(sql)
        return cur.fetchall()



def update_row(conn, table: str, location_id: str, latitude: float, longitude: float) -> None:
    sql = f"""
        UPDATE {table}
        SET latitude = %s,
            longitude = %s
        WHERE location_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (latitude, longitude, location_id))



def geocode_row(
    geocoder: YandexGeocoder,
    row: Dict[str, Any],
    cache: Dict[str, dict],
    *,
    bbox: Optional[str],
    rspn: Optional[int],
    country_alias_limit: int,
) -> Optional[GeocodeResult]:
    expected_country = (row.get("country_code") or row.get("parent_country_code") or "").upper() or None

    for query in build_queries(row, country_alias_limit=country_alias_limit):
        cache_key = f"yandex|{expected_country or ''}|{bbox or ''}|{rspn if rspn is not None else ''}|{query}"
        cached = cache.get(cache_key)
        if cached:
            result = GeocodeResult(**cached)
            if country_matches(expected_country, result.raw_country_code):
                return result
            continue

        result = geocoder.geocode(query=query, bbox=bbox, rspn=rspn)
        if result and country_matches(expected_country, result.raw_country_code):
            cache[cache_key] = asdict(result)
            return result
    return None



def write_unresolved_csv(path: str, unresolved_rows: list[Dict[str, Any]]) -> None:
    if not unresolved_rows:
        return
    fields = [
        "location_id",
        "location_type",
        "name",
        "country_code",
        "region",
        "parent_location_id",
        "parent_name",
        "parent_country_code",
        "latitude",
        "longitude",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in unresolved_rows:
            writer.writerow({field: row.get(field) for field in fields})



def main() -> int:
    args = parse_args()
    if not args.db_url:
        print("Pass --db-url or set DATABASE_URL", file=sys.stderr)
        return 2

    table = validate_table_name(args.table)
    geocoder = YandexGeocoder(
        api_key=args.api_key,
        lang=args.lang,
        results=args.results,
        timeout=args.timeout,
        retries=args.retries,
        user_agent=args.user_agent,
    )

    cache = load_cache(args.cache_file)
    conn = psycopg2.connect(args.db_url)
    conn.autocommit = False

    try:
        rows = fetch_rows(conn, table, args.allow_overwrite, args.only_country, args.limit)
        if not rows:
            print("No rows to process.")
            return 0

        print(f"Rows to process: {len(rows)}")
        processed = 0
        resolved = 0
        unresolved = []
        errors = 0

        for row in rows:
            processed += 1
            try:
                result = geocode_row(
                    geocoder,
                    row,
                    cache,
                    bbox=args.bbox,
                    rspn=args.rspn,
                    country_alias_limit=args.country_alias_limit,
                )
                if result:
                    print(
                        f"[{processed}/{len(rows)}] OK {row['location_type']} | {row['name']} | "
                        f"{result.latitude}, {result.longitude} | {result.display_name} | query={result.query}"
                    )
                    resolved += 1
                    if not args.dry_run:
                        update_row(conn, table, row["location_id"], result.latitude, result.longitude)
                        if resolved % args.commit_every == 0:
                            conn.commit()
                            save_cache(args.cache_file, cache)
                else:
                    print(f"[{processed}/{len(rows)}] MISS {row['location_type']} | {row['name']}")
                    unresolved.append(row)
            except Exception as exc:
                errors += 1
                unresolved.append(row)
                print(f"[{processed}/{len(rows)}] ERROR {row['location_type']} | {row['name']} | {exc}", file=sys.stderr)

            time.sleep(args.sleep)

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
        save_cache(args.cache_file, cache)
        write_unresolved_csv(args.unresolved_csv, unresolved)

        print("\nDone")
        print(f"Processed:  {processed}")
        print(f"Resolved:   {resolved}")
        print(f"Unresolved: {len(unresolved)}")
        print(f"Errors:     {errors}")
        if unresolved:
            print(f"Check unresolved rows in: {args.unresolved_csv}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
