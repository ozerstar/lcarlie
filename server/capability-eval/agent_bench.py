#!/usr/bin/env python3
"""Real L'CARLIE task through each agent framework candidate.

Task: take CRM evidence from Company Memory, analyse unanswered customers /
open work, PRESERVE the evidence refs, and return a PROPOSED result.

Company Memory is stubbed here with the exact record shapes the live run
returned (mart.musteri, mart.konusma_cevapsiz, mart.acik_isler), because this
container has no docker-exec path to Postgres. What is being measured is the
FRAMEWORK's overhead and what it takes to express the task -- not Postgres.
"""
import importlib
import json
import os
import resource
import sys
import time

FRAMEWORK = sys.argv[1]

CRM_EVIDENCE = {
    "postgres:crm_customers": [
        {"entity_id": 87, "source": "mart.musteri", "identity_status": "MATCHED",
         "siparis_tum_zaman": 3, "ciro_dogrulanmis": 0},
        {"entity_id": 95, "source": "mart.musteri", "identity_status": "MATCHED",
         "siparis_tum_zaman": 1, "ciro_dogrulanmis": 0},
    ],
    "postgres:crm_unanswered": [
        {"entity_id": "k1", "source": "mart.konusma_cevapsiz", "kanal": "INSTAGRAM",
         "mesaj_sayisi": 3, "bekleme_saat": 191.4},
        {"entity_id": "k2", "source": "mart.konusma_cevapsiz", "kanal": "WHATSAPP",
         "mesaj_sayisi": 1, "bekleme_saat": 42.0},
    ],
    "postgres:open_work": [
        {"tur": "CEVAPSIZ_MESAJ", "anahtar": "k1", "zaman": "2026-09-10T00:00:00+00:00"},
    ],
}


def rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def read_crm() -> str:
    """The one tool. Returns CRM evidence with its source refs intact."""
    return json.dumps(CRM_EVIDENCE, ensure_ascii=False)


def analyse(payload: str) -> dict:
    """Deterministic analysis, identical across frameworks so the comparison
    is about the framework and not about the analysis."""
    data = json.loads(payload)
    unanswered = data.get("postgres:crm_unanswered", [])
    worst = max(unanswered, key=lambda r: r.get("bekleme_saat") or 0, default=None)
    return {
        "status": "PROPOSED",
        "findings": [
            {"code": "UNANSWERED_BACKLOG",
             "detail": f"{len(unanswered)} unanswered conversations; "
                       f"longest wait {worst['bekleme_saat']}h on {worst['kanal']}",
             "evidence_refs": ["postgres:crm_unanswered"]},
        ],
        "evidence_refs": sorted(data),
    }


t_start = time.perf_counter()
imported = {}

if FRAMEWORK == "baseline":
    # No framework at all: plain Python calling the same two functions.
    result = analyse(read_crm())
    tool_mechanism = "direct call"

elif FRAMEWORK == "smol":
    t0 = time.perf_counter()
    from smolagents import tool, CodeAgent  # noqa: F401
    imported["import_s"] = round(time.perf_counter() - t0, 3)

    @tool
    def crm_evidence() -> str:
        """Return CRM evidence from Company Memory with its source refs."""
        return read_crm()

    # An agent LOOP needs a model. The tool itself is callable deterministically.
    result = analyse(crm_evidence())
    tool_mechanism = "@tool decorator; CodeAgent loop requires a model"

elif FRAMEWORK == "agno":
    t0 = time.perf_counter()
    from agno.agent import Agent  # noqa: F401
    imported["import_s"] = round(time.perf_counter() - t0, 3)

    def crm_evidence() -> str:
        """Return CRM evidence from Company Memory with its source refs."""
        return read_crm()

    result = analyse(crm_evidence())
    tool_mechanism = "plain python callable as tool; Agent.run requires a model"

elif FRAMEWORK == "qwen":
    t0 = time.perf_counter()
    from qwen_agent.agents import Assistant  # noqa: F401
    imported["import_s"] = round(time.perf_counter() - t0, 3)

    def crm_evidence() -> str:
        return read_crm()

    result = analyse(crm_evidence())
    tool_mechanism = "BaseTool subclass or function registry; Assistant requires an LLM cfg"

else:
    raise SystemExit(f"unknown framework {FRAMEWORK}")

total = round((time.perf_counter() - t_start) * 1000, 2)
print(json.dumps({
    "framework": FRAMEWORK,
    "total_ms": total,
    "import_s": imported.get("import_s"),
    "rss_mb": rss_mb(),
    "tool_mechanism": tool_mechanism,
    "model_calls": 0,
    "evidence_refs_preserved": result["evidence_refs"],
    "status": result["status"],
    "findings": result["findings"],
}, ensure_ascii=False))
