import json
import os

import pytest

from scripts.rescore_suite import _same_metrics, rescore
from scripts.run_api_benchmark import run_benchmark
from sm_bench.model_clients.dummy_random import DummyRandomClient

from tests.test_api_benchmark import _isolate_repo_root, _make_suite_unit  # noqa: F401  (fixture)


def test_rescore_builds_a_new_suite_and_leaves_the_source_untouched(tmp_path):
    root = str(tmp_path)
    slug, _ = _make_suite_unit(root)
    run_benchmark(prompt_slug=slug, model_specs=[{"name": "dummy"}],
                  client_factory=lambda spec: DummyRandomClient(), repeats=2,
                  results_root=root, use_live_prices=False)
    src_dir = os.path.join(root, "zero_shot", slug)
    before = {n: open(os.path.join(src_dir, "api_runs", n), encoding="utf-8").read()
              for n in os.listdir(os.path.join(src_dir, "api_runs"))}

    rescore(slug, "he_suite_v5", "heat_exchanger_score_v5", root)

    after = {n: open(os.path.join(src_dir, "api_runs", n), encoding="utf-8").read() for n in before}
    assert after == before
    dst_dir = os.path.join(root, "zero_shot", "he_suite_v5")
    suite = json.load(open(os.path.join(dst_dir, "suite.json"), encoding="utf-8"))
    assert suite["suite_id"] == "he_suite_v5"
    assert suite["rescored_from"]["suite_id"] == "suite_test_v1"
    tasks = [json.loads(l) for l in open(os.path.join(dst_dir, "tasks.jsonl"), encoding="utf-8")]
    assert {t["score_version"] for t in tasks} == {"heat_exchanger_score_v5"}

    old = [json.loads(l) for l in before["dummy.jsonl"].splitlines()]
    new = [json.loads(l) for l in open(os.path.join(dst_dir, "api_runs", "dummy.jsonl"), encoding="utf-8")]
    assert len(new) == len(old)
    for o, n in zip(old, new):
        assert n["score_version"] == "heat_exchanger_score_v5"
        assert n["suite_id"] == "he_suite_v5"
        assert n["rescored_from"] == {"suite_id": "suite_test_v1",
                                      "score_version": o["score_version"], "timestamp": o["timestamp"]}
        assert n["prompt_text"] == o["prompt_text"] and n["raw_response"] == o["raw_response"]
        assert n["status"] == o["status"]


def test_rescore_refuses_to_overwrite_a_suite(tmp_path):
    root = str(tmp_path)
    slug, _ = _make_suite_unit(root)
    os.makedirs(os.path.join(root, "zero_shot", "taken"))
    with pytest.raises(SystemExit):
        rescore(slug, "taken", "heat_exchanger_score_v5", root)


def test_metrics_comparison_tolerates_round_off_only():
    assert _same_metrics({"a": 0.8584034157403434, "s": "x"}, {"a": 0.8584034157403433, "s": "x"})
    assert not _same_metrics({"a": 1.0}, {"a": 1.0 + 1e-9})
    assert not _same_metrics({"a": 1.0}, {"a": 1.0, "b": 2.0})
