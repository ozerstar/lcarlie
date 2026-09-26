"""BRAND DNA -> CATEGORY DNA -> PRODUCT VISUAL DNA -> CONCEPT KERNEL.

Kural: olculmemis veya kaynakta olmayan nitelik UNKNOWN kalir.
Renk/malzeme/isik nitelikleri urun fotografindan OLCULUR; karakter
yargilari (enerji, duyusal) kutu metninden TURETILIR, uydurulmaz.

J maddesi: urun rengi = sayfa zemini gibi mekanik eslesme YASAK.
Sayfa/urun iliskisi asagidaki yedi iliskiden BIRI secilerek kurulur
ve hangisinin secildigi kayda gecer.
"""
from __future__ import annotations

BILINMIYOR = "UNKNOWN"

# --- I.1 BRAND DNA -------------------------------------------------------
MARKA_DNA = {
    "konum": "Luxury dermocosmetic",
    "eksenler": ("LUXURY", "BOTANICAL", "CLINICAL"),
    "ana_gerilim": "LUXURY × BOTANICAL × CLINICAL",
    "sutunlar": (
        "Botanical science -- formul bitkiseldir ve bunu gizlemez",
        "Clinical credibility -- iddia degil bilesen ve oran konusur",
        "Editorial sophistication -- katalog bir dergi gibi okunur",
        "Real-product integrity -- urun pikseli uretilmez, cekilir",
        "Luxury restraint -- az eleman, cok bosluk, yuksek islik",
    ),
    "olculen_gerceklik": (
        "36 urun / 9 bakim ailesi -- rakipler 3-8 urunde uzmanlasiyor",
        "Fiyat araligi 900-2.400 TL; rakip 350-1.682 TL -- daha pahali",
    ),
    "sonuc": ("Katalog 'tek kategoride en iyi' demiyor; 'bir ailenin tum "
              "cilt ihtiyaci tek markada' diyor. Gorsel dil bu genisligi "
              "tasimak zorunda."),
}

# --- I.2 CATEGORY DNA ----------------------------------------------------
# color/material/light: o kategorinin GERCEK urun fotograflarindan olculdu.
# energy / density / balance: kutu metninin diline gore turetildi.
KATEGORI_DNA = {
    "face": {
        "renk_karakteri": "soguk mavi-gri, dusuk doygunluk",
        "malzeme": "cam, akrilik, berrak jel, beyaz plastik",
        "isik": "yumusak, yandan, uzun capraz golge",
        "enerji": "sakin / klinik",
        "fotograf": "PRODUCT_EDITORIAL + DETAIL",
        "bilgi_yogunlugu": "YUKSEK -- icerik ve islev okunur",
        "botanik_klinik_dengesi": "klinik agirlikli",
    },
    "sport": {
        "renk_karakteri": "lime yesil + amber kahve, yuksek doygunluk",
        "malzeme": "mat karton, koyu cam, ter/jel",
        "isik": "sert, yon belirgin",
        "enerji": "yuksek / hareket",
        "fotograf": "HERO + HUMAN_LIFESTYLE",
        "bilgi_yogunlugu": "DUSUK -- kutu metni zaten sinirli",
        "botanik_klinik_dengesi": "botanik agirlikli (yag formulu)",
    },
    "intimate": {
        "renk_karakteri": "derin kirmizi (kadin) + derin mavi (erkek)",
        "malzeme": "mat siyah karton, amber cam",
        "isik": "kontrollu, dusuk anahtar",
        "enerji": "sessiz / ketum",
        "fotograf": "PRODUCT_EDITORIAL",
        "bilgi_yogunlugu": "ORTA-YUKSEK -- INCI tam ve uzun",
        "botanik_klinik_dengesi": "dengeli",
    },
    "baby": {
        "renk_karakteri": "sari + mavi, yuksek parlaklik",
        "malzeme": "mat karton, opak plastik",
        "isik": "acik, genis, gunes benzeri",
        "enerji": "parlak / korumaci",
        "fotograf": "HERO + PACKSHOT",
        "bilgi_yogunlugu": "ORTA -- zorunlu uyari baskin",
        "botanik_klinik_dengesi": "klinik agirlikli (fiziksel filtre)",
    },
}

