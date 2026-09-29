import json
import inspect
import os
from pathlib import Path

import pytest

from scripts.run_api_benchmark import (
    _DEFAULT_MAX_OUTPUT_TOKENS,
    _apply_reasoning_effort,
    _configure_reasoning,
    _preflight_model,
    _prompt_reasoning_effort,
    _reasoning_choices,
    _safe_name,
    _select_models,
    run_benchmark,
)
from sunimuhendis.model_clients.dummy_random import DummyRandomClient
from sunimuhendis.model_clients.hf_client import HFInferenceClient
from sunimuhendis.model_clients.opencode_client import OpenCodeClient
from sunimuhendis.model_clients.openrouter_client import OpenRouterClient

@pytest.fixture(autouse=True)
def _isolate_repo_root(tmp_path, monkeypatch):
    """Keep run_benchmark from archiving price books into the real repository."""
    import scripts.run_api_benchmark as runner

    monkeypatch.setattr(runner, "_REPO_ROOT", str(tmp_path))


_VALID_STATUS = {
    "success", "schema_error", "drc_error", "simulation_error",
    "parse_error", "empty_response", "client_error", "token_limit",
}


def _make_prompt_unit(root, slug="he_test", **task_overrides):
    prompt_dir = os.path.join(root, "zero_shot", slug)
    os.makedirs(prompt_dir, exist_ok=True)
    with open(os.path.join(prompt_dir, "prompt.txt"), "w", encoding="utf-8") as f:
        f.write("Design a heat exchanger. Output ONLY valid JSON.")
    task = {
        "task_id": "he_test_001",
        "w_heat": 0.4, "w_drop_tube": 0.05, "w_drop_shell": 0.05,
        "w_eff": 0.2, "w_cost": 0.3,
        "target_heat_duty": 150000.0, "max_dp_tube": 50000.0, "max_dp_shell": 50000.0,
    }
    task.update(task_overrides)
    with open(os.path.join(prompt_dir, "task.json"), "w", encoding="utf-8") as f:
        json.dump(task, f)
    return slug


def test_run_benchmark_offline(tmp_path):
    slug = _make_prompt_unit(str(tmp_path))
    specs = [{"name": "dummy-A"}, {"name": "dummy-B"}]

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=specs,
        client_factory=lambda spec: DummyRandomClient(),
        repeats=2,
        results_root=str(tmp_path),
    )

    # 2 model = 2 run dosyasi (her biri jsonl)
    assert len(set(written)) == 2
    for p in written:
        assert os.path.exists(p)
        assert p.endswith(".jsonl")

    rec = json.loads(open(written[0], encoding="utf-8").readline())
    for field in ("model_name", "prompt_slug", "task_id", "status",
                  "total_reward", "weights", "metrics", "design"):
        assert field in rec
    assert rec["status"] in _VALID_STATUS
    assert rec["prompt_slug"] == slug
    assert rec["weights"]["w_heat"] == 0.4


@pytest.mark.parametrize("task_overrides, score_version", [
    # A task that names neither is a heat-exchanger task scored with V1,
    # exactly as every task recorded before tasks named their environment.
    ({}, "heat_exchanger_score_v1"),
    ({"environment": "heat_exchanger", "score_version": "heat_exchanger_score_v4"},
     "heat_exchanger_score_v4"),
])
def test_run_benchmark_records_environment_and_versions(tmp_path, task_overrides, score_version):
    slug = _make_prompt_unit(str(tmp_path), **task_overrides)
    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "dummy"}],
        client_factory=lambda spec: DummyRandomClient(),
        repeats=1,
        results_root=str(tmp_path),
    )
    rec = json.loads(open(written[0], encoding="utf-8").readline())
    assert rec["environment"] == "heat_exchanger"
    assert rec["simulator_version"] == "v4"
    assert rec["score_version"] == score_version


