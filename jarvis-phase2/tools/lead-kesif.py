"""Ankara B2B lead kesfi: OpenStreetMap -> raw.lead_osm -> core.lead.

NEDEN OSM BIRINCIL
ODbL lisansli: ucretsiz, sinirsiz, KALICI SAKLANABILIR. Places API verisi
saklanamaz (Google sartlari) ve 5.000/ay ucretsiz kotayla sinirlidir.

OLCULEN KAPSAMA (24.09.2026, Ankara)
  eczane            1799 kayit, 1374 telefonlu (%76)  <- OSM YETERLI
  klinik             207 kayit,   16 telefonlu (%8)
  spor salonu        185 kayit,   15 telefonlu (%8)
  guzellik merkezi   111 kayit,   14 telefonlu (%13)
  muayenehane         20 kayit,    4 telefonlu (%20)
  spa / masaj          7 kayit,    1 telefonlu (%14)
  tip merkezi          0 kayit
Eczane disinda OSM yetersiz; o segmentler Places ile doldurulacak. Bu betik
OSM tarafini yapar ve eksigi RAPOR EDER -- kapatmis gibi yapmaz.

ROBOTS / SARTLAR
Overpass halka acik ucu hiz sinirli. Uc ayna, ustel bekleme, uc deneme.
Basarisiz segment "0" DEGIL "SORAMADIM" olarak raporlanir.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

IL = "Ankara"
IL_KODU = "TR-06"
SAKLAMA_YIL = 2          # KVKK -- ticari karar, hukuki gorus degil

AYNALAR = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

SEGMENTLER = {
    # Eczane 1799 kayitla en agir sorgu; tek seferde Overpass zaman asimina
    # ugruyor. way'ler ihmal edilebilir (26/24993 olculdu), node yeterli.
    "eczane": '(node["amenity"="pharmacy"](area.a););',
    "muayenehane": ('(node["amenity"="doctors"](area.a);way["amenity"="doctors"](area.a);'
                    'node["healthcare"="doctor"](area.a);way["healthcare"="doctor"](area.a););'),
    "klinik": ('(node["amenity"="clinic"](area.a);way["amenity"="clinic"](area.a);'
               'node["healthcare"="clinic"](area.a);way["healthcare"="clinic"](area.a););'),
    "tip merkezi": ('(node["healthcare"="centre"](area.a);way["healthcare"="centre"](area.a);'
                    'node["healthcare"="medical_centre"](area.a);'
                    'way["healthcare"="medical_centre"](area.a););'),
    "guzellik merkezi": ('(node["shop"="beauty"](area.a);way["shop"="beauty"](area.a);'
                         'node["shop"="cosmetics"](area.a);way["shop"="cosmetics"](area.a););'),
    "spa masaj": ('(node["leisure"="spa"](area.a);way["leisure"="spa"](area.a);'
                  'node["shop"="massage"](area.a);way["shop"="massage"](area.a);'
                  'node["leisure"="sauna"](area.a);'
                  'node["amenity"="public_bath"](area.a);way["amenity"="public_bath"](area.a););'),
    "spor salonu": ('(node["leisure"="fitness_centre"](area.a);way["leisure"="fitness_centre"](area.a);'
                    'node["leisure"="sports_centre"](area.a);way["leisure"="sports_centre"](area.a););'),
}

TEL_ALAN = ("phone", "contact:phone", "contact:mobile", "phone:TR", "contact:phone:TR")
SITE_ALAN = ("website", "contact:website", "url", "contact:instagram", "contact:facebook")


def cek(govde: str):
    alan = f'[out:json][timeout:180];area["ISO3166-2"="{IL_KODU}"]->.a;'
    son = ""
    for deneme in range(3):
        ayna = AYNALAR[deneme % len(AYNALAR)]
        try:
            veri = urllib.parse.urlencode({"data": alan + govde + "out tags center;"}).encode()
            istek = urllib.request.Request(
                ayna, data=veri, headers={"User-Agent": "lcarlie-lead-arastirma/1.0"})
            with urllib.request.urlopen(istek, timeout=200) as y:
                cevap = json.load(y)
            # 🔴 OLCULEN TUZAK: Overpass zaman asiminda HTTP 200 + BOS liste +
            # "remark" doner. Ilk kosuda eczane boyle 0 kayit gorundu -- oysa
            # 1799 oldugu ayrica olculmustu. "Bos sonuc" ile "soramadim" ayni
            # sey degil; bu ayrimi kaybetmek bu projenin tekrar eden kok
            # hatasi. remark varsa BASARISIZ sayilir ve tekrar denenir.
            not_ = (cevap.get("remark") or "").strip()
            if not_:
                raise RuntimeError("overpass remark: " + not_[:90])
            ogeler = cevap.get("elements") or []
            if not ogeler:
                raise RuntimeError("bos sonuc dondu -- zaman asimi olabilir")
            return ogeler, ""
        except Exception as e:                                    # noqa: BLE001
            son = f"{str(e)[:40]} @{ayna.split('//')[1].split('/')[0]}"
            time.sleep(20 * (deneme + 1))
    return None, son


def ilk(tags: dict, alanlar) -> str | None:
    for a in alanlar:
        v = (tags.get(a) or "").strip()
        if v:
            return v[:300]
    return None


def adres(tags: dict) -> str | None:
    if tags.get("addr:full"):
        return tags["addr:full"][:300]
    parca = [tags.get(k) for k in ("addr:street", "addr:housenumber",
                                   "addr:neighbourhood", "addr:district")]
    p = " ".join(x for x in parca if x)
    return p[:300] or None


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1"],
        input=sql, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:400])
    return r.stdout


def main() -> int:
    bitis = date.today() + timedelta(days=365 * SAKLAMA_YIL)
    ozet, soramadim = [], []

    for segment, sorgu in SEGMENTLER.items():
        oge, hata = cek(sorgu)
        if oge is None:
            soramadim.append((segment, hata))
            print(f"  {segment:<18} SORAMADIM -- {hata}")
            time.sleep(12)
            continue

        gorulen, ham, lead = set(), [], []
        for o in oge:
            tip, kimlik = o.get("type"), o.get("id")
            anahtar = f"{tip}/{kimlik}"
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            t = o.get("tags") or {}
            ad = (t.get("name") or "").strip()
            enlem = o.get("lat") or (o.get("center") or {}).get("lat")
            boylam = o.get("lon") or (o.get("center") or {}).get("lon")
            ham.append((tip, kimlik, segment, IL, json.dumps(t, ensure_ascii=False),
                        enlem, boylam))
            if len(ad) > 1:      # adsiz kayit lead degildir
                lead.append(("osm", f"osm:{anahtar}", segment, IL,
                             t.get("addr:district") or t.get("addr:city"),
                             ad, ilk(t, TEL_ALAN), ilk(t, SITE_ALAN), adres(t),
                             enlem, boylam, bitis.isoformat()))

        def q(v):
            if v is None:
                return "NULL"
            return "'" + str(v).replace("'", "''") + "'"

        if ham:
            satir = ",".join(
                f"({q(a)},{b},{q(c)},{q(d)},{q(e)}::jsonb,"
                f"{f if f is not None else 'NULL'},{g if g is not None else 'NULL'})"
                for a, b, c, d, e, f, g in ham)
            psql("INSERT INTO raw.lead_osm (osm_tip,osm_id,segment,il,etiketler,enlem,boylam) "
                 f"VALUES {satir} ON CONFLICT (osm_tip,osm_id) DO UPDATE SET "
                 "etiketler=EXCLUDED.etiketler, segment=EXCLUDED.segment, cekildi=now();")
        if lead:
            satir = ",".join(
                f"({q(a)},{q(b)},{q(c)},{q(d)},{q(e)},{q(f)},{q(g)},{q(h)},{q(i)},"
                f"{j if j is not None else 'NULL'},{k if k is not None else 'NULL'},{q(l)}::date)"
                for a, b, c, d, e, f, g, h, i, j, k, l in lead)
            psql("INSERT INTO core.lead (kaynak,kaynak_kimlik,segment,il,ilce,ad,telefon,"
                 "site,adres,enlem,boylam,saklama_sonu) "
                 f"VALUES {satir} ON CONFLICT (kaynak,kaynak_kimlik) DO UPDATE SET "
                 "ad=EXCLUDED.ad, telefon=EXCLUDED.telefon, site=EXCLUDED.site, "
                 "adres=EXCLUDED.adres, toplandi=now();")

        telefonlu = sum(1 for x in lead if x[6])
        ozet.append((segment, len(ham), len(lead), telefonlu))
        print(f"  {segment:<18} ham {len(ham):>5}   lead {len(lead):>5}   telefonlu {telefonlu:>5}")
        time.sleep(12)

    print()
    print(psql("SELECT segment, kayit, telefonlu, siteli FROM mart.lead_ozet "
               "WHERE il = 'Ankara' ORDER BY kayit DESC;"))
    if soramadim:
        print("SORAMADIM (sifir DEGIL, tekrar denenmeli):")
        for s, h in soramadim:
            print(f"  {s}: {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
