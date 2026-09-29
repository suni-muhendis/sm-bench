import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sm_bench.model_clients.base import BaseModelClient
from sm_heat_exchanger.samplers.random_sampler import RandomSampler

class DummyRandomClient(BaseModelClient):
    def __init__(self):
        super().__init__("DummyRandomClient")
        self.sampler = RandomSampler()

    def generate_design(self, prompt: str) -> str:
        # Ignore the prompt completely, just generate a random design
        design = self.sampler.sample(1)[0]
        # Return it as a JSON string to simulate an LLM text output
        # Add backticks to simulate LLM markdown format
        return f"```json\n{json.dumps(design, indent=2)}\n```"
