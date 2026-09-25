"""Katalog Yetenek Kutugu -- 18 capability'nin makine-okunur kaydi.

NEDEN AYRI BIR KUTUK:
    Denetimde olculdu: 14 persona ayni iki kaynagi okuyordu, hicbiri
    uretimi degistiremiyordu. "Agent sayisi" ile "capability sayisi"
    birbirine karismisti. Bu kutuk ikisini ayirir.

UC KATMAN (FAZ -1B ana hedefi):
    KNOWLEDGE       -- uzman ne biliyor            -> knowledge_required
    INSTRUMENTATION -- sistem neyi olcebiliyor     -> measurements_required
    AUTHORITY       -- kim neyi reddedebiliyor     -> authority

    Yalniz adi ve promptu olan rol IMPLEMENTED sayilmaz.
    Olcup sonucu hicbir seyi degistirmeyen rol GATEKEEPER sayilmaz.

BU MODUL DIS BAGIMLILIK KULLANMAZ. Yalnizca stdlib.

TUZAK -- OLCULDU 25.09.2026:
    jarvis/operator.py stdlib 'operator' modulunu golgeler. Bu yuzden
    'python jarvis/katalog_yetenek.py' CALISMAZ (dairesel import).
    Her zaman 'python -m jarvis.katalog_yetenek' kullan.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable

# --- sabit kumeler -------------------------------------------------------

TIPLER = ("CREATIVE", "HYBRID", "DETERMINISTIC", "VISION", "HUMAN")

DURUMLAR = ("DEFINED", "PARTIAL", "IMPLEMENTED", "TESTED", "GATED")

# Yetki kademeleri -- artan siddet sirasiyla.
YETKILER = (
    "ADVISE",             # yalniz gorus bildirir, akisi degistirmez
    "REVISE",             # duzeltme ister, uretim durmaz
    "REJECT",             # ilgili fazi geri gonderir
    "HARD_REJECT",        # uretimi durdurur, asilamaz
    "APPROVE",            # ileri gecisi onaylar
    "ESCALATE_TO_HUMAN",  # karari sahibe tasir
)


@dataclass(frozen=True)
class Yetenek:
    """Tek bir capability kaydi. Alan adlari sozlesmedir, degistirilmez."""

    id: str
    name: str
    type: str
    purpose: str
    knowledge_required: tuple[str, ...] = ()
    tools_required: tuple[str, ...] = ()
    measurements_required: tuple[str, ...] = ()
    vision_required: bool = False
    llm_required: bool = False
    human_required: bool = False
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    acceptance_conditions: tuple[str, ...] = ()
    rejection_conditions: tuple[str, ...] = ()
    authority: tuple[str, ...] = ()
    upstream: tuple[str, ...] = ()
    downstream: tuple[str, ...] = ()
    implementation_status: str = "DEFINED"
    evidence: tuple[str, ...] = ()

    def sozluk(self) -> dict:
        return asdict(self)


def _y(**kw) -> Yetenek:
    """Kisa yazim; tuple'a cevirmeyi tek yerde yapar."""
    for anahtar, deger in list(kw.items()):
        if isinstance(deger, list):
            kw[anahtar] = tuple(deger)
    return Yetenek(**kw)


# --- kutuk ---------------------------------------------------------------
# Sira uretim akisina gore: once olcen, sonra yargilayan.

