// Dashboard for a task suite (docs/data/leaderboard.json, task.kind === "suite").
// leaderboard.js calls SMSuite.render(container, task) and SMSuite stays inside
// that container. Single-task (archive) pages keep the classic view.
(function () {
  "use strict";

  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 3) => (v == null || Number.isNaN(v) ? "–" : Number(v).toFixed(d));
  const pct = (v) => (v == null ? "–" : `${Math.round(v)}%`);
  const usd = (v) => (v == null ? "–" : v < 0.01 ? "<$0.01" : `$${v.toFixed(2)}`);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const clamp01 = (v) => Math.max(0, Math.min(1, v || 0));

  const name = (r) => (r.display && r.display.label) || r.model.split("__reasoning-")[0];
  const effort = (r) => r.model.split("__reasoning-")[1] || null;
  const role = (r) => (r.display && r.display.role) || null;
  const markClass = (r) => (role(r) === "featured" ? "is-featured" : role(r) === "base" ? "is-base" : "");

  // Sequential ramp (one hue, light -> dark) for score cells; text ink flips on dark steps.
  const RAMP = ["#eef4fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
  const rampIndex = (v) => Math.min(RAMP.length - 1, Math.floor(clamp01(v) * RAMP.length));
  const cell = (v) => {
    if (v == null) return 'class="sm-x-cell is-empty"';
    const i = rampIndex(v);
    return `class="sm-x-cell${i >= 4 ? " is-dark" : ""}" style="--c:${RAMP[i]}"`;
  };

  // ── shared tooltip ────────────────────────────────────────────────────
  let tip;
  function tooltip() {
    if (tip) return tip;
    tip = document.createElement("div");
    tip.className = "sm-x-tip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);
    return tip;
  }
  function showTip(target, html, event) {
    const t = tooltip();
    t.innerHTML = html;
    t.hidden = false;
    const r = target.getBoundingClientRect();
    const x = event && event.clientX ? event.clientX : r.left + r.width / 2;
    const y = event && event.clientY ? event.clientY : r.top;
    const w = t.offsetWidth, h = t.offsetHeight;
    const left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14));
    const top = y - h - 12 < 8 ? y + 18 : y - h - 12;
    t.style.left = `${left + window.scrollX}px`;
    t.style.top = `${top + window.scrollY}px`;
  }
  const hideTip = () => { if (tip) tip.hidden = true; };
  function bindTips(root) {
    const on = (e) => {
      const el = e.target.closest("[data-tip]");
      if (el && root.contains(el)) showTip(el, el.dataset.tip, e.type === "focusin" ? null : e);
    };
    root.addEventListener("mousemove", on);
    root.addEventListener("focusin", on);
    root.addEventListener("mouseleave", hideTip);
    root.addEventListener("focusout", hideTip);
  }
  const tipHtml = (title, rows) =>
    esc(`<strong>${title}</strong>` + rows.map(([k, v]) => `<span><em>${k}</em><b>${v}</b></span>`).join(""));

  // ── header, KPIs, spotlight ───────────────────────────────────────────
  function header(task) {
    const date = (iso) => (iso ? iso.slice(0, 10) : "–");
    return `<header class="sm-x-head">
      <div><p class="sm-x-eyebrow">Task suite · zero-shot</p>
      <h2 class="sm-x-title">${esc(task.title)}</h2>
      <div class="sm-x-tags"><span>${esc(task.score_version || "")}</span><span>simulator ${esc(task.simulator_version || "")}</span><span>recorded ${date(task.last_run)}</span>
      <a href="https://github.com/suni-muhendis/sm-bench/tree/main/results/${encodeURIComponent(task.trackId)}/${encodeURIComponent(task.slug)}">task files ↗</a></div></div>
    </header>`;
  }

  function kpis(task, ranked, featured, base) {
    const s = task.suite;
    const refs = s.groups.map((g) => s.reference_mean_score[g]).filter((v) => v != null);
    const ceiling = refs.length ? refs.reduce((a, b) => a + b, 0) / refs.length : null;
    const top = ranked[0];
    const lift = featured && base && base.mean_score ? featured.mean_score / base.mean_score - 1 : null;
    const tile = (label, value, sub, accent) =>
      `<div class="sm-x-kpi${accent ? " is-accent" : ""}"><span class="sm-x-kpi-label">${label}</span><span class="sm-x-kpi-value">${value}</span><span class="sm-x-kpi-sub">${sub}</span></div>`;
    return `<div class="sm-x-kpis">` +
      tile("Tasks", s.n_tasks, `${s.groups.map(cap).join(" · ")} · one answer each`) +
      tile("Models", ranked.length, "evaluated zero-shot") +
      (top ? tile("Top mean score", num(top.mean_score), esc(name(top))) : "") +
      (lift != null ? tile("Gain from fine-tuning", `+${Math.round(100 * lift)}%`, `${num(base.mean_score)} → ${num(featured.mean_score)} over its base`, true) : "") +
      (ceiling != null ? tile("Reference design", num(ceiling), "reachable score, mean of levels") : "") +
      `</div>`;
  }

  function spotlight(task, featured, base, rival) {
    if (!featured) return "";
    const s = task.suite;
    const series = [[featured, "is-featured"], [base, "is-base"], [rival, "is-other"]].filter(([r]) => r);
    const legend = series.map(([r, c]) => `<span><i class="sm-x-sw ${c}"></i>${esc(name(r))}${r === rival ? " <small>best other model</small>" : ""}</span>`).join("") +
      `<span><i class="sm-x-sw is-ref"></i>reference design</span>`;
    const groups = s.groups.map((g) => {
      const ref = s.reference_mean_score[g];
      const bars = series.map(([r, c]) => {
        const v = (r.group_scores || {})[g];
        const gate = (r.group_gate_pct || {})[g];
        return `<div class="sm-x-sbar" tabindex="0" data-tip="${tipHtml(esc(name(r)), [[cap(g), num(v)], ["Requirements met", pct(gate)], ["Reference", num(ref)]])}">
          <span class="sm-x-sbar-fill ${c}" style="--w:${(100 * clamp01(v)).toFixed(1)}%"></span><span class="sm-x-sbar-val">${num(v)}</span></div>`;
      }).join("");
      return `<div class="sm-x-sgroup"><div class="sm-x-sgroup-name">${cap(g)}<small>reference ${num(ref, 2)}</small></div>
        <div class="sm-x-sbars" style="--ref-f:${clamp01(ref).toFixed(3)}">${bars}</div></div>`;
    }).join("");
    const d = featured.display || {};
    return `<section class="sm-x-spot" aria-label="Featured model">
      <div class="sm-x-spot-info">
        <p class="sm-x-eyebrow">Suni Muhendis model</p>
        <h3>${esc(name(featured))}</h3>
        <p class="sm-x-muted">${esc(d.note || "")}</p>
        <p class="sm-x-muted">None of these tasks was used to train it.</p>
        <div class="sm-x-spot-stats">
          <div><b>${num(featured.mean_score)}</b><span>mean score</span></div>
          <div><b>#${task.leaderboard.indexOf(featured) + 1}</b><span>of ${task.leaderboard.filter((r) => r.complete !== false).length}</span></div>
          <div><b>${featured.distinct_designs}</b><span>distinct designs</span></div>
        </div>
        ${d.url ? `<a class="sm-x-btn" href="${esc(d.url)}" target="_blank" rel="noopener">View on Hugging Face ↗</a>` : ""}
      </div>
      <div class="sm-x-spot-chart"><div class="sm-x-legend">${legend}</div>${groups}</div>
    </section>`;
  }

  // ── charts ────────────────────────────────────────────────────────────
  const VIEWS = [["ranking", "Ranking"], ["heatmap", "Heatmap"], ["tasks", "Task by task"], ["efficiency", "Cost & speed"]];

  function metricOf(r, metric) { return metric === "overall" ? r.mean_score : (r.group_scores || {})[metric]; }

  function ranking(task, rows, metric) {
    const s = task.suite;
    const order = [...rows].sort((a, b) => (metricOf(b, metric) ?? -1) - (metricOf(a, metric) ?? -1));
    const ref = metric === "overall" ? null : s.reference_mean_score[metric];
    const h = 34;
    const items = rows.map((r) => {
      const v = metricOf(r, metric);
      const pos = order.indexOf(r);
      const shown = r.complete === false ? "–" : pos + 1;
      const gate = metric === "overall" ? r.requirements_pct : (r.group_gate_pct || {})[metric];
      const t = tipHtml(esc(name(r)), [[metric === "overall" ? "Mean score" : `${cap(metric)} score`, num(v)], ["Rank", `${pos + 1} of ${rows.length}`], ["Requirements met", pct(gate)], ...(effort(r) ? [["Reasoning", effort(r)]] : [])]);
      return `<div class="sm-x-rrow ${markClass(r)}" style="transform:translateY(${pos * h}px)" tabindex="0" data-tip="${t}">
        <span class="sm-x-rrank">${shown}</span><span class="sm-x-rname">${esc(name(r))}${effort(r) ? `<small>${esc(effort(r))}</small>` : ""}</span>
        <span class="sm-x-rtrack"><span class="sm-x-rfill" style="--w:${(100 * clamp01(v)).toFixed(1)}%"></span></span><span class="sm-x-rval">${num(v)}</span></div>`;
    }).join("");
    const refLine = ref != null ? `<span class="sm-x-rref" style="--ref:${(100 * ref).toFixed(1)}%"><em>reference ${num(ref, 2)}</em></span>` : "";
    return `<div class="sm-x-ranking" style="height:${rows.length * h}px">${items}<div class="sm-x-rref-wrap">${refLine}</div></div>`;
  }

  function heatmap(task, rows) {
    const s = task.suite;
    const cols = [...s.groups, "overall"];
    const head = cols.map((c) => `<th scope="col">${cap(c)}</th>`).join("");
    const body = rows.map((r) => `<tr class="${markClass(r)}"><th scope="row">${esc(name(r))}</th>` + cols.map((c) => {
      const v = metricOf(r, c);
      const gate = c === "overall" ? r.requirements_pct : (r.group_gate_pct || {})[c];
      return `<td ${cell(v)} tabindex="0" data-tip="${tipHtml(esc(name(r)), [[cap(c), num(v)], ["Requirements met", pct(gate)]])}">${num(v, 2)}</td>`;
    }).join("") + `</tr>`).join("");
    const refRow = `<tr class="is-ref"><th scope="row">Reference design</th>` + cols.map((c) => {
      const v = c === "overall" ? null : s.reference_mean_score[c];
      return `<td ${cell(v)}>${num(v, 2)}</td>`;
    }).join("") + `</tr>`;
    return `<div class="sm-x-scroll"><table class="sm-x-heat"><thead><tr><th></th>${head}</tr></thead><tbody>${body}${refRow}</tbody></table></div>` + scale();
  }

  function scale() {
    return `<div class="sm-x-scale"><span>0</span>${RAMP.map((c) => `<i style="background:${c}"></i>`).join("")}<span>1</span><em>score</em></div>`;
  }

  function perTask(task, rows) {
    const s = task.suite;
    const tasks = s.groups.flatMap((g) => s.tasks.filter((t) => t.group === g));
    const head = s.groups.map((g) => `<th scope="colgroup" colspan="${s.tasks.filter((t) => t.group === g).length}" class="sm-x-gh">${cap(g)}</th>`).join("");
    const body = rows.map((r) => `<tr class="${markClass(r)}"><th scope="row">${esc(name(r))}</th>` + tasks.map((t, i) => {
      const v = (r.task_scores || {})[t.id];
      const edge = i > 0 && tasks[i - 1].group !== t.group ? " is-edge" : "";
      return `<td ${cell(v).replace('class="', `class="sm-x-dot${edge} `)} tabindex="0" data-tip="${tipHtml(esc(name(r)), [["Task", t.id], ["Level", cap(t.group)], ["Score", num(v)], ["Requirements", v != null && v >= 0.3 ? "met" : "not met"]])}"></td>`;
    }).join("") + `</tr>`).join("");
    return `<p class="sm-x-note">Every cell is one task, answered once. A score of 0.3 or more means the design met every requirement; above that, cost and design quality add the rest.</p>
      <div class="sm-x-scroll"><table class="sm-x-tasks"><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table></div>` + scale();
  }

  function efficiency(task, rows, axis) {
    const W = 760, H = 380, L = 56, R = 24, T = 18, B = 46;
    const xs = (r) => (axis === "cost" ? (r.cost_usd != null && r.runs ? r.cost_usd / r.runs : null) : r.p50_latency_s);
    const pts = rows.filter((r) => xs(r) != null && xs(r) > 0 && r.mean_score != null);
    const skipped = rows.length - pts.length;
    if (!pts.length) return '<p class="sm-x-note">No data for this view.</p>';
    const lo = Math.log10(Math.min(...pts.map(xs))), hi = Math.log10(Math.max(...pts.map(xs)));
    const x0 = Math.floor(lo), x1 = Math.ceil(hi === lo ? hi + 1 : hi);
    const sx = (v) => L + ((Math.log10(v) - x0) / (x1 - x0)) * (W - L - R);
    const ymax = Math.min(1, Math.ceil(Math.max(...pts.map((r) => r.mean_score)) * 10 + 1) / 10);
    const sy = (v) => T + (1 - v / ymax) * (H - T - B);
    let g = "";
    for (let e = x0; e <= x1; e++) {
      const v = 10 ** e;
      g += `<line class="sm-x-grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H - B}"/><text class="sm-x-axis" x="${sx(v)}" y="${H - B + 18}" text-anchor="middle">${axis === "cost" ? (v < 0.01 ? `$${v}` : `$${v.toFixed(2)}`) : `${v} s`}</text>`;
    }
    for (let v = 0; v <= ymax + 1e-9; v += 0.1) {
      g += `<line class="sm-x-grid" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="sm-x-axis" x="${L - 8}" y="${sy(v) + 4}" text-anchor="end">${v.toFixed(1)}</text>`;
    }
    const label = axis === "cost" ? "Cost per task (log scale)" : "Median latency per answer (log scale)";
    g += `<text class="sm-x-axis-title" x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">${label}</text>` +
      `<text class="sm-x-axis-title" transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">Mean score</text>`;
    const dots = pts.map((r) => {
      const t = tipHtml(esc(name(r)), [["Mean score", num(r.mean_score)], [axis === "cost" ? "Cost per task" : "Median latency", axis === "cost" ? `$${xs(r).toFixed(4)}` : `${xs(r).toFixed(1)} s`], ["Total cost", usd(r.cost_usd)]]);
      const lbl = role(r) || r === pts.reduce((a, b) => (b.mean_score > a.mean_score ? b : a)) ? `<text class="sm-x-dlabel" x="${sx(xs(r)) + 10}" y="${sy(r.mean_score) + 4}">${esc(name(r))}</text>` : "";
      return `<g class="sm-x-pt ${markClass(r)}" tabindex="0" data-tip="${t}"><circle cx="${sx(xs(r))}" cy="${sy(r.mean_score)}" r="14" class="sm-x-hit"/><circle cx="${sx(xs(r))}" cy="${sy(r.mean_score)}" r="6"/>${lbl}</g>`;
    }).join("");
    const note = skipped ? `<p class="sm-x-note">${skipped} model${skipped > 1 ? "s" : ""} without ${axis === "cost" ? "a recorded price" : "latency data"} not shown.</p>` : "";
    return `<svg class="sm-x-scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mean score against ${label}">${g}${dots}</svg>${note}`;
  }

  // ── table ─────────────────────────────────────────────────────────────
  const COLS = [
    ["mean_score", "Mean", "score"], ["group:easy", "Easy", "heat"], ["group:medium", "Medium", "heat"], ["group:hard", "Hard", "heat"],
    ["requirements_pct", "Req. met", "pct"], ["valid_pct", "Valid", "pct"], ["cost_usd", "Cost", "usd"], ["p50_latency_s", "Latency", "sec"],
  ];
  const colVal = (r, k) => (k.startsWith("group:") ? (r.group_scores || {})[k.slice(6)] : r[k]);

  function table(task, state) {
    const q = state.query.trim().toLowerCase();
    let rows = task.leaderboard.filter((r) => [name(r), r.model, r.model_id].some((v) => String(v || "").toLowerCase().includes(q)));
    if (state.sort) rows = [...rows].sort((a, b) => state.sort.dir * ((colVal(a, state.sort.key) ?? -1) - (colVal(b, state.sort.key) ?? -1)));
    const max = Math.max(1e-9, ...task.leaderboard.map((r) => r.mean_score || 0));
    const head = COLS.map(([k, l]) => {
      const on = state.sort && state.sort.key === k;
      return `<th scope="col" aria-sort="${on ? (state.sort.dir < 0 ? "descending" : "ascending") : "none"}"><button type="button" data-xsort="${k}">${l}${on ? (state.sort.dir < 0 ? " ↓" : " ↑") : ""}</button></th>`;
    }).join("");
    const body = rows.map((r) => {
      const rank = r.complete === false ? "–" : task.leaderboard.indexOf(r) + 1;
      const chips = (role(r) === "featured" ? '<span class="sm-x-chip is-brand">Fine-tuned</span>' : "") +
        (effort(r) ? `<span class="sm-x-chip">reasoning: ${esc(effort(r))}</span>` : "") +
        (r.complete === false ? `<span class="sm-x-chip is-warn">${r.tasks_done}/${task.suite.n_tasks} tasks</span>` : "");
      const link = r.display && r.display.url ? `<a href="${esc(r.display.url)}" target="_blank" rel="noopener">${esc(name(r))}</a>` : esc(name(r));
      const cells = COLS.map(([k, , kind]) => {
        const v = colVal(r, k);
        if (kind === "score") return `<td class="n"><span class="sm-x-meanbar"><i style="--w:${(100 * (v || 0) / max).toFixed(1)}%"></i></span><b>${num(v)}</b></td>`;
        if (kind === "heat") return `<td ${cell(v).replace('class="', 'class="n ')}>${num(v)}</td>`;
        if (kind === "pct") return `<td class="n">${pct(v)}</td>`;
        if (kind === "usd") return `<td class="n">${usd(v)}</td>`;
        return `<td class="n">${v == null ? "–" : `${v.toFixed(1)} s`}</td>`;
      }).join("");
      return `<tr class="${markClass(r)}"><td class="sm-x-rank">${rank}</td><td><div class="sm-x-model">${link}${chips}</div>${r.display && r.display.note ? `<div class="sm-x-sub">${esc(r.display.note)}</div>` : ""}</td>${cells}</tr>`;
    }).join("");
    return `<div class="sm-x-scroll"><table class="sm-x-table"><thead><tr><th>#</th><th>Model</th>${head}</tr></thead><tbody>${body ||
      `<tr><td colspan="${COLS.length + 2}" class="sm-x-empty">No model matches.</td></tr>`}</tbody></table></div>`;
  }

  // ── mount ─────────────────────────────────────────────────────────────
  function render(root, task) {
    const ranked = task.leaderboard.filter((r) => r.complete !== false);
    const featured = task.leaderboard.find((r) => role(r) === "featured");
    const base = task.leaderboard.find((r) => role(r) === "base");
    const rival = ranked.find((r) => !role(r));
    const state = { view: "ranking", metric: "overall", axis: "cost", sort: null, query: "" };
    try {
      // ?view=heatmap etc. opens a chart directly, so a view can be linked.
      const asked = new URLSearchParams(location.search).get("view");
      if (VIEWS.some(([id]) => id === asked)) state.view = asked;
    } catch (_) { /* no URL API: keep the default view */ }
    const metrics = ["overall", ...task.suite.groups];

    root.innerHTML = header(task) + kpis(task, ranked, featured, base) + spotlight(task, featured, base, rival) +
      `<section class="sm-x-panel" aria-label="Interactive charts">
        <div class="sm-x-tabs" role="tablist">${VIEWS.map(([id, l]) => `<button type="button" role="tab" data-view="${id}">${l}</button>`).join("")}</div>
        <div class="sm-x-controls"></div><div class="sm-x-chart"></div>
      </section>
      <section class="sm-x-panel" aria-label="All results">
        <div class="sm-x-panel-head"><h3>All results</h3><input type="search" class="sm-x-search" placeholder="Find a model…" aria-label="Find a model"></div>
        <div class="sm-x-table-wrap"></div>
        <p class="sm-x-note">Mean averages every answer except those that never ran; a failed design counts as 0. Requirements met: duty target and both pressure-drop limits. Models that did not answer every task are listed but not ranked.</p>
      </section>`;

    const chart = root.querySelector(".sm-x-chart"), controls = root.querySelector(".sm-x-controls");
    const seg = (key, opts) => `<div class="sm-x-seg" role="group">${opts.map(([v, l]) => `<button type="button" data-${key}="${v}" aria-pressed="${state[key] === v}">${l}</button>`).join("")}</div>`;
    const drawChart = (keepRanking) => {
      root.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === state.view)));
      controls.innerHTML = state.view === "ranking" ? seg("metric", metrics.map((m) => [m, cap(m)]))
        : state.view === "efficiency" ? seg("axis", [["cost", "Cost"], ["latency", "Latency"]]) : "";
      if (state.view === "ranking" && keepRanking) {
        // Re-order in place so the rows glide to their new rank.
        const fresh = document.createElement("div");
        fresh.innerHTML = ranking(task, task.leaderboard, state.metric);
        const next = fresh.firstElementChild, cur = chart.querySelector(".sm-x-ranking");
        [...cur.querySelectorAll(".sm-x-rrow")].forEach((row, i) => {
          const n = next.querySelectorAll(".sm-x-rrow")[i];
          row.style.transform = n.style.transform;
          row.dataset.tip = n.dataset.tip;
          row.querySelector(".sm-x-rrank").textContent = n.querySelector(".sm-x-rrank").textContent;
          row.querySelector(".sm-x-rfill").style.setProperty("--w", n.querySelector(".sm-x-rfill").style.getPropertyValue("--w"));
          row.querySelector(".sm-x-rval").textContent = n.querySelector(".sm-x-rval").textContent;
        });
        cur.querySelector(".sm-x-rref-wrap").innerHTML = next.querySelector(".sm-x-rref-wrap").innerHTML;
        return;
      }
      chart.innerHTML = state.view === "ranking" ? ranking(task, task.leaderboard, state.metric)
        : state.view === "heatmap" ? heatmap(task, task.leaderboard)
        : state.view === "tasks" ? perTask(task, task.leaderboard)
        : efficiency(task, task.leaderboard, state.axis);
    };
    const drawTable = () => { root.querySelector(".sm-x-table-wrap").innerHTML = table(task, state); };

    root.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || !root.contains(b)) return;
      if (b.dataset.view) {
        state.view = b.dataset.view;
        try { const u = new URL(location.href); u.searchParams.set("view", state.view); history.replaceState(null, "", u); } catch (_) { /* ignore */ }
        drawChart(false);
      }
      else if (b.dataset.metric) { state.metric = b.dataset.metric; drawChart(true); }
      else if (b.dataset.axis) { state.axis = b.dataset.axis; drawChart(false); }
      else if (b.dataset.xsort) {
        const k = b.dataset.xsort;
        state.sort = state.sort && state.sort.key === k ? (state.sort.dir < 0 ? { key: k, dir: 1 } : null) : { key: k, dir: -1 };
        drawTable();
        root.querySelector(`[data-xsort="${k}"]`).focus({ preventScroll: true });
      }
    });
    root.querySelector(".sm-x-search").addEventListener("input", (e) => { state.query = e.target.value; drawTable(); });
    bindTips(root);
    drawChart(false);
    drawTable();
  }

  window.SMSuite = { render };
})();