# --- I.3 PRODUCT VISUAL DNA ---------------------------------------------
# CHROMATIC/MATERIAL/LIGHT/GEOMETRY: fotograf olcumunden (asset index)
# FUNCTIONAL/BOTANICAL: onayli kutu metninden
# SENSORY/ENERGY: kutu metninin kendi dilinden turetildi
# PHOTOGRAPHIC: elde bulunan photo_role dagilimi
URUN_DNA = {
    "hydravie": {
        "CHROMATIC": "beyaz gövde + camgöbeği şerit; zemin soğuk mavi-gri",
        "MATERIAL": "opak beyaz plastik pompa, karton kutu, cam blok",
        "LIGHT": "yandan yumuşak; ölçülen ışık açısı 163°, uzun çapraz gölge",
        "FUNCTIONAL": "günlük nemlendirme; el ve yüz",
        "BOTANICAL": "aloe vera, shea, skualan, bakuchiol, nar çekirdeği",
        "GEOMETRY": "dikey pompa + yatay kutu; ikili geometri",
        "SENSORY": "hafif doku, hızlı emilim, yağlı his bırakmaz",
        "ENERGY": "sakin, düşük tempo",
        "PHOTOGRAPHIC": "PRODUCT_EDITORIAL baskın; makro detay mevcut",
    },
    "kinesis+": {
        "CHROMATIC": "lime yeşili kutu + amber kahve şişe; en yüksek doygunluk",
        "MATERIAL": "mat karton, koyu cam/plastik, siyah etiket bandı",
        "LIGHT": "ölçülen açı 118°; sert ve yönlü",
        "FUNCTIONAL": "masajla uygulanan sporcu bakım kremi",
        "BOTANICAL": BILINMIYOR + " -- onaylı kutu metninde bileşen tablosu yok",
        "GEOMETRY": "dik kutu + yatık şişe; diyagonal ikili",
        "SENSORY": BILINMIYOR + " -- kutu metninde doku tarifi yok",
        "ENERGY": "yüksek; tek insan/hareket karesi bu üründe",
        "PHOTOGRAPHIC": "HERO + tek HUMAN_LIFESTYLE karesi",
    },
    "femisia": {
        "CHROMATIC": "derin kırmızı kutu + amber şişe; sıcak doygun",
        "MATERIAL": "mat siyah-kırmızı karton, amber cam, siyah pompa",
        "LIGHT": "ölçülen açı 95°; kontrollü, düşük anahtar",
        "FUNCTIONAL": "kadın hassas bölge bakım kremi",
        "BOTANICAL": "epimedium, maca kökü, hindistan cevizi, aloe, hodan",
        "GEOMETRY": "uzun dikdörtgen kutu; VIREON ile eş geometri",
        "SENSORY": "hafif doku, hızlı emilim, ipeksi his",
        "ENERGY": "sessiz, ketum",
        "PHOTOGRAPHIC": "PRODUCT_EDITORIAL; VIREON ile AYNI KAREDE",
    },
    "vireon": {
        "CHROMATIC": "derin mavi kutu + amber şişe; soğuk doygun",
        "MATERIAL": "FEMISIA ile aynı karton ve cam ailesi",
        "LIGHT": "FEMISIA ile aynı kare -- aynı ışık",
        "FUNCTIONAL": "erkek hassas bölge bakım kremi",
        "BOTANICAL": "epimedium, L-arginin, nioli, karabiber, havuç tohumu",
        "GEOMETRY": "FEMISIA ile eş geometri -- çift olarak tasarlanmış",
        "SENSORY": "yoğun nemlendirme, elastikiyet desteği",
        "ENERGY": "sessiz, ketum",
        "PHOTOGRAPHIC": "PRODUCT_EDITORIAL; FEMISIA ile AYNI KAREDE",
    },
    "babysol": {
        "CHROMATIC": "sarı kutu + kırmızı etiket + mavi zemin; en yüksek parlaklık",
        "MATERIAL": "mat sarı karton, opak plastik şişe",
        "LIGHT": "ölçülen açı 147°; açık, geniş",
        "FUNCTIONAL": "fiziksel filtreli bebek güneş kremi, non-nano çinko oksit %30",
        "BOTANICAL": "tamanu, shea, mango, jojoba, aloe, yulaf",
        "GEOMETRY": "kalın dikdörtgen kutu + yassı şişe",
        "SENSORY": BILINMIYOR + " -- kutu metninde doku tarifi yok",
        "ENERGY": "parlak, korumacı",
        "PHOTOGRAPHIC": "HERO + PACKSHOT; ambalajda çizgi film grafiği var",
    },
}

# --- J: sayfa/urun iliskisi ----------------------------------------------
ILISKILER = (
    "TONAL_CONTINUITY",        # sayfa urunun ton ailesini surdurur
    "NEUTRAL_ISOLATION",       # sayfa notr kalir, urun tek renk kaynagi
    "COMPLEMENTARY_CONTRAST",  # sayfa karsit tonla urunu iter
    "MATERIAL_DERIVATION",     # sayfa urunun MALZEMESINDEN turetilir
    "PHOTOGRAPHIC_CONTINUATION",  # sayfa fotografin zeminini surdurur
    "CONTROLLED_ACCENT",       # urun rengi yalnizca kucuk bir vurguda
    "NO_REPETITION",           # urun rengi sayfada HIC tekrarlanmaz
)


