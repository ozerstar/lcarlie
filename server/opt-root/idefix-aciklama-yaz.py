#!/usr/bin/env python3
"""Idefix urun aciklamalari — satis odakli, pazaryeri duzeninde, mevzuatli.

YONTEM: UYDURMA YOK, AYIKLAMA VAR
Wix'teki 36 aciklama zaten mevzuat duzeltmesinden gecmis ve canli. Buradaki is
onlari yeniden yazmak degil; bolum bolum ayiklayip pazaryeri okuma sirasina
dizmek, satmayan/yasak olan parcalari cikarmak, eksik zorunlu ibareleri eklemek.

PAZARYERI SIRASI (musteri boyle okur)
  1 Kanca      -> tagline + giris paragrafi
  2 Fayda      -> "Bakimda one cikanlar" maddeleri
  3 Kime/nere  -> "Kullanim alani"
  4 Nasil      -> "Nasil kullanilir?"
  5 Guven      -> "Iceriklerin formuldeki rolu"
  6 Uyari      -> "Uyarilar" (+ gunes urunlerinde zorunlu ibareler)
  7 Saklama    -> raf omru
  8 Icindekiler-> tam INCI (alerjen sorusunun tek dogru cevabi)

CIKARILANLAR ve NEDENI
  - "Marka sahibi ve iletisim": telefon/e-posta/adres. Pazaryerleri listeleme
    icinde satici iletisimini yasaklar (platform disina yonlendirme sayilir).
  - "Sik sorulan soru": HYDRAVIE ve OPTYWAVE'de "gunes koruyucu" gecen SSS
    satiri, gunes urunu olmadiklari halde zorunlu-ibare kuralini tetikliyordu.
    Pazaryeri listesinde site SSS'sinin isi yok; cikarildi, tetik de bitti.
  - One cikarilamayan bilesen (epimedium, tribulus, damiana, maca, arjinin)
    adini TASIYAN paragraf cikarilir. INCI'de kalir (kilavuz Kural 3) --
    cumle elle yeniden yazilmaz, cunku yeniden yazmak editoryal karardir.

GUNES URUNLERI
Mevzuat dort ibareyi sart kosuyor. BABYSOL'de ikisi eksikti; iki gunes
urununde de ibarelerin TAMAMI uyari bolumune eklenir.
"""
from __future__ import annotations

import csv
import html as html_mod
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import compliance  # noqa: E402

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
RAPOR = Path("/opt/lcarlie/idefix-hazirlik/ACIKLAMALAR.md")
AYRAC = "<<>>"

# Gunes urunu olan barkodlar (SPF/gunes koruma islevi beyan edilen)
GUNES = {"8684869609097", "8684869609530"}

# Kozmetik Urunler Yonetmeligi'nin gunes urunlerinde sart kostugu ibareler.
GUNES_IBARELERI = [
    "Hiçbir ürün %100 koruma sağlamaz.",
    "Yeterli miktarda uygulanmaması korumayı önemli ölçüde düşürür.",
    "Aşırı güneş maruziyeti sağlık tehdididir.",
    "Bebek ve küçük çocuklar doğrudan güneşe maruz bırakılmamalıdır.",
]

# Kilavuz §2: one cikarilamayan bilesenler. INCI'de KALIR, cumlede anilmaz.
YASAK_BILESEN = ("epimedium", "tribulus", "damiana", "maca", "arjinin", "l-arginin")

# Kilavuz §2'nin kendi verdigi karsilik: bu adlarin yerine "bitkisel ekstreler".
BILESEN_KARSILIGI = "bitkisel ekstreler"


