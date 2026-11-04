#!/usr/bin/env python3
"""Idefix urun basliklari — SEO + satis odakli, mevzuat filtresinden gecirilmis.

KALIP
  L'CARLIE <Urun Adi> <Aranan Jenerik Tur> <Ayirt Edici> <Hacim>

  - Marka basta: pazaryeri yazim kurali ve marka taninirligi.
  - "Aranan jenerik tur" musterinin ARAMA KUTUSUNA yazdigi sozdur
    ("bebek sampuani", "ayak bakim kremi") -- urun adi aranmaz, tur aranir.
  - Ayirt edici: kutudan/INCI'den DOGRULANMIS bir ozellik. Uydurulmaz;
    BABYSOL'de "Cinko Oksitli" yazilir cunku formul oyle, ama SPF YAZILMAZ
    cunku deger hicbir kaynakta belirtilmemis.
  - Hacim sonda: pazaryeri aramasinda ayirt edici, iade sorularini azaltir.

MEVZUAT (Masaustu\\01 LCARLIE\\KATALOG-YAZIM-KILAVUZU.md)
  - Yasak NESNE yok: hucre, doku, damar, dolasim, kan, hormon, kas...
  - Hastalik/lezyon adi yok: nasir, akne, mantar, yara, dokulme, kasinti...
  - Tedavi dili yok: onarici, tedavi, iyilestirir, onler
  - Ilac karinesi yok: antibakteriyel, antiseptik, dezenfekte
  - One cikarilamayan bilesen yok: epimedium, tribulus, damiana, maca, arjinin
  - Ustunluk iddiasi yok: en iyi, aninda, mucizevi
  - 🔴 Kilavuz §4: SUNACNEA'da "+30 SPF" DEGIL "SPF 30" yazilir.

Her baslik `compliance.review`den gecirilir; bulgu varsa dosyaya YAZILMAZ.
"""
from __future__ import annotations

import csv
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import compliance  # noqa: E402

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
RAPOR = Path("/opt/lcarlie/idefix-hazirlik/BASLIKLAR.md")
UZUNLUK_SINIR = 120

# "Zorunlu ibare" kurallari ibarenin YOKLUGUNU bulgu sayar. Baslik tek basina
# tarandiginda o ibareler zaten yoktur -- yerleri aciklamadir. Bu yuzden
# baslikta bu sinif YOK SAYILIR; ayni kural listeleme metninin TAMAMI
# (baslik + aciklama) uzerinde ayrica kosulur ve eksik ibare oradan raporlanir.
IBARE_KURALI = "zorunlu ibare"

# Ayrac olarak nadir bir dizi; aciklamalarda '|' gectigi icin psql'in
# varsayilan ayraci kullanilamaz. Satir sonlari chr(10)/chr(13) ile
# bosluga cevrilir -- kacis dizisi yazmamak icin bilerek chr() kullanildi.
AYRAC = "<<>>"
ACIKLAMA_SQL = (
    "select sku || '" + AYRAC + "' || "
    "replace(replace(regexp_replace(ham->>'description','<[^>]+>',' ','g'), "
    "chr(10), ' '), chr(13), ' ') from raw.wix_urun;")


def wix_aciklamalari() -> dict[str, str]:
    """Aciklamalar CSV'de tasinmiyor; dogrudan aynadan okunur."""
    c = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql",
                        "-U", "n8n", "-d", "n8n", "-At", "-f", "-"],
                       input=ACIKLAMA_SQL, capture_output=True, text=True, check=True)
    d = {}
    for satir in c.stdout.splitlines():
        if AYRAC in satir:
            sku, metin = satir.split(AYRAC, 1)
            d[sku] = html.unescape(re.sub(r"[ ]+", " ", metin)).strip()
    return d

