"""Run an open-weight model locally with Hugging Face transformers (and PEFT adapters).

For models no API serves, such as a LoRA adapter on top of a base model. The model
is loaded once per client; every prompt is sent as a single user chat message
and decoded greedily, one prompt at a time, so the output does not depend on
batch padding. Needs a GPU and the optional ``local`` extra
(``pip install -e .[local]``).

Model spec (``configs/benchmarks/models.json``, provider ``local``)::

    {"name": "SM_heat_exchanger_v1",
     "model": "Qwen/Qwen2.5-7B-Instruct",
     "params": {"adapter": "SM-AI/SM_heat_exchanger_v1"}}
"""
import time
from typing import Any, Dict, Optional

from sm_bench.model_clients.base import BaseModelClient
from sm_bench.model_clients.usage import empty_usage

_DEFAULT_MAX_NEW_TOKENS = 8192


class TransformersClient(BaseModelClient):
    def __init__(self, model: str, name: Optional[str] = None,
                 params: Optional[Dict[str, Any]] = None):
        super().__init__(name or model)
        self.model = model
        self.params = dict(params or {})
        self.adapter = self.params.get("adapter")
        self.revision = self.params.get("revision")
        self.adapter_revision = self.params.get("adapter_revision")
        self.max_new_tokens = int(
            self.params.get("max_tokens")
            or self.params.get("max_completion_tokens")
            or _DEFAULT_MAX_NEW_TOKENS
        )
        self.last_latency_ms: float = 0.0
        self.last_prompt_tokens: Optional[int] = None
        self.last_completion_tokens: Optional[int] = None
        self.last_usage: Dict[str, Any] = empty_usage()
        self._load()

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # The adapter repo ships the tokenizer and chat template it was trained with.
        tok_source = self.adapter or self.model
        tok_revision = self.adapter_revision if self.adapter else self.revision
        self.tokenizer = AutoTokenizer.from_pretrained(tok_source, revision=tok_revision)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            self.model, revision=self.revision, device_map="auto", dtype=torch.bfloat16,
        )
        if self.adapter:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, self.adapter, revision=self.adapter_revision)
        model.eval()
        self._torch = torch
        self._model = model

    def generate_design(self, prompt: str) -> str:
        torch = self._torch
        text = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True,
        )
        enc = self.tokenizer(text, return_tensors="pt", add_special_tokens=False)
        enc = enc.to(self._model.device)
        start = time.perf_counter()
        with torch.no_grad():
            out = self._model.generate(
                **enc, max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        self.last_latency_ms = (time.perf_counter() - start) * 1000.0
        new = out[0, enc["input_ids"].shape[1]:]
        self.last_prompt_tokens = int(enc["input_ids"].shape[1])
        self.last_completion_tokens = int(new.shape[0])
        usage = empty_usage()
        usage.update(prompt_tokens=self.last_prompt_tokens,
                     completion_tokens=self.last_completion_tokens,
                     total_tokens=self.last_prompt_tokens + self.last_completion_tokens)
        self.last_usage = usage
        return self.tokenizer.decode(new, skip_special_tokens=True)
