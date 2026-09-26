"""Reference / Taste Intelligence (C03) + Anti-Luxury Failure Memory (Y).

DURUSTLUK NOTU -- bu modulun sinirlari:

Disaridan dergi/katalog referansi TARANMADI. Elimde dogrulanmis bir
referans kutuphanesi yok ve olmayan bir kaynaga atif uydurmayacagim.
Asagidaki PRENSIPLER bu projede OLCULEN kanittan cikarildi:

  - eski kare katalog (52 sayfa, 210x210)  -> 43 algisal ayni cift
  - eski A4 surumu (33 sayfa, 216x303)     -> 9 algisal ayni cift
  - tur 1 / tur 2 / tur 3 pilotlari        -> olculen zemin, punto,
    yogunluk, kontrast degerleri ve reddedilme gerekceleri

Yani bunlar "begendigim sayfalardan cikardigim izlenimler" degil,
bu katalogda OLCULMUS davranislardir. Gercek dis referans geldiginde
`DIS_REFERANS_DURUMU` guncellenir.
"""
from __future__ import annotations

DIS_REFERANS_DURUMU = {
    "durum": "YOK",
    "neden": "Dogrulanmis dis referans kutuphanesi saglanmadi.",
    "gereken": "Sahibin sectigi 5-10 gercek katalog/dergi sayfasi "
               "(PDF ya da yuksek cozunurluklu tarama).",
    "uydurma_yapildi_mi": "HAYIR",
}

# --- X: REFERENCE -> DESIGN PRINCIPLE ------------------------------------
# Her prensip: neyin olculdugu, neden ise yaradigi, nasil uygulanacagi.
PRENSIPLER = [
    {
        "eksen": "hierarchy",
        "prensip": "Olcek kontrasti sayfadan sayfaya DEGISMELI; sabit "
                   "kontrast hiyerarsi degil aliskanlik uretir.",
        "kanit": "Tur 1'de bes sayfanin besinde de display 27-32 pt ve "
                 "olcek kontrasti ~3x sabitti; tur 2'de aralik 14-19 pt'ye "
                 "daraldi. Tur 3'te 12.5-30 pt araligi acilinca sayfalar "
                 "birbirinden ayrildi.",
        "uygulama": "Her sayfa icin hedef olcek kontrasti dizide onceden "
                    "belirlenir; iki komsu sayfa ayni kontrasta sahip olamaz.",
    },
    {
        "eksen": "product prominence",
        "prensip": "Urun buyuklugu fiziksel kaynakla sinirlidir; 'daha "
                   "buyuk gostermek' icin yukari ornekleme yapmak urunun "
                   "kendisini bozar.",
        "kanit": "Eski katalog ~97 mm urun genisligini ancak ~2.3x yukari "
                 "ornekleme ile elde etmisti. 1254 px kaynak 212 mm'de "
                 "150.2 DPI verir; 1800x1200 kaynak 216x216 mm'de 141 DPI'a "
                 "duser -- taban delinir.",
        "uygulama": "Yerlesim olcusu once DPI ile sinanir, sonra "
                    "kompozisyona girer. Tersi degil.",
    },
    {
        "eksen": "negative space",
        "prensip": "Bosluk gorunce doldurma; once ACTIVE mi DEAD mi "
                   "siniflandir. Renkli alan da bos olabilir.",
        "kanit": "Tur 2 FEMISIA sayfasinda bosluk orani 0.00 olculdu "
                 "cunku alan RENKLIYDI; gozle bakildiginda sol ust ucte "
                 "biri islevsizdi. Kapi bunu goremedi.",
        "uygulama": "Bosluk siniflandirmasi gorsel karar olarak kayda "
                    "gecer; olcum tek basina yetmez.",
    },
    {
        "eksen": "grid / grid breaking",
        "prensip": "Grid'i bazen fotograf kurar. Fotografin kendi "
                   "geometrisi sayfa grid'inden guclu ise grid geri ceker.",
        "kanit": "Tur 1 KINESIS'te fotografin uzerine sayfa grid'i "
                 "oturtulmustu ve AD 'fotograf layout'tan yaratici' dedi. "
                 "Tur 3'te fotograf kendi 3:2 cercevesinde birakildi.",
        "uygulama": "Fotografin olculen agirlik merkezi ve sakin bolgeleri "
                    "yerlesimin girdisi olur.",
    },
    {
        "eksen": "type / image",
        "prensip": "Ters tipografi ESTETIK degil OLCUM karari ile "
                   "yerlesir; sakin bolge tespiti baslangictir, karar degil.",
        "kanit": "KINESIS salon karesinde sol-ust L=212 (pencere), "
                 "sol-alt L=7..54. Tur 2 tasarisi metni sol-uste koyuyordu.",
        "uygulama": "Metin/goruntu kontrast kapisi zorunlu; ayrica metnin "
                    "kompozisyona tutunup tutunmadigi gozle denetlenir.",
    },
    {
        "eksen": "materiality",
        "prensip": "Marka tutarliligi ayni iskeletle degil ayni MALZEME "
                   "disipliniyle kurulur -- ama tek malzeme dunyasi da "
                   "tekdüzelik uretir.",
        "kanit": "Tur 2'de bes sayfanin dordu ayni sicak krem zemin "
                 "ailesindeydi (RGB 207-233/190-223/176-209). Her sayfa "
                 "tek basina kusursuzdu; kusur dizideydi.",
        "uygulama": "Dizi duzeyinde zemin ailesi dagilimi denetlenir; "
                    "tek aile %60'i gecemez.",
    },
    {
        "eksen": "color",
        "prensip": "Urun rengi ile sayfa iliskisi SECILIR ve kayda gecer; "
                   "mekanik eslesme (urun rengi = zemin) yasaktir.",
        "kanit": "Yedi mesru iliski tanimlandi (katalog_dna.ILISKILER); "
                 "bazen dogru karar urun rengini sayfada HIC "
                 "tekrarlamamaktir.",
        "uygulama": "Her sayfa plani hangi iliskiyi kullandigini bildirir "
                    "ve iliski_dogrula() ile sinanir.",
    },
    {
        "eksen": "density",
        "prensip": "Yogunluk ritmi olmalidir: en yogun sayfa en seyregin "
                   "en az iki kati olmali.",
        "kanit": "Tur 3'te metin orani araligi 0.0149-0.0509 (3.4x). "
                 "Tur 2'de 0.011-0.065 idi ama zemin ailesi tekdüzeydi -- "
                 "yogunluk tek basina yetmiyor.",
        "uygulama": "dizi_ritmi() yogunluk araligini denetler.",
    },
    {
        "eksen": "crop tension",
        "prensip": "Kadraj urunun logotype'ini kelime ortasindan "
                   "kesmemelidir; kesilecekse tamamen disarida kalmali.",
        "kanit": "Tur 3 ilk iterasyonunda 70x144 mm pano kaynagin %32.4'unu "
                 "aliyordu, urun kutulari %46-56 genisliginde -- 'ARLIE', "
                 "'FEMISI' gibi kesikler olustu.",
        "uygulama": "Pano orani urun kutusu genisligine gore hesaplanir.",
    },
    {
        "eksen": "information hierarchy",
        "prensip": "Mansetsizlik bir karardir ama yerine bir sey koymayi "
                   "gerektirir.",
        "kanit": "Tur 2'de manset kaldirildi; yalnizca HYDRAVIE'de yerine "
                 "tablo kondu ve tek PASS alan sayfa o oldu.",
        "uygulama": "Manset yoksa sayfanin baskin ogesi acikca bildirilir.",
    },
    {
        "eksen": "luxury restraint",
        "prensip": "Luks daha cok eleman degil; her elemanin kaldirilma "
                   "testinden gecmesidir.",
        "kanit": "Tur 2 BABYSOL'de yari saydam bant butun kapilari geciyor "
                 "ama 'tasarlanmis mi yerlestirilmis mi' olculemiyordu.",
        "uygulama": "REMOVE TEST her final elemana uygulanir.",
    },
    {
        "eksen": "sequence contribution",
        "prensip": "En guzel fotograf katalog icin en dogru fotograf "
                   "olmayabilir.",
        "kanit": "FEMISIA icin F2 'Mimari Sessizlik' karesi olculen en "
                 "yuksek kontrastli (0.528) kareydi; F5 secilince besinci "
                 "sayfa da krem dunyasina girdi.",
        "uygulama": "Fotograf secimi LOCAL QUALITY + SEQUENCE CONTRIBUTION "
                    "birlikte degerlendirilerek yapilir.",
    },
]


