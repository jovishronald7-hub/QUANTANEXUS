import math
import unittest

from quantanexus.models import (
    BatteryParameters,
    EVChargingCohort,
    HourlySeries,
    Scenario,
    Sector,
    SectorDemand,
    SeriesUnit,
    TerminalCondition,
    TerminalMode,
)
from quantanexus.scenarios import get_scenario
from quantanexus.validation import ScenarioValidationError


class HourlySeriesTests(unittest.TestCase):
    def test_requires_exactly_24_values(self) -> None:
        with self.assertRaises(ScenarioValidationError):
            HourlySeries((1.0,) * 23, SeriesUnit.ENERGY_MWH)

    def test_rejects_negative_energy_and_non_finite_values(self) -> None:
        with self.assertRaises(ScenarioValidationError):
            HourlySeries((-1.0,) + (0.0,) * 23, SeriesUnit.ENERGY_MWH)
        with self.assertRaises(ScenarioValidationError):
            HourlySeries((math.nan,) + (0.0,) * 23, SeriesUnit.ENERGY_MWH)

    def test_rejects_unknown_units(self) -> None:
        with self.assertRaises(ScenarioValidationError):
            HourlySeries((0.0,) * 24, "kW")  # type: ignore[arg-type]

    def test_allows_negative_prices_but_not_negative_energy(self) -> None:
        prices = HourlySeries((-0.1,) * 24, SeriesUnit.CURRENCY_PER_MWH)
        self.assertEqual(len(prices.values), 24)


class EVFeasibilityTests(unittest.TestCase):
    def test_separates_structural_and_operational_shortfall(self) -> None:
        cohort = EVChargingCohort(
            cohort_id="limited-window",
            requested_energy_mwh=50.0,
            arrival_slot=18,
            departure_slot=22,
            charging_power_limits_mw=(0.0,) * 18 + (4.0, 0.0, 8.0, 2.0) + (0.0,) * 2,
            critical_floor_mwh=25.0,
        )
        feasibility = cohort.structural_feasibility
        self.assertEqual(feasibility.connection_capacity_mwh, 14.0)
        self.assertEqual(cohort.maximum_deliverable_energy_mwh, 14.0)
        self.assertEqual(feasibility.structurally_impossible_mwh, 36.0)
        self.assertEqual(feasibility.deliverable_obligation_mwh, 14.0)
        self.assertEqual(feasibility.critical_floor_structurally_impossible_mwh, 11.0)

        assessment = cohort.assess_delivery(10.0)
        self.assertEqual(assessment.structural_unmet_mwh, 36.0)
        self.assertEqual(assessment.operational_unmet_mwh, 4.0)
        self.assertEqual(assessment.total_unmet_mwh, 40.0)

    def test_reports_structurally_impossible_critical_floor(self) -> None:
        cohort = EVChargingCohort(
            "short-window",
            50.0,
            18,
            22,
            (0.0,) * 18 + (8.0,) * 4 + (0.0,) * 2,
            critical_floor_mwh=40.0,
        )
        self.assertEqual(cohort.structural_feasibility.critical_floor_structurally_impossible_mwh, 8.0)

    def test_rejects_invalid_window_power_and_floor(self) -> None:
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("bad-window", 5.0, 8, 8, (0.0,) * 24)
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("bad-power", 5.0, 8, 10, (0.0,) * 8 + (-1.0, 0.0) + (0.0,) * 14)
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("bad-floor", 5.0, 8, 10, (0.0,) * 8 + (2.0, 2.0) + (0.0,) * 14, critical_floor_mwh=6.0)
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("bad-slot", 5.0, 0, 25, (0.0,) * 24)
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("bad-length", 5.0, 8, 10, (0.0,) * 23)
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("bad-nan", 5.0, 8, 10, (0.0,) * 8 + (float("nan"), 2.0) + (0.0,) * 14)
        with self.assertRaises(ScenarioValidationError):
            EVChargingCohort("outside-window", 5.0, 8, 10, (1.0,) + (0.0,) * 23)

    def test_zero_charging_capacity_is_fully_structural(self) -> None:
        cohort = EVChargingCohort("no-charger", 5.0, 8, 10, (0.0,) * 24)
        feasibility = cohort.structural_feasibility
        self.assertEqual(feasibility.connection_capacity_mwh, 0.0)
        self.assertEqual(feasibility.structurally_impossible_mwh, 5.0)
        self.assertEqual(feasibility.deliverable_obligation_mwh, 0.0)
        assessment = cohort.assess_delivery(0.0)
        self.assertEqual(assessment.operational_unmet_mwh, 0.0)

    def test_rejects_delivery_above_structural_obligation(self) -> None:
        cohort = EVChargingCohort("small", 5.0, 10, 12, (0.0,) * 10 + (2.0, 2.0) + (0.0,) * 12)
        with self.assertRaises(ScenarioValidationError):
            cohort.assess_delivery(5.1)

    def test_zero_request_has_no_operational_unmet_demand(self) -> None:
        cohort = EVChargingCohort("empty", 0.0, 10, 12, (0.0,) * 10 + (2.0, 2.0) + (0.0,) * 12)
        assessment = cohort.assess_delivery(0.0)
        self.assertEqual(assessment.structural_unmet_mwh, 0.0)
        self.assertEqual(assessment.operational_unmet_mwh, 0.0)


