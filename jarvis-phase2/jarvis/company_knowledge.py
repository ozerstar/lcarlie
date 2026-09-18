"""Company knowledge: what Jarvis knows about L'CARLIÉ itself.

Company Memory answers *what the numbers are*. This module answers *who we
are*: the brand, the people, the products, the claim rules, the measurement
traps. That knowledge is not in the database and never will be -- it is
editorial, it changes by decision rather than by transaction, and it is
reviewed by a human before it lands here.

Two deliberate choices:

1. **Nothing is injected wholesale.** `identity()` is tiny and loaded every
   turn; everything else is retrieved by keyword, the same shape the Context
   Compiler already uses for Company Memory. A 40 KB profile in every prompt
   would be both slow on a CPU-only box and a reliable way to drown the actual
   question.

2. **Retrieved text is appended last.** The conversational system prompt is a
   stable prefix, so llama.cpp's prompt cache keeps hitting it; only the
   retrieved tail is re-evaluated.

The `gizlilik` front-matter field is a real boundary, not a label. A file
marked `ic-bilgi` may carry a `## 🔒 İÇ BİLGİ` section quoting the old catalog,
whose sentences are regulatorily unusable. Any caller producing customer-facing
copy passes ``internal_ok=False`` and that section is removed before the text
is ever seen by a model.

What that boundary is *not*: a word filter. Each product file ends its
compliant half with a warning that quotes the forbidden phrasing verbatim --
*"kolajen sentezini destekler" yazılamaz* -- because a rule that names the
exact sentence is the only form that reliably stops a model reproducing it,
and because the claim-rules file is nothing but a list of forbidden terms. So
a banned string legitimately appears in a copy context; what may never appear
is a line taken from the catalog, asserted as fact. The unit is the source
section, not the vocabulary.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CompanyKnowledge", "Document", "KNOWLEDGE_DIR"]

KNOWLEDGE_DIR = Path(
    os.environ.get("JARVIS_KNOWLEDGE_DIR",
                   "/opt/lcarlie/jarvis-phase2/knowledge"))

#: The file loaded on every turn. Kept short on purpose.
IDENTITY_NAME = "00-kimlik"

#: Files that describe the collection rather than the company.
EXCLUDED = {"INDEX"}

#: Heading that opens an internal-only section. Everything from this line to
#: the end of the file is dropped when ``internal_ok`` is False. A file marked
#: ``gizlilik: ic-bilgi`` that has no such heading is internal in its entirety
#: and is withheld completely instead.
_INTERNAL_RE = re.compile(r"^##\s*\U0001F512\s*İÇ BİLGİ", re.MULTILINE)

#: Matching fold. Python gets Turkish wrong in both directions: ``"İ".casefold()``
#: is "i" + COMBINING DOT ABOVE, which matches nothing, and ``"I".lower()`` is
#: "i" where Turkish wants "ı". But a strict Turkish fold is wrong here too --
#: the brand names are written in ASCII, so "Intimblanc" would fold to
#: "ıntımblanc" and miss its own document. So the dotted/dotless distinction is
#: collapsed entirely for matching: I, İ, ı and i all become "i". That is only
#: safe because BOTH sides are folded the same way -- the stored keyword
#: "satış" folds to "satis" exactly as a typed "SATIŞ" does.
_TR_FOLD = str.maketrans({"İ": "i", "I": "i", "ı": "i"})

_WORD_RE = re.compile(r"[0-9a-zçğöşü]+")

#: Two documents of the size these files run to. Measured on the box rather
#: than guessed: ~8000 extra characters of system prompt is ~3500 tokens and
#: costs a couple of seconds of prompt evaluation, against 27-73 s of
#: generation. The budget exists to stop the whole folder being pasted in, not
#: because a second document is expensive.
_MAX_CHARS = 9000
_MAX_DOCS = 2

#: Words that appear in a ``konu`` without identifying it.
_KONU_STOP = frozenset(
    {"ve", "ile", "için", "ürün", "ürünler", "bilgi", "bilgisi", "listesi",
     "kurallar", "gerçeği", "gerçekler"})


def fold(text: str) -> str:
    """Lowercase for matching, with I/İ/ı/i collapsed. See ``_TR_FOLD``."""
    return text.translate(_TR_FOLD).lower().translate(_TR_FOLD)


@dataclass(frozen=True)
class Document:
    name: str
    konu: str
    keywords: tuple[str, ...]
    internal: bool
    body: str

    def text(self, internal_ok: bool = True) -> str:
        """The body, with the internal part removed when not allowed.

        Returns "" for a document that is internal end to end, so a caller
        writing customer-facing copy simply does not receive it.
        """
        if internal_ok:
            return self.body
        match = _INTERNAL_RE.search(self.body)
        if match is not None:
            return self.body[:match.start()].rstrip()
        return "" if self.internal else self.body


def _parse(path: Path) -> Document | None:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return None
    end = raw.find("\n---", 3)
    if end == -1:
        return None
    header, body = raw[3:end], raw[end + 4:].lstrip("\n")

    konu = ""
    gizlilik = "serbest"
    keywords: list[str] = []
    key = None
    buf = ""
    for line in header.splitlines():
        stripped = line.strip()
        if key == "anahtar":
            buf += " " + stripped
            if "]" in stripped:
                key = None
            continue
        if stripped.startswith("konu:"):
            konu = stripped[5:].strip()
        elif stripped.startswith("gizlilik:"):
            gizlilik = stripped[9:].strip()
        elif stripped.startswith("anahtar:"):
            buf = stripped[8:].strip()
            key = None if "]" in buf or not buf.startswith("[") else "anahtar"
    for item in buf.strip().strip("[]").split(","):
        item = fold(item.strip())
        if item:
            keywords.append(item)

    return Document(name=path.stem, konu=konu, keywords=tuple(keywords),
                    internal=gizlilik.startswith("ic"), body=body.rstrip())


class CompanyKnowledge:
    """A directory of small markdown files, retrieved by keyword.

    Loading is lazy and cached; the files are read-only to the service (the
    unit runs under ProtectSystem=strict with only the state directory
    writable), so a reload only happens when the process restarts.
    """

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory else KNOWLEDGE_DIR
        self._docs: dict[str, Document] | None = None

    # -- loading ---------------------------------------------------------
    @property
    def documents(self) -> dict[str, Document]:
        if self._docs is None:
            docs: dict[str, Document] = {}
            if self.directory.is_dir():
                for path in sorted(self.directory.glob("*.md")):
                    doc = _parse(path)
                    if doc is not None:
                        docs[doc.name] = doc
            self._docs = docs
        return self._docs

    @property
    def available(self) -> bool:
        return bool(self.documents)

    def identity(self) -> str:
        """The always-loaded identity block, or "" when not installed."""
        doc = self.documents.get(IDENTITY_NAME)
        return doc.body if doc else ""

    # -- retrieval -------------------------------------------------------
    def score(self, query: str) -> list[tuple[int, Document]]:
        """Rank documents against a query.

        Three signals, in increasing weight: a single-word keyword, a
        multi-word keyword (more specific, so worth more), and a hit on the
        document's own subject. The subject bonus is what keeps "Intimblanc
        nedir?" on the Intimblanc file instead of on the 36-product list,
        which mentions the word in passing.
        """
        folded = fold(query)
        tokens = set(_WORD_RE.findall(folded))
        scored: list[tuple[int, Document]] = []
        for doc in self.documents.values():
            if doc.name == IDENTITY_NAME or doc.name in EXCLUDED:
                continue
            hits = 0
            for keyword in doc.keywords:
                if " " in keyword:
                    if keyword in folded:
                        hits += 2
                elif keyword in tokens:
                    hits += 1
            subject = set(_WORD_RE.findall(fold(doc.konu))) - _KONU_STOP
            if subject & tokens:
                hits += 2
            if hits:
                scored.append((hits, doc))
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return scored

    def retrieve(self, query: str, *, limit: int = _MAX_DOCS,
                 max_chars: int = _MAX_CHARS,
                 internal_ok: bool = True) -> list[Document]:
        """The documents worth putting in front of the model for this query.

        Returns [] when nothing matches -- a miss is a miss, never the whole
        folder as a consolation prize.
        """
        chosen: list[Document] = []
        budget = max_chars
        for _hits, doc in self.score(query):
            if len(chosen) >= limit:
                break
            size = len(doc.text(internal_ok))
            if not size or size > budget:
                continue
            chosen.append(doc)
            budget -= size
        return chosen

    def context(self, query: str, *, internal_ok: bool = True,
                limit: int = _MAX_DOCS, max_chars: int = _MAX_CHARS) -> str:
        """Retrieved knowledge as a prompt block, or "" when nothing matched."""
        docs = self.retrieve(query, limit=limit, max_chars=max_chars,
                             internal_ok=internal_ok)
        if not docs:
            return ""
        parts = ["ŞİRKET BİLGİSİ (doğrulanmış, bu bilgiye güven):"]
        for doc in docs:
            parts.append(doc.text(internal_ok))
        return "\n\n".join(parts)

    def status(self) -> dict[str, object]:
        return {
            "directory": str(self.directory),
            "available": self.available,
            "documents": len(self.documents),
            "identity_chars": len(self.identity()),
            "internal": sorted(d.name for d in self.documents.values()
                               if d.internal),
        }


_SHARED: CompanyKnowledge | None = None


def shared() -> CompanyKnowledge:
    """The process-wide instance, so the files are parsed once."""
    global _SHARED
    if _SHARED is None:
        _SHARED = CompanyKnowledge()
    return _SHARED
