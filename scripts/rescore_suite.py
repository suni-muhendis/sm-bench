"""Judge a suite's recorded answers again under another score version.

Creates a new suite folder with the same tasks, each naming the new score
version, and re-evaluates every recorded design against its task with the
installed environment. Nothing is sent to a model: the answers are the ones
on record, so the new suite costs nothing and its numbers differ from the old
suite's only by the score. The source suite is never modified.

Each new record keeps the model's raw response and the prompt it was actually
shown (which names the old score version), and carries ``rescored_from`` with
the source suite, score version and timestamp. Answers that never produced a
design (client errors, token-limit stops, parse errors) are copied with their
status unchanged.

Usage:
    python scripts/rescore_suite.py --source heat_exchanger_suite_v1 \
        --target heat_exchanger_suite_v2 --score-version heat_exchanger_score_v5
"""

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone

from sm_core import make_env

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_NO_DESIGN = {"client_error", "empty_response", "parse_error", "token_limit"}


def _same_metrics(old: dict, new: dict, rel: float = 1e-12) -> bool:
    """Equal up to floating-point round-off.

    A record made on another platform can differ in the last bit (seen: one
    F_LMTD value, relative difference 1.3e-16, Linux record re-run on Windows).
    Anything larger means the simulator changed and the suite must not be built.
    """
    if old.keys() != new.keys():
        return False
    for key, a in old.items():
        b = new[key]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
            if abs(a - b) > rel * max(abs(a), abs(b), 1e-300):
                return False
        elif a != b:
            return False
    return True


def rescore(source: str, target: str, score_version: str, results_root: str) -> None:
    src = os.path.join(results_root, "zero_shot", source)
    dst = os.path.join(results_root, "zero_shot", target)
    if os.path.exists(dst):
        sys.exit(f"{dst} already exists; refusing to overwrite a suite")

    with open(os.path.join(src, "suite.json"), encoding="utf-8") as handle:
        suite = json.load(handle)
    tasks = {}
    with open(os.path.join(src, "tasks.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                task = json.loads(line)
                task["score_version"] = score_version
                tasks[task["task_id"]] = task

    env = make_env(suite.get("environment", "heat_exchanger"))
    if env.get_score_function({"score_version": score_version}).VERSION != score_version:
        sys.exit(f"installed environment does not provide {score_version}")

    os.makedirs(os.path.join(dst, "api_runs"))
    with open(os.path.join(dst, "tasks.jsonl"), "w", encoding="utf-8", newline="\n") as handle:
        for task in tasks.values():
            handle.write(json.dumps(task) + "\n")
    new_suite = {**suite, "suite_id": target, "score_version": score_version,
                 "rescored_from": {"suite_id": suite.get("suite_id", source),
                                   "score_version": suite.get("score_version")}}
    new_suite.pop("archived", None)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = {}
    for name in sorted(os.listdir(os.path.join(src, "api_runs"))):
        if not name.endswith(".jsonl"):
            continue
        out = []
        with open(os.path.join(src, "api_runs", name), encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                old = json.loads(line)
                rec = copy.deepcopy(old)
                task = tasks[old["task_id"]]
                rec.update(
                    suite_id=target,
                    task_params=task,
                    score_version=score_version,
                    rescored_from={"suite_id": old.get("suite_id"),
                                   "score_version": old.get("score_version"),
                                   "timestamp": old.get("timestamp")},
                    rescored_at=now,
                )
                if old.get("status") not in _NO_DESIGN and isinstance(old.get("design"), dict):
                    result = env.evaluate(old["task_id"], task, f"{old['model_name']}_rescore", old["design"])
                    rec.update(
                        status=result.status,
                        total_reward=float(result.score.normalized_total),
                        reward_components=dict(result.score.components),
                        metrics=dict(result.metrics),
                        error=result.error_message,
                        environment=env.name,
                        simulator_version=env.simulator.VERSION,
                    )
                    if old.get("status") == "success" and not _same_metrics(old.get("metrics") or {}, result.metrics):
                        sys.exit(f"metrics changed for {name} {old['task_id']}: the simulator moved")
                out.append(rec)
        with open(os.path.join(dst, "api_runs", name), "w", encoding="utf-8", newline="\n") as handle:
            for rec in out:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        counts[name] = len(out)

    with open(os.path.join(dst, "suite.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(new_suite, handle, indent=2)
        handle.write("\n")
    print(f"{target}: {sum(counts.values())} records from {len(counts)} files rescored with {score_version}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--score-version", required=True)
    parser.add_argument("--results", default=os.path.join(_REPO_ROOT, "results"))
    args = parser.parse_args()
    rescore(args.source, args.target, args.score_version, args.results)


if __name__ == "__main__":
    main()
