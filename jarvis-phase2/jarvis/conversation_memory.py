"""Conversation memory: what was said, and what is worth keeping.

Until now every message started from nothing -- the operator could not say
"dün Vireon'u konuşmuştuk", because there was no yesterday. This keeps the
thread on disk and hands back only the last few turns, under a hard character
budget, for the same reason the Context Compiler never ships the whole of
Company Memory: a model given everything answers worse, not better.

Two stores, deliberately separate:

  turns  -- the rolling transcript. Append-only, trimmed, and read back as a
            short window. Cheap to write, cheap to forget.
  notes  -- the few things that should survive the window: a decision, a
            preference, a correction. Written only when asked, never inferred,
            because a memory that guesses is worse than no memory.

Everything degrades: a missing or unreadable file is an empty history, never
an error. A conversation must not fail because its transcript did.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
MEMORY_DIR = STATE_DIR / "conversation"
# Aramaya hazir dizin (jarvis.hatira) YALNIZ gercek durum dizininde yazilir.
# Testler JARVIS_STATE_DIR'i gecici bir klasore cevirip modulu yeniden
# yukluyor; dosya katmani boylece izole oluyor ama dizin ORTAK postgres'te
# duruyor. Bu kapi olmadan test metinleri uretim dizinine karisiyordu
# (olculdu: 17 satirin hepsi test verisiydi).
_VARSAYILAN_STATE = Path("/opt/lcarlie/jarvis-phase2/state")


def _dizin_acik() -> bool:
    return STATE_DIR == _VARSAYILAN_STATE

# How much of the past a turn is allowed to carry. Six turns is enough for
# "onu değil, diğerini" to resolve; more than that and the model starts
# answering the old question instead of the new one.
DEFAULT_TURNS = 6
MAX_HISTORY_CHARS = 1800
MAX_TURN_CHARS = 600
# The transcript is trimmed rather than rotated: this is a working memory, not
# an archive, and the audit trail already lives in audit.jsonl.
MAX_STORED_TURNS = 400
MAX_NOTES = 60


def _path(thread: str, name: str) -> Path:
    safe = "".join(ch for ch in thread if ch.isalnum() or ch in "-_") or "operator"
    return MEMORY_DIR / f"{safe}.{name}.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # one bad line must not lose the rest
    except OSError:
        return []
    return rows


def _write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(MEMORY_DIR, 0o750)
    tmp = path.with_suffix(".tmp")
    body = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    os.chmod(path, 0o640)


# --- transcript ---------------------------------------------------------
def record(message: str, answer: str, intent: str = "", thread: str = "operator",
           **meta: Any) -> None:
    """Append one exchange. Never raises: losing a transcript line is not a
    reason to fail the turn the user is waiting on."""
    try:
        rows = _read(_path(thread, "turns"))
        rows.append({"at": _now(), "intent": intent,
                     "user": (message or "")[:MAX_TURN_CHARS],
                     "jarvis": (answer or "")[:MAX_TURN_CHARS], **meta})
        _write(_path(thread, "turns"), rows[-MAX_STORED_TURNS:])
    except Exception:  # noqa: BLE001 - memory is an aid, not a dependency
        pass


def history(turns: int = DEFAULT_TURNS, thread: str = "operator") -> list[dict[str, str]]:
    """The last few exchanges as chat messages, newest last, budget-capped.

    The budget is applied from the most recent backwards, so a single long
    answer in the past cannot crowd out what was just said.
    """
    rows = _read(_path(thread, "turns"))[-turns:]
    messages: list[dict[str, str]] = []
    used = 0
    for row in reversed(rows):
        pair = [{"role": "user", "content": str(row.get("user") or "")},
                {"role": "assistant", "content": str(row.get("jarvis") or "")}]
        size = sum(len(m["content"]) for m in pair)
        if used + size > MAX_HISTORY_CHARS:
            break
        messages = pair + messages
        used += size
    return [m for m in messages if m["content"]]


# --- durable notes ------------------------------------------------------
def remember(note: str, source: str = "operator", thread: str = "operator") -> bool:
    """Keep one fact beyond the transcript window.

    Only ever called explicitly. Nothing here infers what is worth
    remembering, because a memory that quietly decides for itself is one the
    operator cannot correct.
    """
    note = " ".join((note or "").split())
    if not note:
        return False
    try:
        rows = [row for row in _read(_path(thread, "notes"))
                if row.get("note") != note]
        rows.append({"at": _now(), "note": note[:400], "source": source})
        _write(_path(thread, "notes"), rows[-MAX_NOTES:])
        # Dosya yazildi: not artik guvende. Dizin bunun USTUNDE bir arama
        # katmani, kayit kaynagi degil -- bu yuzden basarisizligi yutuluyor
        # ve donus degerini DEGISTIRMIYOR. Dizin kaybolursa yeniden kurulur;
        # not kaybolursa kurulamaz.
        if _dizin_acik():
            try:
                from jarvis import hatira
                hatira.kaydet(note[:400], thread=thread)
            except Exception:  # noqa: BLE001
                pass
        return True
    except Exception:  # noqa: BLE001
        return False


def forget(fragment: str, thread: str = "operator") -> int:
    """Drop notes containing this fragment. Returns how many went."""
    fragment = (fragment or "").strip().casefold()
    if not fragment:
        return 0
    try:
        rows = _read(_path(thread, "notes"))
        keep = [row for row in rows if fragment not in str(row.get("note", "")).casefold()]
        _write(_path(thread, "notes"), keep)
        # Unutulan not dizinde kalirsa aramada cikmaya devam eder; geri
        # alinmis bir karari hatirlayan hafiza, hatirlamayandan kotudur.
        if _dizin_acik():
            try:
                from jarvis import hatira
                hatira.unut(fragment, thread=thread)
            except Exception:  # noqa: BLE001
                pass
        return len(rows) - len(keep)
    except Exception:  # noqa: BLE001
        return 0


def notes(thread: str = "operator") -> list[str]:
    return [str(row.get("note")) for row in _read(_path(thread, "notes")) if row.get("note")]


def note_rows(thread: str = "operator") -> list[dict[str, Any]]:
    """Notlar, yazildiklari zaman ve kaynagiyla birlikte -- en yeni once.

    notes() yalnız metni döner; bir prompt'a girecek olan budur ve öyle
    kalmalı. Panel ise notu DENETLEMEK için var: "bu ne zaman, kim yazdı"
    sorusunun cevabı olmadan operatör eski bir kararı yenisinden ayırt
    edemez. Bu yüzden ayrı bir kapı; notes()'un yükü büyümüyor.
    """
    rows = [row for row in _read(_path(thread, "notes")) if row.get("note")]
    return [{"at": str(row.get("at") or ""), "note": str(row.get("note")),
             "source": str(row.get("source") or "")} for row in reversed(rows)]


def notes_block(thread: str = "operator", limit: int = 12,
                soru: str = "") -> str:
    """Notes rendered for a system prompt, or an empty string when there are
    none -- so a fresh install adds nothing to the context at all.

    `soru` verilirse once ONA ANLAMCA YAKIN notlar konur, sonra kalan yer
    son notlarla doldurulur. Verilmezse davranis birebir eskisi gibidir:
    son `limit` not, sirasiyla. Boylece mevcut cagirilar degismez.

    Neden gerek vardi: not sayisi MAX_NOTES'a (60) yaklastikca "son 12 not"
    ile "bu soruyla ilgili 12 not" birbirinden uzaklasir. Eskisi tarihe
    gore seciyordu; soru sorulduysa alaka daha iyi bir olcut.
    """
    kept = notes(thread)
    if not kept:
        return ""

    secilen: list[str] = []
    if soru and _dizin_acik():
        try:
            from jarvis import hatira
            for n in hatira.ara(soru, limit=limit, thread=thread):
                if n not in secilen:
                    secilen.append(n)
        except Exception:  # noqa: BLE001
            pass  # dizin yoksa asagidaki tarih sirasi devrali

    for n in reversed(kept):
        if len(secilen) >= limit:
            break
        if n not in secilen:
            secilen.append(n)

    if not secilen:
        return ""
    return ("Daha önce konuşulanlardan aklında tutman istenenler:\n"
            + "\n".join(f"- {note}" for note in secilen))


def status(thread: str = "operator") -> dict[str, int]:
    return {"turns": len(_read(_path(thread, "turns"))),
            "notes": len(_read(_path(thread, "notes")))}
