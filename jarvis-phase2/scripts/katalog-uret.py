#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eczane/profesyonel kataloğunu ÖLÇÜLMÜŞ kaynaklardan üretir.

NEDEN ÜRETİCİ, NEDEN ELLE YAZILMIŞ BİR KATALOG DEĞİL
Katalogda 36 ürün var. Her ürünün ne içerdiğini ve ne söylenebileceğini
kendi bilgimden yazmak UYDURMA olurdu. Bu betik her satırı kaynaktan
türetir ve türetemediği yeri "kaynakta yok" diye İŞARETLER -- boş bırakıp
geçmez, çünkü eksik olduğu görünmeyen bilgi, var sanılır.

KAYNAKLAR (hepsi ölçülmüş)
  raw.wix_urun       yayındaki açıklama HTML'i, INCI, fiyat, görsel adresi
  mart.urun_karti    fiyat/stok otoritesi
  jarvis.compliance  TİTCK iddia denetçisi
  katalog-gorsel/    sunucumuza indirilmiş ürün görselleri

🔴 METİN BİLGİ DOSYALARINDAN ALINMAZ. knowledge/30-urun-*.md dosyalarının
beşinde "🔒 İÇ BİLGİ — ESKİ KATALOG (MÜŞTERİYE ÇIKAMAZ)" başlıklı bölüm
var: eski katalogun bloklu tıbbi iddiaları (panik atak, migren, yatak
yarası...). O dosyalar Jarvis'in İÇ bilgisi; katalog ECZANEYE gidiyor.
Kaynak olarak yayındaki Wix metni kullanılır -- hem gerçek (sitede duruyor)
hem denetimden geçmiş.