def test_run_benchmark_rejects_an_unknown_environment(tmp_path):
    slug = _make_prompt_unit(str(tmp_path), environment="no_such_environment")
    with pytest.raises(KeyError, match="no_such_environment"):
        run_benchmark(
            prompt_slug=slug,
            model_specs=[{"name": "dummy"}],
            client_factory=lambda spec: DummyRandomClient(),
            repeats=1,
            results_root=str(tmp_path),
        )


def test_run_benchmark_client_error_isolated(tmp_path):
    slug = _make_prompt_unit(str(tmp_path))

    def boom_factory(spec):
        raise RuntimeError("no token")

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "broken"}],
        client_factory=boom_factory,
        repeats=1,
        results_root=str(tmp_path),
    )
    assert len(written) == 1
    rec = json.loads(open(written[0], encoding="utf-8").read())
    assert rec["status"] == "client_error"
    assert rec["error"]


@pytest.mark.parametrize("raw", ["", "   \n\t"])
def test_run_benchmark_records_empty_response_separately(tmp_path, raw):
    slug = _make_prompt_unit(str(tmp_path))

    class EmptyClient:
        def generate_design(self, prompt):
            return raw

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "empty"}],
        client_factory=lambda spec: EmptyClient(),
        repeats=1,
        results_root=str(tmp_path),
    )

    rec = json.loads(open(written[0], encoding="utf-8").read())
    assert rec["status"] == "empty_response"
    assert rec["raw_response"] == raw
    assert rec["error"] == "Model returned an empty response."


@pytest.mark.parametrize(
    "client_class",
    [HFInferenceClient, OpenCodeClient, OpenRouterClient],
)
def test_api_clients_default_to_three_minute_timeout(client_class):
    timeout = inspect.signature(client_class.__init__).parameters["timeout"].default
    assert timeout == 180.0


def test_run_benchmark_preflight_failure_makes_no_client_calls(tmp_path):
    slug = _make_prompt_unit(str(tmp_path))
    calls = []
    spec = {
        "name": "unsafe-router",
        "metadata": {
            "context_length": 100000,
            "supported_parameters": ["temperature"],
        },
    }

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[spec],
        client_factory=lambda model: calls.append(model),
        repeats=20,
        results_root=str(tmp_path),
    )

    assert written == []
    assert calls == []


def test_select_models():
    all_models = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    assert _select_models(all_models, None) == all_models
    assert _select_models(all_models, ["b"]) == [{"name": "b"}]


def test_safe_name():
    assert _safe_name("Claude Opus 4.8") == "Claude Opus 4.8"
    assert _safe_name("a/b") == "a_b"


def test_apply_reasoning_effort_creates_distinct_run_variant():
    original = [{
        "name": "kimi-k2.6",
        "model": "moonshotai/kimi-k2.6",
        "provider": "openrouter",
        "params": {"temperature": 0.7, "max_tokens": 8192},
    }]

    configured = _apply_reasoning_effort(original, "none")

    assert configured[0]["name"] == "kimi-k2.6__reasoning-none"
    assert configured[0]["reasoning_mode"] == "none"
    extra_body = configured[0]["params"]["extra_body"]
    assert extra_body["reasoning"] == {"effort": "none"}
    assert extra_body["provider"]["require_parameters"] is True
    assert "extra_body" not in original[0]["params"]


def test_apply_reasoning_effort_omitted_keeps_model_name():
    original = [{"name": "plain", "params": {"temperature": 0.7}}]
    assert _apply_reasoning_effort(original, None) == original


def test_apply_default_reasoning_only_changes_variant_name():
    original = [{"name": "model-a", "provider": "openrouter", "params": {}}]
    configured = _apply_reasoning_effort(original, "default")
    assert configured[0]["name"] == "model-a__reasoning-default"
    assert configured[0]["reasoning_mode"] == "default"
    assert configured[0]["params"] == {}


