# Benchmarking

The benchmark harness is this repository. It sends a prompt to a model, parses
the response, evaluates the design with the environment the task names, and
appends a provenance-rich record.

## Experiment tracks

Tracks are top-level boundaries under `results/`. A task owns its prompt,
configuration, notes, and output files:

```text
results/
  zero_shot/<task-slug>/
    prompt.txt
    task.json
    notes.md
    api_runs/<model>.jsonl
    manual_runs/<model>.jsonl
  feedback_driven/
    # reserved; no runner is published yet
```

The active track is zero-shot: one prompt produces one response, with no
simulator feedback or score-guided retry. See
[the experiment protocol](../results/EXPERIMENT_TRACKS.md) for the exact
separation rules.

## Run a benchmark

Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. Then run:

```bash
# One task and model, twenty independent attempts
python scripts/run_api_benchmark.py \
  --prompt heat_exchanger_hard_v4 \
  --model gpt-5.6-sol \
  --repeats 20

# Inspect effective provider limits without making a model call
python scripts/run_api_benchmark.py \
  --prompt heat_exchanger_hard_v4 \
  --model gpt-5.6-sol \
  --preflight-only
```

Reasoning effort is stored as an inference setting. The runner clamps output
budgets to live provider limits and records the exact task, prompt, parameters,
usage, latency, and model identity.

The OpenRouter registry is a point-in-time capability cache. Refresh it with:

```bash
python scripts/sync_openrouter.py
```

## Token and cost accounting

Every run stores token usage, the price snapshot used at run time, and a cost
basis. Live prices are archived so historical records can be repriced without
silently replacing what was known when the run occurred.

```bash
python scripts/token_report.py --by model
python scripts/token_report.py --as-of 2026-09-01 --csv spend.csv
```

## Dashboard

```bash
streamlit run scripts/dashboard.py
```

The dashboard presents the evaluation funnel, requirement compliance, design
diversity, individual run records, and the all-time spend ledger. It keeps
experiment tracks and task definitions isolated.

## Data licensing

Scores, metrics, project-authored annotations, and task definitions are covered
by [the benchmark-data license](../results/LICENSE.md). Raw model responses are
third-party output and are outside that grant; inspect the originating model and
provider terms before reusing them, especially for training.
