from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .models import TariffSegment


def to_segments(data: Any) -> list[TariffSegment]:
    if data is None:
        return []
    if isinstance(data, list) and (not data or isinstance(data[0], TariffSegment)):
        return data
    if isinstance(data, pd.DataFrame):
        records = data.to_dict(orient="records")
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        records = list(data)
    else:
        records = list(data)
    return [TariffSegment.from_dict(_clean_record(r)) for r in records]


def segments_to_df(segments: Iterable[TariffSegment]) -> pd.DataFrame:
    return pd.DataFrame([s.to_dict() for s in segments])


def coerce_tariff_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return segments_to_df(to_segments(df))


def _clean_record(record: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in dict(record).items():
        try:
            cleaned[k] = None if pd.isna(v) else v
        except Exception:
            cleaned[k] = v
    return cleaned
