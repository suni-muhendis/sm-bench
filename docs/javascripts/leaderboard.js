// Renders docs/data/leaderboard.json (written by scripts/build_site_data.py)
// into the #sm-leaderboard element on the leaderboard page.
(function () {
  "use strict";

  const COLUMNS = [
    { key: "mean_score", label: "Mean score", kind: "score" },
    { key: "valid_pct", label: "Valid design", kind: "pct" },
    { key: "requirements_pct", label: "Requirements met", kind: "pct" },
    { key: "best_score", label: "Best", kind: "num" },
    { key: "runs", label: "Runs", kind: "int" },
    { key: "cost_usd", label: "Cost", kind: "usd" },
    { key: "p50_latency_s", label: "Median latency", kind: "sec" },
  ];

  const esc = (value) =>
    String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fmt(value, kind) {
    if (value === null || value === undefined) return '<span class="sm-lb-na">–</span>';
    switch (kind) {
      case "pct": return `${value.toFixed(0)}%`;
      case "int": return String(value);
      case "usd": return value < 0.01 ? "<$0.01" : `$${value.toFixed(2)}`;
      case "sec": return `${value.toFixed(1)} s`;
      default: return value.toFixed(3);
    }
  }

  function modelCell(row) {
    const [base, variant] = row.model.split("__reasoning-");
    const chip = variant ? `<span class="sm-lb-chip">reasoning: ${esc(variant)}</span>` : "";
    const meta = [row.provider, row.source === "Manual" ? "manual runs" : null].filter(Boolean).join(" · ");
    return `<div class="sm-lb-model"><strong title="${esc(row.model_id)}">${esc(base)}</strong>${chip}</div>` +
      (meta ? `<div class="sm-lb-sub">${esc(meta)}</div>` : "");
  }

  function renderTable(task, state) {
    const query = state.query.trim().toLowerCase();
    const rows = task.leaderboard.filter((row) =>
      [row.model, row.model_id, row.provider].some((value) => String(value || "").toLowerCase().includes(query)));
    if (state.sort) {
      const { key, dir } = state.sort;
      rows.sort((a, b) => {
        const av = a[key], bv = b[key];
        if (av == null && bv == null) return 0;
        if (av === null || av === undefined) return 1;
        if (bv === null || bv === undefined) return -1;
        return dir * (av - bv);
      });
    }
    const max = Math.max(1e-9, ...task.leaderboard.map((r) => r.mean_score || 0));
    const head = COLUMNS.map((c) => {
      const active = state.sort && state.sort.key === c.key;
      const arrow = active ? (state.sort.dir < 0 ? " ↓" : " ↑") : "";
      return `<th scope="col" class="sm-lb-num" aria-sort="${active ? (state.sort.dir < 0 ? "descending" : "ascending") : "none"}"><button type="button" data-sort="${c.key}">${c.label}${arrow}</button></th>`;
    }).join("");
    const body = rows.map((row) => {
      const cells = COLUMNS.map((c) => {
        if (c.kind === "score") {
          const width = row.mean_score ? (100 * row.mean_score) / max : 0;
          return `<td class="sm-lb-num"><span class="sm-lb-score"><span class="sm-lb-bar"><span style="width:${width.toFixed(1)}%"></span></span><span class="sm-lb-val">${fmt(row.mean_score, "num")}</span></span></td>`;
        }
        return `<td class="sm-lb-num">${fmt(row[c.key], c.kind)}</td>`;
      }).join("");
      return `<tr><td class="sm-lb-rank">${task.leaderboard.indexOf(row) + 1}</td><td>${modelCell(row)}</td>${cells}</tr>`;
    }).join("");
    return `<p class="sm-lb-count" role="status">Showing ${rows.length} of ${task.leaderboard.length} models · Rank follows the original score order. Select a column to sort.</p>` +
      `<div class="sm-lb-scroll" tabindex="0" role="region" aria-label="Model results; scroll horizontally for more columns"><table class="sm-lb-table"><caption class="sm-sr-only">${esc(task.title)} model results</caption><thead><tr><th scope="col" class="sm-lb-rank">#</th><th scope="col">Model</th>${head}</tr></thead><tbody>${body || '<tr><td colspan="9" class="sm-lb-empty">No models match your search. Try another name or provider.</td></tr>'}</tbody></table></div>`;
  }

  function renderFunnel(task) {
    const total = task.runs || 1;
    const stages = [{ stage: "Attempts", runs: task.runs }, ...task.funnel];
    return `<div class="sm-lb-funnel">` + stages.map((s) => {
      const pct = (100 * s.runs) / total;
      return `<div class="sm-lb-stage"><span class="sm-lb-stage-name">${esc(s.stage)}</span>` +
        `<span class="sm-lb-stage-track"><span style="width:${pct.toFixed(1)}%"></span></span>` +
        `<span class="sm-lb-stage-val">${s.runs} <small>${pct.toFixed(0)}%</small></span></div>`;
    }).join("") + `</div>`;
  }

  function renderTask(task, state) {
    const t = task.targets || {};
    const targets = [
      t.heat_duty_kw != null ? `duty ≥ ${t.heat_duty_kw} kW` : null,
      t.max_dp_tube_kpa != null ? `ΔP tube ≤ ${t.max_dp_tube_kpa} kPa` : null,
      t.max_dp_shell_kpa != null ? `ΔP shell ≤ ${t.max_dp_shell_kpa} kPa` : null,
    ].filter(Boolean).join(" · ");
    const date = (iso) => (iso ? iso.slice(0, 10) : "–");
    const facts = [
      ["Simulator", task.simulator_version || "legacy"],
      ["Score", task.score_version || "legacy"],
      ["Requirements", targets || "–"],
      ["Runs", `${task.runs} across ${task.models} models`],
      ["Recorded", `${date(task.first_run)} to ${date(task.last_run)}`],
    ].map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");
    return `<h2 class="sm-lb-title">${esc(task.title)}</h2>` +
      `<p class="sm-lb-slug"><code>${esc(task.slug)}</code> · <a href="https://github.com/suni-muhendis/sm-bench/tree/main/results/${encodeURIComponent(task.trackId)}/${encodeURIComponent(task.slug)}">task files</a></p>` +
      `<dl class="sm-lb-facts">${facts}</dl>` +
      `<section class="sm-charts" aria-label="Interactive model comparisons"></section>` +
      `<h3>Detailed results</h3>` +
      `<div class="sm-lb-toolbar"><label for="sm-lb-search">Find a model<input id="sm-lb-search" type="search" placeholder="Model name or provider…" value="${esc(state.query)}" autocomplete="off"></label></div>` +
      `<div class="sm-lb-results">${renderTable(task, state)}</div>` +
      `<h3>Where attempts stop</h3>` + renderFunnel(task);
  }

  function mount(root, data) {
    const tasks = data.tracks.flatMap((track) => track.tasks.map((task) => ({ ...task, track: track.label, trackId: track.id })));
    if (!tasks.length) {
      root.innerHTML = '<p class="sm-lb-status">No recorded runs yet.</p>';
      return;
    }
    const state = { slug: tasks[0].slug, sort: null, query: "" };
    let fromHash = "";
    try { fromHash = decodeURIComponent(location.hash.slice(1)); } catch (_) { /* Ignore malformed links. */ }
    if (tasks.some((t) => t.slug === fromHash)) state.slug = fromHash;

    const options = tasks.map((t) =>
      `<option value="${esc(t.slug)}">${esc(t.slug)} (${esc(t.track)}, ${t.runs} runs)</option>`).join("");
    root.innerHTML =
      `<div class="sm-lb-picker"><label for="sm-lb-task">Task</label><select id="sm-lb-task">${options}</select>` +
      `<span class="sm-lb-built">Built ${esc(data.generated_at.slice(0, 10))}</span></div><div class="sm-lb-body"></div>`;
    const select = root.querySelector("#sm-lb-task");
    const body = root.querySelector(".sm-lb-body");

    const draw = () => {
      select.value = state.slug;
      const task = tasks.find((t) => t.slug === state.slug);
      body.innerHTML = renderTask(task, state);
      if (window.SMBenchCharts) window.SMBenchCharts.mount(body.querySelector(".sm-charts"), task);
    };
    select.addEventListener("change", () => {
      state.slug = select.value;
      state.sort = null;
      state.query = "";
      history.replaceState(null, "", "#" + encodeURIComponent(state.slug));
      draw();
    });
    body.addEventListener("input", (event) => {
      if (event.target.id !== "sm-lb-search") return;
      state.query = event.target.value;
      body.querySelector(".sm-lb-results").innerHTML = renderTable(tasks.find((t) => t.slug === state.slug), state);
    });
    body.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-sort]");
      if (!button) return;
      const key = button.dataset.sort;
      state.sort = state.sort && state.sort.key === key
        ? (state.sort.dir < 0 ? { key, dir: 1 } : null)
        : { key, dir: -1 };
      body.querySelector(".sm-lb-results").innerHTML = renderTable(tasks.find((t) => t.slug === state.slug), state);
      body.querySelector(`button[data-sort="${key}"]`).focus({ preventScroll: true });
    });
    draw();
  }

  function init() {
    const root = document.getElementById("sm-leaderboard");
    if (!root) return;
    fetch(root.dataset.src)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => mount(root, data))
      .catch(() => {
        root.innerHTML = '<p class="sm-lb-status" role="alert">The results could not be loaded. ' +
          'Please reload the page or <a href="https://github.com/suni-muhendis/sm-bench/tree/main/results">browse the recorded runs on GitHub</a>.</p>';
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
