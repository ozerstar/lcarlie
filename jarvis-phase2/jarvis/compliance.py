"""Kademe 1 mevzuat taraması — L'CARLIÉ metin denetimi.

Kural kaynağı: `03_MEVZUAT_KURALLARI.md` (06.09.2026, sahip onaylı). Buradaki
hiçbir madde veya dayanak bu dosyada üretilmedi; hepsi o belgeden alındı ve
`LEGAL_BASIS` içinde kaynağıyla taşınıyor.

NE YAPAR
Üç kademeli onayın (belgenin §9) yalnız BİRİNCİ kademesidir: mekanik tarama.
Görsel yargı (kademe 2) ve konumlandırma/rakam onayı (kademe 3) insana aittir.

NE YAPMAZ
Bir metni "uygun" ilan etmez. Çıktı yalnız iki etiket üretir:
    BLOCKED       — belgedeki açık yasak, yayınlanmaz
    VERIFY        — belge/delil olmadan kullanılamaz, doğrulama sorusu doğurur
Belgenin (A) "dosyayla destekli" ve (D) "duyusal ifade" etiketleri BURADA
ÜRETİLMEZ: ikisi de ürün bilgilendirme dosyasına ve insan yargısına bakar.
Tarayıcının sessiz kalması onay değildir — `clean=True` yalnız "kademe 1'de
yakalanan bulgu yok" demektir.

NEDEN KELİME LİSTESİ DEĞİL
Belge §1: mevzuat fiili değil, fiil ile NESNENİN birleşimini değerlendiriyor.
"Güvenli fiiller" listesi 06.09.2026'da bu yüzden silindi — "destekler" fiili
temiz görünür ama "dolaşımı destekler" ihlalin ta kendisidir. Bu yüzden tarama
yasak NESNE üzerinden yürür: "ısınma sayesinde bölgeye daha çok kan gider"
cümlesinde yasak bir fiil yoktur, yasak bir nesne (kan) vardır ve yakalanır.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

RULES_SOURCE = "03_MEVZUAT_KURALLARI.md (06.09.2026)"

BLOCKED = "BLOCKED"
VERIFY = "VERIFY"

# Belge §3 — doğrulanmış dayanaklar. Kısaltma yok, olduğu gibi taşınır.
LEGAL_BASIS = {
    "ispat": "Ticari Reklam Yönetmeliği m.8 — ispat külfeti reklamverende",
    "kozmetik_kapsam": ("Kozmetik Ürünler Yönetmeliği — iddia kapsamına metinler, "
                        "ADLAR, ticari markalar, resimler ve figüratif işaretler dahil"),
    "saglik_beyani": "Sağlık Beyanı Denetimi Yönetmeliği m.9/(3)",
    "ceza": "1262 sayılı Kanun m.19 — 1–5 yıl hapis",
    "saglik_calisani": ("Ticari Reklam Yönetmeliği m.16/(3) — sağlık çalışanı algısı; "
                        "beyaz önlük, klinik ortam, laboratuvar sahnesi dahil"),
    "sinir_urun": ("TİTCK Sınır Ürünler Kılavuzu m.9/(4)/(c) — vazodilatasyonla etki "
                   "eden ürünler kozmetik dışı"),
    "ilac_karinesi": ("TİTCK Sınır Ürünler Kılavuzu m.9/(4)/(c)-1 — ilaç etken maddesi "
                      "olarak kullanılan bileşenleri öne çıkaran ürünler kozmetik sayılmaz"),
}

# Belge §1 — izinli nesneler. Bilgi amaçlı taşınır; tarama yasak nesne üzerinden
# yürür, çünkü izinli listede olmayan her nesneyi makine güvenle sayamaz.
PERMITTED_OBJECTS = ("görünüm", "his", "doku", "nem", "konfor", "koku")

# Belge §1 — yasak nesneler, kategori ve dayanağıyla.
FORBIDDEN_OBJECTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("fizyolojik fonksiyon",
     ("dolaşım", "dolasim", "kan akışı", "kan akisi", "kan gider", "kan gelir",
      "kanlanma", "mikrosirkülasyon", "mikrosirkulasyon", "vazodilat",
      "damar genişle", "damar genisle", "kas", "sinir", "hormon", "metabolizma",
      "bağışıklık", "bagisiklik"),
     "saglik_beyani"),
    ("hastalık veya durum adı",
     ("egzama", "sedef", "akne", "sivilce", "mantar", "iltihap", "dermatit",
      "hemoroid", "varis", "kanser", "migren", "horlama", "selülit", "sellulit",
      "kızarıklık", "kizariklik", "ödem", "odem", "ağrı", "agri", "yara izi",
      "çatlak", "catlak", "leke"),
     "saglik_beyani"),
    ("yapısal değişim",
     ("kolajen", "kollajen", "elastin", "elastikiyet", "doku onarım", "doku onarim",
      "hücre yenile", "hucre yenile", "hücre yenileyici", "yeniden yapılandır",
      "yeniden yapilandir", "gözenek sıkılaş", "gozenek sikilas"),
     "kozmetik_kapsam"),
)

# Belge §2 — genel yasak ifadeler.
FORBIDDEN_PHRASES: tuple[tuple[str, str], ...] = tuple(
    (phrase, "saglik_beyani") for phrase in (
        "tedavi eder", "tedavi edici", "iyileştirir", "iyilestirir", "geçirir",
        "gecirir", "yok eder", "kesin sonuç", "kesin sonuc", "mucize",
        "kalıcı çözüm", "kalici cozum", "şifa", "sifa", "ağrıyı keser",
        "agriyi keser", "önler", "onler",
    )
)

# Belge §2 — 06.09.2026 eklenenleri, her biri kendi gerekçesiyle.
SUPERIORITY = ("en iyi", "en etkili", "lider", "türkiye'nin ilk", "turkiye'nin ilk",
               "bir numara", "rakipsiz", "benzersiz etki")
ICERMEZ = ("içermez", "icermez", "içermeyen", "icermeyen", "arındırılmış",
           "arindirilmis", "kimyasallardan arındır", "kimyasallardan arindir")
DOSSIER_REQUIRED = ("%100 doğal", "%100 dogal", "100% doğal", "klinik etkinliği kanıtlanmış",
                    "klinik etkinligi kanitlanmis", "dermatolojik olarak test edilmiş",
                    "dermatolojik olarak test edilmis", "klinik olarak kanıtlanmış",
                    "klinik olarak kanitlanmis")
AUTHORITY = ("doktor formülü", "doktor formulu", "doktor tavsiyesi", "eczacı önerisi",
             "eczaci onerisi", "beyaz önlük", "beyaz onluk", "klinik ortam",
             "laboratuvar sahnesi")
BEFORE_AFTER = ("öncesi/sonrası", "oncesi/sonrasi", "öncesi sonrası", "oncesi sonrasi",
                "önce sonra", "once sonra", "before after", "before/after",
                "kullanmadan önce ve sonra", "kullanmadan once ve sonra")
QUALITY_MARKS = ("gmp", "iso 22716")

# Belge §11 — ürüne özel tuzaklar.
PRODUCT_TRAPS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("VIREON/FEMISIA bileşen tuzağı",
     ("epimedium", "tribulus", "damiana", "maca", "arginine", "arjinin"),
     "ilac_karinesi"),
)

# Belge §5 — güneş koruyucuda zorunlu ibare seti.
SUNSCREEN_MARKERS = ("spf", "güneş koruyucu", "gunes koruyucu", "güneşten koruma",
                     "gunesten koruma")
SUNSCREEN_REQUIRED = (
    ("yeterli miktarda uygulanmaması korumayı önemli ölçüde düşürür",
     ("yeterli miktarda uygulanma",)),
    ("aşırı güneş maruziyeti sağlık tehdididir",
     ("aşırı güneş maruziyeti", "asiri gunes maruziyeti")),
    ("bebek ve küçük çocuklar doğrudan güneşe maruz bırakılmamalıdır",
     ("bebek ve küçük çocuk", "bebek ve kucuk cocuk")),
    ("hiçbir ürün %100 koruma sağlamaz",
     ("hiçbir ürün %100 koruma", "hicbir urun %100 koruma", "%100 koruma sağlamaz")),
)

# Belge §6 — hastalık/semptom etiketleri ve hashtag tavanı.
HASHTAG_CAP = 5

# Birim ek alır: "14 günde", "2 haftada", "96 saatte". Sondaki \b bunları kaçırıyordu.
# İçerik beyanı (INCI) ile pazarlama cümlesini ayırmak için. Kılavuzun 3.
# kuralı: "İçerik beyanı pazarlama değildir, silinmez -- Epimedium INCI'de
# kalır, cümlede anılmaz." Bu ayrımı yapmayan bir tarama, ürünün yasal
# zorunluluğu olan içerik listesini ihlal sayar ve 39 üründe onlarca yanlış
# alarm üretir -- ölçüldü.
_INGREDIENT_HEADERS = ("içindekiler", "icindekiler", "ingredients", "inci",
                       "bileşenler", "bilesenler", "içerik", "icerik")
# "L-Arginin | L-Arginine | 5." gibi formül tablosu satırı: boru işaretiyle
# ayrılmış ve sayı ile biten.
_FORMULA_ROW = re.compile(r"\|.*\|\s*\d+[.,]?\d*\s*%?\s*$")

_DURATION = re.compile(r"\b\d+\s*(gün|gun|hafta|saat|ay)\w*", re.IGNORECASE)
_PERCENT = re.compile(r"[%‰]\s?\d+|\b\d+\s?%")
_HASHTAG = re.compile(r"#\w+", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def fold(text: str) -> str:
    """Türkçe'ye güvenli küçültme.

    Python'un casefold'u 'İ' için birleşik noktalı 'i̇' üretir ve eşleşme sessizce
    kaçar; 'I' de 'ı' yerine 'i' olur. İkisi de düzeltilir, sonra aksan kaldırılmış
    bir kopya da aranabilsin diye normalize edilir.
    """
    swapped = text.replace("İ", "i").replace("I", "ı")
    return swapped.casefold()


def deaccent(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("ı", "i").replace("ğ", "g").replace("ş", "s")


_SOFTENING = {"k": "ğ", "p": "b", "t": "d", "ç": "c"}


def _soften(term: str) -> str | None:
    """Türkçe ünsüz yumuşaması: ek alınca son sessiz değişir.

    "kızarıklık" listede olsa bile metinde "kızarıklığı" geçer ve düz alt dize
    araması kaçırır. Bu, taramanın sessizce yanlış negatif üretmesi demektir —
    belgenin uyardığı "sahte güven" durumunun ta kendisi.
    """
    if not term or term[-1] not in _SOFTENING:
        return None
    return term[:-1] + _SOFTENING[term[-1]]


def _contains(haystack_folded: str, haystack_flat: str, needle: str) -> bool:
    for candidate in (needle, _soften(needle)):
        if not candidate:
            continue
        folded = fold(candidate)
        if folded in haystack_folded or deaccent(folded) in haystack_flat:
            return True
    return False


@dataclass(frozen=True)
class Finding:
    label: str            # BLOCKED | VERIFY
    rule: str             # hangi kural
    matched: str          # metinde bulunan ifade
    sentence: str         # bulunduğu cümle
    basis: str            # dayanak metni
    remedy: str           # ne yapılmalı

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Review:
    findings: tuple[Finding, ...] = ()
    hashtags: tuple[str, ...] = ()
    checked_at: str = ""
    rules_source: str = RULES_SOURCE

    @property
    def blocked(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.label == BLOCKED)

    @property
    def verify(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.label == VERIFY)

    @property
    def clean(self) -> bool:
        """Kademe 1'de bulgu yok. ONAY DEĞİLDİR — §9 kademe 2 ve 3 insana ait."""
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": [f.to_dict() for f in self.blocked],
            "verify": [f.to_dict() for f in self.verify],
            "hashtags": list(self.hashtags),
            "clean_tier1": self.clean,
            "approval_required": True,
            "rules_source": self.rules_source,
            "checked_at": self.checked_at,
            "note": ("Kademe 1 mekanik taramadır. Bulgu çıkmaması yayın onayı değildir; "
                     "görsel yargı ve konumlandırma onayı insana aittir."),
        }


