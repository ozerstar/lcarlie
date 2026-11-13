#!/usr/bin/env python3
"""Google Haritalar taraması (gosom/google-maps-scraper CSV) -> raw.eczane_kaynak
-> core.eczane_hedef eşleşmesi + core.eczane_eposta.

Kullanım:  eczane-gmaps-ice.py <il> <tarama.csv>

🔴 E-POSTA AYIKLAMA. Tarayıcı, haritadaki "web sitesi" bağlantısına girip
bulduğu her adresi toplar. Ölçüldü (13.11, Kızılay): 29 eczanenin 5 "sitesi"
vardı; dördü rehber sayfası (firmasec, eczaneleri.org), biri Bioderma'nın ürün
sayfasıydı ve oradan Bioderma'nın destek adresi "eczane e-postası" diye
geldi. O adrese eczane kampanyası gitseydi hem boşa gider hem marka itibarı
zedelenirdi. Bu yüzden adres YALNIZ şu iki durumda kabul edilir:
  1. Ücretsiz posta (gmail, hotmail…) ve yerel kısımda eczane izi ya da
     eczane adından bir parça var.
  2. Eczanenin KENDİ alan adı: e-posta alanı == site alanı ve alan adında
     eczane izi ya da eczane adından bir parça var.
Kabul edilmeyen adres silinmez; ham'da kalır, kampanyaya girmez.
"""
import csv
import json
import re
import subprocess
import sys
from urllib.parse import urlparse

PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
        "-v", "ON_ERROR_STOP=1", "-At"]
UCRETSIZ = {"gmail.com", "hotmail.com", "hotmail.com.tr", "outlook.com", "outlook.com.tr",
            "yahoo.com", "yahoo.com.tr", "yandex.com", "yandex.com.tr", "icloud.com",
            "mynet.com", "live.com", "windowslive.com", "msn.com", "superonline.com",
            "ttmail.com", "turk.net"}
ECZANE_IZI = ("ecz", "pharm", "eczane")
# Adında "eczane" geçen ama TEK bir eczaneye ait olmayan alanlar: rehberler,
# meslek kuruluşları, çok satıcılı siteler. Ölçüldü (13.11, Çankaya): iki ayrı
# eczanenin "sitesi" eczane.com.tr çıktı ve info@eczane.com.tr ikisine de yazıldı.
REHBER = {"eczane.com.tr", "eczaneleri.org", "nobetcieczaneler.org", "firmasec.com",
          "aeo.org.tr", "teb.org.tr", "eczanem.com", "nobetcieczane.com", "eczanebul.com",
          "ikas.com", "ikas.de", "tr.naos.com", "bioderma.com.tr"}
GENEL_KELIME = {"eczane", "eczanesi", "eczanes", "pharmacy", "yeni", "merkez", "hayat",
                "sifa", "saglik", "ankara", "istanbul", "izmir", "cadde"}
csv.field_size_limit(10 ** 8)


def sade(s):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    return s.translate(str.maketrans("çğıöşüâî", "cgiosuai"))


def ad_parcalari(ad):
    return {k for k in re.findall(r"[a-z0-9]{4,}", sade(ad)) if k not in GENEL_KELIME}


def alan(url):
    try:
        h = urlparse(url if "://" in url else "http://" + url).hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def eposta_sec(epostalar, site, ad):
    """(kabul, red) listeleri."""
    parca = ad_parcalari(ad)
    site_alan = alan(site)
    kabul, red = [], []
    for e in epostalar:
        e = e.strip().lower().rstrip(".")
        if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", e):
            continue
        yerel, ea = e.split("@", 1)
        iz = lambda m: any(z in m for z in ECZANE_IZI) or any(p in m for p in parca)  # noqa: E731
        if ea in REHBER or site_alan in REHBER and ea not in UCRETSIZ:
            red.append(e)
        elif ea in UCRETSIZ and iz(yerel):
            kabul.append(e)
        elif ea not in UCRETSIZ and ea == site_alan and iz(ea):
            kabul.append(e)
        else:
            red.append(e)
    return sorted(set(kabul)), sorted(set(red))


