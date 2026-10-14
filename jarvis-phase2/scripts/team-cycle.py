#!/usr/bin/env python3
"""Produce evidenced work for research, synthesis and agency roles."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jarvis.memory import CompanyMemory
from jarvis.role_activity import run
from jarvis.transport import memory_host
if __name__=="__main__":
    print(json.dumps(run(CompanyMemory(host=memory_host())),ensure_ascii=False))
