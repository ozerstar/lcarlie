"""Minimum Operational Jarvis: READ -> ANALYZE -> DETECT -> PROPOSE -> STOP.

Discovered during this task: a SEPARATE, older, pre-existing orchestrator
("System A": ai_generate_company_intelligence_task -> PROPOSE_DECISION tasks
-> core.karar rows -> mart.ai_approval_inbox -> human-approval-cli.sh ->
core.human_decide_karar) already runs on this host, with its own worker
(worker.js, currently failing on an unrelated DNS issue -- EAI_AGAIN
lcarlie-postgres inside the lcarlie_ai_egress docker network) and its own
human approval CLI. That system is NOT touched, NOT fixed, and NOT reused
here: this task's mandate is specifically the Action Firewall / PROPOSE_ACTION
/ core.ai_action_proposal pipeline built in Phase 2C/2D ("System B"). Naming a
different action type/table would be scope creep.

core.ai_claim_task() has no task_type filter -- it claims whatever OPEN task
is oldest, regardless of who it belongs to. To avoid ever silently absorbing a
System-A PROPOSE_DECISION task, this loop:
  1. claims at most one task per cycle,
  2. immediately checks task_type,
  3. if it is not PROPOSE_ACTION, calls core.ai_fail_task(..., FAILED_RETRYABLE)
     to hand it straight back to the pool (it stays eligible for whoever
     actually owns it), and stops -- it never touches the task's payload.

ai_writer has no SELECT on core.ai_task (table ACL is owner-only), so the only
task content this loop can see after claiming is what ai_claim_task() itself
returns: task_id, source_type, source_id, task_type, idempotency_key,
context_profile, lease_token, attempt_count. There is no free-text field
available to ai_writer. The internal intent is therefore carried in the
idempotency_key by convention, set by a human via `jarvis-operator create-task`:

    jarvis:<INTERNAL_INTENT>:<slug>

e.g. jarvis:HUMAN_REVIEW_REQUEST:demo-2026-09-18. This requires no new grant
and needs no schema change. A richer per-task context field is a real
improvement -- recorded in the report backlog, not implemented here.

Zero model calls anywhere in this module. Analysis is pure deterministic
Python.
"""
from __future__ import annotations

import json
import os
from jarvis.db_transport import run as db_run
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import perf_counter, time
from typing import Any

from . import gunluk
from . import business_signals
from .action_contract import ContractCache
from .coding_executor import CodingExecutorError, CodingTaskSpec, run_coding_task, summarize_for_proposal
from .firewall import ContractDriftError, FirewallError, validate_proposal
from .memory import CompanyMemory, MemoryError

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
STATE_FILE = STATE_DIR / "loop-state.json"
FINDINGS_LOG = STATE_DIR / "findings.jsonl"
AUDIT_LOG = STATE_DIR / "audit.jsonl"
CODING_TASK_PENDING_DIR = STATE_DIR / "coding_executor" / "pending"


class CodingTaskDenied(FirewallError):
    """A CODE_CHANGE_REVIEW task was claimed but CodingExecutor denied it
    (scope violation, failed tests, missing/malformed spec, or a run error).
    Subclasses FirewallError so it is caught by the existing propose/fail
    handling in run_cycle without changing that except clause: the task
    fails (FAILED_RETRYABLE) and, correctly, NO proposal is ever created for
    a denied coding attempt."""

