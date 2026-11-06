# Heat exchanger suite v2

The 30 heat-exchanger design tasks of
[`heat_exchanger_suite_v1`](../heat_exchanger_suite_v1/README.md), ten at each
of three difficulty levels (`easy`, `medium`, `hard`), judged with
`heat_exchanger_score_v5` from `sm-heat-exchanger` `v0.9.0`.

The answers are the ones recorded for v1: every recorded design was evaluated
again against its task with `scripts/rescore_suite.py`. The simulator (`v4`)
is unchanged, so the engineering metrics are the same; only the score
differs. Each record keeps the model's response and the prompt it was shown
(which names `heat_exchanger_score_v4`) and carries `rescored_from` with the
source suite and timestamp. New runs on this suite see the same prompt with
the new score version named.

## Score V5

- **Gate.** A design that reaches the duty target within both pressure-drop
  limits earns 0.3. A design that misses earns at most 0.15, scaled by how
  close it came, so any design that meets every requirement outranks any
  design that does not.
- **Cost.** Past the gate, up to 0.7 more is earned on a logarithmic cost
  scale: full credit at the task's `cost_good`, none at 80 times that (about
  64 times a reference design). Under V4 every design beyond `cost_bad` scored
  the same, so designs at 5x and 37x the reference cost were indistinguishable.
- **Warnings.** Each mechanical design warning removes a tenth of the cost
  term, as in V4.

Every task has a reference design that meets all requirements; its mean score
per level under V5 is easy 0.96, medium 0.90, hard 0.80. The reference designs
themselves are not published.

## Files

- `tasks.jsonl`: the tasks, exactly as in v1 apart from `score_version`.
- `suite.json`: prompt builder, difficulty labels, reference means, and the
  runs hidden from the site (`hidden_models`).
- `api_runs/<model>.jsonl`: one record per task and model.
