"""Protect the denominators and missing-data semantics used by site charts."""

import pytest

from scripts.build_site_data import _distribution, _leaderboard


def record(status, score=0, cost=None, latency=None, model="model-a"):
    return {"model_name": model, "status": status, "total_score": score,
            "cost_usd": cost, "latency_ms": latency, "_source": "API"}


def test_distribution_uses_inclusive_quartiles_and_preserves_singletons():
    assert _distribution([]) is None
    assert _distribution([0.4]) == dict(min=0.4, q1=0.4, median=0.4, q3=0.4, max=0.4, count=1)
    assert _distribution([1, 0, 0.5, 0.25])["q1"] == pytest.approx(0.1875)


def test_score_distribution_excludes_not_run_but_includes_failed_designs():
    row = _leaderboard([
        record("success", 0.8), record("drc_error"),
        record("client_error"), record("token_limit"),
    ], {})[0]
    assert row["mean_score"] == 0.4
    assert row["charts"]["score_distribution"]["count"] == 2
    assert row["charts"]["score_distribution"]["median"] == row["median_score"]
    assert row["charts"]["statuses"] == {"success": 1, "drc_error": 1, "client_error": 1, "token_limit": 1}
    assert sum(row["charts"]["statuses"].values()) == row["runs"]


def test_all_not_run_has_no_score_distribution():
    row = _leaderboard([record("client_error"), record("token_limit")], {})[0]
    assert row["charts"]["score_distribution"] is None
    assert row["mean_score"] is None


def test_incomplete_costs_are_not_used_in_cost_comparison():
    row = _leaderboard([record("success", cost=0.2), record("success")], {})[0]
    assert row["charts"]["priced_runs"] == 1
    assert row["charts"]["mean_cost_usd"] is None
    assert row["cost_usd"] == 0.2  # Existing ledger behavior is unchanged.


def test_zero_cost_is_known_and_models_are_kept_separate():
    rows = _leaderboard([
        record("success", cost=0, latency=1000),
        record("success", cost=0.02, latency=3000),
        record("success", cost=0.5, model="model-b"),
    ], {})
    a = next(row for row in rows if row["model"] == "model-a")
    assert a["charts"]["mean_cost_usd"] == 0.01
    assert a["charts"]["priced_runs"] == 2
    assert a["charts"]["latency_distribution"]["median"] == a["p50_latency_s"] == 2
    assert len(rows) == 2