KUTUK: tuple[Yetenek, ...] = (
    _y(
        id="C01",
        name="Executive Creative Director",
        type="CREATIVE",
        purpose="Katalogun bir fikre mi yoksa iyi uygulanmis bir sablona mi dayandigina karar verir.",
        knowledge_required=["02-art-direction", "01-brand", "09-luxury-cosmetics"],
        tools_required=["faz_ozet_toplayici", "sayfa_kucuk_goruntu"],
        measurements_required=[],
        vision_required=True,
        llm_required=True,
        inputs=["faz_ozetleri", "marka_konumu", "ret_kayitlari"],
        outputs=["ana_fikir", "yaratici_seviye", "reddedilen_yonler", "tutarsizliklar"],
        acceptance_conditions=[
            "ana fikir tek cumlede yazilabiliyor",
            "yaratici_seviye >= 4",
            "bolumler arasi tutarsizlik listesi bos",
        ],
        rejection_conditions=[
            "ana fikir cumlesi yazilamiyor",
            "cumle rakiplere de uyuyor",
            "bolumler celiskili marka anlatiyor",
        ],
        authority=["REJECT", "ESCALATE_TO_HUMAN"],
        upstream=["C02", "C04", "C07", "C13"],
        downstream=["HUMAN"],
        implementation_status="DEFINED",
        evidence=["FAZ -1 raporu B03 kart 01"],
    ),
    _y(
        id="C02",
        name="Brand & Category Strategist",
        type="CREATIVE",
        purpose="Eczacinin katalogu kapattiginda markayi nasil hatirlayacagini tanimlar.",
        knowledge_required=["01-brand", "10-dermocosmetics", "09-luxury-cosmetics"],
        tools_required=["company_memory_okuyucu"],
        measurements_required=["semantik_ayirt_edicilik"],
        llm_required=True,
        inputs=["knowledge/11-marka-dili.md", "customer_voice", "market_research"],
        outputs=["konum_cumlesi", "kanit_sutunlari", "kacinilacak_algi"],
        acceptance_conditions=[
            "konum cumlesi rakip cumlelerine semantik olarak yakin degil",
            "her kanit sutununun veri kaynagi var",
        ],
        rejection_conditions=["editoryal hikaye konum cumlesiyle celisiyor"],
        authority=["REJECT"],
        upstream=[],
        downstream=["C04", "C05"],
        implementation_status="DEFINED",
        evidence=["FAZ -1 raporu B03 kart 02"],
    ),
    _y(
        id="C03",
        name="Research & Reference Director",
        type="CREATIVE",
        purpose="Her tasarim kararinin literaturdeki karsiligini bulur veya bulunamadigini soyler.",
        knowledge_required=["00-core"],
        tools_required=["web_arama", "belge_cekme", "kaynak_kaydi"],
        measurements_required=["kaynak_kademesi"],
        llm_required=True,
        inputs=["dis_kaynaklar"],
        outputs=["ilke", "kaynak_url", "kaynak_kademesi", "kanit_kalitesi"],
        acceptance_conditions=["kaynaksiz ilke yok", "her ilkenin kademesi yazili"],
        rejection_conditions=["kaynaksiz tasarim gerekcesi", "blog iddiasinin standart gibi sunulmasi"],
        authority=["REJECT"],
        upstream=[],
        downstream=["C01", "C07", "C08", "C15"],
        implementation_status="PARTIAL",
        evidence=["jarvis arastirma yetenegi mevcut, katalog baglamina bagli degil"],
    ),
    _y(
        id="C04",
        name="Editorial Director / Information Architect",
        type="CREATIVE",
        purpose="36 urunu liste degil anlati haline getiren sirayi ve ritmi kurar.",
        knowledge_required=["03-editorial-design", "17-sales-usability"],
        tools_required=["urun_veri_okuyucu", "ritim_dogrulayici"],
        measurements_required=["yogunluk_haritasi", "bolum_kapsama", "ardisik_tekrar"],
        llm_required=True,
        inputs=["urun_karti", "sales_items", "soru_konu", "konum_cumlesi"],
        outputs=["bolumler", "urun_sirasi", "sayfa_ritmi", "bilgi_yogunlugu_haritasi"],
        acceptance_conditions=[
            "her bolum gecisi gerekceli",
            "ardisik uc sayfa ayni yogunluk kademesinde degil",
            "her urun tam olarak bir bolumde",
        ],
        rejection_conditions=["sayfa sistemi hikaye akisini bozuyor"],
        authority=["REJECT"],
        upstream=["C02"],
        downstream=["C08", "C14"],
        implementation_status="PARTIAL",
        evidence=["scripts/katalog_mimari.py BOLUMLER elle yazilmis sabit liste"],
    ),
    _y(
        id="C05",
        name="Senior Copywriter",
        type="HYBRID",
        purpose="Urunun dogrulanmis gercegini 36 urun boyunca ayni kaliba dusmeden anlatir.",
        knowledge_required=["08-copy-editorial", "16-regulatory", "01-brand"],
        tools_required=["kalip_envanteri", "turkce_imla"],
        measurements_required=["ngram_tekrar", "birebir_tekrar", "anlamsal_benzerlik"],
        llm_required=True,
        inputs=["urun_bilgi", "knowledge/30-urun-*.md", "konum_cumlesi"],
        outputs=["baslik", "govde", "mikro_metin", "kaynak_satirlari"],
        acceptance_conditions=[
            "kalip tekrari esik altinda",
            "birebir tekrar eden satis cumlesi = 0 (zorunlu uyarilar haric)",
            "her cumle bir kaynak satirina bagli",
        ],
        rejection_conditions=[],
        authority=[],
        upstream=["C02"],
        downstream=["C06"],
        implementation_status="PARTIAL",
        evidence=["metin uretiliyor; kalip/anlam olcumu yok"],
    ),
    _y(
        id="C06",
        name="Regulatory Copy Editor",
        type="HYBRID",
        purpose="Her satis cumlesinin urunun gercegine mi yazarin iyi niyetine mi dayandigini ayirir.",
        knowledge_required=["16-regulatory"],
        tools_required=["jarvis.compliance", "jarvis.turkish", "kutu_gercegi_okuyucu"],
        measurements_required=["kaynak_baglanabilirlik", "zorunlu_ibare_kapsama", "yasak_ifade_eslesmesi"],
        llm_required=True,
        inputs=["C05 ciktisi", "varliklar/kutu-gercegi/*.json", "zorunlu_uyari_listesi"],
        outputs=["karar", "gerekce", "kaynak_kanit", "zorunlu_uyari_eksik"],
        acceptance_conditions=[
            "her satis cumlesi bir kaynaga baglanmis",
            "zorunlu uyarisi eksik urun = 0",
        ],
        rejection_conditions=[
            "kaynaga baglanamayan cumle",
            "tibbi iddiaya kayan nesne",
            "eksik zorunlu ibare",
        ],
        authority=["HARD_REJECT", "REVISE"],
        upstream=["C05"],
        downstream=["C08"],
        implementation_status="PARTIAL",
        evidence=["jarvis.compliance mevcut, katalog uretim hattina bagli degil"],
    ),
    _y(
        id="C07",
        name="Art Director",
        type="CREATIVE",
        purpose="Urunlerin sayfada guclu mu kucuk mu durdugunu karara baglar.",
        knowledge_required=["02-art-direction", "05-composition", "04-product-photography"],
        tools_required=["saliency", "kontrast_haritasi", "sayfa_render"],
        measurements_required=["urun_baskinlik_kaniti", "sayfa_olcumleri", "kirpma_korunumu"],
        vision_required=True,
        llm_required=True,
        inputs=["varlik_siniflandirmasi", "baskinlik_kaniti", "sayfa_render"],
        outputs=["fotograf_dili", "urun_baskinlik_hedefi", "kadraj_yonergesi", "gorsel_ritim_plani"],
        acceptance_conditions=[
            "her sayfanin gorsel rolu tanimli",
            "baskinlik hedefi profil olarak verilmis (tek oran degil)",
        ],
        rejection_conditions=[
            "urun gorsel hiyerarside kayboluyor",
            "klise kompozisyon",
            "isik yonu sahne ile celisiyor",
        ],
        authority=["REJECT", "REVISE"],
        upstream=["C07A", "C08", "C10"],
        downstream=["C01"],
        implementation_status="DEFINED",
        evidence=["FAZ -1 raporu B03 kart 07"],
    ),
    _y(
        id="C07A",
        name="Product Asset Classifier",
        type="HYBRID",
        purpose="Her urun gorselini dort sinifa ayirir ve editoryal fotografin kesilmesini engeller.",
        knowledge_required=["04-product-photography", "13-print-production"],
        tools_required=["pillow", "kenar_analizi"],
        measurements_required=[
            "cozunurluk", "efektif_dpi", "arka_plan_karmasikligi",
            "konu_izolasyonu", "kompozisyon_kaniti", "azami_yerlesim_mm",
        ],
        vision_required=False,
        inputs=["ham_gorsel", "hedef_yerlesim_mm"],
        outputs=["asset_type", "confidence", "evidence", "allowed_operations", "forbidden_operations"],
        acceptance_conditions=[
            "her gorsel tam bir sinifta",
            "her sinif karari sinyal degerleriyle gerekceli",
            "azami_yerlesim_mm hesaplanmis",
        ],
        rejection_conditions=[
            "TYPE A gorselin kesilmeye gonderilmesi",
            "TYPE D gorselin yerlestirilmeye gonderilmesi",
        ],
        authority=["HARD_REJECT"],
        upstream=[],
        downstream=["C07", "C10", "C12"],
        implementation_status="DEFINED",
        evidence=["olculdu: ham medyan 1254px -> kesim medyan 299px"],
    ),
    _y(
        id="C08",
        name="Senior Editorial Designer",
        type="HYBRID",
        purpose="Ayni aileye ait ama birbirinin kopyasi olmayan sayfa sistemini kurar.",
        knowledge_required=["03-editorial-design", "05-composition"],
        tools_required=["grid_motoru", "duzen_imzasi"],
        measurements_required=["duzen_imzasi", "ardisik_tekrar", "algisal_benzerlik", "taban_uyumu"],
        inputs=["format_karari", "ritim_plani", "kadraj_yonergesi", "tip_sistemi"],
        outputs=["grid_sartnamesi", "duzen_ailesi", "urun_sayfa_tipleri"],
        acceptance_conditions=[
            "ardisik iki sayfanin duzen imzasi ayni degil",
            "duzen ailesi >= 6 varyant",
            "her varyant ayni grid'den turemis",
        ],
        rejection_conditions=[],
        authority=[],
        upstream=["C04", "C07", "C09A"],
        downstream=["C09B", "C13"],
        implementation_status="PARTIAL",
        evidence=["scripts/katalog_mimari.py ACILIS_DUZENLERI 3 varyant"],
    ),
    _y(
        id="C09A",
        name="Typography Art Director",
        type="HYBRID",
        purpose="Tip sistemini kurar, basliklari kirar, optik ayari yapar.",
        knowledge_required=["06-typography"],
        tools_required=["font_metrik", "sayfa_render"],
        measurements_required=["glif_kapsama", "olcek_orani"],
        vision_required=True,
        llm_required=True,
        inputs=["format_karari", "metin_uzunluk_dagilimi", "grid"],
        outputs=["tip_sistemi", "baslik_kirma_kurallari", "optik_duzeltmeler"],
        acceptance_conditions=[
            "her metin isi bir role eslenmis",
            "not/isaretleme rolu tanimli",
            "turkce glif kapsama tam",
        ],
        rejection_conditions=["tipografik olarak hiyerarsi kurulmamis"],
        authority=["REJECT", "ADVISE"],
        upstream=[],
        downstream=["C08", "C09B"],
        implementation_status="PARTIAL",
        evidence=["katalog_mimari.py TIP sozlugu 10 stil; rol ayrimi ve not rolu yok"],
    ),
    _y(
        id="C09B",
        name="Typography QA Engine",
        type="DETERMINISTIC",
        purpose="Sayfanin basildiginda okunup okunmayacagini olcer.",
        knowledge_required=["06-typography"],
        tools_required=["fonttools", "pymupdf"],
        measurements_required=[
            "satir_uzunlugu", "punto", "dul_yetim", "carpisma",
            "eksik_glif", "guvenli_alan", "tasma", "font_gomme",
        ],
        inputs=["yerlestirilmis_metin_kutulari", "font_metrikleri", "esik_tablosu"],
        outputs=["ihlal_listesi"],
        acceptance_conditions=["ihlal sayisi = 0"],
        rejection_conditions=["herhangi bir ihlal"],
        authority=["HARD_REJECT"],
        upstream=["C08", "C09A"],
        downstream=["C15"],
        implementation_status="DEFINED",
        evidence=["katalog-tasarim.py icinde tek bir denetim islevi yok"],
    ),
    _y(
        id="C10",
        name="Product Photography & Retouch Director",
        type="HYBRID",
        purpose="Kesilmis urunun sahneye ait mi yapistirilmis mi durdugunu karara baglar.",
        knowledge_required=["11-retouch-compositing", "07-color-science"],
        tools_required=["rembg", "pillow", "renk_farki"],
        measurements_required=["delta_e", "kenar_artefakti", "efektif_dpi", "buyutme_bayragi"],
        vision_required=True,
        inputs=["sinif_karari", "ham_fotograf", "kesim_maskesi", "kutu_gercegi_renkleri"],
        outputs=["kesim_kalitesi", "isik_uyumu", "temas_golgesi", "renk_sapmasi_dE"],
        acceptance_conditions=[
            "gövde rengi referanstan delta E esigi icinde",
            "alfa kenarinda halo yok",
            "efektif DPI buyutmeden saglaniyor",
        ],
        rejection_conditions=["kenar artefakti", "isik yonu celiskisi", "buyutmeyle saglanan DPI"],
        authority=["REJECT", "REVISE"],
        upstream=["C07A"],
        downstream=["C12", "C08"],
        implementation_status="PARTIAL",
        evidence=["gorsel-kompozit.py rembg u2net + maske sertlestirme; isik/golge/dE yok"],
    ),
    _y(
        id="C11",
        name="Image Generation Supervisor",
        type="HYBRID",
        purpose="Uretilen sahnenin urunu guclendirip guclendirmedigine karar verir.",
        knowledge_required=["04-product-photography", "05-composition"],
        tools_required=["comfyui_kuyruk_surucusu", "nesne_tespiti", "ocr"],
        measurements_required=["cozunurluk", "sakin_alan_orani", "metin_varligi"],
        vision_required=True,
        inputs=["sanat_yonu_yonergesi", "gorsel-kuyruk/"],
        outputs=["sahne_kodu", "istem", "artefakt_bulgulari", "karar"],
        acceptance_conditions=[
            "sahne cozunurlugu hedef yerlesimde yeterli",
            "uretilen gorselde urun, logo veya metin YOK",
        ],
        rejection_conditions=["sahne urunle yarisiyor", "sahnede nesne/metin var"],
        authority=["REJECT"],
        upstream=["C07"],
        downstream=["C10", "C12"],
        implementation_status="DEFINED",
        evidence=["gorsel-kuyruk klasorleri var, surucu ve kalite kapisi yok"],
    ),
    _y(
        id="C12",
        name="Product Integrity Guardian",
        type="DETERMINISTIC",
        purpose="Sayfadaki urunun gercek urunden farkli olup olmadigini olcer.",
        knowledge_required=["12-product-integrity"],
        tools_required=["pillow", "hash_zinciri"],
        measurements_required=["en_boy_sapmasi", "delta_e", "koken_zinciri", "uretken_model_temasi"],
        inputs=["kaynak_urun_fotografi", "yerlesmis_hali", "islem_gunlugu"],
        outputs=["karar", "koken_zinciri", "ihlal_gerekcesi"],
        acceptance_conditions=[
            "en/boy sapmasi esik altinda",
            "urun pikselleri hicbir uretken modelden gecmemis",
        ],
        rejection_conditions=["herhangi bir butunluk ihlali"],
        authority=["HARD_REJECT"],
        upstream=["C07A", "C10", "C11"],
        downstream=["C15"],
        implementation_status="DEFINED",
        evidence=["koken kaydi sistemde yok"],
    ),
    _y(
        id="C13",
        name="Independent Critic / Red Team",
        type="VISION",
        purpose="Sayfayi ilk kez goren birinin neyi zayif bulacagini soyler.",
        knowledge_required=["15-perceptual-qa"],
        tools_required=["sayfa_render", "yalitim"],
        measurements_required=[],
        vision_required=True,
        llm_required=True,
        inputs=["yalniz_sayfa_goruntuleri"],
        outputs=["kusur_tipi", "bolge", "neden_zayif", "agirlik"],
        acceptance_conditions=["her itiraz taksonomiden bir ada bagli"],
        rejection_conditions=["YUKSEK agirlikli tek itiraz"],
        authority=["REJECT"],
        upstream=["C08"],
        downstream=["C01"],
        implementation_status="DEFINED",
        evidence=["FAZ -1 raporu B03 kart 13"],
    ),
    _y(
        id="C14",
        name="Sales Usability Reviewer",
        type="HYBRID",
        purpose="Temsilcinin gorusmede aradigini bulup bulamayacagini olcer.",
        knowledge_required=["17-sales-usability"],
        tools_required=["sayfa_dizini", "sayfa_render"],
        measurements_required=["cevirme_sayisi", "not_alani_mm2", "fiyat_listesi_konumu"],
        vision_required=True,
        inputs=["sayfa_sirasi", "soru_konu", "saha_senaryosu"],
        outputs=["senaryo", "bulundu_mu", "not_alani_yeterli_mi"],
        acceptance_conditions=[
            "en sik sorularin cevabi esik ici sayfa cevirmede",
            "her urun sayfasinda yazilabilir not alani var",
        ],
        rejection_conditions=["bulunabilirlik esigi karsilanmiyor", "not alani yok"],
        authority=["REJECT"],
        upstream=["C04"],
        downstream=["C01"],
        implementation_status="DEFINED",
        evidence=["FAZ -1 raporu B03 kart 14"],
    ),
    _y(
        id="C15",
        name="Prepress & Print Production Director",
        type="DETERMINISTIC",
        purpose="Dosyanin matbaaya gonderilebilir oldugunu kanitlar.",
        knowledge_required=["14-prepress", "13-print-production", "07-color-science"],
        tools_required=["pymupdf", "fonttools"],
        measurements_required=[
            "tasma", "guvenli_alan", "efektif_dpi", "buyutme_bayragi",
            "font_gomme", "renk_uzayi", "sayfa_olcusu",
        ],
        inputs=["final_pdf", "matbaa_sartnamesi"],
        outputs=["preflight_raporu"],
        acceptance_conditions=["tum kontroller esik icinde"],
        rejection_conditions=["herhangi bir baski engelleyici ihlal"],
        authority=["REJECT", "APPROVE"],
        upstream=["C09B", "C12"],
        downstream=["HUMAN"],
        implementation_status="PARTIAL",
        evidence=["yalniz DPI raporu var ve buyutulmus pikseli sayiyor"],
    ),
    _y(
        id="HUMAN",
        name="Sahip -- final baski onayi",
        type="HUMAN",
        purpose="Fiziksel provayi elinde tutarak tiraji onaylar.",
        knowledge_required=[],
        tools_required=["fiziksel_prova"],
        measurements_required=[],
        human_required=True,
        inputs=["preflight_raporu", "fiziksel_prova"],
        outputs=["baski_emri"],
        acceptance_conditions=["provada kalemle yazilabiliyor", "acik kaliyor", "renkler ambalajla uyusuyor"],
        rejection_conditions=["fiziksel provada herhangi bir kusur"],
        authority=["APPROVE", "HARD_REJECT"],
        upstream=["C15", "C01"],
        downstream=[],
        implementation_status="DEFINED",
        evidence=["hicbir kosulda otomatiklestirilmez"],
    ),
)

