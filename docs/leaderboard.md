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
a physics simulation and a versioned score (`heat_exchanger_score_v5`). A
design that fails a check scores 0; one that misses a requirement earns at most
0.15; one that meets every requirement earns 0.3, and up to 1 the closer its
cost comes to that of a well-engineered reference design.

The current benchmark is **heat_exchanger_suite_v2**: 30 different tasks at
three difficulty levels. Next to frontier and open models it includes
[SM_heat_exchanger_v1](https://huggingface.co/SM-AI/SM_heat_exchanger_v1), the
first Suni Muhendis model, and its untuned base model, so the effect of
fine-tuning is visible directly. None of the 30 tasks was used to train it.

Each task set is ranked on its own, because each pins its own simulator and
score version. The earlier single-task sets, which send one prompt many times,
are kept under **Archive**.

<div id="sm-leaderboard" data-src="../data/leaderboard.json?v=20261106-v5b" markdown="0">
  <p class="sm-lb-status" role="status">Loading results…</p>
</div>

<noscript>Enable JavaScript to explore the interactive table. The recorded runs are also available in the <a href="https://github.com/suni-muhendis/sm-bench/tree/main/results">results repository</a>.</noscript>

## Reading the table

| Column | Meaning |
|---|---|
| Easy / Medium / Hard | Mean score over the ten tasks of each level. A design that fails a check scores 0; one that misses a requirement earns at most 0.15. |
| Score when met | Mean score of the answers whose design met every requirement: 0.3 for a design that only meets them, up to 1 the closer its cost comes to a well-engineered reference design. |
| Valid | Share of answers that passed schema checks, design-rule checks and simulation. |
| Cost | Total spend for the recorded answers, as charged or priced at run time. |
| Latency | Median time to answer. |
| Req. met | Share of answers whose design reaches the duty target within both pressure-drop limits. |

Rows are listed by the mean of the three level scores. Select a column to
sort by it. Archived single-task sets keep their original table, with a mean
and best score over repeated attempts at one task.

The numbers are computed from the run records under
[`results/`](../results/EXPERIMENT_TRACKS.md) each time the site is built.
Benchmark data is licensed under [CC BY 4.0](../results/LICENSE.md). For
individual runs, raw responses, and cost breakdowns, use the
[Streamlit dashboard](benchmarking.md) in the repository.

## Exploring the charts

Hover over a mark, or focus it with the keyboard, to see its values. Each chart
can be linked directly with `?view=` (for example `?view=tasks`).

- **Compare:** every model as a bar, for the level or measure you choose; the
  bars re-order as you switch. The reference design's score is marked.
- **Heatmap:** level scores, score when met and requirements met for every
  model, with the reference design underneath.
- **Task by task:** one cell per task and model. A cell at 0.3 or above met
  every requirement.
- **Cost & speed:** mean of the level scores against cost per task or median
  latency, both on a log scale. Models without a recorded price are left out.
- **Requirements vs score:** how often a model's design meets every
  requirement against what its working designs score, with the reference
  design for scale.

Charts show recorded answers, one per task and model, not confidence
intervals. Close scores, within a few hundredths, should be read as ties.
