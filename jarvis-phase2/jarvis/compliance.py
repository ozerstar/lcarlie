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
from dataclasses import asdict, dataclass
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
# 28.09.2026 denetimi: liste, Kozmetik Kanunu m.3'teki işlevlerin yalnız bir
# kısmını taşıyordu. "Temizlemek", "korumak" ve "iyi durumda tutmak" yoktu; bu
# yüzden diş macununun diş yüzeyini temizlemesi ENGELLENİYORDU (BRIGHT SMILE,
# ölçüldü). Kanunun tanımındaki işlevler eksiksiz taşınır.
PERMITTED_OBJECTS = ("görünüm", "his", "doku", "nem", "konfor", "koku",
                     "temizlik", "koruma", "iyi durumda tutma")

# Belge §1 — yasak nesneler, kategori ve dayanağıyla.
FORBIDDEN_OBJECTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("fizyolojik fonksiyon",
     ("dolaşım", "dolasim", "kan akışı", "kan akisi", "kan gider", "kan gelir",
      "kanlanma", "mikrosirkülasyon", "mikrosirkulasyon", "vazodilat",
      # "sinir" tek basina KULLANILMAZ: deaccent ı->i cevirdigi icin "sınır"
      # (boundary) kelimesi "sinir"e donusuyor ve "iddia sınırı" gibi tamamen
      # mesru bir ifade ihlal sayiliyordu -- ajans testinde olculdu.
      "damar genişle", "damar genisle",
      # "kas" tek basina ARANMAZ: uc harf oldugu icin "kasa", "kasım" ve
      # "kasten" kelimelerine carpiyor. Olculen gercek ihlal cumleleri
      # ("Kas zarı besleyici", "Kas lifleri", "Kas rahatlatıcı") hep bosluk
      # veya ek ile devam ediyor; terim ona gore daraltildi.
      "kas ", "kasları", "kasların", "kas dokusu", "kas zarı", "kas lif",
      "sinir sistemi", "hormon", "metabolizma",
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

# Belge §1 EK — CİLT TİPİ TANIMI İDDİA DEĞİLDİR (27.09.2026, sahip kararı).
#
# “akneye eğilimli cilt” bir hastalık iddiası değil, ürünün hangi cilt
# tipinin KULLANIMINA UYGUN olduğunu söyleyen tanımdır. Motor bunu “durum
# adı” saydığı için dört meşru metni bloke etmişti (ölçüldü 27.09.2026):
#   LUCIDERM tanımlayıcı · LUCIDERM madde · SUNACNEA madde · CALMAROS tanımlayıcı
#
# Çözüm terimi listeden ÇIKARMAK DEĞİL: “akne” tek başına geçtiğinde hala
# bloke edilir. Yalnız aşağıdaki cilt tipi kalıplarının İÇİNDEKİ geçiş
# sayılmaz; cümle taranmadan önce bu kalıplar maskelenir. Böylece
# “Akneye eğilimli ciltlerde akneyi tedavi eder” yine BLOCKED kalır.
SKIN_TYPE_DESCRIPTORS = (
    "akneye eğilimli", "akne eğilimli", "sivilceye eğilimli",
    "kızarıklığa eğilimli", "kızarıklık eğilimli",
    "akneye yatkın", "kızarıklığa yatkın",
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


# Cilt tipi kalıpları iki biçimde de maskelenir: fold() çıktısı ve
# aksansız kopya — arama ikisinde de yapılıyor.
_SKIN_TYPE_RE = re.compile(
    "|".join(re.escape(fold(_p)) for _p in SKIN_TYPE_DESCRIPTORS))
_SKIN_TYPE_FLAT_RE = re.compile(
    "|".join(re.escape(deaccent(fold(_p))) for _p in SKIN_TYPE_DESCRIPTORS))


def mask_skin_type(haystack: str, *, flat: bool = False) -> str:
    """Cilt tipi tanımlarını aynı uzunlukta boşlukla değiştirir.

    Uzunluk korunur ki maskeleme kelime sınırlarını bozmasın. Aynı cümlede
    kalıp dışında geçen terim maskelenmez, yani bloke edilmeye devam eder.
    """
    rx = _SKIN_TYPE_FLAT_RE if flat else _SKIN_TYPE_RE
    return rx.sub(lambda m: " " * len(m.group(0)), haystack)


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


# Bu uzunluga kadar olan terimler alt dize olarak degil, KELIME olarak aranir.
# Sebebi olculdu: "kas" (muscle) alt dize arandiginda "kasa", "kasım" ve
# "kasten" kelimelerini de yakaliyor. Uzun terimlerde bu risk yok ve kelime
# siniri Turkce ekleri ("dolaşımı", "kolajeni") disarida birakirdi.
_SHORT_TERM_CHARS = 5


# 🔴 KISA TERİM / UZUN KELİME ÇAKIŞMASI — ÖLÇÜLDÜ 15.10.2026
# Kısa terimlerde sağ tarafta sınır aranmıyor (Türkçe ek alsın diye, doğru
# karar). Ama "ödem" + "e" = "ödeme": PARA kelimesi hastalık adı sayılıyordu.
# Ölçüldü: "Kapıda ödeme yapabilirsiniz", "Güvenli ödeme", "ödeme linki
# gönderiyorum" — hepsi BLOCKED. Bu kapı WhatsApp gönderimini tutuyor ve
# işletme kapıda ödemeyle satış yapıyor, yani tam kritik yolda.
#
# Modül bu hata sınıfını zaten tanıyor: "sinir" ve "kas" terimleri aynı
# sebeple daraltılmış. Burada terim daraltılmıyor -- "ödem" hâlâ yakalanır --
# yalnız BİLİNEN çakışan kelimeler istisna tutuluyor.
#
# ⚠️ KABUL EDİLEN RİSK: "ödeme neden olur" (ödem'in yönelme hâli) artık
# yakalanmaz. Pazarlama metninde bu kullanım neredeyse yok; "kapıda ödeme"
# ise her satış konuşmasında var. Yanlış alarmın bedeli daha yüksek.
TERIM_ISTISNALARI: dict[str, frozenset[str]] = {
    "ödem": frozenset({
        "ödeme", "ödemeyi", "ödemeye", "ödemede", "ödemeden", "ödemeler",
        "ödemeleri", "ödemeniz", "ödemenizi", "ödemesi", "ödemesini",
        "ödemek", "ödemeli", "ödemem", "ödemen",
    }),
    "odem": frozenset({
        "odeme", "odemeyi", "odemeye", "odemede", "odemeden", "odemeler",
        "odemeleri", "odemeniz", "odemenizi", "odemesi", "odemesini",
        "odemek", "odemeli", "odemem", "odemen",
    }),
}


def _istisna_mi(haystack: str, konum: int, terim: str) -> bool:
    """Eşleşmenin düştüğü TAM KELİME istisna listesinde mi?"""
    istisnalar = TERIM_ISTISNALARI.get(terim)
    if not istisnalar:
        return False
    bas = konum
    while bas > 0 and (haystack[bas - 1].isalnum() or haystack[bas - 1] == "'"):
        bas -= 1
    son = konum
    while son < len(haystack) and (haystack[son].isalnum() or haystack[son] == "'"):
        son += 1
    return haystack[bas:son] in istisnalar


def _contains(haystack_folded: str, haystack_flat: str, needle: str) -> bool:
    for candidate in (needle, _soften(needle)):
        if not candidate:
            continue
        folded = fold(candidate)
        flat = deaccent(folded)
        if len(folded) <= _SHORT_TERM_CHARS and " " not in folded:
            # Ek alabilsin diye sag tarafta sinir aranmaz; sol tarafta aranir
            # ki "kasa" ve "kasım" gibi bagimsiz kelimeler eslesmesin.
            pattern = r"(?<!\w)" + re.escape(folded)
            flat_pattern = r"(?<!\w)" + re.escape(flat)
            for desen, saman, terim in ((pattern, haystack_folded, folded),
                                        (flat_pattern, haystack_flat, flat)):
                for m in re.finditer(desen, saman):
                    # Eslesme bir istisna kelimesinin icine dustuyse sayilmaz;
                    # ayni metinde gercek bir kullanim varsa o yine yakalanir.
                    if not _istisna_mi(saman, m.start(), terim):
                        return True
            continue
        if folded in haystack_folded or flat in haystack_flat:
            return True
    return False


# ======================================================================
# 28.09.2026 — AŞIRI ENGELLEME DÜZELTMELERİ
#
# Ölçüm: motor, 39 ürünün ONAYLI KUTU METNİ üzerinde 77 bulgu üretti;
# 66'sı yanlıştı. Kanunen basmak zorunda olduğumuz üç metni engelliyordu:
# istenmeyen etki uyarısını, INCI listesini ve raf ömrünü.
#
# Kök neden tek: tarama, belgenin kendi kuralından (§1 "fiil değil NESNE
# denetlenir") önce davranıyordu. Nesnesi izinli olan cümle bile, içinde
# geçen terim yüzünden engelleniyordu. Cilt tipi düzeltmesi bunu tek kalıp
# için çözmüştü; burada kural genelleştiriliyor.
#
# Kaçak riski: her muafiyet, muafiyeti kötüye kullanacak cümleyi hâlâ
# engelleyen bir testle birlikte yazıldı (tests/test_asiri_engelleme.py).
# ======================================================================

# Uygulama BÖLGESİ tarifi iddia değildir (sahip kararı 28.09.2026:
# "alan adı kullanımı ve cilt tipi olarak değerlendir, sorun yok").
# "kas bölgesi" nerede uygulanacağını söyler; "kası gevşetir" işlev iddiasıdır.
AREA_DESCRIPTORS = ("kas bölge", "kas bolge", "kas bolgesi", "kas bölgesi")

# Yüzeysel görünüm terimleri: izinli bir nesneyle ya da temizlik bağlamıyla
# birlikte geçtiğinde hastalık adı sayılmaz. Liste bilinçli olarak dardır --
# egzama, sedef, mantar, kanser gibi tıbbi tanılar BU LİSTEDE YOKTUR ve
# "görünümü" eklenerek aklanamaz.
SURFACE_TERMS = ("leke", "çatlak", "catlak", "kızarıklık", "kizariklik",
                 "selülit", "sellulit", "sellülit", "yara izi")

# İzinli nesne veya temizlik bağlamı işaretleri.
_OBJECT_MARKERS = ("görünüm", "gorunum", "his", "doku", "nem", "konfor",
                   "koku", "temizle", "temizli", "yüzeyindeki", "yuzeyindeki")

# İstenmeyen etki uyarısı kalıpları -- zorunlu metin.
_WARNING_MARKERS = ("halinde kullanımı bırak", "halinde kullanimi birak",
                    "halinde kullanmayı bırak", "halinde kullanmayi birak",
                    "durumunda kullanımı bırak", "durumunda kullanimi birak",
                    "doktora başvur", "doktora basvur",
                    "hekime başvur", "hekime basvur",
                    "görülmesi halinde", "gorulmesi halinde")

# Fayda fiili: uyarı muafiyetini iptal eder ve süre iddiasını doğurur.
_BENEFIT_MARKERS = ("yardımcı ol", "yardimci ol", "destek", "azal", "gider",
                    "iyileş", "iyiles", "artır", "artir", "sağlar", "saglar",
                    "geçir", "gecir", "tedavi", "önler", "onler", "yok eder",
                    "pürüzsüz", "puruzsuz", "canlan", "sıkılaş", "sikilas",
                    "nemlen", "onar", "etki", "sonuç ver", "sonuc ver", "sonuçlan", "sonuclan",
                    "fark ed", "hissedil", "belirgin", "görünür", "gorunur",
                    "yumuşa", "yumusa", "parla", "beyazla", "temizle",
                    "dolgunlaş", "dolgunlas")

# Sağlık mesleği çağrışımı. Üretim ortamının kendisi (beyaz önlük,
# laboratuvar) bu listede DEĞİLDİR: sahip kararı 27.09.2026 -- kimyagerler de
# beyaz giyer ve kozmetik laboratuvarda üretilir. Otorite transferi, sağlık
# mesleği çağrışımı eşlik ettiğinde doğar.
_HEALTH_SIGNALS = ("doktor", "hekim", "eczacı", "eczaci", "hemşire", "hemsire",
                   "sağlık", "saglik", "tedavi", "reçete", "recete", "hasta",
                   "teşhis", "teshis", "klinik olarak")

# Bağlama bağlı otorite ifadeleri: tek başına işaretlenmez.
_AUTHORITY_CONTEXTUAL = ("beyaz önlük", "beyaz onluk", "klinik ortam",
                         "laboratuvar sahnesi")

# Kullanım talimatı deyimi -- rakiple kıyas değil.
_USAGE_IDIOMS = ("en iyi sonuç için", "en iyi sonuc icin")

# Zorunlu güneş ibaresinin kendisi oran iddiası sayılmaz.
_PERCENT_EXEMPT = ("%100 koruma", "% 100 koruma")

# INCI listesi başlıksız da gelebilir (alan adı metinde yoktur). Yapısal
# tanıma: çok sayıda virgülle ayrılmış parça ve içlerinde bileşen sözcükleri.
_INCI_TOKENS = ("yağı", "yagi", " oil", "extract", "ekstresi", "ekstre",
                "butter", "juice", "aqua", "water", "acid", "alcohol",
                "glycerin", "gliserin", "sodium", "parfum", "tocopherol",
                "tokoferol", " su,", "saf su")
_INCI_MIN_PARTS = 6
_INCI_MIN_TOKENS = 3


def _variants(term: str) -> list[str]:
    """Bir terimin maskelenecek bütün yazımları: düz, yumuşamış, aksansız."""
    out = []
    for base in (term, _soften(term)):
        if not base:
            continue
        f = fold(base)
        out.append(f)
        out.append(deaccent(f))
    return [v for v in dict.fromkeys(out) if v]


def _mask_re(terms) -> re.Pattern:
    parts = []
    for t in terms:
        parts.extend(re.escape(v) for v in _variants(t))
    return re.compile("|".join(sorted(set(parts), key=len, reverse=True)))


_AREA_RE = _mask_re(AREA_DESCRIPTORS)
_SURFACE_RE = _mask_re(SURFACE_TERMS)
_CONDITION_RE = _mask_re(
    tuple(t for _c, terms, _b in FORBIDDEN_OBJECTS for t in terms
          if _c == "hastalık veya durum adı"))


def _blank(rx: re.Pattern, haystack: str) -> str:
    """Eşleşmeyi aynı uzunlukta boşlukla değiştirir; kelime sınırları bozulmaz."""
    return rx.sub(lambda m: " " * len(m.group(0)), haystack)


def _has(folded: str, flat: str, markers) -> bool:
    return any(m in folded or deaccent(m) in flat for m in markers)


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
    if _FORMULA_ROW.search(sentence.strip()):
        return True
    # Alan adi metinde gecmeyebilir: VIREON ve FEMISIA'nin INCI listesi
    # basliksiz geliyordu ve bilesen tuzagi ZORUNLU beyani engelliyordu
    # (olculdu 28.09.2026). Yapisal tanima: cok parcali virgullu liste ve
    # icinde bilesen sozcukleri.
    parts = [x for x in sentence.split(",") if x.strip()]
    if len(parts) >= _INCI_MIN_PARTS:
        hits = sum(1 for tok in _INCI_TOKENS
                   if tok in folded or tok in ascii_lower)
        if hits >= _INCI_MIN_TOKENS:
            return True
    return False


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

    # --- nesne kontrolu, terim taramasinin ONUNDE ---
    # Belge §1: denetlenen sey fiil degil NESNEDIR. Nesnesi izinli olan cumle,
    # icinde gecen terim yuzunden engellenemez. Maskeleme sirasi:
    #   1) cilt tipi tanimlari            (sahip karari 27.09.2026)
    #   2) yuzey terimleri + izinli nesne (leke gorunumu, catlak gorunumu)
    #   3) istenmeyen etki uyarisi        (zorunlu metin)
    folded_ct = mask_skin_type(folded)
    flat_ct = mask_skin_type(flat, flat=True)

    if _has(folded, flat, _OBJECT_MARKERS):
        # Nesne izinli: yuzeysel gorunum terimi hastalik adi sayilmaz.
        # Tibbi tanilar SURFACE_TERMS'te yok, bu yuzden aklanmaz.
        folded_ct = _blank(_SURFACE_RE, folded_ct)
        flat_ct = _blank(_SURFACE_RE, flat_ct)

    if (_has(folded, flat, _WARNING_MARKERS)
            and not _has(folded, flat, _BENEFIT_MARKERS)):
        # Istenmeyen etki uyarisi: iddia degil, basilmasi zorunlu metin.
        # Fayda fiili varsa muafiyet YOK -- uyari ekleyerek iddia aklanamaz.
        folded_ct = _blank(_CONDITION_RE, folded_ct)
        flat_ct = _blank(_CONDITION_RE, flat_ct)

    # Uygulama bolgesi tarifi islev iddiasi degildir (sahip karari 28.09.2026).
    folded_fz = _blank(_AREA_RE, folded)
    flat_fz = _blank(_AREA_RE, flat)

    for category, terms, basis_key in FORBIDDEN_OBJECTS:
        if category == "hastalık veya durum adı":
            hay_folded, hay_flat = folded_ct, flat_ct
        elif category == "fizyolojik fonksiyon":
            hay_folded, hay_flat = folded_fz, flat_fz
        else:
            hay_folded, hay_flat = folded, flat
        for term in terms:
            if _contains(hay_folded, hay_flat, term):
                add(BLOCKED, f"yasak nesne — {category}", term, basis_key,
                    "Cümlenin nesnesi izinli listede değil "
                    f"({'/'.join(PERMITTED_OBJECTS)}). "
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

    # "En iyi sonuç için kurulayın" bir kullanım talimatıdır, rakiple kıyas
    # değil. Deyim maskelenir; "en iyi krem" engelli kalır.
    folded_us, flat_us = folded, flat
    for idiom in _USAGE_IDIOMS:
        folded_us = folded_us.replace(fold(idiom), " " * len(idiom))
        flat_us = flat_us.replace(deaccent(fold(idiom)), " " * len(idiom))
    for phrase in SUPERIORITY:
        if _contains(folded_us, flat_us, phrase):
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

    # Sahip kararı 27.09.2026: kimyagerler de beyaz önlük giyer ve kozmetik
    # laboratuvarda üretilir. Üretim ortamının kendisi sağlık çalışanı algısı
    # değildir; otorite transferi, sağlık mesleği çağrışımı EŞLİK ETTİĞİNDE
    # doğar. Yönetmelik maddesi kalkmadı, kapsamı daraltıldı.
    saglik_cagrisimi = _has(folded, flat, _HEALTH_SIGNALS)
    for phrase in AUTHORITY:
        if phrase in _AUTHORITY_CONTEXTUAL and not saglik_cagrisimi:
            continue
        if _contains(folded, flat, phrase):
            add(VERIFY, "sağlık çalışanı algısı / otorite transferi", phrase,
                "saglik_calisani",
                "Sağlık mesleği çağrışımıyla birlikte denetlenir; üretim "
                "ortamının kendisi (laboratuvar, önlük) tek başına ihlal değildir.")
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

    # Süre, bir ETKİYE bağlıyken iddiadır: "7 günde pürüzsüz". Raf ömrüne
    # ("24 ay – serin ve kuru yerde saklayınız") veya kullanım talimatına
    # ("en az 6 saat suyla temas ettirmeyiniz") bağlıyken iddia değildir.
    # Ölçüm 28.09.2026: 35 süre bulgusunun 35'i iddia değildi.
    duration = _DURATION.search(sentence)
    if duration and _has(folded, flat, _BENEFIT_MARKERS):
        add(VERIFY, "süre iddiası", duration.group(0), "ispat",
            "Klinik veri olmadan süre sonucu verilemez.")

    # Formülasyon tablosunun % sütunu iddia değildir; zorunlu güneş ibaresi
    # ("%100 koruma sağlamaz") de değildir.
    percent = _PERCENT.search(sentence)
    if percent and not ingredient_line and not _has(folded, flat, _PERCENT_EXEMPT):
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


# --------------------------------------------------------------------------
# Action Firewall kapısı
# --------------------------------------------------------------------------
# Müşteriye ulaşan metin taşıyan kanonik aksiyon tipleri. Bu listede OLMAYAN
# tipler taranmaz: PRICE_CHANGE'in yükü pazarlama metni değildir ve onu iddia
# gibi denetlemek yalnız gürültü üretir.
PUBLISHED_TEXT_ACTIONS = frozenset({
    "DRAFT_CUSTOMER_REPLY",
    "WHATSAPP_SEND_TEMPLATE",
    "WIX_PUBLISH",
    "META_CAMPAIGN_CHANGE",
})

# Yükte yayımlanabilir metin taşıyan alanlar. subject_ref bilerek dışarıda:
# o bir kimliktir, metin değildir -- taranırsa "coding-task:akne-fix" gibi bir
# referans hastalık adı sayılır.
# Firewall payload'unda taranan metin alanlari. `primary_text` ve
# `landing_page_message` OLCULEN bir acikti: ajans konsepti bu adlari
# kullaniyor ve liste onlari icermedigi icin reklamin asil govdesi kapidan
# denetlenmeden geciyordu. Yeni bir alan adi eklendiginde BURAYA da eklenmezse
# o alan sessizce taranmaz -- bu listenin eksikligi hata vermez, sadece
# denetimi atlatir.
TEXT_FIELDS = ("reason", "text", "body", "message", "caption", "content", "draft",
               "primary_text", "landing_page_message", "headline", "hook",
               "visual_brief", "video_15s_brief")


class ComplianceBlocked(ValueError):
    """Yayımlanacak metin kademe 1'de bloklu bir iddia taşıyor."""

    def __init__(self, findings):
        self.findings = tuple(findings)
        detail = "; ".join(f"{f.rule} <- {f.matched}" for f in self.findings[:4])
        super().__init__(f"COMPLIANCE_BLOCKED: {detail}")


def gate_payload(action_type: str, payload: dict[str, Any],
                 checked_at: str = "") -> dict[str, Any]:
    """Öneri yükünü mevzuat kapısından geçirir.

    BLOCKED bulgusu varsa ComplianceBlocked yükselir ve öneri hiç oluşmaz --
    firewall'un diğer her kuralı gibi fail-closed. VERIFY bulguları önermeyi
    durdurmaz ama zarfa iliştirilir, çünkü onları insan görmeli.
    """
    if action_type not in PUBLISHED_TEXT_ACTIONS:
        return {"checked": False, "reason": "aksiyon tipi metin yayımlamıyor"}

    parts = [str(payload[field]) for field in TEXT_FIELDS
             if isinstance(payload.get(field), str) and payload[field].strip()]
    if not parts:
        return {"checked": False, "reason": "yükte yayımlanabilir metin alanı yok"}

    result = review("\n".join(parts), checked_at=checked_at)
    if result.blocked:
        raise ComplianceBlocked(result.blocked)
    return {
        "checked": True,
        "clean_tier1": result.clean,
        "verify": [f.to_dict() for f in result.verify],
        "rules_source": result.rules_source,
        "note": ("Kademe 1 mekanik tarama geçti. Görsel yargı ve konumlandırma "
                 "onayı hâlâ insana ait."),
    }
