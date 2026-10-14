#!/usr/bin/env python3
"""Five model checks on server loopback only. External fallback is disabled."""
from pathlib import Path
import sys
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.improvement import evaluate_model
from jarvis.memory import CompanyMemory
from jarvis.model_layer import ModelRouter, LocalProvider
from jarvis.adapter_factory import AdapterState
from jarvis.transport import memory_host


class DisabledProvider:
    name = 'disabled-for-local-evaluation'
    model = None
    tier = 'DISABLED'

    def state(self):
        return AdapterState.UNAVAILABLE

    def complete(self, *args, **kwargs):
        raise RuntimeError('External model calls are disabled for this evaluation')


def local_router():
    return ModelRouter(local=LocalProvider(url='http://127.0.0.1:8099/v1'),
                       external=DisabledProvider(), gpu=DisabledProvider())


if __name__ == '__main__':
    print(json.dumps(evaluate_model(CompanyMemory(host=memory_host()), local_router()), ensure_ascii=False))
