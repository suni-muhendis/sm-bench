---
hide:
  - navigation
  - toc
---

<p class="sm-eyebrow">The benchmark / Recorded results</p>

# Engineering performance, measured.

<p class="sm-lb-intro">How well do language models design real engineering hardware? Every answer below is a complete heat-exchanger design, judged by the same physics referee.</p>

Each model receives a design task (operating conditions, a duty target,
pressure-drop limits and cost anchors) and answers once, with no feedback and
no second attempt. The answer goes through schema checks, design-rule checks,
a physics simulation and a versioned score. A design that fails any stage
scores 0; one that meets every requirement earns 0.3, and a cheaper,
better-engineered design earns up to 1.

The current benchmark is **heat_exchanger_suite_v1**: 30 different tasks at
three difficulty levels. Next to frontier and open models it includes
[SM_heat_exchanger_v1](https://huggingface.co/SM-AI/SM_heat_exchanger_v1), the
first Suni Muhendis model, and its untuned base model, so the effect of
fine-tuning is visible directly. None of the 30 tasks was used to train it.

Each task set is ranked on its own, because each pins its own simulator and
score version. The earlier single-task sets, which send one prompt many times,
are kept under **Archive**.

<div id="sm-leaderboard" data-src="../data/leaderboard.json?v=20261106-split2" markdown="0">
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
