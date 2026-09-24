#!/usr/bin/env python3
"""OpenStreetMap -> raw.osm_poi. Ankara'daki ziyaret hedeflerini tarar.

NE YAPAR. Overpass API'den eczane / klinik / diş / hastane / spor salonu
noktalarını çeker ve kendi veri merkezimize yazar. Ayda bir çalışır; ilk
koşuda hepsini alır, sonrakilerde YENİ yerleri bulur.

🔴 SILME YOK. OSM'den kalkan bir kayıt silinmez, `kayip_at` yazılır. Silseydik
iki ayrı durum aynı görünürdü: "dükkân kapandı" ve "tarama o gün eksik döndü".
Üstelik o noktaya yapılmış ziyaret kaydı öksüz kalırdı. Karar insana bırakılır.

🔴 İNSAN BEYANINA DOKUNMAZ. Ziyarette öğrenilen telefon, düzeltilen ad ve branş
`core.saha_bilgi`'de durur; bu betik oraya hiç yazmaz. Aynı desen bu projede
gönderi sınıflandırmasında da kullanılıyor: beyan çıkarımı yener ama gizlemez.

BRANŞ TAHMİNİ. OSM'de branş alanı Ankara'da 2.449 kaydın yalnız 48'inde dolu
(%2). Ama Türkçe isimler söylüyor: "Alyadent Diş Polikliniği", "... Kadın
Doğum". İsimden çıkarılan branş `brans_tahmin` sütununa yazılır -- BEYAN
sütununa DEĞİL. İkisini karıştırmak, tahmini bilgi gibi göstermek olurdu.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

KAP = "lcarlie-postgres"
KULLANICI = "n8n"
VERITABANI = "n8n"
UA = "lcarlie-saha/1.0 (iletisim: moy.ozeryildiz@gmail.com)"

# OSM etiketi -> bizim turumuz
TUR = {
    ("amenity", "pharmacy"): "ECZANE",
    ("amenity", "clinic"): "KLINIK",
    ("amenity", "doctors"): "DOKTOR",
    ("amenity", "dentist"): "DIS",
    ("amenity", "hospital"): "HASTANE",
    ("leisure", "fitness_centre"): "SPOR",
    ("leisure", "sports_centre"): "SPOR",
}

# İsimden branş. Sıra önemli: önce daha özgül olan.
BRANS_KALIPLARI = [
    (r"\bdent|diş\s*(hek|pol|kli|mer)|ağız\s*ve?\s*diş", "DIS"),
    (r"kadın\s*(hast|doğ)|jinekolog|doğum", "KADIN_DOGUM"),
    (r"göz\s*(hast|pol|kli|mer)|oftalmolog", "GOZ"),
    (r"çocuk\s*(hast|pol|kli|dok)|pediatri", "COCUK"),
    (r"kulak\s*burun|\bkbb\b|otorinolaring", "KBB"),
    (r"deri|cilt\s*(hast|pol|kli)|dermatolog", "DERMATOLOJI"),
    (r"ortopedi|travmatolo", "ORTOPEDI"),
    (r"fizik\s*tedavi|fizyoterap|\bftr\b", "FIZIK_TEDAVI"),
    (r"psikiyatr|psikolog|ruh\s*sağlığ", "PSIKOLOJI"),
    (r"dahiliye|iç\s*hastalık", "DAHILIYE"),
    (r"kardiyolo|kalp", "KARDIYOLOJI"),
    (r"nöroloj|beyin\s*ve?\s*sinir", "NOROLOJI"),
    (r"üroloj", "UROLOJI"),
    (r"estetik|güzellik|medikal\s*estetik", "ESTETIK"),
    (r"diyaliz", "DIYALIZ"),
    (r"veteriner|hayvan\s*hast", "VETERINER"),
    (r"aile\s*sağlığ|aile\s*hekim|\basm\b", "AILE_SAGLIGI"),
    (r"tıp\s*merkez|poliklinik", "GENEL"),
]

SORGU = """[out:json][timeout:170];
area["name"="%s"]["admin_level"="4"]->.a;
(
  nwr["amenity"="pharmacy"](area.a);
  nwr["amenity"="clinic"](area.a);
  nwr["amenity"="doctors"](area.a);
  nwr["amenity"="dentist"](area.a);
  nwr["amenity"="hospital"](area.a);
  nwr["leisure"="fitness_centre"](area.a);
  nwr["leisure"="sports_centre"](area.a);
);
out center tags;"""


def brans_tahmin(ad: str | None, tur: str) -> str | None:
    """İsimden branş. Eczane ve spor salonunda branş kavramı yok."""
    if not ad or tur in ("ECZANE", "SPOR"):
        return None
    d = ad.casefold()
    for kalip, brans in BRANS_KALIPLARI:
        if re.search(kalip, d):
            return brans
    return None


def tur_bul(etiket: dict) -> str | None:
    for (anahtar, deger), ad in TUR.items():
        if etiket.get(anahtar) == deger:
            return ad
    return None


def konum(e: dict):
    if e.get("lat") is not None:
        return e["lat"], e["lon"]
    merkez = e.get("center") or {}
    return merkez.get("lat"), merkez.get("lon")


# Overpass'in genel sunuculari ucretsiz ve paylasimli: yogun anda 504/429
# donuyorlar. Olculdu 24.09.2026 -- ayni sorgu once 12 saniyede dondu, on
# dakika sonra 504 verdi. Ayda bir kosan bir is bunu kaldirabilmeli, yoksa
# "tarama yapilmadi" ile "yeni yer yok" ayni gorunur.
AYNALAR = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)


def cek(il: str) -> list[dict]:
    """Aynalari sirayla dener. Hepsi dusmeden VAZGECMEZ.

    Son hatayi yukseltir: sessizce bos liste donmek, "hic yer yok" demek
    olurdu ve bir sonraki adim butun kayitlari kayip isaretlerdi.
    """
    veri = urllib.parse.urlencode({"data": SORGU % il}).encode()
    son_hata = None
    for deneme, adres in enumerate(AYNALAR, 1):
        istek = urllib.request.Request(adres, data=veri,
                                       headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(istek, timeout=200) as cevap:
                ogeler = json.loads(cevap.read()).get("elements", [])
            if ogeler:
                if deneme > 1:
                    print("  (%d. ayna kullanildi: %s)" % (deneme, adres))
                return ogeler
            son_hata = RuntimeError("bos cevap")
        except Exception as exc:  # noqa: BLE001 - bir sonraki aynaya gec
            son_hata = exc
            print("  ayna %d basarisiz (%s), sonrakine geciliyor"
                  % (deneme, type(exc).__name__))
            time.sleep(4)
    raise RuntimeError("butun aynalar basarisiz, son hata: %r" % son_hata)


def psql(sql: str, girdi: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", KULLANICI, "-d", VERITABANI]
        + ([] if girdi else ["-tAc", sql]),
        input=girdi, capture_output=True, text=True, timeout=300)


def satir_say(sql: str) -> int:
    c = psql(sql)
    try:
        return int(c.stdout.strip())
    except Exception:  # noqa: BLE001 - okunamamak ayri bir durum
        return -1



def gorunumu_tazele() -> None:
    """Maddileştirilmiş hedef görünümlerini yeniden kurar.

    CONCURRENTLY: tazeleme sürerken panel okumaya devam eder. Tarama
    gece koşuyor olsa bile sahadaki kişi listeyi kaybetmemeli.
    """
    sql = ("REFRESH MATERIALIZED VIEW CONCURRENTLY mart.saha_tum;\n"
           "REFRESH MATERIALIZED VIEW CONCURRENTLY mart.saha_kaynak;\n")
    sonuc = psql("", girdi=sql)  # stdin: her deyim kendi isleminde (CONCURRENTLY sart)
    if sonuc.returncode != 0:
        # Sessizce gecilemez: tazelenmemis gorunum, taranmamis veriyle
        # AYNI gorunur ama "tarandi" diye raporlanir.
        print("UYARI: gorunum tazelenemedi -- panel ESKI veriyi gosterir")
        print((sonuc.stderr or "").strip()[:400])
    else:
        print("gorunum tazelendi (mart.saha_tum, mart.saha_kaynak)")

def main() -> int:
    il = sys.argv[1] if len(sys.argv) > 1 else "Ankara"
    t0 = time.time()
    try:
        ogeler = cek(il)
    except Exception as exc:  # noqa: BLE001
        print("TARAMA BASARISIZ: %s %s" % (type(exc).__name__, str(exc)[:200]))
        return 1

    satirlar = []
    atlanan = 0
    for e in ogeler:
        etiket = e.get("tags") or {}
        tur = tur_bul(etiket)
        enlem, boylam = konum(e)
        if not tur or enlem is None or boylam is None:
            # Konumsuz kayit ziyaret hedefi olamaz; sessizce yutulmaz, sayilir.
            atlanan += 1
            continue
        ad = etiket.get("name")
        satirlar.append([
            e.get("type"), e.get("id"), ad or "", tur, enlem, boylam,
            etiket.get("phone") or etiket.get("contact:phone") or "",
            etiket.get("email") or etiket.get("contact:email") or "",
            etiket.get("website") or etiket.get("contact:website") or "",
            " ".join(x for x in (etiket.get("addr:street"),
                                 etiket.get("addr:housenumber")) if x),
            etiket.get("addr:district") or etiket.get("addr:suburb") or "",
            brans_tahmin(ad, tur) or "",
            json.dumps(etiket, ensure_ascii=False, sort_keys=True),
        ])

    if not satirlar:
        print("hic kayit yok -- yazma yapilmadi")
        return 1

    import csv
    import io
    tampon = io.StringIO()
    yazici = csv.writer(tampon, lineterminator="\n")
    for s in satirlar:
        yazici.writerow(s)

    once = satir_say("select count(*) from raw.osm_poi")

    sql = """\\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE _gelen (
  osm_tur text, osm_id bigint, ad text, tur text,
  enlem double precision, boylam double precision,
  telefon text, eposta text, website text, adres text, ilce text,
  brans_tahmin text, etiket jsonb
) ON COMMIT DROP;
COPY _gelen FROM STDIN WITH (FORMAT csv);
""" + tampon.getvalue() + """\\.
INSERT INTO raw.osm_poi AS p
  (osm_tur, osm_id, ad, tur, enlem, boylam, telefon, eposta, website,
   adres, ilce, brans_tahmin, etiket, ilk_gorulme, son_gorulme)