# barkod -> (baslik, aranan jenerik tur = SEO cekirdegi)
BASLIK: dict[str, tuple[str, str]] = {
    "8684869609363": ("L'CARLIE Baby Rescue Bebek Bakım Balmı Bölgesel Kullanım 5 ml",
                      "bebek bakım balmı"),
    "8684869609387": ("L'CARLIE Babydent Bebek ve Çocuk Diş Bakım Jeli 50 ml",
                      "bebek diş bakım jeli"),
    "8684869609356": ("L'CARLIE Babyshower Bebek Şampuanı Günlük Kullanım 400 ml",
                      "bebek şampuanı"),
    "8684869609523": ("L'CARLIE Babysoft Bebek Vücut Losyonu Nemlendirici 200 ml",
                      "bebek vücut losyonu"),
    "8684869609530": ("L'CARLIE Babysol Bebek Güneş Kremi Çinko Oksitli 150 ml",
                      "bebek güneş kremi"),
    "8684869609394": ("L'CARLIE Bright Smile Bitkisel Diş Macunu Naneli 50 ml",
                      "bitkisel diş macunu"),
    "8684869609301": ("L'CARLIE Buguard Bitkisel Vücut Spreyi Aromatik 100 ml",
                      "bitkisel vücut spreyi"),
    "8684869609196": ("L'CARLIE Caljaw Çene Çevresi Bakım Roll-On Gece Kullanımı 10 ml",
                      "çene çevresi bakım roll-on"),
    "8684869609080": ("L'CARLIE Calmaros Ferahlatıcı Tonik Sprey Yüz ve Vücut 200 ml",
                      "ferahlatıcı tonik sprey"),
    "8684869609578": ("L'CARLIE Calmoris Rahatlatıcı Aromatik Bakım Roll-On 10 ml",
                      "aromatik bakım roll-on"),
    "8684869609066": ("L'CARLIE Dermabed Bariyer ve Koruyucu Bakım Kremi Vücut 200 ml",
                      "bariyer bakım kremi"),
    "8684869609288": ("L'CARLIE Dermacorn Sertleşmiş Bölge Bakım Kremi Üre İçerikli 10 ml",
                      "sertleşmiş bölge bakım kremi"),
    "8684869609103": ("L'CARLIE Dermaguard Ayak ve Tırnak Bakım Kremi 50 ml",
                      "ayak ve tırnak bakım kremi"),
    "8684869609516": ("L'CARLIE Dermamovera Bitkisel Masaj ve Bakım Kremi 200 ml",
                      "bitkisel masaj kremi"),
    "8684869609073": ("L'CARLIE Dermanova İz Görünümü Bakım Kremi Bitkisel 50 ml",
                      "iz görünümü bakım kremi"),
    "8684869609554": ("L'CARLIE Dermarnica Arnika Özlü Bitkisel Bakım Kremi 50 ml",
                      "arnika özlü krem"),
    "8684869609561": ("L'CARLIE Dermastra Gerilme Bölgeleri Bakım Kremi Vücut 100 ml",
                      "gerilme bölgeleri bakım kremi"),
    "8684869609271": ("L'CARLIE Dermavasc Bacak ve Vücut Bakım Kremi 50 ml",
                      "bacak bakım kremi"),
    "8684869609400": ("L'CARLIE Dorsivia Isınma Etkili Masaj Kremi Bitkisel 100 ml",
                      "ısınma etkili masaj kremi"),
    "8684869609370": ("L'CARLIE Easycomb Bebek ve Çocuk Saç Bakım Spreyi Kolay Tarama 100 ml",
                      "bebek saç bakım spreyi"),
    "8684869609127": ("L'CARLIE Femisia Kadınlara Özel Bitkisel İntim Bakım Kremi 50 ml",
                      "intim bakım kremi"),
    "8684869609158": ("L'CARLIE Hair Nourisher Bitkisel Saç Bakım Yağı 100 ml",
                      "saç bakım yağı"),
    "8684869609233": ("L'CARLIE Hydravie Yoğun Nemlendirici Yüz Kremi Kuru ve Hassas Ciltler 50 ml",
                      "nemlendirici yüz kremi"),
    "8684869609318": ("L'CARLIE Intimblanc Hassas Bölge Ton Görünümü Bakım Kremi 100 ml",
                      "hassas bölge bakım kremi"),
    "8684869609547": ("L'CARLIE Kinesis+ Sporcu Bakım Kremi Masaj 150 ml",
                      "sporcu bakım kremi"),
    "8684869609141": ("L'CARLIE Liftelle Göğüs ve Dekolte Bakım Kremi 50 ml",
                      "göğüs ve dekolte bakım kremi"),
    "8684869609134": ("L'CARLIE Lipvora Dudak Nemlendirici Balm 5 ml",
                      "dudak balmı"),
    "8684869609295": ("L'CARLIE Luciderm Yüz Temizleme Köpüğü Günlük Kullanım 150 ml",
                      "yüz temizleme köpüğü"),
    "8684869609585": ("L'CARLIE Menthalis Canlandırıcı Bitki Yağları Roll-On Naneli 10 ml",
                      "naneli roll-on"),
    "8684869609325": ("L'CARLIE Minisooth Bebek Bez Bölgesi Bakım Kremi 100 ml",
                      "bebek bez bölgesi kremi"),
    "8684869609172": ("L'CARLIE Optywave Göz Çevresi Bakım Roll-On Aydınlatıcı 10 ml",
                      "göz çevresi bakım roll-on"),
    "8684869609165": ("L'CARLIE Oragarde Ağız Bakım Spreyi Ferahlatıcı 50 ml",
                      "ağız bakım spreyi"),
    # Adi "Gece Bakim Kremi" ama kendi tanimi gun sonu BACAK bakimi.
    "8684869609202": ("L'CARLIE Seralimbo Gece Bacak Bakım Kremi 200 ml",
                      "bacak bakım kremi"),
    "8684869609608": ("L'CARLIE Softguard Tekstil Bakım Spreyi Yatak ve Döşemelik 100 ml",
                      "tekstil bakım spreyi"),
    # Kilavuz §4: "+30 SPF" degil "SPF 30".
    "8684869609097": ("L'CARLIE Sunacnea Güneş Kremi SPF 30 Yüz 50 ml",
                      "güneş kremi spf 30"),
    "8684869609110": ("L'CARLIE Vireon For Men Erkek Bakım Kremi 50 ml",
                      "erkek bakım kremi"),
}


