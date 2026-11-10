"""Immutable scenario and resource data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .validation import (
    ScenarioValidationError,
    finite_number,
    fixed_length_values,
    nonempty_string,
    nonnegative_number,
    validate_scenario_components,
)

HORIZON_HOURS = 24
SLOT_HOURS = 1.0


class Sector(str, Enum):
    HOSPITALS = "hospitals"
    WATER = "water"
    PUBLIC_LIGHTING = "public_lighting"


class SeriesUnit(str, Enum):
    ENERGY_MWH = "MWh"
    CURRENCY_PER_MWH = "currency/MWh"


class DataOrigin(str, Enum):
    SYNTHETIC = "synthetic_assumption"
    PUBLISHED = "published_data"


class TerminalMode(str, Enum):
    CYCLIC = "cyclic"
    MINIMUM_SOC = "minimum_soc"


@dataclass(frozen=True, slots=True)
class HourlySeries:
    values: tuple[float, ...]
    unit: SeriesUnit

    def __post_init__(self) -> None:
        if not isinstance(self.unit, SeriesUnit):
            raise ScenarioValidationError("unit must be a supported SeriesUnit")
        values = fixed_length_values(self.values, HORIZON_HOURS, "hourly series")
        if self.unit is SeriesUnit.ENERGY_MWH and any(value < 0 for value in values):
            raise ScenarioValidationError("energy series values must be non-negative")
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class SectorDemand:
    sector: Sector
    demand: HourlySeries
    essential_floor: HourlySeries

    def __post_init__(self) -> None:
        if not isinstance(self.sector, Sector):
            raise ScenarioValidationError("sector must be a supported Sector")
        if not isinstance(self.demand, HourlySeries) or not isinstance(self.essential_floor, HourlySeries):
            raise ScenarioValidationError("demand and essential_floor must be HourlySeries instances")
        if self.demand.unit is not SeriesUnit.ENERGY_MWH:
            raise ScenarioValidationError("sector demand must use MWh units")
        if self.essential_floor.unit is not SeriesUnit.ENERGY_MWH:
            raise ScenarioValidationError("essential floors must use MWh units")
        if any(floor > demand for demand, floor in zip(self.demand.values, self.essential_floor.values)):
            raise ScenarioValidationError("essential-service floors must not exceed requested demand")


@dataclass(frozen=True, slots=True)
class EVStructuralFeasibility:
    requested_energy_mwh: float
    connection_capacity_mwh: float
    structurally_impossible_mwh: float
    deliverable_obligation_mwh: float
    critical_floor_structurally_impossible_mwh: float | None


@dataclass(frozen=True, slots=True)
class EVDeliveryAssessment:
    structural_unmet_mwh: float
    operational_unmet_mwh: float

    @property
    def total_unmet_mwh(self) -> float:
        return self.structural_unmet_mwh + self.operational_unmet_mwh


@dataclass(frozen=True, slots=True)
class EVChargingCohort:
    cohort_id: str
    requested_energy_mwh: float
    arrival_slot: int
    departure_slot: int
    charging_power_limits_mw: tuple[float, ...]
    critical_floor_mwh: float | None = None

    def __post_init__(self) -> None:
        nonempty_string(self.cohort_id, "cohort_id")
        requested = nonnegative_number(self.requested_energy_mwh, "requested_energy_mwh")
        if isinstance(self.arrival_slot, bool) or not isinstance(self.arrival_slot, int):
            raise ScenarioValidationError("arrival_slot must be an integer")
        if isinstance(self.departure_slot, bool) or not isinstance(self.departure_slot, int):
            raise ScenarioValidationError("departure_slot must be an integer")
        if not 0 <= self.arrival_slot < self.departure_slot <= HORIZON_HOURS:
            raise ScenarioValidationError("EV window must satisfy 0 <= arrival < departure <= 24")
        power_limits = fixed_length_values(
            self.charging_power_limits_mw,
            HORIZON_HOURS,
            "charging_power_limits_mw",
        )
        if any(power < 0 for power in power_limits):
            raise ScenarioValidationError("EV charging power limits must be non-negative")
        if any(
            power != 0
            for slot, power in enumerate(power_limits)
            if not self.arrival_slot <= slot < self.departure_slot
        ):
            raise ScenarioValidationError("EV charging power must be zero outside the availability window")
        if self.critical_floor_mwh is not None:
            floor = nonnegative_number(self.critical_floor_mwh, "critical_floor_mwh")
            if floor == 0:
                raise ScenarioValidationError("a critical EV floor must be positive or omitted")
            if floor > requested:
                raise ScenarioValidationError("critical EV floor must not exceed requested cohort energy")
            object.__setattr__(self, "critical_floor_mwh", floor)
        object.__setattr__(self, "requested_energy_mwh", requested)
        object.__setattr__(self, "charging_power_limits_mw", power_limits)

    @property
    def maximum_deliverable_energy_mwh(self) -> float:
        return sum(
            self.charging_power_limits_mw[slot] * SLOT_HOURS
            for slot in range(self.arrival_slot, self.departure_slot)
        )

    @property
    def connection_capacity_mwh(self) -> float:
        """Compatibility alias for the hourly-profile-derived deliverable capacity."""
        return self.maximum_deliverable_energy_mwh

    @property
    def structural_feasibility(self) -> EVStructuralFeasibility:
        capacity = self.maximum_deliverable_energy_mwh
        deliverable = min(self.requested_energy_mwh, capacity)
        floor_structural = (
            None
            if self.critical_floor_mwh is None
            else max(0.0, self.critical_floor_mwh - capacity)
        )
        return EVStructuralFeasibility(
            requested_energy_mwh=self.requested_energy_mwh,
            connection_capacity_mwh=capacity,
            structurally_impossible_mwh=self.requested_energy_mwh - deliverable,
            deliverable_obligation_mwh=deliverable,
            critical_floor_structurally_impossible_mwh=floor_structural,
        )

    def assess_delivery(self, delivered_energy_mwh: float) -> EVDeliveryAssessment:
        delivered = nonnegative_number(delivered_energy_mwh, "delivered_energy_mwh")
        feasibility = self.structural_feasibility
        if delivered > feasibility.deliverable_obligation_mwh:
            raise ScenarioValidationError("delivered EV energy exceeds the deliverable cohort obligation")
        return EVDeliveryAssessment(
            structural_unmet_mwh=feasibility.structurally_impossible_mwh,
            operational_unmet_mwh=feasibility.deliverable_obligation_mwh - delivered,
        )


@dataclass(frozen=True, slots=True)
class TerminalCondition:
    mode: TerminalMode
    minimum_soc_mwh: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, TerminalMode):
            raise ScenarioValidationError("terminal mode must be a supported TerminalMode")
        if self.mode is TerminalMode.CYCLIC:
            if self.minimum_soc_mwh is not None:
                raise ScenarioValidationError("cyclic terminal conditions do not take a minimum SOC")
        else:
            if self.minimum_soc_mwh is None:
                raise ScenarioValidationError("minimum-SOC terminal conditions require minimum_soc_mwh")
            object.__setattr__(
                self,
                "minimum_soc_mwh",
                nonnegative_number(self.minimum_soc_mwh, "terminal minimum_soc_mwh"),
            )


@dataclass(frozen=True, slots=True)
class BatteryParameters:
    capacity_mwh: float
    minimum_soc_mwh: float
    initial_soc_mwh: float
    max_charge_power_mw: float
    max_discharge_power_mw: float
    charge_efficiency: float
    discharge_efficiency: float
    terminal_condition: TerminalCondition

    def __post_init__(self) -> None:
        names = (
            "capacity_mwh",
            "minimum_soc_mwh",
            "initial_soc_mwh",
            "max_charge_power_mw",
            "max_discharge_power_mw",
        )
        for name in names:
            object.__setattr__(self, name, nonnegative_number(getattr(self, name), name))
        for name in ("charge_efficiency", "discharge_efficiency"):
            efficiency = finite_number(getattr(self, name), name)
            if not 0 < efficiency <= 1:
                raise ScenarioValidationError(f"{name} must be in (0, 1]")
            object.__setattr__(self, name, efficiency)

        if self.minimum_soc_mwh > self.capacity_mwh:
            raise ScenarioValidationError("minimum SOC must not exceed battery capacity")
        if not self.minimum_soc_mwh <= self.initial_soc_mwh <= self.capacity_mwh:
            raise ScenarioValidationError("initial SOC must lie between minimum SOC and capacity")
        if self.capacity_mwh == 0 and (
            self.minimum_soc_mwh != 0
            or self.initial_soc_mwh != 0
            or self.max_charge_power_mw != 0
            or self.max_discharge_power_mw != 0
        ):
            raise ScenarioValidationError("a zero-capacity battery must have zero SOC and power limits")
        if not isinstance(self.terminal_condition, TerminalCondition):
            raise ScenarioValidationError("terminal_condition must be a TerminalCondition")
        if self.terminal_condition.mode is TerminalMode.MINIMUM_SOC:
            target = self.terminal_condition.minimum_soc_mwh
            if target is None or not self.minimum_soc_mwh <= target <= self.capacity_mwh:
                raise ScenarioValidationError("terminal SOC target must lie within battery SOC bounds")


@dataclass(frozen=True, slots=True)
class OperatingCosts:
    grid_price_per_mwh: HourlySeries
    battery_degradation_per_mwh: float
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.grid_price_per_mwh, HourlySeries):
            raise ScenarioValidationError("grid_price_per_mwh must be an HourlySeries")
        if self.grid_price_per_mwh.unit is not SeriesUnit.CURRENCY_PER_MWH:
            raise ScenarioValidationError("grid prices must use currency/MWh units")
        object.__setattr__(
            self,
            "battery_degradation_per_mwh",
            nonnegative_number(self.battery_degradation_per_mwh, "battery_degradation_per_mwh"),
        )
        object.__setattr__(self, "currency", nonempty_string(self.currency, "currency"))


@dataclass(frozen=True, slots=True)
class DataProvenance:
    origin: DataOrigin
    note: str
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, DataOrigin):
            raise ScenarioValidationError("origin must be a supported DataOrigin")
        object.__setattr__(self, "note", nonempty_string(self.note, "provenance note"))
        if self.origin is DataOrigin.PUBLISHED:
            if self.source_reference is None:
                raise ScenarioValidationError("published data requires a source reference")
            object.__setattr__(
                self,
                "source_reference",
                nonempty_string(self.source_reference, "source_reference"),
            )
        elif self.source_reference is not None:
            object.__setattr__(
                self,
                "source_reference",
                nonempty_string(self.source_reference, "source_reference"),
            )


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    name: str
    description: str
    provenance: DataProvenance
    sector_demands: tuple[SectorDemand, ...]
    solar_generation: HourlySeries
    grid_import_limit: HourlySeries
    ev_cohorts: tuple[EVChargingCohort, ...]
    battery: BatteryParameters
    operating_costs: OperatingCosts

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", nonempty_string(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "name", nonempty_string(self.name, "scenario name"))
        object.__setattr__(self, "description", nonempty_string(self.description, "scenario description"))
        if not isinstance(self.provenance, DataProvenance):
            raise ScenarioValidationError("provenance must be a DataProvenance")
        if not isinstance(self.solar_generation, HourlySeries):
            raise ScenarioValidationError("solar_generation must be an HourlySeries")
        if not isinstance(self.grid_import_limit, HourlySeries):
            raise ScenarioValidationError("grid_import_limit must be an HourlySeries")
        if not isinstance(self.battery, BatteryParameters):
            raise ScenarioValidationError("battery must be BatteryParameters")
        if not isinstance(self.operating_costs, OperatingCosts):
            raise ScenarioValidationError("operating_costs must be OperatingCosts")

        sectors = tuple(self.sector_demands)
        cohorts = tuple(self.ev_cohorts)
        if any(not isinstance(item, SectorDemand) for item in sectors):
            raise ScenarioValidationError("sector_demands must contain SectorDemand instances")
        if any(not isinstance(item, EVChargingCohort) for item in cohorts):
            raise ScenarioValidationError("ev_cohorts must contain EVChargingCohort instances")
        object.__setattr__(self, "sector_demands", sectors)
        object.__setattr__(self, "ev_cohorts", cohorts)

        validate_scenario_components(
            sector_demands=sectors,
            solar=self.solar_generation,
            grid_import_limit=self.grid_import_limit,
            ev_cohorts=cohorts,
            operating_costs=self.operating_costs,
        )
        if self.solar_generation.unit is not SeriesUnit.ENERGY_MWH:
            raise ScenarioValidationError("solar generation must use MWh units")
        if self.grid_import_limit.unit is not SeriesUnit.ENERGY_MWH:
            raise ScenarioValidationError("grid import limits must use MWh units")

    def demand_for(self, sector: Sector) -> SectorDemand:
        if not isinstance(sector, Sector):
            raise ScenarioValidationError("sector must be a supported Sector")
        return next(item for item in self.sector_demands if item.sector is sector)