def test_reasoning_choices_use_synced_capabilities():
    kimi = {
        "metadata": {
            "supported_parameters": ["reasoning"],
            "reasoning": {"mandatory": False, "default_enabled": True},
        }
    }
    assert _reasoning_choices(kimi) == ["default", "none"]

    model_with_levels = {
        "metadata": {
            "supported_parameters": ["reasoning", "reasoning_effort"],
            "reasoning": {
                "mandatory": False,
                "default_effort": "medium",
                "supported_efforts": ["high", "medium", "low", "none"],
            },
        }
    }
    assert _reasoning_choices(model_with_levels) == [
        "default", "high", "medium", "low", "none",
    ]


def test_prompt_reasoning_effort_uses_numbered_choice():
    spec = {
        "name": "kimi-k2.6",
        "metadata": {
            "supported_parameters": ["reasoning"],
            "reasoning": {"mandatory": False, "default_enabled": True},
        },
    }
    output = []
    selected = _prompt_reasoning_effort(
        spec,
        input_func=lambda prompt: "2",
        print_func=output.append,
    )
    assert selected == "none"
    assert any("Reasoning mode for kimi-k2.6" in line for line in output)


def test_configure_reasoning_rejects_unadvertised_effort():
    spec = {
        "name": "kimi-k2.6",
        "metadata": {
            "supported_parameters": ["reasoning"],
            "reasoning": {"mandatory": False, "default_enabled": True},
        },
    }
    with pytest.raises(SystemExit, match="not advertised"):
        _configure_reasoning([spec], requested_effort="low", interactive=False)


def test_preflight_clamps_limits_and_omits_unsupported_temperature():
    spec = {
        "name": "small-output-model",
        "params": {"temperature": 0.1, "max_tokens": 99999},
        "metadata": {
            "context_length": 131072,
            "max_completion_tokens": 4096,
            "supported_parameters": ["max_tokens"],
        },
    }

    configured, report = _preflight_model(
        spec,
        "short prompt",
        max_output_tokens=8192,
        temperature=0.7,
    )

    assert report["status"] == "ready"
    assert report["effective_params"] == {"max_tokens": 4096}
    assert configured["params"] == {"max_tokens": 4096}
    assert any("model maximum 4096" in item for item in report["adjustments"])
    assert any("temperature omitted" in item for item in report["adjustments"])


def test_preflight_rejects_model_without_token_limit_support():
    spec = {
        "name": "unbounded-router",
        "metadata": {
            "context_length": 1000000,
            "max_completion_tokens": None,
            "supported_parameters": ["temperature"],
        },
    }
    _, report = _preflight_model(spec, "prompt")
    assert report["status"] == "error"
    assert any("fixed-budget run is unsafe" in item for item in report["errors"])


def test_preflight_uses_max_completion_tokens_when_required():
    spec = {
        "name": "completion-limit-model",
        "metadata": {
            "context_length": 100000,
            "max_completion_tokens": 12000,
            "supported_parameters": ["max_completion_tokens", "temperature"],
        },
    }
    configured, report = _preflight_model(spec, "prompt")
    assert report["status"] == "ready"
    assert configured["params"]["max_completion_tokens"] == _DEFAULT_MAX_OUTPUT_TOKENS
    assert "max_tokens" not in configured["params"]


def test_preflight_clamps_to_context_budget():
    spec = {
        "name": "tiny-context",
        "metadata": {
            "context_length": 1000,
            "max_completion_tokens": 900,
            "supported_parameters": ["max_tokens", "temperature"],
        },
    }
    _, report = _preflight_model(spec, "x" * 1200, max_output_tokens=900)
    assert report["status"] == "ready"
    assert report["effective_params"]["max_tokens"] == 344


