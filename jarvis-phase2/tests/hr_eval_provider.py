"""Promptfoo runs local fixtures against the actual HR review, without LLM calls."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.hr_team import review


def call_api(prompt, options, context):
    result = review(json.loads(prompt))
    return {'output': json.dumps(result, ensure_ascii=False), 'cost': 0,
            'tokenUsage': {'total': 0, 'numRequests': 0}}
