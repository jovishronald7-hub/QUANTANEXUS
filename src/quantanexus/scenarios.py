"""Deterministic, explicitly synthetic 24-hour scenario definitions."""

from __future__ import annotations

import math
from types import MappingProxyType

from .models import (
    HORIZON_HOURS,
    BatteryParameters,
    DataOrigin,
    DataProvenance,
    EVChargingCohort,
    HourlySeries,
    OperatingCosts,
    Scenario,
    Sector,
    SectorDemand,
    SeriesUnit,
    TerminalCondition,
    TerminalMode,
)

_SYNTHETIC_NOTE = (
    "All numerical values are deterministic synthetic assumptions for software development "
    "and testing; they are not measured city data or published observations."
)
_PROVENANCE = DataProvenance(origin=DataOrigin.SYNTHETIC, note=_SYNTHETIC_NOTE)


def _energy(values: tuple[float, ...] | list[float]) -> HourlySeries:
    return HourlySeries(tuple(values), SeriesUnit.ENERGY_MWH)


def _prices() -> HourlySeries:
    values = tuple(
        0.12 if hour < 7 or hour >= 22 else 0.24 if 16 <= hour < 22 else 0.16
        for hour in range(HORIZON_HOURS)
    )
    return HourlySeries(values, SeriesUnit.CURRENCY_PER_MWH)


def _solar(multiplier: float) -> HourlySeries:
    values = tuple(
        multiplier * 10.0 * max(0.0, math.sin(math.pi * (hour - 6) / 12.0))
        for hour in range(HORIZON_HOURS)
    )
    return _energy(values)


def _sector_profiles(scales: dict[Sector, float]) -> tuple[SectorDemand, ...]:
    demands = {
        Sector.HOSPITALS: tuple(
            (8.0 + (1.0 if 7 <= hour <= 10 or 17 <= hour <= 20 else 0.0))
            * scales.get(Sector.HOSPITALS, 1.0)
            for hour in range(HORIZON_HOURS)
        ),
        Sector.WATER: tuple(
            (5.0 + (1.5 if 6 <= hour <= 10 or 17 <= hour <= 20 else 0.0))
            * scales.get(Sector.WATER, 1.0)
            for hour in range(HORIZON_HOURS)
        ),
        Sector.PUBLIC_LIGHTING: tuple(
            (2.5 if hour < 6 or hour >= 19 else 0.25)
            * scales.get(Sector.PUBLIC_LIGHTING, 1.0)
            for hour in range(HORIZON_HOURS)
        ),
    }
    floor_fractions = {
        Sector.HOSPITALS: 0.60,
        Sector.WATER: 0.45,
        Sector.PUBLIC_LIGHTING: 0.35,
    }
    return tuple(
        SectorDemand(
            sector=sector,
            demand=_energy(list(values)),
            essential_floor=_energy([value * floor_fractions[sector] for value in values]),
        )
        for sector, values in demands.items()
    )


def _battery(terminal: TerminalCondition | None = None) -> BatteryParameters:
    return BatteryParameters(
        capacity_mwh=80.0,
        minimum_soc_mwh=8.0,
        initial_soc_mwh=40.0,
        max_charge_power_mw=18.0,
        max_discharge_power_mw=18.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        terminal_condition=terminal or TerminalCondition(mode=TerminalMode.CYCLIC),
    )


def _cohort(
    cohort_id: str,
    requested_mwh: float,
    arrival: int,
    departure: int,
    available_hour_limits_mw: tuple[float, ...],
    critical_floor_mwh: float | None = None,
) -> EVChargingCohort:
    if len(available_hour_limits_mw) != departure - arrival:
        raise ValueError("hourly EV power limits must match the availability window length")
    power_limits = [0.0] * HORIZON_HOURS
    power_limits[arrival:departure] = available_hour_limits_mw
    return EVChargingCohort(
        cohort_id=cohort_id,
        requested_energy_mwh=requested_mwh,
        arrival_slot=arrival,
        departure_slot=departure,
        charging_power_limits_mw=tuple(power_limits),
        critical_floor_mwh=critical_floor_mwh,
    )


