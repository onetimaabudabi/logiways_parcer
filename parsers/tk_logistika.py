from __future__ import annotations

from .models import TariffSegment
from .utils import to_segments as _to_segments


def parse() -> list[TariffSegment]:
    """
    Парсер ТК Логистика с захардкодированными маршрутами.
    """
    segments = [
        TariffSegment(
            transport_type="auto",
            start_point="Владивостокский морской рыбный порт, Россия",
            end_point="Артем, Россия",
            container_type="20DC",
            cost=36000,
            currency="RUB",
            weight_limit="20",
            max_weight_kg="20",
            company="ТК Логистика",
            duration_min_days=1,
            duration_max_days=1,
            end_location_type="rail_station",
            start_location_type="port",
            parent_start_location="Владивосток",
            parent_end_location="Артем",
            parent_start_location_type="city",
            parent_end_location_type="city"
        ),
        TariffSegment(
            transport_type="auto",
            start_point="Владивостокский морской рыбный порт, Россия",
            end_point="Уссурийск, Россия",
            container_type="20DC",
            cost=54000,
            currency="RUB",
            weight_limit="20",
            max_weight_kg="20",
            company="ТК Логистика",
            duration_min_days=1,
            duration_max_days=1,
            end_location_type="rail_station",
            start_location_type="port",
            parent_start_location="Владивосток",
            parent_end_location="Уссурийск",
            parent_start_location_type="city",
            parent_end_location_type="city"
        ),
        TariffSegment(
            transport_type="auto",
            start_point="Терминал Астафьева, Россия",
            end_point="Артем, Россия",
            container_type="20DC",
            cost=57000,
            currency="RUB",
            weight_limit="20",
            max_weight_kg="20",
            company="ТК Логистика",
            duration_min_days=1,
            duration_max_days=1,
            end_location_type="rail_station",
            start_location_type="port",
            parent_start_location="Находка",
            parent_end_location="Артем",
            parent_start_location_type="city",
            parent_end_location_type="city"

        ),
        TariffSegment(
            transport_type="auto",
            start_point="Терминал Астафьева, Россия",
            end_point="Уссурийск, Россия",
            container_type="20DC",
            cost=63000,
            currency="RUB",
            weight_limit="20",
            max_weight_kg="20",
            company="ТК Логистика",
            duration_min_days=1,
            duration_max_days=1,
            end_location_type="rail_station",
            start_location_type="port",
            parent_start_location="Находка",
            parent_end_location="Уссурийск",
            parent_start_location_type="city",
            parent_end_location_type="city"
        ),
    ]
    return segments