WORKER_ID = "jarvis-operational-loop"
# 🔴 KIRA_NEDEN — 60 SANİYE KODLAMA GÖREVLERİNİ İMKÂNSIZ KILIYORDU.
#
# Ölçüldü 21.09.2026: `CODE_CHANGE_REVIEW` görevi açıldı, döngü onu aldı,
# CodingExecutor modeli çağırdı ve koşu 10 dakikayı aştı. Dönüşte:
#     ERROR: invalid or expired lease
#     CONTEXT: PL/pgSQL function ai_fail_task(...) line 18
# Kira çoktan bitmişti; görev LEASED'te asılı kaldı, öneri yazılamadı.
#
# Bu, modülün KENDİ belgesiyle çelişiyordu. coding_executor.py docstring:
#   "A CodingExecutor run can legitimately take much longer than a typical
#    Jarvis cycle" ve ücretsiz katmanda "several minutes of retry/backoff".
# Yani sistem kendi kendini geliştirebilsin diye kurulmuştu ama kira süresi
# bunu yapısal olarak engelliyordu.
#
# NEDEN GLOBAL OLARAK YÜKSELTİLDİ, göreve göre değil:
# `core.ai_claim_task(worker, saniye)` kirayı ALIRKEN veriyor; hangi niyet
# olduğu ancak görev alındıktan SONRA (idempotency_key'den) anlaşılıyor.
# Kirayı sonradan uzatacak bir fonksiyon veritabanında YOK (arandı).
#
# UZUN KİRANIN BEDELİ VE NEDEN KABUL EDİLEBİLİR:
# Döngü çökerse görev bu süre boyunca kilitli kalır. Burada tek bir işçi
# var (WORKER_ID tek), yani kira "iki işçi aynı görevi almasın" derdine
# karşı duruyor ve o dert bu kurulumda yok denecek kadar küçük. Buna
# karşılık kısa kiranın bedeli ölçüldü: kodlama yeteneği HİÇ çalışmıyordu.
LEASE_SECONDS = 1800


# --------------------------------------------------------------------------
# local operational bookkeeping (NOT company truth -- that stays in Postgres)
# --------------------------------------------------------------------------
def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"cycle_count": 0, "noop_count": 0, "issue_found_count": 0,
                "task_claimed_count": 0, "proposal_created_count": 0,
                "skipped_not_mine_count": 0, "last_issue_signature": None,
                "last_run_at": None}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


# --------------------------------------------------------------------------
# database access -- one-shot subprocess calls, exactly the pattern already
# used by jarvis/memory.py and jarvis/operator.py in this repository
# --------------------------------------------------------------------------
def _psql(sql: str, host: str | None, role: str | None = None, timeout_s: int = 15) -> list[Any]:
    body = f"SET SESSION AUTHORIZATION {role}; {sql}" if role else sql
    wrapped = f"BEGIN; {body} COMMIT;"
    psql = ["docker", "exec", "lcarlie-postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-U", "n8n", "-d", "n8n", "-Atc", wrapped]
    command = (["ssh", host, " ".join(
        ["docker exec lcarlie-postgres psql -X -q -v ON_ERROR_STOP=1 -U n8n -d n8n -Atc",
         f'"{wrapped}"']
    )] if host else psql)
    result = db_run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    if result.returncode:
        raise MemoryError(result.stderr.strip() or "loop query failed")
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _claim_task(host: str | None) -> dict[str, Any] | None:
    sql = (f"SELECT row_to_json(x) FROM (SELECT task_id,source_type,source_id,task_type,"
           f"idempotency_key,context_profile,lease_token,attempt_count "
           f"FROM core.ai_claim_task('{WORKER_ID}', {LEASE_SECONDS}, 'PROPOSE_ACTION')) x;")
    rows = _psql(sql, host, role="ai_writer")
    return rows[0] if rows else None


def _fail_task(task_id: int, lease_token: str, reason: str, host: str | None) -> None:
    safe_reason = reason.replace("'", "''")[:500]
    sql = (f"SELECT core.ai_fail_task({int(task_id)}, '{lease_token}'::uuid, "
           f"'FAILED_RETRYABLE', '{safe_reason}');")
    _psql(sql, host, role="ai_writer")


def _propose_action(task_id: int, lease_token: str, idempotency_key: str,
                    action_type: str, payload: dict[str, Any], host: str | None) -> int:
    escaped_key = idempotency_key.replace("'", "''")
    payload_json = json.dumps(payload, ensure_ascii=False).replace("'", "''")
    sql = (f"SELECT core.ai_propose_action({int(task_id)}, '{lease_token}'::uuid, "
           f"'{escaped_key}', '{action_type}', '{payload_json}'::jsonb) AS proposal_id;")
    rows = _psql(sql, host, role="ai_writer")
    return int(rows[0]) if rows else None


