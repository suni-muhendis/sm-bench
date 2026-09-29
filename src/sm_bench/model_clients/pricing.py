"""Live per-token prices, read from the provider rather than from a local file.

``configs/benchmarks/models.json`` is a snapshot that is only as fresh as the
last manual sync, so pricing a run from it can attribute a run to a rate that
stopped being true weeks earlier. The price a run freezes must be the price
that was actually live when the call was made, so it is fetched from the
OpenRouter models endpoint at the start of a benchmark and stamped with the
exact moment it was read.

The endpoint is public (no key) and returns every model in one response, so a
benchmark fetches it once and prices every run from that one read.
"""

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

_LIVE_CACHE: Optional[Dict[str, Any]] = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def parse_price_payload(payload: Dict[str, Any], fetched_at: Optional[str] = None) -> Dict[str, Any]:
    """Turn an OpenRouter ``/models`` response into a price book."""
    prices: Dict[str, Dict[str, Optional[float]]] = {}
    for model in payload.get("data") or []:
        model_id = model.get("id")
        pricing = model.get("pricing") or {}
        if not model_id or not pricing:
            continue
        prices[model_id] = {
            "prompt": _float(pricing.get("prompt")),
            "completion": _float(pricing.get("completion")),
        }
    return {
        "source": "openrouter_api",
        "fetched_at": fetched_at or _utcnow_iso(),
        "prices": prices,
    }


def fetch_openrouter_prices(
    url: str = OPENROUTER_MODELS_URL,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Read the live price list. Raises on any network or decoding failure."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_price_payload(payload)


def live_price_book(
    fetcher: Optional[Callable[[], Dict[str, Any]]] = None,
    refresh: bool = False,
) -> Dict[str, Any]:
    """Fetch the live price list once per process.

    A benchmark run priced from two different reads of a moving price list would
    not be internally consistent, so the first read is reused for the whole
    process unless a refresh is asked for.
    """
    global _LIVE_CACHE
    if _LIVE_CACHE is not None and not refresh:
        return _LIVE_CACHE
    _LIVE_CACHE = (fetcher or fetch_openrouter_prices)()
    return _LIVE_CACHE


def reset_live_cache() -> None:
    """Drop the memoized price list (tests, and long-lived processes)."""
    global _LIVE_CACHE
    _LIVE_CACHE = None


def rates_for(
    price_book: Optional[Dict[str, Any]],
    *candidates: Optional[str],
) -> Optional[Dict[str, Optional[float]]]:
    """Look a model up by any of the names a record might know it under."""
    prices = (price_book or {}).get("prices") or {}
    for candidate in candidates:
        if candidate and candidate in prices:
            return prices[candidate]
    return None


def snapshot_from_live(
    price_book: Optional[Dict[str, Any]],
    *candidates: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Freeze the live rate for one model into a record-ready snapshot."""
    rates = rates_for(price_book, *candidates)
    if rates is None:
        return None
    return {
        "prompt_usd_per_token": rates.get("prompt"),
        "completion_usd_per_token": rates.get("completion"),
        "source": (price_book or {}).get("source", "openrouter_api"),
        "synced_at": (price_book or {}).get("fetched_at"),
    }