def tel10(t):
    d = re.sub(r"\D", "", t or "")
    return d[-10:] if len(d) >= 10 else ""


def satirlar(il, yol):
    with open(yol, encoding="utf-8") as f:
        yield from _satirlar(il, csv.DictReader(f))


def _satirlar(il, okuyucu):
    for r in okuyucu:
        kategori = r.get("category") or ""
        baslik = r.get("title") or ""
        if "eczane" not in sade(kategori + " " + baslik) and "pharmacy" not in sade(kategori):
            continue
        try:
            ham_ep = json.loads(r.get("emails") or "[]")
        except json.JSONDecodeError:
            ham_ep = [x for x in re.split(r"[,\s]+", r.get("emails") or "") if "@" in x]
        kabul, red = eposta_sec(ham_ep, r.get("website") or "", baslik)
        try:
            tam = json.loads(r.get("complete_address") or "{}")
        except json.JSONDecodeError:
            tam = {}
        yield {
            "kaynak_id": r.get("place_id") or r.get("cid") or r.get("data_id"),
            "il": il, "ilce": tam.get("borough") or "", "ad": baslik, "kategori": kategori,
            "telefon": tel10(r.get("phone")), "epostalar": kabul, "web": r.get("website") or "",
            "adres": r.get("address") or "",
            "enlem": r.get("latitude") or None, "boylam": r.get("longitude") or None,
            "ham": {"reddedilen_eposta": red, "puan": r.get("review_rating"),
                    "yorum": r.get("review_count"), "durum": r.get("status"),
                    "link": r.get("link"), "saatler": r.get("open_hours")},
        }


