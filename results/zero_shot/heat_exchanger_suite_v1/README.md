# Heat exchanger suite v1

Thirty heat-exchanger design tasks, ten at each of three difficulty levels
(`easy`, `medium`, `hard`). Each model answers every task once, with no
feedback, and every answer is judged by the `heat_exchanger` environment of
`sm-heat-exchanger` `v0.8.0` with score `heat_exchanger_score_v4`.

Unlike the single-task sets, which send one hand-written prompt many times,
a suite sends a different task each time. The prompt is the environment's own,
`sm_heat_exchanger.prompts.build_heat_exchanger_prompt(task)`, built from the
task as it appears in `tasks.jsonl`.

## Files

- `tasks.jsonl`: the tasks, one per line, exactly as the models see them.
- `suite.json`: the suite definition: the prompt builder, the difficulty label
  of every task, and the mean score of a reference design per difficulty level.
- `api_runs/<model>.jsonl`: one record per task and model.

## What the levels mean

- **easy**: small flow rates and duty, loose pressure-drop limits.
- **medium**: a tight tube-side pressure-drop limit.
- **hard**: a tight tube-side pressure-drop limit with a close temperature
  approach.

Every task has a reference design, found by a referee-driven search, that
passes all requirements. Its mean score per level (easy 0.96, medium 0.89,
hard 0.79) shows what is reachable; the reference designs themselves are not
published.

## Scoring

Score V4 is gated: a design that meets the duty target and both pressure-drop
limits earns 0.3, and the remaining 0.7 rewards cost and design quality on top
of that. A design that meets the requirements but is oversized therefore scores
about 0.3.

## Models

API models run through OpenRouter at temperature 0 (where the model accepts
it) with the lowest reasoning effort each model offers. Open-weight models
(`provider: local`) run greedily on one GPU with `transformers`, pinned to an
exact Hugging Face revision in `configs/benchmarks/models.json`.
`SM_heat_exchanger_v1` is the first Suni Muhendis model, a LoRA adapter on
`Qwen/Qwen2.5-7B-Instruct`; none of these tasks was used to train it.
