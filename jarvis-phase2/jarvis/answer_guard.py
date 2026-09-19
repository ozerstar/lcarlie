"""Model cevabını yayımlanmadan önce denetler: uydurma ürün ve ton.

NEDEN İSTEM YETMEDİ -- ÖLÇÜLDÜ
Sohbet istemi açıkça şunları söylüyordu: "ürün bilgisi UYDURMA", "emoji
kullanma", "kullanıcıya 'siz' diye hitap et". Gerçek modelin gerçek cevabı:

  "Teşekkür ederim, iyiyim! Seninle konuşmak güzel bir fırsat. ... 😊"
  "...VIREON FOR MEN ve FEMISIA FOR WOMEN gibi ürünler öne çıkmıştır."

Katalogda 23 ürün var ve FEMISIA onlardan biri DEĞİL. Model bir ürün
uydurup şirketin ürünüymüş gibi sundu. 4B'lik bir modele uzun bir kural
listesi vermek, kuralların uygulanacağı anlamına gelmiyor.

Bu yüzden denetim istemden ÇIKARILIP koda alınır. İstem hâlâ yerinde durur
(iyi cevabı yönlendirir), ama garanti buradadır.

NE YAPMAZ
Cevabı yeniden yazmaz ve model çağırmaz. Yalnız sayar, işaretler ve
gerektiğinde uydurma cümleyi düşürür. Sıfır token.
"""
from __future__ import annotations

import re
import unicodedata

# Buyuk harfle yazilmis marka gorunumlu diziler: "FEMISIA FOR WOMEN",
# "VIREON FOR MEN". Model urun adlarini bu bicimde yaziyor (olculdu).
_CAPS_RUN = re.compile(r"\b[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9+]{3,}(?:\s+[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9+]{1,})*")

# Marka olmayan, mesru buyuk harfli terimler. Kisa ve kapali bir kume:
# kurum adlari, olcut kisaltmalari, teknik terimler.
KNOWN_CAPS = frozenset({
    "TITCK", "TİTCK", "KDV", "ROAS", "CTR", "CPC", "CPM", "DM", "GA4", "PDF",
    "SEO", "SEM", "API", "URL", "SMS", "KVKK", "IYS", "İYS", "INCI", "SPF",
    "WHATSAPP", "INSTAGRAM", "META", "WIX", "GOOGLE", "FACEBOOK", "TL",
    "AI", "CRM", "KPI", "UTM", "OK", "NOT", "VE", "VEYA", "ANCAK",
})

_EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF"
    "\U0001F000-\U0001F0FF" "\U0000FE0F" "\U00002190-\U000021FF" "]+")

# Samimi hitap ve abarti. Cevap resmi olmali (sahip talimati, 20.09.2026).
_INFORMAL = (
    (re.compile(r"\bseninle\b", re.IGNORECASE), "sizinle"),
    (re.compile(r"\bsenin\b", re.IGNORECASE), "sizin"),
    (re.compile(r"\bsana\b", re.IGNORECASE), "size"),
    (re.compile(r"\bsende\b", re.IGNORECASE), "sizde"),
    (re.compile(r"\bsen\b", re.IGNORECASE), "siz"),
    (re.compile(r"\bharika\b", re.IGNORECASE), "iyi"),
    (re.compile(r"\bsüper\b", re.IGNORECASE), "iyi"),
    (re.compile(r"\bmuhteşem\b", re.IGNORECASE), "iyi"),
)

# Bos acilis kaliplari: bilgi tasimaz, yeri doldurur.
_OPENERS = re.compile(
    r"^\s*(tabii ki|tabi ki|elbette|memnuniyetle|kesinlikle|şüphesiz)[,:]?\s*",
    re.IGNORECASE)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _fold(text: str) -> str:
    lowered = text.replace("İ", "i").replace("I", "ı").casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).replace("ı", "i")


def unknown_products(text: str, known: tuple[str, ...]) -> list[str]:
    """Cevapta geçen ama katalogda olmayan ürün görünümlü adlar.

    Katalog BOŞSA hiçbir şey bildirilmez: ürün listesi okunamadığında her adı
    "uydurma" saymak, veri yokluğunu hataya çevirmek olurdu.
    """
    if not known:
        return []
    folded_known = {_fold(name) for name in known}
    found: list[str] = []
    for match in _CAPS_RUN.finditer(text or ""):
        term = match.group(0).strip()
        if term.upper() in KNOWN_CAPS or _fold(term) in folded_known:
            continue
        # Katalog adinin bir parcasi mi ("VIREON" <- "VIREON FOR MEN")
        if any(_fold(term) in name or name in _fold(term) for name in folded_known):
            continue
        if term not in found:
            found.append(term)
    return found


def drop_fabricated(text: str, invented: list[str]) -> tuple[str, int]:
    """Uydurma ad geçen cümleleri düşürür.

    Cumle icinden kelime silmek anlamsiz cumle uretir; dogru birim cumledir.
    Geriye cumle kalmazsa metin OLDUGU GIBI birakilir ve cagiran taraf
    uyariyi gosterir -- bos cevap dondurmek, yanlis cevaptan da kotudur
    cunku kullanici neyin yanlis oldugunu goremez.
    """
    if not invented or not text:
        return text, 0
    parts = _SENTENCE_SPLIT.split(text)
    kept = [s for s in parts if not any(term in s for term in invented)]
    if not kept:
        return text, 0
    return " ".join(kept).strip(), len(parts) - len(kept)


def formalize(text: str) -> str:
    """Emoji, ünlem ve samimi hitabı temizler. Model çağrısı yok."""
    if not text:
        return text
    out = _EMOJI.sub("", text)
    out = _OPENERS.sub("", out)
    for pattern, replacement in _INFORMAL:
        out = pattern.sub(replacement, out)
    # Unlem bilgi tasimaz; noktaya cevrilir. Soru isareti korunur.
    out = re.sub(r"!+", ".", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def guard(text: str, known_products: tuple[str, ...] = ()) -> dict[str, object]:
    """Cevabı denetler. Dönen sözlük neyin değiştiğini açıkça söyler."""
    invented = unknown_products(text, known_products)
    cleaned, dropped = drop_fabricated(text, invented)
    final = formalize(cleaned)
    return {
        "text": final,
        "invented_products": invented,
        "sentences_dropped": dropped,
        "changed": final != (text or "").strip(),
        "model_calls": 0,
    }
