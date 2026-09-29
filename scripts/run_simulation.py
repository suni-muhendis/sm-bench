import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sm_core import BaseSimulator
from sm_core import BaseScoreFunction
from sm_core import BaseEnvironment
from sm_core import EvaluationResult, ScoreResult
from sm_bench.logging import setup_logger, save_evaluation_result
from typing import Dict, Any, Tuple, Optional

class DummySimulator(BaseSimulator):
    def simulate(self, design_params: Dict[str, Any]) -> Tuple[bool, Dict[str, float], Dict[str, Any], str]:
        if design_params.get("fail_sim", False):
            return False, {}, {}, "Error occurred during simulation."
        if design_params.get("crash_sim", False):
            raise RuntimeError("Unexpected crash!")
        
        metrics = {"score": design_params.get("value", 0) * 2.0}
        return True, metrics, {"details": "Dummy simulation completed"}, ""

class DummyReward(BaseScoreFunction):
    def calculate_score(self, task_params: Dict[str, Any], metrics: Dict[str, float], is_valid: bool = True, error_message: Optional[str] = None) -> ScoreResult:
        if not is_valid:
            return ScoreResult(normalized_total=0.0, is_valid=False, error_message=error_message)
        
        score = metrics.get("score", 0.0)
        norm_score = min(max(score / 100.0, 0.0), 1.0)
        return ScoreResult(normalized_total=norm_score, components={"main": norm_score}, is_valid=True)

class DummyEnvironment(BaseEnvironment):
    def validate_schema(self, design_params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if "value" not in design_params:
            return False, "Missing parameter: 'value'"
        return True, None
        
    def run_drc(self, design_params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if design_params.get("value", 0) < 0:
            return False, "DRC Error: 'value' cannot be negative."
        return True, None

def main():
    logger = setup_logger("dummy_sim")
    logger.info("Dummy simulation is starting...")
    
    sim = DummySimulator()
    rew = DummyReward()
    env = DummyEnvironment(sim, rew)
    
    task_params = {"target": "dummy"}
    
    designs = [
        {"id": "d1", "params": {"value": 30}}, # Success
        {"id": "d2", "params": {}}, # Schema Error
        {"id": "d3", "params": {"value": -5}}, # DRC Error
        {"id": "d4", "params": {"value": 10, "fail_sim": True}}, # Sim Error
        {"id": "d5", "params": {"value": 10, "crash_sim": True}}, # Crash
    ]
    
    for d in designs:
        logger.info(f"Testing: {d['id']}")
        res = env.evaluate("task_1", task_params, d["id"], d["params"])
        logger.info(f"Result: {res.status}, Score: {res.score.normalized_total}")
        
        saved_path = save_evaluation_result(res)
        logger.info(f"Log saved: {saved_path}")

if __name__ == "__main__":
    main()
