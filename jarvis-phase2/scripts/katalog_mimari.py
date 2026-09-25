# -*- coding: utf-8 -*-
"""KATALOG MİMARİSİ — kararlar burada, çizim başka yerde.

Bu dosya bir renderer değil; **alınmış kararların kaydıdır**. Grid,
tipografi ölçeği, bölüm sırası ve renk ailesi burada durur ki tartışılabilsin
ve tek yerden değişsin.

═══ EXECUTIVE CREATIVE IDEA ═══

  "BİTKİNİN BİLDİĞİ YER"

Her L'CARLIÉ ürünü iki şeyin buluşma noktasıdır: **belirli bir bitki** ve
**hayatın belirli bir yeri.** Arnika morarmayı bilir, tamanu basınç altındaki
cildi, lavanta geceyi, papatya bebeğin ilk banyosunu.

🔴 BU FİKİR UYDURULMADI, VERİDEN ÇIKTI: 36 ürün özetinin tamamında hem bir
bitki adı hem somut bir durum geçiyor ("yoğun bir günün ardından", "uzun
süreli yatış", "spor öncesi veya sonrası", "gün sonunda bacaklara"). Katalog
bu yüzden "güzellik" anlatmaz; **yere uygulanmış bilgi** anlatır.

Fikrin ikinci işi: görsel çeşitlilik kuralını çözer. Her bölüm ayrı bir
MALZEME DÜNYASIDIR (su, bazalt, kil, tekstil, pamuk, mineral) -- aynı bej
set tekrar etmez, ama hepsi aynı ölçülü, bilimsel, editoryal dünyaya aittir.

═══ BİLGİ MİMARİSİ ═══

Kategoriler fiyata ya da ambalaja göre değil, **kullanım yerine** göre
kuruldu. 36 ürünün tamamı bir bölüme düşer; artan yoktur.
"""
from __future__ import annotations

# ── SAYFA VE IZGARA ──────────────────────────────────────────────────────
# A4 dikey. Baskı gerçek ölçüsü mm; PDF de mm ile üretilir, piksel değil.
SAYFA_EN_MM, SAYFA_BOY_MM = 210.0, 297.0
TASMA_MM = 3.0                    # bleed -- kesim payı
GUVENLI_MM = 5.0                  # safe area: kesim çizgisinden içeri

# Kenar boşlukları. İç kenar dışa göre GENİŞ: ciltlenen katalogda sayfanın
# iç tarafı kıvrıma girer ve dar bırakılırsa metin oraya gömülür.
UST_MM, ALT_MM = 20.0, 24.0
IC_MM, DIS_MM = 22.0, 18.0

SUTUN = 12
OLUK_MM = 4.0                     # gutter
TABAN_MM = 4.8                    # baseline grid

# ── TİPOGRAFİ ÖLÇEĞİ ─────────────────────────────────────────────────────
# 🔴 "Doğru fontu kullanmak yeterli değildir." Ölçek, satır yüksekliği ve
# harf aralığı burada SABİTLENİR; sayfa başına serbestçe seçilmez, yoksa
# katalog kendi içinde tutarsızlaşır.
#
# Gövde 9,5/14 -- A4'te 9,5 punto baskıda rahat okunur. Daha küçüğü
# (kataloglarda sık görülen 8 punto) dermokozmetik alıcısının yaş
# aralığında zorlar.
TIP = {
    "kapak_dev":   ("MonumentExtended-Ultrabold", 58, 58, 1.2),
    "bolum_dev":   ("MonumentExtended-Ultrabold", 40, 42, 0.8),
    "sayfa_basli": ("MonumentExtended-Regular",   20, 24, 0.4),
    "urun_ad":     ("MonumentExtended-Ultrabold", 14, 17, 0.6),
    "ust_etiket":  ("Metropolis-SemiBold",         7,  9, 2.2),
    "govde":       ("Metropolis-Regular",        9.5, 14, 0.0),
    "govde_hafif": ("Metropolis-Light",          9.5, 14, 0.0),
    "alt_yazi":    ("Metropolis-Medium",           7, 10, 0.2),
    "inci":        ("Metropolis-Light",            6,  8, 0.1),
    "sayfa_no":    ("Metropolis-Medium",           7,  9, 0.6),
}

# ── RENK ─────────────────────────────────────────────────────────────────
# Kontrollü aile: hepsi düşük doygunluk, yakın değer aralığı. Sayfalar
# farklıdır ama aynı markaya ait oldukları anlaşılır.
MUREKKEP = (0.09, 0.09, 0.10)       # ana metin
MUREKKEP_SOLUK = (0.42, 0.42, 0.44)
KAGIT = (0.957, 0.949, 0.933)

# ── AÇILIŞ DÜZENLERİ ─────────────────────────────────────────────────────
# 🔴 ALTI AÇILIŞIN DA TAM TAŞMA OLMASI BİR TEKRARDI. İlk sürümde her bölüm
# açılışı sayfayı dolduran bir görseldi; marka DNA'sı sabit kalmalı ama
# "aynı kompozisyonu tekrar etmek" aynı şey değildir. Üç düzen dönüşümlü
# kullanılır:
#   tam    görsel tam taşma; bölümün ağırlık merkezi
#   bant   görsel üstte bant, altta geniş negatif alan
#   sutun  görsel dar dikey sütun, yanında AŞIRI negatif alan
# Yan fayda: bant ve sütun düzenlerinde görsel daha küçük yerleşir, yani
# efektif DPI yükselir.
ACILIS_DUZENLERI = ("tam", "bant", "sutun")