# --------------------------------------------------------------------------
# CodingExecutor bridge: a CODE_CHANGE_REVIEW task never builds a generic
# payload directly. Its spec (objective/allowed_files/test_command) lives on
# disk, written by a human via `jarvis-operator create-coding-task` --
# ai_writer has no SELECT on core.ai_task, so this is the same
# idempotency-key-carries-intent convention every other intent already uses,
# extended with a spec FILE instead of just a slug, because a coding
# objective and an allowlist cannot fit in an idempotency key.
# --------------------------------------------------------------------------
def _build_agency_payload(slug: str | None) -> dict[str, str] | None:
    """Ajans şartnamesinden gerçek yük. Şartname yoksa None.

    None donmek onemli: cagiran taraf o zaman eski genel yuke duser ve
    elle acilmis gorevler bozulmaz. Uydurulmus bir yuk dondurmek, bos
    yukten daha kotu olurdu.
    """
    if not slug:
        return None
    try:
        from .agency_store import load_spec
    except Exception:  # noqa: BLE001 - modul yoklugu bir durumdur
        return None
    spec = load_spec(slug)
    if not spec:
        return None
    payload = spec.get("payload")
    if not isinstance(payload, dict) or not payload:
        return None
    # `reason` onaylayan insanin ilk gordugu alandir; konsept adi ve urun
    # oraya yazilir ki kuyrukta ne oldugu slug okumadan anlasilsin.
    metin = payload.get("primary_text") or payload.get("headline") or ""
    payload = dict(payload)
    payload.setdefault("reason", " — ".join(
        parca for parca in (str(spec.get("product") or ""),
                            str(spec.get("concept_name") or ""),
                            str(metin)[:400]) if parca))
    return payload


# --------------------------------------------------------------------------
# Kreatif partisi kopruusu. CODE_CHANGE_REVIEW ile AYNI desendir: is burada
# yapilmaz, DISARIDA yapilmis ve diske yazilmis bir sonuc okunur.
#
# 🔴 UretIM BU DONGUDE KOSMAZ ve bu bilincli. Brief + 4 gorsel + ekip
# incelemesi olculdugunde ~8 dakika suruyor; 5 dakikalik dongude kosarsa
# dongu kendi kendini bloklar. Uretimi ayri bir timer yapar
# (lcarlie-kreatif-hat), bitince `jarvis-operator create-task
# KREATIF_INCELEME <parti>` ile gorevi acar. Dongu yalniz SONUCU okuyup
# sahibin onay kuyruguna koyar.
#
# 🔴 INCELEME YOKSA ONERI YAZILMAZ. Ekip bakmadan sahibin onune gorsel
# konmaz -- akisin butun anlami o ara adimdi.
KREATIF_KOK = Path(os.environ.get(
    "KREATIF_BRIEF_DIR", "/opt/lcarlie/jarvis-phase2/state/kreatif-brief"))
KREATIF_TABAN_URL = os.environ.get("KREATIF_TABAN_URL", "/kreatif")


def _build_brief_payload(slug: str) -> dict[str, str]:
    """Brief + promptlar hazir -> GORSEL URETIMI icin sahibin onayi.

    🔴 SAHIP KARARI (21.09.2026): "brief verilsin, uretim benim onayim
    olmadan yapilmasin ama promptlar hazirlansin."

    Bu yuzden haftalik kosu HIC GORSEL URETMEZ. Uretilen sey arastirmadir:
    rakip ne yapmis, ne tutmus, urun ne, hangi cumleler denetimden gecti ve
    image modeline yapistirilacak promptlar. Gorsel ancak sahip bu oneriyi
    ONAYLAYINCA uretilir -- fatura da, yayin riski de o andan sonra baslar.
    """
    if not slug:
        raise CodingTaskDenied(
            "KREATIF_BRIEF bir parti adi ister: jarvis:KREATIF_BRIEF:<parti>")
    yol = KREATIF_KOK / f"{slug}.json"
    if not yol.exists():
        raise CodingTaskDenied(f"brief bulunamadi: {yol}")
    try:
        brief = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CodingTaskDenied(f"brief okunamadi: {exc}") from exc
    from .kreatif_ozet import brief_ozeti
    return {"subject_ref": f"kreatif-brief:{slug}",
            "reason": brief_ozeti(brief, slug, KREATIF_TABAN_URL)}


