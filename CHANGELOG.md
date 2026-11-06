# Changelog

All notable public changes are recorded here. Simulator and score behavior have
their own explicit versions; a package release does not make results from
different simulator or score versions comparable.

## [Unreleased]

### Added

- `heat_exchanger_suite_v2`: the 30 tasks and recorded answers of
  `heat_exchanger_suite_v1`, judged with `heat_exchanger_score_v5`
  (`sm-heat-exchanger` `v0.9.0`). It is the suite the site shows first;
  `heat_exchanger_suite_v1` moves to the archive with its records unchanged.
- `scripts/rescore_suite.py`: builds a new suite from an existing one under
  another score version by evaluating every recorded design again. No model is
  called; the source suite is never modified; each record keeps its response
  and prompt and carries `rescored_from`. It stops if the simulator's metrics
  differ beyond floating-point round-off.
- A suite can be archived (`"archived": true` in `suite.json`).
- Task suites: a `results/<track>/<slug>/` folder with `suite.json` and
  `tasks.jsonl` runs every task once per repeat, each with the prompt the
  environment builds from it. Records carry `suite_id` and `task_group`.
- `heat_exchanger_suite_v1` (archived): 30 heat-exchanger tasks at three difficulty
  levels, scored with `heat_exchanger_score_v4`, with zero-shot results for
  15 model configurations (13 shown on the site).
- Provider `local` (`TransformersClient`): open-weight models and PEFT adapters
  run greedily on a GPU, pinned to a Hugging Face revision. Install with
  `pip install -e .[local]`.
- `SM_heat_exchanger_v1`, the first Suni Muhendis model, in the model registry.

### Changed

- `sm-heat-exchanger` is pinned to `v0.9.0`, which adds score V5; scores V1-V4
  are unchanged and every earlier record re-scores identically.
- The leaderboard lists suites first, with a mean score per difficulty level,
  and the single-task sets under **Archive**. A model that has not answered
  every task of a suite is shown but not ranked.
- A suite page is a dashboard: headline figures, the featured model against
  its base model, and interactive charts (ranking by level, heatmap, task by
  task, cost and speed; `?view=` links a chart). A suite can hide a run from
  the site with `hidden_models`; the record stays in the repository.
- A suite has no overall ranking and no mean score. It reports two separate
  measures, the share of answers that meet every requirement and the mean score
  of those answers ("score when met"), next to the mean score per difficulty
  level, and lists models by the first, then the second. A new chart plots
  one against the other, with the reference design for scale.

## [0.8.0] - 2026-09-29

SM-Bench is now the benchmark application only. The evaluation contract and
the heat-exchanger environment moved, with their history, into packages of
their own, which this repository installs by tag. Every recorded design
re-scores identically.

### Changed

- `sm-heat-exchanger` is pinned to `v0.9.0`, which adds score V5; scores V1-V4
  are unchanged and every earlier record re-scores identically.

- The evaluation contract is [sm-core](https://github.com/suni-muhendis/sm-core)
  (`sm_core`) and the heat exchanger is
  [sm-heat-exchanger](https://github.com/suni-muhendis/sm-heat-exchanger)
  (`sm_heat_exchanger`), both at `v0.8.0`. Install those to evaluate designs
  outside the benchmark.
- The harness package is `sm_bench` (model clients and run logging); scripts
  use `sm_core.make_env` and `sm_core.parse_llm_json`.
- Physics, score and contract tests moved with the code; the tests here cover
  the runners, dashboard, pricing and token ledger.

### Removed

- The `sunimuhendis` package, its wheel and the wheel checks. Tags up to
  `envs-v0.7.0` still install it.

## [0.7.0] - 2026-09-29

Groundwork for moving each environment into a package of its own. No
simulator or score behavior changed: every recorded benchmark design re-scores
identically.

### Added

- Environments are discovered through the `sunimuhendis.environments`
  entry-point group; this package registers `heat_exchanger` there. Two
  packages registering the same name is an error.
- `EvaluationResult` now carries `environment`, `simulator_version` and
  `score_version`, stamped by `evaluate()` on every result.
- `BaseSimulator.VERSION`, `BaseScoreFunction.VERSION` and
  `BaseEnvironment.name`; every heat-exchanger score function declares its
  version.
- Benchmark records carry an `environment` field. A task may name its
  environment with an `"environment"` key; tasks without one are
  heat-exchanger tasks.

### Changed

- `sm-heat-exchanger` is pinned to `v0.9.0`, which adds score V5; scores V1-V4
  are unchanged and every earlier record re-scores identically.

- The benchmark runners and the rescoring script build environments through
  `make_env` instead of importing heat-exchanger classes.
- Manual zero-shot records now include the environment and the simulator and
  score versions.

## [0.6.0] - 2026-09-21

### Changed

- `sm-heat-exchanger` is pinned to `v0.9.0`, which adds score V5; scores V1-V4
  are unchanged and every earlier record re-scores identically.

- Raised the supported runtime to CPython `>=3.12,<3.13`.
- Added Windows and Ubuntu CI with full tests, package builds, metadata checks,
  and clean-wheel consumer validation.
- Added a constrained Python 3.12 development profile.
- Clarified the public package boundary and external-consumer workflow.
- Reorganized public documentation and added citation, security, and
  third-party provenance guidance.

## [0.5.0] - 2026-09-20

- Added the audited heat-exchanger simulator V4 and Score V4 task family.
- Added multi-point evaluation, reference-design feasibility witnesses, and
  task-owned operating conditions.
- Added live price snapshots and token/cost accounting for benchmark runs.

[Unreleased]: https://github.com/suni-muhendis/sm-bench/compare/v0.8.0...main
[0.8.0]: https://github.com/suni-muhendis/sm-bench/releases/tag/v0.8.0
[0.7.0]: https://github.com/suni-muhendis/sm-bench/releases/tag/envs-v0.7.0
[0.6.0]: https://github.com/suni-muhendis/sm-bench/releases/tag/envs-v0.6.0
[0.5.0]: https://github.com/suni-muhendis/sm-bench/releases/tag/envs-v0.5.0