SELECT osm_tur, osm_id, nullif(ad,''), tur, enlem, boylam,
       nullif(telefon,''), nullif(eposta,''), nullif(website,''),
       nullif(adres,''), nullif(ilce,''), nullif(brans_tahmin,''),
       etiket, now(), now()
FROM _gelen
ON CONFLICT (osm_tur, osm_id) DO UPDATE SET
  ad = EXCLUDED.ad, tur = EXCLUDED.tur,
  enlem = EXCLUDED.enlem, boylam = EXCLUDED.boylam,
  telefon = EXCLUDED.telefon, eposta = EXCLUDED.eposta,
  website = EXCLUDED.website, adres = EXCLUDED.adres, ilce = EXCLUDED.ilce,
  brans_tahmin = EXCLUDED.brans_tahmin, etiket = EXCLUDED.etiket,
  son_gorulme = now(),
  kayip_at = NULL;          -- geri geldiyse kayip degildir

-- Bu taramada gorulmeyenler: SILINMEZ, kayip isaretlenir.
UPDATE raw.osm_poi SET kayip_at = now()
 WHERE kayip_at IS NULL
   AND (osm_tur, osm_id) NOT IN (SELECT osm_tur, osm_id FROM _gelen);
COMMIT;
"""
    sonuc = psql("", girdi=sql)
    if sonuc.returncode != 0:
        print("YAZMA BASARISIZ (psql %d)" % sonuc.returncode)
        print((sonuc.stderr or "").strip()[:600])
        return 1

    sonra = satir_say("select count(*) from raw.osm_poi")
    kayip = satir_say("select count(*) from raw.osm_poi where kayip_at is not null")
    yeni = sonra - once if once >= 0 and sonra >= 0 else -1
    print("%s · %d oge · %d yazildi · konumsuz atlanan %d · %.1f sn"
          % (il, len(ogeler), len(satirlar), atlanan, time.time() - t0))
    print("tabloda %d -> %d (yeni %d) · kayip isaretli %d"
          % (once, sonra, yeni, kayip))
    gorunumu_tazele()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