@pytest.mark.parametrize(
    ("slug", "score_version"),
    [
        ("heat_exchanger_v1", "heat_exchanger_score_v1"),
        ("heat_exchanger_v2", "heat_exchanger_score_v1"),
        ("heat_exchanger_v3", "heat_exchanger_score_v1"),
        ("heat_exchanger_v4", "heat_exchanger_score_v1"),
        ("heat_exchanger_hard_v1", "heat_exchanger_score_v1"),
        ("heat_exchanger_hard_v2", "heat_exchanger_score_v3"),
    ],
)
def test_active_prompt_targets_match_task(slug, score_version):
    root = Path(__file__).resolve().parents[1]
    unit = root / "results" / "zero_shot" / slug
    prompt = (unit / "prompt.txt").read_text(encoding="utf-8-sig")
    task = json.loads((unit / "task.json").read_text(encoding="utf-8-sig"))
    details = prompt.split("Task Details:", 1)[1].lstrip()
    stated, _ = json.JSONDecoder().raw_decode(details)
    for key, value in stated.items():
        assert task[key] == value
    assert task.get("score_version", "heat_exchanger_score_v1") == score_version


def test_benchmark_sends_and_records_paired_prompt(tmp_path):
    slug = _make_prompt_unit(str(tmp_path))
    expected = (tmp_path / "zero_shot" / slug / "prompt.txt").read_text()
    received = []

    class CapturingClient:
        def generate_design(self, prompt):
            received.append(prompt)
            return "{}"

    paths = run_benchmark(
        prompt_slug=slug, model_specs=[{"name": "capture"}],
        client_factory=lambda spec: CapturingClient(), results_root=str(tmp_path),
    )
    assert received == [expected]
    assert Path(paths[0]).parent == tmp_path / "zero_shot" / slug / "api_runs"
    record = json.loads(Path(paths[0]).read_text())
    assert record["evaluation_mode"] == "zero_shot"
    assert record["prompt_text"] == expected
    assert record["task_params"]["target_heat_duty"] == 150000.0
    assert record["score_version"] == "heat_exchanger_score_v1"
    assert record["requested_params"] == {
        "max_tokens": _DEFAULT_MAX_OUTPUT_TOKENS, "temperature": 0.7}
    assert record["inference_params"] == {
        "max_tokens": _DEFAULT_MAX_OUTPUT_TOKENS, "temperature": 0.7}
    assert record["effective_params"] == {
        "max_tokens": _DEFAULT_MAX_OUTPUT_TOKENS, "temperature": 0.7}
    assert record["parameter_adjustments"] == []
    assert record["model_metadata"] == {}
    assert record["reasoning_mode"] is None


def test_run_benchmark_records_token_accounting_and_frozen_prices(tmp_path):
    """Every run is a receipt: tokens, the price list used, and the cost."""
    slug = _make_prompt_unit(str(tmp_path))

    class _PricedClient(DummyRandomClient):
        def __init__(self):
            super().__init__()
            self.last_latency_ms = 1234.0
            self.last_usage = {
                "prompt_tokens": 1000,
                "completion_tokens": 400,
                "reasoning_tokens": 250,
                "cached_prompt_tokens": 32,
                "total_tokens": 1400,
                "charged_cost_usd": None,
            }

    spec = {
        "name": "priced-model",
        "model": "vendor/m",
        "metadata": {
            "context_length": 32000,
            "max_completion_tokens": 4096,
            "supported_parameters": ["max_tokens", "temperature"],
            "pricing": {"prompt": "0.000001", "completion": "0.000003"},
            "pricing_source": "openrouter",
            "pricing_synced_at": "2026-09-18",
        },
    }

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[spec],
        client_factory=lambda _spec: _PricedClient(),
        repeats=1,
        results_root=str(tmp_path),
    )

    with open(written[0], "r", encoding="utf-8") as handle:
        record = json.loads(handle.readline())

    assert record["usage"]["reasoning_tokens"] == 250
    assert record["usage"]["total_tokens"] == 1400
    # Legacy flat fields stay populated for older tooling.
    assert record["prompt_tokens"] == 1000
    assert record["completion_tokens"] == 400
    assert record["pricing_snapshot"]["prompt_usd_per_token"] == 1e-6
    assert record["pricing_snapshot"]["synced_at"] == "2026-09-18"
    assert record["cost_usd"] == pytest.approx(1000 * 1e-6 + 400 * 3e-6)
    assert record["cost_basis"] == "price_snapshot"


