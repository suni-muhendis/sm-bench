import argparse
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sm_heat_exchanger.simulator import HeatExchangerSimulator
from sm_heat_exchanger.score import HeatExchangerScoreV1, HeatExchangerScoreV2
from sm_heat_exchanger.env import HeatExchangerEnv
from sm_heat_exchanger.samplers.random_sampler import RandomSampler

def main():
    parser = argparse.ArgumentParser(description="Analyze score distribution between V1 and V2.")
    parser.add_argument("--task", type=str, required=True, help="Path to task.json")
    parser.add_argument("--samples", type=int, default=100, help="Number of random samples to simulate")
    
    args = parser.parse_args()
    
    with open(args.task, "r", encoding="utf-8") as f:
        task_params = json.load(f)
        
    sampler = RandomSampler()
    env = HeatExchangerEnv(HeatExchangerSimulator(), HeatExchangerScoreV1())
    
    print(f"Generating {args.samples} samples...")
    designs = sampler.sample(args.samples)
    
    score_v1_fn = HeatExchangerScoreV1()
    score_v2_fn = HeatExchangerScoreV2()
    
    v1_scores = []
    v2_scores = []
    
    valid_count = 0
    
    print("Simulating designs...")
    for i, design in enumerate(designs):
        schema_valid, _ = env.validate_schema(design)
        if not schema_valid: continue
        
        drc_valid, _ = env.run_drc(design)
        if not drc_valid: continue
        
        success, metrics, _, _ = env.simulator.simulate(design)
        if not success: continue
        
        valid_count += 1
        
        res_v1 = score_v1_fn.calculate_score(task_params, metrics, is_valid=True)
        res_v2 = score_v2_fn.calculate_score(task_params, metrics, is_valid=True)
        
        v1_scores.append(res_v1.normalized_total)
        v2_scores.append(res_v2.normalized_total)

    if not v1_scores:
        print("No valid designs found out of the random samples.")
        return

    print(f"\n--- Analysis Results ({valid_count} valid designs) ---")
    print(f"Task file: {args.task}")
    
    def print_stats(name, data):
        data = np.array(data)
        print(f"  {name}:")
        print(f"    Mean: {np.mean(data):.4f}")
        print(f"    Std:  {np.std(data):.4f}")
        print(f"    Min:  {np.min(data):.4f}")
        print(f"    Max:  {np.max(data):.4f}")
        print(f"    P25:  {np.percentile(data, 25):.4f}")
        print(f"    P50:  {np.percentile(data, 50):.4f}")
        print(f"    P75:  {np.percentile(data, 75):.4f}")
        
        # Saturation check
        sat_0 = np.sum(data == 0.0) / len(data)
        sat_1 = np.sum(data >= 0.99) / len(data)
        print(f"    Sat=0: {sat_0*100:.1f}%")
        print(f"    Sat~1: {sat_1*100:.1f}%")

    print_stats("V1 Scores", v1_scores)
    print_stats("V2 Scores", v2_scores)

if __name__ == "__main__":
    main()