# ── BÖLÜMLER ─────────────────────────────────────────────────────────────
# Her bölüm: slug listesi + renk + sahne + editoryal açılış cümlesi.
# `sahne` = gorsel-kuyruk/cikti altındaki dosya öneki.
BOLUMLER = [
    {
        "kod": "YUZ",
        "duzen": "bant",
        "ad": "YÜZ",
        "ustyazi": "BÖLÜM BİR",
        "vurgu": (0.478, 0.549, 0.549),
        "sahne": "kt-yuz",
        "acilis": "Cilt, günün ilk ve son on dakikasında bakılır. "
                  "Arada kalan on altı saat, o on dakikanın üstüne biner.",
        "urunler": ["luciderm", "hydravie", "optywave", "sunacnea-30-spf"],
    },
    {
        "kod": "VUCUT",
        "duzen": "tam",
        "ad": "VÜCUT VE HAREKET",
        "ustyazi": "BÖLÜM İKİ",
        "vurgu": (0.760, 0.447, 0.227),
        "sahne": "kt-vucut",
        "acilis": "Kas ısınmayı, bacak gün sonunu, çene geceyi bilir. "
                  "Bitkisel yağların ısıtıcı hissi buraya aittir.",
        "urunler": ["dermamovera", "dorsivia", "kinesis", "dermavasc",
                    "seralimbo", "menthalis", "calmoris", "calmjaw"],
    },
    {
        "kod": "BARIYER",
        "duzen": "sutun",
        "ad": "CİLT BARİYERİ",
        "ustyazi": "BÖLÜM ÜÇ",
        "vurgu": (0.659, 0.420, 0.322),
        "sahne": "kt-bariyer",
        "acilis": "Bariyer görünmez olduğunda iyi çalışıyordur. "
                  "Basınç, sürtünme ve kuruluk onu ilk yoklayan şeylerdir.",
        "urunler": ["dermabed", "dermanova", "dermarnica", "dermastra",
                    "dermacorn", "dermaguard", "lipvora"],
    },
    {
        "kod": "MAHREM",
        "duzen": "tam",
        "ad": "MAHREM BAKIM",
        "ustyazi": "BÖLÜM DÖRT",
        "vurgu": (0.549, 0.333, 0.400),
        "sahne": "kt-mahrem",
        "acilis": "Konuşulmayan bakım alanları, en çok özen isteyenlerdir. "
                  "Formülasyon burada sessiz ve ölçülü olmak zorundadır.",
        "urunler": ["femisia-for-women", "vireon-for-men", "intimblanc",
                    "liftelle"],
    },
    {
        "kod": "BEBEK",
        "duzen": "bant",
        "ad": "BEBEK",
        "ustyazi": "BÖLÜM BEŞ",
        "vurgu": (0.561, 0.659, 0.749),
        "sahne": "kt-bebek",
        "acilis": "Bebek cildi yetişkin cildinin küçüğü değildir. "
                  "Bariyeri daha ince, tepkisi daha hızlıdır.",
        "urunler": ["babysoft", "babysol", "minisooth-bebek-pişik-kremi",
                    "babydent", "babyshower", "baby-rescue", "easycomb"],
    },
    {
        "kod": "RITUEL",
        "duzen": "sutun",
        "ad": "GÜNLÜK RİTÜEL",
        "ustyazi": "BÖLÜM ALTI",
        "vurgu": (0.431, 0.498, 0.388),
        "sahne": "kt-ritual",
        "acilis": "Bakım yalnız ciltte olmaz. Ağız, saç ve yaşanan alan "
                  "aynı rutinin parçasıdır.",
        # hair-nouriher Wix'teki GERCEK slug ve icinde yazim hatasi
        # var (nourisher -> nouriher). Duzeltmek URL'i degistirir ve
        # varsa disaridan gelen baglantilari kirar -- sahip karari.
        "urunler": ["bright-smile", "oragarde", "hair-nouriher", "calmaros",
                    "buguard", "softguard"],
    },
]

# Kapak ve kapanış
KAPAK = {
    "sahne": "kt-kapak",
    "ust": "L'CARLIÉ",
    "dev": "BİTKİNİN\nBİLDİĞİ YER",
    "alt": "Botanik formülasyon · Dermokozmetik bakım · 36 ürün",
}

MANIFESTO = (
    "Bir bitkiyi tanımak, onu bir kremin içine koymak demek değildir.\n\n"
    "Arnika morarmayı bilir. Tamanu basınç altında kalan cildi bilir. "
    "Lavanta geceyi, papatya bebeğin ilk banyosunu bilir.\n\n"
    "L'CARLIÉ formülasyonları bu bilgiyi bir yere uygular: belirli bir "
    "bölgeye, belirli bir ana, belirli bir ihtiyaca."
)
