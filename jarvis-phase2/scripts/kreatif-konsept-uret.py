#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KONSEPT AŞAMASI — kreatif zincirin hiç yazılmamış halkası.

🔴 26.09.2026'da ÖLÇÜLDÜ: `core.kreatif_konsept` tablosunda SIFIR satır var
ve tabloya yazan HİÇBİR kod yok. Şema tam (amaç, kitle, ana fikir, görsel
metafor, kompozisyon, altı puanlama ekseni, sanat yönetimi, öz eleştiri),
kısıt tam, indeks tam -- üreteci yok. 93 tasarım şablonu tanımlı, iki
tasarım işi yapılmış. Yani kreatif departman "tanımlı" ama üretmiyor.

Sonucu görünür: `ig_gonderi_plani`'ndeki kısıt diyor ki bir görsel ancak
`konsept_id` varsa TASLAK OLMAKTAN ÇIKAR. Sıfır konsept olduğu için yedi
paketin yedisi de taslak. Reklama çıkacak görsel, tanım gereği buradan
geçmek zorunda.

Bu betik o halkayı kurar: amaç -> strateji -> EN AZ ÜÇ farklı konsept ->
puanlama -> öz eleştiri -> sanat yönetimi -> seçim.

🔴 KLİŞE KAPISI MODELDEN RİCA EDİLMEZ, MAKİNEYLE ÖLÇÜLÜR. Modele "klişe
kullanma" demek yeterli değil; kendi ürettiğini beğenir. Reddedilen
klişeler (kaide üstünde ürün, rastgele çiçek, bej fon, su sıçraması...)
metinde ARANIR ve eşleşen konsept, modelin verdiği puan ne olursa olsun
TERK edilir.

🔴 "HİÇBİRİ YETERLİ DEĞİL" GEÇERLİ BİR SONUÇTUR. Eşiğin altında kalan
konsept seçilmez; betik boş döner ve sebebini yazar. Her koşuda mutlaka
bir kazanan çıkaran kapı, kapı değildir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import turkish  # noqa: E402
from jarvis.model_layer import ModelRouter  # noqa: E402

KAP = "lcarlie-postgres"
EN_AZ_KONSEPT = 3
# Secilebilmek icin toplam esik (6 eksen x 1-5 = 6..30). 22, her eksende
# ortalama 3,7 demek: "idare eder" degil, "yayinlanabilir".
SECIM_ESIGI = 22
# Tek eksen bile 2'nin altindaysa secilmez: toplami yuksek ama marka
# uyumu 1 olan bir konsept, toplamiyla kurtarilamaz.
EKSEN_TABANI = 2

PUAN_EKSENLERI = [
    ("p_marka_uyumu", "marka uyumu"),
    ("p_ozgunluk", "özgünlük"),
    ("p_mesaj_netligi", "mesaj netliği"),
    ("p_durdurma_gucu", "durdurma gücü"),
    ("p_uretilebilirlik", "üretilebilirlik"),
    ("p_gorsel_olgunluk", "görsel olgunluk"),
]

# knowledge/41-gorsel-yonetimi.md "Reddedilen klişeler" bolumunden.
# Turkce alt dize tuzagi: "tas" yazarsak "plastik" eslesir, "cicek"
# yazarsak sorun yok ama "bej" -> "bejleme" gibi kelimelere kacabilir.
# Bu yuzden KELIME SINIRIYLA aranir (turkish.words).
# Anahtarlar GOVDE (lemma) olarak yazilir: "cicekler" -> cicek,
# "taslar" -> tas, "sicramasi" -> sicramak. Kelimeyi oldugu gibi
# arasaydik cekimli hallerin hicbiri eslesmezdi.
KLISE = {
    "kaide": "kaide üstünde ürün",
    "pedestal": "kaide üstünde ürün",
    "podyum": "kaide üstünde ürün",
    "çiçek": "rastgele çiçek",
    "yaprak": "dekoratif yaprak",
    "taş": "dekoratif taş",
    "çakıl": "dekoratif taş",
    "sıçramak": "su sıçraması",
    "sıçrama": "su sıçraması",
    "bej": "bej fon",
    "gradyan": "aşırı gradyan",
    "klipart": "3B klipart",
    "canva": "Canva şablonu görünümü",
}
# Cok kelimeli kaliplar ayri aranir (kelime sinirli birlesik arama).
KLISE_KALIP = [
    ("havada uçuşan", "havada uçuşan bileşen"),
    ("uçuşan bileşen", "havada uçuşan bileşen"),
    ("jenerik kadın", "jenerik kadın yüzü"),
    ("kadın yüzü", "jenerik kadın yüzü"),
    ("lüks nesne", "anlamsız lüks nesne"),
    ("tıbbi görsel", "sahte tıbbi görsel"),
]

