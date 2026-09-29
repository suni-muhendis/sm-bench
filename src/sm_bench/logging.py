import json
import logging
import os
from datetime import datetime
from typing import Dict, Any
from sm_core import EvaluationResult

def setup_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """Creates a basic logger."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        # File handler
        log_file = os.path.join(log_dir, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
    return logger

def save_evaluation_result(result: EvaluationResult, output_dir: str = "examples/outputs") -> str:
    """Saves the EvaluationResult object to disk as JSON."""
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{result.task_id}_{result.design_id}_result.json")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
        
    return file_path