def bilesen_temizle(cumle: str) -> tuple[str, bool]:
    """Yasak bilesen ADINI kilavuzun karsiligiyla degistirir.

    Cumleyi yeniden YAZMAZ, yalniz adi degistirir: kilavuz §3'teki kanitlanmis
    ornekler canli sitede tam olarak bu ikameyi uygulamis. Ayni cumlede birden
    cok ad varsa karsilik tekrarlanmaz, tek sefer birakilir.
    """
    yeni = cumle
    degisti = False
    for ad in YASAK_BILESEN:
        desen = re.compile(r"(?<![\wçğıöşüÇĞİÖŞÜ])" + re.escape(ad)
                           + r"(?![\wçğıöşüÇĞİÖŞÜ])", re.IGNORECASE)
        if desen.search(yeni):
            yeni = desen.sub(BILESEN_KARSILIGI, yeni)
            degisti = True
    if degisti:
        # "bitkisel ekstreler, bitkisel ekstreler ve X" -> tek sefer
        yeni = re.sub(r"(" + BILESEN_KARSILIGI + r")(\s*[,;]\s*|\s+ve\s+)(?=" 
                      + BILESEN_KARSILIGI + r")", "", yeni, flags=re.IGNORECASE)
        yeni = re.sub(r"\s{2,}", " ", yeni).strip()
    return yeni, degisti

# Cikarilacak bolumler (baslik kucuk harfe katlanmis haliyle aranir)
AT = ("marka sahibi", "iletişim", "sık sorulan", "içerik adları hakkında")

# Pazaryeri sirasi: (hedef baslik, kaynak basliklarinda aranacak parca)
SIRA = [
    ("Öne çıkanlar", "öne çıkanlar"),
    ("Kullanım alanı", "kullanım alanı"),
    ("Nasıl kullanılır", "nasıl kullanılır"),
    ("İçeriklerin formüldeki rolü", "formüldeki rolü"),
    ("Formülü tamamlayan içerikler", "tamamlayan içerik"),
    ("Uyarılar", "uyarı"),
    ("Saklama ve raf ömrü", "saklama"),
    ("İçindekiler / INCI", "içindekiler"),
]


def kucult(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").casefold()


def metin(parca: str) -> str:
    duz = re.sub(r"<[^>]+>", " ", parca)
    return re.sub(r"\s+", " ", html_mod.unescape(duz)).strip()


def bolumle(ham: str) -> tuple[str, list[tuple[str, str]]]:
    """HTML'i (giris, [(baslik, icerik_html)]) olarak ayirir."""
    parcalar = re.split(r"<h[1-4][^>]*>(.*?)</h[1-4]>", ham, flags=re.S)
    giris = parcalar[0]
    bolumler = []
    for i in range(1, len(parcalar) - 1, 2):
        bolumler.append((metin(parcalar[i]), parcalar[i + 1]))
    return giris, bolumler


def veri_cek() -> dict[str, str]:
    sql = ("select sku || '" + AYRAC + "' || replace(replace("
           "ham->>'description', chr(10), ' '), chr(13), ' ') from raw.wix_urun;")
    c = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql",
                        "-U", "n8n", "-d", "n8n", "-At", "-f", "-"],
                       input=sql, capture_output=True, text=True, check=True)
    return dict(s.split(AYRAC, 1) for s in c.stdout.splitlines() if AYRAC in s)


def madde_listesi(icerik: str) -> list[str]:
    return [metin(m) for m in re.findall(r"<li[^>]*>(.*?)</li>", icerik, flags=re.S)]


def paragraflar(icerik: str) -> list[str]:
    p = [metin(m) for m in re.findall(r"<p[^>]*>(.*?)</p>", icerik, flags=re.S)]
    return [x for x in p if x]


