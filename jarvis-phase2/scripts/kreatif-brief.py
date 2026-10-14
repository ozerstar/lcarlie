#!/usr/bin/env python3
"""KREATİF BRIEF — tek ürün için uçtan uca brifing ve görsel üretim paketi.

NEDEN VAR
Eski yol `agency._concepts()` idi: ANGLES adında ÜÇ SABİT ŞABLON var, içine
`{brand}` yazılıp geri veriliyordu. Ölçüldü — HYDRAVIE için çıkan üç konsept
("Bakım Rutini", "Kendine Ayırdığın An", "Açık ve Bakım Odaklı") üründen tek
bir şey söylemiyor: ne içindeki madde, ne fiyatı, ne rakibin ne dediği, ne de
alıcının itirazı. Aynı üç metin her ürün için aynı çıkar. O bir kreatif motor
değil, mail-merge'dü.

Bu hat altı katmanı sırayla üretir ve her katman bir ÖNCEKİNİ girdi alır:

  1. ÜRÜN GERÇEĞİ        şirket ölçümü   (CompanyMemory → mart.urun_karti)
  2. KENDİ GEÇMİŞİMİZ    şirket ölçümü   (mart.kreatif_performans) + TUTARLILIK
  3. RAKİP               DIŞ KAYNAK/iddia (grounded arama, kaynak URL'li)
  4. KONUMLANDIRMA       model çıkarımı, 1-3'e dayalı, mevzuat kapısından geçer
  5. GÖRSEL PROMPTLARI   model + KOD ZORLAMASI
  6. RED TEAM            model, TÜRKÇE ve kreatife dair

🔴 KATMAN 5 — AI GÖRSEL YASAĞI KODDA ZORLANIR, İSTEMDE DEĞİL
Sahibin kararı (14.09.2026): "Kural ürünün karede olmaması değil: AMBALAJ
AI'YA YENİDEN TASARLATILMAZ. Şişe/kutu görseli ve üstündeki yazılar
değişmeyecek, gerçek çekim fotoğrafı direkt öyle kullanılacak." Ayrıca
Türkçe metin image modeline yazdırılmaz.

Bunun sonucu: image modeline giden istem YALNIZ SAHNE/ARKA PLAN üretir.
Ürün, logo ve tüm yazı, gerçek dosyalardan Pillow ile üstüne dizilir.
YASAK CÜMLESİ HER İSTEME KOD TARAFINDAN EKLENİR (`_istemi_muhurle`) —
modelden "şunu da yaz" diye istenmez, çünkü model onu unutabilir; kod unutmaz.

Çıkış: 0=brief üretildi · 1=hata · 2=ürün bulunamadı · 3=kısmi (rakip yok)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis import providers  # noqa: E402
from jarvis.compliance import review as uyum_denetimi  # noqa: E402
from jarvis.memory import CompanyMemory  # noqa: E402
from jarvis.model_layer import ModelRouter  # noqa: E402
from jarvis.model_layer import ModelUnavailable as ModelUnavailable_  # noqa: E402

CIKTI_KOK = Path(os.environ.get("KREATIF_BRIEF_DIR", str(KOK / "state" / "kreatif-brief")))
ARAMA_MODELI = os.environ.get("KREATIF_ARAMA_MODELI", "gemini-3.5-flash-lite")

# --------------------------------------------------------------------------
# 1) ÜRÜN GERÇEĞİ
# --------------------------------------------------------------------------

# mart.urun_karti.aciklama_duz Wix'ten HTML kaçışlı gelir (&amp; &nbsp; &#39;).
# Ham bırakılırsa bu diziler modele "&amp;" olarak gider ve metne sızar.
_KACIS = (("&amp;", "&"), ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"'),
          ("&lt;", "<"), ("&gt;", ">"))


def _duzelt(metin: str) -> str:
    for eski, yeni in _KACIS:
        metin = metin.replace(eski, yeni)
    return re.sub(r"\s{2,}", " ", metin).strip()


KUTU_DIZINI = Path(os.environ.get("KREATIF_KUTU_DIZINI", str(KOK / "varliklar" / "kutu-gercegi")))


def kutu_gercegi(ad: str) -> dict:
    """Onaylı kutu metninden KULLANIM · UYARILAR · INCI.

    🔴 NEDEN VAR. Ölçüldü (21.09.2026): bu hat ürün gerçeği olarak yalnız Wix
    site açıklamasını görüyordu. Oysa kendi istemi "alıcı itirazının cevabı
    ürün kaydındaki İÇERİK ve KULLANIM bilgisinden kurulur; elde bilgi yoksa o
    itirazı listeye HİÇ ALMA" diyor. Yani hat bu bilgiyi istiyordu, kimse
    vermemişti; sonuç, itirazların sessizce elenmesiydi.

    🔴 KUTU TANIMI BİLEREK ALINMAZ. Kutu metnindeki ürün tanımı pazarlama
    metnidir ve mevzuat temizliğinden geçmemiştir (EASYCOMB kutusu: "saçları
    beslerken", "saç derisinin doğal dengesini korumaya destek olur" -- aynı
    ürünün canlı site metni bu ifadeleri 13.09.2026'da ÇIKARMIŞ). Tanımı
    buradan alırsak o temizliği geri almış oluruz. Tanım Wix'ten gelir.

    🔴 ETKİ TABLOSU HİÇ YOK. Kutu .docx'lerinin sonundaki bileşen/etki
    tabloları yasak iddia dolu ("Dolaşımı uyarır", "Hormon dengeleyici",
    "Antimikrobiyal"). Bunlar urun_metni'ne girseydi FELAKET olurdu: aşağıdaki
    dayanak_kapisi() bir cümleyi "ürün kaydında geçiyor mu" diye denetliyor --
    tablo metne girseydi model "antimikrobiyal" yazar ve kapı ONAYLARDI.
    Ayıklama `kutu-gercegi-cikar.py` içinde izin listesiyle yapılır ve orada
    ayrı bir kirlilik kapısı vardır.
    """
    if not KUTU_DIZINI.is_dir():
        return {}
    hedef = katla(ad).replace(" ", "")
    adaylar = sorted(p for p in KUTU_DIZINI.glob("*.json") if p.stem != "_hepsi")
    for yol in adaylar:
        anahtar = katla(yol.stem).replace(" ", "")
        if anahtar and (anahtar in hedef or hedef in anahtar):
            try:
                return json.loads(yol.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as hata:
                print(f"  kutu gerçeği okunamadı ({yol.name}): {hata}", file=sys.stderr)
                return {}
    return {}


URUN_KITLE_DOSYASI = Path(os.environ.get(
    "KREATIF_URUN_KITLE", str(KOK / "varliklar" / "urun-kitle.json")))


def urun_kitlesi(ad: str) -> dict:
    """Ürünün GERÇEK alıcısı ve araştırma kategorileri.

    🔴 ÜRÜN ADI KİMİN ALDIĞINI BİLMEZ. Bu hat kategoriyi ürün adından
    türetiyordu (`ad.split("|")[-1]`). EASYCOMB'un adı "Bebek ve Çocuklar
    İçin Saç Bakım Spreyi" -- dolayısıyla 11 araştırma açısı, Ad Library
    araması, kanca havuzu ve senaryolar hepsi BEBEK pazarına kuruldu.
    Oysa sahip 21.09.2026'da söyledi: ürünü ağırlıklı olarak YETİŞKİNLER
    alıyor.

    Tek bir yanlış kategori dizesi bütün araştırma zincirini yanlış pazara
    çeviriyor ve hiçbir yerde hata vermiyor -- brief dolu ve tutarlı
    görünüyor, sadece yanlış kişiye konuşuyor.

    🔴 ETİKET DEĞİŞMEZ. Gerçek alıcı yetişkin olsa bile kutudaki "bebek ve
    çocukların hassas saç yapısı için geliştirilmiştir" cümlesi yerinde
    kalır; değişen yalnız reklamın KİME konuştuğudur.
    """
    try:
        veri = json.loads(URUN_KITLE_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    hedef = katla(ad).replace(" ", "")
    for anahtar, kayit in veri.items():
        if anahtar.startswith("_") or not isinstance(kayit, dict):
            continue
        a = katla(anahtar).replace(" ", "")
        if a and (a in hedef or hedef in a):
            return kayit
    return {}


def urun_gercegi(hafiza: CompanyMemory, arama: str) -> dict | None:
    """Ürünü adından bulur. Bulamazsa None — uydurulmuş ürün brief'i yazılmaz.

    🔴 İKİ SORGU BİRLEŞTİRİLİR. Ölçüldü: `urun_bilgi` uzun açıklamayı taşır
    ama `birim_maliyet` alanını TAŞIMAZ; `urun_karti` maliyeti taşır. Tek
    sorguyla gidildiğinde maliyet None kaldı, marj hesaplanamadı ve
    maliyetin altına düşen satışlar SESSİZCE elendi -- HYDRAVIE'de 6 Haziran'da
    840 TL indirimle 300 TL'ye satılan, 400 TL'ye mal olan bir satış vardı ve
    rapora hiç girmedi. Eksik alan burada sessiz değil, birleştirilerek kapanır.
    """
    hedef = katla(arama)
    birlesik: dict | None = None
    for sorgu in ("urun_bilgi", "urun_karti"):
        try:
            kayitlar = hafiza._fetch(sorgu).records
        except Exception as hata:  # noqa: BLE001
            print(f"  {sorgu}: okunamadı ({str(hata)[:80]})", file=sys.stderr)
            continue
        for kayit in kayitlar:
            if hedef not in katla(str(kayit.get("urun_adi") or "")):
                continue
            if birlesik is None:
                birlesik = dict(kayit)
            else:
                # Dolu alan boş alanı ezmez; ilk sorgunun değeri korunur.
                for anahtar, deger in kayit.items():
                    if birlesik.get(anahtar) in (None, "") and deger not in (None, ""):
                        birlesik[anahtar] = deger
            break
    if birlesik is not None:
        birlesik["aciklama_duz"] = _duzelt(str(birlesik.get("aciklama_duz") or ""))
    return birlesik


def katla(metin: str) -> str:
    """Türkçe güvenli karşılaştırma anahtarı.

    🔴 `.lower()` KULLANILMAZ: Türkçe'de I→ı dönüşümü "HYDRAVIE" ile
    "Hydravie"yi bile ayırabiliyor. Aksan da sökülür ki "L’CARLIÉ" ile
    "L'CARLIE" aynı anahtara insin — tutarlılık denetimi bunu AYRICA
    kontrol eder, burada sadece ürün eşleşmesi için düzleştiriyoruz.
    """
    duz = unicodedata.normalize("NFKD", metin)
    duz = "".join(c for c in duz if not unicodedata.combining(c))
    return duz.casefold().replace("’", "'").replace("i̇", "i")


def _sayi(deger: object) -> float | None:
    try:
        return float(deger)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def urun_ozeti(u: dict, satislar: list[dict]) -> dict:
    """Modele gidecek sıkıştırılmış ürün gerçeği. Her alan ÖLÇÜMDÜR."""
    wix = _sayi(u.get("wix_satis"))
    maliyet = _sayi(u.get("birim_maliyet"))
    marj = None
    if wix is not None and maliyet is not None and wix:
        marj = round((wix - maliyet) / wix * 100, 1)
    return {
        "urun_adi": u.get("urun_adi"),
        "sku": u.get("sku"),
        "wix_fiyat_tl": wix,
        "trendyol_fiyat_tl": _sayi(u.get("trendyol_satis")),
        "birim_maliyet_tl": maliyet,
        "brut_marj_yuzde": marj,
        "wix_stok": u.get("wix_stok"),
        "yayinda": u.get("wix_yayinda"),
        "aciklama": u.get("aciklama_duz", "")[:2200],
        "olculen_satis_adedi": len(satislar),
        "satis_detay": [
            {"gun": s.get("gun"), "birim_fiyat": _sayi(s.get("birim_fiyat")),
             "indirim": _sayi(s.get("indirim")),
             "satir_ciro_net": _sayi(s.get("satir_ciro_net"))}
            for s in satislar],
    }


def zararina_satislar(satislar: list[dict], maliyet: float | None) -> list[dict]:
    """Net satır cirosu birim maliyetin ALTINDA kalan satışlar.

    Bu bir kreatif bulgusu değil gibi görünür ama öyledir: indirim kuponu
    kreatifin çağrısıdır. Kreatif brief'i yazarken hangi indirimin ürünü
    zarara soktuğunu bilmek gerekir.
    """
    if maliyet is None:
        return []
    zarar = []
    for s in satislar:
        net = _sayi(s.get("satir_ciro_net"))
        adet = _sayi(s.get("adet")) or 1
        if net is not None and net < maliyet * adet:
            zarar.append({"gun": s.get("gun"), "net": net,
                          "maliyet": maliyet * adet,
                          "indirim": _sayi(s.get("indirim"))})
    return zarar


# --------------------------------------------------------------------------
# 2) KENDİ GEÇMİŞİMİZ + TUTARLILIK DENETİMİ
# --------------------------------------------------------------------------

# Reklam metninde geçip de ürün kaydında OLMAYAN etken madde, yanlış ürün
# iddiasıdır. Liste kozmetikte en sık adı geçen etken maddelerden kuruldu;
# amaç tam kapsam değil, YAKALANABİLİR olanı yakalamak.
ETKEN_MADDELER = (
    "ceramide", "seramid", "niacinamide", "niasinamid", "retinol", "bakuchiol",
    "hyaluronik", "hyaluronic", "sodium hyaluronate", "squalane", "skualan",
    "panthenol", "pantenol", "salicylic", "salisilik", "glycolic", "glikolik",
    "vitamin c", "c vitamini", "askorbik", "peptit", "peptide", "kollajen",
    "collagen", "aha", "bha", "pha", "allantoin", "shea", "jojoba", "argan",
    "aloe", "centella", "cica", "azelaic", "azelaik", "urea", "ure",
)

MARKA_DOGRU = "L’CARLIÉ"
# Kabul edilen iki yazım: kesme işareti düz ya da eğik olabilir, ama É şart.
MARKA_KALIBI = re.compile(r"L\s*['’]\s*CARLI[EÉ]", re.IGNORECASE)


def kreatif_tutarlilik(kreatifler: list[dict], urun_metni: str) -> list[dict]:
    """Yayına çıkmış kendi metinlerimizi ürün kaydıyla karşılaştırır.

    İki tür hata arar ve ikisi de ÖLÇÜMDÜR, yorum değil:
      A) metinde geçen etken madde ürün kaydında yok  → yanlış ürün iddiası
      B) marka adı É'siz yazılmış                     → marka tutarsızlığı
    """
    urun_anahtar = katla(urun_metni)
    bulgular = []
    for k in kreatifler:
        govde = str(k.get("govde") or "")
        if not govde:
            continue
        govde_anahtar = katla(govde)
        eksik = [m for m in ETKEN_MADDELER
                 if katla(m) in govde_anahtar and katla(m) not in urun_anahtar]
        yazimlar = {y for y in MARKA_KALIBI.findall(govde)}
        # findall grup döndürmüyor; tam eşleşmeleri ayrıca al
        yazimlar = {m.group(0) for m in MARKA_KALIBI.finditer(govde)}
        yanlis_marka = [y for y in yazimlar if "É" not in y and "é" not in y]
        if not eksik and not yanlis_marka:
            continue
        bulgular.append({
            "ad_id": k.get("ad_id"), "ad_adi": k.get("ad_adi"),
            "durum": k.get("etkin_durum"),
            "urunde_olmayan_madde": eksik,
            "yanlis_marka_yazimi": yanlis_marka,
            "alinti": govde[:220],
        })
    return bulgular


def kendi_kreatiflerimiz(hafiza: CompanyMemory, urun_adi: str) -> list[dict]:
    """Bu ürünün adı gövdesinde geçen reklam metinleri."""
    anahtar = katla(urun_adi.split("|")[0].strip())
    return [k for k in hafiza._fetch("kreatif_performans").records
            if anahtar in katla(str(k.get("govde") or ""))]


# --------------------------------------------------------------------------
# 3) RAKİP — DIŞ KAYNAK, İDDİA
# --------------------------------------------------------------------------

# Açı seviyeleri. TEMEL her koşuda çalışır; DERIN yalnız --derin ile.
#
# 🔴 NEDEN SEVİYE VAR. Sahip 21.09.2026'da "tek repo/tek kaynak istemiyorum,
# farklı açılarla araştırma yapılmalı" dedi -- doğru. Ama her açı ürün başına
# BİR grounded arama demek ve haftalık parti 36 ürün koşuyor: 4 açı 144 arama,
# 11 açı 396 arama. Açıları seviyesiz eklemek, haftalık yükü sormadan 2,75
# katına çıkarmak olurdu. Haftalık parti TEMEL ile koşar; tek ürün üzerinde
# çalışırken --derin ile hepsi açılır.
TEMEL, DERIN = "temel", "derin"

# 🔴 HER SORU TEK ODAKLI VE KISA. Ölçüldü: ilk `rakip_kreatif` sorusu dört
# parçalıydı (format + başlık + tutan gönderi + zayıf yaklaşım) ve grounded
# arama HİÇ KAYNAK döndürmedi -- çok parçalı soru aramayı dağıtıyor.
# Yeni açı eklerken kural: bir soru, bir şey sorar. Birleştirme, açı ekle.
RAKIP_ACILARI = (
    ("fiyat_ve_marka", TEMEL,
     "Türkiye pazarında {kategori} satan markalar hangileri? Her satırda "
     "MARKA + ÜRÜN ADI + ml + GÜNCEL TL FİYAT ver. En az 8 ürün listele. "
     "SADECE kaynakta açıkça yazan fiyatı ver; yazmıyorsa 'fiyat kaynakta yok' "
     "yaz, TAHMİN ETME."),
    ("satis_vaadi", TEMEL,
     "Türkiye'de {kategori} satan markaların ürün sayfalarında ve "
     "reklamlarında kullandığı BAŞLIK ve SATIŞ CÜMLELERİ nelerdir? "
     "Cümleleri olduğu gibi, tırnak içinde aktar. Hangi markanın cümlesi "
     "olduğunu yaz."),
    ("alici_itirazi", TEMEL,
     "Türkiye'de {kategori} ürünlerinin yorumlarında ve soru-cevap "
     "bölümlerinde alıcılar en çok neyden ŞİKAYET ediyor ve ne SORUYOR? "
     "Somut şikayet ve soruları madde madde yaz."),
    ("rakip_kreatif", TEMEL,
     "{kategori} satan markaların Instagram gönderilerinde ve reklamlarında "
     "en çok hangi içerik türleri ve hangi mesajlar kullanılıyor? "
     "Somut marka adı ve gönderi örneği ver."),

    # --- DERİN AÇILAR (21.09.2026) --------------------------------------
    # Sahip: "organik içeriklerin nasıl yükseldiğini görüyoruz" -- o yüzden
    # organik yükseliş kendi açısı oldu, reklamdan ayrı sorulur.
    ("organik_yukselen", DERIN,
     "Türkiye'de {kategori} konusunda son aylarda Instagram ve TikTok'ta çok "
     "izlenen ORGANİK içerikler hangileri? İçeriğin konusunu ve hesabı yaz."),
    # 🔴 TEK AÇI İKİYE BÖLÜNDÜ. Ölçüldü (21.09.2026): birleşik kanca sorusu
    # iki koşuda kaynak döndürmedi, üçüncüde 512 karakterle geçiştirdi.
    # Ayrı ayrı sorulunca ikisi de kaynak getirdi (3.426 ve 3.388 karakter).
    # Sebep: organik içerik ile ücretli reklam AYRI şeyler ve ayrı yerlerde
    # yazılıyor; tek soru ikisini de bulanıklaştırıyor.
    #
    # 🔴 GENEL SORU SORMA. "En çok dönüşüm getiren hook kalıpları nelerdir?"
    # 4.640 karakter döndürdü ama SIFIR kaynakla -- model ezberden konuştu ve
    # hat onu doğru şekilde reddetti. Soru markaya/platforma bağlanmalı.
    #
    # 🔴 KANCA BİZDEN DEĞİL PİYASADAN ÖĞRENİLİR (sahip kararı, 21.09.2026):
    # kendi 63 kreatifimiz kötü örnek -- çoğu duraklatılmış ve hesap
    # kapsaması 1/3. Referans, bizimle uyumlu kozmetik markaları.
    # 🔴 BIREBIR ALINTI İSTEMEK GROUNDING'İ BASTIRIYOR.
    # Ölçüldü (22.09.2026, iki ayrı kategoride tekrarlandı):
    #
    #   "…açılış cümlesi örnekleri neler? Cümleleri tırnak içinde,
    #    olduğu gibi aktar."                       -> 0 kaynak / 0 kaynak
    #   "…viral olan sosyal medya videolarında
    #    neler anlatılıyor?"                       -> 1 kaynak / 2 kaynak
    #
    #   "…Google'da en çok hangi soruları arıyor?
    #    Arama ifadelerini olduğu gibi yaz."       -> 0 kaynak / 0 kaynak
    #   "…hakkında en çok sorulan sorular nelerdir?" -> 7 kaynak / 11 kaynak
    #
    # İkisinde de tek fark "olduğu gibi/tırnak içinde aktar" şartıydı. Model
    # birebir alıntı istenince kendi belleğinden yazıyor ve aramaya hiç
    # gitmiyor gibi görünüyor; hat da kaynaksız cevabı doğru şekilde atıyor.
    # Ders: aramaya BİÇİM dayatma, KONU sor. Alıntıyı biz çıkarırız
    # (kanca havuzu zaten tırnak içi cümleleri kendisi ayıklıyor).
    ("kanca_organik", DERIN,
     "Türkiye'de {kategori} hakkında viral olan sosyal medya videolarında "
     "neler anlatılıyor?"),
    ("kanca_sponsorlu", DERIN,
     "Türkiye'de kozmetik markalarının Facebook ve Instagram reklamlarında "
     "kullandığı reklam metni başlangıç cümlesi örnekleri neler?"),
    ("video_formati", DERIN,
     "{kategori} tanıtımlarında hangi video formatı kullanılıyor: "
     "kullanıcı çekimi mi, ürün yakın çekimi mi, önce-sonra mı, rutin anlatımı mı?"),
    ("pazaryeri_yorumu", DERIN,
     "Trendyol ve Hepsiburada'da {kategori} ürünlerinin DÜŞÜK PUANLI "
     "yorumlarında hangi şikayetler tekrar ediyor? Yorumlardan alıntı ver."),
    # 🔴 EN DEĞERLİ AÇI. Reklam Kurulu ceza kararları hem rakibin neyi
    # söyleyip ceza yediğini hem BİZİM neyi söyleyemeyeceğimizi öğretir.
    # Kreatif girdisi olduğu kadar mevzuat kalkanı.
    ("mevzuat_cezasi", DERIN,
     "Reklam Kurulu {kategori} ürünleri için hangi reklam ifadelerine ceza "
     "verdi? Cezaya konu olan ifadeyi ve markayı yaz."),
    ("influencer_kullanimi", DERIN,
     "Türkiye'de {kategori} markaları influencer iş birliklerinde nasıl bir "
     "anlatım kullanıyor? Somut örnek ver."),
    ("arama_niyeti", DERIN,
     "{kategori} hakkında en çok sorulan sorular nelerdir?"),
)


def _grounded(soru: str, anahtar: str) -> tuple[str, list[str]]:
    govde = {"contents": [{"parts": [{"text": soru}]}],
             "tools": [{"google_search": {}}]}
    istek = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{ARAMA_MODELI}"
        f":generateContent?key={anahtar}",
        data=json.dumps(govde).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=120) as cevap:
        d = json.loads(cevap.read().decode("utf-8"))
    aday = (d.get("candidates") or [{}])[0]
    metin = "".join(p.get("text") or ""
                    for p in ((aday.get("content") or {}).get("parts") or []))
    kaynaklar = []
    for ch in ((aday.get("groundingMetadata") or {}).get("groundingChunks") or []):
        u = ((ch.get("web") or {}).get("uri")) or ""
        b = ((ch.get("web") or {}).get("title")) or u
        if u:
            kaynaklar.append(b)
    return metin, kaynaklar


def rakip_taramasi(kategori: str, derin: bool = False) -> list[dict]:
    """Üç açıdan grounded tarama.

    🔴 KAYNAKSIZ CEVAP KAYDEDİLMEZ. groundingChunks boşsa model kendi
    belleğinden konuşmuş demektir; o bir arama sonucu değil, bir tahmindir
    ve rakip fiyatı olarak yazılamaz.
    """
    anahtar = providers.load_env().get("GEMINI_API_KEY")
    if not anahtar:
        return []
    cikti = []
    acilar = [a for a in RAKIP_ACILARI if derin or a[1] == TEMEL]
    print(f"  rakip taraması: {len(acilar)} açı "
          f"({'derin' if derin else 'temel'})", file=sys.stderr)
    kaynaksiz = []
    for ad, _seviye, kalip in acilar:
        try:
            metin, kaynaklar = _grounded(kalip.format(kategori=kategori), anahtar)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as hata:
            print(f"  rakip/{ad}: HATA {str(hata)[:120]}", file=sys.stderr)
            continue
        if not kaynaklar:
            # 🔴 "kaynak yok" ile "bakılmadı" AYRI durumlar. Atlanan açı
            # sessizce kaybolursa brief "bu konuda bulgu yok" gibi okunur;
            # oysa doğrusu "arandı, kaynak dönmedi".
            kaynaksiz.append(ad)
            print(f"  rakip/{ad}: kaynak yok -> atlandı", file=sys.stderr)
            continue
        print(f"  rakip/{ad}: {len(metin)} karakter · {len(kaynaklar)} kaynak")
        cikti.append({"aci": ad, "bulgu": metin.strip()[:4000],
                      "kaynaklar": kaynaklar[:10],
                      "seviye": "DIŞ KAYNAK — şirket ölçümü değil, iddia"})
    if kaynaksiz:
        cikti.append({"aci": "kaynak dönmeyen açılar", "kaynaklar": [],
                      "seviye": "DURUM — bulgu yokluğu değil, arama sonucu yokluğu",
                      "bulgu": "Şu açılarda arama yapıldı ama kaynak dönmedi: "
                               + ", ".join(kaynaksiz)})
    return cikti


# --------------------------------------------------------------------------
# 3c) EKİBİN GÖRÜŞÜ — 42 kişilik kadro, SIFIR model çağrısı
# --------------------------------------------------------------------------
#
# 🔴 SAHİP İSTEDİ: "o kadar uzman boşuna durmayacak sistemde."
# Haklı: kadro kuruldu, panoda duruyordu, ama kreatif brief'i onlara hiç
# sormuyordu. `roster.opinions()` her üyenin ŞİRKET VERİSİNE bakıp söylediği
# cümleyi üretir ve bunu MODEL ÇAĞIRMADAN yapar -- yani ekibi hatta sokmanın
# maliyeti sıfır. Sokmamanın maliyeti ise brief'in şirketin kendi
# ölçümlerinden habersiz yazılmasıydı.
#
# 🔴 "VERI YOK" DİYEN ÜYE SUSTURULMAZ, OLDUĞU GİBİ TAŞINIR. Bir departmanın
# veriyi okuyamaması bir DURUMDUR; onu gizleyip brief'i dolu göstermek, o
# ürün hakkında bilmediğimiz şeyi biliyormuş gibi yapmak olurdu.
KREATIF_KURUL = (
    "creative_decision", "creative_hypothesis", "creative_copy",
    "creative_coverage", "creative_fatigue", "art_format",
    "brand_voice", "brand_positioning", "brand_strategy",
    "content_cadence", "social_engagement", "price_position",
    "market_findings", "regulatory_quality", "bizdev",
    # --- 21.09.2026'da eklenenler ---------------------------------------
    # 🔴 Kadroda 43 üye var, kreatif kurulu 15'ini çağırıyordu. Dışarıda
    # kalanların arasında tam bu işin adamları vardı; en çarpıcısı
    # `creative_intelligence`: görevi "reklam kayıtlarından hangi kreatifin
    # TUTTUĞUNU okumak" ve kreatif brief'i ona hiç sormuyordu.
    "creative_intelligence",   # hangi kreatif tuttu — ölçümden
    "meta_performance",        # harcama, gösterim, tıklama
    "social_media",            # kanal performansı
    "crm_customer",            # müşterinin kendi sorduğu — itirazın kaynağı
    "product_portfolio",       # ürün kârlılığı ve huni
    "data_measurement",        # ölçüm güvenilir mi
    "market_intelligence",     # pazarın dışarıdaki hali
    "competitor_intelligence",  # rakip hamleleri
)


def kurul_gorusu(hafiza: CompanyMemory) -> list[dict]:
    """Kreatifi ilgilendiren departmanların veriye bakınca söyledikleri."""
    try:
        from jarvis import roster
    except Exception as hata:  # noqa: BLE001
        print(f"  kurul okunamadı: {str(hata)[:100]}", file=sys.stderr)
        return []
    try:
        ham = roster.opinions(hafiza, only=KREATIF_KURUL)
    except Exception as hata:  # noqa: BLE001
        print(f"  kurul çalışmadı: {str(hata)[:100]}", file=sys.stderr)
        return []
    cikti = []
    for u in ham:
        cumle = str(u.get("statement") or "").strip()
        if not cumle:
            continue
        cikti.append({"uye": u.get("name"), "gorev": u.get("job"),
                      "durum": u.get("status"), "soyledigi": cumle})
    return cikti


# --------------------------------------------------------------------------
# 3b) FİYAT KONUMU — KODDA HESAPLANIR, MODELE SORULMAZ
# --------------------------------------------------------------------------

# "1.234,56 TL" / "990,00 TL" / "98 TL" — Türkçe biçim: nokta binlik, virgül ondalık
_TL = re.compile(r"(\d[\d.]*(?:,\d{1,2})?)\s*TL", re.IGNORECASE)
_ML = re.compile(r"(\d+(?:[.,]\d+)?)\s*ml", re.IGNORECASE)


def _tl_sayi(ham: str) -> float | None:
    try:
        return float(ham.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def fiyat_konumu_hesapla(bizim_tl: float | None, bizim_ml: float | None,
                         rakip_bulgulari: list[dict]) -> dict:
    """Rakip satırlarından fiyat/hacim çıkarır ve konumumuzu SAYIYLA söyler.

    🔴 BU İŞ MODELE BIRAKILMAZ. Ölçüldü: aynı kanıtı gören model
    "HYDRAVIE fiyat olarak orta seviye, rakiplerle aynı seviyede yer alır"
    yazdı; oysa kendi listelediği sekiz rakibin en pahalısı 990 TL, bizimki
    1.200 TL idi. Model kendi kanıtıyla çelişebiliyor, aritmetik çelişemez.

    🔴 MUTLAK FİYAT TEK BAŞINA YANILTIR. 200 ml'lik 98 TL'lik ürünle 50 ml'lik
    1.200 TL'yi yan yana koymak kıyas değildir; ml başına fiyat ayrıca
    hesaplanır ve iki sıralama da raporlanır.
    """
    satirlar: list[dict] = []
    for bulgu in rakip_bulgulari:
        if bulgu.get("aci") != "fiyat_ve_marka":
            continue
        for ham in str(bulgu.get("bulgu") or "").splitlines():
            fiyat_es = _TL.search(ham)
            if not fiyat_es:
                continue
            fiyat = _tl_sayi(fiyat_es.group(1))
            # 🔴 MAKUL ARALIK DIŞI FİYAT ATILIR. Ölçüldü: bir koşuda rakip
            # aralığı "730–139990 TL" çıktı; 139.990 TL bir yüz kremi değil,
            # metne karışmış alakasız bir rakamdı. Tek bir saçma değer hem
            # aralığı hem ml başına kıyası bozuyor ve brief'e "rakipler
            # bizden pahalı" diye YANLIŞ bir cümle yazdırıyor.
            if fiyat is None or not (20.0 <= fiyat <= 20000.0):
                continue
            hacim_es = _ML.search(ham)
            hacim = None
            if hacim_es:
                try:
                    hacim = float(hacim_es.group(1).replace(",", "."))
                except ValueError:
                    hacim = None
            # Ml başına fiyat da elenir: 0,1 TL/ml altı ve 500 TL/ml üstü
            # bu kategoride yok; böyle bir değer ml'nin yanlış okunduğunu
            # gösterir (ör. "1.69 fl oz" içindeki 1,69'u hacim sanmak).
            birim = round(fiyat / hacim, 2) if hacim else None
            if birim is not None and not (0.1 <= birim <= 500.0):
                birim = None
            satirlar.append({
                "satir": ham.strip().lstrip("*-• ")[:160],
                "tl": fiyat, "ml": hacim, "tl_ml": birim})

    sonuc: dict = {"rakip_satir_sayisi": len(satirlar), "rakipler": satirlar,
                   "bizim_tl": bizim_tl, "bizim_ml": bizim_ml,
                   "kaynak": "DIŞ KAYNAK fiyat iddiaları + şirket ölçümü (bizim fiyat)"}
    if not satirlar or bizim_tl is None:
        sonuc["cumle"] = "Karşılaştırılabilir rakip fiyatı çıkarılamadı."
        return sonuc

    mutlak = sorted(s["tl"] for s in satirlar)
    ustunde = sum(1 for f in mutlak if f < bizim_tl)
    sonuc["mutlak"] = {"en_ucuz": mutlak[0], "en_pahali": mutlak[-1],
                       "ortanca": mutlak[len(mutlak) // 2],
                       "bizden_ucuz_adet": ustunde, "toplam": len(mutlak)}
    parcalar = [f"Bizim fiyat {bizim_tl:.0f} TL; listelenen {len(mutlak)} rakip "
                f"{mutlak[0]:.0f}–{mutlak[-1]:.0f} TL aralığında ve "
                f"{ustunde} tanesi bizden ucuz."]

    birim = [s for s in satirlar if s["tl_ml"]]
    if birim and bizim_ml:
        bizim_birim = round(bizim_tl / bizim_ml, 2)
        sirali = sorted(s["tl_ml"] for s in birim)
        birim_ustunde = sum(1 for f in sirali if f < bizim_birim)
        sonuc["birim"] = {"bizim_tl_ml": bizim_birim, "en_ucuz": sirali[0],
                          "en_pahali": sirali[-1],
                          "bizden_ucuz_adet": birim_ustunde, "toplam": len(sirali)}
        parcalar.append(
            f"Ml başına: bizde {bizim_birim:.2f} TL/ml, rakiplerde "
            f"{sirali[0]:.2f}–{sirali[-1]:.2f} TL/ml ve {birim_ustunde}/{len(sirali)} "
            f"tanesi bizden ucuz.")
    else:
        parcalar.append("Ml bilgisi yeterli değil, birim fiyat kıyası yapılamadı.")
    sonuc["cumle"] = " ".join(parcalar)
    return sonuc


# --------------------------------------------------------------------------
# 4) KONUMLANDIRMA + SATIŞ CÜMLELERİ
# --------------------------------------------------------------------------

KONUM_SISTEM = """Sen L'CARLIÉ markasının kreatif stratejistisin. Türkçe yazarsın.