def sentences(text: str) -> list[str]:
    return [" ".join(part.split()) for part in _SENTENCE.findall(text) if part.strip()]


def _is_ingredient_declaration(sentence: str, folded: str) -> bool:
    """Bu cümle bir içerik beyanı mı, yoksa pazarlama cümlesi mi?

    Yalnız bileşen ADINA dayanan kurallar bu satırlarda susar. Nesne kuralı
    susmaz: "Isıtıcı, dolaşımı artırıcı" bir tablo satırında da olsa işlev
    iddiasıdır ve yakalanmalıdır.
    """
    # İki biçime de bakılır: fold() Türkçe için doğru davranıp büyük "I"yı "ı"
    # yapar, ama bu İngilizce "Ingredients" kelimesini "ıngredients"e çevirip
    # eşleşmeyi kaçırır. Türkçe doğru olan kural, İngilizce başlıkta yanlış
    # negatif üretiyor -- ikisi birlikte aranır.
    ascii_lower = sentence.lower()
    if any(header in folded or header in ascii_lower
           for header in _INGREDIENT_HEADERS):
        return True
    return bool(_FORMULA_ROW.search(sentence.strip()))


def _scan_sentence(sentence: str) -> list[Finding]:
    folded = fold(sentence)
    flat = deaccent(folded)
    ingredient_line = _is_ingredient_declaration(sentence, folded)
    found: list[Finding] = []

    def add(label, rule, matched, basis_key, remedy):
        found.append(Finding(label=label, rule=rule, matched=matched, sentence=sentence,
                             basis=LEGAL_BASIS[basis_key], remedy=remedy))

    # Aynı kuralın aksanlı ve aksansız yazımı tek bulgudur; ilkinde durulur.
    for phrase, basis_key in FORBIDDEN_PHRASES:
        if _contains(folded, flat, phrase):
            add(BLOCKED, "yasak ifade", phrase, basis_key,
                "İfade kaldırılır. Yumuşatma veya eşanlamlı ile saklama yapılmaz.")
            break  # tek bulgu

    for category, terms, basis_key in FORBIDDEN_OBJECTS:
        for term in terms:
            if _contains(folded, flat, term):
                add(BLOCKED, f"yasak nesne — {category}", term, basis_key,
                    "Cümlenin nesnesi izinli listede değil (görünüm/his/doku/nem/konfor/koku). "
                    "Nesne değiştirilir; fiili değiştirmek yetmez.")
                break

    for label, terms, basis_key in PRODUCT_TRAPS:
        if ingredient_line:
            break  # INCI'de kalması zorunlu; ihlal cümlede anılmasıdır
        for term in terms:
            if _contains(folded, flat, term):
                add(BLOCKED, label, term, basis_key,
                    "Bileşen INCI listesinde kalır, cümlede anılmaz.")
                break

    for phrase in SUPERIORITY:
        if _contains(folded, flat, phrase):
            add(BLOCKED, "üstünlük iddiası", phrase, "ispat",
                "Üstünlük iddiası kaldırılır; ispat külfeti reklamverendedir.")
            break

    for phrase in ICERMEZ:
        if _contains(folded, flat, phrase):
            add(BLOCKED, "'içermez' kalıbı", phrase, "ispat",
                "Yasal kullanılabilen bileşenin yokluğu üstünlük olarak sunulmaz. "
                "Belge de kurtarmaz — sorun ispat değil adillik kriteridir.")
            break

    for phrase in BEFORE_AFTER:
        if _contains(folded, flat, phrase):
            add(VERIFY, "öncesi/sonrası", phrase, "ispat",
                "Otomatik güvenli sayılmaz: aynı ışık/açı/kamera/ifade, gerçek süre, "
                "retouch yok, tipik sonuç izlenimi ve açıklamalar birlikte değerlendirilir.")
            break

    for phrase in AUTHORITY:
        if _contains(folded, flat, phrase):
            add(VERIFY, "sağlık çalışanı algısı / otorite transferi", phrase,
                "saglik_calisani",
                "Beyaz önlük, klinik ortam ve laboratuvar sahnesi dahil denetlenir.")
            break

    for phrase in DOSSIER_REQUIRED:
        if _contains(folded, flat, phrase):
            add(VERIFY, "belge gerektiren ifade", phrase, "ispat",
                "Ürün bilgilendirme dosyasında dayanağı yoksa kullanılamaz.")
            break

    for mark in QUALITY_MARKS:
        if _contains(folded, flat, mark):
            add(VERIFY, "GMP/ISO kullanımı", mark, "ispat",
                "Yasal gerekliliktir, ürüne özgü fayda değildir; üstünlük kurgusunda kullanılmaz.")

    duration = _DURATION.search(sentence)
    if duration:
        add(VERIFY, "süre iddiası", duration.group(0), "ispat",
            "Klinik veri olmadan süre sonucu verilemez.")

    percent = _PERCENT.search(sentence)
    if percent:
        add(VERIFY, "oran/yüzde iddiası", percent.group(0), "ispat",
            "Rakamın dayandığı belge onay kaydına yazılır.")

    return found


