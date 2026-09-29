# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository.

## What this is

SM-Bench (Python package `sunimuhendis`) is a framework researching whether an LLM can learn to produce **valid, performant engineering designs** using physics-simulation feedback . The first concrete environment is a **heat exchanger**: it takes a design (JSON), runs real engineering calculations, and returns a normalized benchmark score in `[0.0, 1.0]`. The current weight of the codebase is the *evaluation engine* ("referee").

## Environment & commands

- **Setup:** dependencies live in a project venv. Activate it once per shell — `source .venv/bin/activate` — then use plain `python` / `pytest` / `streamlit`. Recreate with `python3.12 -m venv .venv`, `python -m pip install -c constraints/python312.txt -r requirements.txt`, and `python -m pip install -e .`. The editable install makes the `sunimuhendis` package importable.
- **Interpreter:** CPython **3.12**; the reproducible development version is in `.python-version`. The package currently declares `>=3.12,<3.13`; expand that range only after the full test and clean-wheel consumer checks pass on the new minor version.
- **Tests:** `pytest tests/ -v` — run a single file/test with `pytest tests/test_heat_exchanger_score.py -v` or `-k <substring>`.
- **Secrets:** `HF_TOKEN` is read from `.env` (gitignored; see `.env.example`) via `python-dotenv`.

### Run targets (all from repo root, venv activated)
- `python scripts/run_heat_exchanger.py` — simulate the sample design end-to-end (demo).
- `python scripts/run_simulation.py` — core pipeline demo that exercises every failure path (schema/DRC/sim/crash) with dummy components.
- `python scripts/run_baseline.py` — generate ~10k designs via samplers, simulate all, and write the training dataset `datasets/sft/heat_exchanger_initial.jsonl` (designs with score > threshold).
- `python scripts/run_api_benchmark.py --prompt <slug> [--model NAME | --models a,b] [--repeats N]` — **automated zero-shot** benchmark: send `results/zero_shot/<slug>/prompt.txt` (scored by the adjacent `task.json`) to configured models, run each response through schema→DRC→sim→score, and append results under that task's `api_runs/`. Core loop `run_benchmark(...)` takes an injectable `client_factory` (offline-testable with `DummyRandomClient`).
- `python scripts/run_llm_eval.py --client [dummy|interactive] --prompt <slug>` — **manual zero-shot** single-model chain; on success prompts for a model name and appends to `results/zero_shot/<slug>/manual_runs/`.
- `python scripts/token_report.py [--by model|month|task] [--as-of YYYY-MM-DD] [--csv out.csv]` — all-time token and spend ledger over every recorded run. Each run is priced twice: at the rate frozen into the record when it ran, and at a current or dated price list, so historical spend and today-equivalent spend are both reportable.
- `streamlit run scripts/dashboard.py` — track-first dashboard with isolated task catalogs. It reads the evaluation pipeline as a funnel (responded → parsed → schema → DRC → simulated), scores requirement compliance against the task config (duty target, both ΔP limits), reports design diversity, and keeps run-level exploration and exports. Its Spend tab reports the all-time token ledger across every task and track, independent of the on-screen filters. The feedback-driven track is currently a prepared placeholder only.

### Token and cost accounting
Every benchmark record carries a `usage` block (prompt / completion / reasoning / cached / total tokens), a `pricing_snapshot` and a `cost_usd` with `cost_basis` — `provider_charged` when the provider reported what it billed, otherwise `price_snapshot`.

**Prices are read live, not from a local file.** `run_benchmark(...)` fetches `openrouter.ai/api/v1/models` once at the start of a run (`sunimuhendis.model_clients.pricing`), and freezes each model's rate plus the exact fetch timestamp into that run's record. Reading the rate from `configs/benchmarks/models.json` would attribute a run to whatever price was true at the last manual sync, which can be weeks stale. If the API is unreachable the runner logs it and falls back to the registry rates, stamped with their own older sync date; `--offline-prices` forces that path. Every benchmark also archives the live price list it used to `configs/benchmarks/pricing_history/openrouter-<date>.json` (committed), so the history needed to reprice old runs accumulates on its own; `scripts/sync_openrouter.py` writes the same file.

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

