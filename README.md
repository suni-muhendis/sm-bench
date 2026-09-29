# SM-Bench

[![Tests](https://github.com/suni-muhendis/sm-bench/actions/workflows/tests.yml/badge.svg)](https://github.com/suni-muhendis/sm-bench/actions/workflows/tests.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-31210/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#project-status)

**Physics-based evaluation environments for machine-generated engineering designs.**

Part of [Suni Muhendis](https://github.com/suni-muhendis). The library is
published as the `sunimuhendis` Python package.

SM-Bench turns a proposed design into structured engineering feedback and a
normalized score. Each environment applies schema validation, design-rule checks,
a deterministic physics simulation, and a versioned scoring function. The same
API can be used from this repository, an optimizer, or a separate training system.

> **Project status:** public research software in alpha. The heat-exchanger
> environment is available; further engineering domains are planned.

## Available environments

| Environment | Status | Install extra |
|---|---|---|
| `heat_exchanger` | Available; simulator V4 and versioned scores | `heat_exchanger` |

The heat-exchanger environment supports shell-and-tube and concentric-tube
geometries. It uses `ht` and `fluids` where suitable, with additional
shell-side, cost, mechanical, and correlation-validity checks implemented in
the environment.

## Install

Python 3.12 is required. Install from a release tag so simulator and scoring
behavior cannot move underneath an experiment:

```bash
pip install "sunimuhendis[heat_exchanger] @ git+https://github.com/suni-muhendis/sm-bench.git@envs-v0.7.0"
```

The supported runtime contract is `>=3.12,<3.13`. Support for another Python
minor version is added only after the full test suite and clean-wheel consumer
checks pass on that version.

## Quick start

```python
from sunimuhendis import list_environments, make_env

print(list_environments())  # ['heat_exchanger']

env = make_env(
    "heat_exchanger",
    score_version="heat_exchanger_score_v4",
)

task = {
    "task_id": "example",
    "score_version": "heat_exchanger_score_v4",
    "target_heat_duty": 250_000.0,
    "max_dp_tube": 5_000.0,
    "max_dp_shell": 5_000.0,
}

design = {
    "geometry_type": "shell_and_tube",
    "length": 3.0,
    "inner_tube_di": 0.016,
    "inner_tube_do": 0.020,
    "outer_shell_di": 0.30,
    "number_of_tubes": 50,
    "baffle_spacing": 0.2,
}

result = env.evaluate("example", task, "design-1", design)

print(result.status)
print(result.score.normalized_total)
print(result.metrics)
```

Invalid model output is data, not an exception from the training loop.
`evaluate()` returns `schema_error`, `drc_error`, or `simulation_error` with a
score of `0.0`; successful simulations return a score in `[0.0, 1.0]` and the
engineering metrics used to calculate it.

## Evaluation contract

```text
design (JSON) -> schema -> design-rule checks -> simulation -> score
```

| Stage | Purpose | Failure status |
|---|---|---|
| Schema | Reject missing, extra, or incorrectly typed fields | `schema_error` |
| DRC | Reject impossible geometry before expensive work | `drc_error` |
| Simulation | Run the versioned engineering model | `simulation_error` |
| Score | Convert valid metrics into a benchmark score | `success` |

Evaluation is deterministic within the pinned runtime and dependency profile.
Every stored benchmark record carries the simulator and score versions that
produced it. Results from different versions must not be pooled implicitly.

## Repository map

| Path | Contents |
|---|---|
| `src/sunimuhendis/core/` | Environment-independent evaluation contracts |
| `src/sunimuhendis/environments/` | Physics environments and registry |
| `scripts/` | Benchmark, audit, reporting, and dashboard tools |
| `results/` | Versioned experiment definitions and recorded runs |
| `reports/` | Engineering audits and research evidence |
| `tests/` | Unit, regression, packaging, and runtime tests |

The wheel contains `core`, `environments`, `parsing`, and `prompts`. Benchmark
clients, samplers, the dashboard, stored results, and research artifacts remain
repository tools and are excluded from the wheel.

## Documentation

- [Documentation site and leaderboard](https://suni-muhendis.github.io/sm-bench/)
- [Library API and task auditing](docs/library.md)
- [Benchmarking, cost accounting, and dashboard](docs/benchmarking.md)
- [Development and release workflow](docs/development.md)
- [Experiment track layout](results/EXPERIMENT_TRACKS.md)
- [Architecture decisions](ARCHITECTURE_DECISIONS.md)

## Development

```bash
git clone https://github.com/suni-muhendis/sm-bench.git
cd sm-bench
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints/python312.txt -r requirements.txt -e .
python -m pytest tests/ -q
```

On Windows, create the environment with `py -3.12 -m venv .venv` and activate
it with `.venv\Scripts\Activate.ps1`. See [the development guide](docs/development.md)
for packaging checks and the clean consumer test.

API keys are read from a git-ignored `.env`; copy `.env.example` and add only
the providers you use.

## Benchmark dashboard

The repository includes a Streamlit dashboard for exploring every recorded
benchmark run. From the development environment above:

```bash
streamlit run scripts/dashboard.py
```

It opens in the browser and reads the results stored under `results/`, so no
API key is needed to browse them. Pick an experiment track and task, then use
the tabs:

| Tab | Shows |
|---|---|
| Overview | Evaluation funnel (responded → parsed → schema → DRC → simulated) and headline scores |
| Runs | Individual run records: raw response, parsed design, metrics, score breakdown, provenance |
| Leaderboard | Model ranking for the selected task |
| Engineering | Requirement compliance (duty target, pressure-drop limits) and design diversity |
| Reliability | Reliability and inference efficiency: cost per benchmark point, and whether more reasoning effort pays off |
| Spend | All-time token use and cost across every task |
| Task | The task definition, prompt, and notes |

## Project status

- **Available:** heat-exchanger evaluation, task feasibility auditing,
  zero-shot benchmark runner, cost ledger, and Streamlit dashboard.
- **Planned:** feedback-driven experiments and additional engineering domains.

## License, citation, and security

Source code is licensed under the [Apache License 2.0](LICENSE). Benchmark data
and project-authored reports are covered separately by
[CC BY 4.0](results/LICENSE.md); third-party model responses are explicitly
excluded from that grant. Third-party provenance is documented in
[THIRD_PARTY.md](THIRD_PARTY.md).

Use [CITATION.cff](CITATION.cff) when citing the software. Report
vulnerabilities through the private process in [SECURITY.md](SECURITY.md).