def test_run_benchmark_prefers_the_cost_the_provider_charged(tmp_path):
    slug = _make_prompt_unit(str(tmp_path), slug="he_charged")

    class _ChargedClient(DummyRandomClient):
        def __init__(self):
            super().__init__()
            self.last_usage = {
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "reasoning_tokens": None,
                "cached_prompt_tokens": None,
                "total_tokens": 20,
                "charged_cost_usd": 0.99,
            }

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "charged", "model": "vendor/m"}],
        client_factory=lambda _spec: _ChargedClient(),
        repeats=1,
        results_root=str(tmp_path),
    )

    with open(written[0], "r", encoding="utf-8") as handle:
        record = json.loads(handle.readline())

    assert record["cost_usd"] == 0.99
    assert record["cost_basis"] == "provider_charged"


def test_run_benchmark_keeps_accounting_for_a_failed_client(tmp_path):
    """A client that never answered still produces an auditable zero-usage line."""
    slug = _make_prompt_unit(str(tmp_path), slug="he_broken")

    def _explode(_spec):
        raise RuntimeError("no credentials")

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "broken", "model": "vendor/m"}],
        client_factory=_explode,
        repeats=1,
        results_root=str(tmp_path),
    )

    with open(written[0], "r", encoding="utf-8") as handle:
        record = json.loads(handle.readline())

    assert record["status"] == "client_error"
    assert record["usage"]["prompt_tokens"] is None
    assert record["cost_usd"] is None


def test_run_benchmark_freezes_the_live_price_not_the_local_registry(tmp_path):
    """The rate a run records must be the one the provider quoted at run time."""
    slug = _make_prompt_unit(str(tmp_path), slug="he_live_price")

    class _PricedClient(DummyRandomClient):
        def __init__(self):
            super().__init__()
            self.last_usage = {
                "prompt_tokens": 1000,
                "completion_tokens": 1000,
                "reasoning_tokens": None,
                "cached_prompt_tokens": None,
                "total_tokens": 2000,
                "charged_cost_usd": None,
            }

    def _live_prices():
        return {
            "source": "openrouter_api",
            "fetched_at": "2026-09-18T10:00:00Z",
            "prices": {"vendor/m": {"prompt": 5e-6, "completion": 5e-6}},
        }

    spec = {
        "name": "live-priced",
        "model": "vendor/m",
        "metadata": {
            "context_length": 32000,
            "supported_parameters": ["max_tokens", "temperature"],
            # Deliberately stale local prices: the live list must win.
            "pricing": {"prompt": "0.000001", "completion": "0.000001"},
            "pricing_synced_at": "2026-01-01",
        },
    }

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[spec],
        client_factory=lambda _spec: _PricedClient(),
        repeats=1,
        results_root=str(tmp_path),
        price_fetcher=_live_prices,
    )

    with open(written[0], "r", encoding="utf-8") as handle:
        record = json.loads(handle.readline())

    snapshot = record["pricing_snapshot"]
    assert snapshot["source"] == "openrouter_api"
    assert snapshot["prompt_usd_per_token"] == 5e-6
    assert snapshot["synced_at"] == "2026-09-18T10:00:00Z"
    assert record["cost_usd"] == pytest.approx(0.01)


def test_run_benchmark_falls_back_to_local_prices_when_the_api_is_unreachable(tmp_path):
    slug = _make_prompt_unit(str(tmp_path), slug="he_offline_price")

    def _offline():
        raise OSError("network unreachable")

    spec = {
        "name": "offline",
        "model": "vendor/m",
        "metadata": {
            "context_length": 32000,
            "supported_parameters": ["max_tokens", "temperature"],
            "pricing": {"prompt": "0.000002", "completion": "0.000002"},
            "pricing_source": "openrouter",
            "pricing_synced_at": "2026-01-01",
        },
    }

    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[spec],
        client_factory=lambda _spec: DummyRandomClient(),
        repeats=1,
        results_root=str(tmp_path),
        price_fetcher=_offline,
    )

    with open(written[0], "r", encoding="utf-8") as handle:
        record = json.loads(handle.readline())

    # The run still records a defensible price, clearly attributed to the sync.
    assert record["pricing_snapshot"]["prompt_usd_per_token"] == 2e-6
    assert record["pricing_snapshot"]["synced_at"] == "2026-01-01"


