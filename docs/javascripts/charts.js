// Dependency-free, task-scoped benchmark charts. Only exported aggregates are used.
(function () {
  "use strict";
  const esc = (value) => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const colors = ["#c87846", "#419fa9", "#748bda", "#b580bb", "#91a852", "#d08891", "#719e85", "#a89173"];
  const views = {
    scores: "Score comparison", reliability: "Validity & requirements", distribution: "Score distribution",
    efficiency: "Cost & speed", outcomes: "Run outcomes",
  };
  const statuses = {
    success: ["Simulated", "#419f89"], drc_error: ["Design-rule error", "#cf9350"],
    schema_error: ["Schema error", "#af83c2"], simulation_error: ["Simulation error", "#cf7073"],
    parse_error: ["Parse error", "#7f91c2"], empty_response: ["Empty response", "#97a169"],
    token_limit: ["Token limit (not run)", "#8b96a5"], client_error: ["Client error (not run)", "#6d7c8b"],
  };
  const num = (v, digits = 3) => v == null ? "Unavailable" : Number(v).toLocaleString("en-US", {maximumFractionDigits: digits});
  const money = v => v == null ? "Unavailable" : `$${num(v, 6)}`;
  const text = (x, y, value, attrs = "") => `<text x="${x}" y="${y}" ${attrs}>${esc(value)}</text>`;
  const line = (x1, y1, x2, y2, cls = "sm-chart-grid") => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="${cls}"/>`;
  const label = (row, y) => {
    const [name, effort] = row.model.split("__reasoning-");
    return text(12, y - 3, name.length > 31 ? name.slice(0, 29) + "…" : name, 'class="sm-chart-label"') +
      text(12, y + 14, effort ? `reasoning: ${effort}` : (row.provider || ""), 'class="sm-chart-small"');
  };
  const mark = (detail, shape) => `<g class="sm-chart-mark" tabindex="0" role="img" aria-label="${esc(detail)}" data-detail="${esc(detail)}"><title>${esc(detail)}</title>${shape}</g>`;
  const rect = (x, y, w, h, color) => `<rect x="${x}" y="${y}" width="${Math.max(0, w)}" height="${h}" rx="2" fill="${color}"/>`;
  const legend = items => `<div class="sm-chart-legend">${items.map(([name,color])=>`<span><i style="background:${color}"></i>${esc(name)}</span>`).join("")}</div>`;
  function svg(body, height, title) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="${height}" viewBox="0 0 900 ${height}" aria-label="${esc(title)}" role="group">` +
      `<title>${esc(title)}</title><style>text{fill:#233748;font:13px sans-serif}.sm-chart-small{font-size:11px}.sm-chart-grid{stroke:#97a7b5;stroke-opacity:.25}.sm-chart-whisker{stroke:#8193a3;stroke-width:2}</style><rect width="900" height="${height}" fill="white"/>${body}</svg>`;
  }
  function ticks(max, height, format = v => num(v)) {
    return Array.from({length:5}, (_,i) => {
      const x = 250 + i * 150;
      return line(x, 20, x, height - 28) + text(x, height - 9, format(max * i / 4), 'text-anchor="middle" class="sm-chart-small"');
    }).join("");
  }
  function table(headers, rows) {
    return `<details class="sm-chart-data"><summary>View chart data</summary><div class="sm-lb-scroll" tabindex="0" role="region" aria-label="Chart data"><table><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
  }
  function bars(rows, reliability) {
    const series = reliability ? [["valid_pct","Valid design",colors[1]],["requirements_pct","Requirements met",colors[0]]] :
      [["mean_score","Mean score",colors[0]],["best_score","Best score",colors[1]]];
    const max = reliability ? 100 : 1, height = rows.length * 60 + 55;
    let body = ticks(max, height, v => reliability ? `${v}%` : num(v,2));
    rows.forEach((row,i) => {
      const y = 40 + i * 60;
      body += label(row,y);
      series.forEach(([key,name,color],j) => {
        const v = row[key];
        const value = v == null ? "Unavailable" : num(v) + (reliability ? "%" : "");
        const yy = y - 17 + j * 19;
        body += mark(`${row.model} · ${name}: ${value} · ${row.runs} runs`,
          rect(250, yy, v == null ? 0 : 600*v/max, 13, color) + text(860, yy+11, value, 'class="sm-chart-small"'));
      });
    });
    return {
      plot: svg(body,height,reliability ? views.reliability : views.scores),
      legend: legend(series.map(([,n,c])=>[n,c])),
      note: reliability ? "Both percentages use all recorded attempts. A simulated design may still miss the task requirements." :
        "Mean score excludes client errors and token-limit stops; failed designs count as zero. Best score is the highest recorded score. Small run counts can make comparisons unstable.",
      data: table(["Model",...series.map(([,n])=>n),"Runs"], rows.map(r=>[r.model,...series.map(([k])=>num(r[k])),r.runs])),
    };
  }
  function boxes(rows) {
    const height = rows.length * 60 + 55;
    let body = ticks(1,height);
    rows.forEach((row,i)=>{
      const y = 40+i*60, d = row.charts?.score_distribution;
      body += label(row,y);
      if (!d) { body += text(260,y,"No scored attempts"); return; }
      const x = v => 250 + 600*v;
      const detail = `${row.model} · ${d.count} scored attempts · min ${num(d.min)}, Q1 ${num(d.q1)}, median ${num(d.median)}, Q3 ${num(d.q3)}, max ${num(d.max)}`;
      body += mark(detail, line(x(d.min),y,x(d.max),y,"sm-chart-whisker") +
        line(x(d.min),y-9,x(d.min),y+9,"sm-chart-whisker") + line(x(d.max),y-9,x(d.max),y+9,"sm-chart-whisker") +
        rect(x(d.q1),y-13,Math.max(2,x(d.q3)-x(d.q1)),26,colors[1]) +
        `<line x1="${x(d.median)}" y1="${y-14}" x2="${x(d.median)}" y2="${y+14}" stroke="#fff" stroke-width="3"/>` + text(860,y+4,`n=${d.count}`,'class="sm-chart-small"'));
    });
    return {plot:svg(body,height,views.distribution),legend:"",
      note:"Box: 25th–75th percentile. White line: median. Whiskers: minimum and maximum (not Tukey outlier fences). Inclusive linear quartiles; failed designs are included as zero, client errors and token-limit stops are excluded.",
      data:table(["Model","Scored attempts","Min","Q1","Median","Q3","Max"],rows.map(r=>{
        const d=r.charts?.score_distribution;
        return [r.model,d?.count || 0,...["min","q1","median","q3","max"].map(k=>num(d?.[k]))];
      }))};
  }
  function scatter(rows, axis) {
    const cost = axis === "cost", xLabel = cost ? "Mean cost per recorded run (USD)" : "Median latency (seconds)";
    const xValue = r => cost ? r.charts?.mean_cost_usd : r.p50_latency_s;
    const usable = rows.filter(r=>xValue(r)!=null && r.mean_score!=null);
    if (!usable.length) return {plot:"",legend:"",note:`No models have both a mean score and ${cost ? "complete cost coverage" : "recorded latency"} for this selection.`,data:""};
    const max = Math.max(...usable.map(xValue),cost ? 0.000001 : 1)*1.12;
    let body = "";
    for (let i=0;i<=4;i++) {
      const x=80+i*180,y=360-i*80;
      body+=line(x,40,x,360)+text(x,384,cost?money(max*i/4):num(max*i/4,1),'text-anchor="middle"') +
        line(80,y,800,y)+text(65,y+5,num(i/4,2),'text-anchor="end"');
    }
    body+=text(440,420,xLabel,'text-anchor="middle"')+text(18,200,"Mean score",'transform="rotate(-90 18 200)" text-anchor="middle"');
    usable.forEach(r=>{
      const i=rows.indexOf(r),x=80+720*xValue(r)/max,y=360-320*r.mean_score;
      body+=mark(`${r.model} · Mean score ${num(r.mean_score)} · ${xLabel}: ${cost?money(xValue(r)):num(xValue(r),1)} · ${r.runs} runs`,
        `<circle cx="${x}" cy="${y}" r="9" fill="${colors[i%colors.length]}" stroke="var(--sm-surface, white)" stroke-width="2"/>`+text(x+13,y-10,i+1,'class="sm-chart-label"'));
    });
    return {plot:svg(body,440,`Mean score vs ${xLabel}`),legend:legend(usable.map(r=>[`${rows.indexOf(r)+1}. ${r.model}`,colors[rows.indexOf(r)%colors.length]])),
      note:`Each point is one model configuration. Higher and further left means a higher mean score at lower ${cost?"average cost":"median latency"}. ${rows.length-usable.length} model(s) omitted for missing data. ${cost?"Cost includes all recorded runs, including failed or interrupted runs; models with any unknown run cost are omitted.":"Latency uses positive recorded measurements; missing latency is not zero."}`,
      data:table(["Model","Mean score",xLabel,"Runs","Runs with known cost"],rows.map(r=>[r.model,num(r.mean_score),cost?money(xValue(r)):num(xValue(r),1),r.runs,r.charts?.priced_runs ?? "Unavailable"]))};
  }
  function outcomes(rows) {
    const present = [...new Set(rows.flatMap(r=>Object.keys(r.charts?.statuses || {})))];
    present.sort((a,b)=>a==="success"?-1:b==="success"?1:a.localeCompare(b));
    const height=rows.length*60+55;
    let body=ticks(100,height,v=>`${v}%`);
    rows.forEach((r,i)=>{
      const y=40+i*60;
      body+=label(r,y);
      if(!r.charts?.statuses) {body+=text(260,y,"Outcome data unavailable");return;}
      let x=250;
      present.forEach(s=>{
        const count=r.charts.statuses[s] || 0, w=r.runs ? 600*count/r.runs : 0;
        if(count) body+=mark(`${r.model} · ${statuses[s]?.[0] || s}: ${count}/${r.runs} runs (${num(100*count/r.runs,1)}%)`,rect(x,y-12,w,24,statuses[s]?.[1] || "#83909a"));
        x+=w;
      });
      body+=text(860,y+4,`n=${r.runs}`,'class="sm-chart-small"');
    });
    return {plot:svg(body,height,views.outcomes),legend:legend(present.map(s=>statuses[s] || [s,"#83909a"])),
      note:"Every recorded run appears once. Simulated means the physics evaluation completed, not that all requirements were met. Client errors and token-limit stops are shown separately from design failures.",
      data:table(["Model",...present.map(s=>statuses[s]?.[0] || s)],rows.map(r=>[r.model,...present.map(s=>r.charts?.statuses?.[s] || 0)]))};
  }
  function mount(root, task) {
    const selected=new Set(task.leaderboard.map(r=>r.model));
    let view="scores",axis="cost";
    root.innerHTML=`<div class="sm-chart-heading"><div><p class="sm-eyebrow">Compare models / ${esc(task.slug)}</p><h3>Explore the results</h3></div></div>`+
      `<div class="sm-chart-controls"><label>Chart<select id="sm-chart-view">${Object.entries(views).map(([v,n])=>`<option value="${v}">${n}</option>`).join("")}</select></label>`+
      `<label id="sm-chart-axis-label" hidden>Horizontal axis<select id="sm-chart-axis"><option value="cost">Cost per run</option><option value="latency">Median latency</option></select></label>`+
      `<button type="button" id="sm-chart-download">Download SVG</button></div>`+
      `<details class="sm-chart-models"><summary>Choose models <span id="sm-chart-selected"></span></summary><div class="sm-chart-selection"><button type="button" data-models="all">Select all</button><button type="button" data-models="none">Clear selection</button></div><fieldset><legend class="sm-sr-only">Models included in charts</legend>${task.leaderboard.map((r,i)=>`<label><input type="checkbox" data-model="${i}" checked> <span>${esc(r.model)}</span></label>`).join("")}</fieldset></details>`+
      `<div class="sm-chart-content"></div><p class="sm-chart-tooltip" role="status" aria-live="polite">Hover over a mark or focus it with Tab to inspect its values.</p>`;
    const content=root.querySelector(".sm-chart-content");
    const draw=()=>{
      const rows=task.leaderboard.filter(r=>selected.has(r.model));
      root.querySelector("#sm-chart-selected").textContent=`(${rows.length}/${task.leaderboard.length})`;
      root.querySelector("#sm-chart-axis-label").hidden=view!=="efficiency";
      const result=!rows.length ? {note:"Select at least one model to compare.",plot:"",legend:"",data:""} :
        view==="distribution"?boxes(rows):view==="efficiency"?scatter(rows,axis):view==="outcomes"?outcomes(rows):bars(rows,view==="reliability");
      content.innerHTML=`<p class="sm-chart-note">${esc(result.note)}</p>${result.legend}<div class="sm-chart-scroll" tabindex="0" role="region" aria-label="${views[view]}; scroll horizontally on small screens">${result.plot}</div>${result.data}`;
      root.querySelector("#sm-chart-download").disabled=!result.plot;
      root.querySelector(".sm-chart-tooltip").textContent="Hover over a mark or focus it with Tab to inspect its values.";
    };
    root.addEventListener("change",event=>{
      if(event.target.id==="sm-chart-view") view=event.target.value;
      else if(event.target.id==="sm-chart-axis") axis=event.target.value;
      else if(event.target.matches("input[data-model]")) {
        const model=task.leaderboard[Number(event.target.dataset.model)].model;
        event.target.checked?selected.add(model):selected.delete(model);
      } else return;
      draw();
    });
    root.addEventListener("click",event=>{
      const choice=event.target.closest("button[data-models]");
      if(choice) {
        const all=choice.dataset.models==="all";
        selected.clear();
        root.querySelectorAll("input[data-model]").forEach(input=>{
          input.checked=all;
          if(all) selected.add(task.leaderboard[Number(input.dataset.model)].model);
        });
        draw();
      }
      if(event.target.id==="sm-chart-download") {
        const element=content.querySelector("svg");
        if(!element) return;
        const url=URL.createObjectURL(new Blob([element.outerHTML],{type:"image/svg+xml"}));
        const a=document.createElement("a");a.href=url;a.download=`${task.slug}-${view}${view==="efficiency"?"-"+axis:""}.svg`;a.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      }
    });
    for(const name of ["pointerover","focusin"]) root.addEventListener(name,event=>{
      const point=event.target.closest("[data-detail]");
      if(point) root.querySelector(".sm-chart-tooltip").textContent=point.dataset.detail;
    });
    draw();
  }
  window.SMBenchCharts={mount};
})();
