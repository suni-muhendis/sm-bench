import json

from scripts.token_ledger import (
    build_ledger,
    group_summary,
    load_price_book,
    reprice,
    summarize,
    usage_row,
)
from sm_bench.model_clients.usage import (
    estimate_cost,
    extract_usage,
    price_snapshot,
)


class _Details:
    def __init__(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)


class _Response:
    def __init__(self, usage):
        self.usage = usage


def _write_run(root, track, task, model_file, records):
    run_dir = root / track / task / "api_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / model_file
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def test_extract_usage_reads_reasoning_and_cached_tokens():
    response = _Response(_Details(
        prompt_tokens=120,
        completion_tokens=400,
        total_tokens=520,
        completion_tokens_details=_Details(reasoning_tokens=310),
        prompt_tokens_details=_Details(cached_tokens=64),
        cost=0.0042,
    ))

    usage = extract_usage(response)

    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 400
    assert usage["reasoning_tokens"] == 310
    assert usage["cached_prompt_tokens"] == 64
    assert usage["total_tokens"] == 520
    assert usage["charged_cost_usd"] == 0.0042


def test_extract_usage_survives_a_provider_that_reports_almost_nothing():
    usage = extract_usage(_Response(_Details(prompt_tokens=10, completion_tokens=5)))

    assert usage["total_tokens"] == 15  # derived, not reported
    assert usage["reasoning_tokens"] is None
    assert usage["charged_cost_usd"] is None


def test_extract_usage_handles_a_response_without_usage():
    usage = extract_usage(_Response(None))

    assert usage["prompt_tokens"] is None
    assert usage["total_tokens"] is None


def test_price_snapshot_and_estimate_freeze_the_rate_that_was_used():
    snapshot = price_snapshot({
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        "pricing_source": "openrouter",
        "pricing_synced_at": "2026-09-18",
    })

    assert snapshot["prompt_usd_per_token"] == 1e-6
    assert snapshot["synced_at"] == "2026-09-18"
    assert estimate_cost(
        {"prompt_tokens": 1000, "completion_tokens": 500}, snapshot
    ) == 1000 * 1e-6 + 500 * 2e-6


def test_estimate_cost_is_none_when_the_price_is_unknown():
    assert estimate_cost({"prompt_tokens": 10, "completion_tokens": 5}, {}) is None


def test_usage_row_prefers_the_cost_the_provider_actually_charged():
    row = usage_row({
        "model_name": "m", "model_id": "vendor/m", "status": "success",
        "timestamp": "2026-09-18T10:00:00Z",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "pricing_snapshot": {
            "prompt_usd_per_token": 1e-6, "completion_usd_per_token": 2e-6,
            "synced_at": "2026-09-01",
        },
        "cost_usd": 0.5,
        "cost_basis": "provider_charged",
    })

    assert row["cost_then_usd"] == 0.5
    assert row["cost_basis"] == "provider_charged"
    assert row["month"] == "2026-09"


def test_usage_row_prices_legacy_records_from_their_embedded_metadata():
    """Runs written before the ledger existed still carry a usable price."""
    row = usage_row({
        "model_name": "legacy",
        "prompt_tokens": 1000,
        "completion_tokens": 1000,
        "model_metadata": {"pricing": {"prompt": "0.000001", "completion": "0.000003"}},
    })

    assert row["total_tokens"] == 2000
    assert row["cost_then_usd"] == 0.004
    assert row["cost_basis"] == "price_snapshot"


def test_usage_row_leaves_cost_unknown_rather_than_calling_it_free():
    row = usage_row({"model_name": "m", "prompt_tokens": 10, "completion_tokens": 5})

    assert row["cost_then_usd"] is None
    assert row["cost_basis"] == "unknown"


def test_reprice_applies_a_different_price_list_to_the_same_tokens():
    row = {"model_id": "vendor/m", "prompt_tokens": 1000, "completion_tokens": 1000}
    book = {"prices": {"vendor/m": {"prompt": 2e-6, "completion": 4e-6}}}

    assert reprice(row, book) == 0.006
    assert reprice(row, {"prices": {}}) is None


def test_build_ledger_reads_every_track_and_prices_then_and_now(tmp_path):
    _write_run(tmp_path, "zero_shot", "task-a", "m.jsonl", [
        {
            "model_name": "m", "model_id": "vendor/m", "status": "success",
            "timestamp": "2026-09-18T10:00:00Z", "prompt_slug": "task-a",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
            "pricing_snapshot": {
                "prompt_usd_per_token": 1e-6, "completion_usd_per_token": 1e-6,
            },
        },
    ])
    _write_run(tmp_path, "feedback_driven", "task-b", "m.jsonl", [
        {
            "model_name": "m", "model_id": "vendor/m", "status": "client_error",
            "timestamp": "2026-09-18T11:00:00Z",
        },
    ])
    book = {"synced_at": "2026-12-01", "prices": {"vendor/m": {"prompt": 2e-6, "completion": 2e-6}}}

    ledger = build_ledger(str(tmp_path), book)
    totals = summarize(ledger)

    assert totals["runs"] == 2
    assert totals["total_tokens"] == 2000
    assert totals["cost_then_usd"] == 0.002
    assert totals["cost_now_usd"] == 0.004
    # Only the run that has both prices may be compared.
    assert totals["comparable_runs"] == 1
    assert totals["price_change_pct"] == 100.0
    assert {row["track"] for row in ledger} == {"zero_shot", "feedback_driven"}


def test_group_summary_ranks_by_historical_spend(tmp_path):
    rows = [
        {"model": "cheap", "cost_then_usd": 0.001, "cost_now_usd": 0.001, "total_tokens": 10},
        {"model": "pricey", "cost_then_usd": 0.500, "cost_now_usd": 0.400, "total_tokens": 20},
    ]

    groups = group_summary(rows, "model")

    assert [group["model"] for group in groups] == ["pricey", "cheap"]


def test_load_price_book_reads_a_dated_snapshot(tmp_path):
    path = tmp_path / "openrouter-2026-09-18.json"
    path.write_text(json.dumps({
        "provider": "openrouter",
        "synced_at": "2026-09-18",
        "models": {"vendor/m": {"prompt": "0.000005", "completion": "0.000009"}},
    }), encoding="utf-8")

    book = load_price_book(str(path))

    assert book["synced_at"] == "2026-09-18"
    assert book["prices"]["vendor/m"]["completion"] == 9e-6


def test_load_price_book_reads_the_live_model_registry(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({
        "providers": {
            "openrouter": [
                {
                    "name": "friendly-name",
                    "model": "vendor/m",
                    "metadata": {
                        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                        "pricing_synced_at": "2026-09-18",
                    },
                }
            ]
        }
    }), encoding="utf-8")

    book = load_price_book(str(path))

    assert book["synced_at"] == "2026-09-18"
    # Both the API id and the display name resolve, because old records stored
    # whichever of the two the runner happened to know.
    assert book["prices"]["vendor/m"]["prompt"] == 1e-6
    assert book["prices"]["friendly-name"]["prompt"] == 1e-6
