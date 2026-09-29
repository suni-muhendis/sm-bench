# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository.

## What this is

SM-Bench is a benchmark of machine-generated engineering designs judged by physics simulation. This repository is the **benchmark application**: the runners that send tasks to models, the model clients, the recorded results under `results/`, the Streamlit dashboard and the documentation site. It is not a library.

The evaluation itself lives in separate packages, pinned by tag in `pyproject.toml`:

- [`sm-core`](https://github.com/suni-muhendis/sm-core) (`sm_core`): the evaluation contract (schema → DRC → simulate → score), `make_env`, task auditing, `parse_llm_json`.
- [`sm-heat-exchanger`](https://github.com/suni-muhendis/sm-heat-exchanger) (`sm_heat_exchanger`): the `heat_exchanger` environment, its prompt and design samplers.

Changes to the contract or to an environment's physics or score belong in those repositories; their `AGENTS.md` files describe them. Up to `envs-v0.7.0` both lived here as the `sunimuhendis` package, and those tags must keep working.

## Environment & commands

- **Setup:** dependencies live in a project venv. Activate it once per shell — `source .venv/bin/activate` — then use plain `python` / `pytest` / `streamlit`. Recreate with `python3.12 -m venv .venv` and `python -m pip install -c constraints/python312.txt -r requirements.txt -e .`, which also installs the pinned environment packages from GitHub.
- **Interpreter:** CPython **3.12**; the reproducible development version is in `.python-version`. The project declares `>=3.12,<3.13`.
- **Tests:** `pytest tests/ -v` — run a single file/test with `pytest tests/test_api_benchmark.py -v` or `-k <substring>`. Physics and contract tests live in the environment repositories.
- **Secrets:** API keys (`OPENROUTER_API_KEY`, `HF_TOKEN`, `OPENCODE_API_KEY`) are read from `.env` (gitignored; see `.env.example`) via `python-dotenv`.

### Run targets (all from repo root, venv activated)
- `python scripts/run_api_benchmark.py --prompt <slug> [--model NAME | --models a,b] [--repeats N]` — **automated zero-shot** benchmark: send `results/zero_shot/<slug>/prompt.txt` (scored by the adjacent `task.json`) to configured models, run each response through the environment the task names, and append results under that task's `api_runs/`. Core loop `run_benchmark(...)` takes an injectable `client_factory` (offline-testable with `DummyRandomClient`).
- `python scripts/run_llm_eval.py --client [dummy|interactive] --prompt <slug>` — **manual zero-shot** single-model chain; on success prompts for a model name and appends to `results/zero_shot/<slug>/manual_runs/`.
- `python scripts/calibrate_hard_task.py`, `python scripts/analyze_score_distribution.py` — heat-exchanger task calibration and score-distribution studies; records go to `reports/`.
- `python scripts/run_baseline.py` — generate ~10k designs with the heat-exchanger samplers, simulate all, and write the ones above a score threshold to `datasets/sft/heat_exchanger_initial.jsonl` (git-ignored).
- `python scripts/run_simulation.py` — pipeline demo that exercises every failure path (schema/DRC/sim/crash) with dummy components.
- `python scripts/rescore_benchmark_results.py --input … --output … --score-version …` — apply another score version to recorded metrics.
- `python scripts/token_report.py [--by model|month|task] [--as-of YYYY-MM-DD] [--csv out.csv]` — all-time token and spend ledger over every recorded run. Each run is priced twice: at the rate frozen into the record when it ran, and at a current or dated price list, so historical spend and today-equivalent spend are both reportable.
- `streamlit run scripts/dashboard.py` — track-first dashboard with isolated task catalogs. It reads the evaluation pipeline as a funnel (responded → parsed → schema → DRC → simulated), scores requirement compliance against the task config (duty target, both ΔP limits), reports design diversity, and keeps run-level exploration and exports. Its Spend tab reports the all-time token ledger across every task and track, independent of the on-screen filters. The feedback-driven track is currently a prepared placeholder only.

### Token and cost accounting
Every benchmark record carries a `usage` block (prompt / completion / reasoning / cached / total tokens), a `pricing_snapshot` and a `cost_usd` with `cost_basis` — `provider_charged` when the provider reported what it billed, otherwise `price_snapshot`.

**Prices are read live, not from a local file.** `run_benchmark(...)` fetches `openrouter.ai/api/v1/models` once at the start of a run (`sm_bench.model_clients.pricing`), and freezes each model's rate plus the exact fetch timestamp into that run's record. Reading the rate from `configs/benchmarks/models.json` would attribute a run to whatever price was true at the last manual sync, which can be weeks stale. If the API is unreachable the runner logs it and falls back to the registry rates, stamped with their own older sync date; `--offline-prices` forces that path. Every benchmark also archives the live price list it used to `configs/benchmarks/pricing_history/openrouter-<date>.json` (committed), so the history needed to reprice old runs accumulates on its own; `scripts/sync_openrouter.py` writes the same file.

Repricing is live too: `scripts/token_report.py` and the dashboard's Spend tab read current prices from the API by default (`--prices local` or `--as-of <date>` to use the registry or an archived book). Records that predate all this still work — they are priced from their embedded `model_metadata.pricing`, and where even that is missing the cost is reported as unknown, never as zero.

**Truncation is separated from silence.** A reasoning model can spend the entire
output budget thinking and emit no answer tokens at all. Recorded as
`empty_response` that reads on a leaderboard as a model unable to produce a
design, when the run in fact never happened — so the runner checks the usage and
records **`token_limit`** instead when completion or reasoning tokens reached the
effective cap. `qwen3.8-27b` at medium effort hit exactly 8192 of 8192 on both of
its two `hard_v4` runs and produced nothing, while `gpt-5.6-sol` at the same
effort peaked at 6619 and answered every time.

The default `--max-output-tokens` stays at **8192**. It is a known confound that
scales with how much a model thinks, and raising it is a deliberate experimental
choice rather than a default, because it changes what every recorded run means.
Pass `--max-output-tokens` explicitly when benchmarking a model that reasons at
length, and read `token_limit` in the results as "this run did not happen",
never as a model failure.

### Benchmark results layout
Experiment tracks are top-level: active independent tasks live at `results/zero_shot/<prompt-slug>/`, while future iterative tasks will live separately at `results/feedback_driven/<feedback-task-slug>/`. Every task owns its `prompt.txt`, `task.json`, dashboard-rendered `notes.md`, and outputs; feedback-driven tasks must not implicitly reuse zero-shot definitions. The feedback track has no runner yet. The dashboard keeps the task catalogs separate and reads older layouts only for compatibility.

## Architecture

### Tasks name their environment
A benchmark task (`results/<track>/<slug>/task.json`) names its environment with an `"environment"` key; tasks without one are heat-exchanger tasks, which covers every task recorded so far. The runners build the environment with `sm_core.make_env(...)` and never import environment classes. A task's `score_version` selects the score the environment applies.

### Every record carries its provenance
`evaluate()` stamps `environment`, `simulator_version` and `score_version` on every result, and the runners copy them into each record. Results from different simulator or score versions are **never pooled**; historical records are never rewritten to look as though a newer referee produced them.

### Determinism is a hard requirement
Identical input must give identical output, in every environment. When an environment tag is bumped, re-score the recorded runs and confirm that every number that should not move did not move.

### Model clients
`src/sm_bench/model_clients/`, all implementing `BaseModelClient.generate_design(prompt) -> str`:
- `OpenRouterClient` (`openrouter_client.py`) — the primary API client; `HFInferenceClient` (`hf_client.py`, Hugging Face Inference Providers via `router.huggingface.co/v1`) and `OpenCodeClient` are alternatives. They expose latency and token usage after each call.
- `DummyRandomClient` / `HeuristicClient` — ignore the prompt, return a design from the heat-exchanger samplers (offline/pipeline testing; also the injected client in `tests/test_api_benchmark.py`).
- `InteractiveBrowserClient` — prints the prompt and reads a pasted response from stdin (manual cloud-model testing via `run_llm_eval.py`).

### LLM output parsing
`sm_core.parse_llm_json()` uses the `json-repair` library to recover messy/markdown-wrapped/broken JSON (see `ARCHITECTURE_DECISIONS.md` ADR-01; constrained decoding via outlines/vLLM/guidance is a possible future move).

### Packaging & import convention
The harness is a small src-layout package, `src/sm_bench/` (model clients and run logging), installed editable with the rest of the environment (`pip install -e .`); the root `conftest.py` also puts `src/` on `sys.path` for tests. Scripts import `from sm_bench...`, `from sm_core import make_env, parse_llm_json`, and heat-exchanger helpers from `sm_heat_exchanger`. SM-Bench is not published as a package for others to install; consumers install the environment packages directly.