_INDEKS = {y.id: y for y in KUTUK}


# --- erisim --------------------------------------------------------------

def kayitlar() -> tuple[Yetenek, ...]:
    return KUTUK


def getir(kimlik: str) -> Yetenek | None:
    return _INDEKS.get(kimlik)


def tipe_gore(tip: str) -> tuple[Yetenek, ...]:
    return tuple(y for y in KUTUK if y.type == tip)


def yetkiye_gore(yetki: str) -> tuple[Yetenek, ...]:
    return tuple(y for y in KUTUK if yetki in y.authority)


def durdurabilenler() -> tuple[Yetenek, ...]:
    """Uretimi fiilen durdurabilen yetenekler."""
    return tuple(y for y in KUTUK if "HARD_REJECT" in y.authority)


# --- dogrulama -----------------------------------------------------------

def _dongu_var_mi(kenarlar: dict[str, Iterable[str]]) -> list[str]:
    """downstream grafiginde dongu arar; bulursa dongudeki dugumleri doner."""
    BEYAZ, GRI, SIYAH = 0, 1, 2
    renk = {k: BEYAZ for k in kenarlar}
    dongu: list[str] = []

    def gez(dugum: str, yol: list[str]) -> bool:
        renk[dugum] = GRI
        for komsu in kenarlar.get(dugum, ()):  # bilinmeyen dugumu atla
            if komsu not in renk:
                continue
            if renk[komsu] == GRI:
                dongu.extend(yol[yol.index(komsu):] + [komsu] if komsu in yol else [komsu])
                return True
            if renk[komsu] == BEYAZ and gez(komsu, yol + [komsu]):
                return True
        renk[dugum] = SIYAH
        return False

    for dugum in kenarlar:
        if renk[dugum] == BEYAZ and gez(dugum, [dugum]):
            break
    return dongu


