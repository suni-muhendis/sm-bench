---
hide:
  - navigation
  - toc
---

<p class="sm-eyebrow">The benchmark / Recorded results</p>

# Engineering performance, measured.

<p class="sm-lb-intro">Explore how language models turn a single prompt into a complete engineering design. Compare performance within a task, then inspect the constraints and evaluation stages behind the score.</p>

Each model receives a task's prompt once per run and has to answer with a
complete heat-exchanger design in a single attempt, with no feedback. Every
answer goes through the same schema, design-rule, simulation, and scoring
stages as any other design.

Tasks are ranked separately. Each task pins its own simulator and score
version, so a score from one task cannot be compared with a score from another.

<div id="sm-leaderboard" data-src="../data/leaderboard.json" markdown="0">
  <p class="sm-lb-status" role="status">Loading results…</p>
</div>

<noscript>Enable JavaScript to explore the interactive table. The recorded runs are also available in the <a href="https://github.com/suni-muhendis/sm-bench/tree/main/results">results repository</a>.</noscript>

## Reading the table

| Column | Meaning |
|---|---|
| Mean score | Average score over every attempt except those that never ran (client errors and token-limit stops). Failed designs count as `0.0`. |
| Valid design | Share of attempts that passed schema, design-rule checks, and simulation. |
| Requirements met | Share of attempts whose design reaches the duty target and stays inside both pressure-drop limits. |
| Best | Highest score any single attempt reached. |
| Cost | Total spend for the recorded runs, as charged or priced at run time. |

The numbers are computed from the run records under
[`results/`](../results/EXPERIMENT_TRACKS.md) each time the site is built.
Benchmark data is licensed under [CC BY 4.0](../results/LICENSE.md). For
individual runs, raw responses, and cost breakdowns, use the
[Streamlit dashboard](benchmarking.md) in the repository.