SISTEM = """Sen L'CARLIÉ'nin kreatif ve sanat yönetmenisin.
L'CARLIÉ: lüks dermokozmetik, botanik bilim. Premium, editoryal, bilimsel,
ölçülü, inandırıcı.

SEN BİR İSTEM ÜRETİCİSİ DEĞİLSİN. Önce fikir, sonra üretim.

REDDEDİLEN KLİŞELER (konsept özellikle gerektirmedikçe kullanma):
kaide üstünde ürün, rastgele çiçek, su sıçraması, havada uçuşan bileşen,
jenerik kadın yüzü, bej fon, anlamsız lüks nesne, ucuz e-ticaret
estetiği, Canva şablonu görünümü, jenerik AI görüntüsü, aşırı gradyan,
3B klipart, sahte tıbbi görsel, görsel kalabalık.

NESNE KURALI: dekorasyon için obje ekleme. Objeyi çıkarınca konsept
değişmiyorsa o obje gereksizdir.

ÜRÜN KURALI: ambalaj yeniden çizilmez. Görsel ORTAMI tarif eder, ürünü
değil; gerçek ürün fotoğrafı sonradan yerleştirilir.

TİPOGRAFİ: görsele yazı yazdırılmaz. Kompozisyonda yazı için BOŞ ALAN
bırakılır; yazı sonradan dizilir.

YALNIZ JSON döndür, başka hiçbir şey yazma."""


def calistir(sql: str, degiskenler: dict | None = None) -> list:
    komut = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n"]
    for ad, deger in (degiskenler or {}).items():
        komut += ["-v", "%s=%s" % (ad, "" if deger is None else str(deger))]
    komut += ["-f", "-"]
    p = subprocess.run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
                       capture_output=True, text=True, timeout=120, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:500])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def _govdeler(metin: str) -> set:
    """Metindeki kelimelerin gövdeleri + kelimelerin kendisi.

    🔴 ALT DİZE ARAMASI KULLANILMAZ. "taş" alt dize olarak "tasarım"
    içinde geçmez ama önek eşleşmesi kullansaydık geçerdi ve her sanat
    yönetimi metni "dekoratif taş" diye reddedilirdi. Morfoloji bunu
    ayırıyor: tasarım -> tasar/tasarı/tasarım, taş DEĞİL.

    Model diyakritiksiz yazarsa ("cicek") deasciifier devreye girer.
    """
    bulunan = set()
    for kelime in turkish.words(metin):
        k = kelime.lower()
        bulunan.add(k)
        bulunan |= {g.lower() for g in turkish.lemmas(k)}
        duzeltilmis = turkish.deasciify(k)
        if duzeltilmis and duzeltilmis != k:
            bulunan.add(duzeltilmis)
            bulunan |= {g.lower() for g in turkish.lemmas(duzeltilmis)}
    return bulunan


def klise_bul(*metinler) -> list:
    """Reddedilen klişeleri GÖVDE eşleşmesiyle arar."""
    metin = " ".join(str(m or "") for m in metinler)
    govdeler = _govdeler(metin)
    bulunan = [etiket for anahtar, etiket in KLISE.items()
               if anahtar in govdeler]
    duz = metin.lower()
    for kalip, etiket in KLISE_KALIP:
        if re.search(r"\b" + re.escape(kalip) + r"\b", duz):
            bulunan.append(etiket)
    return sorted(set(bulunan))


def json_cikar(metin: str):
    """Model çıktısından JSON. Bulamazsa HATA verir, tahmin etmez."""
    m = re.search(r"[\[{].*[\]}]", metin or "", re.S)
    if not m:
        raise ValueError("model JSON dondurmedi")
    return json.loads(m.group(0))


def paket_oku(plan_id: int) -> dict:
    satir = calistir(
        "SELECT row_to_json(t) FROM (SELECT plan_id, urun_slug, amac, bicim,"
        " kanca, caption, dayanak, cta, gorsel_dosya"
        " FROM core.ig_gonderi_plani WHERE plan_id = %d) t;" % plan_id)
    if not satir:
        raise SystemExit("plan bulunamadi: %d" % plan_id)
    return satir[0]


