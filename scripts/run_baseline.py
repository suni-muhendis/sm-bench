import sys
import os
import json
import statistics
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sm_heat_exchanger.env import HeatExchangerEnv
from sm_heat_exchanger.simulator import HeatExchangerSimulator
from sm_heat_exchanger.score import HeatExchangerScore
from sm_heat_exchanger.samplers.random_sampler import RandomSampler
from sm_heat_exchanger.samplers.heuristic_sampler import HeuristicSampler
from sm_heat_exchanger.samplers.latin_hypercube_sampler import LatinHypercubeSampler
from sm_bench.logging import setup_logger

def main():
    logger = setup_logger("baseline_runner")
    logger.info("Starting Phase 2 Baseline Generation...")
    
    # 1. Setup Environment
    env = HeatExchangerEnv(HeatExchangerSimulator(), HeatExchangerScore())
    
    # Target Task (from configs)
    task_path = os.path.join(os.path.dirname(__file__), '../configs/tasks/heat_exchanger/task_001.json')
    with open(task_path, 'r', encoding='utf-8') as f:
        task_params = json.load(f)
        
    SAMPLES_PER_METHOD = 3334 # Total ~10000 across 3 samplers
    REWARD_THRESHOLD = 0.60
    
    samplers = [
        RandomSampler(),
        LatinHypercubeSampler(),
        HeuristicSampler()
    ]
    
    all_successful_designs = []
    
    for sampler in samplers:
        logger.info(f"--- Running {sampler.name} for {SAMPLES_PER_METHOD} samples ---")
        designs = sampler.sample(SAMPLES_PER_METHOD)
        
        valid_count = 0
        rewards = []
        
        start_time = time.time()
        for i, design in enumerate(designs):
            # Evaluate
            res = env.evaluate(f"task_001", task_params, f"{sampler.name}_{i}", design)
            
            if res.status == "success":
                valid_count += 1
                r = res.score.normalized_total
                rewards.append(r)
                
                # Check threshold for the training dataset
                if r >= REWARD_THRESHOLD:
                    all_successful_designs.append({
                        "sampler": sampler.name,
                        "task": task_params,
                        "design": design,
                        "score": r,
                        "metrics": res.metrics
                    })
                    
        elapsed = time.time() - start_time
        
        # Statistics
        if rewards:
            mean_r = statistics.mean(rewards)
            median_r = statistics.median(rewards)
            max_r = max(rewards)
        else:
            mean_r, median_r, max_r = 0.0, 0.0, 0.0
            
        logger.info(f"{sampler.name} Results: Time={elapsed:.2f}s")
        logger.info(f"Valid Rate: {valid_count}/{SAMPLES_PER_METHOD} ({valid_count/SAMPLES_PER_METHOD*100:.2f}%)")
        logger.info(f"Rewards - Mean: {mean_r:.4f}, Median: {median_r:.4f}, Max: {max_r:.4f}")
        logger.info("-" * 40)
        
    # Save the training dataset
    sft_path = os.path.join(os.path.dirname(__file__), '../datasets/sft/heat_exchanger_initial.jsonl')
    os.makedirs(os.path.dirname(sft_path), exist_ok=True)
    with open(sft_path, 'w', encoding='utf-8') as f:
        for item in all_successful_designs:
            f.write(json.dumps(item) + "\n")
            
    logger.info(f"Total samples generated (Score >= {REWARD_THRESHOLD}): {len(all_successful_designs)}")
    logger.info(f"Dataset saved to: {sft_path}")

if __name__ == "__main__":
    main()