def dogrula() -> list[str]:
    """Kutugun ic tutarliligini denetler. Bos liste = temiz."""
    sorunlar: list[str] = []
    gorulen: set[str] = set()

    for y in KUTUK:
        if y.id in gorulen:
            sorunlar.append("%s: kimlik tekrar ediyor" % y.id)
        gorulen.add(y.id)

        if y.type not in TIPLER:
            sorunlar.append("%s: gecersiz type %r" % (y.id, y.type))
        if y.implementation_status not in DURUMLAR:
            sorunlar.append("%s: gecersiz status %r" % (y.id, y.implementation_status))
        for yetki in y.authority:
            if yetki not in YETKILER:
                sorunlar.append("%s: gecersiz authority %r" % (y.id, yetki))

        # baglanti butunlugu
        for baglanti, ad in ((y.upstream, "upstream"), (y.downstream, "downstream")):
            for hedef in baglanti:
                if hedef not in _INDEKS:
                    sorunlar.append("%s: %s bilinmeyen kimlige isaret ediyor: %s" % (y.id, ad, hedef))

        # DETERMINISTIC hicbir kosulda model istemez
        if y.type == "DETERMINISTIC" and (y.vision_required or y.llm_required):
            sorunlar.append("%s: DETERMINISTIC yetenek model istiyor" % y.id)

        # olcen ama hicbir seyi degistiremeyen yetenek GATEKEEPER degildir
        if y.measurements_required and not y.authority and y.type == "DETERMINISTIC":
            sorunlar.append("%s: olcuyor ama hicbir yetkisi yok -- GATEKEEPER degil" % y.id)

        # HARD_REJECT yalnizca olcume dayanabilir ya da insan olabilir
        if "HARD_REJECT" in y.authority and not y.measurements_required and y.type != "HUMAN":
            sorunlar.append("%s: HARD_REJECT yetkisi var ama olcumu yok" % y.id)

    dongu = _dongu_var_mi({y.id: y.downstream for y in KUTUK})
    if dongu:
        sorunlar.append("yetki grafiginde dongu: %s" % " -> ".join(dongu))

    return sorunlar


