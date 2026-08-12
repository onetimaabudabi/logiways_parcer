"""Парсер ОАО «Владморрыбпорт» — ускоренный контейнерный поезд (УКП).

Файл: data/ТЭУ УКП С <дата>.pdf (скан без текстового слоя, разбирается через OCR).

СТРУКТУРА ТАБЛИЦЫ
-----------------
Одна таблица на стр. 2. Колонки:
    Станция назначения | 20 фут. до 24т | 20 фут. 24–28т | 40 фут. до 28т
                       | Охрана 20 фут. | Охрана 40 фут.

Таблица сгруппирована по узлам: строка с городом (со сноской), под ней —
станции этого узла, а ставка задана на группу целиком объединённой ячейкой:

    Москва¹
      ст. Белый Раст
      ст. Электроугли
      ст. Селятино      200 000,00 | 235 000,00 | 335 000,00 | 6 400,00 | 12 700,00
      ст. Ворсино
      ст. Люберцы 2
      ст. Раменское

Цена печатается в строке той станции, на которую пришлась середина
объединённой ячейки (или отдельной строкой), но относится ко ВСЕМ станциям
узла. Поэтому станции набираются в буфер, а при закрытии группы каждой
выдаётся ставка группы; город становится parent_end_location.

КАК ОТЛИЧАЮТСЯ ГОРОД И СТАНЦИЯ
------------------------------
По отступу в исходном скане: города печатаются с x≈179, названия станций —
с x≈249. Плюс у станций есть префикс «ст.». Классификация опирается на оба
признака, а не на список городов: список пришлось бы править под каждый
новый файл.

ПОРОГ УВЕРЕННОСТИ OCR
---------------------
Здесь он понижен (_MIN_CONF = 0). При стандартном пороге 30 tesseract
отбрасывал «Санкт-Петербург» (conf=14) и «Тольятти» (conf=15) — из-за
надстрочных сносок, — и станции этих узлов слипались с предыдущей группой,
получая чужую ставку. По той же причине терялось значение «210 000,00»
(conf=0) у Екатеринбурга. Понижение порога компенсируется проверкой
структуры группы перед выдачей (_validate_group).

ЧТО ВЫГРУЖАЕТСЯ
---------------
Только перевозка, transport_type="rail": три записи на станцию
(20' до 24т, 20' 24–28т, 40' до 28т). Ставки охраны из колонок 4-5
намеренно НЕ выгружаются.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Optional

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import vmrp_ocr as _ocr

# ── Хелперы OCR ───────────────────────────────────────────────────────────────
#
# Модуль СОЗНАТЕЛЬНО не импортирует ничего из parsers/vladmorrybport.py.
#
# Причина: разбор этой таблицы держится на КООРДИНАТАХ слов, а не на плоском
# тексте. Ставка задана объединённой ячейкой на весь узел, а город от станции
# отличается только отступом (x≈179 против x≈249) — из строки текста такую
# структуру не восстановить. Сигнатуры и типы возврата хелперов в разных
# копиях проекта расходятся (_ocr_pages где-то отдаёт пути к изображениям,
# где-то готовый текст; набор аргументов _make_segment меняется), и слепой
# импорт даёт либо TypeError, либо — что хуже — молчаливые ноль записей.
#
# TariffSegment собирается напрямую, со всеми полями (company, currency,
# start_point и прочими). _make_segment не используется: тогда изменение
# его сигнатуры не может сломать этот парсер.
#
# Имена функций ниже совпадают с принятыми в проекте, поэтому код читается
# так же, как повагонка.


def _ocr_pages(path: Path, workdir: Path) -> list[Path]:
    """PDF → постраничные PNG (нужны координаты слов, не текст)."""
    return _ocr.render(path, workdir)


def _extract_valid_from(text: str) -> Optional[str]:
    """«действующие с 15 августа 2026 г.» → '2026-08-15'."""
    return _ocr.extract_valid_from(text)


def _clean_station(raw: str) -> str:
    """'ст. Белый Раст¹' → 'Белый Раст'."""
    return _ocr.clean_station(raw)


def _parse_rate_line(line) -> tuple[str, list[float]]:
    """Строка (слова с координатами) → (подпись, список ставок)."""
    label, cells = _ocr.split_row(line)
    prices = [_ocr.parse_price(c["text"]) for c in cells]
    return label, [p for p in prices if p is not None]


_COMPANY = "ОАО «Владморрыбпорт»"
_ORIGIN = "Владивостокский морской рыбный порт, Россия"
_CURRENCY = "RUB"
_SERVICE = "Ускоренный контейнерный поезд"

_MIN_CONF = 0          # см. пояснение в докстринге
_CITY_INDENT = 215     # x0 < порога → город; станции печатаются правее

# Колонки ставок перевозки: (индекс, тип контейнера, предел массы, уточнение).
# Колонки 3 и 4 (охрана) не выгружаются по постановке задачи.
_RATE_COLUMNS = [
    (0, "20DC", 24, "вес груза до 24 т"),
    (1, "20DC", 28, "вес груза от 24 до 28 т"),
    (2, "40HC", 28, "вес груза до 28 т"),
]
_EXPECTED_VALUES = 5   # в строке 5 чисел: 3 ставки + 2 охраны

_STATION_PREFIX = re.compile(r"^\s*ст\.?\s+", re.IGNORECASE)

# Текст, которым таблица заканчивается — ниже идут примечания
_TABLE_END = re.compile(r"тарифы\s+включают\s+в\s+себя", re.IGNORECASE)

# Служебные строки внутри таблицы (шапка, подписи колонок, шапка бланка)
_NOISE = re.compile(
    r"\b(станци\w*|тариф\w*|включа\w*|фут\w*|охран\w*|вес\s+груза|НДС|"
    r"прибывш\w*|терминал\w*|владивостокск\w*|морско\w*|рыбны\w*|порт|"
    r"поезд\w*|груз\w*|услуг\w*|контейнер\w*|назначени\w*)\b",
    re.IGNORECASE,
)

# Заголовок узла: одно-два слова с заглавной, возможно через дефис
_CITY_RE = re.compile(r"^[А-ЯЁ][А-Яа-яЁё]+(?:[-\s][А-ЯЁ][А-Яа-яЁё]+)*$")

_FILE_PATTERNS = [r"ТЭУ\s*УКП", r"УКП.*15[.\-_]?08", r"УКП"]


def _looks_like_city(label: str, x0: float) -> bool:
    """Заголовок узла: без префикса «ст.», на левом отступе, похож на топоним."""
    if _STATION_PREFIX.match(label or ""):
        return False
    if x0 >= _CITY_INDENT:
        return False
    text = _clean_station(label)
    if not text or len(text) < 4 or _NOISE.search(text):
        return False
    return bool(_CITY_RE.match(text))


def _validate_group(city: str, stations: list[str], prices: list[float]) -> Optional[str]:
    """Проверка группы перед выдачей. Возвращает текст ошибки или None.

    Нужна из-за пониженного порога OCR: если заголовок узла всё же потерян,
    станции соседних узлов склеятся и получат чужую ставку. Лучше не выдать
    группу вовсе, чем выдать неверные цены.
    """
    if not stations:
        return "не найдено ни одной станции"
    if len(prices) < _EXPECTED_VALUES:
        return f"распознано {len(prices)} значений из {_EXPECTED_VALUES}"
    if len(stations) > 8:
        return (f"станций {len(stations)} — подозрительно много, "
                f"вероятно потерян заголовок соседнего узла")
    return None


def parse_VladmorrybportUkp(file_path: str | Path | None = None) -> list[dict]:
    """Разбирает скан тарифов на ускоренные контейнерные поезда."""
    if file_path is not None:
        path = Path(file_path)
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        found: list[Path] = []
        for pattern in _FILE_PATTERNS:
            found = [p for p in sorted(data_dir.glob("*.pdf"))
                     if re.search(pattern, p.name, re.IGNORECASE)]
            if found:
                break
        if not found:
            raise FileNotFoundError(
                "В data/ не найден PDF с тарифами УКП. "
                "Ожидался файл вида «ТЭУ УКП С 15.08.2026.pdf»."
            )
        path = max(found, key=lambda p: p.stat().st_mtime)

    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    groups: list[tuple[str, list[str], list[float]]] = []
    valid_from: Optional[str] = None
    skipped: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        pages = _ocr_pages(path, Path(tmp))

        for png in pages:
            valid_from = _extract_valid_from(_ocr.page_text(png))
            if valid_from:
                break

        city: Optional[str] = None
        stations: list[str] = []
        prices: list[float] = []

        def close_group() -> None:
            nonlocal city, stations, prices
            if city is None:
                return
            problem = _validate_group(city, stations, prices)
            if problem:
                skipped.append(f"{city} ({problem})")
            else:
                groups.append((city, list(stations), list(prices)))
            city, stations, prices = None, [], []

        stop = False
        for png in pages:
            if stop:
                break
            for line in _ocr.lines(png, min_conf=_MIN_CONF):
                label, values = _parse_rate_line(line)

                if _TABLE_END.search(label or ""):
                    stop = True
                    break

                if len(values) >= _EXPECTED_VALUES:
                    prices = values[:_EXPECTED_VALUES]

                if _STATION_PREFIX.match(label or ""):
                    station = _clean_station(label)
                    if station and station not in stations:
                        stations.append(station)
                    continue

                if _looks_like_city(label, line[0]["x0"]):
                    close_group()
                    city = _clean_station(label)

        close_group()

    results: list[dict] = []
    for city, stations, prices in groups:
        for station in stations:
            for idx, container_type, weight_limit, note in _RATE_COLUMNS:
                results.append(
                    TariffSegment(
                        transport_type="rail",
                        start_point=_ORIGIN,
                        end_point=f"{station}, Россия",
                        container_type=container_type,
                        cost=prices[idx],
                        currency=_CURRENCY,
                        company=_COMPANY,
                        conditions=(f"{_SERVICE}; {city} (ст. {station}); "
                                    f"{note}; без НДС"),
                        valid_from=valid_from,
                        start_location_type="port",
                        end_location_type="rail_station",
                        parent_start_location="Владивосток",
                        parent_start_location_type="city",
                        parent_end_location=city,
                        parent_end_location_type="city",
                        weight_limit=weight_limit,
                    ).to_dict()
                )

    stations_total = sum(len(s) for _, s, _ in groups)
    print(
        f"[vladmorrybport_ukp] записей: {len(results)}; "
        f"узлов: {len(groups)}, станций: {stations_total}; "
        f"valid_from: {valid_from or '—'}; источник: {path.name}"
    )
    for city, stations, prices in groups:
        print(f"    {city}: {', '.join(stations)} → "
              f"{prices[0]:.0f} / {prices[1]:.0f} / {prices[2]:.0f} ₽")
    for problem in skipped:
        print(f"[vladmorrybport_ukp] ВНИМАНИЕ: узел пропущен — {problem}")
    if not results:
        print("[vladmorrybport_ukp] ВНИМАНИЕ: ничего не распознано — "
              "проверьте скан и наличие tesseract-ocr-rus")
    return results


def parse(*args, **kwargs) -> list[TariffSegment]:
    """Точка входа парсера."""
    return _to_segments(parse_VladmorrybportUkp(*args, **kwargs))
