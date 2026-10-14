#!/usr/bin/env python3
"""Run evidence checks and owned follow-ups; print only aggregate counts."""
from pathlib import Path
import sys
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.improvement import cycle
from jarvis.memory import CompanyMemory
from jarvis.transport import memory_host
if __name__ == '__main__':
    result = cycle(CompanyMemory(host=memory_host()))
    print(json.dumps({'works': len(result['works']), 'lessons': len(result['outcome_lessons']),
                      'cases': [{k: r[k] for k in ('query', 'status', 'duration_ms')} for r in result['evaluation']['cases']]}, ensure_ascii=False))
