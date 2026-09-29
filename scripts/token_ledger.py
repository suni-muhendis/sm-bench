"""Token and spend ledger over every benchmark run ever recorded.

Each run's JSONL line is the permanent receipt for one API call. This module
turns those receipts into an auditable ledger that answers two different
questions about the same run:

* **What did it cost then?** - from the price the run itself froze, or from the
  amount the provider said it charged.
* **What would it cost now?** - by repricing the same token counts against a
  current (or any dated) price list.

Both are needed because the numbers diverge: quoting only today's price
misstates what the research actually cost, and quoting only the historical
price misstates what repeating it would cost.

Pure stdlib on purpose - the dashboard and the CLI report both import it.
"""

import glob
import json
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_ROOT = os.path.join(REPO_ROOT, "results")
MODELS_JSON = os.path.join(REPO_ROOT, "configs", "benchmarks", "models.json")
PRICING_HISTORY_DIR = os.path.join(REPO_ROOT, "configs", "benchmarks", "pricing_history")


LEDGER_EXPORT_COLUMNS = (
    "timestamp", "month", "track", "task", "model", "model_id", "provider",
    "status", "prompt_tokens", "completion_tokens", "reasoning_tokens",
    "cached_prompt_tokens", "total_tokens", "cost_then_usd", "cost_basis",
    "priced_at", "cost_now_usd", "priced_now_at",
)


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _int(value: Any) -> Optional[int]:
    parsed = _float(value)
    return int(parsed) if parsed is not None else None


def iter_run_records(results_root: str = RESULTS_ROOT) -> Iterator[Tuple[str, int, Dict[str, Any]]]:
    """Yield every recorded run, whatever results layout it was written in."""
    pattern = os.path.join(results_root, "**", "*.jsonl")
    for path in sorted(set(glob.glob(pattern, recursive=True))):
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        yield path, line_number, json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def _path_context(path: str, results_root: str) -> Tuple[str, str]:
    """Recover (track, task) from the file's location under results/."""
    relative = os.path.relpath(path, results_root).replace("\\", "/")
    parts = relative.split("/")
    known_tracks = ("zero_shot", "feedback_driven")
    if parts and parts[0] in known_tracks:
        return parts[0], parts[1] if len(parts) > 1 else "unknown"
    for index, part in enumerate(parts):
        if part in known_tracks:
            return part, parts[index - 1] if index else "unknown"
    return "zero_shot", parts[0] if parts else "unknown"


