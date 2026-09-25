#!/usr/bin/env python3
"""Basin/itibar taramasi — marka adinin TUM yazim varyantlariyla.

🔴 VARYANTLAR ELLE YAZILMAZ, URETILIR. Sahip 22.09.2026: "SEO sorunu
nedeniyle bulamamis olabilirsin; lcarlie / l'carlie / lcarlie' tarzi cok
fonksiyonlu aranmasi lazim." Haklı çıktı: arama sonucunda gecen gercek
yazim **L'CARLİÉ** idi -- Turkce buyuk İ ile -- ve benim elle yazdigim
sekiz varyantin hicbirinde yoktu.

Marka adi su eksenlerde degisiyor:
  apostrof : '  ’  ʼ  (yok)  (bosluk)  -
  E harfi  : É  E
  I harfi  : I  İ
  buyuk/kucuk farki aramada onemsiz, uretilmez.

🔴 GOOGLE NEWS KULLANILMAZ. Olculdu: sekiz varyantin hepsinde 0 haber
dondurdu, oysa haberler VAR (ankarakenthaber.com). Google News yerel ve
sektorel siteleri indekslemiyor. Grounded arama (Gemini + Google Search)
ayni sorularda haberleri buldu. "Kaynak bos dondu" ile "o kaynak bu
icerigi hic gormuyor" ayri seylerdir.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "kb", "/opt/lcarlie/jarvis-phase2/scripts/kreatif-brief.py")
kb = importlib.util.module_from_spec(_spec)
sys.argv = ["itibar-tara"]
_spec.loader.exec_module(kb)

from jarvis import providers  # noqa: E402
from jarvis.compliance import review as uyum_denetimi  # noqa: E402

APOSTROFLAR = ["'", "’", "ʼ", "", " ", "-"]


def ad_varyantlari(govde_sol: str, govde_sag: str) -> list[str]:
    """L + apostrof + CARLIE ekseninde tum yazimlar."""
    cikti: list[str] = []
    for ap in APOSTROFLAR:
        for e in ("É", "E"):
            for i in ("I", "İ"):
                sag = govde_sag.replace("É", e).replace("I", i)
                cikti.append(f"{govde_sol}{ap}{sag}")
    # Tekillestir, sirayi koru
    return list(dict.fromkeys(cikti))


MARKA_VARYANTLARI = ad_varyantlari("L", "CARLIÉ")
DIGER_TERIMLER = ["Lemos Medikal", "Lemos Medikal L'CARLIE"]


# --------------------------------------------------------------------------
# KİŞİ ADLARI — şirket yetkilileri de itibar kapsamındadır
# --------------------------------------------------------------------------
# 🔴 Sahip 22.09.2026: "ayrıca Murat Özer Yıldız, Muharrem Murat Yıldız gibi
# isimleri de araştır." Kurumsal itibar yalnız marka adıyla ölçülmez;
# yetkililer hakkında çıkan haber de markaya yazılır.
#
# 🔴 KİŞİ ADINDA DA VARYANT SORUNU VAR ve marka adından daha kötüsü:
# Türkçe karakterler haber sitelerinde sıklıkla ASCII'ye düşürülüyor
# (Yıldız -> Yildiz, Özer -> Ozer). Ad sırası da değişiyor
# (Muharrem Murat Yıldız / Murat Yıldız / M. Murat Yıldız).
# Elle liste yazmak yerine aynı üretim disiplini uygulanır.
KISI_GOVDELERI = [
    "Murat Özer Yıldız",
    "Muharrem Murat Yıldız",
    "Özer Yıldız",
    "Murat Yıldız",
]

_TR_ASCII = str.maketrans({"ı": "i", "İ": "I", "ö": "o", "Ö": "O",
                           "ü": "u", "Ü": "U", "ş": "s", "Ş": "S",
                           "ğ": "g", "Ğ": "G", "ç": "c", "Ç": "C"})


def kisi_varyantlari(adlar: list[str]) -> list[str]:
    """Her ad için Türkçe ve ASCII yazımı; sıra korunur, tekilleşir."""
    cikti: list[str] = []
    for ad in adlar:
        cikti.append(ad)
        ascii_ad = ad.translate(_TR_ASCII)
        if ascii_ad != ad:
            cikti.append(ascii_ad)
    return list(dict.fromkeys(cikti))


KISI_ADLARI = kisi_varyantlari(KISI_GOVDELERI)


def grounded_ara(soru: str, anahtar: str) -> tuple[str, list[str]]:
    try:
        return kb._grounded(soru, anahtar)
    except Exception as hata:  # noqa: BLE001
        print(f"  arama hatası: {str(hata)[:90]}", file=sys.stderr)
        return "", []


BASLIK_KALIBI = re.compile(r"[\"“”'‘’]([^\"“”'‘’\n]{18,140})[\"“”'‘’]")
SITE_KALIBI = re.compile(r"\b([a-z0-9-]+\.(?:com|net|org|com\.tr|gov\.tr))\b")


# --------------------------------------------------------------------------
# ÖZEL İSİM İSTİSNASI — kelimeye değil ANLAMA bakılır
# --------------------------------------------------------------------------
# 🔴 SAHİP DÜZELTMESİ, 22.09.2026: *"Böyle kelime bazlı olmaz ki, anlam
# bazlı bakılması lazım. Oradaki Şifa Köprüsü etkinliğin adı; senin bunu
# yasaklı demen çok yanlış."* Haklı.
#
# Tarama "Şifa Köprüsü Forumu'nda L'CARLİÉ Dikkat Çekti" başlığını
# `şifa` yasak kelimesi geçtiği için RİSKLİ işaretledi. Oysa bu bir
# ETKİNLİK ADI -- özel isim, ürünümüz hakkında bir iddia değil.
#
# Bu, kılavuzun kendi kuralının aynısı: "Uyarı cümlesi iddia değildir,
# içinde 'yara' geçmesi önemli değil." Yasak olan KELİME değil, kelimenin
# ürüne YÜKLEDİĞİ İDDİA. Bir etkinliğe katılmak iddia değildir.
#
# Uygulama: yasak sözcük ÖZEL İSİM parçasıysa (büyük harfle başlıyor ve
# yanında kurum/etkinlik belirten bir sözcük var) bayrak kaldırılmaz.
OZEL_ISIM_BAGLAMI = (
    "forum", "foruma", "forumu", "forumunda", "kongre", "kongresi",
    "zirve", "zirvesi", "festival", "festivali", "fuar", "fuari", "fuarı",
    "dernek", "derneği", "vakıf", "vakfı", "platform", "platformu",
    "köprüsü", "köprüsünde", "buluşma", "buluşması", "ödül", "ödülü",
    "panel", "paneli", "sempozyum", "kurultay", "hastane", "hastanesi",
    "merkezi", "enstitü", "enstitüsü", "üniversite", "üniversitesi",
)


def ozel_isim_mi(cumle: str, sozcuk: str) -> bool:
    """Yasak sözcük bir ÖZEL İSMİN parçası mı?

    İki koşul birlikte aranır:
      1. Sözcük cümlede BÜYÜK harfle başlıyor (Şifa, Doğa...)
      2. Yakınında kurum/etkinlik belirten bir sözcük var (Forum, Köprüsü…)
    Tek başına büyük harf yetmez: cümle başındaki her sözcük büyüktür.
    """
    if not sozcuk:
        return False
    duz = cumle.casefold()
    kok = sozcuk.casefold()
    yer = duz.find(kok)
    if yer < 0:
        return False
    # 1) özgün metinde büyük harfle mi yazılmış
    ozgun = cumle[yer:yer + len(sozcuk)]
    if not ozgun[:1].isupper():
        return False
    # 2) çevresinde kurum/etkinlik sözcüğü var mı (±60 karakter)
    pencere = duz[max(0, yer - 60): yer + len(kok) + 60]
    return any(b in pencere for b in OZEL_ISIM_BAGLAMI)


# --------------------------------------------------------------------------
# TÜRKÇE VARLIK TANIMA (NER) — anlam bazlı denetim
# --------------------------------------------------------------------------
# 🔴 SAHİP 22.09.2026: *"Böyle kelime bazlı olmaz ki, anlam bazlı bakılması
# lazım. Oradaki Şifa Köprüsü etkinliğin adı; senin bunu yasaklı demen çok
# yanlış."* Ardından: *"Bunun için repo bul, düzgün anlaşılmıyor."*
#
# İlk çözümüm sezgiseldi (büyük harf + yakında "forum/köprüsü" gibi sözcük).
# Çalışıyordu ama kırılgandı: listede olmayan bir etkinlik türü gelince
# yine yanlış bayrak kaldıracaktı.
#
# Doğru araç VARLIK TANIMA. Model bir sözcük öbeğinin KURUM/KİŞİ/YER adı
# olduğunu dilbilgisel olarak işaretliyor; yasak sözcük o öbeğin İÇİNDEYSE
# ürün hakkında iddia değil, isimdir.
#
# Ölçüldü (savasy/bert-base-turkish-ner-cased, 6/6 doğru):
#   "Şifa Köprüsü Forumu'nda L'CARLİÉ Dikkat Çekti"
#       -> Şifa Köprüsü Forumu [ORG]  => 'şifa' varlık içinde, iddia DEĞİL
#   "Sağlık Vakfı Şifa Ödülü'nü aldı"
#       -> Sağlık Vakfı Şifa Ödülü [ORG]  => iddia DEĞİL
#   "Ürün cilde şifa verir"       -> varlık yok  => İDDİA
#   "Kremin şifalı etkisi..."     -> varlık yok  => İDDİA
# Hız: model yükleme 8,4 sn (bir kez) + cümle başına 0,03-0,14 sn.
#
# 🔴 MODEL YOKSA SESSİZ KALMAZ. Yüklenemezse sezgisel kurala düşer ve bunu
# LOG'a yazar -- "denetlendi" görünüp aslında denetlenmemiş olmaz.
NER_MODELI = os.environ.get("ITIBAR_NER_MODELI",
                            "savasy/bert-base-turkish-ner-cased")
_ner_hattı = None
_ner_denendi = False


def _ner():
    """NER hattını tembel yükler. Yoksa None döner (sezgisel yola düşülür)."""
    global _ner_hattı, _ner_denendi
    if _ner_denendi:
        return _ner_hattı
    _ner_denendi = True
    try:
        from transformers import pipeline
        _ner_hattı = pipeline("ner", model=NER_MODELI,
                              aggregation_strategy="simple")
        print(f"  NER hazır: {NER_MODELI}", file=sys.stderr)
    except Exception as hata:  # noqa: BLE001
        print(f"  🔴 NER YÜKLENEMEDİ ({str(hata)[:90]}) — sezgisel kurala "
              "düşülüyor, özel isim ayrımı zayıf olacak", file=sys.stderr)
        _ner_hattı = None
    return _ner_hattı


def varlik_icinde_mi(cumle: str, sozcuk: str) -> bool:
    """Yasak sözcük bir KURUM/KİŞİ/YER adının içinde mi (NER ile)."""
    hat = _ner()
    if hat is None or not sozcuk:
        return ozel_isim_mi(cumle, sozcuk)      # sezgisel yedek
    yer = cumle.casefold().find(sozcuk.casefold())
    if yer < 0:
        return False
    try:
        for v in hat(cumle):
            if v.get("start", -1) <= yer < v.get("end", -1):
                return True
    except Exception:  # noqa: BLE001
        return ozel_isim_mi(cumle, sozcuk)
    return False


def mevzuat_bayraklari(metin: str) -> list[str]:
    """🔴 Basinda cikan metin de iddia sayilabilir; yasak ifade RISKTIR.

    AMA ozel isim istisnasi uygulanir: etkinlik/kurum adindaki sozcuk
    urun hakkinda bir iddia degildir. Bkz. OZEL_ISIM_BAGLAMI.
    """
    karar = uyum_denetimi(metin)
    bayraklar = []
    for b in (karar.blocked or []):
        sozcuk = str(getattr(b, "matched", "") or "")
        if varlik_icinde_mi(metin, sozcuk):
            continue
        bayraklar.append(sozcuk)
    return bayraklar


# 🔴 MODELIN KENDI YORUMU BASIN METNI DEGILDIR.
# Grounded arama ham haber metnini degil, modelin OZETINI donduruyor. Ozet
# icinde modelin kendi aciklamalari da var. Olculdu 22.09.2026: mevzuat
# kapisi "kanser" bayragi kaldirdi ama cumle su idi:
#   "Eger bahsettiginiz konu baska bir kozmetik markasiyla ... kanser riskini"
# Bu bizim basinimiz degil, modelin sorumuza verdigi kosullu aciklama.
# Boyle bir bayragi "basinda hakkimizda kanser dendi" diye raporlamak,
# olmayan bir krizi gundeme sokardi.
ANLATICI_KALIBI = re.compile(
    r"(bahsettiğiniz|sorduğunuz|sorunuz|belirtmek gerekir|"
    r"^eğer\b|^ancak\b|^not:|^özetle|^kısacası|"
    r"bulunmamaktadır|bilgi bulunamadı|kaynaklarda yer almamaktadır|"
    r"tarafımca|yapay zekâ|varsayarak)",
    re.IGNORECASE)


def anlatici_mi(cumle: str) -> bool:
    return bool(ANLATICI_KALIBI.search(cumle.strip()))


# --------------------------------------------------------------------------
# ATIF KAPISI — bu haber gerçekten BİZİM hakkımızda mı?
# --------------------------------------------------------------------------
# 🔴 AD BENZERLİĞİ BİZİM HABERİMİZ DEĞİLDİR. Ölçüldü 22.09.2026: kişi adı
# araması, aynı adı taşıyan BAŞKA kişiler hakkındaki haberleri getirdi —
# yolsuzluk soruşturması, kayıp kişi dosyası, bir cerrah, bir cinayet
# haberi. Hepsi "Murat Yıldız" / "Özer Yıldız" adını taşıyordu ve sistem
# bunları şirketin itibar kaydına yazdı.
#
# Yaygın bir Türkçe ad için bu kaçınılmaz. Kural:
#   MARKA adı  -> tek başına yeter (ayırt edici)
#   KİŞİ adı   -> ancak ŞİRKET BAĞLAMIYLA birlikte sayılır
#
# 🔴 VE FİLTRE TEK YERDE DEĞİL, VERİ GİREN HER YOLDA OLMALI. İlk sürümde
# yalnız cümle yolunda vardı; başlık ayıklama yolu süzgeçsizdi ve alakasız
# haberler oradan girdi. Kapalı bir kapı ile açık bir pencere, kapısız
# odadan farksızdır.
SIRKET_BAGLAMI = ("lemos", "carlie", "carlié", "kozmetik", "dermokozmetik",
                  "krem", "bakim", "bakım", "cilt", "marka")


def bize_ait_mi(metin: str) -> bool:
    duz = (metin or "").casefold()
    marka_var = (any(a.casefold() in duz for a in MARKA_VARYANTLARI)
                 or "lemos" in duz)
    kisi_var = any(a.casefold() in duz for a in KISI_ADLARI)
    baglam_var = any(b in duz for b in SIRKET_BAGLAMI)
    return marka_var or (kisi_var and baglam_var)


def cumle_cumle_denetle(metin: str) -> list[dict]:
    """Basin metnini CUMLE CUMLE mevzuattan gecir.

    🔴 BASLIK AYIKLAMAK YETMEDI. Ilk surum tirnak icindeki basliklari
    ariyordu ve uc aramadan yalnizca 2 baslik cikardi -- oysa asil risk
    baslikta degil METINDE: "sert kimyasallardan arindirilmis" ifadesi
    govde metninde geciyordu ve yasak ("kimyasallardan arindirmak",
    katalog kilavuzu).
    🔴 Basinda cikan cumle de bize ait sayilabilir: Ticari Reklam
    Yonetmeligi m.8 ispat kulfetini REKLAMVERENE yukluyor ve tanitim
    yazisi reklamdir.
    """
    # BIZE_AIT_MI — baska sirketin haberini bizim riskimiz sanma.
    # Olculdu 22.09.2026: grounded arama, genis sorgu yuzunden BASKA bir
    # markanin (sac duzlestirici / Arizona Bassavciligi) kanser davasini
    # getirdi ve mevzuat kapisi dogru sekilde "kanser" bayragi kaldirdi.
    # Tespit dogruydu, OZNE yanlisti. Bir cumleyi bize yazabilmek icin o
    # cumlenin bizden bahsetmesi gerekir.
    # 🔴 AD BENZERLIGI BIZIM HABERIMIZ DEGILDIR.
    # Olculdu 22.09.2026: "Ozer Yildiz" aramasi, ayni adi tasiyan BASKA
    # bir kisi hakkindaki yolsuzluk sorusturmasi haberlerini getirdi ve
    # sistem bunlari bizim itibar kaydimiza yazdi. Yaygin bir Turkce ad
    # icin bu kacinilmaz.
    # Kural: KISI adi tek basina yetmez; ayni cumlede SIRKET BAGLAMI da
    # gecmeli. Marka adi kendi basina ayirt edici oldugu icin ona bu sart
    # uygulanmaz.
    # 🔴 Bu kural ARTIK `bize_ait_mi()` icinde ve modul duzeyindeki
    # SIRKET_BAGLAMI'ndan okunuyor. Burada duran yerel kopya olculdu
    # (25.09.2026) ve modul duzeyindekinden FARKLIYDI: "cilt" ve "marka"
    # yalniz modul surumunde vardi. Hicbir yerde kullanilmadigi icin fark
    # da gorunmuyordu -- yani birileri bu listeyi duzeltse SESSIZCE hicbir
    # sey degismezdi. Tek kaynak birakildi.
    bulgular = []
    for cumle in re.split(r"(?<=[.!?])\s+|\n", metin):
        cumle = cumle.strip(" -*•\t")
        if len(cumle) < 25 or anlatici_mi(cumle):
            continue
        if not bize_ait_mi(cumle):
            continue
        bayrak = mevzuat_bayraklari(cumle)
        if bayrak:
            bulgular.append({"cumle": cumle[:300], "bayrak": bayrak})
    return bulgular


def db_yaz(kayitlar: list[dict]) -> int:
    """Bulgulari core.basin_bahsi'ye yazar. Ayni baslik+site tekrar yazilmaz."""
    import subprocess

    if not kayitlar:
        return 0
    # 🔴 ON CONFLICT ayni komutta ayni satiri IKI KEZ goremez; once bizim
    # tekillestirmemiz gerekiyor. Ilk surum bu yuzden hicbir sey yazamadi.
    gorulen: set[tuple[str, str]] = set()
    tekil: list[dict] = []
    for k in kayitlar:
        anahtar = (str(k.get("baslik"))[:900], str(k.get("kaynak_site")))
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        tekil.append(k)
    kayitlar = tekil

    satirlar = []
    for k in kayitlar:
        def q(x: object) -> str:
            return "'" + str(x or "").replace("'", "''")[:900] + "'"
        bayrak = k.get("mevzuat_bayragi") or []
        dizi = ("ARRAY[" + ",".join(q(b) for b in bayrak) + "]::text[]"
                if bayrak else "NULL")
        satirlar.append(
            f"({q(k['baslik'])},{q(k['kaynak_site'])},{q(k['arama_terimi'])},"
            f"{q(k.get('ozet'))},{dizi},{q(k['mevzuat_durumu'])})")
    sql = (
        "INSERT INTO core.basin_bahsi "
        "(baslik,kaynak_site,arama_terimi,ozet,mevzuat_bayragi,mevzuat_durumu) "
        "VALUES " + ",".join(satirlar) +
        " ON CONFLICT (baslik,kaynak_site) DO UPDATE SET "
        "guncelleme=clock_timestamp(), mevzuat_bayragi=EXCLUDED.mevzuat_bayragi,"
        " mevzuat_durumu=EXCLUDED.mevzuat_durumu;")
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres",
         "psql", "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode("utf-8"), capture_output=True, timeout=120)
    if r.returncode != 0:
        print(f"  DB yazilamadi: {r.stderr.decode()[:200]}", file=sys.stderr)
        return 0
    return len(kayitlar)


