#!/usr/bin/env python3
"""Manually evaluate five model answers; never run on hourly source timer."""
from pathlib import Path
import sys
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.improvement import evaluate_model
from jarvis.memory import CompanyMemory
from jarvis.model_layer import ModelRouter
from jarvis.transport import memory_host
if __name__ == '__main__':
    print(json.dumps(evaluate_model(CompanyMemory(host=memory_host()), ModelRouter()), ensure_ascii=False))
