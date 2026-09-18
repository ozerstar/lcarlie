"""Turkish morphology for the one decision that actually needs it.

Three bugs in a row came from hand-written string rules: "İ".casefold() is not
"i", "sil" hides inside "nasılsın", and "yapabiliyoruz" begins with "yap". The
first two are tokenisation and folding problems and are fixed without a
dependency. The third is not: telling the imperative "yap" from the ability
"yapabiliyoruz" is morphology, and a suffix table will keep leaking.

zeyrek answers it directly -- "yap" parses as Verb+Imp, "yapabiliyoruz" as
Verb+Able+Prog -- so the suffix table is replaced by an analysis. A
lemmatiser alone would have made this WORSE: it maps "yapabiliyoruz" to
"yapmak", which then matches "yap" again.

Everything here degrades to None or to the input. If the venv that carries
zeyrek is not the interpreter in use -- the test suite runs on the system
python -- callers fall back to the existing rules and behave exactly as they
did before.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
from functools import lru_cache

_WORD = re.compile(r"[0-9A-Za-zÇĞİIÖŞÜçğıiöşü']+")

_ANALYZER = None
_DEASCIIFIER = None
MORPHOLOGY_AVAILABLE = False
DEASCIIFIER_AVAILABLE = False

try:  # pragma: no cover - availability depends on the interpreter in use
    os.environ.setdefault(
        "NLTK_DATA", os.environ.get("JARVIS_NLTK_DATA",
                                    "/opt/lcarlie/jarvis-phase2/nltk_data"))
    import zeyrek  # type: ignore

    _ANALYZER = zeyrek.MorphAnalyzer()
    MORPHOLOGY_AVAILABLE = True
except Exception:  # noqa: BLE001 - absence is a state, not an error
    _ANALYZER = None

try:  # pragma: no cover
    from turkish.deasciifier import Deasciifier  # type: ignore

    _DEASCIIFIER = Deasciifier
    DEASCIIFIER_AVAILABLE = True
except Exception:  # noqa: BLE001
    _DEASCIIFIER = None


def words(text: str) -> list[str]:
    """Whole words, punctuation dropped. Comparing tokens instead of scanning
    for substrings is what keeps "sil" out of "nasılsın"."""
    return _WORD.findall(text or "")


def deasciify(text: str) -> str:
    """"nasilsin" -> "nasılsın". Returns the input unchanged when unavailable,
    and never touches a string that already carries Turkish letters."""
    if not text or _DEASCIIFIER is None:
        return text
    if any(character in text for character in "çğıöşüÇĞİÖŞÜ"):
        return text
    try:
        return _DEASCIIFIER(text).convert_to_turkish()
    except Exception:  # noqa: BLE001
        return text


@lru_cache(maxsize=4096)
def imperative_stem(word: str) -> str | None:
    """The verb stem if this word is a POSITIVE imperative, else None.

    A negative imperative ("yapmayın", "yayınlamayın") is a prohibition -- the
    opposite of an instruction to act -- so it is deliberately not reported as
    a command.

    Returns None, not False, when morphology is unavailable, so a caller can
    tell "not a command" from "could not tell".
    """
    if _ANALYZER is None or not word:
        return None
    try:
        # zeyrek prints its parse trace to stdout; keep it out of the logs.
        with contextlib.redirect_stdout(io.StringIO()):
            parses = _ANALYZER.analyze(word)
    except Exception:  # noqa: BLE001
        return None
    for group in parses or ():
        for parse in (group if isinstance(group, list) else [group]):
            morphemes = getattr(parse, "morphemes", None) or ()
            if "Imp" not in morphemes or "Neg" in morphemes:
                continue
            lemma = (getattr(parse, "lemma", "") or "").casefold()
            for ending in ("mak", "mek"):
                if lemma.endswith(ending):
                    return lemma[: -len(ending)]
            return lemma or None
    return None


@lru_cache(maxsize=4096)
def is_positive_imperative(word: str) -> bool | None:
    """Is this word a command, in mood terms alone?

    True for an imperative that is not negated, False for anything else, None
    when morphology is unavailable.

    Deliberately says nothing about WHICH verb it is. A derived verb does not
    lemmatise to its own surface form -- "değiştir" is the causative of
    "değiş", "durdur" of "dur" -- so matching the lemma against a table of
    surface stems silently fails on exactly the verbs that matter. The caller
    already knows which verb it is looking at; it needs to know whether the
    speaker is ordering or asking.
    """
    if _ANALYZER is None or not word:
        return None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            parses = _ANALYZER.analyze(word)
    except Exception:  # noqa: BLE001
        return None
    for group in parses or ():
        for parse in (group if isinstance(group, list) else [group]):
            morphemes = getattr(parse, "morphemes", None) or ()
            if "Imp" in morphemes and "Neg" not in morphemes:
                return True
    return False


def is_imperative_of(word: str, stems: frozenset[str]) -> bool | None:
    """Is this word a command formed from one of these verb stems?

    None means morphology could not answer and the caller should fall back.
    """
    stem = imperative_stem(word)
    if stem is None:
        return None if not MORPHOLOGY_AVAILABLE else False
    return stem in stems


def status() -> dict[str, bool]:
    return {"morphology": MORPHOLOGY_AVAILABLE, "deasciifier": DEASCIIFIER_AVAILABLE}