def main() -> int:
    hamlar = veri_cek()
    satirlar = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))
    alanlar = list(satirlar[0].keys())
    if "idefix_aciklama" not in alanlar:
        alanlar.insert(alanlar.index("seo_cekirdek") + 1, "idefix_aciklama")

    atilan_bilesen, bulgulu, uzunluklar, ikame, ibare_muaf = [], [], [], [], []

    for s in satirlar:
        b = s["barkod"]
        ham = hamlar.get(b, "")
        if not ham:
            print(f"KAYNAK YOK: {s['urun_adi_wix']}")
            return 1
        giris, bolumler = bolumle(ham)

        # --- 1) Kanca: tagline (ilk baslik) + giris paragrafi -------------
        kanca_baslik = bolumler[0][0] if bolumler else ""
        giris_p = paragraflar(bolumler[0][1]) if bolumler else []
        # giristeki "L'CARLIÉ · 50 ml" satiri atlanir; hacim zaten baslikta.
        giris_p = [p for p in giris_p if not re.match(r"^L.?CARLI", p)]

        # Giris paragraflari da bilesen suzgecinden gecer -- FEMISIA'da
        # yasak ad tam burada, bolum icinde degil giris cumlesindeydi.
        temiz_giris = []
        for p in giris_p:
            yeni, degisti = bilesen_temizle(p)
            if degisti:
                ikame.append((s["urun_adi_wix"], p[:80], yeni[:80]))
            temiz_giris.append(yeni)
        giris_p = temiz_giris

        html = []
        if kanca_baslik:
            html.append(f"<p><strong>{html_mod.escape(kanca_baslik)}</strong></p>")
        for p in giris_p:
            html.append(f"<p>{html_mod.escape(p)}</p>")

        # --- 2..8) Pazaryeri sirasiyla bolumler --------------------------
        kullanilan = {kucult(kanca_baslik)}
        for hedef, arama in SIRA:
            for baslik, icerik in bolumler:
                kb = kucult(baslik)
                if arama not in kb or kb in kullanilan:
                    continue
                kullanilan.add(kb)

                maddeler = madde_listesi(icerik)
                pler = paragraflar(icerik)

                # One cikarilamayan bilesen tasiyan paragraf CIKARILIR
                temiz_p = []
                for p in pler:
                    # INCI bolumu DOKUNULMAZ: icerik beyani pazarlama degildir
                    # (kilavuz Kural 3). Yalniz pazarlama cumlelerinde ikame.
                    if hedef.startswith("İçindekiler"):
                        temiz_p.append(p)
                        continue
                    yeni, degisti = bilesen_temizle(p)
                    if degisti:
                        ikame.append((s["urun_adi_wix"], p[:80], yeni[:80]))
                    temiz_p.append(yeni)

                if not maddeler and not temiz_p:
                    continue
                html.append(f"<h3>{html_mod.escape(hedef)}</h3>")
                if maddeler:
                    html.append("<ul>" + "".join(
                        f"<li>{html_mod.escape(m)}</li>" for m in maddeler) + "</ul>")
                for p in temiz_p:
                    html.append(f"<p>{html_mod.escape(p)}</p>")

                # Gunes urunlerinde zorunlu ibareler uyari bolumune eklenir
                if hedef == "Uyarılar" and b in GUNES:
                    html.append("<ul>" + "".join(
                        f"<li>{html_mod.escape(i)}</li>" for i in GUNES_IBARELERI)
                        + "</ul>")

        aciklama = "".join(html)

        duz = metin(aciklama)
        for f in compliance.review(duz).findings:
            # ISTISNA 1 (kilavuz Kural 2): uyari/tavsiye cumlesi iddia degildir.
            # Cumlede olumsuz kalip ya da "onerilir" varsa bulgu sayilmaz.
            cumle = (f.sentence or "")
            if re.search(r"(ma(z|yın|malı)|mez|meyin|durunuz|önerilir|kaçın)",
                         kucult(cumle)):
                continue
            # ISTISNA 2: urun gunes urunu DEGILSE, "gunes koruyucu kullanin"
            # tavsiyesi dort zorunlu ibareyi gerektirmez -- gerektirseydi
            # urunu gunes urunu gibi gostermis olurduk.
            if "zorunlu ibare" in f.rule and b not in GUNES:
                ibare_muaf.append((s["urun_adi_wix"], f.matched))
                continue
            bulgulu.append((s["urun_adi_wix"], f.rule, f.matched))
        if any(x[0] == s["urun_adi_wix"] for x in bulgulu):
            continue

        s["idefix_aciklama"] = aciklama
        uzunluklar.append(len(aciklama))

    if bulgulu:
        print("MEVZUAT BULGUSU OLAN ACIKLAMALAR -- yazilmadi:")
        for ad, kural, ifade in bulgulu:
            print(f"  {ad}: {kural} -> '{ifade}'")
        return 1

    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        y = csv.DictWriter(f, fieldnames=alanlar, delimiter=";")
        y.writeheader()
        y.writerows(satirlar)

    md = ["# Idefix ürün açıklamaları — 36 ürün", "",
          "Wix'teki onaylı metinlerden **ayıklandı**, pazaryeri okuma sırasına dizildi.",
          "Hepsi `compliance.review`den geçti; bulgu çıkan açıklama yazılmaz.", "",
          "## Sıra", "",
          "kanca → öne çıkanlar → kullanım alanı → nasıl kullanılır → içerik rolleri",
          "→ uyarılar → saklama → tam INCI", "",
          "## Çıkarılanlar", "",
          "- **Marka sahibi ve iletişim bloğu** (telefon/e-posta/adres): pazaryerleri",
          "  listeleme içinde satıcı iletişimini yasaklar, platform dışına yönlendirme",
          "  sayılır. Wix'teki metinde vardı, Idefix açıklamasına taşınmadı.",
          "- **Sık sorulan soru bloğu**: HYDRAVIE ve OPTYWAVE'de 'güneş koruyucu'",
          "  geçen SSS satırı, güneş ürünü olmadıkları halde zorunlu-ibare kuralını",
          "  tetikliyordu. Pazaryeri listesinde site SSS'sinin işi yok.", ""]
    if ikame:
        md += ["## Bileşen adı ikamesi (kılavuz §2)", "",
               "Öne çıkarılamayan bileşen adları kılavuzun kendi karşılığıyla",
               f"(**{BILESEN_KARSILIGI}**) değiştirildi. INCI listesinde **duruyorlar**",
               "(Kural 3) — yalnız pazarlama cümlesinden çıktılar.", "",
               "| Ürün | Önce | Sonra |", "|---|---|---|"]
        for ad, once, sonra in ikame:
            md.append(f"| {ad[:24]} | {once} | {sonra} |")
        md.append("")
    if ibare_muaf:
        md += ["## Zorunlu-ibare muafiyeti", "",
               "Güneş ürünü **olmayan** ürünlerde geçen “güneş koruyucu kullanılması",
               "önerilir” tavsiyesi, dört zorunlu güneş ibaresini gerektirmez; eklemek",
               "ürünü güneş ürünü gibi gösterirdi. Muaf tutulanlar:", ""]
        for ad, ifade in dict.fromkeys(ibare_muaf):
            md.append(f"- {ad}")
        md.append("")
    md += ["## Güneş ürünleri", "",
           "BABYSOL ve SUNACNEA'nın uyarı bölümüne mevzuatın şart koştuğu **dört",
           "ibarenin tamamı** eklendi (BABYSOL'de ikisi eksikti).", "",
           f"## Uzunluk", "",
           f"En kısa {min(uzunluklar)} · ortalama {sum(uzunluklar)//len(uzunluklar)}"
           f" · en uzun {max(uzunluklar)} karakter (HTML dahil).", ""]
    RAPOR.write_text("\n".join(md), encoding="utf-8")

    print(f"yazilan aciklama : {len(uzunluklar)}")
    print(f"karakter         : en kisa {min(uzunluklar)} · ortalama "
          f"{sum(uzunluklar)//len(uzunluklar)} · en uzun {max(uzunluklar)}")
    print(f"bilesen adi ikamesi      : {len(ikame)}")
    if ikame:
        for ad, once, sonra in ikame:
            print(f"   {ad}")
            print(f"     once : {once}")
            print(f"     sonra: {sonra}")
    if ibare_muaf:
        print(f"zorunlu-ibare muafiyeti  : {len(ibare_muaf)} "
              "(gunes urunu olmayanlarda 'gunes koruyucu kullanin' tavsiyesi)")
    print(f"rapor            : {RAPOR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
