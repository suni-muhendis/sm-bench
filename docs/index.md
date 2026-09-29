---
hide:
  - navigation
---

# SM-Bench

**Physics-based evaluation environments for machine-generated engineering designs.**

SM-Bench turns a proposed design into structured engineering feedback and a
normalized score. Each environment applies schema validation, design-rule
checks, a deterministic physics simulation, and a versioned scoring function,
so a language model, an optimizer, or a training system can all be judged by
the same referee.

SM-Bench is part of [Suni Muhendis](https://github.com/suni-muhendis) and is
published as the `sunimuhendis` Python package.

<div class="grid cards" markdown>

-   **Leaderboard**

    ---

    How current language models do when asked to design a heat exchanger in
    one attempt, task by task.

    [See the results](leaderboard.md)

-   **Use the library**

    ---

    Install an environment, evaluate designs, and audit a task before running
    any model against it.

    [Library guide](library.md)

-   **Run a benchmark**

    ---

    Send a task to models through the API, record every run with its cost, and
    explore the results.

    [Benchmark guide](benchmarking.md)

</div>

## Available environments

| Environment | Status | Install extra |
|---|---|---|
| `heat_exchanger` | Available; simulator V4 and versioned scores | `heat_exchanger` |

The heat-exchanger environment supports shell-and-tube and concentric-tube
geometries. It uses `ht` and `fluids` where suitable, with additional
shell-side, cost, mechanical, and correlation-validity checks implemented in
the environment. Further engineering domains are planned.

## Install

Python 3.12 is required. Install from a release tag so simulator and scoring
behavior cannot move underneath an experiment:

```bash
pip install "sunimuhendis[heat_exchanger] @ git+https://github.com/suni-muhendis/sm-bench.git@envs-v0.7.0"
```

## Quick start

```python
from sunimuhendis import make_env

env = make_env("heat_exchanger", score_version="heat_exchanger_score_v4")

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
print(result.status, result.score.normalized_total)
```

Invalid model output is data, not an exception: `evaluate()` returns
`schema_error`, `drc_error`, or `simulation_error` with a score of `0.0`, and a
successful simulation returns a score in `[0.0, 1.0]` with the engineering
metrics behind it.

## How a design is judged

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
produced it, and results from different versions are never pooled.

## License and citation

Source code is licensed under the
[Apache License 2.0](https://github.com/suni-muhendis/sm-bench/blob/main/LICENSE).
Benchmark data and project-authored reports are covered by
[CC BY 4.0](../results/LICENSE.md); third-party model responses are excluded
from that grant. Use
[CITATION.cff](https://github.com/suni-muhendis/sm-bench/blob/main/CITATION.cff)
when citing the software.
