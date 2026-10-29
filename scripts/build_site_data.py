"""Export benchmark records as the JSON the documentation site renders.

The Streamlit dashboard needs a running server, so the public site ships a
static leaderboard instead. This script reads the same ``results/`` records and
applies the dashboard's definitions (see ``scripts/dashboard.py``) so both show
the same numbers:

- one leaderboard per task, never pooled across tasks, because every task pins
  its own simulator and score version;
- scores average every attempt except client errors and token-limit stops,
  which record that a run did not happen rather than that a model failed;
- "requirements met" counts successful designs that reach the duty target and
  stay inside both pressure-drop limits, as a share of all attempts.

Only aggregates are written. Raw responses, prompts, and designs stay in the
repository records. The script uses the standard library only, so the site
build does not need the benchmark dependencies.

Usage: python scripts/build_site_data.py [--results results] [--out docs/data/leaderboard.json]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRACKS = {"zero_shot": "Zero-shot", "feedback_driven": "Feedback-driven"}
RUN_SOURCES = ("api_runs", "manual_runs")

# Statuses that mean the run never produced an answer to judge.
NOT_RUN = {"client_error", "token_limit"}
NO_JSON = {"client_error", "empty_response", "parse_error", "token_limit"}

# Mirrors PIPELINE_STAGES in scripts/dashboard.py: each stage removes the
# statuses that stopped a run at that point.
PIPELINE_STAGES = (
    ("Responded", ("client_error", "empty_response", "token_limit")),
    ("Parsed as JSON", ("parse_error",)),
    ("Schema valid", ("schema_error",)),
    ("DRC passed", ("drc_error",)),
    ("Simulated", ("simulation_error",)),
)


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(mapping: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        number = _number(mapping.get(key))
        if number is not None:
            return number
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pa(metrics: Dict[str, Any], name: str) -> Optional[float]:
    pa = _first(metrics, (f"{name}_Pa",))
    if pa is None:
        kpa = _first(metrics, (f"{name}_kPa",))
        pa = kpa * 1000.0 if kpa is not None else None
    return pa


def _heat_w(metrics: Dict[str, Any]) -> Optional[float]:
    watts = _first(metrics, ("heat_duty_W", "heat_duty"))
    if watts is None:
        kw = _first(metrics, ("heat_duty_kW",))
        watts = kw * 1000.0 if kw is not None else None
    return watts


def _meets_requirements(record: Dict[str, Any], task: Dict[str, Any]) -> bool:
    """Duty target and both pressure-drop limits, record values first."""
    metrics = _as_dict(record.get("metrics"))
    params = _as_dict(record.get("task_params"))

    def limit(key: str) -> Optional[float]:
        value = _number(params.get(key))
        return value if value is not None else _number(task.get(key))

    checks = [
        (_heat_w(metrics), limit("target_heat_duty"), lambda v, l: v >= l),
        (_pa(metrics, "dp_tube"), limit("max_dp_tube"), lambda v, l: v <= l),
        (_pa(metrics, "dp_shell"), limit("max_dp_shell"), lambda v, l: v <= l),
    ]
    applicable = [(v, l, ok) for v, l, ok in checks if l is not None]
    if not applicable:
        return False
    return all(v is not None and ok(v, l) for v, l, ok in applicable)


def _score(record: Dict[str, Any]) -> float:
    score = _number(record.get("total_score"))
    if score is None:
        score = _number(record.get("total_reward"))
    return score if score is not None else 0.0


def _cost(record: Dict[str, Any]) -> Optional[float]:
    cost = _number(record.get("cost_usd"))
    if cost is not None:
        return cost
    pricing = _as_dict(_as_dict(record.get("model_metadata")).get("pricing"))
    prompt, completion = _number(record.get("prompt_tokens")), _number(record.get("completion_tokens"))
    prompt_rate, completion_rate = _number(pricing.get("prompt")), _number(pricing.get("completion"))
    if None in (prompt, completion, prompt_rate, completion_rate):
        return None
    return prompt * prompt_rate + completion * completion_rate


def _mean(values: List[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def _median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _pct(part: int, whole: int) -> Optional[float]:
    return 100.0 * part / whole if whole else None


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _read_records(task_dir: Path) -> List[Dict[str, Any]]:
    records = []
    for source in RUN_SOURCES:
        for path in sorted((task_dir / source).rglob("*.jsonl")):
            with path.open("r", encoding="utf-8-sig") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record["_source"] = "Manual" if source == "manual_runs" else "API"
                    records.append(record)
    return records


def _task_title(task_dir: Path) -> str:
    for name in ("README.md", "notes.md"):
        path = task_dir / name
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith("# "):
                    return line[2:].strip()
    return task_dir.name


def _distribution(values: List[float]) -> Optional[Dict[str, Any]]:
    """Five-number summary; inclusive linear quartiles, whiskers at min/max."""
    if not values:
        return None
    quartiles = statistics.quantiles(values, n=4, method="inclusive") if len(values) > 1 else values * 3
    return dict(zip(
        ("min", "q1", "median", "q3", "max", "count"),
        [*[_round(v) for v in (min(values), *quartiles, max(values))], len(values)],
    ))


def _leaderboard(records: List[Dict[str, Any]], task: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        by_model.setdefault(str(record.get("model_name") or "Unknown"), []).append(record)

    rows = []
    for model, group in by_model.items():
        attempts = len(group)
        scored = [_score(r) for r in group if r.get("status") not in NOT_RUN]
        successes = [r for r in group if r.get("status") == "success"]
        latencies = [
            v / 1000.0 for v in (_number(r.get("latency_ms")) for r in group) if v and v > 0
        ]
        outputs = [v for v in (_number(r.get("completion_tokens")) for r in group) if v is not None]
        costs = [v for v in (_cost(r) for r in group) if v is not None]
        designs = {json.dumps(r.get("design"), sort_keys=True) for r in successes}
        first = group[0]
        reasoning = sorted({str(r.get("reasoning_mode")) for r in group if r.get("reasoning_mode")})
        rows.append({
            "model": model,
            "model_id": first.get("model_id") or model,
            "provider": first.get("provider") or None,
            "reasoning": ", ".join(reasoning) or None,
            "source": ", ".join(sorted({r["_source"] for r in group})),
            "runs": attempts,
            "valid_pct": _round(_pct(len(successes), attempts), 2),
            "requirements_pct": _round(
                _pct(sum(_meets_requirements(r, task) for r in successes), attempts), 2
            ),
            "json_pct": _round(
                _pct(sum(r.get("status") not in NO_JSON for r in group), attempts), 2
            ),
            "mean_score": _round(_mean(scored)),
            "median_score": _round(_median(scored)),
            "best_score": _round(max((_score(r) for r in group), default=None)),
            "distinct_designs": len(designs),
            "p50_latency_s": _round(_median(latencies), 2),
            "mean_output_tokens": _round(_mean(outputs), 0),
            "cost_usd": _round(sum(costs), 4) if costs else None,
            "charts": {
                "score_distribution": _distribution(scored),
                "latency_distribution": _distribution(latencies),
                "priced_runs": len(costs),
                # A partial cost ledger is not comparable with a complete one.
                "mean_cost_usd": _round(_mean(costs), 6) if len(costs) == attempts else None,
                "statuses": {
                    status: sum(str(r.get("status") or "unknown") == status for r in group)
                    for status in sorted({str(r.get("status") or "unknown") for r in group})
                },
            },
        })

    rows.sort(key=lambda row: (
        -(row["mean_score"] if row["mean_score"] is not None else -1),
        -(row["valid_pct"] or 0),
        -(row["best_score"] or 0),
    ))
    return rows


def _funnel(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocked: set = set()
    stages = []
    for stage, statuses in PIPELINE_STAGES:
        blocked |= set(statuses)
        stages.append({
            "stage": stage,
            "runs": sum(r.get("status") not in blocked for r in records),
        })
    return stages


def build(results_root: Path) -> Dict[str, Any]:
    tracks = []
    for track, label in TRACKS.items():
        track_dir = results_root / track
        if not track_dir.is_dir():
            continue
        tasks = []
        for task_dir in sorted(p for p in track_dir.iterdir() if p.is_dir()):
            task_path = task_dir / "task.json"
            records = _read_records(task_dir)
            if not task_path.is_file() or not records:
                continue
            task = json.loads(task_path.read_text(encoding="utf-8-sig"))
            timestamps = sorted(str(r["timestamp"]) for r in records if r.get("timestamp"))
            statuses: Dict[str, int] = {}
            for record in records:
                status = str(record.get("status") or "unknown")
                statuses[status] = statuses.get(status, 0) + 1
            versioned = next((r for r in records if r.get("simulator_version")), {})
            leaderboard = _leaderboard(records, task)
            tasks.append({
                "slug": task_dir.name,
                "title": _task_title(task_dir),
                "task_set_version": task.get("task_set_version") or versioned.get("task_set_version"),
                "score_version": task.get("score_version") or versioned.get("score_version"),
                "simulator_version": versioned.get("simulator_version"),
                "targets": {
                    "heat_duty_kw": _round(_number(task.get("target_heat_duty")) / 1000.0, 1)
                    if _number(task.get("target_heat_duty")) is not None else None,
                    "max_dp_tube_kpa": _round(_number(task.get("max_dp_tube")) / 1000.0, 1)
                    if _number(task.get("max_dp_tube")) is not None else None,
                    "max_dp_shell_kpa": _round(_number(task.get("max_dp_shell")) / 1000.0, 1)
                    if _number(task.get("max_dp_shell")) is not None else None,
                },
                "runs": len(records),
                "models": len(leaderboard),
                "first_run": timestamps[0] if timestamps else None,
                "last_run": timestamps[-1] if timestamps else None,
                "statuses": dict(sorted(statuses.items(), key=lambda item: -item[1])),
                "funnel": _funnel(records),
                "leaderboard": leaderboard,
            })
        if tasks:
            tasks.sort(key=lambda t: t["last_run"] or "", reverse=True)
            tracks.append({"id": track, "label": label, "tasks": tasks})

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": os.environ.get("GITHUB_SHA"),
        "tracks": tracks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", default="results", type=Path)
    parser.add_argument("--out", default="docs/data/leaderboard.json", type=Path)
    args = parser.parse_args()

    data = build(args.results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tasks = sum(len(track["tasks"]) for track in data["tracks"])
    print(f"Wrote {args.out} ({tasks} tasks)")


if __name__ == "__main__":
    main()
