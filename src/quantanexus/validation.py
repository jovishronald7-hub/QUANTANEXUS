"""Shared validation primitives for scenario inputs."""

from __future__ import annotations

import math
from numbers import Real
from typing import TypeVar


class ScenarioValidationError(ValueError):
    """Raised when scenario input is invalid or internally inconsistent."""


T = TypeVar("T")


def finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ScenarioValidationError(f"{field_name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ScenarioValidationError(f"{field_name} must be finite")
    return result


def nonnegative_number(value: object, field_name: str) -> float:
    result = finite_number(value, field_name)
    if result < 0:
        raise ScenarioValidationError(f"{field_name} must be non-negative")
    return result


def nonempty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def fixed_length_values(values: object, expected_length: int, field_name: str) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise ScenarioValidationError(f"{field_name} must be a sequence of numbers")
    try:
        items = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ScenarioValidationError(f"{field_name} must be a sequence of numbers") from error

    if len(items) != expected_length:
        raise ScenarioValidationError(
            f"{field_name} must contain exactly {expected_length} hourly values; got {len(items)}"
        )
    return tuple(finite_number(item, f"{field_name}[{index}]") for index, item in enumerate(items))


def validate_scenario_components(
    *,
    sector_demands: tuple[object, ...],
    solar: object,
    grid_import_limit: object,
    ev_cohorts: tuple[object, ...],
    operating_costs: object,
) -> None:
    expected_sectors = {"hospitals", "water", "public_lighting"}
    sector_names = [getattr(getattr(item, "sector", None), "value", None) for item in sector_demands]
    if len(sector_names) != len(expected_sectors) or set(sector_names) != expected_sectors:
        raise ScenarioValidationError(
            "sector_demands must contain exactly one profile for hospitals, water, and public_lighting"
        )

    for profile_name, series in (("solar", solar), ("grid_import_limit", grid_import_limit)):
        if getattr(series, "unit", None) is None or getattr(series, "values", None) is None:
            raise ScenarioValidationError(f"{profile_name} must be an hourly energy series")
        if getattr(series.unit, "value", None) != "MWh":
            raise ScenarioValidationError(f"{profile_name} must use MWh units")

    cohort_ids = [getattr(cohort, "cohort_id", None) for cohort in ev_cohorts]
    if len(cohort_ids) != len(set(cohort_ids)):
        raise ScenarioValidationError("EV cohort identifiers must be unique within a scenario")

    prices = getattr(operating_costs, "grid_price_per_mwh", None)
    if getattr(getattr(prices, "unit", None), "value", None) != "currency/MWh":
        raise ScenarioValidationError("grid prices must use currency/MWh units")