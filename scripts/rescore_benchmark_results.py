import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sm_core import make_env

def main():
    parser = argparse.ArgumentParser(description="Rescore existing benchmark results using a new score version.")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL file.")
    parser.add_argument("--output", type=str, required=True, help="Output JSONL file.")
    parser.add_argument("--score-version", type=str, default="heat_exchanger_score_v2", help="Score version to apply.")
    parser.add_argument("--environment", type=str, default="heat_exchanger", help="Environment that defines the score version.")

    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
        
    try:
        score_fn = make_env(args.environment).get_score_function({"score_version": args.score_version})
    except Exception as e:
        print(f"Error instantiating score function: {e}")
        sys.exit(1)
        
    rescore_count = 0
    total_count = 0
    
    with open(args.input, "r", encoding="utf-8") as fin, \
         open(args.output, "w", encoding="utf-8") as fout:
             
        for line in fin:
            if not line.strip(): continue
            total_count += 1
            record = json.loads(line)
            
            # If the run was successful, rescore it
            if record.get("status") == "success":
                metrics = record.get("metrics", {})
                task_params = record.get("weights", {})
                # Note: original task params might not have V2 parameters, so defaults will be used
                # We can also inject score_version into task_params
                task_params["score_version"] = args.score_version
                
                result = score_fn.calculate_score(task_params, metrics, is_valid=True)
                
                record["total_reward"] = result.normalized_total
                record["reward_components"] = result.components
                record["score_version"] = args.score_version
                rescore_count += 1
            else:
                record["score_version"] = args.score_version
                
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    print(f"Done. Processed {total_count} records. Rescored {rescore_count} successes.")
    print(f"Output written to {args.output}")

if __name__ == "__main__":
    main()
