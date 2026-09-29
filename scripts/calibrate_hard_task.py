"""Offline, seeded feasibility check for the hard heat-exchanger benchmark."""
import argparse
import json
import random
from pathlib import Path

from sm_core import make_env
from sm_heat_exchanger.geometry import bundle_diameter
from sm_heat_exchanger.simulator import HeatExchangerSimulator


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate one self-contained hard heat-exchanger prompt unit."
    )
    parser.add_argument("--prompt", default="heat_exchanger_hard_v1")
    parser.add_argument("--samples", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.samples <= 0:
        raise ValueError("--samples must be positive")

    rng = random.Random(args.seed)
    env = make_env("heat_exchanger")
    root = Path(__file__).resolve().parents[1]
    task_path = root / "results" / "zero_shot" / args.prompt / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    rows = []
    for i in range(args.samples):
        di = rng.uniform(0.008, 0.035)
        do = di + 2 * rng.uniform(0.001, 0.003)
        n = 2 * rng.randint(5, 175)
        pitch = do * 1.25
        required_bundle = bundle_diameter(n, do, pitch, 2, "square")
        design = {
            "geometry_type": "shell_and_tube",
            "length": rng.uniform(1.0, 10.0),
            "inner_tube_di": di, "inner_tube_do": do,
            "outer_shell_di": required_bundle + rng.uniform(0.006, 0.20),
            "number_of_tubes": n, "baffle_spacing": rng.uniform(0.1, 1.5),
        }
        result = env.evaluate("calibration", task, str(i), design)
        if result.status != "success":
            continue
        m = result.metrics
        feasible = (m["heat_duty_W"] >= task["target_heat_duty"]
                    and m["dp_tube_Pa"] <= task["max_dp_tube"]
                    and m["dp_shell_Pa"] <= task["max_dp_shell"])
        rows.append({"design": design, "metrics": m,
                     "score": result.score.normalized_total, "meets_targets": feasible})
    feasible = [r for r in rows if r["meets_targets"]]
    rows.sort(key=lambda r: r["score"], reverse=True)
    reference = max(feasible, key=lambda r: r["score"]) if feasible else None
    summary = {
        "seed": args.seed, "simulator_version": HeatExchangerSimulator.VERSION,
        "prompt_slug": args.prompt, "score_version": task.get("score_version"),
        "samples": args.samples, "successful_simulations": len(rows),
        "task_params": task, "meets_targets": len(feasible),
        "meets_targets_without_warnings": sum(r["metrics"]["num_warnings"] == 0 for r in feasible),
        "score_quantiles": {str(q): rows[round((len(rows)-1)*(1-q))]["score"]
                            for q in [0, 0.25, 0.5, 0.75, 0.9, 1]},
        "reference": reference, "highest_score": rows[0],
    }
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
    elif args.prompt == "heat_exchanger_hard_v1":
        output = root / "reports" / "hard_task_calibration.json"
    else:
        output = root / "reports" / "{}_calibration.json".format(args.prompt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("reference", "highest_score")}, indent=2))
    if reference:
        print("Reference score:", reference["score"], "warnings:", reference["metrics"]["num_warnings"])


if __name__ == "__main__":
    main()