YUKLE = r"""
BEGIN;
CREATE TEMP TABLE y (j jsonb);
\copy y FROM STDIN
INSERT INTO raw.eczane_kaynak (kaynak, kaynak_id, il, ilce, ad, kategori, telefonlar, epostalar,
                               web, adres, enlem, boylam, ham)
SELECT 'GMAPS', j->>'kaynak_id', j->>'il', nullif(j->>'ilce',''), j->>'ad', j->>'kategori',
       CASE WHEN j->>'telefon' <> '' THEN ARRAY[j->>'telefon'] ELSE '{}' END,
       ARRAY(SELECT jsonb_array_elements_text(j->'epostalar')),
       nullif(j->>'web',''), j->>'adres', (j->>'enlem')::float8, (j->>'boylam')::float8, j->'ham'
FROM y WHERE j->>'kaynak_id' IS NOT NULL
ON CONFLICT (kaynak, kaynak_id) DO UPDATE SET
  telefonlar = EXCLUDED.telefonlar, epostalar = EXCLUDED.epostalar, web = EXCLUDED.web,
  adres = EXCLUDED.adres, ham = EXCLUDED.ham, son_gorulme = now();

CREATE OR REPLACE FUNCTION pg_temp.nrm(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT regexp_replace(translate(lower(replace(replace(coalesce(t,''),'İ','i'),'I','ı')),
         'çğıöşüâî','cgiosuai'), '(eczanesi|eczane|pharmacy|ecz\.?|\s|[^a-z0-9])', '', 'g') $$;

-- 1) Telefonla (aynı ilde)
UPDATE raw.eczane_kaynak k SET hedef_id = h.id, eslesme = 'TELEFON'
FROM core.eczane_hedef h
WHERE k.kaynak = 'GMAPS' AND k.hedef_id IS NULL AND k.il = :'il' AND h.il = k.il
  AND cardinality(k.telefonlar) > 0
  AND right(regexp_replace(coalesce(h.telefon,''),'\D','','g'),10) = k.telefonlar[1];
-- 2) Adla: ad o ilde iki tarafta da TEK ise (aynı adlı iki eczaneye yanlış veri yazmamak için)
WITH hk AS (SELECT id, pg_temp.nrm(eczane) n FROM core.eczane_hedef WHERE il = :'il'),
     hs AS (SELECT n FROM hk GROUP BY n HAVING count(*) = 1),
     kk AS (SELECT id, pg_temp.nrm(ad) n FROM raw.eczane_kaynak
            WHERE kaynak = 'GMAPS' AND il = :'il'),
     ks AS (SELECT n FROM kk GROUP BY n HAVING count(*) = 1)
UPDATE raw.eczane_kaynak k SET hedef_id = hk.id, eslesme = 'AD'
FROM kk JOIN ks USING (n) JOIN hs USING (n) JOIN hk USING (n)
WHERE k.id = kk.id AND k.hedef_id IS NULL AND length(kk.n) >= 3;
-- 3) Eşleşmeyen: listede olmayan eczane -> yeni hedef
WITH yeni AS (
  INSERT INTO core.eczane_hedef (il, eczane, telefon, adres, ilce, kaynak, oncelik)
  SELECT k.il, k.ad, k.telefonlar[1], k.adres, k.ilce, 'GMAPS',
         (SELECT min(oncelik) FROM core.eczane_hedef WHERE il = k.il)
  FROM raw.eczane_kaynak k
  WHERE k.kaynak = 'GMAPS' AND k.il = :'il' AND k.hedef_id IS NULL
  ON CONFLICT (il, eczane, telefon) DO NOTHING
  RETURNING id, il, eczane, telefon)
UPDATE raw.eczane_kaynak k SET hedef_id = yeni.id, eslesme = 'YENI'
FROM yeni WHERE k.kaynak = 'GMAPS' AND k.hedef_id IS NULL AND k.il = yeni.il
  AND k.ad = yeni.eczane AND k.telefonlar[1] IS NOT DISTINCT FROM yeni.telefon;

-- Eksik telefon/ilçe tamamlanır (var olan beyan EZİLMEZ)
UPDATE core.eczane_hedef h SET telefon = coalesce(h.telefon, k.telefonlar[1]),
       ilce = coalesce(h.ilce, k.ilce), guncellendi = now()
FROM raw.eczane_kaynak k WHERE k.hedef_id = h.id AND k.kaynak = 'GMAPS' AND k.il = :'il'
  AND (h.telefon IS NULL OR h.ilce IS NULL);
-- E-postalar
INSERT INTO core.eczane_eposta (hedef_id, eposta, kaynak)
SELECT k.hedef_id, e, 'GMAPS' FROM raw.eczane_kaynak k, unnest(k.epostalar) e
WHERE k.kaynak = 'GMAPS' AND k.il = :'il' AND k.hedef_id IS NOT NULL
ON CONFLICT (hedef_id, eposta) DO NOTHING;

SELECT count(*) || ' kayıt · ' ||
       count(*) FILTER (WHERE eslesme = 'TELEFON') || ' telefonla · ' ||
       count(*) FILTER (WHERE eslesme = 'AD') || ' adla · ' ||
       count(*) FILTER (WHERE eslesme = 'YENI') || ' yeni eczane · ' ||
       count(*) FILTER (WHERE cardinality(epostalar) > 0) || ' e-postalı · ' ||
       count(*) FILTER (WHERE left(telefonlar[1],1) = '5') || ' cep'
FROM raw.eczane_kaynak WHERE kaynak = 'GMAPS' AND il = :'il';
COMMIT;
"""


def main():
    il, yol = sys.argv[1], sys.argv[2]
    veri = list(satirlar(il, yol))
    # \copy metin biçiminde ters eğik çizgi kaçış karakteridir
    govde = "\n".join(json.dumps(v, ensure_ascii=False).replace("\\", "\\\\") for v in veri)
    sql = YUKLE.replace("\\copy y FROM STDIN", "\\copy y FROM STDIN\n" + govde + "\n\\.")
    cikti = subprocess.run(PSQL + ["-v", "il=" + il], input=sql, capture_output=True, text=True)
    if cikti.returncode:
        sys.exit(cikti.stderr)
    print(il + ":", [s for s in cikti.stdout.splitlines() if "kayıt" in s][-1])


if __name__ == "__main__":
    main()
