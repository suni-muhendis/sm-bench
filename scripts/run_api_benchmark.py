import argparse
import copy
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sm_core import make_env
from sm_bench.logging import setup_logger
from sm_bench.model_clients.base import BaseModelClient
from sm_bench.model_clients.pricing import (
    live_price_book,
    snapshot_from_live,
)
from sm_bench.model_clients.usage import (
    empty_usage,
    estimate_cost,
    price_snapshot,
)
from sm_core import parse_llm_json

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_WEIGHT_KEYS = ("w_heat", "w_cost", "w_drop_tube", "w_drop_shell", "w_eff")

ClientFactory = Callable[[Dict[str, Any]], BaseModelClient]

_REASONING_EFFORTS = ("default", "none", "minimal", "low", "medium", "high", "xhigh", "max")
_DEFAULT_MAX_OUTPUT_TOKENS = 8192
_DEFAULT_TEMPERATURE = 0.7
_CONTEXT_SAFETY_MARGIN = 256

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _safe_name(name: str) -> str:
    cleaned = name.strip().replace(os.sep, "_")
    if os.altsep:
        cleaned = cleaned.replace(os.altsep, "_")
    return cleaned or "unknown"


def _estimate_prompt_tokens(prompt: str) -> int:
    """Conservative tokenizer-independent estimate used only for preflight."""
    return max(1, int(math.ceil(len(prompt.encode("utf-8")) / 3.0)))


def _preflight_model(
    model_spec: Dict[str, Any],
    prompt: str,
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
    temperature: Optional[float] = _DEFAULT_TEMPERATURE,
):
    """Build safe effective parameters from synced capabilities."""
    if max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be positive")

    spec = copy.deepcopy(model_spec)
    metadata = spec.get("metadata") or {}
    supported = set(metadata.get("supported_parameters") or [])
    has_metadata = bool(metadata)
    estimated_prompt_tokens = _estimate_prompt_tokens(prompt)
    requested_params = {"max_tokens": max_output_tokens}
    if temperature is not None:
        requested_params["temperature"] = temperature

    effective_params = {}
    adjustments = []
    errors = []

    effective_max = max_output_tokens
    model_max = metadata.get("max_completion_tokens")
    if isinstance(model_max, int) and model_max > 0 and effective_max > model_max:
        adjustments.append(
            f"max_tokens clamped from {effective_max} to model maximum {model_max}"
        )
        effective_max = model_max

    context_length = metadata.get("context_length")
    if isinstance(context_length, int) and context_length > 0:
        context_budget = context_length - estimated_prompt_tokens - _CONTEXT_SAFETY_MARGIN
        if context_budget <= 0:
            errors.append(
                "estimated prompt plus safety margin exceeds the model context length"
            )
        elif effective_max > context_budget:
            adjustments.append(
                f"max_tokens clamped from {effective_max} to context budget {context_budget}"
            )
            effective_max = context_budget

    if not has_metadata or "max_tokens" in supported:
        effective_params["max_tokens"] = effective_max
    elif "max_completion_tokens" in supported:
        effective_params["max_completion_tokens"] = effective_max
        adjustments.append("using max_completion_tokens instead of max_tokens")
    else:
        errors.append(
            "model does not advertise an output-token limit parameter; "
            "fixed-budget run is unsafe"
        )

    if temperature is not None:
        if has_metadata and "temperature" not in supported:
            adjustments.append("temperature omitted; model uses provider default")
        else:
            effective_params["temperature"] = temperature

    params = spec.setdefault("params", {})
    params.pop("max_tokens", None)
    params.pop("max_completion_tokens", None)
    params.pop("temperature", None)
    params.update(effective_params)
    report = {
        "status": "error" if errors else "ready",
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "requested_params": requested_params,
        "effective_params": effective_params,
        "adjustments": adjustments,
        "errors": errors,
    }
    return spec, report


def _format_preflight(model_name: str, report: Dict[str, Any]) -> str:
    effective = report.get("effective_params", {})
    summary = (
        f"[preflight] {model_name}: {report['status'].upper()} | "
        f"prompt~{report['estimated_prompt_tokens']} tokens | effective={effective}"
    )
    details = report.get("errors") or report.get("adjustments") or []
    if details:
        summary += " | " + "; ".join(details)
    return summary


