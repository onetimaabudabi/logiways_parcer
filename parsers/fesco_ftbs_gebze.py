"""FESCO — FTBS: Турция ↔ Новороссийск.

Файл: data/ftbs-gebze.xlsx, лист «FTBS Tariff».

    EB (ex Turkey to Novorossiysk)   — Ambarli / Gebze → Новороссийск, FIOS
    WB (ex Novorossiysk to Turkey)   — Новороссийск → Ambarli / Gebze, LIFO

В каждом блоке по шесть колонок ставок: COC и SOC × 20' / 40'HC / 45'HCPW.
Срок действия берётся из колонки Validity («1/8 - 31/8/2026»).

ВНИМАНИЕ: 45'HCPW пропускается — такого типа нет в ContainerType проекта
(допустимы 20DC, 20GP, 20RF, 20TK, 20TC, 20FR, 40HC, 40HQ, 40RF, 40OT).
Если тип понадобится, добавьте его в справочник и в CONTAINER_MAP
модуля fesco_common.

Листы IMO, DEMDET и Contact List не разбираются: это надбавки за опасный
груз, сверхнормативное хранение и контакты, а не тарифы перевозки.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

from .models import TariffSegment
from .utils import to_segments as _to_segments
from . import fesco_common as _c

_FILE = "ftbs-gebze.xlsx"
_SHEET = "FTBS Tariff"

_EB_CONDITIONS = (
    "FTBS, импорт FIOS Турция – Новороссийск; OTHC 336 USD за единицу "
    "оплачивается в порту погрузки, DTHC — в рублях местному агенту; "
    "GRI 150 USD за единицу на маршруте EB; надбавка за флекси-танки "
    "125 USD; 40'DC COC в Новороссийске не принимается"
)
_WB_CONDITIONS = (
    "FTBS, экспорт LIFO Новороссийск – Турция; OTHC включён в ставку, "
    "DTHC 336 USD за единицу оплачивается в порту назначения; "
    "надбавка за флекси-танки 125 USD"
)


def _is_blank(val) -> bool:
    return val is None or (isinstance(val, float) and math.isnan(val)) or str(val).strip() == ""


def _find_blocks(df: pd.DataFrame) -> list[dict]:
    """Находит блоки EB и WB по заголовкам в первой колонке."""
    blocks = []
    for idx in range(len(df)):
        cell = _c.text(df.iat[idx, 0])
        m = re.match(r"^(EB|WB)\s+FTBS", cell, re.IGNORECASE)
        if m:
            blocks.append({"direction": m.group(1).upper(), "row": idx})
    for i, block in enumerate(blocks):
        block["end"] = blocks[i + 1]["row"] if i + 1 < len(blocks) else len(df)
    return blocks


def _parse_block(df: pd.DataFrame, block: dict) -> list[dict]:
    """Разбирает один блок: шапка с типами контейнеров + строки портов."""
    start, end = block["row"], block["end"]

    # Строка с типами контейнеров («20'», «40'HC», «45'HCPW» дважды:
    # сначала COC, затем SOC).
    size_row = None
    for idx in range(start, end):
        row = [_c.text(v) for v in df.iloc[idx]]
        if sum(1 for v in row if re.match(r"^\d{2}['’]", v)) >= 4:
            size_row = idx
            break
    if size_row is None:
        return []

    # Колонки COC и SOC различаем по заголовку блока (строка start + 1).
    owner_row = [_c.text(v) for v in df.iloc[start + 1]]
    owner_by_col: dict[int, str] = {}
    current = None
    for col, value in enumerate(owner_row):
        found = _c.normalize_ownership(value)
        if found:
            current = found
        if current:
            owner_by_col[col] = current

    columns = []
    for col, value in enumerate(_c.text(v) for v in df.iloc[size_row]):
        container_type = _c.normalize_container(value)
        if container_type and col in owner_by_col:
            columns.append((col, container_type, owner_by_col[col]))
    if not columns:
        return []

    # Срок действия — в колонке Validity той же строки, что и первый порт.
    valid_from = valid_to = None
    for idx in range(start, end):
        joined = " ".join(_c.text(v) for v in df.iloc[idx])
        found_from, found_to = _c.parse_validity(joined)
        if found_from:
            valid_from, valid_to = found_from, found_to
            break

    results: list[dict] = []
    novo = _c.translate_port("Novorossiysk")
    for idx in range(size_row + 1, end):
        port_cell = _c.text(df.iat[idx, 0])
        if not port_cell or port_cell.lower().startswith(("port of", "subject")):
            continue
        port = _c.translate_port(port_cell)
        if not port:
            continue

        for col, container_type, ownership in columns:
            cost = _c.parse_price(df.iat[idx, col]) if col < df.shape[1] else None
            if cost is None:
                continue
            if block["direction"] == "EB":
                kw = dict(start_point=port[0], start_country=port[1],
                          end_point=novo[0], end_country=novo[1])
                term, conditions = "FIOS", _EB_CONDITIONS
            else:
                kw = dict(start_point=novo[0], start_country=novo[1],
                          end_point=port[0], end_country=port[1])
                term, conditions = "LIFO", _WB_CONDITIONS
            results.append(_c.make_sea(
                container_type=container_type, ownership=ownership, cost=cost,
                term=term, conditions=conditions,
                valid_from=valid_from, valid_to=valid_to, **kw,
            ))
    return results


def parse(file_path: str | Path | None = None) -> list[TariffSegment]:
    """Парсит прайс FTBS и возвращает список сегментов."""
    path = _c.resolve_path(file_path) if file_path else _c.find_file(_FILE)
    if path is None or not Path(path).exists():
        print(f"  [FESCO FTBS] файл не найден: {file_path or _FILE}")
        return []

    sheets = pd.read_excel(path, header=None, sheet_name=None)
    df = next((d for name, d in sheets.items() if name.strip().lower() == _SHEET.lower()),
              next(iter(sheets.values())))

    results: list[dict] = []
    for block in _find_blocks(df):
        results += _parse_block(df, block)

    eb = sum(1 for r in results if r["end_point"].startswith("Новороссийск"))
    print(f"  [FESCO FTBS] сегментов: {len(results)} (EB {eb}, WB {len(results)-eb})")
    return _to_segments(results)
