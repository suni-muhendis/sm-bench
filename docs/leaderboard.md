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

## Exploring the charts

Select a task, then choose a chart and the model configurations to compare.
Model selection applies to the charts; the search field below filters the
detailed table independently. Switching tasks resets the chart selection.
Hover over a mark or focus it with the keyboard to inspect its values. Use
**View chart data** for an accessible numeric table or **Download SVG** to
save the selected chart.

- **Score comparison:** mean and best score on a fixed 0–1 scale.
- **Validity & requirements:** simulated designs and designs meeting all
  requirements, both as percentages of all recorded attempts.
- **Score distribution:** inclusive quartiles and median, with whiskers at
  the minimum and maximum. Failed designs count as zero; client errors and
  token-limit stops are excluded. These are summaries, not individual runs.
- **Cost & speed:** mean score against average recorded cost per run or
  median latency. Cost comparisons omit models with any unpriced runs;
  latency uses positive recorded measurements only.
- **Run outcomes:** each model's recorded attempts, broken down by status.
  A completed simulation does not necessarily meet the task requirements.

Charts show recorded samples, not confidence intervals or claims of statistical
significance. Compare run counts alongside scores. All views stay within the
selected task and use the same versioned results as the table.