def main() -> int:
    anahtar = providers.load_env().get("GEMINI_API_KEY")
    if not anahtar:
        print("GEMINI_API_KEY yok; tarama yapılamaz", file=sys.stderr)
        return 1

    print(f"üretilen marka varyantı: {len(MARKA_VARYANTLARI)} · "
          f"kişi varyantı: {len(KISI_ADLARI)}")
    print("  " + " · ".join(MARKA_VARYANTLARI[:8]) + " …")

    # 🔴 Her varyant icin ayri arama YAPILMAZ: 36 varyant x arama = israf ve
    # hiz siniri. Varyantlar TEK soruya konur; arama motoru zaten esdeger
    # yazimlari birlikte degerlendiriyor. Olculdu: tek birlesik sorgu
    # ankarakenthaber sonuclarini getiriyor.
    sorular = [
        (" veya ".join(MARKA_VARYANTLARI[:10])
         + " kozmetik markasi hangi haber sitelerinde yer aldi? "
           "Haber basligini ve siteyi yaz.", "marka_varyantlari"),
        ("Lemos Medikal L'CARLIE dermokozmetik basin haberleri ve "
         "tanitim yazilari hangi sitelerde yayimlandi?", "lemos_medikal"),
        ("L'CARLIE kozmetik hakkinda cikan haberlerde hangi iddialar ve "
         "ifadeler kullanildi?", "iddia_denetimi"),
        # 🔴 Kisi adlari: yetkili hakkindaki haber de markaya yazilir.
        (" veya ".join(KISI_ADLARI)
         + " hakkinda haber sitelerinde ne yer aldi? Haber basligini ve "
           "siteyi yaz.", "kisi_adlari"),
        ("Lemos Medikal yoneticisi Murat Yildiz kozmetik sektorunde hangi "
         "etkinliklerde ve haberlerde yer aldi?", "yonetici_etkinlik"),
    ]

    bulgular: list[dict] = []
    for soru, terim in sorular:
        metin, kaynaklar = grounded_ara(soru, anahtar)
        if not kaynaklar:
            print(f"  {terim:<20} kaynak dönmedi")
            continue
        siteler = []
        for k in kaynaklar:
            e = SITE_KALIBI.search(k.lower())
            siteler.append(e.group(1) if e else k[:60])
        basliklar = [b.strip() for b in BASLIK_KALIBI.findall(metin)]
        ihlaller = cumle_cumle_denetle(metin)
        print(f"  {terim:<20} {len(kaynaklar)} kaynak · "
              f"{len(basliklar)} başlık · {len(ihlaller)} riskli cümle")
        ana_site = siteler[0] if siteler else "?"
        for i, b in enumerate(basliklar):
            if not bize_ait_mi(b):
                continue
            bayrak = mevzuat_bayraklari(b)
            bulgular.append({
                "baslik": b[:300],
                "kaynak_site": siteler[i % len(siteler)] if siteler else "?",
                "arama_terimi": terim,
                "ozet": metin[:400],
                "mevzuat_bayragi": bayrak,
                "mevzuat_durumu": "RISKLI" if bayrak else "TEMIZ",
            })
        for ih in ihlaller:
            bulgular.append({
                "baslik": ih["cumle"],
                "kaynak_site": ana_site,
                "arama_terimi": terim + "/cumle",
                "ozet": "Basın metninde geçen ifade; mevzuat kapısına takıldı.",
                "mevzuat_bayragi": ih["bayrak"],
                "mevzuat_durumu": "RISKLI",
            })

    print()
    print(f"toplam bulgu: {len(bulgular)}")
    riskli = [b for b in bulgular if b["mevzuat_durumu"] == "RISKLI"]
    if riskli:
        print(f"🔴 mevzuata takılan başlık: {len(riskli)}")
        for b in riskli:
            print(f"   {b['mevzuat_bayragi']} <- {b['baslik'][:90]}")

    yazilan = db_yaz(bulgular)
    print(f"veritabanına yazılan: {yazilan}")
    Path("/tmp/itibar-bulgular.json").write_text(
        json.dumps(bulgular, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
