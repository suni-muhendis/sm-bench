# Changelog

All notable public changes are recorded here. Simulator and score behavior have
their own explicit versions; a package release does not make results from
different simulator or score versions comparable.

## [Unreleased]

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

- The benchmark runners and the rescoring script build environments through
  `make_env` instead of importing heat-exchanger classes.
- Manual zero-shot records now include the environment and the simulator and
  score versions.

## [0.6.0] - 2026-09-21

### Changed

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

[Unreleased]: https://github.com/suni-muhendis/sm-bench/compare/envs-v0.6.0...main
[0.6.0]: https://github.com/suni-muhendis/sm-bench/releases/tag/envs-v0.6.0
[0.5.0]: https://github.com/suni-muhendis/sm-bench/releases/tag/envs-v0.5.0