def _build_kreatif_payload(slug: str) -> dict[str, str]:
    if not slug:
        raise CodingTaskDenied(
            "KREATIF_INCELEME bir parti adi ister: jarvis:KREATIF_INCELEME:<parti>")
    klasor = KREATIF_KOK / f"{slug}-gorseller"
    yol = klasor / "inceleme.json"
    if not yol.exists():
        raise CodingTaskDenied(
            f"kreatif partisi incelenmemis, oneri yazilmadi: {yol}")
    try:
        inceleme = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CodingTaskDenied(f"inceleme okunamadi: {exc}") from exc
    kareler = inceleme.get("gorseller") or []
    if not kareler:
        raise CodingTaskDenied(f"partide kare yok: {slug}")
    from .kreatif_ozet import onay_ozeti
    return {"subject_ref": f"kreatif:{slug}",
            "reason": onay_ozeti(inceleme, slug, KREATIF_TABAN_URL)}


def _build_coding_review_payload(slug: str) -> dict[str, str]:
    if not slug:
        raise CodingTaskDenied("CODE_CHANGE_REVIEW requires a slug: jarvis:CODE_CHANGE_REVIEW:<slug>")
    spec_path = CODING_TASK_PENDING_DIR / f"{slug}.json"
    if not spec_path.is_file():
        raise CodingTaskDenied(f"missing coding task spec: {spec_path}")
    try:
        spec = CodingTaskSpec.from_dict(json.loads(spec_path.read_text(encoding="utf-8")))
    except (ValueError, json.JSONDecodeError) as exc:
        raise CodingTaskDenied(f"invalid coding task spec: {exc}") from exc

    try:
        result = run_coding_task(spec, task_id=slug)
    except CodingExecutorError as exc:
        raise CodingTaskDenied(f"CodingExecutor could not run: {exc}") from exc

    if not result.success:
        evidence_path = getattr(result, "evidence_dir", None)
        detail = f"; evidence: {evidence_path}" if evidence_path else ""
        raise CodingTaskDenied(f"CodingExecutor denied: {result.denied_reason}{detail}")

    return {"subject_ref": f"coding-task:{slug}", "reason": summarize_for_proposal(result)}


# --------------------------------------------------------------------------
# observation + deterministic analysis (zero model calls)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Observation:
    health: dict[str, Any]
    agenda_count: int
    observed_at: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observe(memory: CompanyMemory) -> Observation:
    health_evidence = memory.get_system_status()
    health = health_evidence.records[0] if health_evidence.records else {}
    agenda_evidence = memory.get_company_agenda()
    agenda_count = len(agenda_evidence.records)
    payload = {"health": health, "agenda_count": agenda_count}
    content_hash = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return Observation(health=health, agenda_count=agenda_count,
                       observed_at=datetime.now(timezone.utc).isoformat(),
                       content_hash=content_hash)


@dataclass(frozen=True)
class Analysis:
    status: str  # NOOP | ISSUE
    reason: str
    signature: str | None
    evidence: dict[str, Any]


def analyze(observation: Observation) -> Analysis:
    """Deterministic rule set. No model call. No fabricated issue."""
    failed = int(observation.health.get("failed_executions") or 0)
    if failed > 0:
        return Analysis(
            status="ISSUE", reason=f"{failed} failed execution(s) detected",
            signature=f"failed_executions:{failed}",
            evidence={"failed_executions": failed, "checked_at": observation.health.get("checked_at")},
        )
    open_tasks = int(observation.health.get("open_tasks") or 0)
    leased = int(observation.health.get("leased_tasks") or 0)
    if open_tasks > 50:
        return Analysis(
            status="ISSUE", reason=f"{open_tasks} open tasks, queue may be stuck",
            signature=f"open_tasks_high:{open_tasks}",
            evidence={"open_tasks": open_tasks, "leased_tasks": leased},
        )
    return Analysis(status="NOOP", reason="no rule matched current evidence",
                    signature=None, evidence=observation.to_dict())