## Architecture (the parts that need multiple files to understand)

### The 4-stage evaluation pipeline (the core contract)
Everything funnels through `BaseEnvironment.evaluate()` in `src/core/base_environment.py`:

```
design (raw dict) → [1] schema validation → [2] DRC → [3] simulate → [4] benchmark score
```

- Stages run **cheapest-first, fail-fast**: any failure short-circuits with `score = 0.0` and a `status` of `schema_error` / `drc_error` / `simulation_error`, plus an `error_message`. This per-stage status is the evaluation feedback for the benchmark.
- The **raw design dict flows through all stages** (not the validated Pydantic model). So `validate_schema`, `run_drc`, and `simulator.simulate` each receive the original dict. Note this does **not** let a design smuggle extra fields through: `schema.py` sets `extra="forbid"`, so anything outside the schema's fields (seven required, seven optional) is rejected at stage 1.
- `EvaluationResult` and `ScoreResult` (Pydantic, `src/core/types.py`) are the shared "language" returned everywhere.
- **Every result carries its provenance.** `evaluate()` stamps `environment` (the env class's `name`), `simulator_version` (the simulator's `VERSION`) and `score_version` (the `VERSION` of the score function the task selected) onto every `EvaluationResult`, whatever stage it stopped at. The benchmark runner copies them into each record, so no script has to know which environment it ran.

### Layered, ABC-based, environment-agnostic core
`src/core/` defines contracts; each environment fills them. To add an environment, implement the same five pieces a heat exchanger has under `src/environments/heat_exchanger/`: `schema.py` (Pydantic), `drc.py`, `simulator.py`, `score.py`, `env.py` (wires simulator + benchmark score via dependency injection into `BaseEnvironment`). Give the env class a `name`, the simulator and every score function a `VERSION`, expose a `make_env(**kwargs)` factory that imports the physics lazily, and register that factory under the `sunimuhendis.environments` entry-point group in the providing package's `pyproject.toml`. Nothing in `src/core/` is heat-exchanger-specific, and nothing outside the environment imports it by name: this is what lets an environment live in its own package. Benchmark tasks name their environment with an `"environment"` key; tasks without one are heat-exchanger tasks. `SimpleCache` (`src/core/cache.py`) exists but is **not** wired into `evaluate()` yet.

### Task feasibility audit (`BaseEnvironment.audit_task`)
A **second environment-agnostic contract**, alongside `evaluate()`. Where `evaluate()` scores one design, `audit_task(task_params)` audits the *task itself* — before any model is run against it — and returns an `AuditReport` (`core/types.py`).

It exists because a task can be calibrated into a wall: a target no design can reach, a penalty no design can avoid, or a reward budget that pays more for producing *any* valid design than for producing a good one. See `reports/simulator_v3_physics_audit.md` for the audit that motivated it — `heat_exchanger_hard_v2` has all three problems, and its observed score ceiling (0.783) is an artefact of them rather than a measurement of any model.

It is a **template method**: the algorithm lives in `BaseEnvironment` and is shared; each environment supplies the environment-specific parts as hooks, so `make_env("heat_exchanger").audit_task(...)` audits heat-exchanger physics and a future environment audits its own.

| Hook | Required | What it supplies |
|---|---|---|
| `sample_designs(n, seed)` | yes | Deterministic, deliberately *broad* coverage of the design space. A sampler biased towards good designs hides the walls the audit exists to find. |
| `get_requirements(task_params)` | yes | The task's hard requirements as `Requirement(name, metric_key, operator, limit)` — distinct from score weights, which only assign partial credit. |
| `list_design_checks()` | no | Catalogue of every check the environment can raise, so the audit can report *dead* checks (rules that, as configured, can never fire). |
| `analyse_physics(task_params)` | no | Closed-form limits sampling cannot prove. Keys prefixed `CRITICAL`/`WARNING` are promoted into `AuditReport.findings`. The heat exchanger reports its ε-NTU ceiling, the duty past which the LMTD-F warning becomes unavoidable, and the nozzle share of each ΔP budget. |

