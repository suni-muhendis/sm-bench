"""Token accounting shared by every OpenAI-compatible model client.

Benchmark runs are the permanent record of what an experiment cost. Token
counts are only half of that: prices move, so a run that is read back months
later also needs the price that was in force when it was made. This module
extracts everything the provider reports about one call, and freezes the price
list that was used, so both "what it cost then" and "what it would cost now"
stay answerable from the stored record alone.
"""

from typing import Any, Dict, Optional


USAGE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "total_tokens",
)


def _attr(source: Any, key: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None  # drop NaN


def extract_usage(response: Any) -> Dict[str, Any]:
    """Pull the full token accounting out of a chat-completions response.

    Providers agree on ``prompt_tokens`` / ``completion_tokens`` and disagree on
    everything else, so the extras are read defensively. ``charged_cost_usd`` is
    only set when the provider states what it actually billed (OpenRouter does
    when usage accounting is requested); otherwise it stays ``None`` and the
    cost has to be estimated from the price list.
    """
    usage = _attr(response, "usage")
    completion_details = _attr(usage, "completion_tokens_details")
    prompt_details = _attr(usage, "prompt_tokens_details")

    prompt_tokens = _int(_attr(usage, "prompt_tokens"))
    completion_tokens = _int(_attr(usage, "completion_tokens"))
    total_tokens = _int(_attr(usage, "total_tokens"))
    if total_tokens is None and None not in (prompt_tokens, completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        # Reasoning tokens are billed as output tokens but are invisible in the
        # response text, so they are tracked separately to explain the bill.
        "reasoning_tokens": _int(_attr(completion_details, "reasoning_tokens")),
        "cached_prompt_tokens": _int(_attr(prompt_details, "cached_tokens")),
        "total_tokens": total_tokens,
        "charged_cost_usd": _float(_attr(usage, "cost")),
    }


def empty_usage() -> Dict[str, Any]:
    """Usage placeholder for a call that never reached the provider."""
    return {field: None for field in USAGE_FIELDS + ("charged_cost_usd",)}


def price_snapshot(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Freeze the per-token prices that were in force for this call.

    The rates are copied into the run record rather than referenced, because
    ``configs/benchmarks/models.json`` is re-synced regularly and would
    otherwise rewrite the cost of every historical run.
    """
    metadata = metadata or {}
    pricing = metadata.get("pricing") or {}
    return {
        "prompt_usd_per_token": _float(pricing.get("prompt")),
        "completion_usd_per_token": _float(pricing.get("completion")),
        "source": metadata.get("pricing_source") or "configs/benchmarks/models.json",
        "synced_at": metadata.get("pricing_synced_at"),
    }


def estimate_cost(usage: Dict[str, Any], snapshot: Dict[str, Any]) -> Optional[float]:
    """Cost of one call under a given price list, or ``None`` if unknowable."""
    prompt_rate = _float(snapshot.get("prompt_usd_per_token"))
    completion_rate = _float(snapshot.get("completion_usd_per_token"))
    prompt_tokens = _float(usage.get("prompt_tokens"))
    completion_tokens = _float(usage.get("completion_tokens"))
    if None in (prompt_rate, completion_rate, prompt_tokens, completion_tokens):
        return None
    return prompt_tokens * prompt_rate + completion_tokens * completion_rate