def urun_oku(slug: str) -> dict:
    yol = Path(os.environ.get("JARVIS_STATE_DIR",
                              str(KOK / "state"))) / "katalog.json"
    if not yol.exists():
        return {}
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    for u in veri.get("urunler") or []:
        if u.get("slug") == slug:
            return u
    return {}


def konsept_uret(yonlendirici, paket: dict, urun: dict, adet: int,
                 guclu: bool) -> list:
    istek = json.dumps({
        "gorev": "En az %d GERÇEKTEN FARKLI kreatif konsept üret" % adet,
        "urun": urun.get("ad") or paket["urun_slug"],
        "urun_ozeti": (urun.get("ozet") or "")[:400],
        "amac": paket["amac"],
        "bicim": paket["bicim"],
        "kanca": paket["kanca"],
        "neden_bu_urun": (paket.get("dayanak") or "")[:300],
        "istenen_alanlar": {
            "ad": "konseptin kısa adı",
            "ana_fikir": "tek cümlede fikir",
            "gorsel_metafor": "neyin neye benzetildiği",
            "kompozisyon": "kadraj ve yerleşim",
            "odak": "gözün ilk gittiği yer",
            "duygu": "izleyicide bırakılan his",
            "urunle_iliski": "ürün kompozisyonda nerede ve neden",
            "neden_durdurur": "kaydırmayı ne durdurur",
            "amac_iletisim": "iletişim amacı",
            "hedef_kitle": "kim",
            "istenen_tepki": "izleyici ne yapsın",
            "ana_mesaj": "tek cümle",
            "ikincil_mesaj": "tek cümle",
            "puan": {e: "1-5 arası tam sayı" for e, _ in PUAN_EKSENLERI},
            "sanat_yonetimi": {
                "kamera": "", "isik": "", "malzeme": "", "ortam": "",
                "derinlik": "", "negatif_alan": "yazı için bırakılan alan",
                "yerlesim": "", "tipografi_alani": "", "renk": ""},
            "istem": "İngilizce, ORTAMI tarif eder, ürünü değil",
            "negatif_istem": "İngilizce",
        },
        "cikti": "JSON dizi (list), her eleman bir konsept",
        # Model ilk kosuda ucunde de istenen_tepki alanini atladi ve uc
        # konsept birden reddedildi. Ic ice sozluk yeterince baglayici
        # degilmis: zorunlu alanlar DUZ LISTE olarak da yaziliyor.
        "zorunlu_alanlar": [
            "ad", "ana_fikir", "gorsel_metafor", "kompozisyon", "odak",
            "duygu", "urunle_iliski", "neden_durdurur", "amac_iletisim",
            "hedef_kitle", "istenen_tepki", "ana_mesaj", "puan",
            "sanat_yonetimi", "istem", "negatif_istem"],
        "kural": "Bir alan eksikse o konsept TAMAMEN REDDEDILIR. "
                 "Hicbir alani bos birakma, kisa da olsa doldur.",
    }, ensure_ascii=False)

    sonuc, kademe, _ = yonlendirici.generate(
        [{"role": "system", "content": SISTEM},
         {"role": "user", "content": istek}],
        4000, escalate=guclu, is_anahtari="kreatif_konsept")
    print("  konsept üretimi kademe: %s" % kademe)
    ham = (sonuc or {}).get("text") or (sonuc or {}).get("content") or ""
    veri = json_cikar(ham)
    if isinstance(veri, dict):
        veri = veri.get("konseptler") or veri.get("concepts") or [veri]
    if not isinstance(veri, list):
        raise ValueError("model dizi dondurmedi")
    return veri


