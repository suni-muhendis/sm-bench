import os
import time
from typing import Any, Dict, Optional

from sm_bench.model_clients.base import BaseModelClient
from sm_bench.model_clients.usage import empty_usage, extract_usage

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

class OpenRouterClient(BaseModelClient):
    """
    Client calling the model via OpenRouter API (OpenAI compatible).
    Token is read from `.env`/environment `OPENROUTER_API_KEY`.
    """

    def __init__(
        self,
        model: str,
        name: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 180.0,
        max_retries: int = 3,
        backoff_factor: float = 3.0,
        auto_fallback_free: bool = True,
        usage_accounting: bool = True,
    ):
        super().__init__(name or model)
        self.model = model
        self.params = params or {}
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.auto_fallback_free = auto_fallback_free
        # OpenRouter reports what it actually billed when usage accounting is
        # requested, which beats any price-list estimate we could compute.
        self.usage_accounting = usage_accounting

        self.last_latency_ms: float = 0.0
        self.last_prompt_tokens: Optional[int] = None
        self.last_completion_tokens: Optional[int] = None
        self.last_usage: Dict[str, Any] = empty_usage()

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{api_key_env} not found. Add {api_key_env} to your .env file."
            )

        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise ImportError("pip install openai") from e

        # OpenRouter recommendation: Send HTTP-Referer and X-Title via Headers.
        default_headers = {
            "HTTP-Referer": "https://github.com/suni-muhendis/sm-bench", # Your site address or repository link
            "X-Title": "Heat Exchanger Benchmark"
        }

        self._client = OpenAI(
            base_url=base_url, 
            api_key=api_key, 
            timeout=timeout,
            default_headers=default_headers
        )

    def generate_design(self, prompt: str) -> str:
        for attempt in range(self.max_retries):
            try:
                # The caller may already be sending an extra_body of its own —
                # reasoning effort and provider routing both travel that way —
                # so merge into it rather than passing a second one, which
                # collides as a duplicate keyword argument.
                params = dict(self.params)
                extra_body = dict(params.pop("extra_body", None) or {})
                if self.usage_accounting:
                    extra_body.setdefault("usage", {"include": True})

                start = time.perf_counter()
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body=extra_body,
                    **params,
                )
                self.last_latency_ms = (time.perf_counter() - start) * 1000

                self.last_usage = extract_usage(resp)
                self.last_prompt_tokens = self.last_usage["prompt_tokens"]
                self.last_completion_tokens = self.last_usage["completion_tokens"]

                return resp.choices[0].message.content or ""
            except Exception as e:
                err_str = str(e).lower()

                # 1. 404 / Free unavailable fallback: automatically fall back to base model
                if self.auto_fallback_free and ":free" in self.model.lower():
                    if "404" in err_str or "unavailable for free" in err_str or "not found" in err_str:
                        fallback_model = self.model.replace(":free", "")
                        print(
                            f"[OpenRouterClient] Warning: '{self.model}' is unavailable for free. "
                            f"Falling back to '{fallback_model}'..."
                        )
                        self.model = fallback_model
                        continue

                # 2. 429 Rate limit retry: wait with backoff
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and attempt < self.max_retries - 1:
                    sleep_time = self.backoff_factor * (attempt + 1)
                    print(
                        f"[OpenRouterClient] Rate limited (429) on '{self.model}'. "
                        f"Retrying in {sleep_time:.1f}s (attempt {attempt + 1}/{self.max_retries})..."
                    )
                    time.sleep(sleep_time)
                    continue

                raise
        return ""