SANA VERİLEN HER ŞEY KANITTIR. Kanıtta olmayan hiçbir SAYI, MADDE ADI, FİYAT
veya RAKİP ADI yazma.

🔴 "kanıtta yok" SADECE sayı/madde/fiyat/rakip için geçerlidir. Bu ifadeyi
müşteriye giden bir cümlenin içine ASLA yazma. Ölçüldü: bir önceki denemede
alıcı itirazlarının cevabı "Kanıtta yok. Ürün, gözenekleri tıkama..." diye
başladı — bu cevap müşteriye gösterilemez. Alıcı itirazının cevabı, ürün
kaydındaki İÇERİK ve KULLANIM bilgisinden kurulur; elde bilgi yoksa o itirazı
listeye HİÇ ALMA.

🔴 KİME KONUŞTUĞUNU KANITTAN AL, ÜRÜN ADINDAN DEĞİL. Kanıtta
`gercek_kitle` alanı varsa `kime` cevabını ONA göre yaz. Ürün adında ve
etiketinde geçen kitle, ürünü SATIN ALAN kitle olmayabilir. Ölçüldü
(21.09.2026): EASYCOMB'un adı "Bebek ve Çocuklar İçin" ama ürünü ağırlıklı
olarak YETİŞKİNLER alıyor -- adı okuyup "ebeveynler" yazmak, brief'i dolu ve
tutarlı gösterip yanlış kişiye konuşturur. Etiket cümlesi değişmez, reklamın
muhatabı değişir.

🔴 FİYAT KONUMUNU SEN HESAPLAMA. Kanıtta `fiyat_konumu_olcumu` diye hazır
hesaplanmış bir alan var; `fiyat_konumu` cevabını ONUN SAYILARIYLA yaz.
Kendi kanıtınla çelişen bir fiyat cümlesi kurma.

🔴 İTİRAZI "YALANLAYARAK" CEVAPLAMA. Alıcı "topaklanma yapar mı?" diye
soruyorsa cevabın "yapmaz / riski yoktur" OLAMAZ — elimizde o testin sonucu
yok. Olumsuzlama da bir iddiadır ve belge ister. Bunun yerine ürün kaydında
GERÇEKTEN yazan şeyi söyle: dokusu, kullanım şekli, içindeki madde.

🔴 SÜRE, ORAN VE YÜZDE UYDURMA. "3-4 saat boyunca", "%90", "24 saat nem"
gibi ifadeler ölçüm sonucudur; ölçmedik. Ürün kaydında geçmeyen hiçbir sayıyı
cümleye koyma.

🔴 TL/ml RAKAMI REKLAM METNİNE GİRMEZ. `fiyat_konumu_olcumu` içindeki
"24 TL/ml" bizim iç kıyas ölçümümüzdür. Satış cümlesinde geçerse alıcı onu
ürünün fiyatı sanır. Reklamda yazılabilecek tek fiyat ürünün SATIŞ FİYATIDIR.

🔴 İÇ MUHAKEMENİ YAZMA. "mevzuata uygun", "klinik olarak kanıtlanmış değil",
"cilt bariyerini güçlendirmez" gibi ifadeler senin kendi kontrol notundur;
brief'e girmez. Ayrışma maddeleri ALICIYA ne söylediğini anlatır, denetçiye
değil.

MEVZUAT — Türkiye Kozmetik Yönetmeliği. Kozmetik ürün TEDAVİ ETMEZ, HASTALIK
İYİLEŞTİRMEZ. Şu tür cümleler YASAKTIR ve yazarsan iş çöpe gider:
- "iyileştirir, tedavi eder, onarır, geçirir, yok eder"
- hastalık/semptom adı + fayda ("egzamayı geçirir", "akneyi yok eder")
- "klinik olarak kanıtlanmış", "dermatolog onaylı" (belgesi elimizde yoksa)
İZİN VERİLEN dil: "görünümünü destekler", "nem dengesinin korunmasına yardımcı
olur", "cildi yumuşak hissettirir", "bakım rutinine eşlik eder".

KÖTÜ İŞ NEYE BENZER (bunu YAPMA): "Günlük bakım rutininizde kendinize
ayırdığınız adım" — bu cümle her ürün için doğru, yani hiçbir ürün için
bir şey söylemiyor. Ürünün İÇİNDEKİNİ, FİYATINI, ALICININ İTİRAZINI konuş.

SADECE geçerli JSON döndür, öncesinde ve sonrasında tek kelime yazma."""

KONUM_ISTEK = """Aşağıdaki kanıta dayanarak {urun} için kreatif brief üret.

JSON şeması — birebir bu anahtarlar:
{{
 "urun_tek_cumle": "Ürün nedir, tek cümlede, içindeki maddeyle birlikte",
 "kime": "Hedef alıcı. Kanıtta gercek_kitle varsa ONU esas al; yoksa alıcı itirazlarına dayan. Ürün adındaki kitleyi kopyalama.",
 "ayrisma": ["Rakipten ayrıştığı 3 somut nokta. ALICIYA söylenen dille yaz, iç not değil."],
 "alici_itirazi": [{{"itiraz": "Kanıttaki GERÇEK alıcı şikayet/sorularından biri, birebir konu", "cevap": "Ürün kaydındaki içerik ve kullanım bilgisiyle verilen, müşteriye gösterilebilir cevap. 'Kanıtta yok' YAZMA; cevaplayamıyorsan bu itirazı hiç ekleme."}}],
 "fiyat_konumu": "fiyat_konumu_olcumu alanındaki SAYILARLA yaz. Pahalıysak pahalı de; bunun karşılığında alıcıya ne verdiğimizi de yaz.",
 "satis_cumleleri": ["6 adet. Her biri 12 kelimeyi geçmesin. En az 3 tanesi yukarıdaki GERÇEK alıcı itirazlarından birine cevap versin. Ürün adı, ml, içindeki madde gibi SOMUT şeyler geçsin."],
 "baslik_onerileri": ["4 adet reklam başlığı, 6 kelimeyi geçmesin, her biri TAM ve düzgün Türkçe cümle ya da tamlama olsun"],
 "kacinilacaklar": [{{"ifade": "Bu üründe kullanılmaması gereken ifade", "neden": "Neden kullanılamaz"}}]
}}"""


KANIT_BUTCESI = 10000


# --------------------------------------------------------------------------
# 3d) EKSİK UZMANI JARVIS ATAR
# --------------------------------------------------------------------------
#
# 🔴 SAHİP KARARI, 21.09.2026: "olmayan uzmanın yerine uzman koysun jarvis,
# bu işleri o yapacak."
#
# Önceki hâlde kreatif kurulu SABİT bir anahtar listesiydi ve o listeyi elle
# ben seçiyordum. Yanlıştı: hangi uzmanlığın eksik olduğunu, ürünü ve
# kategoriyi gören taraf bilir -- yani Jarvis. Artık kadro şöyle kuruluyor:
#
#   1. Sabit çekirdek (KREATIF_KURUL) şirket verisinden konuşur — model yok.
#   2. Jarvis, eldeki 43 görev tanımına ve bu ürünün kanıtına bakıp
#      EKSİK uzmanlığı söyler ve o uzmanı ATAR.
#   3. Atama `state/kadro/atanan-uzmanlar.json`'a yazılır ve BİRİKİR;
#      sonraki koşularda aynı uzman yeniden atanmaz, yeniden kullanılır.
#
# 🔴 ATANAN UZMAN ÖLÇÜM DEĞİL, GÖRÜŞTÜR -- ve öyle etiketlenir.
# Çekirdek kurul şirket verisini OKUYOR; atanan uzmanın çoğunun okuyacağı bir
# tablo yok, kanıt üzerinden yorum yapıyor. Bu ikisi brief'te aynı hizada
# gösterilirse brief sahte otorite kazanır. Bu yüzden her atanan üyenin
# `kaynak` alanı vardır ve markdown'da ayrı tabloda, kaynağıyla birlikte
# görünür. Kadroyu büyütmek, ölçümü büyütmek DEĞİLDİR.
KADRO_DOSYASI = Path(os.environ.get(
    "KREATIF_KADRO_DOSYASI", str(KOK / "state" / "kadro" / "atanan-uzmanlar.json")))

KADRO_SISTEM = """Sen bir ajansın İş Planlama Müdürüsün. Görevin kadroyu
tamamlamak: eldeki uzmanların KAPSAMADIĞI bir bakış açısı varsa o uzmanı
atamak.

🔴 VAR OLANI TEKRAR ATAMA. Sana mevcut uzmanların görev tanımları verilecek.
Aynı işi başka adla yapan bir uzman atarsan kadroyu büyütmüş değil,
kalabalıklaştırmış olursun.

