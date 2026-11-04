#!/usr/bin/env python3
"""Kutu metni (.docx) -> onaylı ürün gerçeği JSON'u.

NEDEN VAR
=========
Jarvis kreatif hattı (`kreatif-brief.py`) ürün gerçeği olarak YALNIZ Wix site
açıklamasını görüyordu (`urun_metni = ozet["aciklama"] + " " + ad`). Kullanım
talimatı, uyarılar ve INCI listesi hattın dışındaydı. Oysa hattın kendi istemi
"alıcı itirazının cevabı ürün kaydındaki İÇERİK ve KULLANIM bilgisinden
kurulur" diyor -- yani bilgiyi istiyor ama kimse vermemiş.

🔴 İZİN LİSTESİ, KARA LİSTE DEĞİL
=================================
Kutu .docx dosyalarının SONUNDA bileşen/etki tabloları var ve bu tablolar
YASAK İDDİA DOLU. Ölçülen gerçek satırlar:

    "Dolaşımı uyarır, folikül desteği"        (hair nourisher)
    "Hormon dengeleyici, kolajen uyarıcı"     (liftella)
    "Antimikrobiyal ve dolaşım uyarıcı"       (optywave)
    "Soğutucu etki, baş ağrısı hafifletici"   (aurolis)
    "Yatıştırıcı, topraklayıcı, bağımlılık kırıcı etki"  (nomore)
    "saç derisi mikrobiyotasını dengeler, bağışıklığı güçlendirir" (easycomb)

Bunlar hatta girerse felaket olur: `kreatif-brief.py` içindeki
`dayanak_kapisi()` bir cümleyi "ürün metninde geçiyor mu" diye denetliyor.
Tablo metne girerse model "antimikrobiyal" yazar ve kapı ONAYLAR -- çünkü
kelime gerçekten ürün kaydında geçiyor olur. Denetim kapısı, denetlemesi
gereken şeyin kaynağı hâline gelir.

Bu yüzden bu çıkarıcı SEÇEREK ALIR, atmaya çalışmaz:
sadece beş bölüm alınır (tanım · kullanım · uyarılar · raf ömrü · INCI),
geri kalan her şey -- tablolar dahil -- hiç okunmaz.

KULLANIM
========
    py kutu-gercegi-cikar.py                     # hepsi -> ./kutu-gercegi/
    py kutu-gercegi-cikar.py --urun easycomb     # tek ürün, ekrana
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

KUTU_DIZINI = Path.home() / "OneDrive" / "Masaüstü" / "02 LEMOS-MOY" / "lemos" / "kutu-icerik-son"
CIKTI_DIZINI = Path(__file__).resolve().parent / "kutu-gercegi"

# --- Alınacak bölümler (İZİN LİSTESİ) ---------------------------------------
# Sıra önemli: uzun başlık kısa olandan ÖNCE denenir ("Kullanım Talimatı"
# "Kullanım"dan önce), yoksa kısa olan uzunu yutar.
BOLUMLER: list[tuple[str, str]] = [
    ("tanim",     r"(?:Ürün\s*Tanımı|Ürün\s*Açıklaması|Açıklama|Tanım)"),
    ("kullanim",  r"(?:Kullanım\s*Talimatı|Kullanım\s*Şekli|Kullanım\s*Önerisi|Kullanım)"),
    ("uyarilar",  r"(?:Uyarılar|Uyarı)"),
    ("raf_omru",  r"(?:Raf\s*Ömrü)"),
    ("inci",      r"(?:İçindekiler|INCI\s*Listesi|İÇİNDEKİLER)"),
]

# Başlık satırının başındaki emoji/madde işaretleri ("📌 KULLANIM TALİMATI").
# 🔴 Ölçüldü: bunlar sökülmeyince EASYCOMB'un dört bölümü birden kayboluyordu.
ONEK_SUS = re.compile(r"^[\s\W_]*?(?=[A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû])", re.UNICODE)

# "İçindekiler (TR – INCI Hodan Yağı, ..." -- parantez KAPANMIYOR, bu yüzden
# \([^)]*\) kalıbı tutmuyordu ve INCI bölümü hiç yakalanmıyordu.
INCI_ETIKETI = re.compile(r"^\s*\(?\s*(?:TR|EN)?\s*[–\-]?\s*INCI\s*\)?\s*[:：]?\s*", re.IGNORECASE)
KISA_ETIKET = re.compile(r"^\s*\((?:[^)]{0,14})\)\s*[:：]?\s*")

# --- Bölümü BİTİREN işaretler ------------------------------------------------
# 🔴 Tablo başlangıçları buraya konur. Ölçüldü: NOMORE'da "İçindekiler (INCI)"
# bölümünün hemen ardından "Etki" tablosu geliyor; terminatör olmasa INCI
# bölümü tabloyu da yutardı ve yasak iddialar içeri sızardı.
BITIRICILER = re.compile(
    r"^\s*(?:"
    r"Etki(?:si)?|Kozmetik\s*Etki|Etki\s*\(Kozmetik\s*Tanım\)|Faydası|Fayda|"
    r"INCI\s*Adı|Bileşen|İçerik(?:\s*Oranı)?|Oran|Miktar|ml\s*/\s*g|"
    r"✅|💡|🌿|🧴|📌|⚠️"
    r")\s*[:\-–]?\s*$",
    re.IGNORECASE,
)

# İngilizce bölümler ayrı yakalanır ama şimdilik kullanılmıyor (TR hat).
EN_BASLIK = re.compile(
    r"^[\s\W_]*(?:EN\s*[–\-]|Product\s*Description|Directions|Cautions|Ingredients|Shelf\s*Life)",
    re.IGNORECASE)

# Brief'in dayanağı olan dört bölüm. `raf_omru` bilgi amaçlıdır, kreatife girmez.
ZORUNLU = ("tanim", "kullanim", "uyarilar", "inci")

AZAMI = {"tanim": 1400, "kullanim": 600, "uyarilar": 700, "raf_omru": 200, "inci": 1600}

# --- KİRLİLİK KAPISI ---------------------------------------------------------
# 🔴 Terminatör listesi yetmiyor. Ölçüldü: KINESIS+'ta "Uyarı" başlığı tablonun
# İÇİNDE geçiyor ve tablo satırları tek paragrafa dizildiği için hiçbir
# terminatör satırı yok -- bölüm tabloyu yuttu ve "antimikrobiyal" dışarı sızdı.
#
# Bu yüzden çıkarımın kendisi denetlenir: bir bölümde tablo iddia sözcüğü
# görülürse o bölüm ÇIKTIYA ALINMAZ ve raporlanır. Yarım doğru bir bölüm,
# olmayan bölümden tehlikelidir -- çünkü hat onu "ürün kaydı" sayar.
KIRLI = re.compile(
    r"(?:antimikrobiyal|antibakteriyel|antiseptik|antiviral|antifungal|"
    r"anti[\s-]?enflamatuar|antienflamatuar|antiinflamatuar|inflamasyon|"
    r"dolaşım|kan\s*akışı|mikrosirkülasyon|lenf|"
    r"hücre\s*yenile|doku\s*onarım|doku\s*yenile|kolajen|elastikiyet\s*art|"
    r"hormon\s*dengele|bağışıklık|metabolizma|toksin|detoks|"
    r"folikül|kepek|bağımlılık\s*kırıcı|baş\s*ağrısı|"
    r"mikrobiyota|yara\s*iyileş|iz\s*giderici)",
    re.IGNORECASE)


def docx_metni(yol: Path) -> str:
    """docx -> düz metin. Paragraf sınırları korunur."""
    with zipfile.ZipFile(yol) as z:
        ham = z.read("word/document.xml").decode("utf-8", "replace")
    ham = re.sub(r"</w:p>", "\n", ham)
    ham = re.sub(r"<w:tab/>", " ", ham)
    ham = re.sub(r"<[^>]+>", "", ham)
    import html
    return html.unescape(ham)


def katla(metin: str) -> str:
    """Türkçe güvenli anahtar. kreatif-brief.py:katla() ile AYNI davranış.

    🔴 .lower() kullanılmaz: Türkçe I→ı dönüşümü "HYDRAVIE" ile "Hydravie"yi
    ayırabiliyor. Bkz. [[turkce-metin-eslesme-tuzagi]]
    """
    duz = unicodedata.normalize("NFKD", metin)
    duz = "".join(c for c in duz if not unicodedata.combining(c))
    return duz.casefold().replace("’", "'").replace("i̇", "i")


def _baslik_mi(satir: str) -> tuple[str, str] | None:
    """Satır bir bölüm başlığıysa (anahtar, aynı satırdaki içerik) döner.

    Kutu metinlerinde başlık ve içerik ÇOĞU ZAMAN aynı satırda:
        "Kullanım:Temiz ve kuru cilde ince bir tabaka halinde uygulanır"
    """
    sade = ONEK_SUS.sub("", satir)          # emoji/madde işareti önekini sök
    for anahtar, kalip in BOLUMLER:
        e = re.match(rf"^(?:TR\s*[–\-]\s*)?{kalip}\s*[:：]?\s*(.*)$", sade, re.IGNORECASE)
        if not e:
            continue
        kalan = e.group(1).strip()
        # "Kullanım" diye geçen ama başlık OLMAYAN uzun cümleleri ele:
        # başlıktan sonra ya iki nokta vardı ya da satırın kalanı kısaydı.
        if ":" not in sade and len(kalan) > 120:
            return None
        if anahtar == "inci":
            kalan = INCI_ETIKETI.sub("", kalan)
        kalan = KISA_ETIKET.sub("", kalan)
        return anahtar, kalan.strip()
    return None


def bolumle(metin: str) -> dict[str, str]:
    """🔴 SEÇEREK ALIR. Tanınmayan hiçbir şey çıktıya girmez."""
    bulunan: dict[str, list[str]] = {}
    aktif: str | None = None
    ilk_paragraflar: list[str] = []
    basliga_girildi = False

    for ham_satir in metin.split("\n"):
        satir = re.sub(r"[ \t ]+", " ", ham_satir).strip()
        if not satir:
            continue

        if BITIRICILER.match(satir):
            aktif = None            # tablo başladı -> toplamayı KES
            continue
        if EN_BASLIK.match(satir):
            aktif = None            # EN bloğu -> TR hattı için toplamıyoruz
            continue

        vurus = _baslik_mi(satir)
        if vurus:
            basliga_girildi = True
            aktif = vurus[0]
            bulunan.setdefault(aktif, [])
            if vurus[1]:
                bulunan[aktif].append(vurus[1])
            continue

        if aktif:
            bulunan[aktif].append(satir)
        elif not basliga_girildi and len(satir) > 60:
            # Başlıksız giriş paragrafı (ör. "L'CARLIE Dorsivia, doğal yağlar...")
            ilk_paragraflar.append(satir)

    sonuc = {a: " ".join(p).strip() for a, p in bulunan.items() if " ".join(p).strip()}

    # Tanım başlığı yoksa başlıksız giriş paragrafını tanım say.
    if "tanim" not in sonuc and ilk_paragraflar:
        aday = max(ilk_paragraflar, key=len)
        if katla("l'carlie") in katla(aday) or len(aday) > 120:
            sonuc["tanim"] = aday

    return {a: m[: AZAMI.get(a, 800)] for a, m in sonuc.items()}


def urun_adi_cikar(dosya_adi: str) -> str:
    """'37-easycomb' -> 'easycomb' · '2- AUROLİS' -> 'AUROLIS'"""
    ad = re.sub(r"^\s*\d+\s*[-–]\s*", "", dosya_adi).strip()
    return re.sub(r"\s+", " ", ad)


# 🔴 `tanim` DAYANAĞA GİRMEZ -- kasıtlı.
#
# Kutu metnindeki ürün tanımı PAZARLAMA metnidir ve mevzuat temizliğinden
# geçmemiştir. Ölçülen örnek (EASYCOMB kutusu): "saçları beslerken",
# "probiyotik kompleks, saç derisinin doğal dengesini korumaya destek olur".
# Aynı ürünün canlı site metni bu iki ifadeyi 13.09.2026 temizliğinde
# ÇIKARMIŞ. Kutu tanımını dayanak yaparsak o temizliği geri almış oluruz.
#
# Her kaynak yalnız OTORİTE OLDUĞU şeyi verir:
#   Wix açıklaması  -> ürün tanımı (zaten hatta var, temizlikten geçmiş)
#   Kutu metni      -> kullanım talimatı · uyarılar · INCI (olgusal, pazarlama değil)
DAYANAK_BOLUMLERI = ("kullanim", "uyarilar", "inci")


def islem(yol: Path) -> dict:
    metin = docx_metni(yol)
    bolum = bolumle(metin)
    ad = urun_adi_cikar(yol.stem)

    kirli = {a: KIRLI.search(m).group(0) for a, m in bolum.items() if KIRLI.search(m)}
    for a in kirli:
        bolum.pop(a, None)

    eksik = [a for a in ZORUNLU if a not in bolum]
    return {
        "urun_adi": ad,
        "urun_anahtari": katla(ad).replace(" ", ""),
        "kaynak": yol.name,
        "kaynak_tur": "onayli_kutu_metni",
        "bolumler": bolum,
        "eksik_bolumler": eksik,
        "kirli_bolumler": kirli,      # tablo sızıntısı nedeniyle atılanlar
        # Hattın urun_metni'ne EKLENECEK metin. Etki tablosu ve kutu tanımı YOK.
        "dayanak_metni": " ".join(
            bolum.get(a, "") for a in DAYANAK_BOLUMLERI).strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urun", help="yalnız bu ürün (ada göre eşleşir)")
    ap.add_argument("--dizin", type=Path, default=KUTU_DIZINI)
    ap.add_argument("--cikti", type=Path, default=CIKTI_DIZINI)
    a = ap.parse_args()

    if not a.dizin.is_dir():
        print(f"kutu dizini yok: {a.dizin}", file=sys.stderr)
        return 1

    dosyalar = sorted(a.dizin.glob("*.docx"))
    if a.urun:
        hedef = katla(a.urun)
        dosyalar = [d for d in dosyalar if hedef in katla(d.stem)]
        if not dosyalar:
            print(f"eşleşen kutu metni yok: {a.urun}", file=sys.stderr)
            return 1

    a.cikti.mkdir(parents=True, exist_ok=True)
    kayitlar = []
    for yol in dosyalar:
        try:
            kayit = islem(yol)
        except Exception as hata:  # noqa: BLE001
            print(f"  HATA {yol.name}: {hata}", file=sys.stderr)
            continue
        kayitlar.append(kayit)
        (a.cikti / f"{kayit['urun_anahtari']}.json").write_text(
            json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")

    (a.cikti / "_hepsi.json").write_text(
        json.dumps(kayitlar, ensure_ascii=False, indent=1), encoding="utf-8")

    tam = [k for k in kayitlar if not k["eksik_bolumler"]]
    print(f"{len(kayitlar)} ürün işlendi -> {a.cikti}")
    print(f"  dört zorunlu bölümü tam olan: {len(tam)}/{len(kayitlar)}")
    for k in kayitlar:
        if k["kirli_bolumler"]:
            detay = ", ".join(f"{a}→'{s}'" for a, s in k["kirli_bolumler"].items())
            print(f"  KİRLİ  {k['urun_adi']:<22} atıldı: {detay}")
    for k in kayitlar:
        if k["eksik_bolumler"]:
            print(f"  eksik  {k['urun_adi']:<22} {','.join(k['eksik_bolumler'])}")

    # Son kontrol: hiçbir dayanak metni kirli olmamalı.
    sizan = [k["urun_adi"] for k in kayitlar if KIRLI.search(k["dayanak_metni"])]
    print(f"  sızıntı denetimi: {'TEMİZ' if not sizan else 'BAŞARISIZ → ' + ', '.join(sizan)}")
    if a.urun and kayitlar:
        print()
        print(json.dumps(kayitlar[0], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