class BatteryAndScenarioValidationTests(unittest.TestCase):
    def test_rejects_invalid_efficiency_initial_soc_and_terminal_condition(self) -> None:
        base = {
            "capacity_mwh": 10.0,
            "minimum_soc_mwh": 1.0,
            "initial_soc_mwh": 5.0,
            "max_charge_power_mw": 2.0,
            "max_discharge_power_mw": 2.0,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "terminal_condition": TerminalCondition(TerminalMode.CYCLIC),
        }
        with self.assertRaises(ScenarioValidationError):
            BatteryParameters(**(base | {"charge_efficiency": 0.0}))
        with self.assertRaises(ScenarioValidationError):
            BatteryParameters(**(base | {"initial_soc_mwh": 11.0}))
        with self.assertRaises(ScenarioValidationError):
            BatteryParameters(**(base | {"terminal_condition": TerminalCondition(TerminalMode.MINIMUM_SOC, 11.0)}))

    def test_accepts_zero_capacity_battery(self) -> None:
        battery = BatteryParameters(
            capacity_mwh=0.0,
            minimum_soc_mwh=0.0,
            initial_soc_mwh=0.0,
            max_charge_power_mw=0.0,
            max_discharge_power_mw=0.0,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
            terminal_condition=TerminalCondition(TerminalMode.CYCLIC),
        )
        self.assertEqual(battery.capacity_mwh, 0.0)

    def test_rejects_sector_floor_above_demand(self) -> None:
        demand = HourlySeries((1.0,) * 24, SeriesUnit.ENERGY_MWH)
        floor = HourlySeries((2.0,) + (1.0,) * 23, SeriesUnit.ENERGY_MWH)
        with self.assertRaises(ScenarioValidationError):
            SectorDemand(Sector.HOSPITALS, demand, floor)

    def test_rejects_incomplete_scenario_sector_set(self) -> None:
        scenario = get_scenario("normal-weekday")
        with self.assertRaises(ScenarioValidationError):
            Scenario(
                scenario_id="missing-sector",
                name="Missing sector",
                description="Invalid test scenario.",
                provenance=scenario.provenance,
                sector_demands=scenario.sector_demands[:2],
                solar_generation=scenario.solar_generation,
                grid_import_limit=scenario.grid_import_limit,
                ev_cohorts=scenario.ev_cohorts,
                battery=scenario.battery,
                operating_costs=scenario.operating_costs,
            )


if __name__ == "__main__":
    unittest.main()