# --- agent theater korumasi ---------------------------------------------

def tiyatro_taramasi() -> list[dict]:
    """Benzersiz yetenek / kanit / yetki ucundan hicbirine sahip olmayan
    kayitlari isaretler. Uyari uretir, karar vermez."""
    bulgular: list[dict] = []

    olcum_sahipleri: dict[str, list[str]] = {}
    girdi_sahipleri: dict[str, list[str]] = {}
    for y in KUTUK:
        for m in y.measurements_required:
            olcum_sahipleri.setdefault(m, []).append(y.id)
        for g in y.inputs:
            girdi_sahipleri.setdefault(g, []).append(y.id)

    for y in KUTUK:
        benzersiz_olcum = any(len(olcum_sahipleri[m]) == 1 for m in y.measurements_required)
        benzersiz_girdi = any(len(girdi_sahipleri[g]) == 1 for g in y.inputs)
        gercek_yetki = bool(set(y.authority) & {"REJECT", "HARD_REJECT", "APPROVE"})

        if not (benzersiz_olcum or benzersiz_girdi or gercek_yetki):
            bulgular.append({
                "id": y.id,
                "uyari": "POTENTIAL_AGENT_THEATER",
                "benzersiz_olcum": benzersiz_olcum,
                "benzersiz_girdi": benzersiz_girdi,
                "gercek_yetki": gercek_yetki,
            })
    return bulgular