class IliskiIhlali(ValueError):
    pass


def iliski_dogrula(iliski: str, urun_rgb: tuple, sayfa_rgb: tuple) -> None:
    """Mekanik eslesmeyi yakala: 'urun rengi = sayfa zemini' YASAK."""
    if iliski not in ILISKILER:
        raise IliskiIhlali("bilinmeyen iliski: %s" % iliski)
    d = sum(abs(a - b) for a, b in zip(urun_rgb, sayfa_rgb, strict=True))
    if iliski == "NO_REPETITION" and d < 90:
        raise IliskiIhlali(
            "NO_REPETITION secildi ama sayfa zemini urun rengine cok yakin "
            "(manhattan %d < 90)" % d)
    if iliski != "TONAL_CONTINUITY" and d < 30:
        raise IliskiIhlali(
            "sayfa zemini urun rengiyle neredeyse ayni (manhattan %d < 30); "
            "bu mekanik eslesmedir, '%s' degil" % (d, iliski))


# --- K: CONCEPT KERNEL ---------------------------------------------------
# Tek cumlelik cekirdek gorsel fikir. Renk tarifi DEGILDIR.
KERNEL = {
    "cover": {
        "kernel": "Bir marka, aynı anda kaç ayrı dünyaya bakabildiğidir.",
        "neden_kernel": "Renk tarifi değil: sayfanın işi genişliği "
                        "göstermek. 'Üç renkli kapak' bir tarif olurdu; "
                        "bu bir iddia.",
        "reddettigi": "Tek ürünün kahraman olduğu kapak.",
    },
    "hydravie": {
        "kernel": "Nem, tutulan bir şeydir — tutulduğu yer görünür olmalı.",
        "neden_kernel": "'Mavi nemlendirme sayfası' renk tarifidir. "
                        "Askıda tutma fikri hem cam/gölge fotoğrafına hem "
                        "de tablo yapısına dönüşebilir.",
        "reddettigi": "Ürünü ortalayıp yanına açıklama koymak.",
    },
    "kinesis+": {
        "kernel": "Bakım, dinlenme anında değil çaba anında başlar.",
        "neden_kernel": "Kutu metninde bileşen tablosu YOK; bu ürünün "
                        "sayfası bilgiyle değil ANLA taşınmak zorunda.",
        "reddettigi": "Sahte bileşen listesi uydurmak.",
    },
    "femisia": {
        "kernel": "İki beden, tek formül dili — ayrım ürüne ait, bakıma değil.",
        "neden_kernel": "FEMISIA ve VIREON aynı karede çekilmiş ve eş "
                        "geometride. Fikir asetin kendisinde duruyor.",
        "reddettigi": "Kadın ürününü pembe, erkek ürününü lacivert yapmak.",
    },
    "babysol": {
        "kernel": "Koruma görünmez; görünen tek şey ondan sonraki gündür.",
        "neden_kernel": "Fiziksel filtre bir kalkan kurar. Sayfa kalkanı "
                        "çizmeden, ışığın kendisiyle anlatabilir.",
        "reddettigi": "Dev '50+' rakamı ve çocuksu grafik.",
    },
}


def kernel_sorgusu(kernel_anahtar: str, karar: str) -> str:
    """K: her buyuk tasarim kararina sorulacak soru."""
    k = KERNEL.get(kernel_anahtar, {}).get("kernel", BILINMIYOR)
    return ("DOES THIS STRENGTHEN THE CORE IDEA?\n  kernel : %s\n  karar  : %s"
            % (k, karar))


def dna_ozet() -> dict:
    bilinmeyen = []
    for u, d in URUN_DNA.items():
        for k, v in d.items():
            if str(v).startswith(BILINMIYOR):
                bilinmeyen.append("%s.%s" % (u, k))
    return {
        "marka_ekseni": MARKA_DNA["ana_gerilim"],
        "kategori": list(KATEGORI_DNA),
        "urun": list(URUN_DNA),
        "kernel": {k: v["kernel"] for k, v in KERNEL.items()},
        "iliskiler": list(ILISKILER),
        "UNKNOWN_alanlar": bilinmeyen,
    }


if __name__ == "__main__":
    import json
    o = dna_ozet()
    print(json.dumps(o, ensure_ascii=False, indent=1))