def usage_row(
    record: Dict[str, Any],
    path: str = "",
    results_root: str = RESULTS_ROOT,
) -> Dict[str, Any]:
    """Normalize one run into a ledger line.

    Records written before full usage accounting existed only carry flat
    ``prompt_tokens`` / ``completion_tokens``; those still produce a valid line,
    just without the reasoning and cache detail.
    """
    usage = record.get("usage") or {}
    metadata = record.get("model_metadata") or {}
    snapshot = record.get("pricing_snapshot") or {}
    if not snapshot:
        # Pre-ledger records embedded the price list inside model metadata.
        pricing = metadata.get("pricing") or {}
        snapshot = {
            "prompt_usd_per_token": _float(pricing.get("prompt")),
            "completion_usd_per_token": _float(pricing.get("completion")),
            "source": metadata.get("pricing_source"),
            "synced_at": metadata.get("pricing_synced_at"),
        }

    prompt_tokens = _int(usage.get("prompt_tokens"))
    if prompt_tokens is None:
        prompt_tokens = _int(record.get("prompt_tokens"))
    completion_tokens = _int(usage.get("completion_tokens"))
    if completion_tokens is None:
        completion_tokens = _int(record.get("completion_tokens"))
    total_tokens = _int(usage.get("total_tokens"))
    if total_tokens is None and None not in (prompt_tokens, completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    cost_then = _float(record.get("cost_usd"))
    basis = record.get("cost_basis")
    if cost_then is None:
        cost_then = _cost_at(
            prompt_tokens,
            completion_tokens,
            _float(snapshot.get("prompt_usd_per_token")),
            _float(snapshot.get("completion_usd_per_token")),
        )
        basis = "price_snapshot" if cost_then is not None else "unknown"

    timestamp = str(record.get("timestamp") or "")
    track, task = _path_context(path, results_root) if path else ("zero_shot", "unknown")

    return {
        "timestamp": timestamp,
        "month": timestamp[:7] if len(timestamp) >= 7 else "unknown",
        "track": record.get("evaluation_mode") or track,
        "task": record.get("prompt_slug") or task,
        "model": record.get("model_name") or "Unknown",
        "model_id": record.get("model_id") or record.get("model_name") or "Unknown",
        "provider": record.get("provider") or "unknown",
        "status": record.get("status") or "unknown",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": _int(usage.get("reasoning_tokens")),
        "cached_prompt_tokens": _int(usage.get("cached_prompt_tokens")),
        "total_tokens": total_tokens,
        "cost_then_usd": cost_then,
        "cost_basis": basis or "unknown",
        "price_prompt_then": _float(snapshot.get("prompt_usd_per_token")),
        "price_completion_then": _float(snapshot.get("completion_usd_per_token")),
        "priced_at": snapshot.get("synced_at"),
    }


def _cost_at(
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    prompt_rate: Optional[float],
    completion_rate: Optional[float],
) -> Optional[float]:
    if None in (prompt_tokens, completion_tokens, prompt_rate, completion_rate):
        return None
    return prompt_tokens * prompt_rate + completion_tokens * completion_rate


def load_price_book(path: Optional[str] = None) -> Dict[str, Any]:
    """Load a price list: the live registry by default, or a dated snapshot."""
    if path is None:
        path = MODELS_JSON
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)

    prices: Dict[str, Dict[str, Optional[float]]] = {}
    synced_at = data.get("synced_at")

    if "models" in data and "providers" not in data:  # dated snapshot file
        for model_id, pricing in (data.get("models") or {}).items():
            prices[model_id] = {
                "prompt": _float(pricing.get("prompt")),
                "completion": _float(pricing.get("completion")),
            }
    else:  # configs/benchmarks/models.json
        for entries in (data.get("providers") or {}).values():
            for entry in entries:
                metadata = entry.get("metadata") or {}
                pricing = metadata.get("pricing") or {}
                rates = {
                    "prompt": _float(pricing.get("prompt")),
                    "completion": _float(pricing.get("completion")),
                }
                if entry.get("model"):
                    prices[entry["model"]] = rates
                if entry.get("name"):
                    prices.setdefault(entry["name"], rates)
                synced_at = synced_at or metadata.get("pricing_synced_at")

    return {"path": path, "synced_at": synced_at, "prices": prices}


def live_price_book(fetcher=None) -> Dict[str, Any]:
    """Today's prices, read from the OpenRouter API rather than a local file.

    This is what "what would it cost now" should mean: the rate the provider is
    charging at the moment of the report, not the rate of the last local sync.
    """
    from sm_bench.model_clients import pricing

    book = pricing.live_price_book(fetcher)
    prices = dict(book.get("prices") or {})
    # Older records stored the display name rather than the API model id. The
    # local registry is used only to map one to the other - never for rates.
    for display_name, model_id in _display_name_aliases().items():
        if display_name not in prices and model_id in prices:
            prices[display_name] = prices[model_id]
    return {
        "path": pricing.OPENROUTER_MODELS_URL,
        "synced_at": book.get("fetched_at"),
        "source": book.get("source", "openrouter_api"),
        "prices": prices,
    }


