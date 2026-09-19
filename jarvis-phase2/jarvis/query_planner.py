"""Araştırma isteğini gerçek arama sorgularına çevirir.

NEDEN VAR — ÖLÇÜLDÜ, TAHMİN EDİLMEDİ
Araştırma verimi sıfıra yakındı (12 sonuç → 8 sayfa → 1 kaynak → 0).
Önce eşikler suçlanmıştı; ölçüm başka şey gösterdi. Gerçek istek üzerinde
iki üretici de kötü sorgu veriyordu:

  deterministik: "dermokozmetik birbirinden pazar raporu son gelişmeler"
                 → "birbirinden" bir talimat kelimesi, konu sanılmış.
  model        : "Türkiye'de premium dermokozmetik pazarındaki son
                  gelişmeleri ara"
                 "Bulguların kaynakları ile birlikte bağımsız sunulması"
                 → bunlar arama sorgusu değil, GÖREV CÜMLESİ. Sonuncuda
                   konu kelimesi hiç yok.

Bir arama motoruna görev cümlesi verilince boş dönmesi normaldir. Sorun
eşikte değil, sorgudaydı.

NE DEĞİŞTİ
1) İstem soyut kural yerine ÖRNEK veriyor. 4B'lik bir model kurala değil
   örneğe uyar: "fiil kullanma" demek yetmedi, "şöyle yaz" demek gerekti.
2) Çıktı DOĞRULANIR. decompose_query hiçbir doğrulama yapmıyordu; modelin
   döndürdüğü her string aynen arama sorgusu oluyordu.

GARANTİ
Bu modül araştırmayı DURDURAMAZ. Model yoksa, yavaşsa veya çöp üretirse
deterministik yedeğe düşülür.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .research_sources import _token_set, decompose, research_subject

MAX_TOKENS = 160

# Bir arama sorgusu kısadır. Ölçülen kötü çıktıların hepsi 7+ kelimeydi ve
# hepsi cümleydi; işe yarayan sorgular 2-6 kelime çıktı.
MIN_WORDS = 2
MAX_WORDS = 6
MAX_QUERIES = 4

# Talimat kelimeleri: "ne yapılacağını" söyleyen, "neyin aranacağını"
# söylemeyen sözcükler. Kapalı ve küçük bir küme -- tıbbi iddia listelerinin
# aksine burada bloklist uygun, çünkü kelime haznesi dünyadan değil kendi
# istemimizden geliyor. Aksansız gövde olarak tutulur.
#
# Bunlar hangi ekle gelirse gelsin talimattır: "kaynaklarıyla", "bulguları",
# "bağımsız" bir arama sorgusunda asla aranacak şeyi göstermez.
_INSTRUCTION_STEMS = (
    "bilgi", "kaynak", "bagims", "birbir", "bulgu", "hakkind",
    "yapilan", "dahil", "sekild", "birlikt", "verilme", "sunul",
)

# Bu köklerin İSİM hâli meşru bir arama terimidir: "pazar analizi",
# "ürün incelemesi", "fiyat karşılaştırması", "araştırma raporu". Talimat
# olan yalnız FİİL hâlidir. Ölçüldü: kökü toptan elemek "intim bakım pazar
# analizi" gibi iyi bir sorguyu da eledi. Kelime sınırı (\b) isim ekli
# biçimleri dışarıda bırakır -- "incele" eşleşir, "incelemesi" eşleşmez.
_INSTRUCTION_VERBS = re.compile(
    r"\b(?:analiz|tespit|rapor|kiyas)\s+(?:et|etmek|edil\w*)\b"
    r"|\b(?:incele|arastir|ozetle|topla|dogrula|karsilastir|dondur|getir"
    r"|listele|belirle|degerlendir|sun)\b"
)

_EXAMPLES = (
    "ORNEK 1\n"
    "Istek: Turkiye premium dermokozmetik pazarindaki son gelismeleri ve rakip "
    "markalarin yeni urun lansmanlarini arastir, fiyat kampanyalarini da dahil et.\n"
    "Sorgular:\n"
    "dermokozmetik pazari Turkiye 2026\n"
    "dermokozmetik marka yeni urun lansmani\n"
    "dermokozmetik fiyat kampanyasi eczane\n\n"
    "ORNEK 2\n"
    "Istek: Kozmetik urun etiketlerinde hangi iddialar yasak, mevzuati "
    "kaynaklariyla getir.\n"
    "Sorgular:\n"
    "kozmetik urun iddia yonetmeligi\n"
    "TITCK kozmetik iddia kilavuzu\n"
    "kozmetik etiket yasak ifade\n"
)

SYSTEM = (
    "Sen bir arama sorgusu yazarsin. Gorev cumlesi YAZMAZSIN.\n"
    "Bir arama sorgusu 2-6 kelimedir ve sadece ARANACAK SEYI icerir: "
    "konu adi, yer, yil, kategori.\n"
    "Fiil kullanma: 'ara', 'topla', 'analiz et', 'incele', 'dogrula' yazma.\n"
    "'kaynaklariyla', 'bagimsiz', 'bulgulari' gibi talimat kelimeleri yazma.\n"
    # NOT: burada bir zamanlar "her sorguya belge turu ekle (raporu, analizi,
    # istatistik)" talimati vardi. OLCULDU ve ZARAR VERDI: bilgi kaynagi
    # ortalamasi 2,00'den 1,17'ye dustu -- "analizi"/"raporu" kelimeleri
    # danismanlik ve pazarlama sayfalarini cekiyor. Olcmeden eklenmisti,
    # olculunce kaldirildi.
    "Her satira bir sorgu. En fazla 4 satir. Numara, tire, aciklama yok.\n\n"
    + _EXAMPLES
)

_LINE_CLEAN = re.compile(
    r"^\s*(?:\d+[.)]\s*|[-*•]\s*|[\"'`]+|Sorgu\s*\d*\s*[:.]\s*)",
    re.IGNORECASE)


def _deaccent(text: str) -> str:
    """Aksansız gövde karşılaştırması. Türkçe ı/İ tuzağı burada zararsız:
    karşılaştırılan iki taraf da aynı dönüşümden geçer."""
    text = text.replace("ı", "i").replace("İ", "i")
    stripped = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in stripped if not unicodedata.combining(ch))


def _clean(line: str) -> str:
    text = _LINE_CLEAN.sub("", line).strip().strip("\"'`").strip()
    return " ".join(text.split())


def is_instruction(query: str) -> bool:
    """Sorgu, aranacak şeyi değil yapılacak işi tarif ediyorsa True."""
    flat = _deaccent(query)
    if _INSTRUCTION_VERBS.search(flat):
        return True
    return any(re.search(rf"\b{re.escape(stem)}", flat)
               for stem in _INSTRUCTION_STEMS)


def topic_terms(request: str) -> set[str]:
    """İsteğin konusunu temsil eden terimler; sorgu bunlardan birini taşımalı."""
    terms = {_deaccent(t) for t in research_subject(request, count=6)}
    terms |= {_deaccent(t) for t in _token_set(request) if len(t) > 4}
    return {t for t in terms
            if t and not any(t.startswith(_deaccent(stem))
                             for stem in _INSTRUCTION_STEMS)}


def validate(candidates: list[str], request: str,
             max_queries: int = MAX_QUERIES
             ) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Model çıktısını süzer ve NEDEN elendiğini de döndürür.

    Gerekçe döndürmek şart: elemeler sessiz olsaydı hangi kuralın fazla sert
    olduğunu ölçmek imkânsız olurdu.
    """
    topics = topic_terms(request) or {_deaccent(t) for t in _token_set(request)}
    seen: set[str] = set()
    good: list[str] = []
    rejected: list[dict[str, str]] = []

    for raw in candidates:
        query = _clean(raw)
        if not query:
            continue
        words = query.split()
        if not (MIN_WORDS <= len(words) <= MAX_WORDS):
            rejected.append({"query": query, "reason": f"{len(words)} kelime"})
            continue
        if is_instruction(query):
            rejected.append({"query": query, "reason": "talimat cümlesi"})
            continue
        if not ({_deaccent(t) for t in _token_set(query)} & topics):
            rejected.append({"query": query, "reason": "konudan sapmış"})
            continue
        key = _deaccent(query)
        if key in seen:
            rejected.append({"query": query, "reason": "tekrar"})
            continue
        seen.add(key)
        good.append(query)
        if len(good) >= max_queries:
            break
    return tuple(good), rejected


def plan(request: str, router: Any | None = None,
         max_queries: int = MAX_QUERIES) -> dict[str, Any]:
    """İstek için arama sorguları üretir; hangi yolun kullanıldığını söyler."""
    fallback = decompose(request, max_queries)
    base: dict[str, Any] = {"fallback": list(fallback), "model_calls": 0}

    if router is None:
        return dict(base, queries=fallback, source="deterministic",
                    reason="model yok")

    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user",
                 "content": "Istek: " + request.strip()[:1200] + "\nSorgular:"}]
    try:
        result, tier, attempts = router.generate(messages, MAX_TOKENS)
    except Exception as exc:  # noqa: BLE001 - araştırma model yüzünden durmaz
        return dict(base, queries=fallback, source="deterministic",
                    reason=f"model çağrısı başarısız: {str(exc)[:120]}")

    text = str(result.get("text") or "")
    queries, rejected = validate(text.splitlines(), request, max_queries)
    base.update(model_calls=attempts, tier=tier, rejected=rejected)

    if not queries:
        return dict(base, queries=fallback, source="deterministic",
                    reason="model çıktısı doğrulamayı geçemedi", raw=text[:300])
    return dict(base, queries=queries, source="model")