🔴 HER UZMAN BİR KAYNAĞA BAĞLANIR. Atadığın uzmanın `kaynak` alanı şunlardan
biri olmalı:
- araştırma açısının adı (sana listesi verilecek) — o açının bulgusunu okur
- "SIRKET_VERISI" — kanıt paketindeki ölçümleri okur
- "KAYNAK_YOK" — okuyacağı veri yok, yalnız yorum yapar
Son seçeneği dürüstçe kullan: veri olmadığı hâlde "SIRKET_VERISI" yazmak,
brief'e olmayan bir ölçüm eklemek olur.

🔴 GÖREV TANIMI ÜRÜNE ÖZEL OLMAZ. Atadığın uzman kadroya KALICI olarak
girer ve bundan sonra 36 ürünün hepsinde çalışır. Görev tanımına bugünkü
ürünün ayrıntısını yazma ("yapışkanlık hissi itirazını okur" gibi) -- o
ayrıntı yarın başka üründe anlamsız kalır. Tanım, uzmanın HANGİ TÜR bulguyu
okuyup NE tür sonuç çıkardığını söylemeli.

🔴 UZMAN, SORU SORAN DEĞİL CEVAP VEREN OLMALI. "Araştırılmalı" diyen bir
uzman iş yapmaz. Atadığın uzman eldeki kanıtla SOMUT bir şey söyleyebilmeli.

SADECE geçerli JSON döndür."""

KADRO_ISTEK = """{urun} için kreatif brief hazırlanıyor.

Aşağıdaki araştırma açıları BULGU ÜRETTİ ama kadroda bu bulguyu okuyup
yorumlayacak ATANMIŞ KİMSE YOK. Her biri için bir uzman ata.

KAPSANMAYAN AÇILAR (her biri için bir uzman, en fazla {adet} tane):
{bosluklar}

Bu açıların bulgusundan örnekler:
{ornekler}

MEVCUT UZMANLAR — bunların hepsi ŞİRKET TABLOLARINI okur, dış araştırma
bulgusunu değil. Atadığın uzmanın adı bunlardan biriyle aynı OLMASIN:
{mevcut}

JSON şeması — birebir:
{{"atanan": [
  {{"anahtar": "kisa_ingilizce_anahtar",
    "ad": "Uzmanın Türkçe unvanı",
    "gorev": "Bu açının bulgusundan ne okur ve ne söyler — tek cümle",
    "kaynak": "kapsanmayan açılardan BİRİNİN adı, birebir",
    "neden_eksikti": "Mevcut kadronun bu bakışı neden kapsamadığı"}}
]}}"""


def kapsanmayan_acilar(rakip: list[dict], kadro: dict) -> list[str]:
    """Bulgu üretmiş ama okuyucusu olmayan açılar.

    🔴 BOŞLUK TESPİTİ MODELE SORULMAZ, HESAPLANIR. Ölçüldü (21.09.2026):
    modele 43 görev tanımı gösterilip "eksik uzmanlık var mı" diye
    sorulduğunda -- 9.349 karakterlik dolu kanıtla bile -- `{"atanan": []}`
    döndü. Kalabalık bir kadro görünce "eksik yok" demek, modelin makul ama
    işe yaramaz cevabı.

    Gerçek boşluk soyut değil, sayılabilir: 11 araştırma açısı bulgu
    üretiyor ve kadronun TAMAMI şirket tablolarını okuyor -- dış araştırma
    bulgusunu okuyan atanmış kimse yok. Kod bunu kesin olarak bilir;
    modele kalan iş, boşluğu doldurmak.
    """
    okunan = {str(v.get("kaynak") or "") for v in kadro.values()}
    bulgulu = [r.get("aci") for r in rakip
               if r.get("aci") and r.get("kaynaklar") and r.get("bulgu")]
    return [a for a in bulgulu if a not in okunan]

GORUS_SISTEM = """Sen bir ajans ekibisin. Her uzman KENDİ görev tanımının
penceresinden, verilen kanıta bakıp TEK CÜMLE söyler.

🔴 KANITTA OLMAYANI SÖYLEME. Rakam veriyorsan kanıttan almalısın.
🔴 "Araştırılmalı", "incelenmeli" YAZMA — bu bir görüş değil, işin ertelenmesi.
Kanıt o konuda sessizse bunu açıkça söyle: "kanıtta bu konuda veri yok".
🔴 Uzmanın kaynağı KAYNAK_YOK ise cümlesi bir YORUMDUR; ölçüm diliyle yazma.

SADECE geçerli JSON döndür."""

GORUS_ISTEK = """Bu uzmanların her biri için tek cümlelik görüş yaz.
Her uzmanın ALTINDA okuyacağı bulgu veriliyor; uzman YALNIZ kendi bulgusuna
ve şirket ölçümüne bakar.

UZMANLAR VE OKUYACAKLARI BULGU:
{uzmanlar}

ŞİRKET ÖLÇÜMÜ:
{kanit}

JSON şeması — birebir:
{{"gorusler": [{{"anahtar": "...", "soyledigi": "Tek cümle"}}]}}"""


def _kadro_oku() -> dict:
    try:
        return json.loads(KADRO_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _kadro_yaz(kadro: dict) -> None:
    KADRO_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    KADRO_DOSYASI.write_text(json.dumps(kadro, ensure_ascii=False, indent=1),
                             encoding="utf-8")


def kadro_tamamla(yonlendirici: ModelRouter, urun_adi: str,
                  rakip: list[dict], azami: int = 4,
                  guclu: bool = False) -> list[dict]:
    """Okuyucusu olmayan açılara uzman atar; kadro KALICI olarak biriker."""
    from jarvis import roster  # yerel içe aktarım: roster yalnız burada gerekli

    kadro = _kadro_oku()
    bosluklar = kapsanmayan_acilar(rakip, kadro)[:azami]
    if not bosluklar:
        print(f"  atanan uzman: kadroda {len(kadro)} · kapsanmayan açı yok")
        return [dict(v, anahtar=k) for k, v in kadro.items()]

    mevcut_anahtarlar = {u.key for u in roster.ROSTER} | set(kadro)
    mevcut = "\n".join(f"- {u.name}" for u in roster.ROSTER)
    ornekler = "\n".join(
        f"[{r.get('aci')}] {str(r.get('bulgu') or '')[:420]}"
        for r in rakip if r.get("aci") in bosluklar)

    veri, _ = _uret(yonlendirici, KADRO_SISTEM,
                    KADRO_ISTEK.format(urun=urun_adi, adet=len(bosluklar),
                                       bosluklar="\n".join(f"- {b}" for b in bosluklar),
                                       ornekler=ornekler[:5000], mevcut=mevcut),
                    1800, guclu=guclu)
    yeni = 0
    if isinstance(veri, dict):
        for u in veri.get("atanan") or []:
            if not isinstance(u, dict):
                continue
            anahtar = re.sub(r"[^a-z0-9_]+", "_", str(u.get("anahtar") or "").lower()).strip("_")
            if not anahtar or anahtar in mevcut_anahtarlar:
                continue          # var olanı tekrar atama
            kaynak = str(u.get("kaynak") or "KAYNAK_YOK")
            if kaynak not in bosluklar:
                # Modelin uydurduğu ya da kapsanmış bir açıya bağladığı uzman,
                # doldurması istenen boşluğu doldurmuyor demektir.
                print(f"    atama reddedildi ({anahtar}): kaynak '{kaynak}' "
                      f"kapsanmayan açılar arasında değil", file=sys.stderr)
                continue
            if False:
                # 🔴 Uydurulmuş kaynak adı, olmayan bir ölçüme bağlanmış uzman
                # demektir. Reddetmek yerine en dürüst değere indiriyoruz.
                kaynak = "KAYNAK_YOK"
            kadro[anahtar] = {
                "ad": str(u.get("ad") or anahtar)[:60],
                "gorev": str(u.get("gorev") or "")[:220],
                "kaynak": kaynak,
                "neden_eksikti": str(u.get("neden_eksikti") or "")[:220],
                "atandi": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "atayan": "jarvis/kreatif-brief",
            }
            mevcut_anahtarlar.add(anahtar)
            yeni += 1
    if yeni:
        _kadro_yaz(kadro)
    print(f"  atanan uzman: kadroda {len(kadro)} · bu koşuda yeni {yeni} · kapsanmayan açı {len(bosluklar)}")
    return [dict(v, anahtar=k) for k, v in kadro.items()]


def atanan_gorusleri(yonlendirici: ModelRouter, atanan: list[dict], kanit: str,
                     rakip: list[dict] | None = None,
                     guclu: bool = False) -> list[dict]:
    """Atanan uzmanların görüşü — TEK model çağrısında, hepsi birden.

    🔴 HER UZMANA KENDİ AÇISININ TAM METNİ VERİLİR.
    İlk sürümde hepsine ortak `kanit` paketi gidiyordu ve ölçüldü ki dört
    uzmanın ÜÇÜ "kanıtta bu konuda veri yok" dedi -- haklıydılar: kanıt
    paketi bütçeye sığdırılırken ilk kırpılan şey rakip bulgularıdır
    (`kanit_kur` kısaltma sırası), yani uzmanı okuması için atadığımız metin
    tam da ona ulaşmadan kesiliyordu. Bir uzmanı bir açıya atayıp o açının
    metnini vermemek, kadroyu kalabalıklaştırıp brief'e "veri yok" satırı
    eklemekten başka bir şey yapmaz.
    """
    if not atanan:
        return []
    bulgular = {r.get("aci"): str(r.get("bulgu") or "")
                for r in (rakip or []) if r.get("aci")}
    satirlar = []
    for u in atanan:
        satirlar.append(f"- {u['anahtar']}: {u['ad']} — {u['gorev']}")
        metin = bulgular.get(u["kaynak"], "")
        if metin:
            satirlar.append(f"  OKUYACAĞI BULGU ({u['kaynak']}):\n  {metin[:2200]}")
        elif u["kaynak"] == "SIRKET_VERISI":
            satirlar.append("  OKUYACAĞI: aşağıdaki şirket ölçümü")
        else:
            satirlar.append("  OKUYACAĞI BULGU YOK — bu koşuda o açı kaynak döndürmedi")
    uzmanlar = "\n".join(satirlar)
    veri, _ = _uret(yonlendirici, GORUS_SISTEM,
                    GORUS_ISTEK.format(uzmanlar=uzmanlar[:9000],
                                       kanit=kanit[:4000]),
                    2200, guclu=guclu)
    sozluk = {}
    if isinstance(veri, dict):
        for g in veri.get("gorusler") or []:
            if isinstance(g, dict) and g.get("anahtar"):
                sozluk[str(g["anahtar"])] = str(g.get("soyledigi") or "")
    cikti = []
    for u in atanan:
        cumle = sozluk.get(u["anahtar"], "").strip()
        cikti.append({
            "uye": u["ad"], "gorev": u["gorev"], "anahtar": u["anahtar"],
            "kaynak": u["kaynak"],
            "durum": "GORUS" if cumle else "CEVAP_YOK",
            "soyledigi": cumle or "bu koşuda görüş üretmedi",
        })
    return cikti


# --------------------------------------------------------------------------
# 3e) KANCA HAVUZU — piyasadan toplanır, kalıbı alınır, cümlesi ALINMAZ
# --------------------------------------------------------------------------
#
# 🔴 SAHİP KARARI, 21.09.2026: "o kancaları bize göre değil, piyasadaki
# bizimle uyumlu diğer kozmetik reklamlarının hooklarına bakacağız; hem doğal
# tutan videolara hem ücretli sponsorluk reklamları için."
#
# Yani referans kendi kreatiflerimiz DEĞİL. Doğru karar: elimizde 63 kreatif
# var, çoğu duraklatılmış ve reklam hesabı kapsamamız 1/3 -- kendi zayıf
# örneklemimizden kanca öğrenmek, kötü örnekten öğrenmek olurdu.
#
# 🔴 KALIP ALINIR, CÜMLE ALINMAZ. Hattın red team istemi zaten söylüyor:
# "'Rakip böyle diyor' bir gerekçe DEĞİLDİR: CeraVe'in dosyası onlara aittir,
# bize izin vermez." Rakibin kancası "Egzamam 3 günde geçti" ise öğrendiğimiz
# şey CÜMLE değil YAPI'dır: [kişisel dönüşüm + süre]. O yapı bizde yasak
# olduğu için havuzda `bize_uygun=False` diye işaretlenir ve senaryo
# üreticisine ÖRNEK olarak hiç gönderilmez.
KANCA_HAVUZU = Path(os.environ.get(
    "KREATIF_KANCA_HAVUZU", str(KOK / "state" / "kanca" / "havuz.json")))

KANCA_ACILARI = {"kanca_organik": "ORGANIK", "kanca_sponsorlu": "SPONSORLU"}

# Tırnak içi cümle: düz, eğik ve Türkçe tırnaklar.
_TIRNAK = re.compile(r"[\"“”„»«']([^\"“”„»«'\n]{12,160})[\"“”„»«']")

KANCA_SINIF_SISTEM = """Sen reklam kancalarını sınıflandıran bir analistsin.
Her kanca cümlesini ŞU türlerden birine sok:

SORU · MERAK · SAYI · ITIRAF · UYARI · TEKLIF · SOSYAL_KANIT · EMIR · DURUM

Ayrıca her kanca için `yapi` alanına, cümleyi ÜRÜNDEN BAĞIMSIZ kalıbına
indirgeyerek yaz. Örnek: "Egzamam 3 günde geçti" -> "[kişisel dönüşüm] +
[süre]". Kalıp, başka bir üründe yeniden kurulabilecek kadar soyut olmalı.

SADECE geçerli JSON döndür."""

KANCA_SINIF_ISTEK = """Şu kancaları sınıflandır:
{kancalar}

JSON şeması — birebir:
{{"kancalar": [{{"metin": "birebir cümle", "tur": "...", "yapi": "..."}}]}}"""


# --- ÜÇÜNCÜ KANCA KAYNAĞI: Meta Ad Library -------------------------------
#
# 🔴 NEDEN AYRI KAYNAK. Grounded arama kancayı ancak biri bir yazıda
# alıntılamışsa bulabiliyor; ölçüldü ki organik taraf bu yüzden boş geldi
# (havuzun 12/12'si sponsorluydu ve hepsi ikinci elden aktarımdı).
# Ad Library reklamın KENDİSİNİ veriyor: metni, kaç gündür yayında olduğunu
# ve videosunu.
#
# 🔴 "KAÇ GÜNDÜR YAYINDA" TEK DÜRÜST BAŞARI VEKİLİ. Meta ticari reklamlarda
# harcamayı ve gösterimi YAYINLAMIYOR (yalnız siyasi/AB reklamlarında var).
# Bir reklamın tuttuğunu gösteren tek kamuya açık sinyal, yayında kalma
# süresidir: kimse çalışmayan reklamı 30 gün döndürmez.
#
# 🔴 SERVİS YOKSA BRIEF DURMAZ. Bu bir zenginleştirme kaynağıdır, bağımlılık
# değil. Servis kapalıysa uyarı basılır ve hat grounded kancalarla devam eder.
KANCA_ADLIB_URL = os.environ.get("KANCA_ADLIB_URL", "http://127.0.0.1:3010")


def adlib_anahtar(kategori: str) -> str:
    """Ad Library için arama kelimesi üretir.

    🔴 ÜRÜN ADIYLA REKLAM KÜTÜPHANESİ ARANMAZ. Ölçüldü (21.09.2026):

        "EASYCOMB (Bebek ve Çocuklar İçin Saç Bakım Spreyi"  ->  0 reklam
        "Saç Bakım Spreyi"                                   -> 30 reklam
        "saç bakım"                                          -> 30 reklam

    Grounded arama (Gemini) uzun ve kirli bir kategori dizesini tolere edip
    yine de sonuç getiriyordu; Ad Library'nin araması ise DÜZ METİN eşleşmesi
    yapıyor ve kendi ürün adımız hiçbir rakip reklamında geçmiyor. Kaynak
    sessizce boş döndü ve havuza tek kanca eklemedi -- hata vermeden.

    Ders: aynı "kategori" dizesi iki kaynağa gönderiliyorsa, toleranslı olan
    kaynak hatayı gizler; katı olan kaynak sessizce boş döner.
    """
    ham = str(kategori or "")
    # Parantez içi varsa açıklayıcı kısım oradadır.
    ic = re.search(r"\(([^)]*)", ham)
    if ic and len(ic.group(1).strip()) > 8:
        ham = ic.group(1)
    ham = ham.split("|")[-1]
    ham = re.sub(r"[^\w\sÇĞİÖŞÜçğıöşü]+", " ", ham)
    kelimeler = [k for k in ham.split() if len(k) > 1]
    # Marka/ürün adı genelde başta ve BÜYÜK harflidir; sondaki tanımlayıcı
    # kelimeler ("Saç Bakım Spreyi") kategoriyi verir.
    kelimeler = [k for k in kelimeler if not (k.isupper() and len(k) > 3)]
    return " ".join(kelimeler[-3:]) if kelimeler else str(kategori or "")


def _trend_asamasi(gun: object) -> str:
    """Yayında kalma süresinden trend aşaması."""
    try:
        g = int(gun)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "BILINMIYOR"
    if g >= 30:
        return "SAVASTA_SINANMIS"
    if g >= 14:
        return "TUTUYOR"
    return "YENI_DENEME"


# --- DÖRDÜNCÜ KANCA KAYNAĞI: videoda KONUŞULAN cümle --------------------
#
# 🔴 YAZILI METİN İLE SÖYLENEN CÜMLE AYNI ŞEY DEĞİL. Ölçüldü (21.09.2026):
#
#   Propia Türkiye reklamı
#     yazılı   : "#reklam @propiaturkiye Saç dökülmesi başlayınca insan…"
#     söylenen : "Şuradaki bebek saçlarımın ne kadar örtüldüğüne bakar mısınız?"
#
# İzleyiciyi ilk 3 saniyede tutan ikincisidir ve grounded arama onu ASLA
# göremez -- hiçbir sayfada yazmıyor, videonun içinde konuşuluyor. Sahibin
# istediği "doğal tutan videolar" kancasının tek gerçek kaynağı budur.
#
# 🔴 AYRI VENV'DE, ALT SÜREÇ OLARAK. faster_whisper ana venv'e KURULMAZ.
# Ölçülen maliyet: model yükleme 6,9 sn (bir kez) + reklam başına ~3 sn
# (ffmpeg 0,3-0,7 sn + transkript 2,4-4,0 sn). Bu yüzden yalnız EN UZUN
# SÜREDİR YAYINDA olan videolar işlenir: sınırlı bütçe, sınanmış reklama.
SESLI_KANCA_BETIGI = Path(os.environ.get(
    "KANCA_SESLI_BETIK", "/opt/lcarlie/kanca-kaynaklari/sesli-kanca.py"))
SESLI_KANCA_PYTHON = Path(os.environ.get(
    "KANCA_SESLI_PYTHON", "/opt/lcarlie/kanca-kaynaklari/venv-kanca/bin/python"))


# --- BEŞİNCİ KANCA KAYNAĞI: gerçek ORGANİK video -------------------------
#
# 🔴 HAVUZDAKİ HER ŞEY ÜCRETLİ REKLAMDI. "SESLI" kancalar bile Ad Library
# videolarından geliyordu -- yani sponsorlu. Sahip iki kez "hem doğal tutan
# videolar" dedi ve o yarı gerçekten boştu.
#
# 🔴 BAŞARI ÖLÇÜSÜ BURADA DAHA İYİ. Ad Library ticari reklamda harcamayı
# gizliyor, orada tek vekilimiz "kaç gündür yayında"ydı. YouTube doğrudan
# İZLENME veriyor. Ölçülen aralık ("saç bakım spreyi", 21.09.2026):
# 44.256.995 · 12.565.672 · 1.383.081 · 78.333 · 7.556 · 189.
# Dört basamak fark var: eşiksiz "piyasa böyle yapıyor" demek, kimsenin
# izlemediği videoyu örnek almak olurdu.
ORGANIK_BETIGI = Path(os.environ.get(
    "KANCA_ORGANIK_BETIK", "/opt/lcarlie/kanca-kaynaklari/organik-kanca.py"))
ORGANIK_ASGARI_IZLENME = int(os.environ.get("KANCA_ASGARI_IZLENME", "20000"))


def organik_kancalar(kategoriler: list[str], azami: int = 5) -> list[dict]:
    """Tutan kısa organik videolardan konuşulan açılış cümlesi."""
    import subprocess

    if not (ORGANIK_BETIGI.exists() and SESLI_KANCA_PYTHON.exists()):
        print("  organik kanca: betik/venv yok, atlandı", file=sys.stderr)
        return []
    istek = {"kategoriler": kategoriler[:3], "azami": azami,
             "asgari_izlenme": ORGANIK_ASGARI_IZLENME}
    try:
        r = subprocess.run(
            [str(SESLI_KANCA_PYTHON), str(ORGANIK_BETIGI)],
            input=json.dumps(istek, ensure_ascii=False).encode("utf-8"),
            capture_output=True, timeout=900)
        veri = json.loads(r.stdout.decode("utf-8", "replace").strip() or "[]")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as hata:
        print(f"  organik kanca alınamadı: {str(hata)[:110]}", file=sys.stderr)
        return []
    if veri:
        en_yuksek = max(k.get("izlenme") or 0 for k in veri)
        print(f"  organik kanca: {len(veri)} video · en yüksek {en_yuksek:,} izlenme")
    else:
        print("  organik kanca: eşiği geçen video bulunamadı", file=sys.stderr)
    return veri


# --- ALTINCI KANCA KAYNAĞI: TikTok -------------------------------------
#
# 🔴 KİMLİK GEREKTİREN TEK KAYNAK. Altı ayrı yol ölçüldü (22.09.2026) ve
# hepsi bot tespitine takıldı: chromium headless · webkit (sistem
# bağımlılıkları kurulduktan sonra) · Xvfb ile headless=False ·
# yt-dlp hashtag sayfası · yt-dlp marka hesabı · grounded arama ile
# bağlantı toplama. TikTok sunucu IP'sinden gelen oturumsuz isteği boş
# döndürüyor. Kod sorunu değil, çerez sorunu.
#
# `ms_token` sağlanana kadar kaynak SESSİZCE atlanır -- ama log'a yazar.
# Havuz altı kaynaklı; biri kapalıysa diğerleri beslemeye devam eder.
TIKTOK_BETIGI = Path(os.environ.get(
    "KANCA_TIKTOK_BETIK", "/opt/lcarlie/kanca-kaynaklari/tiktok-kanca.py"))
TIKTOK_ASGARI_IZLENME = int(os.environ.get("KANCA_TIKTOK_ASGARI", "50000"))


def tiktok_etiketleri(kategori: str) -> list[str]:
    """Kategori ifadesinden TikTok etiketi üretir (boşluksuz, sadesi)."""
    duz = katla(kategori)
    kelimeler = [k for k in re.findall(r"[0-9a-zçğıöşü]+", duz) if len(k) > 2]
    if not kelimeler:
        return []
    etiketler = ["".join(kelimeler[-2:]), "".join(kelimeler[-3:])]
    return list(dict.fromkeys(e for e in etiketler if 3 < len(e) < 30))


def tiktok_kancalari(kategoriler: list[str], azami: int = 6) -> list[dict]:
    import subprocess

    if not (TIKTOK_BETIGI.exists() and SESLI_KANCA_PYTHON.exists()):
        return []
    etiketler: list[str] = []
    for k in kategoriler[:2]:
        etiketler.extend(tiktok_etiketleri(k))
    etiketler = list(dict.fromkeys(etiketler))[:3]
    if not etiketler:
        return []
    istek = {"etiketler": etiketler, "azami": azami,
             "asgari_izlenme": TIKTOK_ASGARI_IZLENME}
    try:
        r = subprocess.run(
            [str(SESLI_KANCA_PYTHON), str(TIKTOK_BETIGI)],
            input=json.dumps(istek, ensure_ascii=False).encode("utf-8"),
            capture_output=True, timeout=900)
        veri = json.loads(r.stdout.decode("utf-8", "replace").strip() or "[]")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as hata:
        print(f"  tiktok kancası alınamadı: {str(hata)[:110]}", file=sys.stderr)
        return []
    uyari = r.stderr.decode("utf-8", "replace").strip()
    if veri:
        print(f"  tiktok kancası: {len(veri)} video "
              f"(etiketler: {', '.join(etiketler)})")
    elif uyari:
        print(f"  tiktok: {uyari.splitlines()[-1][:120]}", file=sys.stderr)
    return veri


def sesli_kancalar(adlar: list[dict], azami: int = 6) -> list[dict]:
    """Videolu reklamlardan konuşulan kancayı çıkarır (alt süreç)."""
    import subprocess

    if not (SESLI_KANCA_BETIGI.exists() and SESLI_KANCA_PYTHON.exists()):
        print("  sesli kanca: betik/venv yok, atlandı", file=sys.stderr)
        return []
    # Sıralama: en uzun süredir yayında olan önce. Harcama gizli olduğu için
    # yayında kalma süresi tek başarı vekilidir; bütçeyi ona harcıyoruz.
    videolu = [a for a in adlar if a.get("video_url")]
    videolu.sort(key=lambda a: a.get("gun_sayisi") or 0, reverse=True)
    istek = [{"id": a.get("ad_id"), "url": a["video_url"], "marka": a.get("marka", "")}
             for a in videolu[:azami]]
    if not istek:
        return []
    try:
        r = subprocess.run(
            [str(SESLI_KANCA_PYTHON), str(SESLI_KANCA_BETIGI)],
            input=json.dumps(istek, ensure_ascii=False).encode("utf-8"),
            capture_output=True, timeout=600)
        veri = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as hata:
        print(f"  sesli kanca alınamadı: {str(hata)[:110]}", file=sys.stderr)
        return []
    gun = {a.get("ad_id"): a.get("gun_sayisi") for a in videolu}
    for k in veri:
        k["gun_sayisi"] = gun.get(k.get("id"))
        k["trend"] = _trend_asamasi(k["gun_sayisi"])
    print(f"  sesli kanca: {len(veri)} video çözümlendi")
    return veri


def adlib_kancalari(anahtar_kelime: str, ulke: str = "TR",
                    limit: int = 25, zaman_asimi: int = 240) -> list[dict]:
    """Ad Library'den reklam çeker; kanca = reklam metninin İLK cümlesi."""
    govde = json.dumps({"keyword": anahtar_kelime, "country": ulke,
                        "status": "ALL", "limit": limit}).encode("utf-8")
    istek = urllib.request.Request(
        f"{KANCA_ADLIB_URL}/api/scrape", data=govde,
        headers={"Content-Type": "application/json"})
    cikti: list[dict] = []
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as cevap:
            for ham in cevap:
                satir = ham.decode("utf-8", "replace").strip()
                if not satir.startswith("data:"):
                    continue
                try:
                    olay = json.loads(satir[5:].strip())
                except json.JSONDecodeError:
                    continue
                if olay.get("type") != "ad":
                    continue
                r = olay.get("data") or {}
                govdeler = r.get("body_variants") or []
                if not govdeler:
                    continue
                # Kanca = metnin ilk cümlesi/satırı.
                ilk = re.split(r"(?<=[.!?])\s+|\n", str(govdeler[0]).strip())[0]
                ilk = ilk.strip()
                if not (12 <= len(ilk) <= 200):
                    continue
                videolar = r.get("video_urls") or []
                cikti.append({
                    "metin": ilk,
                    "marka": str(r.get("advertiser_name") or "")[:80],
                    "gun_sayisi": r.get("days_running"),
                    "trend": _trend_asamasi(r.get("days_running")),
                    "video_var": bool(videolar),
                    "video_url": videolar[0] if videolar else "",
                    "ad_id": str(r.get("id") or ""),
                })
    except (urllib.error.URLError, OSError, TimeoutError) as hata:
        print(f"  ad library kaynağı yok ({str(hata)[:90]}) — grounded "
              f"kancalarla devam ediliyor", file=sys.stderr)
        return []
    return cikti