def test_run_benchmark_archives_the_price_book_it_used(tmp_path, monkeypatch):
    """Each benchmark leaves behind the dated price list it priced runs against."""
    import scripts.run_api_benchmark as runner

    monkeypatch.setattr(runner, "_REPO_ROOT", str(tmp_path))
    slug = _make_prompt_unit(str(tmp_path), slug="he_archive")

    run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "m", "model": "vendor/m"}],
        client_factory=lambda _spec: DummyRandomClient(),
        repeats=1,
        results_root=str(tmp_path),
        price_fetcher=lambda: {
            "source": "openrouter_api",
            "fetched_at": "2026-09-18T10:00:00Z",
            "prices": {"vendor/m": {"prompt": 1e-6, "completion": 2e-6}},
        },
    )

    archived = tmp_path / "configs" / "benchmarks" / "pricing_history" / "openrouter-2026-09-18.json"
    assert archived.exists()
    payload = json.loads(archived.read_text(encoding="utf-8"))
    assert payload["fetched_at"] == "2026-09-18T10:00:00Z"
    assert payload["models"]["vendor/m"]["completion"] == 2e-6


# ── Truncation is an instrument failure, not a design failure ─────────
#
# A reasoning model can spend the entire output budget thinking and emit no
# answer tokens at all. Recorded as "empty_response" that reads on the
# leaderboard as a model unable to produce a design, when in fact the run never
# happened. Observed on qwen3.8-27b at medium effort against heat_exchanger_hard_v4:
# 8192 completion tokens against an 8192 cap, on both of two runs.


class _TruncatedClient:
    """Spends the whole budget reasoning and returns nothing."""

    model = "dummy/truncated"

    def __init__(self, cap):
        self._cap = cap

    def generate_design(self, prompt):
        self.last_latency_ms = 1.0
        self.last_usage = {
            "prompt_tokens": 100,
            "completion_tokens": self._cap,
            "reasoning_tokens": self._cap + 4,
            "total_tokens": self._cap + 100,
        }
        return ""


class _SilentClient:
    """Returns nothing, having spent nothing."""

    model = "dummy/silent"

    def generate_design(self, prompt):
        self.last_latency_ms = 1.0
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 0,
                           "reasoning_tokens": 0, "total_tokens": 100}
        return ""


def _one_run(tmp_path, client, cap=8192):
    slug = _make_prompt_unit(str(tmp_path))
    written = run_benchmark(
        prompt_slug=slug,
        model_specs=[{"name": "m"}],
        client_factory=lambda spec: client,
        repeats=1,
        results_root=str(tmp_path),
        max_output_tokens=cap,
    )
    return json.loads(open(written[0], encoding="utf-8").readline())


def test_output_truncated_at_the_cap_is_recorded_as_token_limit(tmp_path):
    record = _one_run(tmp_path, _TruncatedClient(4096), cap=4096)
    assert record["status"] == "token_limit"
    assert "truncated" in record["error"].lower()
    assert "4096" in record["error"]


def test_a_genuinely_empty_response_is_still_an_empty_response(tmp_path):
    record = _one_run(tmp_path, _SilentClient())
    assert record["status"] == "empty_response"


def test_truncation_is_distinguishable_after_the_fact(tmp_path):
    """
    The two are told apart by usage, so an analysis can exclude truncated runs
    from a leaderboard without re-running them.
    """
    truncated = _one_run(tmp_path / "a", _TruncatedClient(2048), cap=2048)
    empty = _one_run(tmp_path / "b", _SilentClient())
    assert truncated["status"] != empty["status"]
    assert truncated["usage"]["completion_tokens"] >= 2048
    assert empty["usage"]["completion_tokens"] == 0