def _sunscreen_findings(text: str) -> list[Finding]:
    folded = fold(text)
    flat = deaccent(folded)
    if not any(_contains(folded, flat, marker) for marker in SUNSCREEN_MARKERS):
        return []
    missing = []
    for required, probes in SUNSCREEN_REQUIRED:
        if not any(_contains(folded, flat, probe) for probe in probes):
            missing.append(Finding(
                label=BLOCKED, rule="güneş koruyucu zorunlu ibare eksik",
                matched=required, sentence="", basis=LEGAL_BASIS["kozmetik_kapsam"],
                remedy="Zorunlu ibare setinin tamamı içerikte geçmelidir."))
    return missing


def _hashtag_findings(text: str) -> tuple[list[Finding], tuple[str, ...]]:
    tags = tuple(_HASHTAG.findall(text))
    found: list[Finding] = []
    if len(tags) > HASHTAG_CAP:
        found.append(Finding(
            label=VERIFY, rule="hashtag tavanı", matched=f"{len(tags)} etiket",
            sentence="", basis=LEGAL_BASIS["kozmetik_kapsam"],
            remedy=f"Gönderi başına en fazla {HASHTAG_CAP} etiket."))
    for tag in tags:
        folded, flat = fold(tag), deaccent(fold(tag))
        for category, terms, basis_key in FORBIDDEN_OBJECTS:
            if category != "hastalık veya durum adı":
                continue
            for term in terms:
                if _contains(folded, flat, term):
                    found.append(Finding(
                        label=BLOCKED, rule="hastalık/semptom etiketi", matched=tag,
                        sentence="", basis=LEGAL_BASIS[basis_key],
                        remedy="Hastalık ve semptom etiketleri kullanılmaz."))
                    break
    return found, tags