def dogrula(k: dict) -> tuple:
    """Eksik alanlı konsept YAZILMAZ. Yarım konsept, konsept değildir."""
    zorunlu = ("ad", "ana_fikir", "gorsel_metafor", "kompozisyon", "odak",
               "duygu", "urunle_iliski", "neden_durdurur", "amac_iletisim",
               "hedef_kitle", "istenen_tepki", "ana_mesaj")
    eksik = [a for a in zorunlu if not str(k.get(a) or "").strip()]
    puan = k.get("puan") or {}
    for eksen, _ad in PUAN_EKSENLERI:
        try:
            d = int(puan.get(eksen))
        except (TypeError, ValueError):
            eksik.append("puan." + eksen)
            continue
        if not 1 <= d <= 5:
            eksik.append("puan." + eksen + " (1-5 disinda)")
    return (not eksik), eksik


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_id", type=int)
    ap.add_argument("--adet", type=int, default=EN_AZ_KONSEPT)
    ap.add_argument("--guclu", action="store_true",
                    help="dis modele cik (ucret dogurur)")
    ap.add_argument("--yaz", action="store_true",
                    help="veritabanina yaz (varsayilan: yalniz goster)")
    a = ap.parse_args()
    if a.adet < EN_AZ_KONSEPT:
        raise SystemExit("en az %d konsept: tek fikir secim degildir"
                         % EN_AZ_KONSEPT)

    paket = paket_oku(a.plan_id)
    urun = urun_oku(paket["urun_slug"])
    print("paket %d · %s · %s · %s"
          % (a.plan_id, paket["urun_slug"], paket["amac"], paket["bicim"]))

    varolan = calistir("SELECT row_to_json(t) FROM (SELECT count(*) AS n"
                       " FROM core.kreatif_konsept WHERE plan_id = %d) t;"
                       % a.plan_id)[0]["n"]
    if varolan and a.yaz:
        raise SystemExit("bu planda zaten %s konsept var -- once bakilsin"
                         % varolan)

    yonlendirici = ModelRouter()
    konseptler = konsept_uret(yonlendirici, paket, urun, a.adet, a.guclu)
    print("  model %d konsept dondu" % len(konseptler))

    degerlendirilen = []
    for k in konseptler:
        tam, eksik = dogrula(k)
        if not tam:
            print("  ATLANDI (eksik alan): %s -> %s"
                  % (str(k.get("ad"))[:30], ", ".join(eksik[:4])))
            continue
        ay = k.get("sanat_yonetimi") or {}
        kliseler = klise_bul(k.get("gorsel_metafor"), k.get("kompozisyon"),
                             k.get("ana_fikir"), ay.get("ortam"),
                             ay.get("malzeme"), k.get("istem"))
        puan = {e: int((k.get("puan") or {}).get(e)) for e, _ in PUAN_EKSENLERI}
        toplam = sum(puan.values())
        en_dusuk = min(puan.values())

        if kliseler:
            sonuc = "TERK"
            gerekce = "reddedilen klişe: " + ", ".join(kliseler)
        elif en_dusuk < EKSEN_TABANI:
            sonuc = "YENIDEN"
            gerekce = "bir eksen %d (taban %d)" % (en_dusuk, EKSEN_TABANI)
        elif toplam < SECIM_ESIGI:
            sonuc = "YENIDEN"
            gerekce = "toplam %d (eşik %d)" % (toplam, SECIM_ESIGI)
        else:
            sonuc = "KABUL"
            gerekce = "toplam %d" % toplam

        k["_toplam"] = toplam
        k["_puan"] = puan
        k["_sonuc"] = sonuc
        k["_gerekce"] = gerekce
        k["_klise"] = kliseler
        degerlendirilen.append(k)
        print("  %-28s %2d/30  %-8s %s"
              % (str(k.get("ad"))[:28], toplam, sonuc, gerekce))

    if len(degerlendirilen) < EN_AZ_KONSEPT:
        print("\n🔴 DURDU: yalniz %d gecerli konsept var, en az %d gerekiyor."
              % (len(degerlendirilen), EN_AZ_KONSEPT))
        print("   Tek fikirden secim yapilmaz; secim icin alternatif gerekir.")
        return 2

    kabuller = [k for k in degerlendirilen if k["_sonuc"] == "KABUL"]
    if not kabuller:
        print("\n🔴 HICBIRI YETERLI DEGIL. Secim yapilmadi.")
        print("   Bu gecerli bir sonuctur: her kosuda kazanan cikaran kapi,")
        print("   kapi degildir. Yeniden uret ya da brief'i degistir.")
        return 3

    kazanan = max(kabuller, key=lambda k: k["_toplam"])
    print("\nSECILEN: %s (%d/30)" % (kazanan.get("ad"), kazanan["_toplam"]))

    if not a.yaz:
        print("\n(yalniz gosterildi -- yazmak icin --yaz)")
        return 0

    for k in degerlendirilen:
        ay = k.get("sanat_yonetimi") or {}
        secildi = k is kazanan
        # Secilen konseptin sanat yonetimi EKSIKSIZ olmali: kisit da
        # bunu zorluyor, ama hatayi psql'den degil buradan verelim.
        if secildi:
            bos = [ad for ad, d in (("kamera", ay.get("kamera")),
                                    ("isik", ay.get("isik")),
                                    ("negatif_alan", ay.get("negatif_alan")),
                                    ("tipografi_alani", ay.get("tipografi_alani")))
                   if not str(d or "").strip()]
            if bos:
                print("🔴 SECILEN KONSEPTIN SANAT YONETIMI EKSIK: %s"
                      % ", ".join(bos))
                print("   Yazilmadi. Sanat yonetimi olmayan konsept")
                print("   uretilemez; secmek de onu uretilebilir yapmaz.")
                return 4
        calistir("""
          INSERT INTO core.kreatif_konsept
            (plan_id, amac_iletisim, hedef_kitle, istenen_tepki, ana_mesaj,
             ikincil_mesaj, ad, ana_fikir, gorsel_metafor, kompozisyon,
             odak, duygu, urunle_iliski, neden_durdurur,
             p_marka_uyumu, p_ozgunluk, p_mesaj_netligi, p_durdurma_gucu,
             p_uretilebilirlik, p_gorsel_olgunluk,
             secildi, secim_gerekce,
             ay_kamera, ay_isik, ay_malzeme, ay_ortam, ay_derinlik,
             ay_negatif_alan, ay_yerlesim, ay_tipografi_alani, ay_renk,
             istem, negatif_istem, ozelestiri, ozelestiri_sonuc)
          VALUES (%d, :'amac', :'kitle', :'tepki', :'mesaj',
                  NULLIF(:'mesaj2',''), :'ad', :'fikir', :'metafor', :'komp',
                  :'odak', :'duygu', :'iliski', :'durdurur',
                  %d, %d, %d, %d, %d, %d,
                  %s, NULLIF(:'secgerekce',''),
                  NULLIF(:'kamera',''), NULLIF(:'isik',''),
                  NULLIF(:'malzeme',''), NULLIF(:'ortam',''),
                  NULLIF(:'derinlik',''), NULLIF(:'negalan',''),
                  NULLIF(:'yerlesim',''), NULLIF(:'tipalan',''),
                  NULLIF(:'renk',''),
                  NULLIF(:'istem',''), NULLIF(:'negistem',''),
                  :'ozel'::jsonb, :'ozelsonuc');""" % (
            a.plan_id,
            k["_puan"]["p_marka_uyumu"], k["_puan"]["p_ozgunluk"],
            k["_puan"]["p_mesaj_netligi"], k["_puan"]["p_durdurma_gucu"],
            k["_puan"]["p_uretilebilirlik"], k["_puan"]["p_gorsel_olgunluk"],
            "true" if secildi else "false"),
            {"amac": k["amac_iletisim"], "kitle": k["hedef_kitle"],
             "tepki": k["istenen_tepki"], "mesaj": k["ana_mesaj"],
             "mesaj2": k.get("ikincil_mesaj") or "",
             "ad": k["ad"], "fikir": k["ana_fikir"],
             "metafor": k["gorsel_metafor"], "komp": k["kompozisyon"],
             "odak": k["odak"], "duygu": k["duygu"],
             "iliski": k["urunle_iliski"], "durdurur": k["neden_durdurur"],
             "secgerekce": k["_gerekce"] if secildi else "",
             "kamera": ay.get("kamera") or "", "isik": ay.get("isik") or "",
             "malzeme": ay.get("malzeme") or "", "ortam": ay.get("ortam") or "",
             "derinlik": ay.get("derinlik") or "",
             "negalan": ay.get("negatif_alan") or "",
             "yerlesim": ay.get("yerlesim") or "",
             "tipalan": ay.get("tipografi_alani") or "",
             "renk": ay.get("renk") or "",
             "istem": k.get("istem") or "",
             "negistem": k.get("negatif_istem") or "",
             "ozel": json.dumps({"klise": k["_klise"], "puan": k["_puan"],
                                 "toplam": k["_toplam"],
                                 "gerekce": k["_gerekce"]},
                                ensure_ascii=False),
             "ozelsonuc": k["_sonuc"]})

    kid = calistir("SELECT row_to_json(t) FROM (SELECT konsept_id FROM"
                   " core.kreatif_konsept WHERE plan_id = %d AND secildi) t;"
                   % a.plan_id)[0]["konsept_id"]
    print("yazildi. secilen konsept_id = %s" % kid)
    print("\nBu konsept baglanana kadar gorsel TASLAK kalir:")
    print("  UPDATE core.ig_gonderi_plani SET konsept_id = %s,"
          " gorsel_taslak_mi = false WHERE plan_id = %d;" % (kid, a.plan_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