The hooks are **not** `@abstractmethod` — existing and dummy environments keep working, and `audit_task` fails with a message naming the missing hook.

**Use it when choosing task parameters.** `AuditReport.is_healthy()` is false when any CRITICAL finding survives; `summary()` prints the whole thing. `tests/test_task_audit.py` pins both directions: the walled task is flagged, a task with genuine headroom is not.

### Operating conditions belong to the task (`prepare_simulation_inputs`)

A third environment-agnostic hook, alongside `evaluate()` and `audit_task()`.
`BaseEnvironment.prepare_simulation_inputs(design_params, task_params)` builds
the dict handed to `simulator.simulate()`. Its default returns the design
unchanged, so every other environment is untouched.

**Why it exists.** Stages 1 and 2 must see the design exactly as the model
wrote it, so the operating point cannot travel in the design dict. But a
heat-exchanger task is not just a set of targets — it is a duty specification:
which streams, how much of them, how hot, how dirty, how strong the vessel.
None of that is a design decision, so none of it belongs in the schema; all of
it changes the physics, so a task that cannot set it can only ever pose one
problem. Before this hook the operating point was hardcoded at 2.5 kg/s of
water each side at 80/20 °C, and every task ever written was that same problem
with different targets.

`HeatExchangerEnv` overrides it and reads `task_params["operating_conditions"]`,
a whitelist of nine keys — `m_dot_hot/cold`, `T_hot_in/cold_in`, `k_wall`,
`R_fi`, `R_fo`, `P_design`, `allowable_stress`. Three properties are pinned by
`tests/test_operating_conditions.py`:

- **A task without the block behaves exactly as before**, so every existing
  task and every recorded run stays valid.
- **The task wins over the design.** The schema forbids extra fields so a
  benchmarked design cannot carry these keys, but a design handed straight to
  the environment could — and a design that could restate its own flow rate
  would be answering an easier question than the one it was set.
- **A malformed block raises rather than scoring zero.** `prepare_simulation_inputs`
  is called *outside* `evaluate()`'s crash handler on purpose: everything
  inside it is the design's failure, while a typo like `m_dot_hto` is the
  experimenter's, and silently reverting to 2.5 kg/s would record it as every
  model failing to design.

`analyse_physics` reads the same resolved point, so the ε ceiling, the duty at
which the F warning becomes unavoidable, and the nozzle share of the pressure
budget are all computed for the task actually being audited — and are echoed
back in `AuditReport.physics["operating_conditions"]`.

**Two things this makes possible.** A *family* of tasks rather than one, which
is what separates measuring design skill from measuring memorisation of a
single instance. And simulating one design at more than one operating point,
which is how a turndown requirement would be expressed.

### Multi-point evaluation and witnessed feasibility

Two further hooks, both environment-agnostic and both defaulting to the previous
behaviour, so every existing task and every recorded run is unaffected.

**`secondary_simulations(design_params, task_params)`** returns
`(label, simulator_inputs)` pairs — further conditions the *same* design must
survive. `evaluate()` runs each after a successful primary simulation, adds the
warnings found to `num_warnings`, records each point's count as
`<label>_num_warnings`, prefixes the merged warning list with `[<label>]`, and
stores the full per-point metrics in `raw_data["secondary_points"]`. The
requirements stay a single-point gate; only quality spans the range.

`HeatExchangerEnv` reads `task_params["secondary_operating_points"]`, a list of
`{"name": ..., "operating_conditions": {...}}`. Each point's conditions are
applied over the task's primary point, so a turndown case names only the flows
it changes. Like `prepare_simulation_inputs`, this is called *outside*
`evaluate()`'s crash handler: a malformed point is the experimenter's error and
raises.

**`reference_designs(task_params)`** returns designs the task offers as
*witnesses* to its own feasibility; the default reads
`task_params["reference_designs"]`. The audit evaluates them alongside the
sample and raises a CRITICAL finding for any that fails to meet the task's own
requirements. This exists because sampling can show a score is reachable and can
never show that it is not, so a ceiling measured by sampling is a lower bound —
`heat_exchanger_hard_v4`'s was reported as 0.593 against a true 1.000 until a
witness was added. A task claiming a perfect score is attainable should exhibit
a design that attains it.