def _apply_reasoning_effort(
    model_specs: List[Dict[str, Any]],
    reasoning_effort: Optional[str],
) -> List[Dict[str, Any]]:
    """Return run-specific model specs without mutating the model registry."""
    specs = copy.deepcopy(model_specs)
    if reasoning_effort is None:
        return specs

    for spec in specs:
        base_name = spec.get("name") or spec.get("model")
        spec["name"] = f"{base_name}__reasoning-{reasoning_effort}"
        spec["reasoning_mode"] = reasoning_effort
        if reasoning_effort == "default":
            continue

        params = spec.setdefault("params", {})
        if spec.get("provider") == "openrouter":
            extra_body = params.setdefault("extra_body", {})
            extra_body["reasoning"] = {"effort": reasoning_effort}
            provider_options = extra_body.setdefault("provider", {})
            provider_options["require_parameters"] = True
        else:
            params["reasoning_effort"] = reasoning_effort
    return specs


def _reasoning_choices(model_spec: Dict[str, Any]) -> List[str]:
    """Return reasoning modes that the synced model metadata can justify."""
    metadata = model_spec.get("metadata") or {}
    supported_parameters = set(metadata.get("supported_parameters") or [])
    reasoning = metadata.get("reasoning")
    supports_reasoning = (
        reasoning is not None
        or "reasoning" in supported_parameters
        or "reasoning_effort" in supported_parameters
    )
    if not supports_reasoning:
        return []

    choices = ["default"]
    if reasoning:
        choices.extend(reasoning.get("supported_efforts") or [])
        if not reasoning.get("mandatory", False):
            choices.append("none")

    # Some models expose the reasoning parameter without publishing effort
    # levels. In that case only default/on and off are reliable choices.
    if reasoning is None and "reasoning" in supported_parameters:
        choices.append("none")

    return list(dict.fromkeys(choice for choice in choices if choice in _REASONING_EFFORTS))


def _reasoning_label(model_spec: Dict[str, Any], choice: str) -> str:
    reasoning = (model_spec.get("metadata") or {}).get("reasoning") or {}
    if choice == "default":
        default_effort = reasoning.get("default_effort")
        if default_effort:
            return f"default (provider default: {default_effort})"
        return "default (provider default)"
    if choice == "none":
        return "none (reasoning disabled)"
    return choice