# --- Y: ANTI-LUXURY FAILURE MEMORY ---------------------------------------
# Sadece yasak degil: NEDEN basarisiz oldugu kayitli.
HATA_KUTUGU = [
    {"kod": "RANDOM_PASTEL_RECTANGLES",
     "neden_basarisiz": "Dikdortgen bir bilgi tasimadiginda sayfa "
                        "'duzenlenmis' gorunur ama okunmaz; hiyerarsi "
                        "renkle taklit edilir.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "DEAD_WHITESPACE",
     "neden_basarisiz": "Bosluk islev tasimadiginda sayfa bitmemis "
                        "gorunur; okur gozunu dinlendirmez, kaybolur.",
     "bu_projede_goruldu": "EVET -- tur 1 BABYSOL ust sol %45 zeytin alan"},
    {"kod": "EVERYTHING_CENTERED",
     "neden_basarisiz": "Ortalama karar vermemektir; gerilim ve yon "
                        "uretmez, her sayfa ayni gorunur.",
     "bu_projede_goruldu": "EVET -- tur 1 FEMISIA packshot"},
    {"kod": "SMALL_PRODUCT_GIANT_EMPTY",
     "neden_basarisiz": "Urun kucuk kalinca katalog urunu satmaz, "
                        "estetigi satar; eczaci urunu tanimaz.",
     "bu_projede_goruldu": "EVET -- tur 2 FEMISIA (14 pt ad)"},
    {"kod": "ROUNDED_UI_CARDS",
     "neden_basarisiz": "Ekran arayuzu dili basili sayfada yabanci durur; "
                        "kagit bir uygulama degildir.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "INGREDIENT_ICON_GRID",
     "neden_basarisiz": "Dort esit ikon hiyerarsi yok eder; hangi bilesen "
                        "kahraman belli olmaz, hepsi esit onemsizlesir.",
     "bu_projede_goruldu": "HAYIR -- P maddesiyle onlendi"},
    {"kod": "GRADIENT_SPAM",
     "neden_basarisiz": "Degrade baskida bantlasir ve dijital gorunur; "
                        "ayrica malzemeden degil efektten gelir.",
     "bu_projede_goruldu": "HAYIR -- B2 konsepti bu gerekceyle elendi"},
    {"kod": "GOLD_LINE_LUXURY",
     "neden_basarisiz": "Altin cizgi luksu isaret eder ama uretmez; "
                        "isaret ucuzdur, malzeme pahalidir.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "PREMIUM_BEIGE",
     "neden_basarisiz": "Bej 'sofistike' varsayilir ve secilmeden alinir; "
                        "secilmemis notr en hizli taninan AI izidir.",
     "bu_projede_goruldu": "EVET -- tur 2'de 4/5 sayfa sicak krem"},
    {"kod": "SAME_TEMPLATE",
     "neden_basarisiz": "Okur ikinci sayfada sistemi cozer, ucuncude "
                        "okumayi birakir.",
     "bu_projede_goruldu": "EVET -- tur 1, ECD gerekcesi"},
    {"kod": "STOCK_BOTANICAL_DECORATION",
     "neden_basarisiz": "Formulle iliskisi olmayan yaprak sustur; "
                        "botanik iddiayi zayiflatir cunku dekoratiflesir.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "FAKE_LAB_GRAPHICS",
     "neden_basarisiz": "Uydurma grafik klinik guvenilirligi yok eder; "
                        "tek yalan tum sayfayi supheli yapar.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "BADGE_OVERLOAD",
     "neden_basarisiz": "Her sey vurgulaninca hicbir sey vurgulanmaz.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "UNNECESSARY_SHADOWS",
     "neden_basarisiz": "Sahte golge gercek golgeli fotografla catisir; "
                        "iki farkli isik kaynagi sayfayi bozar.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "GIANT_HEADLINE_EVERYWHERE",
     "neden_basarisiz": "Manset refleks haline gelince karar olmaktan "
                        "cikar; her sayfa bagirinca hicbiri duyulmaz.",
     "bu_projede_goruldu": "EVET -- tur 1, AD gerekcesi"},
    {"kod": "PASTED_ECOMMERCE_PACKSHOT",
     "neden_basarisiz": "E-ticaret karesi katalog sayfasina yapistirilinca "
                        "sayfa urun kartina doner; editoryal olmaz.",
     "bu_projede_goruldu": "EVET -- tur 1 FEMISIA"},
    {"kod": "CANVA_TEMPLATE_FEELING",
     "neden_basarisiz": "Hazir sablon markaya degil sablona ait gorunur.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "CORPORATE_PDF_FEELING",
     "neden_basarisiz": "Kurumsal PDF bilgi tasir ama arzu uretmez; "
                        "dermokozmetikte arzu satisin parcasidir.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "AI_CLUTTER",
     "neden_basarisiz": "Doldurulmus sayfa 'cok calisilmis' gorunur ama "
                        "karar iceremez; luks karardir.",
     "bu_projede_goruldu": "HAYIR"},
    {"kod": "MANIFEST_BLIND_SPOT",
     "neden_basarisiz": "Uretimde kullanilan aset manifestte yoksa "
                        "'human_subject = 0' gibi dogru gorunen ama "
                        "kapsam disi bir iddia uretilir.",
     "bu_projede_goruldu": "EVET -- V1 indeksi yalnizca cekim-ham'i "
                           "tariyordu, KINESIS pilot-assets'ten geliyordu"},
    {"kod": "PPI_FLOOR_AS_QUALITY",
     "neden_basarisiz": "150 PPI tabanini 'baski kalitesi' saymak; "
                        "'interpolasyon yok' ile 'yuksek baski kalitesi' "
                        "ayni sey degildir.",
     "bu_projede_goruldu": "EVET -- V1 raporu 150'yi gecer not sayiyordu"},
]


def hata_ara(kod: str) -> dict | None:
    for h in HATA_KUTUGU:
        if h["kod"] == kod:
            return h
    return None


def gorulen_hatalar() -> list[dict]:
    return [h for h in HATA_KUTUGU if h["bu_projede_goruldu"].startswith("EVET")]


if __name__ == "__main__":
    print("dis referans durumu:", DIS_REFERANS_DURUMU["durum"],
          "| uydurma:", DIS_REFERANS_DURUMU["uydurma_yapildi_mi"])
    print("prensip: %d" % len(PRENSIPLER))
    print("hata kutugu: %d  (bu projede goruldu: %d)"
          % (len(HATA_KUTUGU), len(gorulen_hatalar())))
    print()
    for p in PRENSIPLER:
        print("[%s] %s" % (p["eksen"], p["prensip"][:70]))