def _display_name_aliases(path: Optional[str] = None) -> Dict[str, str]:
    """Map the names used in run records to the provider's model ids."""
    try:
        with open(path or MODELS_JSON, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    aliases: Dict[str, str] = {}
    for entries in (data.get("providers") or {}).values():
        for entry in entries:
            name, model_id = entry.get("name"), entry.get("model")
            if name and model_id:
                aliases.setdefault(name, model_id)
    return aliases


def resolve_price_book(
    mode: str = "live",
    fetcher=None,
    on_fallback=None,
) -> Dict[str, Any]:
    """Pick a price list: live API, the local registry, or a dated snapshot file.

    Live is the default and the local registry is the fallback, because a report
    that silently prices against a stale local file is worse than one that says
    it could not reach the provider.
    """
    if mode == "local":
        return load_price_book()
    if mode not in ("live", "auto"):
        return load_price_book(mode)
    try:
        return live_price_book(fetcher)
    except Exception as exc:
        if on_fallback is not None:
            on_fallback(exc)
        book = load_price_book()
        book["source"] = "models.json (live prices unavailable)"
        return book


def available_price_snapshots(directory: str = PRICING_HISTORY_DIR) -> List[str]:
    """Dated price books written by ``scripts/sync_openrouter.py``, newest last."""
    if not os.path.isdir(directory):
        return []
    return sorted(
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.endswith(".json")
    )


def reprice(row: Dict[str, Any], price_book: Dict[str, Any]) -> Optional[float]:
    """Cost of an already-recorded run under a different price list."""
    prices = price_book.get("prices") or {}
    rates = prices.get(row.get("model_id")) or prices.get(row.get("model"))
    if not rates:
        return None
    return _cost_at(
        row.get("prompt_tokens"),
        row.get("completion_tokens"),
        rates.get("prompt"),
        rates.get("completion"),
    )


def build_ledger(
    results_root: str = RESULTS_ROOT,
    price_book: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Every run as a ledger line, priced then and now."""
    book = price_book if price_book is not None else load_price_book()
    rows: List[Dict[str, Any]] = []
    for path, _line, record in iter_run_records(results_root):
        row = usage_row(record, path, results_root)
        row["cost_now_usd"] = reprice(row, book)
        row["priced_now_at"] = book.get("synced_at")
        rows.append(row)
    return rows


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Totals for a set of ledger lines, including how complete they are."""
    def total(key: str) -> float:
        return float(sum(row.get(key) or 0 for row in rows))

    priced_then = [row for row in rows if row.get("cost_then_usd") is not None]
    priced_now = [row for row in rows if row.get("cost_now_usd") is not None]
    comparable = [
        row for row in rows
        if row.get("cost_then_usd") is not None and row.get("cost_now_usd") is not None
    ]
    then_sum = float(sum(row["cost_then_usd"] for row in comparable))
    now_sum = float(sum(row["cost_now_usd"] for row in comparable))

    return {
        "runs": len(rows),
        "runs_with_tokens": sum(1 for row in rows if row.get("total_tokens")),
        "prompt_tokens": total("prompt_tokens"),
        "completion_tokens": total("completion_tokens"),
        "reasoning_tokens": total("reasoning_tokens"),
        "cached_prompt_tokens": total("cached_prompt_tokens"),
        "total_tokens": total("total_tokens"),
        "cost_then_usd": total("cost_then_usd"),
        "cost_now_usd": total("cost_now_usd"),
        "runs_priced_then": len(priced_then),
        "runs_priced_now": len(priced_now),
        "comparable_runs": len(comparable),
        "comparable_cost_then_usd": then_sum,
        "comparable_cost_now_usd": now_sum,
        "price_change_pct": (
            100.0 * (now_sum - then_sum) / then_sum if then_sum else None
        ),
    }


def group_summary(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Per-group totals, sorted by historical spend."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key, "unknown")), []).append(row)
    summaries = []
    for name, group in groups.items():
        summary = summarize(group)
        summary[key] = name
        summaries.append(summary)
    return sorted(summaries, key=lambda item: item["cost_then_usd"], reverse=True)