def _prompt_reasoning_effort(
    model_spec: Dict[str, Any],
    input_func=input,
    print_func=print,
) -> Optional[str]:
    choices = _reasoning_choices(model_spec)
    if not choices:
        return None

    model_name = model_spec.get("name") or model_spec.get("model")
    print_func(f"\nReasoning mode for {model_name}:")
    for index, choice in enumerate(choices, start=1):
        print_func(f"  {index}) {_reasoning_label(model_spec, choice)}")

    while True:
        answer = input_func(f"Select [1-{len(choices)}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        print_func("Invalid selection.")


def _configure_reasoning(
    model_specs: List[Dict[str, Any]],
    requested_effort: Optional[str],
    interactive: bool,
) -> List[Dict[str, Any]]:
    configured = []
    for spec in model_specs:
        effort = requested_effort
        choices = _reasoning_choices(spec)

        if effort is not None and choices and effort not in choices:
            model_name = spec.get("name") or spec.get("model")
            raise SystemExit(
                f"Reasoning mode '{effort}' is not advertised for {model_name}. "
                f"Available modes: {', '.join(choices)}"
            )
        if effort is None and interactive:
            effort = _prompt_reasoning_effort(spec)

        if effort is None:
            configured.append(copy.deepcopy(spec))
        else:
            configured.extend(_apply_reasoning_effort([spec], effort))
    return configured

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

#: Tasks written before a task named its environment are heat-exchanger tasks.
_DEFAULT_ENVIRONMENT = "heat_exchanger"


def _build_environment(task_params: Dict[str, Any]):
    # The task names its environment. A score version the task names is
    # applied by the environment at every evaluation.
    return make_env(task_params.get("environment", _DEFAULT_ENVIRONMENT))

def multi_client_factory(spec: Dict[str, Any]) -> BaseModelClient:
    provider = spec.get("provider", "hf")
    
    if provider == "opencode":
        from sm_bench.model_clients.opencode_client import OpenCodeClient
        return OpenCodeClient(model=spec["model"], name=spec.get("name"), params=spec.get("params"))
    elif provider == "openrouter":
        from sm_bench.model_clients.openrouter_client import OpenRouterClient
        return OpenRouterClient(model=spec["model"], name=spec.get("name"), params=spec.get("params"))
    else:
        from sm_bench.model_clients.hf_client import HFInferenceClient
        return HFInferenceClient(model=spec["model"], name=spec.get("name"), params=spec.get("params"))

def _load_live_prices(
    enabled: bool,
    fetcher: Optional[Callable[[], Dict[str, Any]]],
    logger,
) -> Optional[Dict[str, Any]]:
    """Read the live price list, or explain why the run falls back to metadata."""
    if not enabled and fetcher is None:
        return None
    try:
        book = live_price_book(fetcher, refresh=True)
    except Exception as exc:
        logger.warning(
            f"[pricing] live OpenRouter prices unavailable ({type(exc).__name__}: {exc}); "
            "falling back to the prices stored in configs/benchmarks/models.json"
        )
        return None
    logger.info(
        f"[pricing] live prices for {len(book.get('prices') or {})} models "
        f"read at {book.get('fetched_at')}"
    )
    return book


def _persist_price_book(book: Dict[str, Any], logger) -> None:
    """Archive the live price list this benchmark priced its runs against.

    Every benchmark therefore leaves behind the dated price book it used, so the
    history needed to reprice old runs accumulates without anyone remembering to
    run a sync.
    """
    fetched_at = str(book.get("fetched_at") or "")
    day = fetched_at[:10] or datetime.now(timezone.utc).date().isoformat()
    directory = os.path.join(_REPO_ROOT, "configs", "benchmarks", "pricing_history")
    path = os.path.join(directory, f"openrouter-{day}.json")
    if os.path.exists(path):
        return
    try:
        os.makedirs(directory, exist_ok=True)
        payload = {
            "provider": "openrouter",
            "synced_at": day,
            "fetched_at": fetched_at,
            "source": "openrouter_api",
            "currency": "USD_per_token",
            "models": {
                model_id: {
                    "prompt": rates.get("prompt"),
                    "completion": rates.get("completion"),
                }
                for model_id, rates in sorted((book.get("prices") or {}).items())
            },
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        logger.info(f"[pricing] archived today's price book to {path}")
    except OSError as exc:
        logger.warning(f"[pricing] could not archive the price book: {exc}")


def run_benchmark(
    prompt_slug: str,
    model_specs: List[Dict[str, Any]],
    client_factory: ClientFactory,
    repeats: int = 1,
    results_root: Optional[str] = None,
    logger=None,
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
    temperature: Optional[float] = _DEFAULT_TEMPERATURE,
    preflight_only: bool = False,
    price_fetcher: Optional[Callable[[], Dict[str, Any]]] = None,
    use_live_prices: bool = True,
) -> List[str]:
    logger = logger or setup_logger("hf_benchmark")
    results_root = results_root or os.path.join(_REPO_ROOT, "results")
    prompt_dir = os.path.join(results_root, "zero_shot", prompt_slug)
    prompt_path = os.path.join(prompt_dir, "prompt.txt")
    task_path = os.path.join(prompt_dir, "task.json")
    
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"prompt.txt not found: {prompt_path}")
    if not os.path.exists(task_path):
        raise FileNotFoundError(f"task.json not found: {task_path}")

    with open(prompt_path, "r", encoding="utf-8-sig") as f:
        prompt_text = f.read()
        
    task_params = _load_json(task_path)
    
    task_id = task_params.get("task_id", prompt_slug)
    task_set_version = task_params.get("task_set_version", "v1")

    weights = {k: task_params[k] for k in _WEIGHT_KEYS if k in task_params}
    env = _build_environment(task_params)
    used_score_version = env.get_score_function(task_params).VERSION
    total = len(model_specs) * repeats
    logger.info(f"Task '{task_id}' (Prompt '{prompt_slug}'): {len(model_specs)} models x {repeats} repeats = {total} runs.")

    # Prices are read live, once, at the start of the benchmark. Pricing a run
    # from the locally synced registry would attribute it to whatever rate was
    # true at the last manual sync, which can be weeks stale.
    live_prices = _load_live_prices(use_live_prices, price_fetcher, logger)
    if live_prices:
        _persist_price_book(live_prices, logger)

    written: List[str] = []
    done = 0
    out_dir = os.path.join(prompt_dir, "api_runs")
    os.makedirs(out_dir, exist_ok=True)
    
    for original_model in model_specs:
        model, preflight = _preflight_model(
            original_model,
            prompt_text,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        model_name = model.get("name") or model.get("model")
        model_id = model.get("model", model_name)
        preflight_message = _format_preflight(model_name, preflight)
        if preflight["status"] == "error":
            logger.error(preflight_message)
            continue
        logger.info(preflight_message)
        if preflight_only:
            continue

        fpath = os.path.join(out_dir, f"{_safe_name(model_name)}.jsonl")

        client = None
        client_err: Optional[str] = None
        try:
            client = client_factory(model)
        except Exception as e:
            client_err = f"{type(e).__name__}: {e}"
            logger.error(f"[{model_name}] client could not be instantiated: {client_err}")

        for r in range(repeats):
            done += 1
            progress = f"[{done}/{total}]"
            record: Dict[str, Any] = {
                "evaluation_mode": "zero_shot",
                "model_name": model_name,
                "model_id": model_id,
                "provider": model.get("provider"),
                "reasoning_mode": model.get("reasoning_mode"),
                "requested_params": copy.deepcopy(preflight["requested_params"]),
                "inference_params": copy.deepcopy(model.get("params", {})),
                "effective_params": copy.deepcopy(preflight["effective_params"]),
                "parameter_adjustments": list(preflight["adjustments"]),
                "model_metadata": copy.deepcopy(model.get("metadata", {})),
                "prompt_slug": prompt_slug,
                "task_id": task_id,
                "task_set_version": task_set_version,
                "environment": env.name,
                "score_version": used_score_version,
                "simulator_version": env.simulator.VERSION,
                "timestamp": _utcnow_iso(),
                "status": "client_error",
                "weights": weights,
                "task_params": dict(task_params),
                "prompt_text": prompt_text,
                "total_reward": 0.0,
                "reward_components": {},
                "metrics": {},
                "design": None,
                "raw_response": None,
                "latency_ms": 0.0,
                "prompt_tokens": None,
                "completion_tokens": None,
                # Full token accounting plus the price list that was in force
                # for this call, so the cost of a historical run stays
                # reconstructible after prices move.
                "usage": empty_usage(),
                "pricing_snapshot": (
                    snapshot_from_live(live_prices, model_id, model_name)
                    or price_snapshot(model.get("metadata"))
                ),
                "cost_usd": None,
                "cost_basis": None,
                "error": client_err,
            }

            if client is not None:
                try:
                    raw = client.generate_design(prompt_text)
                    record["raw_response"] = raw
                    record["latency_ms"] = getattr(client, "last_latency_ms", 0.0)
                    usage = getattr(client, "last_usage", None) or empty_usage()
                    record["usage"] = dict(usage)
                    # Legacy flat fields stay populated: older tooling reads them.
                    record["prompt_tokens"] = usage.get("prompt_tokens")
                    record["completion_tokens"] = usage.get("completion_tokens")
                    charged = usage.get("charged_cost_usd")
                    if charged is not None:
                        record["cost_usd"] = charged
                        record["cost_basis"] = "provider_charged"
                    else:
                        estimated = estimate_cost(usage, record["pricing_snapshot"])
                        record["cost_usd"] = estimated
                        record["cost_basis"] = (
                            "price_snapshot" if estimated is not None else None
                        )
                    record["model_id"] = getattr(client, "model", model_id)

                    design = None
                    if not raw or not raw.strip():
                        # Distinguish "the model had nothing to say" from "we cut
                        # it off mid-thought". A reasoning model that spends the
                        # whole budget thinking emits no answer tokens at all, and
                        # recording that as an empty response reads on the
                        # leaderboard as a design failure when it is a measurement
                        # failure — the run never happened. Observed on
                        # qwen3.8-27b at medium effort: 8192 completion tokens
                        # against an 8192 cap, twice out of two.
                        emitted = usage.get("completion_tokens") or 0
                        reasoned = usage.get("reasoning_tokens") or 0
                        limit = (record.get("effective_params") or {}).get("max_tokens") or                             (record.get("effective_params") or {}).get("max_completion_tokens")
                        if limit and max(emitted, reasoned) >= limit:
                            record["status"] = "token_limit"
                            record["error"] = (
                                "Output truncated at the {} token limit after {} reasoning "
                                "tokens; the model never reached an answer. Re-run with a "
                                "higher --max-output-tokens.".format(limit, reasoned)
                            )
                        else:
                            record["status"] = "empty_response"
                            record["error"] = "Model returned an empty response."
                    else:
                        try:
                            design = parse_llm_json(raw)
                            record["design"] = design
                        except Exception as e:
                            record["status"] = "parse_error"
                            record["error"] = f"{type(e).__name__}: {e}"

                    if design is not None:
                        design_id = f"{model_name}_{r}_{uuid.uuid4().hex[:6]}"
                        result = env.evaluate(task_id, task_params, design_id, design)
                        record["status"] = result.status
                        record["total_reward"] = float(result.score.normalized_total)
                        record["reward_components"] = dict(result.score.components)
                        record["metrics"] = dict(result.metrics)
                        record["error"] = result.error_message
                except Exception as e:
                    record["status"] = "client_error"
                    record["error"] = f"{type(e).__name__}: {e}"

            with open(fpath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written.append(fpath)
            logger.info(f"{progress} {model_name} | r{r} -> {record['status']} score={record['total_reward']:.3f}")

    logger.info(f"Done for task {task_id}.")
    return written

def _select_models(all_models: List[dict], selection: Optional[List[str]], provider: Optional[str] = None) -> List[dict]:
    if provider:
        all_models = [m for m in all_models if m.get("provider", "hf") == provider]

    filtered_models = all_models
    if selection:
        wanted = {s.strip() for s in selection}
        filtered_models = [m for m in all_models if (m.get("name") or m.get("model")) in wanted]
        missing = wanted - {(m.get("name") or m.get("model")) for m in filtered_models}
        if missing:
            raise SystemExit(f"No model matching the criteria in models.json was found: {sorted(missing)}")
            
    # Deduplicate by name, preferring standard/paid models over :free to avoid stale free endpoints
    deduped = {}
    for m in filtered_models:
        name = m.get("name") or m.get("model")
        model_id = m.get("model", "")
        if name not in deduped:
            deduped[name] = m
        else:
            existing_model_id = deduped[name].get("model", "")
            if ":free" in existing_model_id.lower() and ":free" not in model_id.lower():
                deduped[name] = m
                
    return list(deduped.values())


def main():
    parser = argparse.ArgumentParser(description="Automated benchmark for prompt x model using LLM APIs.")
    parser.add_argument(
        "--prompt",
        required=True,
        help="results/zero_shot/<slug> folder name (contains prompt.txt).",
    )
    parser.add_argument("--models", type=str, default=None, help="Comma-separated model 'name' list.")
    parser.add_argument("--model", type=str, default=None, help="A single model 'name' (shortcut for --models).")
    parser.add_argument("--provider", type=str, default=None, help="Provider name to filter models.")
    parser.add_argument("--repeats", type=int, default=1, help="How many runs per model in this execution.")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=_DEFAULT_MAX_OUTPUT_TOKENS,
        help="Shared output-token budget before model-specific safety clamping.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=_DEFAULT_TEMPERATURE,
        help="Shared sampling temperature; omitted automatically when unsupported.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate and print effective model parameters without making API calls.",
    )
    parser.add_argument(
        "--offline-prices",
        action="store_true",
        help=(
            "Do not read live prices from the OpenRouter API; price runs from "
            "configs/benchmarks/models.json instead."
        ),
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=_REASONING_EFFORTS,
        default=None,
        help=(
            "Set reasoning effort at run time. When provided, result model names "
            "receive a '__reasoning-<effort>' suffix."
        ),
    )
    parser.add_argument("--models-config", type=str, default=os.path.join(_REPO_ROOT, "configs", "benchmarks", "models.json"))
    args = parser.parse_args()

    logger = setup_logger("hf_benchmark")
    config_data = _load_json(args.models_config)
    
    all_models = []
    if "providers" in config_data:
        for prov_name, prov_models in config_data["providers"].items():
            for m in prov_models:
                m["provider"] = prov_name
                all_models.append(m)
    elif "models" in config_data:
        all_models = config_data["models"]

    if not all_models:
        raise SystemExit(f"No models in models.json or could not read: {args.models_config}")

    selection = None
    if args.model: selection = [args.model]
    elif args.models: selection = [s for s in args.models.split(",") if s.strip()]
    model_specs = _select_models(all_models, selection, args.provider)
    model_specs = _configure_reasoning(
        model_specs,
        requested_effort=args.reasoning_effort,
        interactive=sys.stdin.isatty() and args.reasoning_effort is None,
    )

    if args.max_output_tokens <= 0:
        parser.error("--max-output-tokens must be positive")

    prompt_slugs = [p.strip() for p in args.prompt.split(",") if p.strip()]
    
    for prompt_slug in prompt_slugs:
        run_benchmark(
            prompt_slug=prompt_slug,
            model_specs=model_specs,
            client_factory=multi_client_factory,
            repeats=args.repeats,
            logger=logger,
            max_output_tokens=args.max_output_tokens,
            temperature=args.temperature,
            preflight_only=args.preflight_only,
            use_live_prices=not args.offline_prices,
        )

if __name__ == "__main__":
    main()