def transkript_kalitesi(metin: str) -> float:
    """Sözlükte BULUNAN kelimelerin oranı (0-1). hunspell yoksa 1.0.

    🔴 BOZUK TRANSKRİPT HAVUZA KANCA DİYE GİRİYORDU. Ölçüldü (22.09.2026,
    OGX reklamı): whisper "saç telini" yerine "saç dilini", "Bond Protein
    Repair" yerine "Saç Hüseyin Yeniler" yazdı. Bu cümleler senaryo
    üreticisine "piyasada kullanılan kanca" diye gidiyordu.

    Çare imla kapısı: transkriptte tanınmayan kelime oranı yüksekse cümle
    kancayı temsil etmiyor, gürültüyü temsil ediyor. Ad Library'nin YAZILI
    metinleri bu kapıdan zaten sorunsuz geçer (insan yazmış).
    """
    kelimeler = _IMLA_KELIME.findall(metin)
    if len(kelimeler) < 3:
        return 0.0
    supheli = imla_denetimi([metin])
    return 1.0 - (len(supheli) / len(kelimeler))


# Sözlükte bulunma oranı bu eşiğin altındaysa transkript kabul edilmez.
TRANSKRIPT_ESIGI = float(os.environ.get("KANCA_TRANSKRIPT_ESIGI", "0.75"))