**`sample_designs` now takes `task_params`** (optional, positional-compatible)
and draws three designs in ten in *velocity coordinates* — picking a target tube
and nozzle velocity and deriving the tube count and bore from the task's flows,
instead of choosing counts and bores independently of it. Sampling in the wrong
coordinates does not bias the audit, it blinds it: every limit that is a
velocity window was invisible to the old sampler, which is why it reported no
warning-free design for `hard_v4` where a structured grid finds 566. This is an
audit-only path — evaluation is untouched, and all 110 recorded `hard_v3` runs
re-score bit for bit.

### Heat exchanger specifics
- **Schema has seven required fields** (`geometry_type`, `length`, `inner_tube_di/do`, `outer_shell_di`, `number_of_tubes`, `baffle_spacing`) plus the seven optional levers described below. The simulator reads further params via `dict.get(...)` defaults — fouling resistances and fluid operating conditions (`m_dot_hot/cold`, `T_hot_in/cold_in`, …) — but since the schema forbids extra fields, **those are not reachable from a benchmarked design**; they are set by the task (`operating_conditions`) or apply only when calling the simulator directly. Fluid thermophysical properties are otherwise **hardcoded** (water), which keeps evaluation deterministic.
- **Simulator (`simulator.py`) library boundary:** tube/annulus side uses `ht` (Nusselt, ε-NTU) and `fluids` (friction factor); **shell side is hand-coded Kern/Bell-Delaware** because no library covers cross-flow over tube bundles. It also computes a cost model and mechanical/TEMA limit checks that produce `num_warnings`. Any metric coming out `NaN`/`Inf` is treated as a simulation failure.
- **Simulator is at `VERSION = "v4"`.** V4 corrected three defects the physics audit found, and **its numbers differ from V3 — results from the two must never be pooled** (~15% of designs get a different warning count). The corrections: unsupported span now follows the TEMA table keyed by tube OD instead of one flat 1.5 m; the ASME wall-thickness check uses UG-27's `t = P·R/(S·E − 0.6·P)` (the previous form *added* where the code subtracts, understating thickness by ~11% at 200 bar) and honours a joint efficiency; and `drc.py` now reads the design's own `tube_passes` / `pitch_ratio` / `pitch_type` rather than assuming the defaults, so DRC and the simulator can no longer disagree about the same design.
- **Correlation limits are reported, never charged to the design.** Kern's shell-side correlations are only valid for 2e3 < Re < 1e6, and its crossflow area assumes a bundle spanning the shell. When a design falls outside either, the simulator sets `shell_correlation_in_range` / `bundle_fill_fraction` and appends to `raw_data["fidelity_notes"]` — deliberately **not** to `warnings`, because the score penalises warnings and charging a design for the referee's blind spots would be scoring our own ignorance.
- **Score V4 is a gated optimisation score, and is what new tasks should use.** V1-V3 spread most of their weight across the requirements themselves, so a design earned ~85% of the raw score the instant it met the duty target and both pressure limits; measured across sixteen parameter settings the reward for reaching any feasible design never moved off 0.439, whatever the targets were. V4 makes the three requirements a **gate** worth `gate_share` (0.30) — missing one scales that share by how close you came, so the boundary is continuous — and puts the remaining 0.70 on annualised cost and warning-freedom, which can always be improved. **V4 deliberately does not score effectiveness:** with flows and inlet temperatures fixed, `Q_max` is constant, so effectiveness is exactly `heat_duty / 627300` (correlation with duty measured at 1.0000000000 over 4,353 designs). Every earlier version rewards both, which pays twice for one quantity.
- **The schema has seven required fields and seven optional ones.** Optional on purpose: `tube_passes`, `pitch_ratio`, `pitch_type`, `baffle_cut`, `D_nozzle_hot/cold`, `material`, each defaulting to the previous behaviour so older designs re-score identically. Making them required would raise the cost of producing *any* valid design, which is the opposite of what the benchmark measures. An absent key and an explicit `null` both mean "not chosen" (`HeatExchangerSimulator._opt`).
- **Nozzle bore is a real lever, and the exploit is closed.** Before, nozzle loss was a fixed tax eating 66.7% of hard_v2's pressure budget; exposing the bore naively would have been a free win, since a 2 m nozzle on a 0.48 m shell was accepted, cut ΔP by 87%, and cost nothing. Now the bore is bounded by DRC (35% of shell diameter for shell-and-tube, the pipe itself for concentric), it adds mass and cost, and a bore below `MIN_NOZZLE_VELOCITY` raises an oversized-nozzle warning. The designable window is roughly 26-57 mm at these flows.
- **Benchmark Score (`score.py`) is multi-objective** with weights pulled from the task config: `w_heat`, `w_cost`, `w_eff`, `w_drop_tube`, `w_drop_shell` (defaults 0.4/0.3/0.2/0.05/0.05). Score is the weighted sum of component sub-scores, normalized by total weight, then multiplied by a **warnings penalty (−10% per warning)**. It reads metrics with **V1↔V2 name fallbacks** (e.g. `heat_duty_W` else `heat_duty`), so both simulator generations work.
- **Two different pressure-drop thresholds exist on purpose:** the simulator's `MAX_DP_TUBE/SHELL` (10 kPa) only drive *warnings*; the score's `max_dp_tube/shell` from the task config (50 kPa in `task_001.json`) drive the *score*. Don't conflate them.

