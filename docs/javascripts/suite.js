// Dashboard for a task suite (docs/data/leaderboard.json, task.kind === "suite").
// leaderboard.js calls SMSuite.render(container, task) and SMSuite stays inside
// that container. Single-task (archive) pages keep the classic view.
//
// A suite has no single ranking. Two measures are reported side by side:
// how often a model's design meets every requirement, and how good the designs
// that do are (their mean score). Rows are listed by the first, then the second.
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

  // Measures a row can be read by. `frac` maps the value onto 0-1 for bars and cells.
  const METRICS = {
    gate: { label: "Requirements met", get: (r) => r.gate_pct, fmt: pct, frac: (v) => (v == null ? null : v / 100) },
    quality: { label: "Score when met", get: (r) => r.quality_when_met, fmt: (v) => num(v), frac: (v) => v },
  };
  const levelMetric = (g) => ({ label: `${cap(g)} score`, get: (r) => (r.group_scores || {})[g], fmt: (v) => num(v), frac: (v) => v });
  const metricFor = (key) => METRICS[key] || levelMetric(key);

  // Sequential ramp (one hue, light -> dark) for 0-1 cells; text ink flips on dark steps.
  const RAMP = ["#eef4fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
  const cell = (f) => {
    if (f == null) return 'class="sm-x-cell is-empty"';
    const i = Math.min(RAMP.length - 1, Math.floor(clamp01(f) * RAMP.length));
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
  const rowTip = (r, extra = []) => tipHtml(esc(name(r)), [
    ["Requirements met", pct(r.gate_pct)], ["Score when met", num(r.quality_when_met)],
    ...extra, ...(effort(r) ? [["Reasoning", effort(r)]] : []),
  ]);

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

  const best = (rows, get) => rows.reduce((a, r) => (get(r) != null && (a == null || get(r) > get(a)) ? r : a), null);

  function kpis(task, rows, featured, base) {
    const s = task.suite;
    const refs = s.groups.map((g) => s.reference_mean_score[g]).filter((v) => v != null);
    const ceiling = refs.length ? refs.reduce((a, b) => a + b, 0) / refs.length : null;
    const mostMet = best(rows, (r) => r.gate_pct);
    const bestQ = best(rows, (r) => r.quality_when_met);
    const tile = (label, value, sub, accent) =>
      `<div class="sm-x-kpi${accent ? " is-accent" : ""}"><span class="sm-x-kpi-label">${label}</span><span class="sm-x-kpi-value">${value}</span><span class="sm-x-kpi-sub">${sub}</span></div>`;
    return `<div class="sm-x-kpis">` +
      tile("Tasks", s.n_tasks, `${s.groups.map(cap).join(" · ")} · one answer each`) +
      tile("Models", rows.length, "evaluated zero-shot, no ranking") +
      (mostMet ? tile("Most requirements met", pct(mostMet.gate_pct), esc(name(mostMet))) : "") +
      (bestQ ? tile("Best score when met", num(bestQ.quality_when_met, 2), esc(name(bestQ))) : "") +
      (featured && base ? tile("Effect of fine-tuning",
        `${num(base.quality_when_met, 2)} → ${num(featured.quality_when_met, 2)}`,
        `score when met; requirements met ${pct(base.gate_pct)} → ${pct(featured.gate_pct)}`, true) : "") +
      (ceiling != null ? tile("Reference design", num(ceiling, 2), "meets every requirement; mean score") : "") +
      `</div>`;
  }

  function spotlight(task, featured, base, rival) {
    if (!featured) return "";
    const s = task.suite;
    const series = [[featured, "is-featured"], [base, "is-base"], [rival, "is-other"]].filter(([r]) => r);
    const legend = series.map(([r, c]) => `<span><i class="sm-x-sw ${c}"></i>${esc(name(r))}${r === rival ? " <small>most requirements met</small>" : ""}</span>`).join("") +
      `<span><i class="sm-x-sw is-ref"></i>reference design</span>`;
    const groups = s.groups.map((g) => {
      const ref = s.reference_mean_score[g];
      const bars = series.map(([r, c]) => {
        const v = (r.group_scores || {})[g];
        const gate = (r.group_gate_pct || {})[g];
        return `<div class="sm-x-sbar" tabindex="0" data-tip="${tipHtml(esc(name(r)), [[`${cap(g)} score`, num(v)], ["Requirements met", pct(gate)], ["Reference", num(ref)]])}">
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
        <p class="sm-x-muted">${esc(d.note || "")}. Trained against this referee on other heat-exchanger tasks; none of these 30 tasks was used to train it.</p>
        <div class="sm-x-spot-stats">
          <div><b>${pct(featured.gate_pct)}</b><span>requirements met</span></div>
          <div><b>${num(featured.quality_when_met, 2)}</b><span>score when met</span></div>
          <div><b>${featured.distinct_designs}</b><span>distinct designs</span></div>
        </div>
        <p class="sm-x-muted">Its working designs are the most cost-efficient in the suite, but it meets the requirements less often than most models: it sizes close to the duty target and sometimes falls just short.</p>
        ${d.url ? `<a class="sm-x-btn" href="${esc(d.url)}" target="_blank" rel="noopener">View on Hugging Face ↗</a>` : ""}
      </div>
      <div class="sm-x-spot-chart"><p class="sm-x-chart-title">Mean score per difficulty level</p><div class="sm-x-legend">${legend}</div>${groups}</div>
    </section>`;
  }

  // What a reader must know before comparing the featured model with the rest.
  function caveats(task, featured) {
    if (!featured) return "";
    const gates = task.suite.groups.map((g) => [g, (featured.group_gate_pct || {})[g]]);
    const passed = gates.filter(([, v]) => v).map(([g]) => g);
    const where = passed.length === 1 ? `only on ${passed[0]} tasks` : `on ${passed.join(" and ")} tasks`;
    const base = task.leaderboard.find((r) => role(r) === "base");
    return `<aside class="sm-x-caveat" aria-label="Read before comparing">
      <p class="sm-x-eyebrow">Read before comparing</p>
      <ul>
        <li><b>Different tasks behind the two scores.</b> ${esc(name(featured))} met the requirements ${where}; the other models also met them on harder tasks. Its higher score when met is measured on the easiest tasks.</li>
        <li><b>It knows this referee.</b> It was trained against the same simulator and cost model on other tasks. The other models answer zero-shot: the prompt gives the cost thresholds but not how cost is computed, so they cannot size a design to cost.</li>
        ${base ? `<li><b>Meeting the requirements is not good design on its own.</b> ${esc(name(base))}, the untuned base model, meets them on every easy task by returning nearly the same oversized design for every task; the loose easy limits let it pass, and it earns nothing for cost.</li>` : ""}
        <li><b>The other models are not at their best.</b> They run at their lowest reasoning effort and answer each task once. More reasoning, or the cost model in the prompt, could change these results; both are next.</li>
      </ul>
    </aside>`;
  }

  // ── charts ────────────────────────────────────────────────────────────
  const VIEWS = [["compare", "Compare"], ["tradeoff", "Requirements vs score"], ["heatmap", "Heatmap"], ["tasks", "Task by task"], ["efficiency", "Cost & speed"]];

  // Horizontal bars ordered by the chosen measure; rows glide when it changes.
  // Deliberately no rank numbers: the suite reports measures, not a winner.
  function compare(task, rows, key) {
    const m = metricFor(key);
    const order = [...rows].sort((a, b) => (m.get(b) ?? -1) - (m.get(a) ?? -1));
    const ref = key in METRICS ? null : task.suite.reference_mean_score[key];
    const h = 34;
    const items = rows.map((r) => {
      const v = m.get(r);
      return `<div class="sm-x-rrow ${markClass(r)}" style="transform:translateY(${order.indexOf(r) * h}px)" tabindex="0" data-tip="${rowTip(r, key in METRICS ? [] : [[m.label, m.fmt(v)]])}">
        <span class="sm-x-rname">${esc(name(r))}${effort(r) ? `<small>${esc(effort(r))}</small>` : ""}</span>
        <span class="sm-x-rtrack"><span class="sm-x-rfill" style="--w:${(100 * clamp01(m.frac(v))).toFixed(1)}%"></span></span><span class="sm-x-rval">${m.fmt(v)}</span></div>`;
    }).join("");
    const refLine = ref != null ? `<span class="sm-x-rref" style="--ref:${(100 * clamp01(ref)).toFixed(1)}%"><em>reference ${num(ref, 2)}</em></span>` : "";
    return `<div class="sm-x-ranking" style="height:${rows.length * h}px">${items}<div class="sm-x-rref-wrap">${refLine}</div></div>`;
  }

  function heatmap(task, rows) {
    const s = task.suite;
    const cols = [["gate", "Req. met"], ["quality", "Score when met"], ...s.groups.map((g) => [g, cap(g)])];
    const head = cols.map(([, l]) => `<th scope="col">${l}</th>`).join("");
    const body = rows.map((r) => `<tr class="${markClass(r)}"><th scope="row">${esc(name(r))}</th>` + cols.map(([k, l]) => {
      const m = metricFor(k), v = m.get(r);
      return `<td ${cell(m.frac(v))} tabindex="0" data-tip="${rowTip(r, [[l, m.fmt(v)]])}">${k === "gate" ? pct(v) : num(v, 2)}</td>`;
    }).join("") + `</tr>`).join("");
    const refRow = `<tr class="is-ref"><th scope="row">Reference design</th>` + cols.map(([k]) => {
      if (k === "gate") return `<td ${cell(1)}>100%</td>`;
      const v = k === "quality" ? null : s.reference_mean_score[k];
      return `<td ${cell(v)}>${num(v, 2)}</td>`;
    }).join("") + `</tr>`;
    return `<div class="sm-x-scroll"><table class="sm-x-heat"><thead><tr><th></th>${head}</tr></thead><tbody>${body}${refRow}</tbody></table></div>` + scale();
  }

  function scale() {
    return `<div class="sm-x-scale"><span>0</span>${RAMP.map((c) => `<i style="background:${c}"></i>`).join("")}<span>1 / 100%</span></div>`;
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

  // Shared scatter frame. xTicks/yTicks return [value, label] pairs in data units;
  // with `log`, the x domain is in decades and x values are plotted on log10.
  function scatter(rows, o) {
    const W = 760, H = 380, L = 60, R = 30, T = 18, B = 46;
    const pts = rows.filter((r) => o.xs(r) != null && o.ys(r) != null && (!o.log || o.xs(r) > 0));
    if (!pts.length) return '<p class="sm-x-note">No data for this view.</p>';
    const tx = o.log ? Math.log10 : (v) => v;
    const [x0, x1] = o.xDomain(pts.map((r) => tx(o.xs(r))));
    const [y0, y1] = o.yDomain;
    const sx = (v) => L + ((tx(v) - x0) / (x1 - x0)) * (W - L - R);
    const sy = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    let g = "";
    o.xTicks(x0, x1).forEach(([v, l]) => { g += `<line class="sm-x-grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H - B}"/><text class="sm-x-axis" x="${sx(v)}" y="${H - B + 18}" text-anchor="middle">${esc(l)}</text>`; });
    o.yTicks.forEach(([v, l]) => { g += `<line class="sm-x-grid" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="sm-x-axis" x="${L - 8}" y="${sy(v) + 4}" text-anchor="end">${esc(l)}</text>`; });
    g += `<text class="sm-x-axis-title" x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">${esc(o.xLabel)}</text>` +
      `<text class="sm-x-axis-title" transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">${esc(o.yLabel)}</text>`;
    // Models with identical values share one point; its tooltip lists them all
    // and a count sits beside it, so no model hides behind another.
    const groups = new Map();
    pts.forEach((r) => {
      const k = `${Math.round(sx(o.xs(r)))},${Math.round(sy(o.ys(r)))}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    });
    const used = [];
    const dots = [...groups.values()].map((grp) => {
      const lead = grp.find((r) => role(r) === "featured") || grp.find((r) => role(r) === "base") || grp[0];
      const cx = sx(o.xs(lead)), cy = sy(o.ys(lead));
      const tipAttr = grp.length === 1 ? o.tipFor(lead)
        : tipHtml(`${grp.length} models`, grp.map((r) => [esc(name(r)), ""]).concat([["Requirements met", pct(lead.gate_pct)], ["Score when met", num(lead.quality_when_met)]]));
      const count = grp.length > 1 ? `<text class="sm-x-dcount" x="${cx}" y="${cy + 20}" text-anchor="middle">×${grp.length}</text>` : "";
      const labelled = grp.filter((r) => o.label(r));
      let lbl = "";
      if (labelled.length) {
        // Put the label above the point, or below it when another label sits close by.
        const near = used.some(([ux, uy]) => Math.abs(ux - cx) < 150 && Math.abs(uy - (cy - 10)) < 14);
        const ly = near ? cy + (grp.length > 1 ? 34 : 22) : cy - 10;
        used.push([cx, ly]);
        lbl = `<text class="sm-x-dlabel" x="${cx + 9}" y="${ly}">${esc(labelled.map(name).join(", "))}</text>`;
      }
      return `<g class="sm-x-pt ${markClass(lead)}" tabindex="0" data-tip="${tipAttr}"><circle cx="${cx}" cy="${cy}" r="14" class="sm-x-hit"/><circle cx="${cx}" cy="${cy}" r="6"/>${count}${lbl}</g>`;
    }).join("");
    const extra = (o.markers || []).map((m) => {
      const cx = sx(m.x), cy = sy(m.y);
      return `<g class="sm-x-ref-pt" tabindex="0" data-tip="${tipHtml(esc(m.label), m.rows)}"><rect x="${cx - 6}" y="${cy - 6}" width="12" height="12" transform="rotate(45 ${cx} ${cy})"/><text class="sm-x-dlabel" x="${cx - 12}" y="${cy - 12}" text-anchor="end">${esc(m.label)}</text></g>`;
    }).join("");
    const skipped = rows.length - pts.length;
    return `<svg class="sm-x-scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.yLabel)} against ${esc(o.xLabel)}">${g}${dots}${extra}</svg>` +
      (skipped ? `<p class="sm-x-note">${o.note(skipped)}</p>` : "");
  }

  const steps = (a, b, step, f) => { const out = []; for (let v = a; v <= b + 1e-9; v += step) out.push([v, f(v)]); return out; };

  function tradeoff(task, rows) {
    const mostMet = best(rows, (r) => r.gate_pct);
    const refs = task.suite.groups.map((g) => task.suite.reference_mean_score[g]).filter((v) => v != null);
    const refMean = refs.length ? refs.reduce((a, b) => a + b, 0) / refs.length : null;
    return `<p class="sm-x-note">Two separate measures: how often a model's design meets every requirement (right is better), and what its working designs score (up is better). The reference design meets every requirement on every task.</p>` +
      scatter(rows, {
        xs: (r) => r.gate_pct, ys: (r) => r.quality_when_met,
        xLabel: "Requirements met (share of tasks)", yLabel: "Score when met (mean score of working designs)",
        xDomain: () => [0, 100], yDomain: [0, 1],
        xTicks: (a, b) => steps(a, b, 20, (v) => `${v}%`), yTicks: steps(0, 1, 0.2, (v) => v.toFixed(1)),
        label: (r) => role(r) || r === mostMet,
        markers: refMean == null ? [] : [{ x: 100, y: refMean, label: "Reference design", rows: [["Requirements met", "100%"], ["Mean score", num(refMean)]] }],
        note: (n) => `${n} model${n > 1 ? "s" : ""} without a working design not shown.`,
        tipFor: (r) => rowTip(r),
      });
  }

  function efficiency(task, rows, axis) {
    const xs = (r) => (axis === "cost" ? (r.cost_usd != null && r.runs ? r.cost_usd / r.runs : null) : r.p50_latency_s);
    const mostMet = best(rows, (r) => r.gate_pct);
    return scatter(rows, {
      xs, ys: (r) => r.gate_pct, log: true,
      xLabel: axis === "cost" ? "Cost per task (log scale)" : "Median latency per answer (log scale)",
      yLabel: "Requirements met",
      xDomain: (vals) => { const lo = Math.floor(Math.min(...vals)), hi = Math.ceil(Math.max(...vals)); return [lo, hi === lo ? hi + 1 : hi]; },
      yDomain: [0, 100],
      xTicks: (a, b) => steps(a, b, 1, (e) => e).map(([e]) => {
        const v = 10 ** e;
        return [v, axis === "cost" ? (v < 0.01 ? `$${v}` : `$${v.toFixed(2)}`) : `${v} s`];
      }),
      yTicks: steps(0, 100, 20, (v) => `${v}%`),
      label: (r) => role(r) || r === mostMet,
      note: (n) => `${n} model${n > 1 ? "s" : ""} without ${axis === "cost" ? "a recorded price" : "latency data"} not shown.`,
      tipFor: (r) => rowTip(r, [[axis === "cost" ? "Cost per task" : "Median latency", axis === "cost" ? `$${xs(r).toFixed(4)}` : `${xs(r).toFixed(1)} s`], ["Total cost", usd(r.cost_usd)]]),
    });
  }

  // ── table ─────────────────────────────────────────────────────────────
  const COLS = [
    ["gate_pct", "Req. met", "gatebar"], ["quality_when_met", "Score when met", "score"],
    ["group:easy", "Easy", "heat"], ["group:medium", "Medium", "heat"], ["group:hard", "Hard", "heat"],
    ["valid_pct", "Valid", "pct"], ["cost_usd", "Cost", "usd"], ["p50_latency_s", "Latency", "sec"],
  ];
  const colVal = (r, k) => (k.startsWith("group:") ? (r.group_scores || {})[k.slice(6)] : r[k]);

  function table(task, state) {
    const q = state.query.trim().toLowerCase();
    let rows = task.leaderboard.filter((r) => [name(r), r.model, r.model_id].some((v) => String(v || "").toLowerCase().includes(q)));
    if (state.sort) rows = [...rows].sort((a, b) => state.sort.dir * ((colVal(a, state.sort.key) ?? -1) - (colVal(b, state.sort.key) ?? -1)));
    const head = COLS.map(([k, l]) => {
      const on = state.sort && state.sort.key === k;
      return `<th scope="col" aria-sort="${on ? (state.sort.dir < 0 ? "descending" : "ascending") : "none"}"><button type="button" data-xsort="${k}">${l}${on ? (state.sort.dir < 0 ? " ↓" : " ↑") : ""}</button></th>`;
    }).join("");
    const body = rows.map((r) => {
      const chips = (role(r) === "featured" ? '<span class="sm-x-chip is-brand">Fine-tuned</span>' : "") +
        (effort(r) ? `<span class="sm-x-chip">reasoning: ${esc(effort(r))}</span>` : "") +
        (r.complete === false ? `<span class="sm-x-chip is-warn">${r.tasks_done}/${task.suite.n_tasks} tasks</span>` : "");
      const link = r.display && r.display.url ? `<a href="${esc(r.display.url)}" target="_blank" rel="noopener">${esc(name(r))}</a>` : esc(name(r));
      const cells = COLS.map(([k, , kind]) => {
        const v = colVal(r, k);
        if (kind === "gatebar") return `<td class="n"><span class="sm-x-meanbar"><i style="--w:${(v || 0).toFixed(1)}%"></i></span><b>${pct(v)}</b></td>`;
        if (kind === "score") return `<td class="n"><b>${num(v)}</b></td>`;
        if (kind === "heat") return `<td ${cell(v).replace('class="', 'class="n ')}>${num(v)}</td>`;
        if (kind === "pct") return `<td class="n">${pct(v)}</td>`;
        if (kind === "usd") return `<td class="n">${usd(v)}</td>`;
        return `<td class="n">${v == null ? "–" : `${v.toFixed(1)} s`}</td>`;
      }).join("");
      return `<tr class="${markClass(r)}"><td><div class="sm-x-model">${link}${chips}</div>${r.display && r.display.note ? `<div class="sm-x-sub">${esc(r.display.note)}</div>` : ""}</td>${cells}</tr>`;
    }).join("");
    return `<div class="sm-x-scroll"><table class="sm-x-table"><thead><tr><th>Model</th>${head}</tr></thead><tbody>${body ||
      `<tr><td colspan="${COLS.length + 1}" class="sm-x-empty">No model matches.</td></tr>`}</tbody></table></div>`;
  }

  // ── mount ─────────────────────────────────────────────────────────────
  function render(root, task) {
    const rows = task.leaderboard;
    const featured = rows.find((r) => role(r) === "featured");
    const base = rows.find((r) => role(r) === "base");
    const rival = best(rows.filter((r) => !role(r)), (r) => r.gate_pct);
    const state = { view: "compare", metric: "gate", axis: "cost", sort: null, query: "" };
    try {
      // ?view=heatmap etc. opens a chart directly, so a view can be linked.
      const asked = new URLSearchParams(location.search).get("view");
      if (VIEWS.some(([id]) => id === asked)) state.view = asked;
    } catch (_) { /* no URL API: keep the default view */ }
    const metricKeys = [["gate", "Requirements met"], ["quality", "Score when met"], ...task.suite.groups.map((g) => [g, cap(g)])];

    root.innerHTML = header(task) + kpis(task, rows, featured, base) + spotlight(task, featured, base, rival) + caveats(task, featured) +
      `<section class="sm-x-panel" aria-label="Interactive charts">
        <div class="sm-x-tabs" role="tablist">${VIEWS.map(([id, l]) => `<button type="button" role="tab" data-view="${id}">${l}</button>`).join("")}</div>
        <div class="sm-x-controls"></div><div class="sm-x-chart"></div>
      </section>
      <section class="sm-x-panel" aria-label="All results">
        <div class="sm-x-panel-head"><h3>All results</h3><input type="search" class="sm-x-search" placeholder="Find a model…" aria-label="Find a model"></div>
        <div class="sm-x-table-wrap"></div>
        <p class="sm-x-note"><b>Req. met:</b> share of the 30 answers whose design reaches the duty target and stays inside both pressure-drop limits. <b>Score when met:</b> mean score of those answers (0.3 for a design that only meets the requirements, up to 1 for a cheap, well-engineered one). <b>Easy / Medium / Hard:</b> mean score per level, failed designs counting as 0. There is no overall ranking; rows are listed by requirements met, then score when met. Select a column to sort.</p>
      </section>`;

    const chart = root.querySelector(".sm-x-chart"), controls = root.querySelector(".sm-x-controls");
    const seg = (key, opts) => `<div class="sm-x-seg" role="group">${opts.map(([v, l]) => `<button type="button" data-${key}="${v}" aria-pressed="${state[key] === v}">${l}</button>`).join("")}</div>`;
    const drawChart = (glide) => {
      root.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === state.view)));
      controls.innerHTML = state.view === "compare" ? seg("metric", metricKeys)
        : state.view === "efficiency" ? seg("axis", [["cost", "Cost"], ["latency", "Latency"]]) : "";
      if (state.view === "compare" && glide && chart.querySelector(".sm-x-ranking")) {
        // Re-order in place so the rows glide to their new position.
        const fresh = document.createElement("div");
        fresh.innerHTML = compare(task, rows, state.metric);
        const next = fresh.firstElementChild, cur = chart.querySelector(".sm-x-ranking");
        const nextRows = next.querySelectorAll(".sm-x-rrow");
        cur.querySelectorAll(".sm-x-rrow").forEach((row, i) => {
          const n = nextRows[i];
          row.style.transform = n.style.transform;
          row.dataset.tip = n.dataset.tip;
          row.querySelector(".sm-x-rfill").style.setProperty("--w", n.querySelector(".sm-x-rfill").style.getPropertyValue("--w"));
          row.querySelector(".sm-x-rval").textContent = n.querySelector(".sm-x-rval").textContent;
        });
        cur.querySelector(".sm-x-rref-wrap").innerHTML = next.querySelector(".sm-x-rref-wrap").innerHTML;
        return;
      }
      chart.innerHTML = state.view === "compare" ? compare(task, rows, state.metric)
        : state.view === "tradeoff" ? tradeoff(task, rows)
        : state.view === "heatmap" ? heatmap(task, rows)
        : state.view === "tasks" ? perTask(task, rows)
        : efficiency(task, rows, state.axis);
    };
    const drawTable = () => { root.querySelector(".sm-x-table-wrap").innerHTML = table(task, state); };

    root.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || !root.contains(b)) return;
      if (b.dataset.view) {
        state.view = b.dataset.view;
        try { const u = new URL(location.href); u.searchParams.set("view", state.view); history.replaceState(null, "", u); } catch (_) { /* ignore */ }
        drawChart(false);
      } else if (b.dataset.metric) { state.metric = b.dataset.metric; drawChart(true); }
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
