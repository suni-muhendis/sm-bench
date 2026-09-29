import os
import time
from typing import Any, Dict, Optional

from sm_bench.model_clients.base import BaseModelClient

OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"

class OpenCodeClient(BaseModelClient):
    """
    Client calling the model via OpenCode API (OpenAI compatible).
    Token is read from `.env`/environment `OPENCODE_API_KEY`.
    """

    def __init__(
        self,
        model: str,
        name: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        api_key_env: str = "OPENCODE_API_KEY",
        base_url: str = OPENCODE_BASE_URL,
        timeout: float = 180.0,
    ):
        super().__init__(name or model)
        self.model = model
        self.params = params or {}

        self.last_latency_ms: float = 0.0
        self.last_prompt_tokens: Optional[int] = None
        self.last_completion_tokens: Optional[int] = None

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{api_key_env} not found. Add {api_key_env} to your .env file."
            )

        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise ImportError("pip install openai") from e

        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    def generate_design(self, prompt: str) -> str:
        start = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **self.params,
        )
        self.last_latency_ms = (time.perf_counter() - start) * 1000

        if resp.usage:
            self.last_prompt_tokens = getattr(resp.usage, "prompt_tokens", None)
            self.last_completion_tokens = getattr(resp.usage, "completion_tokens", None)

        return resp.choices[0].message.content or ""
