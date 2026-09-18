"""Deterministic business-signal analysis over existing Company Memory views.

Complements `loop.analyze()`, which only carries infrastructure rules
(failed_executions, open_tasks). Nothing here calls a model, proposes an
action, or writes anywhere: it reads allowlisted canonical views and returns
findings for a human.

Design rule: a rule that cannot be evaluated is SKIPPED and reported as
skipped -- never downgraded into a finding. Column vocabularies (Turkish
enum values of `oncelik`, `durum`, `tur`) are deliberately never hardcoded,
because guessing them would manufacture intelligence that the data does not
support. Every rule here is structural or temporal instead.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

# mart.karar_ozet / mart.sirket_gundemi / mart.acik_isler column names, taken
# from orchestrator/context_queries.sql -- the canonical definition.
DECISION_AWAITING_APPROVAL = "insan_onayi_bekleyen"
DECISION_POSTPONED = "ertelenen"
DECISION_INCONCLUSIVE = "sonucsuz"
DECISION_RED_TEAM = "red_team_itirazi"
DECISION_OBJECTED = "itiraz_alan_karar"
DECISION_TOTAL = "toplam"

AGENDA_CREATED = "olusturma"
AGENDA_SOURCE_PLAN = "kaynak_plani"
AGENDA_QUESTION = "soru"
AGENDA_ID = "soru_id"

WORK_KIND = "tur"
WORK_TIME = "zaman"
WORK_KEY = "anahtar"


DEFAULT_THRESHOLDS: dict[str, float] = {
    "approval_backlog_min": 5,
    "approval_backlog_critical": 15,
    "decision_stall_ratio": 0.30,
    "decision_stall_min_total": 10,
    "agenda_age_days": 14,
    "agenda_age_min_count": 3,
    "open_work_age_days": 7,
    "open_work_age_min_count": 3,
    "work_concentration_ratio": 0.60,
    "work_concentration_min_count": 5,
}


class RuleSkipped(Exception):
    """Raised by a rule whose inputs are absent or unusable."""


@dataclass(frozen=True)
class Signal:
    code: str
    severity: str  # INFO | WARN | CRITICAL
    summary: str
    evidence: dict[str, Any]
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SignalReport:
    signals: list[Signal] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    observed_at: str = ""
    content_hash: str = ""
    model_calls: int = 0
    external_actions: int = 0

    @property
    def status(self) -> str:
        if any(s.severity == "CRITICAL" for s in self.signals):
            return "CRITICAL"
        return "ISSUE" if self.signals else "NOOP"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "signals": [s.to_dict() for s in self.signals],
            "skipped": self.skipped,
            "observed_at": self.observed_at,
            "content_hash": self.content_hash,
            "model_calls": self.model_calls,
            "external_actions": self.external_actions,
        }


def _as_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        raise RuleSkipped("value is not a number")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuleSkipped(f"value is not a number: {value!r}") from exc


def _parse_ts(value: Any) -> datetime | None:
    """Tolerant timestamp parse. Returns None rather than guessing."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace(" ", "T", 1)
    # Postgres renders +03 where fromisoformat wants +03:00.
    text = re.sub(r"([+-]\d{2})$", r"\1:00", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_days(value: Any, now: datetime) -> float | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() / 86400.0


def _first(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise RuleSkipped("no rows returned")
    return records[0]


# --------------------------------------------------------------------------
# rules -- each returns a Signal or None, or raises RuleSkipped
# --------------------------------------------------------------------------
def rule_approval_backlog(decision: list[dict[str, Any]], _agenda, _work,
                          now: datetime, t: dict[str, float]) -> Signal | None:
    waiting = _as_int(_first(decision).get(DECISION_AWAITING_APPROVAL))
    if waiting < t["approval_backlog_min"]:
        return None
    severity = "CRITICAL" if waiting >= t["approval_backlog_critical"] else "WARN"
    return Signal(
        code="approval_backlog",
        severity=severity,
        summary=f"{waiting} karar insan onayı bekliyor; karar akışı onayda tıkanmış durumda.",
        evidence={DECISION_AWAITING_APPROVAL: waiting,
                  "threshold": t["approval_backlog_min"]},
        signature=f"approval_backlog:{waiting}",
    )


def rule_decision_stall(decision: list[dict[str, Any]], _agenda, _work,
                        now: datetime, t: dict[str, float]) -> Signal | None:
    row = _first(decision)
    total = _as_int(row.get(DECISION_TOTAL))
    if total < t["decision_stall_min_total"]:
        raise RuleSkipped(f"only {total} decisions, below minimum sample")
    stalled = _as_int(row.get(DECISION_POSTPONED)) + _as_int(row.get(DECISION_INCONCLUSIVE))
    ratio = stalled / total
    if ratio < t["decision_stall_ratio"]:
        return None
    return Signal(
        code="decision_stall",
        severity="WARN",
        summary=(f"Kararların %{ratio * 100:.0f}'i ertelenmiş veya sonuçsuz "
                 f"({stalled}/{total}); karar üretimi sonuca bağlanmıyor."),
        evidence={DECISION_POSTPONED: _as_int(row.get(DECISION_POSTPONED)),
                  DECISION_INCONCLUSIVE: _as_int(row.get(DECISION_INCONCLUSIVE)),
                  DECISION_TOTAL: total, "ratio": round(ratio, 4)},
        signature=f"decision_stall:{stalled}/{total}",
    )


def rule_red_team_objection(decision: list[dict[str, Any]], _agenda, _work,
                            now: datetime, t: dict[str, float]) -> Signal | None:
    row = _first(decision)
    objections = _as_int(row.get(DECISION_RED_TEAM))
    if objections < 1:
        return None
    affected = _as_int(row.get(DECISION_OBJECTED))
    return Signal(
        code="red_team_objection",
        severity="CRITICAL",
        summary=(f"{objections} red-team itirazı açık ({affected} kararı etkiliyor); "
                 f"itiraz kapatılmadan ilerlemek risk taşır."),
        evidence={DECISION_RED_TEAM: objections, DECISION_OBJECTED: affected},
        signature=f"red_team_objection:{objections}:{affected}",
    )


def rule_agenda_aging(_decision, agenda: list[dict[str, Any]], _work,
                      now: datetime, t: dict[str, float]) -> Signal | None:
    if not agenda:
        raise RuleSkipped("agenda is empty")
    ages = [(row, _age_days(row.get(AGENDA_CREATED), now)) for row in agenda]
    datable = [(row, age) for row, age in ages if age is not None]
    if not datable:
        raise RuleSkipped(f"no parseable {AGENDA_CREATED} timestamp")
    stale = [(row, age) for row, age in datable if age >= t["agenda_age_days"]]
    if len(stale) < t["agenda_age_min_count"]:
        return None
    oldest = max(stale, key=lambda pair: pair[1])
    return Signal(
        code="agenda_aging",
        severity="WARN",
        summary=(f"{len(stale)} gündem maddesi {t['agenda_age_days']:.0f} günden eski; "
                 f"en eskisi {oldest[1]:.0f} gündür açık."),
        evidence={"stale_count": len(stale), "checked": len(datable),
                  "oldest_days": round(oldest[1], 1),
                  "oldest_id": oldest[0].get(AGENDA_ID),
                  "oldest_question": str(oldest[0].get(AGENDA_QUESTION) or "")[:200]},
        signature=f"agenda_aging:{len(stale)}",
    )


def rule_agenda_without_source_plan(_decision, agenda: list[dict[str, Any]], _work,
                                    now: datetime, t: dict[str, float]) -> Signal | None:
    if not agenda:
        raise RuleSkipped("agenda is empty")
    missing = [row for row in agenda
               if not str(row.get(AGENDA_SOURCE_PLAN) or "").strip()]
    if not missing:
        return None
    return Signal(
        code="agenda_without_source_plan",
        severity="INFO",
        summary=(f"{len(missing)} gündem maddesinin kaynak planı yok; "
                 f"bu sorular veriyle cevaplanamaz durumda."),
        evidence={"missing_count": len(missing), "agenda_size": len(agenda),
                  "ids": [row.get(AGENDA_ID) for row in missing][:10]},
        signature=f"agenda_without_source_plan:{len(missing)}",
    )


def rule_open_work_aging(_decision, _agenda, work: list[dict[str, Any]],
                         now: datetime, t: dict[str, float]) -> Signal | None:
    if not work:
        raise RuleSkipped("no open work rows")
    ages = [(row, _age_days(row.get(WORK_TIME), now)) for row in work]
    datable = [(row, age) for row, age in ages if age is not None]
    if not datable:
        raise RuleSkipped(f"no parseable {WORK_TIME} timestamp")
    stale = [(row, age) for row, age in datable if age >= t["open_work_age_days"]]
    if len(stale) < t["open_work_age_min_count"]:
        return None
    oldest = max(stale, key=lambda pair: pair[1])
    by_kind: dict[str, int] = {}
    for row, _ in stale:
        by_kind[str(row.get(WORK_KIND) or "?")] = by_kind.get(str(row.get(WORK_KIND) or "?"), 0) + 1
    return Signal(
        code="open_work_aging",
        severity="WARN",
        summary=(f"{len(stale)} açık iş {t['open_work_age_days']:.0f} günden eski; "
                 f"en eskisi {oldest[1]:.0f} gün."),
        evidence={"stale_count": len(stale), "checked": len(datable),
                  "oldest_days": round(oldest[1], 1),
                  "oldest_key": oldest[0].get(WORK_KEY),
                  "by_kind": by_kind},
        signature=f"open_work_aging:{len(stale)}",
    )


def rule_open_work_concentration(_decision, _agenda, work: list[dict[str, Any]],
                                 now: datetime, t: dict[str, float]) -> Signal | None:
    if len(work) < t["work_concentration_min_count"]:
        raise RuleSkipped(f"only {len(work)} open work rows, below minimum sample")
    by_kind: dict[str, int] = {}
    for row in work:
        kind = str(row.get(WORK_KIND) or "").strip()
        if not kind:
            raise RuleSkipped(f"open work row without {WORK_KIND}")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    top_kind, top_count = max(by_kind.items(), key=lambda pair: pair[1])
    ratio = top_count / len(work)
    if ratio < t["work_concentration_ratio"]:
        return None
    return Signal(
        code="open_work_concentration",
        severity="INFO",
        summary=(f"Açık işlerin %{ratio * 100:.0f}'i tek bir alanda toplanmış "
                 f"('{top_kind}', {top_count}/{len(work)}); darboğaz bu alanda."),
        evidence={"kind": top_kind, "count": top_count, "total": len(work),
                  "ratio": round(ratio, 4), "by_kind": by_kind},
        signature=f"open_work_concentration:{top_kind}:{top_count}",
    )


RULES = (
    rule_red_team_objection,
    rule_approval_backlog,
    rule_decision_stall,
    rule_agenda_aging,
    rule_open_work_aging,
    rule_agenda_without_source_plan,
    rule_open_work_concentration,
)


def analyze_business(decision_summary: list[dict[str, Any]],
                     agenda: list[dict[str, Any]],
                     open_work: list[dict[str, Any]],
                     now: datetime | None = None,
                     thresholds: dict[str, float] | None = None) -> SignalReport:
    now = now or datetime.now(timezone.utc)
    limits = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        limits.update(thresholds)

    signals: list[Signal] = []
    skipped: list[dict[str, str]] = []
    for rule in RULES:
        try:
            signal = rule(decision_summary, agenda, open_work, now, limits)
        except RuleSkipped as exc:
            skipped.append({"rule": rule.__name__, "reason": str(exc)})
            continue
        if signal is not None:
            signals.append(signal)

    severity_order = {"CRITICAL": 0, "WARN": 1, "INFO": 2}
    signals.sort(key=lambda s: (severity_order.get(s.severity, 9), s.code))

    payload = {"signatures": [s.signature for s in signals],
               "skipped": [entry["rule"] for entry in skipped]}
    digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return SignalReport(signals=signals, skipped=skipped,
                        observed_at=now.isoformat(), content_hash=digest)


def collect(memory: Any) -> dict[str, list[dict[str, Any]]]:
    """Read the three canonical views through the existing allowlisted adapter."""
    return {
        "decision_summary": memory.get_company_context().records,
        "agenda": memory.get_company_agenda().records,
        "open_work": memory.get_open_work().records,
    }


def run(memory: Any, now: datetime | None = None,
        thresholds: dict[str, float] | None = None) -> SignalReport:
    data = collect(memory)
    return analyze_business(data["decision_summary"], data["agenda"],
                            data["open_work"], now=now, thresholds=thresholds)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    from .memory import CompanyMemory, MemoryError

    parser = argparse.ArgumentParser(description="Deterministic business signals (read-only).")
    parser.add_argument("--host", default=os.environ.get("JARVIS_SSH_HOST") or None,
                        help="SSH alias; omit on the server (local-docker transport).")
    args = parser.parse_args(argv)

    try:
        report = run(CompanyMemory(host=args.host))
    except MemoryError as exc:
        print(json.dumps({"status": "MEMORY_ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