def _havuz_oku() -> dict:
    try:
        return json.loads(KANCA_HAVUZU.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def kanca_topla(yonlendirici: ModelRouter, rakip: list[dict], kategori: str,
                guclu: bool = False, adlib_ac: bool = True,
                sesli_ac: bool = True, organik_ac: bool = True,
                tiktok_ac: bool = True,
                ek_kategoriler: list[str] | None = None) -> list[dict]:
    """Kanca açılarından tırnak içi cümleleri toplar, sınıflar, havuza yazar."""
    ham: list[tuple[str, str]] = []
    for r in rakip:
        tur = KANCA_ACILARI.get(str(r.get("aci") or ""))
        if not tur or not r.get("kaynaklar"):
            continue
        for c in _TIRNAK.findall(str(r.get("bulgu") or "")):
            c = c.strip()
            if c and not c.lower().startswith(("http", "www")):
                ham.append((tur, c))
    # Üçüncü kaynak: Ad Library. Grounded aramadan bağımsız çalışır --
    # biri boş dönse diğeri havuzu beslemeye devam eder.
    # 🔴 TEK KATEGORİYLE YETİNME. Bir ürün birden çok arama kelimesiyle
    # aranabilir ("saç bakım spreyi" · "saç açıcı sprey") ve her biri farklı
    # reklam havuzu getirir. Sahip "tek kaynak istemiyorum" derken kastettiği
    # çeşitlilik burada da geçerli.
    adlib = []
    if adlib_ac:
        gorulen: set[str] = set()
        # 🔴 Farklı kategori ifadeleri AYNI anahtar kelimeye indirgenebiliyor
        # ("durulanmayan saç bakım spreyi" ve "saç bakım spreyi" -> ikisi de
        # "sac bakim spreyi"). Ölçüldü: aynı arama iki kez koştu, 0 yeni
        # reklam getirdi. Anahtar kelime düzeyinde tekilleştiriyoruz.
        aranan: set[str] = set()
        for ham_kategori in (ek_kategoriler or [kategori])[:4]:
            kelime = adlib_anahtar(ham_kategori)
            if not kelime or kelime in aranan:
                continue
            aranan.add(kelime)
            bulunan = adlib_kancalari(kelime)
            yeni_olan = [b for b in bulunan if b["metin"] not in gorulen]
            gorulen.update(b["metin"] for b in yeni_olan)
            adlib.extend(yeni_olan)
            print(f"  ad library araması: '{kelime}' -> {len(bulunan)} reklam "
                  f"({len(yeni_olan)} yeni)")
    adlib_esleme = {a["metin"]: a for a in adlib}
    ham.extend(("ADLIB", a["metin"]) for a in adlib)

    # Dördüncü kaynak: videoda konuşulan cümle. Ad Library'nin verdiği
    # video URL'leri üzerinden çalışır; ayrı bir indirme yapmaz.
    sesli = sesli_kancalar(adlib) if (adlib_ac and sesli_ac) else []
    for s in sesli:
        adlib_esleme.setdefault(s["metin"], {
            "marka": s.get("marka", ""), "gun_sayisi": s.get("gun_sayisi"),
            "trend": s.get("trend", ""), "video_var": True})
    ham.extend(("SESLI", s["metin"]) for s in sesli)

    # Beşinci kaynak: gerçek organik. Diğer dördünden BAĞIMSIZ çalışır.
    organik = organik_kancalar(ek_kategoriler or [kategori]) if organik_ac else []
    for o in organik:
        adlib_esleme.setdefault(o["metin"], {
            "marka": o.get("kanal", ""), "izlenme": o.get("izlenme"),
            "video_var": True})
    ham.extend(("ORGANIK", o["metin"]) for o in organik)

    # Altıncı kaynak: TikTok (token yoksa sessizce boş döner).
    tiktok = tiktok_kancalari(ek_kategoriler or [kategori]) if tiktok_ac else []
    for tk in tiktok:
        adlib_esleme.setdefault(tk["metin"], {
            "marka": tk.get("kanal", ""), "izlenme": tk.get("izlenme"),
            "video_var": True})
    ham.extend(("TIKTOK", tk["metin"]) for tk in tiktok)

    if not ham:
        print("  kanca havuzu: hiçbir kaynaktan kanca gelmedi", file=sys.stderr)
        return []

    # 🔴 SES KAYNAKLI KANCALAR KALİTE KAPISINDAN GEÇER. Yazılı kaynaklar
    # (SPONSORLU/ADLIB) insan eliyle yazılmış, geçirilmez.
    elenen_kalite = 0
    suzulmus: list[tuple[str, str]] = []
    for tur, c in ham:
        if tur in ("SESLI", "ORGANIK", "TIKTOK"):
            oran = transkript_kalitesi(c)
            if oran < TRANSKRIPT_ESIGI:
                elenen_kalite += 1
                continue
        suzulmus.append((tur, c))
    if elenen_kalite:
        print(f"  transkript kalitesi: {elenen_kalite} kanca elendi "
              f"(eşik {TRANSKRIPT_ESIGI})", file=sys.stderr)
    ham = suzulmus

    havuz = _havuz_oku()
    # Aynı cümle iki koşuda tekrar gelebilir; havuz metne göre tekilleşir.
    yeni_ham = [(tur, c) for tur, c in ham if c not in havuz]
    siniflar: dict[str, dict] = {}
    if yeni_ham:
        veri, _ = _uret(yonlendirici, KANCA_SINIF_SISTEM,
                        KANCA_SINIF_ISTEK.format(
                            kancalar="\n".join(f"- {c}" for _t, c in yeni_ham[:40])),
                        2200, guclu=guclu)
        if isinstance(veri, dict):
            for k in veri.get("kancalar") or []:
                if isinstance(k, dict) and k.get("metin"):
                    siniflar[str(k["metin"]).strip()] = k

    eklenen = 0
    for tur, c in yeni_ham:
        s = siniflar.get(c, {})
        # 🔴 Rakibin kancası BİZİM mevzuatımızdan geçmek zorunda değil --
        # ama geçmiyorsa senaryo üreticisine ÖRNEK olarak gitmemeli.
        karar = uyum_denetimi(c)
        ek_alan = adlib_esleme.get(c, {})
        havuz[c] = {
            "kaynak_tur": tur,
            "kategori": kategori,
            # Ad Library'den gelenlerde ÖLÇÜLMÜŞ yayın süresi var; grounded
            # aramadan gelenlerde yok. İkisi aynı tabloda ama ayırt edilebilir.
            "marka": ek_alan.get("marka", ""),
            "gun_sayisi": ek_alan.get("gun_sayisi"),
            "trend": ek_alan.get("trend", ""),
            # Organik kaynakta başarı ölçüsü izlenme; ücretlide yayın süresi.
            # İkisi aynı sütuna SIKIŞTIRILMAZ -- farklı şeyler ölçüyorlar.
            "izlenme": ek_alan.get("izlenme"),
            "video_var": ek_alan.get("video_var", False),
            "tur": str(s.get("tur") or "SINIFLANMADI"),
            "yapi": str(s.get("yapi") or ""),
            "bize_uygun": not karar.blocked,
            "engel": karar.blocked[0].matched if karar.blocked else "",
            "toplandi": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
        eklenen += 1

    if eklenen:
        KANCA_HAVUZU.parent.mkdir(parents=True, exist_ok=True)
        KANCA_HAVUZU.write_text(json.dumps(havuz, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    uygun = sum(1 for v in havuz.values() if v["bize_uygun"])
    dagilim: dict[str, int] = {}
    for v in havuz.values():
        dagilim[v.get("kaynak_tur", "?")] = dagilim.get(v.get("kaynak_tur", "?"), 0) + 1
    sinanmis = sum(1 for v in havuz.values() if v.get("trend") == "SAVASTA_SINANMIS")
    print(f"  kanca havuzu: {len(havuz)} kanca (bu koşuda +{eklenen}) · "
          f"bize uygun {uygun} · mevzuata takılan {len(havuz) - uygun}")
    print(f"    kaynak dağılımı: {dagilim} · 30+ gündür yayında: {sinanmis}")
    return [dict(v, metin=k) for k, v in havuz.items()]


# --- KANCA KALIP KÜTÜPHANESİ ---------------------------------------------
#
# 🔴 KALIP ≠ ÖLÇÜLMÜŞ KANCA. Havuzdaki kancalar piyasada gerçekten yayınlanmış
# ve ölçülmüş cümleler (izlenme / kaç gündür yayında). Kalıplar ise sahibin
# verdiği 99 maddelik şablon listesi -- başarı verisi YOK. İkisi aynı listede
# gösterilirse "bu kanca tuttu" sanılır. Bu yüzden havuza KARIŞTIRILMAZ,
# senaryo istemine AYRI blok olarak gider.
#
# 🔴 99 KALIBIN 48'İ KOZMETİKTE YAPISAL OLARAK YASAK. Ölçüldü: kalıbın
# içindeki YER TUTUCU riski belirliyor. "[süre] sonra ne olur?" masum bir
# soru gibi durur ama kozmetikte doldurulduğu anda süre iddiası olur.
# Dağılım: sonuç vaadi 12 · sayı 11 · durum adı 7 · süre 7 · hasar-korku 6 ·
# otorite itibarsızlaştırma 5 · mucize 4 · rakip kötüleme 3.
# Yasak olanlar modele HİÇ GÖNDERİLMEZ -- gönderilip "kullanma" demek,
# kullanmasını istemekle aynı kapıya çıkıyor.
KALIP_DOSYASI = Path(os.environ.get(
    "KREATIF_KANCA_KALIP", str(KOK / "varliklar" / "kanca-kaliplari.json")))


def kanca_kaliplari(azami: int = 18) -> str:
    """Kozmetikte kullanılabilir kalıplar; yasak olanlar hiç dönmez."""
    try:
        veri = json.loads(KALIP_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    uygun = [(k, v) for k, v in veri.items() if v.get("kozmetik_uygun")]
    if not uygun:
        return ""
    uygun.sort(key=lambda kv: kv[1].get("no") or 0)
    # Listenin her yerinden örnek al; baştaki 18'i almak tek tip kanca verir.
    adim = max(1, len(uygun) // azami)
    secilen = uygun[::adim][:azami]
    return "\n".join(f"- {k}" for k, _v in secilen)


def kanca_ornekleri(havuz: list[dict], azami: int = 14) -> str:
    """Senaryo üreticisine gidecek örnekler — YALNIZ bize uygun olanlar."""
    uygun = [h for h in havuz if h.get("bize_uygun")]
    if not uygun:
        return "(havuzda bize uygun kanca yok)"
    # Tür çeşitliliği: aynı türden yığılma olmasın.
    gruplar: dict[str, list[dict]] = {}
    for h in uygun:
        gruplar.setdefault(h.get("tur") or "?", []).append(h)
    sirali: list[dict] = []
    while len(sirali) < azami and any(gruplar.values()):
        for tur in list(gruplar):
            if gruplar[tur]:
                sirali.append(gruplar[tur].pop(0))
            if len(sirali) >= azami:
                break
    return "\n".join(
        f"- [{h['kaynak_tur']}/{h.get('tur')}"
        + (f"/{h['trend']}" if h.get("trend") else "")
        + (f"/{h['izlenme']:,} izlenme" if h.get("izlenme") else "")
        + f"] {h['metin']}"
        + (f"  → kalıp: {h['yapi']}" if h.get("yapi") else "")
        for h in sirali)


def kanit_kur(ozet: dict, zarar: list, fiyat_konumu: dict, kurul: list,
              kreatifler: list, tutarlilik: list, rakip: list) -> str:
    """Modele gidecek kanıt paketi — bütçeye BİLEŞEN KISALTARAK sığdırılır.

    🔴 ÖNCEDEN `json.dumps(...)[:14000]` YAZIYORDU VE ÜRETİMDE PATLADI.
    Dördüncü rakip açısı (rakip kreatifi) ve 15 departman görüşü eklenince
    paket bütçeyi aştı; dilimleme JSON'u BİR DİZENİN ORTASINDAN kesti ve
    modele sözdizimi bozuk bir kanıt gitti. Sonuç: "konumlandırma
    üretilemedi" -- sebebi görünmeden.

    Ders: bir JSON belgesini karakterden kesmek onu BOZAR. Sığdırma, belgenin
    İÇİNDEKİ alanları kısaltarak yapılır; belge her zaman geçerli kalır.

    Kısaltma sırası önem sırasının TERSİDİR: önce rakip metinleri (uzun ve
    tekrarlı), sonra kendi eski reklam gövdelerimiz, en son ekip cümleleri.
    Ürün gerçeği ve fiyat ölçümü HİÇ kısaltılmaz -- brief onların üstüne kurulu.
    """
    def paket(rakip_sinir: int, govde_sinir: int, kurul_sinir: int) -> str:
        return json.dumps({
            "urun": ozet,
            "zararina_satislar": zarar,
            "fiyat_konumu_olcumu": fiyat_konumu,
            "ekip_gorusu": [{"uye": k["uye"], "soyledigi":
                             k["soyledigi"][:kurul_sinir]} for k in kurul],
            "kendi_kreatiflerimiz": [
                {"ad": k.get("ad_adi"), "durum": k.get("etkin_durum"),
                 "govde": str(k.get("govde") or "")[:govde_sinir]}
                for k in kreatifler],
            "tutarlilik_hatalari": tutarlilik,
            "rakip_bulgulari": [{"aci": r.get("aci"), "seviye": r.get("seviye"),
                                 "bulgu": str(r.get("bulgu") or "")[:rakip_sinir]}
                                for r in rakip],
        }, ensure_ascii=False)

    for rakip_sinir, govde_sinir, kurul_sinir in (
            (2600, 400, 260), (1800, 300, 200), (1200, 200, 150), (700, 120, 100)):
        metin = paket(rakip_sinir, govde_sinir, kurul_sinir)
        if len(metin) <= KANIT_BUTCESI:
            return metin
    # Hâlâ sığmıyorsa rakip sayısını azalt; yine de GEÇERLİ JSON döner.
    rakip = rakip[:2]
    return paket(700, 120, 100)


def _json_cek(metin: str) -> dict | list | None:
    metin = metin.strip()
    if metin.startswith("```"):
        parcalar = metin.split("```")
        if len(parcalar) > 1:
            metin = parcalar[1].removeprefix("json").strip()
    for kalip in (r"\{.*\}", r"\[.*\]"):
        e = re.search(kalip, metin, re.S)
        if e:
            try:
                return json.loads(e.group(0))
            except json.JSONDecodeError:
                continue
    return None


def SENARYO_BUTCESI(adet: int) -> int:
    """Senaryo aşamasının token bütçesi — senaryo SAYISINA göre ölçeklenir.

    🔴 SABİT 4000 TOKEN ÜRETİMDE SESSİZCE BAŞARISIZ OLDU.
    Ölçüldü (21.09.2026, BABY RESCUE, zamanlayıcı testi): model senaryoları
    ÜRETTİ -- cevap 9.213 karakterdi ve düzgün başlıyordu
    (`{"senaryolar": [{"ad": "Sabah Telaşında..."`) -- ama token sınırında
    KESİLDİ, JSON yarım kaldı ve `_json_cek` None döndü. Brief'e
    "UGC senaryosu: 0" yazıldı; bu satır normal bir sonuç gibi görünüyor.
    Zamanlayıcı varsayılanı `--senaryo 3` olduğu için, fark edilmeseydi
    HER ÜRÜNDE sıfır senaryo üretilecekti.

    Ders: bir aşamanın çıktısı "boş" ise bu, modelin bir şey söylememesi
    değil, söylediğinin kaybolması olabilir. Boş sonuç sessiz kalmamalı.

    Bir senaryo ~2.600 token (sahne tablosu + konuşma metni + çekim notu).
    Üstüne JSON iskeleti için sabit pay eklenir.
    """
    return min(16000, 2600 * max(1, adet) + 2000)


# Bu koşuda hangi aşama hangi model kademesini kullandı.
KADEME_KAYDI: list[str] = []


def _uret(yonlendirici: ModelRouter, sistem: str, istek: str,
          azami: int = 2400, guclu: bool = False) -> tuple[dict | list | None, str]:
    """guclu=True: dış (güçlü) sağlayıcı ÖNCE denenir.

    🔴 Kreatif metin, hızdan çok dil gücü isteyen bir iş. Ölçüldü
    (21.09.2026, EASYCOMB): yerel 4B model senaryoyu üretti ama Türkçesi
    kullanılamazdı -- "elimizi kırparız", "nazik bakımlaşır",
    "saçını sıkıştırmakta zorlanma". İskele değil, model kademesi sorunu.

    🔴 Ama bu anahtar ÜCRET doğurur (model_layer: escalate ücretli
    sağlayıcıya kadar iner) ve haftalık parti 36 ürün koşar. Varsayılan
    KAPALI; açmak sahibin kararı.
    """
    sonuc, kademe, _cagri = yonlendirici.generate(
        [{"role": "system", "content": sistem},
         {"role": "user", "content": istek}], azami, escalate=guclu,
        is_anahtari="kreatif_brief")
    KADEME_KAYDI.append(kademe)
    # 🔴 GÜÇLÜ MODEL SESSİZCE YERELE DÜŞÜYOR. Ölçüldü (22.09.2026, EASYCOMB):
    # `--guclu` açıkken 6 çağrının 2'si LOCAL_GPU'ya düştü. Zincirin yerele
    # inmesi tasarım gereği DOĞRU davranış -- ama brief'e bakan bunu
    # göremiyordu: aynı dosyada bazı bölümler güçlü modelin, bazıları 4B
    # yerel modelin işiydi ve aradaki Türkçe farkı "model kötü yazmış" gibi
    # görünüyordu. Düşüş bir arıza değil bir DURUM; görünmez kalırsa kalite
    # dalgalanmasının sebebi hiç anlaşılmaz.
    if guclu and kademe != "EXTERNAL_MODEL":
        print(f"    🔴 GÜÇLÜ MODEL İSTENDİ AMA '{kademe}' KULLANILDI — "
              f"bu bölümün dil kalitesi düşük olabilir", file=sys.stderr)
    else:
        print(f"    model kademesi: {kademe}", file=sys.stderr)
    ham = sonuc.get("text") or ""
    veri = _json_cek(ham)
    if veri is None:
        # 🔴 SESSİZ BAŞARISIZLIK YASAK. Önceden yalnız "üretilemedi" yazıyordu
        # ve sebebi görünmüyordu: kanıt mı şişti, model mi düzyazı yazdı, çıktı
        # mı kesildi -- üçü de aynı boş satırı veriyordu. İstem uzunluğu ve ham
        # cevabın başı basılır ki teşhis ölçümle konsun.
        print(f"    JSON çıkmadı · istem {len(istek)} karakter · "
              f"cevap {len(ham)} karakter · başı: {ham[:180]!r}",
              file=sys.stderr)
    return veri, ham


# İKİNCİ KAPI — DAYANAKSIZ İDDİA
#
# 🔴 NEDEN AYRI BİR KAPI GEREKTİ. jarvis.compliance mevzuata aykırı ifadeyi
# yakalar ("sivilce geçirir"). Ama ölçüldü ki model, YASAL AMA KANITSIZ
# cümleler de üretiyor ve bunlar kapıdan geçiyor:
#     "pilling (topaklanma) riski yoktur"      <- test edilmedi, bilmiyoruz
#     "3-4 saat boyunca kuruma riski azalır"   <- bu süre nereden çıktı?
#     "su bazlı formülle"                      <- ürün kaydında yazmıyor
#     "50 ml'de 24 TL"                         <- 24 bizim TL/ml HESABIMIZDI,
#                                                 reklamda ÜRÜN FİYATI okunur
# Bunlar mevzuat ihlali değil; DOĞRULANAMAZ İDDİA. Reklamda iddia edilen her
# performans, istendiğinde belgelenebilmek zorundadır. Belgemiz yoksa cümle
# kurulmaz.
#
# Kapı iki şey arar:
#   A) ürün kaydında GEÇMEYEN bir sayı (süre, oran, fiyat)
#   B) belge isteyen performans ifadeleri (aşağıdaki liste)

DAYANAK_GEREKTIREN = (
    ("pilling", "topaklanma testi yapılmadı"),
    ("topaklan", "topaklanma testi yapılmadı"),
    ("gozenekleri tikamaz", "komedojenite testi yok"),
    ("gozenek tikamaz", "komedojenite testi yok"),
    ("komedojen", "komedojenite testi yok"),
    ("su bazli", "formül tanımı ürün kaydında yok"),
    ("dermatolog", "dermatolog onayı belgesi yok"),
    ("hipoalerjen", "alerji testi belgesi yok"),
    ("test edilmis", "test kaydı yok"),
    ("klinik", "klinik çalışma yok"),
    ("saat boyunca", "süre iddiası ölçülmedi"),
    ("saat kalici", "süre iddiası ölçülmedi"),
)

_SAYI = re.compile(r"\d+(?:[.,]\d+)?")

# ÜRÜNDE OLMAYAN İŞLEV — seramid yakalayan kuralın işlevlere uygulanmışı.
#
# 🔴 ÜRETİMDE YAKALANDI VE TESLİM EDİLMİŞ BİR JPEG'E BASILDI:
#     "Güneşten korunur, cilt daha yumuşak"   <- HYDRAVIE'de SPF YOK
#     "Yüksek Etkili Formül"                  <- etkinlik derecesi ölçülmedi
#     "Maliyetli, cilt üzerinde etkili"       <- reklamda "pahalı" yazıyor;
#                                                fiyat kanıtı kreatife sızmış
# Kural şu: aşağıdaki işlev sözcüklerinden biri metinde geçiyorsa, AYNI
# sözcük ÜRÜN KAYDINDA da geçmek zorundadır. Geçmiyorsa ürünün sahip olmadığı
# bir işlev iddia ediliyordur.
ISLEV_TERIMLERI = (
    "gunes", "spf", "uv", "koruma faktoru", "leke", "kirisik", "yaslanma",
    "anti-aging", "sikilas", "beyazlat", "aydinlat", "arindir", "matlas",
    "gozenek sikilas", "kepek", "dokulme", "selulit", "cilt tonu esitle",
)

# Ölçülmemiş etkinlik derecesi. "Etkili" demek serbest değildir: derece
# iddiası (yüksek/güçlü/en) karşılaştırmalı etkinlik testi ister.
DERECE_IDDIASI = (
    "yuksek etkili", "cok etkili", "en etkili", "guclu etki", "maksimum",
    "ustun etki", "yogun etkili", "maliyetli",
)

# 🔴 OLUMSUZLAMA DA BİR İDDİADIR — ve kelime listesiyle yakalanamaz.
# Ölçüldü: "riski yoktur" ve "yapmaz" listedeydi, ama model şunları yazdı ve
# üçü de listeden kaçtı:
#     "Ciltte Soyulma Riski YOK"        (yoktur değil, yok)
#     "Gözenekleri TIKARMAZ"            (yazım hatası, tıkamaz değil)
#     "Ciltte dökülme OLMAZ"            (listede olmayan fiil)
# Liste kovalamak yerine Türkçe'nin kendi kuralı kullanılır: GENİŞ ZAMAN
# OLUMSUZ EKİ (-maz / -mez). "yapmaz, olmaz, tıkamaz, tıkarmaz, dökülmez"
# hepsi bu kalıba düşer. Reklam metninde bu ek, neredeyse her zaman
# "şu olumsuz etki olmayacak" taahhüdüdür ve belge ister.
#
# Yanlış alarm riski kabul edildi ve yön bilinçli seçildi: fazladan silinen
# cümlenin bedeli bir cümle, kaçan cümlenin bedeli belgelenemeyen bir reklam
# iddiasıdır.
_OLUMSUZ_TAAHHUT = (
    (re.compile(r"\b[a-zçğıöşü]{2,}m[ae]z\b"),
     "geniş zaman olumsuz eki (-maz/-mez): olumsuz etkinin olmayacağı "
     "taahhüdüdür, belge ister"),
    (re.compile(r"\brisk[a-zçğıöşü]*\s+(yok|bulunm)"),
     "risk yokluğu iddiası belge ister"),
    # 🔴 İKİNCİ SIZINTI, ÜRETİMDE YAKALANDI: "ciltte yapışkanlık hissi YOKTUR"
    # kareye basıldı. -maz/-mez kalıbına düşmüyor, "risk" sözcüğü de geçmiyor;
    # ama anlamı aynı: test edilmemiş bir olumsuz etkinin yokluğu taahhüdü.
    (re.compile(r"\b(yoktur|bulunmaz|bulunmamakta[a-zçğıöşü]*)\b"),
     "olumsuz etkinin yokluğu taahhüdü: belge ister"),
    (re.compile(r"\b(hissi|etkisi|kokusu|izi|kalintisi)\s+yok\b"),
     "olumsuz etkinin yokluğu taahhüdü: belge ister"),
)


# 🔴 İKİ KAPI DAHA — ikisi de ÜRETİMDE yakalanan gerçek cümlelerden doğdu.
#
# (a) OLUMSUZLAMANIN "DEĞİL"Lİ HÂLİ. Mevcut kural geniş zaman olumsuz ekini
#     (-maz/-mez) yakalıyordu ama "Kimyasal sprey DEĞİL" cümlesi ekten
#     kaçtı. Yasak olan ek değil, kalıp: yasal olarak kullanılabilen bir
#     madde sınıfının yokluğunu üstünlük diye sunmak (adillik kriteri --
#     belge kurtarmaz). "içermez", "yoktur", "değil" aynı kapıya girer.
#
# (b) UYARIYI İDDİAYA ÇEVİRMEK. Kılavuzun 2. kuralı "uyarı cümlesi iddia
#     değildir, silinmez" der. Tersi de doğrudur ve ihlaldir: uyarıyı SATIŞ
#     VAADİNE çevirmek. Ölçülen cümle: kutuda "Yeni doğanlarda doktor
#     önerisi ile kullanılmalıdır" (kısıt) yazarken model "Yeni doğanlara da
#     uygun, doktor önerisiyle başlayabilir" (vaat + doktor otoritesi) yazdı.
#     Kısıt, kapsam genişletmesine dönüştürüldü.
UYARIYI_IDDIAYA = (
    # 🔴 ARAYA KELİME GİRER. İlk kalıp yasak sözcüğün HEMEN ardından
    # olumsuzlama bekliyordu ve "Kimyasal SPREY değil" kaçtı -- araya bir
    # ad girmişti. En fazla üç kelime tolere edilir; daha fazlası ayrı cümle
    # sayılır ve yanlış pozitif üretir.
    (re.compile(r"\b(?:kimyasal|paraben|silikon|sls|sülfat|alkol|katkı|"
                r"koruyucu|boya)\w*(?:\s+\w+){0,3}\s+(?:içermeyen|"
                r"içermez|yoktur|değil(?:dir)?)", re.IGNORECASE),
     "yasal olarak kullanılabilen bir madde sınıfının yokluğu üstünlük "
     "olarak sunulamaz -- adillik kriteri, belge kurtarmaz"),
    (re.compile(r"\b(?:yeni\s*doğan|bebek)\w*\s+(?:için\s+)?(?:de\s+)?"
                r"(?:uygun|kullanılabilir|güvenli)", re.IGNORECASE),
     "kutudaki kısıt ('yeni doğanlarda doktor önerisi ile kullanılmalıdır') "
     "kapsam genişleten bir vaade çevrilmiş"),
    (re.compile(r"\bdoktor\s+(?:öneri|tavsiye|onay)\w*\s+(?:ile\s+)?"
                r"(?:başlay|kullanab|uygun)", re.IGNORECASE),
     "uyarı cümlesindeki doktor ibaresi satış vaadine ve otorite "
     "aktarımına çevrilmiş"),
)


def uyari_iddia_kapisi(cumle: str, alan: str) -> dict | None:
    for kalip, gerekce in UYARIYI_IDDIAYA:
        es = kalip.search(cumle)
        if es:
            return {"alan": alan, "cumle": cumle, "tur": "uyarı iddiaya çevrilmiş",
                    "yakalanan": es.group(0), "gerekce": gerekce}
    return None


# --------------------------------------------------------------------------
# KİTLE KAPISI — yanlış kitleye konuşan cümle
# --------------------------------------------------------------------------
#
# 🔴 MODELE RİCA ETMEK YETMEDİ, ÖLÇÜLDÜ. EASYCOMB'un kitlesi 22.09.2026'da
# yetişkine çevrildi. `gercek_kitle` alanı kanıta girdi, hem KONUM_SISTEM hem
# SENARYO_SISTEM "kime konuştuğunu kanıttan al, ürün adından değil" diye şart
# koştu, log da üstyazımı bastı. Model YİNE çocuk senaryosu yazdı:
#
#     "Kime: Çocuklarının saçını nazikçe taramak isteyen yetişkin ebeveynler"
#     "Sabah uyandıktan sonra çocuğun saç derisi rahatsız..."
#
# Sebep basit: ürün adı ("Bebek ve Çocuklar İçin Saç Bakım Spreyi"), Wix
# açıklaması ve kutu metni kanıt paketinde ONLARCA KEZ "bebek/çocuk" diyor.
# Tek satırlık kitle notu bu ağırlığa yeniliyor. İstem bir TERCİH bildirir;
# kapı bir KURAL uygular.
#
# Yasak sözcükler ürün başına `urun-kitle.json` içinde `yasak_kurgu`
# alanında durur -- koda gömülmez, çünkü hangi kurgunun yanlış olduğu ürünün
# konumlandırmasına bağlı.
def kitle_kapisi(cumle: str, yasak_kurgu: list[str], alan: str) -> dict | None:
    if not yasak_kurgu or not cumle:
        return None
    duz = katla(cumle)
    for k in yasak_kurgu:
        anahtar = katla(str(k))
        if not anahtar:
            continue
        # 🔴 ÜNSÜZ YUMUŞAMASI. Türkçede k/p/t/ç ile biten kök ek alınca
        # yumuşar: çocuk -> çocuĞun, kitap -> kitaBı. Kökü olduğu gibi
        # aramak çekimli hâli KAÇIRIR. Ölçüldü: "çocuğun saç derisi"
        # cümlesi "çocuk" kalıbına takılmadı.
        # Bkz. [[turkce-metin-eslesme-tuzagi]]
        govdeler = {anahtar}
        YUMUSAMA = {"k": "g", "p": "b", "t": "d", "c": "c"}
        if anahtar[-1] in YUMUSAMA:
            govdeler.add(anahtar[:-1] + YUMUSAMA[anahtar[-1]])
        kalip = "|".join(re.escape(g) for g in sorted(govdeler))
        if re.search(r"\b(?:" + kalip + ")", duz):
            return {"alan": alan, "cumle": cumle, "tur": "yanlış kitle",
                    "yakalanan": str(k),
                    "gerekce": "ürünün konumlandırıldığı kitle bu değil; "
                               "kanıttaki gercek_kitle alanına bak"}
    return None


def dayanak_kapisi(cumle: str, urun_metni: str, izinli_sayilar: set[str],
                   alan: str) -> dict | None:
    """Kanıtta karşılığı olmayan iddiayı yakalar. Mevzuattan AYRI bir kapıdır."""
    duz = katla(cumle)
    for ifade, gerekce in DAYANAK_GEREKTIREN:
        if ifade in duz:
            return {"alan": alan, "cumle": cumle, "tur": "dayanaksız iddia",
                    "yakalanan": ifade, "gerekce": gerekce}
    # katla() aksanı söktüğü için kalıplar aksansız yazılmıştır; yine de
    # özgün metinde arayıp yakalanan sözcüğü OLDUĞU GİBİ raporlarız.
    urun_duz = katla(urun_metni)
    for kalip, gerekce in _OLUMSUZ_TAAHHUT:
        es = kalip.search(cumle.casefold()) or kalip.search(duz)
        if es:
            # 🔴 ONAYLI KAYNAK MUAFİYETİ.
            #
            # Geniş zaman olumsuz eki kuralı (-maz/-mez) doğru kuruldu ve
            # gerçek ihlalleri yakaladı: "Gözenekleri tıkarmaz", "Soyulma
            # riski yok", "yapışkanlık hissi yoktur". Hepsinin ortak yanı:
            # MODELİN UYDURDUĞU, hiçbir belgeye dayanmayan olumsuz taahhüt.
            #
            # Ama kural, ürünün ONAYLI kutu metninde birebir yazan kullanım
            # bilgisini de kesiyordu. Ölçüldü (21.09.2026, EASYCOMB): kutuda
            # "Durulama gerektirmez." yazıyor -- bu bir taahhüt değil, kullanım
            # talimatı. Kapı onu ekran yazısından SİLDİ.
            #
            # Muafiyet dar tutulur: yakalanan sözcük ürünün onaylı metninde
            # GEÇİYORSA geçilir. Uydurulmuş olumsuzlama zaten orada geçmez --
            # yukarıdaki üç gerçek ihlalin hiçbiri bu muafiyetten faydalanamaz.
            if katla(es.group(0)) in urun_duz:
                continue
            return {"alan": alan, "cumle": cumle, "tur": "olumsuz taahhüt",
                    "yakalanan": es.group(0), "gerekce": gerekce}
    for terim in DERECE_IDDIASI:
        if terim in duz:
            return {"alan": alan, "cumle": cumle, "tur": "ölçülmemiş derece",
                    "yakalanan": terim,
                    "gerekce": "etkinlik derecesi iddiası karşılaştırmalı test ister"}
    for islev in ISLEV_TERIMLERI:
        if islev in duz and islev not in urun_duz:
            return {"alan": alan, "cumle": cumle, "tur": "üründe olmayan işlev",
                    "yakalanan": islev,
                    "gerekce": f"'{islev}' ürün kaydında geçmiyor; ürünün sahip "
                               "olmadığı bir işlev iddia ediliyor"}
    for sayi in _SAYI.findall(cumle):
        normal = sayi.replace(",", ".").rstrip("0").rstrip(".") or sayi
        if normal in izinli_sayilar or sayi in izinli_sayilar:
            continue
        if sayi in urun_duz or normal in urun_duz:
            continue
        return {"alan": alan, "cumle": cumle, "tur": "kanıtsız sayı",
                "yakalanan": sayi,
                "gerekce": "bu sayı ürün kaydında geçmiyor; süre/oran/fiyat "
                           "iddiası ölçülmeden yazılamaz"}
    return None


# Ürüne özgü yasak kurgu sözcükleri; main() doldurur.
YASAK_KURGU: list[str] = []


def _denetle(cumle: str, alan: str, urun_metni: str = "",
             izinli_sayilar: set[str] | None = None) -> dict | None:
    """Tek cümleyi kapılardan geçirir; takılırsa silme kaydını döndürür."""
    kitle = kitle_kapisi(cumle, YASAK_KURGU, alan)
    if kitle:
        return kitle
    uyari = uyari_iddia_kapisi(cumle, alan)
    if uyari:
        return uyari
    karar = uyum_denetimi(cumle)
    if karar.blocked:
        b = karar.blocked[0]
        return {"alan": alan, "cumle": cumle, "tur": "mevzuat", "kural": b.rule,
                "yakalanan": b.matched, "dayanak": b.basis, "gerekce": b.remedy}
    if urun_metni:
        return dayanak_kapisi(cumle, urun_metni, izinli_sayilar or set(), alan)
    return None


def red_team_kapisi(red: dict, urun_metni: str = "",
                    izinli_sayilar: set[str] | None = None) -> tuple[dict, list[dict]]:
    """Red team'in ÖNERDİĞİ düzeltmeleri de denetimden geçirir.

    🔴 EN TEHLİKELİ AÇIK BURASIYDI. Ölçüldü: red team, "rakipler böyle
    diyor" gerekçesiyle şu düzeltmeleri önerdi --
      "Niacinamide ... KLİNİK OLARAK KANITLANMIŞ katkı sağlar"
      "Squalane ve Panthenol, CİLT BARİYERİNİ GÜÇLENDİRİR"
    Bunlar bizim için yasak ifadeler. Rakibin CeraVe ya da La Roche-Posay
    olması onlara dosya/ruhsat verir, bize izin vermez. Red team'in çıktısı
    "düzeltme" etiketiyle geldiği için doğrudan metne kopyalanmaya en yatkın
    yerdir; o yüzden kreatifin kendisiyle AYNI kapıdan geçer.
    """
    silinen: list[dict] = []
    temiz: list[dict] = []
    for itiraz in red.get("itirazlar") or []:
        if not isinstance(itiraz, dict):
            continue
        duzeltme = str(itiraz.get("duzeltme") or "")
        kayit = (_denetle(duzeltme, "red_team.duzeltme", urun_metni, izinli_sayilar)
                 if duzeltme else None)
        if kayit:
            itiraz = dict(itiraz)
            itiraz["duzeltme_reddedildi"] = duzeltme
            itiraz["duzeltme"] = ("🔴 Red team'in önerdiği düzeltme mevzuat "
                                  f"kapısından geçmedi ({kayit['yakalanan']}). "
                                  "İtiraz geçerli olabilir ama bu çözüm kullanılamaz.")
            silinen.append(kayit)
        temiz.append(itiraz)
    return {"itirazlar": temiz}, silinen


def mevzuat_kapisi(brief: dict, urun_metni: str = "",
                   izinli_sayilar: set[str] | None = None) -> tuple[dict, list[dict]]:
    """Modelin yazdığı HER müşteriye gidecek cümleyi denetimden geçirir.

    🔴 Bloklu cümle brief'ten ATILIR, uyarıyla bırakılmaz. Uyarıyla bırakılan
    cümle er geç kopyalanıp yayına girer; istemde 'yazma' demek yeterli
    değildir, kod silmelidir.
    """
    silinen = []
    temiz = dict(brief)
    for alan in ("satis_cumleleri", "baslik_onerileri", "ayrisma"):
        kalanlar = []
        for cumle in brief.get(alan) or []:
            if not isinstance(cumle, str):
                continue
            kayit = _denetle(cumle, alan, urun_metni, izinli_sayilar)
            (silinen.append(kayit) if kayit else kalanlar.append(cumle))
        temiz[alan] = kalanlar
    # Alıcı itirazının CEVABI da müşteriye gider; itiraz metni gitmez.
    kalan_itiraz = []
    for i in brief.get("alici_itirazi") or []:
        if not isinstance(i, dict):
            continue
        kayit = _denetle(str(i.get("cevap") or ""), "alici_itirazi.cevap",
                         urun_metni, izinli_sayilar)
        if kayit:
            silinen.append(kayit)
        else:
            kalan_itiraz.append(i)
    temiz["alici_itirazi"] = kalan_itiraz
    return temiz, silinen


# --------------------------------------------------------------------------
# 5) GÖRSEL — SAHNE İSTEMİ + YERLEŞİM ŞARTNAMESİ
# --------------------------------------------------------------------------

# 🔴 BU CÜMLE KOD TARAFINDAN HER İSTEME EKLENİR. Modelden istenmez.
# Sebebi ölçüldü: sahibin kararı ambalajın AI'ya yeniden çizdirilmemesi.
# Bir image modeli "ürün koyma" talimatını unutabilir; bu satır unutmaz.
MUHUR = (
    "NEGATIVE — MUST NOT APPEAR IN THE IMAGE: no product, no bottle, no jar, "
    "no tube, no pump, no cosmetic container of any kind, no packaging, no "
    "label, no logo, no brand mark, no text, no letters, no numbers, no "
    "typography, no watermark, no signage, no hands holding a product. "
    "This image is a BACKGROUND PLATE ONLY. The real product photograph and "
    "all typography will be composited on top afterwards."
)

GORSEL_SISTEM = """Sen bir reklam sanat yönetmenisin. Image modeli (Gemini /
ChatGPT / Midjourney) için ARKA PLAN SAHNESİ istemi yazarsın.

🔴 MUTLAK KURAL: Ürünü, ambalajı, şişeyi, kavanozu, etiketi, logoyu ve HİÇBİR
YAZIYI tarif etme. Bunlar sonradan gerçek fotoğraftan üstüne dizilecek.
Sen yalnızca ARKA PLANI, ışığı, yüzeyi, atmosferi ve ürünün oturacağı BOŞ
ALANI tarif edersin.

İstemleri İNGİLİZCE yaz (image modelleri İngilizce'de daha isabetli).
Her sahne ölçülü, gerçekçi ve premium olsun; çizgi film, 3D render, illüstrasyon
ve stok-fotoğraf klişesi istemiyorum.

SADECE geçerli JSON döndür."""

GORSEL_ISTEK = """{urun} için {adet} farklı reklam görseli sahnesi tasarla.
Her sahne aşağıdaki kreatif brief'teki FARKLI bir satış açısını görselleştirsin.

🔴 KAREYE YAZI YAZMIYORSUN, SEÇİYORSUN. Karede görünecek metin yalnızca
aşağıdaki ONAYLI listelerden numarayla seçilir. Kendi cümleni yazarsan iş
reddedilir — o cümleler denetimden geçmemiştir ve basılmış bir görselden
geri alınamaz.

ONAYLI BAŞLIKLAR (ust_yazi_no için):
{basliklar}

ONAYLI CÜMLELER (alt_yazi_no için):
{cumleler}

KREATİF BRIEF:
{brief}

JSON şeması — birebir:
{{"gorseller": [
  {{"ad": "Sahne adı, Türkçe",
    "hangi_aci": "Brief'teki hangi satış açısını karşılıyor",
    "sahne_istemi": "İNGİLİZCE image modeli istemi. SADECE arka plan, yüzey, ışık, renk, atmosfer, kompozisyon. Ürün/yazı/logo YOK. 60-90 kelime.",
    "urun_yerlesimi": "Gerçek ürün fotoğrafı karenin neresine konacak (ör: 'alt orta, yüzeyin üstünde, %38 yükseklik')",
    "bos_alan": "Sahnede yazı için boş bırakılacak bölge (ör: 'üst üçte bir, düz koyu yüzey')",
    "ust_yazi_no": "Aşağıdaki ONAYLI BAŞLIKLAR listesinden bir numara (0'dan başlar). YENİ CÜMLE YAZMA.",
    "alt_yazi_no": "Aşağıdaki ONAYLI CÜMLELER listesinden bir numara (0'dan başlar). YENİ CÜMLE YAZMA.",
    "oran": "1:1 veya 4:5 veya 9:16"}}
]}}"""


def gorsel_yazi_kapisi(gorseller: list[dict], urun_metni: str,
                       izinli_sayilar: set[str],
                       yedek_ust: list[str],
                       yedek_alt: list[str]) -> tuple[list[dict], list[dict]]:
    """Kareye BASILACAK yazıyı denetler.

    🔴 EN SİNSİ AÇIK BURASIYDI VE ÜRETİMDE YAKALANDI. Mevzuat ve dayanak
    kapıları `satis_cumleleri` ile `baslik_onerileri` üzerinde çalışıyordu.
    Ama karenin üstündeki yazı AYRI bir model çağrısından (görsel adımı)
    geliyor ve hiçbir kapıdan geçmiyordu. Sonuç ölçüldü: "Ciltte soyulma
    riski yok" cümlesi teslim edilmiş bir JPEG'in içine BASILDI.

    Metinden farkı şudur: yanlış cümleyi brief'ten silmek ucuzdur, basılmış
    görselden silmek imkânsızdır -- görsel yeniden üretilmelidir. Bu yüzden
    kareye giren yazı, metinden DAHA SIKI denetlenir: takılan yazı silinmez,
    zaten kapıdan geçmiş bir cümleyle DEĞİŞTİRİLİR; yedek yoksa alan boş
    bırakılır. Denetimden geçmemiş hiçbir harf kareye basılmaz.
    """
    silinen: list[dict] = []
    temiz: list[dict] = []
    for n, g in enumerate(gorseller):
        g = dict(g)
        for alan, onayli in (("ust_yazi", yedek_ust), ("alt_yazi", yedek_alt)):
            # 1) Model NUMARA seçmeliydi: numarayı onaylı listeden metne çevir.
            secim = g.pop(f"{alan}_no", None)
            metin = ""
            if onayli:
                try:
                    metin = onayli[int(secim) % len(onayli)]
                except (TypeError, ValueError):
                    # Model numara yerine cümle yazdıysa o cümle KULLANILMAZ;
                    # sırayla onaylı bir başlık verilir.
                    if secim not in (None, ""):
                        silinen.append({
                            "alan": f"gorsel[{n + 1}].{alan}", "cumle": str(secim),
                            "tur": "onaysız kare yazısı", "yakalanan": "serbest metin",
                            "gerekce": "kareye yalnız denetimden geçmiş cümle basılır; "
                                       "model numara yerine kendi cümlesini yazdı",
                            "gorsel": g.get("ad")})
                    metin = onayli[n % len(onayli)]
            # 2) Kuşak ve askı: seçilen cümle yine de kapılardan geçirilir.
            if metin:
                kayit = _denetle(metin, f"gorsel[{n + 1}].{alan}", urun_metni,
                                 izinli_sayilar)
                if kayit:
                    kayit["gorsel"] = g.get("ad")
                    silinen.append(kayit)
                    metin = ""
            g[alan] = metin
        temiz.append(g)
    return temiz, silinen


def _istemi_muhurle(gorseller: list[dict]) -> list[dict]:
    """Her sahne istemine yasak cümlesini EKLER ve yazı sızıntısını temizler.

    İki iş yapar:
      1. MUHUR'ü isteme ekler (model eklemeyi unutsa da orada olur)
      2. istemde ürün/yazı geçiyorsa işaretler — sessizce geçirmez
    """
    # 🔴 TAM SÖZCÜK ARANIR. Ölçüldü: düz `in` araması "textures" içindeki
    # "text"i yakalayıp iki sahneyi boş yere işaretledi, buna karşılık
    # "a glass JAR with a subtle sheen" gerçek bir kaptı ve o da listedeydi.
    # Yanlış alarm, doğru alarmın ciddiye alınmasını engeller.
    SIZINTI = ("bottle", "bottles", "jar", "jars", "tube", "tubes", "pump",
               "packaging", "label", "labels", "logo", "text", "typography",
               "product", "products", "container", "containers", "lettering",
               "signage", "watermark", "writing", "caption")
    kalip = re.compile(r"\b(" + "|".join(SIZINTI) + r")\b", re.IGNORECASE)
    muhurlu = []
    for g in gorseller:
        istem = str(g.get("sahne_istemi") or "").strip()
        bulasik = sorted({e.group(1).casefold() for e in kalip.finditer(istem)})
        g = dict(g)
        g["sahne_istemi"] = f"{istem}\n\n{MUHUR}"
        g["muhur_eklendi"] = True
        if bulasik:
            g["uyari"] = ("İstemde ürün/yazı sözcüğü geçiyor, elle bak: "
                          + ", ".join(bulasik))
        muhurlu.append(g)
    return muhurlu


def yerlesim_sartnamesi(urun: dict, gorsel: dict) -> dict:
    """Sahne üretildikten SONRA kodun yapacağı birleştirme işi.

    Bu adım image modeline gitmez. Pillow ile yapılır çünkü ölçüldü:
    gerçek fotoğrafın piksellerini taşımada SSIM 1.00, image modeline
    yeniden çizdirmede 0.82 — yani ambalaj gözle görülür şekilde bozuluyor.
    """
    return {
        "yontem": "Python + Pillow (image modeli DEĞİL)",
        "katman_1_arka_plan": "5. adımda üretilen sahne görseli",
        "katman_2_urun": {
            "kaynak": "gerçek ürün çekimi (PNG, şeffaf zemin)",
            "sku": urun.get("sku"),
            "konum": gorsel.get("urun_yerlesimi"),
            "kural": "piksel taşınır, yeniden çizilmez; ambalaj yazısına dokunulmaz",
        },
        "katman_3_logo": {"kaynak": "L'CARLIÉ logo (şeffaf PNG)",
                          "konum": "sol üst ya da alt orta, tek yerde"},
        "katman_4_tipografi": {
            "ust_yazi": gorsel.get("ust_yazi"),
            "alt_yazi": gorsel.get("alt_yazi"),
            "kural": ("gerçek font dosyasıyla kodda dizilir; Türkçe metin "
                      "image modeline YAZDIRILMAZ (ı, ğ, ş, İ bozuluyor)"),
            "bolge": gorsel.get("bos_alan"),
        },
        "oran": gorsel.get("oran"),
    }


# --------------------------------------------------------------------------
# 6) RED TEAM — TÜRKÇE VE KREATİFE DAİR
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 4b) UGC VİDEO SENARYOSU
# --------------------------------------------------------------------------
#
# 🔴 NEDEN AYRI BİR KATMAN. Bu hat 21.09.2026'ya kadar YALNIZ durağan görsel
# üretiyordu (`grep senaryo|video|ugc` -> 0 sonuç). Oysa ölçülen kendi
# verimizde en ucuz erişim gerçek kişinin konuştuğu videoda: CPM 45,58 ·
# CTR 7,84 (k3, saç bakımı). Metin ve kare üretip videoyu dışarıda bırakmak,
# en iyi çalışan formatı üretmemek demekti.
#
# 🔴 EN RİSKLİ ALAN KONUŞMA METNİ. Basılmış kareden yanlış cümleyi silmek
# imkânsız; ÇEKİLMİŞ videodan silmek de öyle. Üstelik konuşan kişi bir
# TANIKTIR (Ticari Reklam Yön. m.16) -- söylediği her cümlenin doğruluğunu
# reklamveren ispatlar. Bu yüzden `seslendirme`, `ekran_yazisi`, `hook` ve
# `cta` alanlarının HEPSİ, satış cümleleriyle aynı iki kapıdan geçer.
#
# `goruntu` ve `cekim_notu` alanları kapıdan GEÇMEZ: onlar kameraya verilen
# yönerge, müşteriye giden cümle değil. Ayrım kasıtlı -- sahne tarifine
# mevzuat kapısı uygulamak "ıslak saç" gibi masum yönergeleri siler.

SENARYO_SISTEM = """Sen Türkiye'de çalışan, satış odaklı bir UGC kreatif
yönetmenisin. Telefonla çekilen, gerçek bir kullanıcının kendi evinde
çektiği hissini veren dikey video senaryoları yazıyorsun.

İŞİN: ürünü satmak. Duygu değil, SATIN ALMA sebebi üret.

🔴 SENARYO GERÇEKTEN ÇEKİLEBİLİR OLMALI. Oyuncu kadrosu, drone, stüdyo,
ışık ekibi YOK. Tek kişi, tek telefon, ev ya da sokak. Yazdığın her sahne
bir kişinin tek başına çekebileceği bir şey olmalı.

🔴 İLK 3 SANİYE. İzleyici ürünü değil KENDİ SORUNUNU görmeli. Ürünle
başlayan senaryo yazma; sorunun yaşandığı anla başla.

🔴 GÖSTER, ANLATMA. Ürünün yaptığı iş gösterilebiliyorsa GÖSTERİLİR ve
o gösterim TEK ÇEKİMDE olur -- kesme yok. Öncesi/sonrası KURGUSU YASAK:
kurgulanmış karşılaştırma "kanıt" sayılır ve ispat külfeti (Ticari Reklam
Yönetmeliği m.8) markaya geçer. Kesintisiz tek çekim hem savunulabilir
hem daha ikna edici.

🔴 KONUŞMA METNİ TANIKLIKTIR. Kişi ürün hakkında ancak ürün kaydında
GERÇEKTEN yazan şeyi söyleyebilir. Kullanım talimatını, içindekini,
dokusunu, kokusunu konuşabilir. Sonuç vaat edemez.

MEVZUAT -- Türkiye Kozmetik Yönetmeliği. Kozmetik ürün TEDAVİ ETMEZ.
Konuşma metninde ya da ekran yazısında ŞUNLAR OLAMAZ:
- "iyileştirir, tedavi eder, onarır, geçirir, yok eder, önler"
- hastalık/semptom adı (egzama, akne, kepek, yara, yanık, dökülme...)
- fizyolojik iddia (dolaşım, kolajen, hücre yenilenmesi, bağışıklık)
- "anında", "tek kullanımda", "X günde", yüzde ya da süre
- doktor/klinik otoritesi, beyaz önlük, laboratuvar
- rakiple karşılaştırma, "en iyi", "piyasadaki tek"
İZİN VERİLEN dil: görünüm · his · doku · nem · konfor · koku · rutin.

🔴 KİME KONUŞTUĞUNU KANITTAN AL. Kanıtta `gercek_kitle` alanı varsa
senaryoyu O KİŞİYE kur. Ürünün adında ya da etiketinde geçen kitle, ürünü
SATIN ALAN kitle olmayabilir; etiket "bebek için" dese de alıcı yetişkinse
senaryodaki kişi yetişkindir. Etiket cümlesi değişmez, reklamın muhatabı değişir.

🔴 SORUNU GÖSTERME, ANI GÖSTER. Ürünün çözdüğü iddia edilen DURUMU
kameraya alma: kırık saç, yara, kızarıklık, döküntü, kepek, ağlayan çocuk
yakın planı YASAK. Kamerada gösterilen durum da bir iddiadır ve mevzuat
resimleri de iddia kapsamına alır. Sorunu ANIN kendisiyle kur -- acele,
telaş, sıra, vakit darlığı -- hasarla değil.

🔴 İÇ MUHAKEMENİ YAZMA. "tedavi değil", "mevzuata uygun", "iddia değildir",
"rutin başlaması işareti olarak" gibi ifadeler senin kendi kontrol notundur;
müşteriye giden cümleye GİRMEZ. Ölçüldü: bir kanca "…bu durum gösterilir, ama
tedavi değil, rutin başlaması işareti olarak" diye çıktı -- kamera karşısında
kimse böyle konuşmaz. Kuralı uygula, anlatma.

🔴 EKRAN YAZISINA SAYI KOYMA. Sahnedeki saat, süre, sayı GÖRÜNTÜYE aittir
("telefon ekranında sabah saati görünür" diye `goruntu` alanına yaz),
ekran üstü yazıya değil. Ürün kaydında geçmeyen her sayı silinir.

🔴 KÖTÜ İŞ NEYE BENZER: "Kendinize ayırdığınız o özel an" -- bu cümle her
ürün için doğru, yani hiçbir ürün için bir şey söylemiyor. Ürünün KULLANIM
ŞEKLİNİ, İÇİNDEKİNİ ve alıcının gerçek itirazını konuş.

SADECE geçerli JSON döndür, öncesinde ve sonrasında tek kelime yazma."""


SENARYO_ISTEK = """{urun} için {adet} adet UGC video senaryosu yaz.
Senaryolar BİRBİRİNDEN FARKLI açıdan girsin; aynı fikrin varyasyonu olmasın.

Kullanabileceğin onaylı satış cümleleri (konuşma metnini bunlara yaslayabilirsin):
{cumleler}

PİYASADAN TOPLANAN KANCALAR — bunlar RAKİP ve benzer kozmetik markaların
gerçekten kullandığı açılış cümleleridir:
{kancalar}

KANCA KALIPLARI — doldurulacak yapı şablonları (mevzuat süzgecinden
geçirilmiş; kozmetikte kullanılamayanlar bu listeden ÇIKARILDI):
{kaliplar}

🔴 KALIP İLE KANCA FARKI: yukarıdaki kancalar piyasada gerçekten yayınlanmış
CÜMLELERDİR; kalıplar ise doldurulacak İSKELETLERDİR. Kalıbı ürünün gerçek
kullanım anıyla doldur, kancayı taklit etme.

🔴 BU CÜMLELERİ KOPYALAMA. Onların KALIBINI al, cümlesini değil. Rakibin
dosyası ona aittir; aynı cümleyi biz yazarsak onun belgesi bizi korumaz.
Kalıp ne demek: "Servis kapıda, saç hâlâ taranmadı" cümlesinin kalıbı
[zaman baskısı] + [yarım kalmış iş]. Aynı kalıbı BİZİM ürünümüzün gerçek
kullanım anıyla yeniden kur.

BRIEF:
{brief}

JSON şeması -- birebir bu anahtarlar:
{{"senaryolar": [
 {{"ad": "Senaryoyu tanımlayan kısa ad",
   "sure_sn": 20,
   "neden_bu_aci": "Bu senaryo hangi alıcı itirazını ya da anı hedefliyor",
   "hook": "İlk 3 saniyede EKRANDA ya da ağızda geçen cümle. Sorunu söyler, ürünü değil.",
   "sahneler": [
     {{"saniye": "0-3",
       "goruntu": "Kameranın ne gördüğü. Yönerge dili. Kapıdan geçmez.",
       "ekran_yazisi": "Kareye basılacak yazı. Kısa. SAYI YOK. Yoksa boş bırak."}}
   ],
   "seslendirme": "Kişinin kendi ağzıyla söyleyeceği metin. Konuşma dili, kısa cümleler. Ürün kaydında yazmayan hiçbir şeyi söyletme.",
   "cta": "Kapanış çağrısı. Tek cümle.",
   "cekim_notu": "Çeken kişiye teknik not: ışık, kesme, kaç çekim. Kapıdan geçmez."}}
]}}"""


# Konuşma ve ekran yazısı -- müşteriye giden alanlar. Kapıdan GEÇER.
SENARYO_KAPILI = ("hook", "seslendirme", "cta")
SAHNE_KAPILI = ("ekran_yazisi",)


# 🔴 SAHNE TARİFİ DE DENETLENİR -- ama ayrı bir kapıyla.
#
# İlk tasarımda `goruntu` alanı kasıtlı olarak kapı dışındaydı: o alan
# kameraya verilen yönergedir, müşteriye giden cümle değil; mevzuat kapısını
# oraya uygulamak "ıslak saç" gibi masum yönergeleri siler.
#
# Ölçüldü ki bu boşluk gerçek bir açık: EASYCOMB ilk koşusunda model
# `goruntu` alanına "saçların kırık ve kırılmaya başlamış hali görülür" yazdı.
# Kamerada GÖSTERİLEN hasar, metinde YAZILAN iddia kadar iddiadır -- Kozmetik
# Ürünler Yönetmeliği iddia kapsamına resimleri de alıyor. Ürünün çözdüğü
# iddia edilen durumu göstermek, o iddiayı sessizce kurar.
#
# Bu yüzden sahneye DAR bir kapı konur: yalnız DURUM/HASAR GÖSTERİMİ aranır,
# tam mevzuat taraması değil. Sahne SİLİNMEZ (silinirse çeken kişi boşluğu
# kendi kafasına göre doldurur) -- işaretlenir ve brief'te 🔴 ile görünür.
# 🔴 KOK_SINIRI — kelime ORTASINDA eşleşme yasak.
#
# İlk yazdığımda kökleri sınırsız bıraktım ve ölçüldü ki:
#     "başlayarak"  -> 'yara'  eşleşti   (baş-la-YARA-k)
#     "bağlantı"    -> 'ağla'  eşleşir   (b-AĞLA-ntı)
# Sahne tarifi masumken "yasak gösterim" damgası yedi.
#
# Bu, hafızada YAZILI bir hatanın tekrarı: aynı kalıp daha önce "hi "
# önekinin kelime ortasında eşleşmesiyle yaşandı. Türkçe eklemeli bir dil
# olduğu için kökün SONU serbest bırakılır ama BAŞI kelime sınırına
# çakılır: "\byara" -> yarası/yaralar ✓, başlayarak ✗.
KOK_SINIRI = r"\b(?:{})"

SAHNE_GOSTERIM_YASAGI = re.compile(
    KOK_SINIRI.format("|".join((
        "kırıl", "kırık", "çatla", "yıpran", "dökül", "seyrel",
        "yara", "yanık", "kabuk", "lezyon", "döküntü", "kızarık",
        "iltihap", "akne", "sivilce", "egzama", "sedef", "mantar",
        "kepek", "pul pul", "leke",
        "ağla", "acı çek", "canı yan",
        "beyaz önlük", "klinik", "muayene", "laboratuvar", "doktor",
    ))),
    re.IGNORECASE)

def senaryo_kapisi(senaryolar: list, urun_metni: str,
                   izinli_sayilar: set[str]) -> tuple[list, list[dict]]:
    """Her senaryonun müşteriye giden alanını iki kapıdan geçirir.

    🔴 SİLMEZ, İŞARETLER. Bir satış cümlesi silinince brief'te bir madde
    eksilir; bir senaryoda `seslendirme` silinirse senaryo ANLAMSIZ kalır ve
    çeken kişi boşluğu kendi cümlesiyle doldurur -- yani denetimsiz cümle
    çekime girer. Bu yüzden alan boşaltılmaz: sorunlu cümle yerinde bırakılır,
    üstüne 🔴 düşülür ve `senaryo_silinen` listesine yazılır. Çeken kişi neyi
    söyleyemeyeceğini görerek çekime gider.
    """
    silinen: list[dict] = []
    temiz: list = []
    for n, s in enumerate(senaryolar, 1):
        if not isinstance(s, dict):
            continue
        ad = str(s.get("ad") or f"senaryo {n}")
        for alan in SENARYO_KAPILI:
            cumle = str(s.get(alan) or "").strip()
            if not cumle:
                continue
            # 🔴 SOYLENEN_DURUM: durum gösterimi kapısı yalnız SAHNE tarifine
            # uygulanmıştı; kancaya ve konuşmaya uygulanmamıştı. Ölçüldü
            # (21.09.2026): model kancayı "Kuru saçta tarama her seferinde
            # ağlama sözü — çocuk acı çekiyor" diye yazdı ve iki kapıdan da
            # GEÇTİ -- çünkü mevzuat kapısı hastalık adı arıyor, dayanak
            # kapısı sayı ve işlev arıyor; "çocuk acı çekiyor" ikisine de
            # takılmıyor. Oysa ürünün çözdüğü iddia edilen ACIYI anlatmak,
            # o iddiayı kurmanın en dolaysız yolu.
            #
            # Sahnede olduğu gibi burada da SİLİNMEZ, işaretlenir: boş
            # bırakılan konuşma metnini çeken kişi kendi cümlesiyle doldurur.
            es = SAHNE_GOSTERIM_YASAGI.search(cumle)
            if es:
                silinen.append({
                    "alan": f"senaryo[{ad}].{alan}", "cumle": cumle,
                    "tur": "söylenen durum", "yakalanan": es.group(0),
                    "gerekce": "ürünün çözdüğü iddia edilen durumu/acıyı "
                               "anlatmak o iddiayı kurar; anı anlat, hasarı değil"})
                s[f"{alan}_uyari"] = (f"söylenen durum: '{es.group(0)}' — "
                                      "anı anlat, hasarı/acıyı değil")
            kayit = _denetle(cumle, f"senaryo[{ad}].{alan}", urun_metni, izinli_sayilar)
            if kayit:
                silinen.append(kayit)
                s[f"{alan}_uyari"] = (
                    f"{kayit.get('tur')}: '{kayit.get('yakalanan')}' — "
                    f"{kayit.get('gerekce', '')}")
        sahneler = []
        for sn in s.get("sahneler") or []:
            if not isinstance(sn, dict):
                continue
            for alan in SAHNE_KAPILI:
                cumle = str(sn.get(alan) or "").strip()
                if not cumle:
                    continue
                kayit = _denetle(cumle, f"senaryo[{ad}].sahne.{alan}",
                                 urun_metni, izinli_sayilar)
                if kayit:
                    silinen.append(kayit)
                    # Kare yazısı BASILIR; basılmış yazıdan cümle silinemez.
                    # Bu yüzden burada gerçekten boşaltılır.
                    sn[alan] = ""
                    sn["uyari"] = f"kare yazısı silindi ({kayit.get('yakalanan')})"
            sahne_tarifi = str(sn.get("goruntu") or "")
            es = SAHNE_GOSTERIM_YASAGI.search(sahne_tarifi)
            if es:
                sn["gosterim_uyarisi"] = es.group(0)
                silinen.append({
                    "alan": f"senaryo[{ad}].sahne.goruntu",
                    "cumle": sahne_tarifi, "tur": "sahnede durum gösterimi",
                    "yakalanan": es.group(0),
                    "gerekce": "kamerada gösterilen durum da iddiadır; "
                               "Kozmetik Ürünler Yönetmeliği resimleri de "
                               "iddia kapsamına alır -- sahne değiştirilmeli"})
            sahneler.append(sn)
        s["sahneler"] = sahneler
        temiz.append(s)
    return temiz, silinen


def kelime_karti(ozet: dict, kutu_bolum: dict) -> dict:
    """Çekime çıkan kişiye verilecek kart: ne diyebilir, ne diyemez.

    🔴 Bu kart brief'in süsü değil, KAPININ ÇEKİME UZANAN KOLU. Senaryo
    metnini denetlemek yetmiyor: kamera karşısındaki kişi kendi cümlesini
    kurar ve o cümle hiçbir kapıdan geçmez. Ölçülen gerçek vaka: bir müşteri
    yanık iyileşme fotoğrafı gönderdi ve "paylaşabilirsiniz" dedi -- sorun
    metinde değil, kaynakta doğuyor.
    """
    diyebilir = []
    for anahtar, etiket in (("kullanim", "Kullanım"), ("uyarilar", "Uyarı")):
        ham = str(kutu_bolum.get(anahtar) or "")
        for parca in re.split(r"(?<=[.!?])\s+", ham):
            parca = parca.strip()
            if 12 < len(parca) < 180 and not parca.upper().startswith("EN:"):
                diyebilir.append(f"{etiket}: {parca}")
    return {
        "diyebilir": diyebilir[:10],
        "diyemez": [
            "iyileştirir · tedavi eder · onarır · geçirir · yok eder · önler",
            "hastalık ya da belirti adı (egzama, akne, kepek, yara, yanık, dökülme)",
            "fizyolojik iddia (dolaşım, kolajen, hücre yenilenmesi, bağışıklık, mikrobiyota)",
            "anında · tek kullanımda · X günde · yüzde ya da süre veren her ifade",
            "doktor önerir · klinik · dermatolog onaylı · beyaz önlük · laboratuvar",
            "en iyi · piyasadaki tek · X markasından iyi",
            "içermez · parabensiz · kimyasal içermez (adillik kriteri)",
        ],
        "gorsel_yasagi": [
            "lezyon, yara, yanık, iz, döküntü yakın planı",
            "öncesi/sonrası KURGUSU — gösterim tek çekimde, kesme yok",
            "beyaz önlük, klinik, muayenehane, laboratuvar algısı",
            "ürünün göze ya da ağza yakın püskürtüldüğü kare",
        ],
    }


RED_SISTEM = """Sen bu kreatifi ÇÜRÜTMEKLE görevli kıdemli bir reklamcısın.
Türkçe yazarsın. İşin kreatifi savunmak değil, YAYINA GİRMEDEN ÖNCE
yanlışını bulmaktır.

Her itirazın ŞU ÜÇÜ birden olmalı, yoksa yazma:
  1. NEYE itiraz ediyorsun — brief'ten BİREBİR ALINTI
  2. NEDEN yanlış — kanıta ya da somut bir sebebe dayanarak
  3. NE YAPILSIN — uygulanabilir, tek cümlelik düzeltme

Yasak: "ölçüm eksik", "veri yetersiz" gibi genel notlar. Onlar zaten ayrı
raporlanıyor. Sen KREATİFİN KENDİSİNE itiraz et: cümle tutmuyor mu, vaat
şişik mi, rakip aynısını mı söylüyor, fiyata değmiyor mu, alıcı inanmaz mı.

🔴 ÖNCE ŞUNU KONTROL ET: brief'in fiyat cümlesi, kanıttaki
`fiyat_konumu_olcumu` sayılarıyla çelişiyor mu? Çelişiyorsa bu senin
BİRİNCİ ve YÜKSEK ağırlıklı itirazın olmalı.

🔴 SORU CÜMLESİNE İTİRAZ ETME. `alici_itirazi` içindeki "itiraz" alanı
ALICININ SORUSUDUR, bizim iddiamız değil. Ona değil, bizim verdiğimiz
CEVABA itiraz et.

🔴 DÜZELTME ÖNERİRKEN MEVZUATI SEN DE ÇİĞNEME. "klinik olarak kanıtlanmış",
"cilt bariyerini güçlendirir", "onarır", "tedavi eder" gibi ifadeleri
DÜZELTME olarak önerme. "Rakip böyle diyor" bir gerekçe DEĞİLDİR: CeraVe ya
da La Roche-Posay'ın dosyası onlara aittir, bize izin vermez. Önerdiğin
düzeltme doğrudan reklam metnine kopyalanacak; yasak ifade önerirsen
kreatifi düzeltmiş değil, bozmuş olursun.

SADECE geçerli JSON döndür."""

RED_ISTEK = """Bu kreatif brief'i çürüt. En sert 4-6 itirazı yaz.

BRIEF:
{brief}

KANIT (şirket ölçümleri ve rakip bulguları):
{kanit}

JSON şeması — birebir:
{{"itirazlar": [
  {{"alinti": "Brief'ten birebir alıntı",
    "itiraz": "Neden yanlış — tek paragraf, Türkçe, somut",
    "dayanak": "Hangi kanıta/sebebe dayanıyor",
    "duzeltme": "Ne yapılsın — tek cümle, uygulanabilir",
    "agirlik": "YÜKSEK | ORTA | DÜŞÜK"}}
]}}"""


# --------------------------------------------------------------------------
# RAPOR
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 6b) TÜRKÇE İMLA KAPISI — uyarır, ENGELLEMEZ
# --------------------------------------------------------------------------
#
# 🔴 NE YAPAR, NE YAPMAZ. Ölçüldü (22.09.2026, gerçek üretim çıktılarıyla):
#
#   yakaladı  : "bakımlaşır", "şunayem", "Aaa"      (sözlükte olmayan kelime)
#   kaçırdı   : "düğünler açılmamış"                 ("düğüm" demek istenmiş,
#                "düğün" geçerli bir kelime -- imla değil KELİME SEÇİMİ hatası)
#   yanlış    : "ciltim", "EASYCOMB"                 (sözlük boşluğu / marka)
#
# Yani bu kapı YAZIM hatasını yakalar, YANLIŞ KELİMEyi yakalamaz. Onu
# yakalayan tek şey insan gözüdür; kapı onun yerine geçmez, işini azaltır.
#
# 🔴 SİLMEZ. Mevzuat kapıları cümleyi siler çünkü yasak cümle yayına
# gitmemeli. İmla hatası yasak değil, çirkin. Silinirse brief'te boşluk kalır
# ve çeken kişi boşluğu kendi cümlesiyle doldurur -- denetimsiz cümle çekime
# girer. Bu yüzden cümle yerinde kalır, üstüne uyarı düşülür.
IMLA_SOZLUK = Path(os.environ.get(
    "KREATIF_IMLA_SOZLUK", str(KOK / "varliklar" / "imla-ek-sozluk.txt")))
_IMLA_KELIME = re.compile(r"[A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû']{3,}")


def imla_denetimi(cumleler: list[str]) -> list[str]:
    """Sözlükte olmayan kelimeleri döndürür. hunspell yoksa sessizce boş."""
    import shutil
    import subprocess

    if not cumleler or not shutil.which("hunspell"):
        return []
    metin = "\n".join(c for c in cumleler if c)
    komut = ["hunspell", "-d", "tr_TR", "-l"]
    if IMLA_SOZLUK.exists():
        komut += ["-p", str(IMLA_SOZLUK)]
    try:
        r = subprocess.run(komut, input=metin.encode("utf-8"),
                           capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return []
    supheli, gorulen = [], set()
    for k in r.stdout.decode("utf-8", "replace").split():
        k = k.strip("'\u2019.,;:!?()")
        # 🔴 4 HARF ALTI ELENIR. Olculdu: hunspell "dan" gibi ek parcalarini
        # kelime sanip isaretliyor. Turkcede 3 harfli gercek yazim hatasi
        # nadir; parca gurultusu ise surekli. Esik 4 yapilinca 5 supheliden
        # 1 gurultu dustu, gercek hatalar (dayiniyor, sea) kaldi.
        if len(k) < 4 or k in gorulen or not _IMLA_KELIME.fullmatch(k):
            continue
        # TAMAMI BÜYÜK yazılanlar marka/ürün adıdır, imla konusu değil.
        if k.isupper():
            continue
        gorulen.add(k)
        supheli.append(k)
    return supheli


def markdown_yaz(b: dict) -> str:
    y: list[str] = []
    ek = y.append
    u = b["urun"]
    ek(f"# KREATİF BRIEF — {u['urun_adi']}")
    ek(f"\n_{b['uretildi']} · L'CARLIÉ Kreatif Hattı_\n")

    ek("## 1. ÜRÜN GERÇEĞİ — şirket ölçümü\n")
    ek("| Alan | Değer |\n|---|---|")
    ek(f"| SKU | {u['sku']} |")
    ek(f"| Site fiyatı | {u['wix_fiyat_tl']} TL |")
    ek(f"| Trendyol fiyatı | {u['trendyol_fiyat_tl']} TL |")
    ek(f"| Birim maliyet | {u['birim_maliyet_tl']} TL |")
    ek(f"| Brüt marj | {u['brut_marj_yuzde']}% |")
    ek(f"| Stok | {u['wix_stok']} |")
    ek(f"| Ölçülen satış | {u['olculen_satis_adedi']} adet |")
    if b["zararina"]:
        ek(f"\n🔴 **Maliyetin altında satılan {len(b['zararina'])} satış var:**\n")
        for z in b["zararina"]:
            ek(f"- {z['gun']}: net {z['net']} TL, maliyet {z['maliyet']} TL "
               f"(indirim {z['indirim']} TL)")

    ek("\n## 2. KENDİ GEÇMİŞİMİZ — şirket ölçümü\n")
    ek(f"Bu ürün için **{b['kreatif_sayisi']}** reklam metni kayıtlı, "
       f"**{b['aktif_kreatif']}** tanesi aktif.")
    if b["tutarlilik"]:
        ek(f"\n🔴 **Tutarlılık hatası bulunan {len(b['tutarlilik'])} metin:**\n")
        for t in b["tutarlilik"]:
            satir = f"- **{t['ad_adi']}** ({t['durum']}): "
            if t["urunde_olmayan_madde"]:
                satir += ("ürün kaydında olmayan madde → "
                          + ", ".join(t["urunde_olmayan_madde"]) + ". ")
            if t["yanlis_marka_yazimi"]:
                satir += ("marka yanlış yazılmış → "
                          + ", ".join(t["yanlis_marka_yazimi"])
                          + f" (doğrusu {MARKA_DOGRU}). ")
            ek(satir)
    else:
        ek("\nTutarlılık hatası bulunamadı.")

    ek("\n## 3. RAKİP — DIŞ KAYNAK (şirket ölçümü değil, iddia)\n")
    if not b["rakip"]:
        ek("🔴 Rakip bulgusu alınamadı — kaynaksız iddia kaydedilmedi.")
    for r in b["rakip"]:
        ek(f"\n### {r['aci']}\n")
        ek(r["bulgu"])
        ek(f"\n_Kaynaklar: {', '.join(r['kaynaklar'])}_")

    kurul = b.get("kurul") or []
    if kurul:
        ek(f"\n## 3b. EKİBİN GÖRÜŞÜ — {len(kurul)} departman, sıfır model çağrısı\n")
        ek("| Üye | Görev | Veriye bakınca söylediği |\n|---|---|---|")
        for u in kurul:
            cumle = str(u.get("soyledigi", "")).replace("\n", " ").replace("|", "/")
            ek(f"| {u.get('uye','')} | {u.get('gorev','')} | {cumle[:230]} |")

    atanan = b.get("atanan_uzmanlar") or []
    if atanan:
        ek(f"\n### 3c. JARVIS'İN ATADIĞI UZMANLAR — {len(atanan)} kişi\n")
        ek("🔴 Bunlar çekirdek kadronun **kapsamadığı** bakış açıları için "
           "Jarvis tarafından atandı ve kadroya kalıcı eklendi. "
           "Kaynağı `KAYNAK_YOK` olan üye ölçüm değil **yorum** verir — "
           "kadroyu büyütmek ölçümü büyütmek değildir.\n")
        ek("| Uzman | Kaynak | Söylediği |\n|---|---|---|")
        for u in atanan:
            c = str(u.get("soyledigi", "")).replace("\n", " ").replace("|", "/")
            ek(f"| {u.get('uye','')} | `{u.get('kaynak','')}` | {c[:230]} |")

    f = b.get("fiyat_konumu_olcumu") or {}
    ek("\n### Fiyat konumu — KODDA HESAPLANDI, model yorumu değil\n")
    ek(f"**{f.get('cumle','—')}**\n")
    if f.get("mutlak"):
        m, bi = f["mutlak"], f.get("birim") or {}
        ek("| Ölçü | Biz | Rakip aralığı | Bizden ucuz |\n|---|---|---|---|")
        ek(f"| Mutlak fiyat | {f.get('bizim_tl')} TL | "
           f"{m['en_ucuz']:.0f}–{m['en_pahali']:.0f} TL | "
           f"{m['bizden_ucuz_adet']}/{m['toplam']} |")
        if bi:
            ek(f"| Ml başına | {bi['bizim_tl_ml']:.2f} TL/ml | "
               f"{bi['en_ucuz']:.2f}–{bi['en_pahali']:.2f} TL/ml | "
               f"{bi['bizden_ucuz_adet']}/{bi['toplam']} |")
        ek("\n_Rakip fiyatları DIŞ KAYNAK iddiasıdır; bizim fiyatımız şirket ölçümü._")

    k = b.get("konumlandirma") or {}
    ek("\n## 4. KONUMLANDIRMA\n")
    if not k:
        ek("🔴 Üretilemedi.")
    else:
        ek(f"**Ürün:** {k.get('urun_tek_cumle','—')}\n")
        ek(f"**Kime:** {k.get('kime','—')}\n")
        ek(f"**Fiyat konumu:** {k.get('fiyat_konumu','—')}\n")
        ek("\n**Ayrışma:**")
        for a in k.get("ayrisma") or []:
            ek(f"- {a}")
        ek("\n**Alıcı itirazı → cevabı:**\n")
        ek("| İtiraz | Cevap |\n|---|---|")
        for i in k.get("alici_itirazi") or []:
            if isinstance(i, dict):
                ek(f"| {i.get('itiraz','')} | {i.get('cevap','')} |")
        ek("\n**Satış cümleleri (mevzuat kapısından geçti):**")
        for c in k.get("satis_cumleleri") or []:
            ek(f"- {c}")
        ek("\n**Başlık önerileri:**")
        for c in k.get("baslik_onerileri") or []:
            ek(f"- {c}")
        ek("\n**Kaçınılacaklar:**")
        for c in k.get("kacinilacaklar") or []:
            if isinstance(c, dict):
                ek(f"- **{c.get('ifade','')}** — {c.get('neden','')}")
            else:
                ek(f"- {c}")
    if b["mevzuat_silinen"]:
        ek(f"\n🔴 **Denetim kapıları {len(b['mevzuat_silinen'])} cümleyi SİLDİ:**\n")
        ek("| Tür | Silinen cümle | Yakalanan | Neden |\n|---|---|---|---|")
        for s in b["mevzuat_silinen"]:
            ek(f"| {s.get('tur','?')} | {s['cumle']} | `{s['yakalanan']}` | "
               f"{s.get('gerekce','')} |")

    kademeler = b.get("model_kademeleri") or []
    dusen = [k for k in kademeler if k != "EXTERNAL_MODEL"]
    if kademeler and dusen:
        ek(f"\n🔴 **Model kademesi:** {len(dusen)}/{len(kademeler)} çağrı "
           f"yerel modele düştü ({', '.join(sorted(set(dusen)))}). "
           "Bu bölümlerin Türkçesi zayıf olabilir — sorun modelin "
           "yeteneğinde değil, hangi modelin yazdığında.\n")

    imla = b.get("imla_supheli") or []
    if imla:
        ek(f"\n### 🔤 İMLA ŞÜPHELİSİ — {len(imla)} kelime\n")
        ek("Bunlar Türkçe sözlükte bulunamadı. **Silinmedi** — çekimden önce "
           "gözle bakılmalı. Kapı yazım hatasını yakalar, YANLIŞ KELİMEYİ "
           "yakalamaz (\"düğün\" ↔ \"düğüm\" gibi).\n")
        ek("`" + "` · `".join(imla[:30]) + "`")

    sen = b.get("senaryolar") or []
    if sen:
        ek("\n## 5. UGC VİDEO SENARYOLARI\n")
        ek("Dikey 9:16 · telefonla çekilir · stüdyo yok. Gösterim sahnesi "
           "**tek çekimde**, kesme yok.\n")
        for n, s in enumerate(sen, 1):
            ek(f"\n### Senaryo {n} — {s.get('ad','?')} "
               f"({s.get('sure_sn','?')} sn)\n")
            if s.get("neden_bu_aci"):
                ek(f"**Neden bu açı:** {s['neden_bu_aci']}\n")
            ek(f"**Hook (ilk 3 sn):** {s.get('hook','—')}")
            if s.get("hook_uyari"):
                ek(f"\n🔴 {s['hook_uyari']}")
            ek("\n| sn | Görüntü | Ekran üstü yazı |\n|---|---|---|")
            for sn_ in s.get("sahneler") or []:
                g = str(sn_.get("goruntu", "")).replace("|", "/")
                # 🔴 BURADA "y" KULLANMA: bu fonksiyonun çıktı listesinin
                # adı y. Gölgelenince return "\n".join(y) listeyi değil
                # son ekran yazısı DİZESİNİ birleştirir; brief dosyası
                # sessizce 1 BAYT çıkar. Ölçüldü, oldu.
                yazi = str(sn_.get("ekran_yazisi", "")).replace("|", "/")
                if sn_.get("uyari"):
                    yazi = f"_(silindi: {sn_['uyari']})_"
                if sn_.get("gosterim_uyarisi"):
                    g = f"🔴 {g}  _(yasak gösterim: {sn_['gosterim_uyarisi']})_"
                ek(f"| {sn_.get('saniye','')} | {g} | {yazi} |")
            ek(f"\n**Konuşma metni:**\n\n> {s.get('seslendirme','—')}")
            if s.get("seslendirme_uyari"):
                ek(f"\n🔴 **Bu cümle kapıya takıldı:** {s['seslendirme_uyari']}")
            ek(f"\n**CTA:** {s.get('cta','—')}")
            if s.get("cta_uyari"):
                ek(f"\n🔴 {s['cta_uyari']}")
            if s.get("cekim_notu"):
                ek(f"\n**Çekim notu:** {s['cekim_notu']}")

        hv = b.get("kanca_havuzu") or []
        if hv:
            uygun = [h for h in hv if h.get("bize_uygun")]
            engelli = [h for h in hv if not h.get("bize_uygun")]
            ek(f"\n### 5a. KANCA HAVUZU — piyasadan {len(hv)} kanca\n")
            ek("🔴 Bunlar rakip ve benzer kozmetik markaların **gerçekten "
               "kullandığı** açılış cümleleridir. Senaryo üreticisine yalnız "
               "**kalıpları** örnek gider; cümleler kopyalanmaz.\n")
            ek("| Kaynak | Tür | Kanca | Kalıp |\n|---|---|---|---|")
            for h in uygun[:20]:
                ek(f"| {h.get('kaynak_tur','')} | {h.get('tur','')} | "
                   f"{str(h.get('metin','')).replace('|','/')[:90]} | "
                   f"{str(h.get('yapi','')).replace('|','/')[:60]} |")
            if engelli:
                ek(f"\n🔴 **Mevzuata takılan {len(engelli)} kanca — kalıbı bile "
                   "kullanılmaz:**\n")
                ek("| Kanca | Takıldığı |\n|---|---|")
                for h in engelli[:12]:
                    ek(f"| {str(h.get('metin','')).replace('|','/')[:90]} | "
                       f"`{h.get('engel','')}` |")

        kk = b.get("kelime_karti") or {}
        ek("\n### 5b. ÇEKİM KELİME KARTI — kamera karşısındaki kişiye verilir\n")
        ek("🔴 Senaryoyu denetlemek yetmez: kişi kendi cümlesini kurar ve o "
           "cümle hiçbir kapıdan geçmez. Kart çekimden ÖNCE eline verilir.\n")
        if kk.get("diyebilir"):
            ek("\n**✅ Söyleyebilir (ürünün onaylı kutu metninden):**")
            for c in kk["diyebilir"]:
                ek(f"- {c}")
        ek("\n**❌ Söyleyemez — çekimde duyulursa o çekim kullanılmaz:**")
        for c in kk.get("diyemez") or []:
            ek(f"- {c}")
        ek("\n**🔴 Görsel yasakları:**")
        for c in kk.get("gorsel_yasagi") or []:
            ek(f"- {c}")

    ek("\n## 6. GÖRSEL ÜRETİM PAKETİ\n")
    ek("🔴 **Kural:** image modeline giden istem YALNIZ arka plan üretir. "
       "Ürün fotoğrafı, logo ve tüm Türkçe yazı sonradan kodla üstüne dizilir. "
       "Ambalaj AI'ya yeniden çizdirilmez.\n")
    for n, g in enumerate(b.get("gorseller") or [], 1):
        ek(f"\n### Görsel {n} — {g.get('ad','?')} ({g.get('oran','1:1')})\n")
        ek(f"**Hangi açı:** {g.get('hangi_aci','—')}\n")
        if g.get("uyari"):
            ek(f"🔴 {g['uyari']}\n")
        ek("**Image modeline yapıştırılacak istem:**\n")
        ek("```text")
        ek(g.get("sahne_istemi", ""))
        ek("```\n")
        ys = g.get("yerlesim") or {}
        ek("**Sonra kodla dizilecek:**\n")
        ek(f"- Ürün: {(ys.get('katman_2_urun') or {}).get('konum','—')} "
           f"— gerçek çekim, piksel taşınır")
        ek(f"- Logo: {(ys.get('katman_3_logo') or {}).get('konum','—')}")
        t = ys.get("katman_4_tipografi") or {}
        ek(f"- Üst yazı: **{t.get('ust_yazi','—')}**")
        ek(f"- Alt yazı: {t.get('alt_yazi','—')}")
        ek(f"- Yazı bölgesi: {t.get('bolge','—')}")

    ek("\n## 6. RED TEAM — kreatife itirazlar\n")
    if b.get("red_team_silinen"):
        ek(f"🔴 Red team'in önerdiği **{len(b['red_team_silinen'])} düzeltme "
           "denetim kapısından geçemedi** ve metne alınamaz:\n")
        for s in b["red_team_silinen"]:
            ek(f"- \"{s['cumle']}\" → `{s['yakalanan']}` "
               f"({s.get('tur','?')}: {s.get('gerekce','')})")
        ek("")
    itirazlar = (b.get("red_team") or {}).get("itirazlar") or []
    if not itirazlar:
        ek("İtiraz üretilemedi.")
    for i in itirazlar:
        if not isinstance(i, dict):
            continue
        ek(f"\n**[{i.get('agirlik','?')}] \"{i.get('alinti','')}\"**\n")
        ek(f"{i.get('itiraz','')}\n")
        ek(f"- _Dayanak:_ {i.get('dayanak','—')}")
        ek(f"- _Düzeltme:_ **{i.get('duzeltme','—')}**")
    return "\n".join(y) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Tek ürün için kreatif brief üretir")
    ap.add_argument("urun", help="Ürün adı ya da bir parçası (ör: HYDRAVIE)")
    ap.add_argument("--kategori", default=None,
                    help="Rakip taraması için kategori (boşsa ürün adından türetilir)")
    ap.add_argument("--gorsel", type=int, default=5, help="Üretilecek sahne sayısı")
    ap.add_argument("--guclu", action="store_true",
                    default=os.environ.get("KREATIF_GUCLU_MODEL") == "1",
                    help="Kreatif yazımı güçlü (dış) modele yönlendir. ÜCRET DOĞURUR; varsayılan kapalı.")
    ap.add_argument("--senaryo", type=int, default=3,
                    help="Üretilecek UGC video senaryosu sayısı (0=kapalı)")
    ap.add_argument("--kadrosuz", action="store_true",
                    help="Jarvis'in eksik uzman atamasını kapat")
    ap.add_argument("--derin", action="store_true",
                    default=os.environ.get("KREATIF_DERIN_ARASTIRMA") == "1",
                    help="Tüm araştırma açılarını aç (11 açı). Haftalık partide kapalı tutulur: ürün başına arama sayısını 2,75 katına çıkarır.")
    ap.add_argument("--rakipsiz", action="store_true",
                    help="Rakip taramasını atla (ağ yok / hızlı deneme)")
    a = ap.parse_args()

    hafiza = CompanyMemory(host=None)
    ham = urun_gercegi(hafiza, a.urun)
    if ham is None:
        print(f"ürün bulunamadı: {a.urun}", file=sys.stderr)
        return 2
    ad = str(ham.get("urun_adi"))
    print(f"ürün: {ad}")

    satislar = [s for s in hafiza._fetch("sales_items").records
                if str(s.get("urun_id")) == str(ham.get("urun_id"))]
    ozet = urun_ozeti(ham, satislar)

    # Onaylı kutu metni: kullanım · uyarılar · INCI (tanım DEĞİL, tablo DEĞİL).
    kutu = kutu_gercegi(ad)
    kutu_bolum = kutu.get("bolumler") or {}
    ozet["kullanim_talimati"] = kutu_bolum.get("kullanim", "")
    ozet["uyarilar"] = kutu_bolum.get("uyarilar", "")
    ozet["inci"] = kutu_bolum.get("inci", "")[:900]
    kutu_dayanak = str(kutu.get("dayanak_metni") or "")
    if kutu_dayanak:
        print(f"  kutu gerçeği: {kutu.get('kaynak')} · {len(kutu_dayanak)} karakter")
    else:
        print("  kutu gerçeği: YOK — itiraz cevapları ve kullanım cümleleri zayıf kalır",
              file=sys.stderr)
    zarar = zararina_satislar(satislar, ozet["birim_maliyet_tl"])
    print(f"  satış {len(satislar)} · zararına {len(zarar)}")

    kreatifler = kendi_kreatiflerimiz(hafiza, ad)
    tutarlilik = kreatif_tutarlilik(kreatifler, ozet["aciklama"] + " " + ad)
    aktif = sum(1 for k in kreatifler
                if "PAUSED" not in str(k.get("etkin_durum") or "").upper())
    print(f"  kreatif {len(kreatifler)} (aktif {aktif}) · tutarsız {len(tutarlilik)}")

    kitle = urun_kitlesi(ad)
    kategoriler = [k for k in (kitle.get("arama_kategorileri") or []) if k]
    kategori = a.kategori or (kategoriler[0] if kategoriler
                              else (ad.split("|")[-1].strip() or ad))
    if kitle:
        ozet["gercek_kitle"] = kitle.get("gercek_kitle", "")
        ozet["etiket_kitlesi"] = kitle.get("etiket_kitlesi", "")
        ozet["kitle_kaynagi"] = kitle.get("kaynak", "")
        global YASAK_KURGU
        YASAK_KURGU = [str(k) for k in (kitle.get("yasak_kurgu") or []) if k]
        if YASAK_KURGU:
            print(f"     yasak kurgu: {', '.join(YASAK_KURGU)}")
        print(f"  🔴 gerçek kitle üstyazımı: {kitle.get('gercek_kitle','')[:90]}")
        print(f"     araştırma kategorisi: '{kategori}' "
              f"(ürün adından DEĞİL, kitle dosyasından)")
    rakip = [] if a.rakipsiz else rakip_taramasi(kategori, derin=a.derin)

    hacim_es = _ML.search(ozet["aciklama"])
    bizim_ml = None
    if hacim_es:
        try:
            bizim_ml = float(hacim_es.group(1).replace(",", "."))
        except ValueError:
            bizim_ml = None
    fiyat_konumu = fiyat_konumu_hesapla(ozet["wix_fiyat_tl"], bizim_ml, rakip)
    print(f"  fiyat konumu: {fiyat_konumu['cumle']}")

    kurul = kurul_gorusu(hafiza)
    konusan = sum(1 for k in kurul if k["durum"] not in ("NEEDS_RESEARCH",
                                                         "NEEDS_INPUT"))
    print(f"  kurul: {len(kurul)} üye · {konusan} tanesi veriden konuştu")

    kanit = kanit_kur(ozet, zarar, fiyat_konumu, kurul, kreatifler,
                      tutarlilik, rakip)
    print(f"  kanıt: {len(kanit)} karakter")

    yonlendirici = ModelRouter()

    # 🔴 Kadro tamamlama kanıttan SONRA gelir: Jarvis neyin eksik olduğunu
    # ancak eldeki kanıtı görünce söyleyebilir. Atanan uzmanların görüşü
    # kurula katılır ve kanıt YENİDEN kurulur ki konumlandırma modeli
    # onları da görsün.
    atanan_gorus: list[dict] = []
    if not a.kadrosuz:
        try:
            atanan = kadro_tamamla(yonlendirici, ad, rakip, guclu=a.guclu)
            atanan_gorus = atanan_gorusleri(yonlendirici, atanan, kanit,
                                            rakip=rakip, guclu=a.guclu)
        except (ModelUnavailable_, OSError, ValueError, KeyError) as hata:
            print(f"  kadro tamamlanamadı: {str(hata)[:120]}", file=sys.stderr)
        if atanan_gorus:
            kurul = list(kurul) + atanan_gorus
            kanit = kanit_kur(ozet, zarar, fiyat_konumu, kurul, kreatifler,
                              tutarlilik, rakip)
            print(f"  kanıt yeniden kuruldu: {len(kanit)} karakter "
                  f"({len(atanan_gorus)} atanan uzman dahil)")

    if a.guclu:
        print("  🔴 güçlü model AÇIK — kreatif yazım dış sağlayıcıya gidiyor (ücret doğurur)")
    konum, _ = _uret(yonlendirici, KONUM_SISTEM,
                     KONUM_ISTEK.format(urun=ad) + "\n\nKANIT:\n" + kanit, 5000,
                     guclu=a.guclu)
    # Reklamda yazılmasına izin verilen sayılar: ürün kaydındakiler + fiyat.
    # 🔴 TL/ml HESABI BU LİSTEDE YOK. O bizim iç kıyas ölçümümüzdür;
    # ölçüldü ki reklam cümlesine "50 ml'de 24 TL" diye ÜRÜN FİYATI gibi sızdı.
    izinli_sayilar = {str(int(x)) for x in
                      (ozet["wix_fiyat_tl"], ozet["trendyol_fiyat_tl"], bizim_ml)
                      if x}
    # 🔴 Dayanak metni ÜÇ kaynaktan kurulur; her biri otorite olduğu şeyi verir:
    #   Wix açıklaması -> ürün tanımı (site temizliğinden geçmiş)
    #   kutu metni     -> kullanım · uyarılar · INCI (olgusal)
    #   ürün adı       -> ad üzerinden işlev
    urun_metni = " ".join(x for x in (ozet["aciklama"], ad, kutu_dayanak) if x)

    if not isinstance(konum, dict):
        print("konumlandırma üretilemedi", file=sys.stderr)
        konum, silinen = {}, []
    else:
        konum, silinen = mevzuat_kapisi(konum, urun_metni, izinli_sayilar)
        mevzuat_adet = sum(1 for s in silinen if s.get("tur") == "mevzuat")
        print(f"  konumlandırma ok · mevzuat sildi: {mevzuat_adet} · "
              f"dayanaksız sildi: {len(silinen) - mevzuat_adet}")

    gorseller: list[dict] = []
    gorsel_silinen: list[dict] = []
    if konum:
        onayli_ust = konum.get("baslik_onerileri") or []
        onayli_alt = konum.get("satis_cumleleri") or []
        gr, _ = _uret(yonlendirici, GORSEL_SISTEM,
                      GORSEL_ISTEK.format(
                          urun=ad, adet=a.gorsel,
                          basliklar="\n".join(f"{i}: {s}" for i, s in
                                              enumerate(onayli_ust)) or "(yok)",
                          cumleler="\n".join(f"{i}: {s}" for i, s in
                                             enumerate(onayli_alt)) or "(yok)",
                          brief=json.dumps(konum, ensure_ascii=False)),
                      3000)
        if isinstance(gr, dict):
            gorseller = _istemi_muhurle(gr.get("gorseller") or [])
            gorseller, gorsel_silinen = gorsel_yazi_kapisi(
                gorseller, urun_metni, izinli_sayilar, onayli_ust, onayli_alt)
            silinen.extend(gorsel_silinen)
            for g in gorseller:
                g["yerlesim"] = yerlesim_sartnamesi(ham, g)
        print(f"  görsel sahnesi: {len(gorseller)} · kare yazısı düzeltilen: "
              f"{len(gorsel_silinen)}")

    havuz: list[dict] = []
    if konum and a.senaryo > 0:
        try:
            havuz = kanca_topla(yonlendirici, rakip, kategori,
                                guclu=a.guclu,
                                ek_kategoriler=kategoriler or None)
        except (ModelUnavailable_, OSError, ValueError, KeyError) as hata:
            print(f"  kanca havuzu kurulamadı: {str(hata)[:120]}", file=sys.stderr)

    senaryolar: list = []
    senaryo_silinen: list[dict] = []
    if konum and a.senaryo > 0:
        sr, _ = _uret(yonlendirici, SENARYO_SISTEM,
                      SENARYO_ISTEK.format(
                          urun=ad, adet=a.senaryo,
                          cumleler="\n".join(
                              f"- {c}" for c in (konum.get("satis_cumleleri") or []))
                          or "(yok)",
                          kancalar=kanca_ornekleri(havuz),
                          kaliplar=kanca_kaliplari() or "(kalıp yok)",
                          brief=json.dumps(konum, ensure_ascii=False)),
                      SENARYO_BUTCESI(a.senaryo), guclu=a.guclu)
        if isinstance(sr, dict):
            senaryolar, senaryo_silinen = senaryo_kapisi(
                sr.get("senaryolar") or [], urun_metni, izinli_sayilar)
            silinen.extend(senaryo_silinen)
        else:
            # 🔴 "0 senaryo" iki AYRI durum olabilir: model bir şey
            # söylemedi, ya da söyledi ama cevabı kesildi. İkisi aynı satırı
            # yazarsa gerçek arıza normal sonuç gibi görünür.
            print(f"  🔴 SENARYO ÜRETİLEMEDİ — cevap ayrıştırılamadı "
                  f"(bütçe {SENARYO_BUTCESI(a.senaryo)} token). Cevap "
                  f"kesilmiş olabilir; --senaryo sayısını düşürmeyi dene.",
                  file=sys.stderr)
        print(f"  UGC senaryosu: {len(senaryolar)} · kapıya takılan cümle: "
              f"{len(senaryo_silinen)}")

    red: dict = {}
    red_silinen: list[dict] = []
    if konum:
        rt, _ = _uret(yonlendirici, RED_SISTEM,
                      RED_ISTEK.format(brief=json.dumps(konum, ensure_ascii=False),
                                       kanit=kanit[:8000]), 2200)
        if isinstance(rt, dict):
            red, red_silinen = red_team_kapisi(rt, urun_metni, izinli_sayilar)
        print(f"  red team itirazı: {len(red.get('itirazlar') or [])} "
              f"· mevzuata takılan düzeltme: {len(red_silinen)}")

    # Müşteriye giden HER metin imla denetiminden geçer (kapı değil, uyarı).
    musteri_metinleri: list[str] = []
    if konum:
        musteri_metinleri += [str(c) for c in (konum.get("satis_cumleleri") or [])]
        musteri_metinleri += [str(c) for c in (konum.get("baslik_onerileri") or [])]
    for s in senaryolar:
        musteri_metinleri += [str(s.get("hook") or ""), str(s.get("seslendirme") or ""),
                              str(s.get("cta") or "")]
        for sn in s.get("sahneler") or []:
            musteri_metinleri.append(str(sn.get("ekran_yazisi") or ""))
    imla_supheli = imla_denetimi(musteri_metinleri)
    if imla_supheli:
        print(f"  imla şüphelisi: {len(imla_supheli)} kelime "
              f"({', '.join(imla_supheli[:6])})")

    brief = {
        "fiyat_konumu_olcumu": fiyat_konumu,
        "imla_supheli": imla_supheli,
        "model_kademeleri": list(KADEME_KAYDI),
        "kurul": kurul,
        "red_team_silinen": red_silinen,
        "uretildi": datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M"),
        "urun": ozet, "zararina": zarar,
        "kreatif_sayisi": len(kreatifler), "aktif_kreatif": aktif,
        "tutarlilik": tutarlilik, "rakip": rakip,
        "konumlandirma": konum, "mevzuat_silinen": silinen,
        "gorseller": gorseller, "red_team": red,
        "senaryolar": senaryolar, "senaryo_silinen": senaryo_silinen,
        "atanan_uzmanlar": atanan_gorus,
        "kanca_havuzu": havuz,
        "kelime_karti": kelime_karti(ozet, kutu_bolum),
    }

    if a.guclu and KADEME_KAYDI:
        dusen = sum(1 for k in KADEME_KAYDI if k != "EXTERNAL_MODEL")
        if dusen:
            print(f"  🔴 {dusen}/{len(KADEME_KAYDI)} model çağrısı yerele "
                  f"düştü — brief'in bir kısmı zayıf dille yazılmış olabilir")

    CIKTI_KOK.mkdir(parents=True, exist_ok=True)
    kok = re.sub(r"[^A-Za-z0-9]+", "-", katla(ad.split("|")[0])).strip("-")
    damga = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    jp = CIKTI_KOK / f"{kok}-{damga}.json"
    mp = CIKTI_KOK / f"{kok}-{damga}.md"
    jp.write_text(json.dumps(brief, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(markdown_yaz(brief), encoding="utf-8")
    print(f"\n{mp}\n{jp}")
    return 0 if (konum and (rakip or a.rakipsiz)) else 3


if __name__ == "__main__":
    sys.exit(main())

