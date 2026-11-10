# QUANTANEXUS
A Quantum-Inspired Smart City Optimization and Simulation Platform.

## Phase 1: Project Foundation

This repository currently contains the scenario data model and strict input validation only. It does not yet implement an optimizer, QUBO, annealer, experiment runner, or dashboard.

The seven bundled scenarios are deterministic **synthetic assumptions** for development and testing. They are not measured city data and are not represented as published data.

### Project structure

```text
src/quantanexus/
	models.py                 Immutable domain models and EV feasibility
	validation.py             Shared value and cross-model validation
	scenarios.py              Seven synthetic scenario definitions
	optimization/             Reserved for the classical MILP phase
	solution_validation/      Reserved for independent schedule validation
	qubo/                     Reserved for QUBO formulation
	experiments/              Reserved for reproducible experiments
	dashboard/                Reserved for the Streamlit dashboard
tests/                      Standard-library automated tests
```

### Environment and dependencies

Python 3.13 or newer is supported. Phase 1 has no runtime dependencies and uses the Python standard library. The package uses `setuptools` as its PEP 517 build backend.

```bash
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

The editable install may download the build backend if it is not already available. No MILP, QUBO, simulated-annealing, plotting, or Streamlit packages are included until their implementation phases.

### Units and scenario data

Hourly demand, solar generation, grid import limits, EV obligations, and battery energy are in MWh per one-hour slot. Battery charge/discharge limits and EV charging limits are in MW. Efficiencies are dimensionless fractions in `(0, 1]`. Grid prices and battery degradation costs use the scenario's declared model currency per MWh. Synthetic cost values are illustrative assumptions only.

EV cohort input validation reports connection-window deliverable energy separately from any future operational shortfall. A critical EV floor is an energy obligation by the cohort's deadline, not a per-hour charging target.
