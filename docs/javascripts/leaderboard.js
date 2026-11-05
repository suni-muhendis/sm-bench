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

  // A suite adds one mean-score column per task group (e.g. easy / medium / hard).
  function columnsFor(task) {
    if (task.kind !== "suite" || !task.suite) return COLUMNS;
    const groups = task.suite.groups.map((g) => ({ key: `group:${g}`, label: g.charAt(0).toUpperCase() + g.slice(1), kind: "num", group: g }));
    return [COLUMNS[0], ...groups, ...COLUMNS.slice(1)];
  }

  const cellValue = (row, c) => (c.group ? (row.group_scores || {})[c.group] : row[c.key]);

  const PROVIDERS = { openrouter: "via OpenRouter", local: "local GPU", opencode: "via OpenCode", hf: "via Hugging Face" };
  const role = (row) => (row.display || {}).role;

  function modelName(row) {
    const shown = row.display || {};
    const label = shown.label || row.model.split("__reasoning-")[0];
    return shown.url
      ? `<a href="${esc(shown.url)}" target="_blank" rel="noopener" title="${esc(row.model_id)}">${esc(label)}</a>`
      : `<span title="${esc(row.model_id)}">${esc(label)}</span>`;
  }

  function modelCell(row, task) {
    const variant = row.model.split("__reasoning-")[1];
    let chip = role(row) === "featured" ? '<span class="sm-lb-chip sm-lb-chip--brand">Fine-tuned</span>' : "";
    chip += variant ? `<span class="sm-lb-chip">reasoning: ${esc(variant)}</span>` : "";
    if (row.complete === false && task && task.suite) {
      chip += `<span class="sm-lb-chip sm-lb-chip--warn" title="Not ranked: the mean covers fewer tasks than the others">incomplete: ${row.tasks_done}/${task.suite.n_tasks} tasks</span>`;
    }
    const meta = [(row.display || {}).note || PROVIDERS[row.provider] || row.provider,
      row.source === "Manual" ? "manual runs" : null].filter(Boolean).join(" · ");
    return `<div class="sm-lb-model"><strong>${modelName(row)}</strong>${chip}</div>` +
      (meta ? `<div class="sm-lb-sub">${esc(meta)}</div>` : "");
  }

  // Overview for a suite: headline tiles, then the featured model against its own
  // base model and the best other model, per difficulty level.
  function renderSuiteOverview(task) {
    const s = task.suite;
    const ranked = task.leaderboard.filter((r) => r.complete !== false);
    const top = ranked[0];
    const featured = task.leaderboard.find((r) => role(r) === "featured");
    const base = task.leaderboard.find((r) => role(r) === "base");
    const rival = ranked.find((r) => !role(r));
    const refs = s.groups.map((g) => s.reference_mean_score[g]).filter((v) => v != null);
    const refMean = refs.length ? refs.reduce((a, b) => a + b, 0) / refs.length : null;
    const name = (r) => esc((r.display || {}).label || r.model.split("__reasoning-")[0]);
    const tile = (label, value, sub) =>
      `<div class="sm-kpi"><span class="sm-kpi-label">${label}</span><span class="sm-kpi-value">${value}</span><span class="sm-kpi-sub">${sub}</span></div>`;
    const tiles = `<div class="sm-kpis">` +
      tile("Tasks", s.n_tasks, `${s.groups.length} levels · one answer each`) +
      tile("Models", task.models, `${ranked.length} ranked`) +
      (top ? tile("Top mean score", fmt(top.mean_score, "num"), name(top)) : "") +
      (refMean != null ? tile("Reference design", fmt(refMean, "num"), "reachable ceiling, mean of levels") : "") +
      `</div>`;
    if (!featured) return tiles;

    const series = [
      { row: featured, cls: "sm-s1", label: name(featured) },
      base ? { row: base, cls: "sm-s2", label: name(base) } : null,
      rival ? { row: rival, cls: "sm-s3", label: `${name(rival)} (best other model)` } : null,
    ].filter(Boolean);
    const legend = series.map((x) => `<span class="sm-legend-item"><span class="sm-swatch ${x.cls}"></span>${x.label}</span>`).join("");
    const levels = s.groups.map((g) => {
      const ref = s.reference_mean_score[g];
      const bars = series.map((x) => {
        const v = (x.row.group_scores || {})[g];
        const w = v == null ? 0 : Math.max(0, Math.min(1, v)) * 100;
        const tip = `${x.label.replace(/<[^>]+>/g, "")}, ${g}: ${fmt(v, "num")}`;
        return `<div class="sm-fbar" tabindex="0" title="${esc(tip)}" aria-label="${esc(tip)}"><span class="sm-fbar-track"><span class="${x.cls}" style="width:${w.toFixed(1)}%"></span>` +
          (ref != null ? `<span class="sm-fbar-ref" style="left:${(100 * ref).toFixed(1)}%"></span>` : "") +
          `</span><span class="sm-fbar-val">${fmt(v, "num")}</span></div>`;
      }).join("");
      return `<div class="sm-flevel"><div class="sm-flevel-name">${esc(g.charAt(0).toUpperCase() + g.slice(1))}` +
        (ref != null ? `<small>reference ${fmt(ref, "num")}</small>` : "") + `</div><div class="sm-fbars">${bars}</div></div>`;
    }).join("");
    const shown = featured.display || {};
    const link = shown.url
      ? `<a class="sm-feature-link" href="${esc(shown.url)}" target="_blank" rel="noopener">View on Hugging Face →</a>` : "";
    return tiles +
      `<section class="sm-feature" aria-label="Featured model">` +
      `<div class="sm-feature-head"><div><span class="sm-feature-eyebrow">Suni Muhendis model</span>` +
      `<h3 class="sm-feature-title">${name(featured)}</h3>` +
      `<p class="sm-feature-note">${esc(shown.note || "")}. None of these tasks was used to train it.</p></div>${link}</div>` +
      `<div class="sm-legend">${legend}<span class="sm-legend-item"><span class="sm-swatch sm-swatch--ref"></span>reference design</span></div>` +
      `<div class="sm-flevels">${levels}</div>` +
      `<p class="sm-feature-foot">Mean score per difficulty level, 0 to 1. The base model ran on the same GPU with the same settings.</p>` +
      `</section>`;
  }

  // Sequential tint for a 0–1 score cell: one hue, stronger with the value.
  const heat = (v) => (v == null ? "" : ` style="--sm-heat-a:${(6 + 30 * Math.max(0, Math.min(1, v))).toFixed(0)}%"`);

  function renderTable(task, state) {
    const query = state.query.trim().toLowerCase();
    const rows = task.leaderboard.filter((row) =>
      [row.model, row.model_id, row.provider, (row.display || {}).label].some((value) => String(value || "").toLowerCase().includes(query)));
    const columns = columnsFor(task);
    if (state.sort) {
      const { key, dir } = state.sort;
      const col = columns.find((c) => c.key === key) || { key };
      rows.sort((a, b) => {
        const av = cellValue(a, col), bv = cellValue(b, col);
        if (av == null && bv == null) return 0;
        if (av === null || av === undefined) return 1;
        if (bv === null || bv === undefined) return -1;
        return dir * (av - bv);
      });
    }
    const max = Math.max(1e-9, ...task.leaderboard.map((r) => r.mean_score || 0));
    const head = columns.map((c) => {
      const active = state.sort && state.sort.key === c.key;
      const arrow = active ? (state.sort.dir < 0 ? " ↓" : " ↑") : "";
      return `<th scope="col" class="sm-lb-num" aria-sort="${active ? (state.sort.dir < 0 ? "descending" : "ascending") : "none"}"><button type="button" data-sort="${c.key}">${c.label}${arrow}</button></th>`;
    }).join("");
    const body = rows.map((row) => {
      const cells = columns.map((c) => {
        if (c.kind === "score") {
          const width = row.mean_score ? (100 * row.mean_score) / max : 0;
          return `<td class="sm-lb-num"><span class="sm-lb-score"><span class="sm-lb-bar"><span style="width:${width.toFixed(1)}%"></span></span><span class="sm-lb-val">${fmt(row.mean_score, "num")}</span></span></td>`;
        }
        if (c.group) {
          const v = cellValue(row, c);
          return `<td class="sm-lb-num sm-lb-heat"${heat(v)}>${fmt(v, c.kind)}</td>`;
        }
        return `<td class="sm-lb-num">${fmt(cellValue(row, c), c.kind)}</td>`;
      }).join("");
      const rank = row.complete === false ? "–" : task.leaderboard.indexOf(row) + 1;
      const cls = role(row) === "featured" ? ' class="sm-lb-featured"' : "";
      return `<tr${cls}><td class="sm-lb-rank">${rank}</td><td>${modelCell(row, task)}</td>${cells}</tr>`;
    }).join("");
    return `<p class="sm-lb-count" role="status">Showing ${rows.length} of ${task.leaderboard.length} models · Rank follows the original score order. Select a column to sort.</p>` +
      `<div class="sm-lb-scroll" tabindex="0" role="region" aria-label="Model results; scroll horizontally for more columns"><table class="sm-lb-table"><caption class="sm-sr-only">${esc(task.title)} model results</caption><thead><tr><th scope="col" class="sm-lb-rank">#</th><th scope="col">Model</th>${head}</tr></thead><tbody>${body || `<tr><td colspan="${columns.length + 2}" class="sm-lb-empty">No models match your search. Try another name or provider.</td></tr>`}</tbody></table></div>`;
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
    const s = task.suite;
    const facts = [
      ["Simulator", task.simulator_version || "legacy"],
      ["Score", task.score_version || "legacy"],
      ...(s ? [] : [["Requirements", targets || "–"]]),
      ["Runs", `${task.runs} across ${task.models} models`],
      ["Recorded", `${date(task.first_run)} to ${date(task.last_run)}`],
    ].map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");
    const badge = task.archived ? ' <span class="sm-lb-chip">Archive</span>' : "";
    return `<h2 class="sm-lb-title">${esc(task.title)}${badge}</h2>` +
      `<p class="sm-lb-slug"><code>${esc(task.slug)}</code> · <a href="https://github.com/suni-muhendis/sm-bench/tree/main/results/${encodeURIComponent(task.trackId)}/${encodeURIComponent(task.slug)}">task files</a></p>` +
      `<dl class="sm-lb-facts">${facts}</dl>` +
      (task.kind === "suite" && task.suite ? renderSuiteOverview(task) : "") +
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

    const option = (t) =>
      `<option value="${esc(t.slug)}">${esc(t.slug)} (${esc(t.track)}, ${t.runs} runs)</option>`;
    const current = tasks.filter((t) => !t.archived), archived = tasks.filter((t) => t.archived);
    const options = (current.length ? `<optgroup label="Current">${current.map(option).join("")}</optgroup>` : "") +
      (archived.length ? `<optgroup label="Archive">${archived.map(option).join("")}</optgroup>` : "");
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