ÜÇ KÜME AYRI TUTULUR (aynı hatayı urun-bilgi-uret.py'de bir kez yaptık)
  satış cümlesi     denetimden temiz geçen, sunumda söylenebilir
  zorunlu uyarı     mevzuatın KENDİSİNİN istediği -- ne satış ne kusur
  kusurlu cümle     yayında duran ama denetime takılan -- KATALOGA GİRMEZ,
                    rapora girer; Wix'te düzeltilmesi gerekir

ÇIKTI: state/katalog.json  (panel bunu okur, her açılışta yeniden
hesaplamaz -- 36 ürün × ~20 cümle denetimi saniyeler sürer)
"""
from __future__ import annotations

import html as html_mod
import json
import os
import pathlib
import re
import subprocess
import sys
import time

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis import compliance  # noqa: E402

KAP = "lcarlie-postgres"
GORSEL_DIZIN = pathlib.Path("/opt/lcarlie/katalog-gorsel")
CIKTI = pathlib.Path(os.environ.get(
    "JARVIS_STATE_DIR", str(KOK / "state"))) / "katalog.json"

EN_COK_SATIS_CUMLESI = 8

SORGU = """
SELECT row_to_json(t) FROM (
  SELECT w.sku, w.ad, w.slug,
         w.ham->>'description' AS html,
         k.wix_satis, k.wix_stok, k.wix_yayinda,
         k.trendyol_satis, k.birim_maliyet, k.maliyet_kaynagi
    FROM raw.wix_urun w
    LEFT JOIN mart.urun_karti k ON k.sku = w.sku AND k.urun_adi = w.ad
   ORDER BY w.ad
) t;
"""


def oku(sql: str) -> list[dict]:
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input="\\set ON_ERROR_STOP on\n" + sql, capture_output=True,
        text=True, timeout=120, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:400])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


# --- HTML bolumleme --------------------------------------------------------
#
# 🔴 IKI OLCUM HATASI, IKISI DE BENDE.
#
# (1) ILK AYRISTIRICI <strong> ETIKETINE BAKIYORDU ve 12 urunun INCI'sini
#     kacirdi. Ayni bilgi dort ayri bicimde yaziliyor:
#       <strong>Ingredients (INCI):</strong>   DERMABED
#       <p>INCI:</p>                           BUGUARD    -- etiket yok
#       <font..><b>INCI:</b></font>            DERMARNICA -- <b>, <strong> degil
#       <br><br>INCI Listesi&nbsp;AQUA...      KINESIS    -- hic etiket yok
#     Etikete bakmak yanlis eksendi; dogru eksen METIN.
#
# (2) METNE GECINCE BES URUN GERILEDI. Sebep: bazi urunlerde baslik
#     BIRLESIK -- "İçindekiler (INCI)", "İÇİNDEKİLER / INCI",
#     "İçindekiler  INCI". Baslik hangi listenin geldigini SOYLEMIYOR:
#     CAL JAW'da govde Ingilizce (Borago Officinalis...), OPTYWAVE'de
#     Turkce (Hodan Yagi...). Ayni baslik, iki farkli liste.
#
#     Dogrusu: ICERIGIN DILINE bakmak. INCI adlari Latincedir; Turkce
#     listede "yağı, ekstresi, suyu" gecer. Bu yuzden ayristirma iki
#     asamali: tarayici TUM baslik-govde ciftlerini toplar, sonra
#     siniflandirici hangisinin INCI hangisinin Turkce oldugunu govdeden
#     karara baglar.
#
# Eksik INCI sessizce gecilemez: eczaneye "icerigi bilmiyoruz" diyen bir
# katalog, eczacinin sormasi gereken ilk soruya cevap veremez.

_ETIKET = re.compile(r"<[^>]+>")
_BOSLUK = re.compile(r"[ \t ]+")
# Blok sinirlari satir sonuna cevrilir; yoksa iki bolum tek satirda birlesir.
_BLOK = re.compile(r"</?\s*(p|br|div|li|tr|h[1-6])\b[^>]*>", re.IGNORECASE)

# Baslik olarak taninan kaliplar. Govde ayni satirda da olabilir, bu yuzden
# baslik kismi ayri gruplanir ve kirpilir.
BASLIK_KALIPLARI = [
    # "EN (International)" ve "TR (Türkçe)" basliklari BABYSHOWER'da
    # kullaniliyor; taninmazsa INCI listesi anlatiya sizar ve urunun
    # tanitim cumlesi "Aqua, Decyl Glucoside, ..." olur (olculdu).
    ("icerik",   r"^((?:ingredients|inci|i̇?çindekiler|icindekiler|bileşenler|"
                 r"içerik|i̇çerik|"
                 r"türkçe\s*(?:içerik|i̇?çindekiler)|"
                 r"(?:en|tr)\s*\((?:international|türkçe|turkce|inci)\)|"
                 # Yalin "(EN)" / "(TR)" basligi: BABYSOL, LUCIDERM ve
                 # SOFTGUARD'da INCI listesi boyle isaretlenmis. Taninmazsa
                 # liste satis cumlesi sanilir ve eczaciya "Aqua, Zinc
                 # Oxide, ..." diye okunur (olculdu).
                 r"\((?:en|tr|international)\))"
                 r"(?:\s*[/(]?\s*(?:inci|tr|en|listesi|listesi\s*\(tr\))\s*\)?)*)"
                 r"\s*:?\s*"),
    ("kullanim", r"^(kullanım(?:\s*(?:şekli|talimatı))?(?:\s*\((?:tr|en)\))?)\s*:?\s*"),
    ("uyarilar", r"^(uyarı(?:lar)?(?:\s*\((?:tr|en)\))?)\s*:?\s*"),
    ("raf_omru", r"^(raf\s*ömrü|son\s*kullanma(?:\s*tarihi)?)\s*:?\s*"),
    ("saklama",  r"^(saklama(?:\s*koşulları)?)\s*:?\s*"),
]

# 🔴 UCUNCU OLCUM HATASI. Ilk surumde bu iki kume tek listeydi ve sonuc
# olculdu: 36 urunun 34'unde tanitim cumlesi "Kargo & Teslimat: 16:00'a
# kadar verilen siparisler ayni gun kargoda" cikti. Kargo blogu aciklamanin
# BASINDA duruyor; cumleleri sirayla alinca ilk cumle o oldu.
#
# Eczacinin karsisinda urunu "16:00'a kadar kargoda" diye tanitmak,
# katalogun tek isini yapmamasidir.
#
# Iki kume ayrildi:
#   TICARI   kargo/iade/odeme -- URUN BILGISI DEGIL, anlatidan tamamen atilir
#   BOLUM_SONU  "one cikan ozellikler" gibi -- acik bolumu bitirir ama
#               govdesi anlatida KALIR, cunku orada urun anlatiliyor
TICARI = re.compile(
    r"^(kargo|iade|cayma|güvenli\s*alışveriş|ödeme|teslimat|ücretsiz\s*kargo"
    r"|satıcı|garanti\s*ve\s*iade|etbis)\b", re.IGNORECASE)

BOLUM_SONU = re.compile(
    r"^(öne\s*çıkan|ürün\s*özellikleri|neden|hakkında|etiket|not|açıklama"
    r"|özellikler)\b", re.IGNORECASE)

# Ticari blok icinde kalmis, basligi olmayan kalip cumleler. Kargo blogu
# bazi urunlerde basliksiz geliyor; satir satir eleniyor.
TICARI_CUMLE = re.compile(
    r"kargoya\s*teslim|kargo\s*(ücretsiz|bedeli)|kapıda\s*ödeme"
    r"|3d\s*secure|cayma\s*hak|mesafeli\s*sözleşme|iade\s*kargo"
    r"|info@lcarlie|hafta\s*sonu\s*ve\s*resmi\s*tatil"
    r"|16:00'?a\s*kadar|ilk\s*iş\s*günü|kart\s*bilgileriniz",
    re.IGNORECASE)

# Turkce icerik listesinin isaretleri. INCI adlari Latincedir ve bunlari
# tasimaz ("Oil", "Extract", "Juice" gecer).
_TURKCE_ICERIK = re.compile(
    r"\b(yağı|yagi|ekstresi|suyu|özü|ozu|vitamini|asidi|tozu|çiçeği|"
    r"yaprağı|kökü|tohumu|kabuğu|balı|sirkesi|tuzu|kili)\b", re.IGNORECASE)


def duz(parca: str) -> str:
    m = html_mod.unescape(_ETIKET.sub(" ", parca or ""))
    return _BOSLUK.sub(" ", m).strip(" :·-–—\n")


def satirla(ham: str) -> list:
    """HTML -> satirlar. Blok sinirlari korunur."""
    m = _BLOK.sub("\n", ham or "")
    m = html_mod.unescape(_ETIKET.sub("", m))
    return [s for s in (_BOSLUK.sub(" ", x).strip() for x in m.split("\n")) if s]


def _baslik_coz(yalin: str):
    """(tur, baslik, ayni satirdaki govde) ya da None."""
    for tur, kalip in BASLIK_KALIPLARI:
        e = re.match(kalip, yalin, re.IGNORECASE)
        if not e:
            continue
        baslik = e.group(1)
        kalan = yalin[e.end():].strip(" :·-–—")
        # Baslik satiri kisa olmali; uzunsa bu bir cumledir, baslik degil.
        # ("Kullanım sırasında..." diye baslayan cumle baslik sanilmasin.)
        if not kalan and len(yalin) > len(baslik) + 26:
            return None
        return tur, baslik, kalan
    return None


def bolumle(ham: str):
    """(bolumler, anlati) dondurur.

    ANLATI, urunun ANLATILDIGI metindir: basliksiz giris paragraflari +
    "one cikan ozellikler" gibi bolumlerin govdesi. Icinden atilanlar:
      * ticari kosullar (kargo/iade/odeme) -- urun bilgisi degil
      * icerik listeleri (INCI/icindekiler) -- cumle degil, liste;
        cumleye bolunurse "Aqua" tek basina bir cumle sanilir
      * raf omru / saklama -- kendi alanlarinda zaten var

    Tanitim cumlesi ve satis cumleleri ANLATIDAN cikarilir, ham metnin
    tamamindan degil.
    """
    ciftler = []          # [(tur, baslik, govde)]
    acik = None           # (tur, baslik)
    birikim = []
    anlati = []
    ticari_acik = False

    def kapat():
        if acik:
            govde = " ".join(birikim).strip(" :·-–—")
            if len(govde) >= 12:
                ciftler.append((acik[0], acik[1], govde))

    for satir in satirla(ham):
        yalin = satir.strip(" :·-–—")

        tic = TICARI.match(yalin)
        if tic:
            kapat()
            acik, birikim = None, []
            # 🔴 DORDUNCU OLCUM HATASI. Ilk surumde burada kosulsuz
            # `ticari_acik = True` yaziyordu ve dokuz urunun ANLATISI
            # TAMAMEN bosaldi (anlati=0). Sebep: kargo blogu tek satir --
            # "Kargo & Teslimat: 16:00'a kadar ... Ucretsiz gonderim" --
            # yani baslik ve govde ayni satirda, blok o satirda BITIYOR.
            # Acik birakinca sonraki paragraflar, yani urunun asil metni,
            # ticari blok sanildi ve atildi. Blok yalniz baslik TEK BASINA
            # bir satirdaysa acik kalir.
            ticari_acik = len(yalin) - tic.end() < 12
            continue

        coz = _baslik_coz(yalin)
        if coz or BOLUM_SONU.match(yalin):
            kapat()
            acik, birikim = None, []
            ticari_acik = False      # yeni baslik ticari blogu bitirir
            if coz:
                tur, baslik, kalan = coz
                if len(kalan) >= 12:
                    ciftler.append((tur, baslik, kalan))
                else:
                    acik, birikim = (tur, baslik), []
            continue

        if ticari_acik or TICARI_CUMLE.search(yalin):
            continue

        if acik:
            birikim.append(satir)
            # Uyari bolumunun govdesi anlatiya da girer: zorunlu uyarilar
            # ayiklama asamasinda ayri kumeye dusuyor, burada elemek
            # onlari tamamen kaybettirirdi.
            if acik[0] == "uyarilar":
                anlati.append(satir)
            continue

        anlati.append(satir)
    kapat()

    # --- siniflandirma ---
    bulunan = {}
    for tur, baslik, govde in ciftler:
        if tur == "icerik":
            continue
        bulunan.setdefault(tur, govde)

    # Icerik listeleri: hangisi INCI, hangisi Turkce? GOVDEYE bakilir.
    for _, baslik, govde in [c for c in ciftler if c[0] == "icerik"]:
        anahtar = "icindekiler" if _TURKCE_ICERIK.search(govde) else "inci"
        bulunan.setdefault(anahtar, govde)

    return bulunan, " ".join(anlati).strip()


# --- Cumle ayirma ve denetim ----------------------------------------------
_UYARI = re.compile(
    r"kullanımı?\s*(bırak|durdur|kesin)|kullanmayı\s*bırak|"
    r"uygulama(yınız|yin)|uygulanmamalı|"
    r"doktora\s*danış|doktorunuza\s*danış|hekime\s*başvur|"
    r"uzak\s*tut|saklayın|temasından\s*kaçın|yutulmamalı|"
    r"harici\s*kullanım|çocukların\s*(ula|eri)|"
    r"%100\s*koruma\s*sağlamaz|2\s*mg/cm|"
    r"test(ler)?le\s*değerlendiril", re.IGNORECASE)

BELGE_DUZEYI = frozenset({"güneş koruyucu zorunlu ibare eksik", "hashtag tavanı"})


def ayikla(metin: str) -> tuple[list, list, list]:
    """(satış cümleleri, zorunlu uyarılar, kusurlu cümleler)."""
    temiz, uyarilar, kusurlu = [], [], []
    for c in compliance.sentences(metin):
        c = c.strip()
        if len(c) < 25:
            continue
        if _UYARI.search(c):
            uyarilar.append(c)
            continue
        bulgular = [f for f in compliance.review(c).findings
                    if f.rule not in BELGE_DUZEYI]
        if bulgular:
            kusurlu.append({"cumle": c,
                            "kural": sorted({f.rule for f in bulgular})})
        else:
            temiz.append(c)
    return temiz, uyarilar, kusurlu


def belge_bulgulari(metin: str) -> list:
    return sorted({f.rule for f in compliance.review(metin).findings
                   if f.rule in BELGE_DUZEYI})


def main() -> int:
    t0 = time.time()
    kayitlar = oku(SORGU)
    if not kayitlar:
        print("DURDU: urun bulunamadi")
        return 1

    gorsel_dizin = {}
    dizin_yolu = GORSEL_DIZIN / "dizin.json"
    if dizin_yolu.exists():
        for g in json.loads(dizin_yolu.read_text(encoding="utf-8")):
            gorsel_dizin.setdefault(g["slug"], []).append(g)
    else:
        print("UYARI: gorsel dizini yok -- once katalog-gorsel-indir.py")

    urunler, sorunlar = [], []
    for k in kayitlar:
        ham = k.get("html") or ""
        bolumler, anlati = bolumle(ham)
        # 🔴 ANLATIDAN, ham metnin tamamindan DEGIL: ham metinde kargo blogu
        # basta duruyor ve tanitim cumlesi olarak o secilirdi (34/36 urunde
        # oldu).
        temiz, uyarilar, kusurlu = ayikla(anlati)
        belge = belge_bulgulari(anlati)

        gorseller = [g["dosya"] for g in
                     sorted(gorsel_dizin.get(k["slug"], []),
                            key=lambda g: (not g["ana"], g["sira"]))]

        urun = {
            "slug": k["slug"],
            "ad": k["ad"],
            "sku": k["sku"],
            "fiyat": k.get("wix_satis"),
            "stok": k.get("wix_stok"),
            "yayinda": k.get("wix_yayinda"),
            "gorseller": gorseller,
            # Tek cümlelik tanıtım: denetimden geçmiş İLK cümle.
            "ozet": temiz[0] if temiz else None,
            "satis_cumleleri": temiz[1:1 + EN_COK_SATIS_CUMLESI],
            "zorunlu_uyarilar": uyarilar,
            "inci": bolumler.get("inci"),
            "icindekiler": bolumler.get("icindekiler"),
            "kullanim": bolumler.get("kullanim"),
            "uyarilar_metni": bolumler.get("uyarilar"),
            "raf_omru": bolumler.get("raf_omru"),
            "saklama": bolumler.get("saklama"),
            "anlati_uzunluk": len(anlati),
        }
        urunler.append(urun)

        # Kusurlar KATALOGA GIRMEZ ama rapora girer: yayindaki metnin kendi
        # kusuru, kataloğun degil. Gizleseydik Wix'te oylece kalirdi.
        if kusurlu or belge or not gorseller or not urun["inci"]:
            sorunlar.append({
                "ad": k["ad"], "slug": k["slug"],
                "gorsel_yok": not gorseller,
                "inci_yok": not urun["inci"],
                "belge_bulgulari": belge,
                "kusurlu_cumleler": kusurlu,
            })

    # Ayni barkodu tasiyan urunler: eczanede barkod okutulur, catisma
    # sessiz kalirsa yanlis urun satilir.
    barkod = {}
    for u in urunler:
        barkod.setdefault(u["sku"], []).append(u["ad"])
    cakisan = {s: a for s, a in barkod.items() if len(a) > 1}

    cikti = {
        "uretim_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "urun_sayisi": len(urunler),
        "urunler": urunler,
        "kapsama": {
            "gorselli": sum(1 for u in urunler if u["gorseller"]),
            "inci_var": sum(1 for u in urunler if u["inci"]),
            "icindekiler_var": sum(1 for u in urunler if u["icindekiler"]),
            "kullanim_var": sum(1 for u in urunler if u["kullanim"]),
            "ozeti_var": sum(1 for u in urunler if u["ozet"]),
            "anlatisi_kisa": sum(1 for u in urunler if u["anlati_uzunluk"] < 200),
        },
        "sorunlar": sorunlar,
        "barkod_cakismasi": cakisan,
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    gecici = CIKTI.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(cikti, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    gecici.replace(CIKTI)

    kap = cikti["kapsama"]
    print("katalog: %d urun · %.1f sn · %s" % (len(urunler), time.time() - t0, CIKTI))
    print("  gorselli %d · INCI %d · icindekiler %d · kullanim %d · ozet %d"
          % (kap["gorselli"], kap["inci_var"], kap["icindekiler_var"],
             kap["kullanim_var"], kap["ozeti_var"]))
    print("  sorunlu urun: %d · barkod cakismasi: %d"
          % (len(sorunlar), len(cakisan)))
    for s, adlar in cakisan.items():
        print("  🔴 AYNI BARKOD %s -> %s" % (s, " + ".join(adlar)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