# --- ozet ----------------------------------------------------------------

def ozet() -> dict:
    sayim_tip = {t: len(tipe_gore(t)) for t in TIPLER}
    sayim_durum: dict[str, int] = {d: 0 for d in DURUMLAR}
    for y in KUTUK:
        sayim_durum[y.implementation_status] += 1
    return {
        "toplam": len(KUTUK),
        "tip": sayim_tip,
        "durum": sayim_durum,
        "durdurabilen": [y.id for y in durdurabilenler()],
        "dogrulama_sorunlari": dogrula(),
        "tiyatro_uyarilari": tiyatro_taramasi(),
    }


def json_dok() -> str:
    return json.dumps([y.sozluk() for y in KUTUK], ensure_ascii=False, indent=1)


if __name__ == "__main__":
    import sys

    if "--json" in sys.argv:
        print(json_dok())
    else:
        o = ozet()
        print("KATALOG YETENEK KUTUGU")
        print("  toplam          : %d" % o["toplam"])
        print("  tip dagilimi    : %s" % o["tip"])
        print("  durum dagilimi  : %s" % o["durum"])
        print("  uretimi durduran: %s" % ", ".join(o["durdurabilen"]))
        if o["dogrulama_sorunlari"]:
            print("  SORUNLAR:")
            for s in o["dogrulama_sorunlari"]:
                print("    - %s" % s)
        else:
            print("  dogrulama       : TEMIZ")
        if o["tiyatro_uyarilari"]:
            print("  TIYATRO UYARISI:")
            for b in o["tiyatro_uyarilari"]:
                print("    - %s" % b)
        else:
            print("  agent theater   : uyari yok")
