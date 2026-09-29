# Environments

SM-Bench evaluates designs with environments that are packages of their own,
built on a shared evaluation contract:

| Package | Provides |
|---|---|
| [sm-core](https://github.com/suni-muhendis/sm-core) | The evaluation contract, `make_env`, task auditing, `parse_llm_json` |
| [sm-heat-exchanger](https://github.com/suni-muhendis/sm-heat-exchanger) | The `heat_exchanger` environment |

An environment registers itself with `sm-core` when it is installed, and is
then built by name:

```bash
pip install "sm-heat-exchanger @ git+https://github.com/suni-muhendis/sm-heat-exchanger.git@v0.8.0"
```

```python
from sm_core import list_environments, make_env

list_environments()                     # ['heat_exchanger']
env = make_env("heat_exchanger", score_version="heat_exchanger_score_v4")
```

Factories import simulator dependencies lazily, so discovering environments
costs nothing. Always install from a tag: simulator and score behaviour is
versioned deliberately.

## Evaluation result

`evaluate(task_id, task_params, design_id, design_params)` applies four stages
in order:

1. schema validation;
2. design-rule checks;
3. simulation;
4. benchmark scoring.

Invalid designs return an `EvaluationResult` with a zero score and a stage
status; they do not raise into the caller's optimisation or training loop.

Results expose:

- `status` and `error_message`;
- `score.normalized_total` and per-objective components;
- engineering `metrics`;
- `raw_simulation_output`, including warnings and fidelity notes;
- `environment`, `simulator_version` and `score_version`.

Configuration errors made by the experiment author, such as an unknown
operating-condition key, raise instead of being attributed to the design.

## Heat-exchanger tasks

Operating conditions belong to the task, not the design. A task may provide an
`operating_conditions` block and optional `secondary_operating_points`.
Secondary points evaluate the same geometry at additional conditions and retain
their metrics under `raw_simulation_output["secondary_points"]`.

The design schema contains the geometric decisions available to the model.
Task-owned flow rates, temperatures, fouling assumptions, material limits, and
targets cannot be overridden by a submitted design. SM-Bench tasks name their
environment with an `"environment"` key; tasks without one are heat-exchanger
tasks.

## Auditing a task

A badly calibrated task can have an unreachable target, an unavoidable warning,
or a score budget dominated by merely reaching feasibility. Audit a task before
spending model calls:

```python
report = env.audit_task(task, num_samples=20_000)

print(report.summary())
print(report.is_healthy())
print(report.score_ceiling)
print(report.forced_warnings)
```

Sampling can demonstrate that a score is reachable; it cannot prove that a
higher score is impossible. Tasks can therefore include `reference_designs` as
explicit feasibility witnesses.

The audit algorithm is environment independent. Each environment supplies broad
sampling, hard requirements, declared checks, and any closed-form physical
limits it can derive.

## Versioning

Simulator and score versions are independent. Every result stores both, and
results are never pooled across either boundary. Score V4 is the recommended
heat-exchanger score for new tasks; older scores remain available only to
reproduce historical experiments.

The physics audit that motivated task auditing is kept with the environment:
[simulator V3 report](https://github.com/suni-muhendis/sm-heat-exchanger/blob/main/docs/simulator_v3_physics_audit.md).