# --------------------------------------------------------------------------
# business signal layer (deterministic, advisory, zero model calls)
# --------------------------------------------------------------------------
# İş zekâsı katmanının yeniden okuma aralığı. Döngü 5 dakikada bir çalışıyor
# ve her turda 3 sorgu atıyordu: günde 864 sorgu. Oysa okuduğu üç görünüm
# (karar_ozet, sirket_gundemi, acik_isler) insan hızında değişir -- onay
# bekleyen karar sayısı beş dakikada bir değişmez.
#
# TAKAS AÇIK: yeni bir koşul en fazla bu süre kadar geç görünür. Onay
# darboğazı ve iş yaşlanması için bir saat fazlasıyla yeterli; anlık
# tepki gereken altyapı kuralları (failed_executions) zaten analyze()'de ve
# her turda çalışmaya devam ediyor.
BUSINESS_TTL_S = float(os.environ.get("JARVIS_BUSINESS_TTL_S", "3600"))

BUSINESS_FINDING_NOTE = (
    "Deterministic business signal. Jarvis cannot enqueue its own task "
    "(ai_enqueue_task is granted to human_approver only, by design). This "
    "finding is recorded for a human to act on."
)


def _business_signals(memory: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Advisory rules over mart.karar_ozet / sirket_gundemi / acik_isler.

    Never raises into the operational path: the loop must still claim and
    propose work even when this layer is unavailable. Only signatures absent
    from the previous cycle are logged, so a standing condition is recorded
    once instead of every five minutes.
    """
    if not hasattr(memory, "get_open_work"):
        return {"status": "SKIPPED", "reason": "adapter has no get_open_work", "new": 0}

    # TTL içindeyse hiç sorgu atılmaz. Atlanan tur sessiz değil: durumu ve
    # kalan süresi cycle raporunda görünür, yoksa katmanın çalışıp
    # çalışmadığı anlaşılmaz.
    now = time()
    last = float(state.get("business_last_run_at") or 0.0)
    age = now - last
    if last and age < BUSINESS_TTL_S:
        return {"status": "CACHED", "new": 0,
                "age_s": round(age, 1),
                "next_in_s": round(BUSINESS_TTL_S - age, 1),
                "codes": list(state.get("business_signal_codes") or ()),
                "signals": len(state.get("business_signatures") or ())}
    try:
        report = business_signals.run(memory)
    except Exception as exc:  # noqa: BLE001 - danisma katmani dongoyu kiramaz
        gunluk.yut("loop", "_business_signals", exc,
                   neden="danisma katmani dongoyu kiramaz",
                   agirlik=gunluk.AGIRLIK_ARIZA)
        return {"status": "ERROR", "error": str(exc)[:300], "new": 0}

    previous = set(state.get("business_signatures") or [])
    fresh = [signal for signal in report.signals if signal.signature not in previous]
    for signal in fresh:
        _append_jsonl(FINDINGS_LOG, {
            "observed_at": report.observed_at, "signature": signal.signature,
            "reason": signal.summary, "evidence": signal.evidence,
            "signal_code": signal.code, "severity": signal.severity,
            "note": BUSINESS_FINDING_NOTE,
        })
    state["business_signatures"] = [signal.signature for signal in report.signals]
    state["business_signal_codes"] = [signal.code for signal in report.signals]
    state["business_last_run_at"] = now
    if fresh:
        state["business_finding_count"] = state.get("business_finding_count", 0) + len(fresh)
    return {"status": report.status, "signals": len(report.signals), "new": len(fresh),
            "codes": [signal.code for signal in report.signals],
            "skipped_rules": len(report.skipped), "report_hash": report.content_hash}


# --------------------------------------------------------------------------
# one operational cycle
# --------------------------------------------------------------------------
def run_cycle(host: str | None = "lcarlie") -> dict[str, Any]:
    started = perf_counter()
    state = _load_state()
    timings: dict[str, float] = {}

    memory = CompanyMemory(host=host)
    t0 = perf_counter()
    observation = observe(memory)
    timings["observe_ms"] = round((perf_counter() - t0) * 1000, 3)

    t0 = perf_counter()
    analysis = analyze(observation)
    timings["analyze_ms"] = round((perf_counter() - t0) * 1000, 3)

    finding_logged = False
    if analysis.status == "ISSUE":
        if analysis.signature != state.get("last_issue_signature"):
            _append_jsonl(FINDINGS_LOG, {
                "observed_at": observation.observed_at, "signature": analysis.signature,
                "reason": analysis.reason, "evidence": analysis.evidence,
                "note": ("Jarvis cannot enqueue its own task (ai_enqueue_task is granted to "
                         "human_approver only, by design). This finding is recorded for a "
                         "human or another authorized source to act on."),
            })
            finding_logged = True
            state["issue_found_count"] = state.get("issue_found_count", 0) + 1
        state["last_issue_signature"] = analysis.signature
    else:
        state["last_issue_signature"] = None

    t0 = perf_counter()
    business = _business_signals(memory, state)
    timings["business_ms"] = round((perf_counter() - t0) * 1000, 3)

    # -- claim at most one PROPOSE_ACTION task, fail-safe on anything else --
    t0 = perf_counter()
    claimed = None
    try:
        claimed = _claim_task(host)
    except MemoryError as exc:
        claimed_error = str(exc)
    else:
        claimed_error = None
    timings["claim_ms"] = round((perf_counter() - t0) * 1000, 3)

    result = "NOOP"
    proposal_id = None
    task_detail = None

    if claimed_error:
        result = "CLAIM_FAILED"
        task_detail = {"error": claimed_error}
    elif claimed is None:
        result = "NOOP"
    elif claimed.get("task_type") != "PROPOSE_ACTION":
        _fail_task(claimed["task_id"], claimed["lease_token"],
                  "not owned by jarvis operational loop; wrong task_type", host)
        result = "SKIPPED_NOT_MINE"
        state["skipped_not_mine_count"] = state.get("skipped_not_mine_count", 0) + 1
        task_detail = {"task_id": claimed["task_id"], "task_type": claimed.get("task_type")}
    else:
        state["task_claimed_count"] = state.get("task_claimed_count", 0) + 1
        key = claimed.get("idempotency_key") or ""
        parts = key.split(":", 2)
        internal_intent = parts[1] if len(parts) >= 2 and parts[0] == "jarvis" else None
        slug = parts[2] if len(parts) >= 3 else None
        t0 = perf_counter()
        try:
            contract = ContractCache(memory).get()
            if internal_intent is None:
                raise FirewallError(f"idempotency_key does not follow jarvis:<intent>:<slug>: {key!r}")

            if internal_intent == "KREATIF_BRIEF":
                state["kreatif_brief_count"] = state.get("kreatif_brief_count", 0) + 1
                payload = _build_brief_payload(slug)
            elif internal_intent == "KREATIF_INCELEME":
                state["kreatif_task_count"] = state.get("kreatif_task_count", 0) + 1
                payload = _build_kreatif_payload(slug)
            elif internal_intent == "CODE_CHANGE_REVIEW":
                # CodingExecutor runs here, inside the firewall try/except: a
                # scope violation, failing tests, or a run error all become a
                # CodingTaskDenied -> caught below -> task fails, no proposal.
                state["coding_task_count"] = state.get("coding_task_count", 0) + 1
                payload = _build_coding_review_payload(slug)
            else:
                # Once burada HER zaman genel bir yer tutucu yaziliyordu ve
                # onay kuyruguna ici bos oneri dusuyordu. Ajans sartnamesi
                # varsa gercek metin kullanilir; yoksa eski davranis surer.
                payload = _build_agency_payload(slug)
                if payload is None:
                    if slug:
                        # 🔴 SARTNAME_YOK — SLUG VERILDI AMA DOSYA YOK.
                        # Eskiden burada genel bir yer tutucu yaziliyordu ve
                        # onay kuyruguna "Automated proposal from
                        # operator-originated task ..." diye ICI BOS bir oneri
                        # dusuyordu. agency_store.py bunu kendi docstring'inde
                        # zaten KUSUR diye tarif ediyor: "Onaylayacak insan
                        # reklamin NE DEDIGINI goremiyor. Ici bos bir oneriyi
                        # onaylamak, onay degildir."
                        #
                        # Uretimde olculdu: bir degisiklik onerisinin sartname
                        # dosyasi silinince gorev yine de PROPOSED oldu ve
                        # kuyruga anlamsiz bir satir dustu -- onaylanabilir
                        # halde. Slug verilmisse cagiran taraf bir sartname
                        # KASTETMISTIR; dosya yoksa bu bir hatadir, yer tutucu
                        # degil. Gorev duser, kuyruk temiz kalir.
                        raise CodingTaskDenied(
                            f"SARTNAME_YOK: '{slug}' icin sartname dosyasi "
                            "bulunamadi; ici bos oneri yazilmadi")
                    # Slug hic verilmemisse eski davranis surer: elle acilmis
                    # sade gorevler bozulmaz.
                    payload = {"subject_ref": key,
                               "reason": f"Automated proposal from operator-originated task {key}"}

            validated = validate_proposal(internal_intent, payload, contract,
                                          idempotency_key=f"action:{key}")
            proposal_id = _propose_action(claimed["task_id"], claimed["lease_token"],
                                          validated["idempotency_key"],
                                          validated["action_type"], validated["payload"], host)
            result = "PROPOSED"
            state["proposal_created_count"] = state.get("proposal_created_count", 0) + 1
            task_detail = {"task_id": claimed["task_id"], "internal_intent": internal_intent,
                          "action_type": validated["action_type"], "proposal_id": proposal_id}
        except CodingTaskDenied as exc:
            _fail_task(claimed["task_id"], claimed["lease_token"], str(exc)[:500], host)
            result = "CODING_TASK_DENIED"
            state["coding_task_denied_count"] = state.get("coding_task_denied_count", 0) + 1
            task_detail = {"task_id": claimed["task_id"], "error": str(exc)}
        except (FirewallError, ContractDriftError, MemoryError) as exc:
            _fail_task(claimed["task_id"], claimed["lease_token"], str(exc)[:500], host)
            result = "FIREWALL_REJECTED"
            task_detail = {"task_id": claimed["task_id"], "error": str(exc)}
        timings["propose_ms"] = round((perf_counter() - t0) * 1000, 3)

    if result == "NOOP" and not finding_logged:
        state["noop_count"] = state.get("noop_count", 0) + 1

    state["cycle_count"] = state.get("cycle_count", 0) + 1
    state["last_run_at"] = observation.observed_at
    _save_state(state)

    coding_cycle = bool(claimed and str(claimed.get("idempotency_key", "")).startswith("jarvis:CODE_CHANGE_REVIEW:"))
    report = {
        "cycle": state["cycle_count"], "result": result,
        "analysis_status": analysis.status, "analysis_reason": analysis.reason,
        "finding_logged": finding_logged, "task_detail": task_detail,
        "business": business,
        "observation_hash": observation.content_hash,
        "timings_ms": timings, "total_ms": round((perf_counter() - started) * 1000, 3),
        "model_calls": None if coding_cycle else 0,
        "external_provider_calls": None if coding_cycle else 0,
        "coding_model_usage": "NOT_MEASURED" if coding_cycle else "NOT_USED",
        "external_actions": 0,
        "state_summary": {k: v for k, v in state.items() if k.endswith("_count")},
    }
    _append_jsonl(AUDIT_LOG, report)
    return report
