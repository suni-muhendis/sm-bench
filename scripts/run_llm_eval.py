import sys
import os
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sunimuhendis import make_env
from sunimuhendis.parsing.json_parser import parse_llm_json
from sunimuhendis.model_clients.dummy_random import DummyRandomClient
from sunimuhendis.model_clients.interactive_browser import InteractiveBrowserClient
from sunimuhendis.core.logging import setup_logger

def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM responses")
    parser.add_argument("--client", type=str, default="dummy", choices=["dummy", "interactive"], help="Client to use")
    parser.add_argument("--prompt", type=str, required=True, help="Prompt slug (e.g. heat_exchanger_v1)")
    parser.add_argument("--model", type=str, default=None, help="Model name to save results under (skips interactive prompt if provided)")
    args = parser.parse_args()

    logger = setup_logger("llm_evaluator")
    
    # 1. Load Task
    task_path = os.path.join(
        os.path.dirname(__file__),
        f'../results/zero_shot/{args.prompt}/task.json',
    )
    if not os.path.exists(task_path):
        logger.error(f"Zero-shot task file not found: {task_path}.")
        return
        
    with open(task_path, 'r', encoding='utf-8') as f:
        task_params = json.load(f)

    # 2. Setup Environment: the one the task names (older tasks are all
    # heat-exchanger tasks and do not name one).
    env = make_env(task_params.get("environment", "heat_exchanger"))

    # 3. Setup Client
    if args.client == "interactive":
        client = InteractiveBrowserClient()
    else:
        client = DummyRandomClient()
        
    logger.info(f"Running LLM Evaluation with {client.model_name}")
    
    # 4. Generate Prompt
    prompt_path = os.path.join(os.path.dirname(task_path), "prompt.txt")
    with open(prompt_path, encoding="utf-8-sig") as f:
        prompt = f.read()
    
    # 5. Get Model Response
    logger.info("Waiting for model response...")
    raw_response = client.generate_design(prompt)
    logger.info("Received raw response from model.")
    
    # 6. Parse JSON
    try:
        design = parse_llm_json(raw_response)
        logger.info(f"Successfully parsed JSON design: {design}")
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"Raw response was: {raw_response}")
        return
        
    # 7. Evaluate in Simulator
    res = env.evaluate(task_params.get("task_id", args.prompt), task_params, "llm_design_001", design)
    
    # 8. Report Results
    logger.info(f"Evaluation Status: {res.status}")
    if res.status == "success":
        logger.info(f"Simulation Success! Score: {res.score.normalized_total:.4f}")
        logger.info(f"Metrics: {res.metrics}")
        
        if args.model:
            model_name = args.model
            logger.info(f"Using provided model name: {model_name}")
        else:
            model_name = input("\nEnter Model Name (e.g. 'GPT 5.5 Pro' or 'Skip' to not save): ").strip()
            
        if model_name.lower() != 'skip' and model_name != '':
            # Safe model name for filename
            safe_model = "".join(c if c.isalnum() else "_" for c in model_name).lower()
            out_dir = os.path.join(
                os.path.dirname(__file__),
                f'../results/zero_shot/{args.prompt}/manual_runs',
            )
            os.makedirs(out_dir, exist_ok=True)
            db_path = os.path.join(out_dir, f"{safe_model}.jsonl")
            
            # Kaydedilecek veri paketi
            record = {
                "evaluation_mode": "zero_shot",
                "model_name": model_name,
                "timestamp": datetime.now().isoformat(),
                "prompt_slug": args.prompt,
                "environment": res.environment,
                "score_version": res.score_version,
                "simulator_version": res.simulator_version,
                "status": "success",
                "error": None,
                "weights": {
                    "w_heat": task_params.get("w_heat", 0.4),
                    "w_cost": task_params.get("w_cost", 0.1),
                    "w_drop_tube": task_params.get("w_drop_tube", 0.15),
                    "w_drop_shell": task_params.get("w_drop_shell", 0.15),
                    "w_eff": task_params.get("w_eff", 0.2)
                },
                "total_score": res.score.normalized_total,
                "metrics": res.metrics,
                "design": design
            }
            
            with open(db_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
            logger.info(f"Saved results for {model_name} to {db_path}")
            
    else:
        logger.warning(f"Simulation/DRC/Schema failed. Reason: {res.status}")
        if res.error_message:
            logger.warning(f"Error Details: {res.error_message}")

if __name__ == "__main__":
    main()
