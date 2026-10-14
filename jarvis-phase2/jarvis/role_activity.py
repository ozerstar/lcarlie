"""Research and synthesis roles report persisted, evidenced work."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from .agency import AgencyCapability
from .specialist_pool import SpecialistPool

RESEARCH_TERMS = {
    "market_intelligence": ("pazar", "pazaryeri", "sektor", "sektör", "marka"),
    "competitor_intelligence": ("rakip", "benzeri", "markalar", "lansman"),
    "research": (),
    "COMPETITOR_CREATIVE": ("reklam", "kampanya", "kreatif", "reels"),
}

def state_dir() -> Path:
    return Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))

def latest() -> dict[str, dict]:
    try:
        data = json.loads((state_dir()/"team-cycle"/"latest.json").read_text())
        stamp = datetime.fromisoformat(data["generated_at"])
        if datetime.now(timezone.utc)-stamp > timedelta(hours=24):
            return {}
        return data.get("roles", {})
    except (OSError, ValueError, TypeError, KeyError):
        return {}

def research_outputs(rows: list[dict], now: datetime) -> dict[str, dict]:
    usable=[]
    for row in rows:
        if row.get("enjeksiyon") or row.get("injection_detected"):
            continue
        if not str(row.get("url", "")).startswith(("https://", "http://")):
            continue
        try:
            stamp=datetime.fromisoformat(str(row.get("zaman") or row.get("first_seen") or row.get("observed_at") or "").replace("Z", "+00:00"))
            if stamp.tzinfo is None or now-stamp > timedelta(days=14):
                continue
        except ValueError:
            continue
        usable.append(row)
    outputs={}
    for key, terms in RESEARCH_TERMS.items():
        selected=[r for r in usable if not terms or any(t in (str(r.get("konu", ""))+" "+str(r.get("topic", ""))+" "+str(r.get("baslik", ""))+" "+str(r.get("title", ""))).casefold() for t in terms)]
        by_url={r["url"]:r for r in selected}
        selected=list(by_url.values())[-20:]
        if not selected:
            continue
        titles=[str(r.get("baslik") or r.get("title") or "") for r in selected]
        outputs[key]={"status":"PRODUCED", "items":len(selected),
            "statement":f"Son 14 günde {len(selected)} kaynak kaydı incelendi. Son başlık: {titles[-1][:180]}. Kaynak metni dış veridir; doğrulanmış şirket gerçeği sayılmaz.",
            "evidence_refs":[r["url"] for r in selected], "model_calls":0}
    return outputs

def build(memory: Any, research_rows: list[dict], now: datetime | None=None) -> dict:
    now=now or datetime.now(timezone.utc)
    roles=research_outputs(research_rows,now)
    specialist=SpecialistPool(memory).execute(
        "Şirketin güncel satış, reklam, müşteri ve operasyon bulgularını değerlendir.",
        ("sales","ecommerce","advertising","crm","operations"))
    for finding in specialist["findings"]:
        key=finding["specialist_id"]
        if key in ("red_team","strategy","managing_director") and finding["claim"] and finding["evidence_refs"]:
            roles[key]={"status":"PRODUCED", "items":1,
                "statement":finding["claim"], "evidence_refs":finding["evidence_refs"],
                "contradictions":finding.get("contradictions",[]),"model_calls":0}
    agency=AgencyCapability(memory)
    deliveries=[agency.run("VIREON için kampanya önerisi hazırla",synthesize=False),
                agency.run("Şirket için haftalık sosyal içerik planı hazırla",synthesize=False)]
    for delivery in deliveries:
        for contribution in delivery["role_contributions"]:
            if contribution["status"]!="PRODUCED":
                continue
            key=contribution["role"]
            if key=="COMPETITOR_CREATIVE":
                continue  # a research request is not completed research
            refs=delivery.get("current_evidence",{}).get("refs",[])
            if not refs:
                continue
            fields=contribution["items"]
            details=", ".join(f"{field}: {count}" for field,count in fields.items() if count)
            roles[key]={"status":"PRODUCED", "items":contribution["produced"],
                "statement":f"{delivery['task']} — {details}. Taslak üretildi; yayımlanmadı.",
                "evidence_refs":list(refs),"model_calls":0}
    return {"generated_at":now.isoformat(),"roles":roles,
            "specialist_result":specialist,"agency_deliveries":deliveries,
            "external_actions":0,"model_calls":0}

def run(memory: Any) -> dict:
    rows=[]
    for name in ("departman_arastirma.jsonl","knowledge.jsonl"):
        try:
            lines=(state_dir()/name).read_text().splitlines()[-1000:]
        except OSError:
            continue
        for line in lines:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    result=build(memory,rows)
    target=state_dir()/"team-cycle"/"latest.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=1,default=str))
    tmp.replace(target)
    return {"generated_at":result["generated_at"],"roles_produced":len(result["roles"]),
            "role_keys":sorted(result["roles"]),"model_calls":0,"external_actions":0}