### Determinism is a hard requirement
Tests assert identical output for identical input (`test_heat_exchanger_smoke.py`) because the evaluation score must be stable and reproducible. Preserve determinism when touching the simulator (hence hardcoded fluid props, no randomness in the eval path).

### Model clients
`src/model_clients/`, all implementing `BaseModelClient.generate_design(prompt) -> str`:
- `HFInferenceClient` (`hf_client.py`) — **real** API client; calls Hugging Face Inference Providers (OpenAI-compatible router at `router.huggingface.co/v1`) using `HF_TOKEN`. Used by `run_api_benchmark.py`; exposes `last_latency_ms` / `last_prompt_tokens` / `last_completion_tokens` after each call.
- `DummyRandomClient` / `HeuristicClient` — ignore the prompt, return a sampled design (offline/pipeline testing; also the injected client in `test_hf_benchmark.py`).
- `InteractiveBrowserClient` — prints the prompt and reads a pasted response from stdin (manual cloud-model testing via `run_llm_eval.py`).

### LLM output parsing
`src/parsing/json_parser.py` → `parse_llm_json()` uses the `json-repair` library to recover messy/markdown-wrapped/broken JSON (see `ARCHITECTURE_DECISIONS.md` ADR-01; constrained decoding via outlines/vLLM/guidance is a possible future move).

### Packaging & import convention
The library is an installable **src-layout package**: everything importable lives under `src/sunimuhendis/` and is exposed via `pyproject.toml`. Install it editable once (`pip install -e .`) so `import sunimuhendis` works everywhere; the root `conftest.py` also puts `src/` on `sys.path` for tests. Scripts import `from sunimuhendis...` (the old repo-root `sys.path` + `from src...` convention is gone). Inside the package, relative imports are used (e.g. `from ...core.base_score import BaseScoreFunction`), and every subpackage has an `__init__.py`.

**Consuming just the environments (e.g. from a separate training repo):** `pip install "sunimuhendis[heat_exchanger] @ git+<repo-url>@<tag>"`, then `from sunimuhendis import make_env, list_environments`. Instantiate by name — `make_env("heat_exchanger")` — via the registry in `environments/registry.py`, which discovers environments through the `sunimuhendis.environments` entry-point group (each factory imports its heavy sim deps **lazily**, so the per-env install extras are meaningful). Two installed packages claiming one name is an error, never a silent choice. The heat exchanger is also a registry built-in so it works from an uninstalled source tree; after changing entry points in `pyproject.toml`, re-run `pip install -e .` so the metadata is current. The repository-only benchmark harness (`model_clients/`, `baselines/`, dashboard and scripts) is **excluded from the wheel**. The wheel contains `core` + `environments` + `parsing` + `prompts`; prompts ship so external consumers can construct the same benchmark input.