def review(text: str, checked_at: str = "") -> Review:
    """Bir metni kademe 1 kurallarına göre tarar."""
    findings: list[Finding] = []
    for sentence in sentences(text):
        findings.extend(_scan_sentence(sentence))
    findings.extend(_sunscreen_findings(text))
    hashtag_findings, tags = _hashtag_findings(text)
    findings.extend(hashtag_findings)

    seen: set[tuple[str, str, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.rule, finding.matched, finding.sentence)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)

    order = {BLOCKED: 0, VERIFY: 1}
    unique.sort(key=lambda f: (order[f.label], f.rule))
    return Review(findings=tuple(unique), hashtags=tags, checked_at=checked_at)


def approval_record(content_code: str, product: str, channel: str,
                    result: Review) -> dict[str, Any]:
    """Belge §9'un zorunlu onay kaydı satırı.

    "Bu dosya hem üretim takibi hem ispat külfeti dosyasıdır" — tarama sonucu
    tek başına kayıt yerine geçmez, kaydın makine tarafından doldurulabilen
    kısmını üretir.
    """
    return {
        "tarih": result.checked_at,
        "icerik_kodu": content_code,
        "urun": product,
        "format": channel,
        "kademe1_bulgu": len(result.findings),
        "bloklu": len(result.blocked),
        "dogrulama_bekleyen": len(result.verify),
        "iddianin_dayandigi_belge": "INSAN DOLDURUR",
        "onaylayan": "INSAN DOLDURUR",
        "yayin_durumu": "BLOCKED" if result.blocked else "PENDING_HUMAN_REVIEW",
    }
