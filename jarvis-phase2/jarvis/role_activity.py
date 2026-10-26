"""Research and synthesis roles report persisted, evidenced work."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from .agency import AgencyCapability
from .specialist_pool import SpecialistPool
from .agency import classify_task, select_roles
from . import roster, office_events

RESEARCH_TERMS = {
    "market_intelligence": ("pazar", "pazaryeri", "sektor", "sektör", "marka"),
    "competitor_intelligence": ("rakip", "benzeri", "markalar", "lansman"),
    "research": (),
    "COMPETITOR_CREATIVE": ("reklam", "kampanya", "kreatif", "reels"),
}

def state_dir() -> Path:
    return Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))

def latest() -> dict[str, dict]:
    return latest_report().get("roles", {})

def latest_report() -> dict:
    try:
        data = json.loads((state_dir()/"team-cycle"/"latest.json").read_text())
        stamp = datetime.fromisoformat(data["generated_at"])
        if stamp.tzinfo is None or not timedelta(0) <= datetime.now(timezone.utc)-stamp <= timedelta(hours=24):
            return {}
        return data
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

def build(memory: Any, research_rows: list[dict], now: datetime | None=None,
          *, emit_events: bool = False) -> dict:
    now=now or datetime.now(timezone.utc)
    roles={}
    activity={}
    finished_emitted: set[str] = set()

    def live_status(status: str) -> str:
        return {"WORKED": "COMPLETED", "WAITING": "WAITING", "ERROR": "FAILED"}.get(status, "WAITING")

    def member_started(key: str, task: str) -> None:
        if emit_events:
            office_events.emit("member", member_key=key, status="WORKING", task=task)

    def record(key, task, status, result, refs, started, finished, kind="ANALİZ / TASLAK"):
        if activity.get(key, {}).get("status") == "WORKED" and status == "WAITING":
            return
        activity[key] = {
            "status": status, "task": task, "kind": kind, "result": str(result)[:300],
            "evidence_refs": list(refs)[:12],
            "started_at": started.isoformat(), "finished_at": finished.isoformat(),
            "duration_ms": round((finished-started).total_seconds()*1000, 2),
        }
        if emit_events and key not in finished_emitted:
            office_events.emit("member", member_key=key, status=live_status(status), task=task)

    started=datetime.now(timezone.utc)
    try:
        for key in RESEARCH_TERMS:
            member_started(key, "Kayıtlı dış kaynakları yeniden değerlendir")
        roles.update(research_outputs(research_rows,now))
        finished=datetime.now(timezone.utc)
        for key in RESEARCH_TERMS:
            output=roles.get(key, {})
            refs=output.get("evidence_refs", [])
            record(key,"Kayıtlı dış kaynakları yeniden değerlendir",
                   "WORKED" if refs else "WAITING",
                   output.get("statement") if refs else "Uygun kaynak kaydı bulunmadı.",
                   refs,started,finished,kind="KAYIT TARAMASI")
    except Exception as exc:  # noqa: BLE001
        finished=datetime.now(timezone.utc)
        for key in RESEARCH_TERMS:
            record(key,"Kayıtlı dış kaynakları yeniden değerlendir","ERROR",
                   type(exc).__name__,[],started,finished,kind="KAYIT TARAMASI")

    specialist={}
    domains=("sales","ecommerce","advertising","crm","operations")
    pool=SpecialistPool(memory)
    selected=pool.router.route(domains).selected
    started=datetime.now(timezone.utc)
    try:
        for key in selected:
            member_started(key, "Şirket verilerinden alan analizi üret")
        specialist=pool.execute(
            "Şirketin güncel satış, reklam, müşteri ve operasyon bulgularını değerlendir.", domains)
        finished=datetime.now(timezone.utc)
        findings={finding["specialist_id"]: finding for finding in specialist["findings"]}
        for key in selected:
            finding=findings.get(key, {})
            refs=finding.get("evidence_refs", [])
            claim=finding.get("claim", "")
            record(key,"Şirket verilerinden alan analizi üret",
                   "WORKED" if claim and refs else "WAITING",
                   claim if claim and refs else "Kanıta bağlı sonuç üretilemedi.",
                   refs,started,finished)
            if key in ("red_team","strategy","managing_director") and claim and refs:
                roles[key]={"status":"PRODUCED", "items":1,
                    "statement":claim, "evidence_refs":refs,
                    "contradictions":finding.get("contradictions",[]),"model_calls":0}
    except Exception as exc:  # noqa: BLE001
        finished=datetime.now(timezone.utc)
        for key in selected:
            record(key,"Şirket verilerinden alan analizi üret","ERROR",
                   type(exc).__name__,[],started,finished)

    agency=AgencyCapability(memory)
    deliveries=[]
    for task in ("VIREON için kampanya önerisi hazırla",
                 "Şirket için haftalık sosyal içerik planı hazırla"):
        selected_roles=select_roles(classify_task(task),task)
        started=datetime.now(timezone.utc)
        try:
            for key in selected_roles:
                member_started(key, task)
            delivery=agency.run(task,synthesize=False)
            deliveries.append(delivery)
            finished=datetime.now(timezone.utc)
            refs=delivery.get("current_evidence",{}).get("refs",[])
            contributions={item["role"]:item for item in delivery["role_contributions"]}
            for key in selected_roles:
                contribution=contributions.get(key,{})
                produced=contribution.get("status")=="PRODUCED" and bool(refs)
                fields=contribution.get("items",{})
                details=", ".join(f"{field}: {count}" for field,count in fields.items() if count)
                statement=f"{task} — {details}. Taslak üretildi; yayımlanmadı."
                record(key,task,"WORKED" if produced else "WAITING",
                       statement if produced else "Kanıta bağlı katkı üretilmedi.",
                       refs if produced else [],started,finished)
                if produced and key!="COMPETITOR_CREATIVE":
                    roles[key]={"status":"PRODUCED", "items":contribution["produced"],
                        "statement":statement,"evidence_refs":list(refs),"model_calls":0}
        except Exception as exc:  # noqa: BLE001
            finished=datetime.now(timezone.utc)
            for key in selected_roles:
                record(key,task,"ERROR",type(exc).__name__,[],started,finished)

    data_keys=tuple(member.key for member in roster.ROSTER if member.mode=="data")
    data_opinions=[]
    started=datetime.now(timezone.utc)
    try:
        def on_data_done(observation: dict) -> None:
            key = observation.get("key", "")
            if not key or not emit_events:
                return
            status = observation.get("status")
            live = ("COMPLETED" if status == roster.SPEAKS else
                    "FAILED" if status in (roster.NO_DATA, roster.ISLEM_HATASI) else "WAITING")
            office_events.emit("member", member_key=key, status=live,
                               task="Şirket verisini oku ve rol değerlendirmesi üret")
            finished_emitted.add(key)

        data_opinions=roster.opinions(
            memory, only=data_keys,
            on_member_start=(lambda member: member_started(
                member.key, "Şirket verisini oku ve rol değerlendirmesi üret")) if emit_events else None,
            on_member_done=on_data_done if emit_events else None)
        observations={item["key"]:item for item in data_opinions}
        finished=datetime.now(timezone.utc)
        for key in data_keys:
            if key in activity:
                continue
            observation=observations.get(key,{})
            refs=observation.get("evidence_refs",[])
            missing=observation.get("missing",[])
            if observation.get("status") in (roster.NO_DATA,roster.ISLEM_HATASI) or missing:
                status="ERROR"
                result=("Okunamayan kaynak: "+", ".join(missing)) if missing else observation.get("statement","İşlem hatası")
            elif observation.get("status")==roster.SPEAKS and refs and observation.get("statement"):
                status="WORKED"
                result=observation["statement"]
            else:
                status="WAITING"
                result="Kanıta bağlı veri değerlendirmesi üretilemedi."
            record(key,"Şirket verisini oku ve rol değerlendirmesi üret",
                   status,result,refs if status=="WORKED" else [],started,finished,
                   kind="VERİ KONTROLÜ")
    except Exception as exc:  # noqa: BLE001
        finished=datetime.now(timezone.utc)
        for key in data_keys:
            if key in activity:
                continue
            record(key,"Şirket verisini oku ve rol değerlendirmesi üret",
                   "ERROR",type(exc).__name__,[],started,finished,
                   kind="VERİ KONTROLÜ")
    return {"generated_at":now.isoformat(),"roles":roles,
            "activity":activity,"data_opinions":data_opinions,
            "specialist_result":specialist,"agency_deliveries":deliveries,
            "external_actions":0,"model_calls":0}

def run(memory: Any) -> dict:
    office_events.emit("cycle", status="WORKING", task="Ekip değerlendirmesi başladı")
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
    result=build(memory,rows,emit_events=True)
    target=state_dir()/"team-cycle"/"latest.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=1,default=str))
    try:
        import grp
        os.chown(tmp, -1, grp.getgrnam("jarvis-web").gr_gid)
    except (ImportError, KeyError, PermissionError):
        pass
    os.chmod(tmp,0o640)
    tmp.replace(target)
    office_events.emit("cycle", status="COMPLETED", task="Ekip değerlendirmesi tamamlandı")
    return {"generated_at":result["generated_at"],"roles_produced":len(result["roles"]),
            "role_keys":sorted(result["roles"]),"model_calls":0,"external_actions":0}