def _scenario(
    scenario_id: str,
    name: str,
    description: str,
    *,
    solar_multiplier: float = 1.0,
    demand_scales: dict[Sector, float] | None = None,
    grid_limit_mwh: float = 40.0,
    outage_slots: range = range(0),
    ev_cohorts: tuple[EVChargingCohort, ...],
    terminal: TerminalCondition | None = None,
) -> Scenario:
    grid = [grid_limit_mwh] * HORIZON_HOURS
    for hour in outage_slots:
        grid[hour] = 0.0
    return Scenario(
        scenario_id=scenario_id,
        name=name,
        description=f"{description} {_SYNTHETIC_NOTE}",
        provenance=_PROVENANCE,
        sector_demands=_sector_profiles(demand_scales or {}),
        solar_generation=_solar(solar_multiplier),
        grid_import_limit=_energy(grid),
        ev_cohorts=ev_cohorts,
        battery=_battery(terminal),
        operating_costs=OperatingCosts(
            grid_price_per_mwh=_prices(),
            battery_degradation_per_mwh=0.01,
            currency="synthetic-unit",
        ),
    )


_SCENARIOS = {
    "normal-weekday": _scenario(
        "normal-weekday",
        "Normal weekday",
        "Baseline demand and supply profiles.",
        ev_cohorts=(_cohort("weekday-ev", 18.0, 17, 24, (6.0,) * 7),),
    ),
    "solar-rich-day": _scenario(
        "solar-rich-day",
        "Solar-rich day",
        "Illustrative increase in available solar energy.",
        solar_multiplier=1.8,
        ev_cohorts=(
            _cohort("solar-day-ev", 24.0, 15, 24, (6.0, 6.0, 7.0, 7.0, 7.0, 6.0, 5.0, 4.0, 3.0)),
        ),
    ),
    "cloudy-evening-peak": _scenario(
        "cloudy-evening-peak",
        "Cloudy evening peak",
        "Reduced solar availability with higher evening water demand.",
        solar_multiplier=0.25,
        demand_scales={Sector.WATER: 1.10},
        ev_cohorts=(_cohort("evening-ev", 30.0, 16, 23, (4.0, 6.0, 8.0, 8.0, 6.0, 4.0, 2.0)),),
    ),
    "constrained-grid-peak": _scenario(
        "constrained-grid-peak",
        "Constrained-grid peak",
        "Reduced grid import limit with elevated hospital and water demand.",
        solar_multiplier=0.8,
        demand_scales={Sector.HOSPITALS: 1.05, Sector.WATER: 1.05},
        grid_limit_mwh=18.0,
        ev_cohorts=(_cohort("weekday-ev", 18.0, 17, 24, (6.0,) * 7),),
    ),
    "heatwave": _scenario(
        "heatwave",
        "Heatwave",
        "Elevated assumed hospital and water energy demand.",
        demand_scales={Sector.HOSPITALS: 1.25, Sector.WATER: 1.35},
        grid_limit_mwh=30.0,
        ev_cohorts=(_cohort("weekday-ev", 18.0, 17, 24, (6.0,) * 7),),
        terminal=TerminalCondition(TerminalMode.MINIMUM_SOC, minimum_soc_mwh=16.0),
    ),
    "grid-outage": _scenario(
        "grid-outage",
        "Grid outage",
        "Grid imports are unavailable from slot 12 through slot 17.",
        outage_slots=range(12, 18),
        ev_cohorts=(_cohort("weekday-ev", 18.0, 17, 24, (6.0,) * 7),),
        terminal=TerminalCondition(TerminalMode.MINIMUM_SOC, minimum_soc_mwh=16.0),
    ),
    "city-under-pressure": _scenario(
        "city-under-pressure",
        "CITY UNDER PRESSURE",
        "Combined heatwave demand, solar reduction, a grid outage, and an EV charging surge.",
        solar_multiplier=0.5,
        demand_scales={Sector.HOSPITALS: 1.30, Sector.WATER: 1.45},
        outage_slots=range(12, 24),
        ev_cohorts=(
            _cohort("critical-response-fleet", 18.0, 16, 23, (4.0,) * 7, critical_floor_mwh=12.0),
            _cohort("sudden-public-ev-surge", 42.0, 17, 23, (8.0,) * 6),
        ),
        terminal=TerminalCondition(TerminalMode.MINIMUM_SOC, minimum_soc_mwh=12.0),
    ),
}

SCENARIOS = MappingProxyType(_SCENARIOS)


def get_scenarios() -> tuple[Scenario, ...]:
    """Return the seven immutable synthetic scenarios in catalog order."""
    return tuple(SCENARIOS.values())


def get_scenario(scenario_id: str) -> Scenario:
    """Return a scenario by id, raising ValueError for unknown ids."""
    try:
        return SCENARIOS[scenario_id]
    except (KeyError, TypeError) as error:
        raise ValueError(f"unknown scenario id: {scenario_id!r}") from error