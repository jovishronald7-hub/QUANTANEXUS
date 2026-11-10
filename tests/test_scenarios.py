import unittest

from quantanexus.models import DataOrigin, Sector, SeriesUnit
from quantanexus.scenarios import get_scenario, get_scenarios


class ScenarioCatalogTests(unittest.TestCase):
    def test_catalog_contains_seven_named_scenarios(self) -> None:
        scenarios = get_scenarios()
        self.assertEqual(len(scenarios), 7)
        self.assertEqual(
            {scenario.scenario_id for scenario in scenarios},
            {
                "normal-weekday",
                "solar-rich-day",
                "cloudy-evening-peak",
                "constrained-grid-peak",
                "heatwave",
                "grid-outage",
                "city-under-pressure",
            },
        )

    def test_every_fixture_is_explicitly_synthetic(self) -> None:
        for scenario in get_scenarios():
            with self.subTest(scenario=scenario.scenario_id):
                self.assertIs(scenario.provenance.origin, DataOrigin.SYNTHETIC)
                self.assertIn("not measured city data", scenario.provenance.note)
                self.assertEqual(len(scenario.solar_generation.values), 24)
                self.assertEqual(len(scenario.grid_import_limit.values), 24)
                self.assertEqual(scenario.solar_generation.unit, SeriesUnit.ENERGY_MWH)
                for cohort in scenario.ev_cohorts:
                    self.assertEqual(len(cohort.charging_power_limits_mw), 24)
                    self.assertTrue(
                        all(
                            power == 0.0
                            for slot, power in enumerate(cohort.charging_power_limits_mw)
                            if not cohort.arrival_slot <= slot < cohort.departure_slot
                        )
                    )
                    self.assertEqual(
                        cohort.maximum_deliverable_energy_mwh,
                        sum(
                            cohort.charging_power_limits_mw[slot]
                            for slot in range(cohort.arrival_slot, cohort.departure_slot)
                        ),
                    )
                self.assertEqual(
                    {profile.sector for profile in scenario.sector_demands},
                    {Sector.HOSPITALS, Sector.WATER, Sector.PUBLIC_LIGHTING},
                )

    def test_scenario_uses_varying_hourly_ev_power_limits(self) -> None:
        cohort = get_scenario("cloudy-evening-peak").ev_cohorts[0]
        self.assertEqual(
            cohort.charging_power_limits_mw[16:23],
            (4.0, 6.0, 8.0, 8.0, 6.0, 4.0, 2.0),
        )

    def test_city_under_pressure_combines_documented_stresses(self) -> None:
        scenario = get_scenario("city-under-pressure")
        self.assertEqual(scenario.grid_import_limit.values[12:], (0.0,) * 12)
        critical = [cohort for cohort in scenario.ev_cohorts if cohort.critical_floor_mwh is not None]
        surge = [cohort for cohort in scenario.ev_cohorts if cohort.cohort_id == "sudden-public-ev-surge"]
        self.assertEqual(len(critical), 1)
        self.assertEqual(critical[0].critical_floor_mwh, 12.0)
        self.assertEqual(len(surge), 1)
        self.assertGreater(scenario.sector_demands[0].demand.values[0], 8.0)

    def test_unknown_scenario_id_is_reported(self) -> None:
        with self.assertRaises(ValueError):
            get_scenario("not-a-scenario")


if __name__ == "__main__":
    unittest.main()