import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sm_bench.model_clients.base import BaseModelClient
from sm_heat_exchanger.samplers.heuristic_sampler import HeuristicSampler

class HeuristicClient(BaseModelClient):
    def __init__(self):
        super().__init__("HeuristicClient")
        self.sampler = HeuristicSampler()

    def generate_design(self, prompt: str) -> str:
        design = self.sampler.sample(1)[0]
        return f"```json\n{json.dumps(design, indent=2)}\n```"
