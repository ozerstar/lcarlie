"""A clean, small intent/capability boundary for informal Turkish chat input.

NOT a giant hardcoded phrase list: a handful of capabilities, each with a
short list of Turkish/English trigger lemmas. Matching is substring-based on
a normalized form of the message, so ordinary Turkish suffixes attached to a
lemma still match ("incele" matches "inceler", "inceledi", "incelesene")
without listing every inflected form. Entity extraction (e.g. "vireon") is
NOT duplicated here -- jarvis.context.ContextCompiler already resolves it
from the raw text via the same substring approach, so "vireonu incele",
"vireona bak" and "vireon tarafında ne oluyor" all still reach it unchanged.

This module decides WHICH capability a message needs; jarvis.shadow /
jarvis.operator still do all the actual work. Designed so a future
Local Intelligence / Frontier Intelligence router can replace or extend this
table without touching the web layer or the wire contract in app.py.
"""
from __future__ import annotations

from dataclasses import dataclass

# Locale-free case folding for matching (not display): every Turkish letter,
# dotted or dotless, upper or lower, folds to one lowercase form. This is
# deliberately looser than correct Turkish casing rules -- for FUZZY MATCHING
# "İncele" and "ıncele" and "Incele" should all hit the same lemma.
_TR_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ç": "ç", "Ğ": "ğ", "Ö": "ö", "Ş": "ş", "Ü": "ü",
})


def normalize(text: str) -> str:
    """Lowercase, Turkish-letter-safe, informal-speech tolerant."""
    folded = (text or "").translate(_TR_FOLD).lower()
    # "bi" is extremely common informal Turkish for "bir" ("buna bi bak").
    folded = folded.replace(" bi ", " bir ")
    return " ".join(folded.split())


@dataclass(frozen=True)
class Capability:
    capability_id: str
    lemmas: tuple[str, ...]


# Order matters: first match wins. WHY and PROPOSALS are checked before the
# generic INSPECT/STATUS bucket because they need a numeric id / are more
# specific.
CAPABILITY_TABLE: tuple[Capability, ...] = (
    Capability("WHY", ("neden oluştu", "neden olustu", "why was", "why created", "neden böyle")),
    Capability("PROPOSALS", ("bekleyen öneri", "bekleyen oneri", "pending proposal",
                             "onay bekleyen", "proposal list", "bekleyen iş", "bekleyen is")),
    Capability("JUDGEMENT", ("ne öneriyorsun", "ne oneriyorsun", "ne yapmalıyım", "ne yapmaliyim",
                             "ne yapabiliriz", "tavsiyen", "recommend", "what should i do",
                             "yorumla", "fikrin ne")),
    # 🔴 INSPECT'TEN ÖNCE. "katalog hazırla" içindeki "hazır", "afişe bak"
    # içindeki "bak" INSPECT'e düşürürdü; ilk eşleşen kazanıyor.
    # Lemmalar AYIRT EDİCİ: tek başına "post" yok, çünkü "kartpostal"
    # içinde de geçiyor (bu tuzağa bugün düşüldü).
    Capability("TASARIM", ("tasarım", "tasarim", "katalog", "kataloğ",
                           "afiş", "afis", "poster", "broşür", "brosur",
                           "raf etiketi", "raf stopper", "wobbler",
                           "fiyat kartı", "fiyat karti", "roll-up", "rollup",
                           "flyer", "instagram gönderi", "instagram gonderi",
                           "story", "reels kapak", "şablon", "sablon",
                           "kartvizit", "davetiye", "stand", "banner",
                           "görsel hazırla", "gorsel hazirla")),
    Capability("INSPECT_OR_STATUS", ("incele", "bak", "kontrol et", "göz at", "goz at",
                                     "durum", "ne oluyor", "status", "sağlık", "saglik",
                                     "sistem", "system", "şirket", "sirket", "company",
                                     "gündem", "gundem", "task", "proposal", "yetenek",
                                     "capability", "vireon", "sorun var mı", "sorun var mi",
                                     "satış", "satis", "meta")),
)


def classify(message: str) -> str | None:
    """Returns a capability_id, or None if nothing matches (unclassified)."""
    normalized = normalize(message)
    for capability in CAPABILITY_TABLE:
        # Lemmas are folded the same way as the message so "ı"/"i"/"İ"/"I"
        # variants in the table itself never cause a silent mismatch.
        if any(normalize(lemma) in normalized for lemma in capability.lemmas):
            return capability.capability_id
    return None
