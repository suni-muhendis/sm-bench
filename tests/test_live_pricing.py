import json

import pytest

from scripts.token_ledger import live_price_book, resolve_price_book
from sm_bench.model_clients.pricing import (
    fetch_openrouter_prices,
    live_price_book as fetch_live_book,
    parse_price_payload,
    rates_for,
    reset_live_cache,
    snapshot_from_live,
)

_PAYLOAD = {
    "data": [
        {"id": "vendor/m", "pricing": {"prompt": "0.000001", "completion": "0.000003"}},
        {"id": "vendor/free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "vendor/broken"},  # no pricing block at all
    ]
}


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_live_cache()
    yield
    reset_live_cache()


def test_parse_price_payload_keeps_only_models_that_state_a_price():
    book = parse_price_payload(_PAYLOAD, fetched_at="2026-09-18T10:00:00Z")

    assert book["source"] == "openrouter_api"
    assert book["fetched_at"] == "2026-09-18T10:00:00Z"
    assert book["prices"]["vendor/m"] == {"prompt": 1e-6, "completion": 3e-6}
    assert book["prices"]["vendor/free"] == {"prompt": 0.0, "completion": 0.0}
    assert "vendor/broken" not in book["prices"]


def test_live_price_book_is_read_once_per_process():
    """One benchmark must price every run from a single read of a moving list."""
    calls = []

    def fetcher():
        calls.append(1)
        return parse_price_payload(_PAYLOAD)

    fetch_live_book(fetcher)
    fetch_live_book(fetcher)

    assert len(calls) == 1
    assert len(fetch_live_book(fetcher, refresh=True)["prices"]) == 2
    assert len(calls) == 2


def test_snapshot_from_live_resolves_by_model_id_or_display_name():
    book = parse_price_payload(_PAYLOAD, fetched_at="2026-09-18T10:00:00Z")

    snapshot = snapshot_from_live(book, "vendor/m", "friendly-name")

    assert snapshot["prompt_usd_per_token"] == 1e-6
    assert snapshot["source"] == "openrouter_api"
    # The stamp is the moment of the read, not just a date.
    assert snapshot["synced_at"] == "2026-09-18T10:00:00Z"
    assert snapshot_from_live(book, "unknown/model") is None
    assert rates_for(book, "unknown/model", "vendor/free")["prompt"] == 0.0


def test_fetch_openrouter_prices_parses_a_real_shaped_response(monkeypatch):
    class _Response:
        def read(self):
            return json.dumps(_PAYLOAD).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout=None: _Response()
    )

    book = fetch_openrouter_prices()

    assert book["prices"]["vendor/m"]["completion"] == 3e-6
    assert book["fetched_at"].endswith("Z")


def test_resolve_price_book_falls_back_to_the_local_registry_when_offline():
    seen = []

    def failing_fetcher():
        raise OSError("network unreachable")

    book = resolve_price_book("live", failing_fetcher, on_fallback=seen.append)

    assert seen and isinstance(seen[0], OSError)
    assert "live prices unavailable" in book["source"]
    assert book["prices"]  # the local registry still answers


def test_live_book_bridges_display_names_to_api_model_ids(monkeypatch):
    """Runs recorded under a display name must still reprice against live rates."""
    monkeypatch.setattr(
        "scripts.token_ledger._display_name_aliases",
        lambda path=None: {"friendly-name": "vendor/m"},
    )

    book = live_price_book(lambda: parse_price_payload(_PAYLOAD))

    assert book["source"] == "openrouter_api"
    assert book["prices"]["friendly-name"] == book["prices"]["vendor/m"]
