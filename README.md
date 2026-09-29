# SM-Bench

[![Tests](https://github.com/suni-muhendis/sm-bench/actions/workflows/tests.yml/badge.svg)](https://github.com/suni-muhendis/sm-bench/actions/workflows/tests.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-31210/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#project-status)

**A benchmark of machine-generated engineering designs, judged by physics
simulation.**

Part of [Suni Muhendis](https://github.com/suni-muhendis). SM-Bench sends
engineering design tasks to language models, evaluates every answer with a
deterministic physics environment, and records the result: score, engineering
metrics, failure stage, tokens and cost. This repository holds the benchmark
runners, the recorded results, a Streamlit dashboard, and the
[documentation site and leaderboard](https://suni-muhendis.github.io/sm-bench/).

> **Project status:** public research software in alpha. The heat-exchanger
> environment is available; further engineering domains are planned.

## Environments

The environments are packages of their own, built on a shared evaluation
contract:

| Package | Provides |
|---|---|
| [sm-core](https://github.com/suni-muhendis/sm-core) | The evaluation contract, `make_env`, task auditing, `parse_llm_json` |
| [sm-heat-exchanger](https://github.com/suni-muhendis/sm-heat-exchanger) | `heat_exchanger`: shell-and-tube and concentric-tube exchangers, simulator V4, scores V1–V4 |

To evaluate designs outside this benchmark (an optimiser, a separate training
system), install an environment directly; it brings `sm-core` with it:

```bash
pip install "sm-heat-exchanger @ git+https://github.com/suni-muhendis/sm-heat-exchanger.git@v0.8.0"
```

```python
from sm_core import make_env

env = make_env("heat_exchanger")
result = env.evaluate("example", task, "design-1", design)
result.status, result.score.normalized_total, result.metrics
```

Up to `envs-v0.7.0` the contract and the heat exchanger shipped from this
repository as the `sunimuhendis` package. Those tags stay installable and
produce identical scores.

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

Invalid model output is data, not an exception: it scores `0.0` with the stage
it failed at. Every stored benchmark record carries the environment and the
simulator and score versions that produced it; results from different versions
are never pooled.

## Repository map

| Path | Contents |
|---|---|
| `scripts/` | Benchmark runners, task calibration, reporting, dashboard |
| `src/sm_bench/` | Model clients and run logging used by the scripts |
| `results/` | Versioned task definitions and recorded runs |
| `reports/` | Task calibration and audit records |
| `configs/` | Model registry and archived price lists |
| `docs/` | Documentation site sources |
| `tests/` | Runner, dashboard, pricing and ledger tests |

## Documentation

- [Documentation site and leaderboard](https://suni-muhendis.github.io/sm-bench/)
- [Environments and task auditing](docs/library.md)
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
it with `.venv\Scripts\Activate.ps1`. The environments are installed from
their pinned tags in `pyproject.toml`.

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
