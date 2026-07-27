from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import fields
from typing import Any, Mapping, Optional


@dataclass(frozen=True, slots=True)
class TariffSegment:
    """
    Canonical segment structure (based on `parse_EuroSib` output).
    Parsers should create this object and then convert to dict/DataFrame.
    """

    transport_type: str
    start_point: str
    end_point: str
    container_type: str
    weight_limit: Any = None
    min_weight_kg: Any = None
    max_weight_kg: Any = None
    cost: Any = None
    currency: str = ""
    departure_dates: Any = None
    company: str = ""
    customs: Any = None
    conditions: Any = ""
    duration_max_days: int = None
    duration_min_days: int = None
    departures: Any = None
    container_ownership: Optional[str] = None
    port_service_term: Optional[str] = None

    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

    end_location_type: Optional[str] = None
    start_location_type: Optional[str] = None

    parent_start_location: Optional[str] = None
    parent_start_location_type: Optional[str] = None
    parent_end_location: Optional[str] = None
    parent_end_location_type: Optional[str] = None

    stopovers_location: Optional[str] = None
    stopovers_location_type: Optional[str] = None
    stopovers_location_country: Optional[str] = None
    parent_stopovers_location: Optional[str] = None
    parent_stopovers_location_type: Optional[str] = None
    sequence: int = 0

    # Dropoff locations for tariffs (uploaded via PUT /admin/tariffs/{tariff_id}/dropoff-locations)
    dropoff_location: Optional[str] = None
    dropoff_location_type: Optional[str] = None
    dropoff_location_country: Optional[str] = None

    # Present in some parsers (kept optional for consistent schema).
    border_point: Optional[str] = None
    border_location: Optional[str] = None
    border_location_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TariffSegment":
        field_names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in dict(data).items() if k in field_names}

        missing: list[str] = []
        for required in (
            "transport_type",
            "start_point",
            "end_point",
            "container_type",
        ):
            if required not in kwargs or kwargs[required] in (None, ""):
                missing.append(required)
        if missing:
            raise ValueError(f"TariffSegment missing required fields: {', '.join(missing)}")

        return cls(**kwargs)  # type: ignore[arg-type]