def main() -> int:
    satirlar = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))
    alanlar = list(satirlar[0].keys())
    for yeni in ("seo_cekirdek",):
        if yeni not in alanlar:
            alanlar.insert(alanlar.index("idefix_baslik") + 1, yeni)

    aciklamalar = wix_aciklamalari()
    bulgular, uzun, eksik, ibare_eksigi = [], [], [], []
    for s in satirlar:
        b = s["barkod"]
        if b not in BASLIK:
            eksik.append(s["urun_adi_wix"])
            continue
        baslik, cekirdek = BASLIK[b]

        # 1) Basligin KENDISINDE iddia var mi (zorunlu-ibare sinifi haric)
        for f in compliance.review(baslik).findings:
            if IBARE_KURALI in f.rule:
                continue
            bulgular.append((s["urun_adi_wix"], baslik, f.rule, f.matched))
        if any(x[0] == s["urun_adi_wix"] for x in bulgular):
            continue  # bulgulu baslik YAZILMAZ

        # 2) Zorunlu ibareler: listeleme metninin tamaminda aranir
        listeleme = baslik + chr(10) + chr(10) + aciklamalar.get(b, "")
        for f in compliance.review(listeleme).findings:
            if IBARE_KURALI in f.rule:
                ibare_eksigi.append((s["urun_adi_wix"], f.matched))
        if len(baslik) > UZUNLUK_SINIR:
            uzun.append((s["urun_adi_wix"], len(baslik)))
            continue
        s["idefix_baslik"] = baslik
        s["seo_cekirdek"] = cekirdek

    if eksik:
        print("BASLIGI TANIMLANMAMIS:", eksik)
        return 1
    if bulgular:
        print("MEVZUAT BULGUSU OLAN BASLIKLAR -- yazilmadi:")
        for ad, baslik, kural, ifade in bulgular:
            print(f"  {ad}: {kural} -> '{ifade}'  ({baslik})")
        return 1
    if uzun:
        print(f"{UZUNLUK_SINIR} karakteri asan basliklar:", uzun)
        return 1
    if ibare_eksigi:
        print("ZORUNLU IBARE EKSIGI (baslik degil ACIKLAMA sorunu, "
              "basliklar yazildi):")
        for ad, ifade in ibare_eksigi:
            print(f"  {ad}: '{ifade}'")

    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        y = csv.DictWriter(f, fieldnames=alanlar, delimiter=";")
        y.writeheader()
        y.writerows(satirlar)

    satirlar.sort(key=lambda r: r["urun_adi_wix"])
    md = ["# Idefix ürün başlıkları — 36 ürün", "",
          "Kalıp: **marka · ürün adı · aranan jenerik tür · ayırt edici · hacim**.",
          "Hepsi `compliance.review`den geçti (bulgu çıkan başlık dosyaya yazılmaz)",
          f"ve {UZUNLUK_SINIR} karakter sınırının altında.", "",
          "| Ürün | Başlık | Krk | SEO çekirdeği |", "|---|---|---|---|"]
    for s in satirlar:
        md.append(f"| {s['urun_adi_wix'][:26]} | {s['idefix_baslik']} "
                  f"| {len(s['idefix_baslik'])} | {s['seo_cekirdek']} |")
    md += ["", "## Bilerek yazılmayanlar", "",
           "- **BABYSOL'de SPF değeri YOK**: formül çinko oksitli ama SPF hiçbir",
           "  kaynakta belirtilmemiş; uydurmak yerine 'Çinko Oksitli' yazıldı.",
           "- **SUNACNEA'da `SPF 30`** (kılavuz §4 `+30 SPF` yazımını yasaklıyor).",
           "- **DERMACORN'da 'nasır' yok** — hastalık/lezyon adı listesinde.",
           "- **MINISOOTH'ta 'pişik' yok** — kutu adıyla aynı: bez bölgesi bakımı.",
           "- **HAIR NOURISHER'da 'dökülme' yok** — yasak liste.",
           "- **SERALIMBO 'gece bacak bakım kremi'**: adı 'Gece Bakım Kremi' ama",
           "  kendi tanımı gün sonu bacak bakımı diyor; yüz ürünü değil.",
           "- Hiçbir başlıkta üstünlük iddiası, tedavi dili veya öne çıkarılamayan",
           "  bileşen (epimedium, tribulus, damiana, maca, arjinin) yok.", ""]
    if ibare_eksigi:
        md += ["## 🔴 Açıklamada eksik zorunlu ibare (başlık sorunu DEĞİL)", "",
               "Güneş ürünü mevzuatı bu ibareleri şart koşuyor; başlıkta değil",
               "açıklamada bulunmaları gerekir. Yükleme öncesi açıklamaya eklenmeli:", ""]
        for ad, ifade in ibare_eksigi:
            md.append(f"- **{ad}** → `{ifade}`")
        md.append("")
    RAPOR.write_text("\n".join(md), encoding="utf-8")

    uzunluklar = [len(s["idefix_baslik"]) for s in satirlar]
    print(f"yazilan baslik : {len(satirlar)}")
    print(f"karakter       : en kisa {min(uzunluklar)} · ortalama "
          f"{sum(uzunluklar)//len(uzunluklar)} · en uzun {max(uzunluklar)}")
    print(f"rapor          : {RAPOR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
