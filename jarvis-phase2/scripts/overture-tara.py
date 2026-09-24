#!/usr/bin/env python3
"""Overture Maps Places -> raw.overture_poi. Ziyaret hedeflerinin ikinci kaynağı.

NEDEN İKİNCİ KAYNAK. OpenStreetMap Ankara'da yalnız 203 klinik ve 19
muayenehane biliyor; 5,7 milyonluk bir şehir için bu açıkça eksik. Ölçüldü
(25.09.2026), iki kaynak BİRBİRİNİ TAMAMLIYOR:

                    OSM      Overture
  eczane           1.799        636     <- OSM daha iyi
  spor salonu        193      1.189     <- Overture 6 kat
  diş                 94        678     <- Overture 7 kat
  hastane            141        564
  güzellik salonu      0      1.368     <- OSM'de HİÇ YOK
  e-posta            %0,5       %36
  telefon             %59       %81
  adres               %23       %96

Bu yüzden ikisi de tutulur, biri diğerinin yerine geçmez.

LİSANS. Overture Places `CDLA Permissive v2.0` -- veriyi saklamamıza ve
kullanmamıza izin verir. Google/Yandex Places'in aksine önbelleğe alma
yasağı yoktur; bu yüzden kendi veri merkezimizde tutulabilir.

🔴 SİLME YOK. OSM tarayıcısındaki kuralın aynısı: taramada görünmeyen kayıt
silinmez, `kayip_at` yazılır. "Kapandı" ile "bu sürümde eksik" aynı şey değil.

AYRI VENV. duckdb yalnız `/opt/lcarlie/venv-veri` içinde kurulu; ana venv
kirletilmez (projede aynı kural MCP sunucusu için de geçerli).
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
import time

import duckdb

KAP = "lcarlie-postgres"
SURUM = "2026-08-19.0"
S3 = ("s3://overturemaps-us-west-2/release/%s/theme=places/type=place/*.parquet"
      % SURUM)

# Ankara kaba sınırları. Overture parquet'te bbox sütunu var, bu yüzden
# filtre sunucuda uygulanıyor ve indirilen veri küçük kalıyor.
SINIR = {"xmin": 32.3, "xmax": 33.3, "ymin": 39.4, "ymax": 40.3}

# Overture kategorisi -> bizim türümüz. Sıra ÖNEMLİ: daha özgül olan önce.
# Eşleşmeyen kategori ALINMAZ -- "belki işimize yarar" diye her şeyi almak,
# listeyi kullanılamaz hale getirir.
# Overture kategorisi -> bizim turumuz.
#
# 🔴 ONCE BIRINCIL KATEGORI. Olculdu 25.09.2026: alternatif kategorilerde ilk
# eslesen alininca `diagnostic_services` uc ayri ture dagildi (DIS 113,
# HASTANE 223, KLINIK 512). Ayni kategori ayni ture gitmeli; aksi halde
# filtre guvenilmez olur ve "kliniklerin hepsi" dedigimizde bir kismi
# hastanede saklanir.
#
# DISLANANLAR once kontrol edilir: arastirma laboratuvari ya da tip fakultesi
# ziyaret hedefi degildir. "Belki isimize yarar" diye her seyi almak, listeyi
# kullanilamaz hale getirir.
DISLANAN = (
    "medical_research", "medical_school", "health_department",
    "public_health", "blood_bank", "career_counseling",
)

# ---------------------------------------------------------------------------
# HEDEF SEGMENTLER -- URUN KATALOGUNDAN TURETILDI
#
# Kategoriler tahminle degil, urunlerin GERCEK kullanim alanlarindan secildi
# (knowledge/40-eski-katalog-ic-bilgi.md):
#
#   DERMABED     yatak yarasi, basiya bagli cilt  -> HUZUREVI, hastane
#   DERMAMOVERA  eklem, diz, kireclenme           -> HUZUREVI, fizik tedavi
#   SERALIMBO    huzursuz bacak, gece krampi      -> HUZUREVI, noroloji
#   DERMAVASC    damar ve dolasim                 -> HUZUREVI, kardiyoloji
#   Bebek serisi (babydent/baby/babyshower/...)   -> KRES, pediatri, eczane
#   OPTYWAVE     goz cevresi, makula              -> OPTIK, goz klinigi
#   DERMACORN/DERMAGUARD  nasir, ayak             -> AYAK (podoloji)
#   HAIR NOURISHER  sac ve sac derisi             -> KUAFOR
#   CALMORIS/MENTHALIS  anksiyete, odaklanma      -> PSIKOLOG
#   SOFTGUARD/BUGUARD  tekstil, akar, bocek       -> OTEL, HUZUREVI
#   VIREON/FEMISIA/INTIMBLANC  intim bakim        -> UROLOJI, kadin dogum
#   LIFTELLE/LIPVORA/DERMASTRA/CALMAROS/SUNACNEA  -> GUZELLIK, dermatoloji
#
# Veteriner ve evcil hayvan kategorileri ALINMADI: katalogda hayvan urunu yok.
# "Belki isimize yarar" diye eklemek, listeyi kullanilamaz hale getirir.
# ---------------------------------------------------------------------------

KATEGORI = [
    # --- dis ---
    ("cosmetic_dentist", "DIS"), ("pediatric_dentist", "DIS"),
    ("general_dentistry", "DIS"), ("orthodont", "DIS"), ("endodont", "DIS"),
    ("dentist", "DIS"), ("dental", "DIS"),
    # --- eczane / takviye ---
    ("pharmacy", "ECZANE"), ("drugstore", "ECZANE"),
    ("medical_supply", "ECZANE"), ("surgical_appliances", "ECZANE"),
    ("vitamins_and_supplements", "ECZANE"), ("herbal", "ECZANE"),
    # --- yasli bakim (DERMABED, DERMAMOVERA, SERALIMBO, DERMAVASC) ---
    ("retirement_home", "HUZUREVI"), ("nursing_home", "HUZUREVI"),
    ("assisted_living", "HUZUREVI"), ("senior_citizen", "HUZUREVI"),
    ("skilled_nursing", "HUZUREVI"), ("home_health_care", "HUZUREVI"),
    ("hospice", "HUZUREVI"), ("elder", "HUZUREVI"),
    ("disability_services", "HUZUREVI"),
    # --- kres / anaokulu (bebek serisi) ---
    ("day_care_preschool", "KRES"), ("child_care_and_day_care", "KRES"),
    ("preschool", "KRES"), ("kindergarten", "KRES"), ("nursery_school", "KRES"),
    # --- hastane ---
    ("hospital", "HASTANE"),
    # --- spor ---
    ("gymnastics_center", "SPOR"), ("fitness_trainer", "SPOR"),
    ("gym", "SPOR"), ("fitness", "SPOR"), ("pilates", "SPOR"),
    ("yoga", "SPOR"), ("crossfit", "SPOR"), ("martial_arts", "SPOR"),
    ("swimming_pool", "SPOR"), ("sports_club", "SPOR"),
    # --- kuafor / berber (HAIR NOURISHER) ---
    ("hair_salon", "KUAFOR"), ("barber", "KUAFOR"), ("nail_salon", "KUAFOR"),
    ("hair_removal", "KUAFOR"), ("laser_hair_removal", "KUAFOR"),
    ("hair_replacement", "KUAFOR"), ("hair_supply", "KUAFOR"),
    # --- guzellik / estetik ---
    ("beauty_salon", "GUZELLIK"), ("medical_spa", "GUZELLIK"),
    ("health_spa", "GUZELLIK"), ("spas", "GUZELLIK"),
    ("cosmetic", "GUZELLIK"), ("skin_care", "GUZELLIK"),
    ("massage", "GUZELLIK"), ("aromatherapy", "GUZELLIK"),
    ("tattoo", "GUZELLIK"), ("piercing", "GUZELLIK"),
    ("personal_care_service", "GUZELLIK"),
    # --- optik (OPTYWAVE) ---
    ("eyewear_and_optician", "OPTIK"), ("optometrist", "OPTIK"),
    ("optician", "OPTIK"),
    # --- ayak (DERMACORN, DERMAGUARD) ---
    ("podiatry", "AYAK"), ("podiatrist", "AYAK"), ("foot_care", "AYAK"),
    # --- psikoloji (CALMORIS, MENTHALIS) ---
    ("psychologist", "PSIKOLOG"), ("psychotherapist", "PSIKOLOG"),
    ("counseling_and_mental_health", "PSIKOLOG"),
    ("mental_health", "PSIKOLOG"), ("speech_therapist", "PSIKOLOG"),
    # --- diyetisyen ---
    ("nutritionist", "DIYETISYEN"), ("dietitian", "DIYETISYEN"),
    # --- otel (SOFTGUARD, BUGUARD) ---
    ("hotel", "OTEL"), ("accommodation", "OTEL"), ("resort", "OTEL"),
    # --- klinik / tani ---
    ("diagnostic_services", "KLINIK"), ("imaging", "KLINIK"),
    ("laborator", "KLINIK"), ("dialysis", "KLINIK"),
    ("eye_care", "KLINIK"), ("womens_health", "KLINIK"),
    ("physical_therapy", "KLINIK"), ("rehabilitation", "KLINIK"),
    ("clinic", "KLINIK"), ("medical_center", "KLINIK"),
    ("health_and_medical", "KLINIK"), ("medical_service", "KLINIK"),
    # --- doktor / mauyenehane ---
    ("obstetrician", "DOKTOR"), ("gynecolog", "DOKTOR"),
    ("urolog", "DOKTOR"), ("neurolog", "DOKTOR"),
    ("pediatric", "DOKTOR"), ("dermatolog", "DOKTOR"),
    ("cardiolog", "DOKTOR"), ("orthoped", "DOKTOR"),
    ("doctor", "DOKTOR"), ("physician", "DOKTOR"), ("surgeon", "DOKTOR"),
]


def tur_bul(kategori: str, alt) -> str | None:
    """Birincil kategoriye gore tur. Alternatifler YALNIZ birincil
    eslesmediginde bakilir -- ayni kategori her zaman ayni ture gitsin."""
    birincil = str(kategori or "").lower()
    for parca in DISLANAN:
        if parca in birincil:
            return None
    for parca, tur in KATEGORI:
        if parca in birincil:
            return tur
    for a in (alt or []):
        metin = str(a).lower()
        if any(d in metin for d in DISLANAN):
            continue
        for parca, tur in KATEGORI:
            if parca in metin:
                return tur
    return None


SORGU = """
SELECT
  id,
  names.primary                         AS ad,
  categories.primary                    AS kategori,
  list_transform(categories.alternate, x -> x) AS alt_kategoriler,
  bbox.xmin                             AS boylam,
  bbox.ymin                             AS enlem,
  phones[1]                             AS telefon,
  emails[1]                             AS eposta,
  websites[1]                           AS website,
  socials[1]                            AS sosyal,
  addresses[1].freeform                 AS adres,
  addresses[1].locality                 AS ilce,
  confidence                            AS guven
FROM read_parquet('%s')
WHERE bbox.xmin BETWEEN %f AND %f
  AND bbox.ymin BETWEEN %f AND %f
  AND categories.primary IS NOT NULL
  AND names.primary IS NOT NULL
""" % (S3, SINIR["xmin"], SINIR["xmax"], SINIR["ymin"], SINIR["ymax"])


def psql(sql: str, girdi: str | None = None):
    return subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n"]
        + ([] if girdi else ["-tAc", sql]),
        input=girdi, capture_output=True, text=True, timeout=600)


def say(sql: str) -> int:
    try:
        return int(psql(sql).stdout.strip())
    except Exception:  # noqa: BLE001
        return -1


def main() -> int:
    t0 = time.time()
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';"
                " SET memory_limit='8GB';")
    try:
        satirlar = con.execute(SORGU).fetchall()
    except Exception as exc:  # noqa: BLE001
        print("OVERTURE OKUNAMADI: %s %s" % (type(exc).__name__, str(exc)[:250]))
        return 1

    tampon = io.StringIO()
    yazici = csv.writer(tampon, lineterminator="\n")
    alinan = atlanan = 0
    for (kimlik, ad, kategori, alt, boylam, enlem, telefon, eposta, website,
         sosyal, adres, ilce, guven) in satirlar:
        tur = tur_bul(kategori, alt)
        if not tur:
            atlanan += 1
            continue
        yazici.writerow([kimlik, ad or "", tur, kategori or "", enlem, boylam,
                         telefon or "", eposta or "", website or "",
                         sosyal or "", adres or "", ilce or "",
                         guven if guven is not None else ""])
        alinan += 1

    if not alinan:
        print("hic uygun kayit yok -- yazma yapilmadi")
        return 1

    once = say("select count(*) from raw.overture_poi")
    sql = """\\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE _gelen (
  overture_id text, ad text, tur text, kategori text,
  enlem double precision, boylam double precision,
  telefon text, eposta text, website text, sosyal text,
  adres text, ilce text, guven numeric
) ON COMMIT DROP;
COPY _gelen FROM STDIN WITH (FORMAT csv);
""" + tampon.getvalue() + """\\.
INSERT INTO raw.overture_poi AS p
  (overture_id, ad, tur, kategori, enlem, boylam, telefon, eposta, website,
   sosyal, adres, ilce, guven, ilk_gorulme, son_gorulme)
SELECT overture_id, nullif(ad,''), tur, nullif(kategori,''), enlem, boylam,
       nullif(telefon,''), nullif(eposta,''), nullif(website,''),
       nullif(sosyal,''), nullif(adres,''), nullif(ilce,''), guven,
       now(), now()
FROM _gelen
ON CONFLICT (overture_id) DO UPDATE SET
  ad = EXCLUDED.ad, tur = EXCLUDED.tur, kategori = EXCLUDED.kategori,
  enlem = EXCLUDED.enlem, boylam = EXCLUDED.boylam,
  telefon = EXCLUDED.telefon, eposta = EXCLUDED.eposta,
  website = EXCLUDED.website, sosyal = EXCLUDED.sosyal,
  adres = EXCLUDED.adres, ilce = EXCLUDED.ilce, guven = EXCLUDED.guven,
  son_gorulme = now(), kayip_at = NULL;

UPDATE raw.overture_poi SET kayip_at = now()
 WHERE kayip_at IS NULL
   AND overture_id NOT IN (SELECT overture_id FROM _gelen);
COMMIT;
"""
    sonuc = psql("", girdi=sql)
    if sonuc.returncode != 0:
        print("YAZMA BASARISIZ (psql %d)" % sonuc.returncode)
        print((sonuc.stderr or "").strip()[:600])
        return 1

    sonra = say("select count(*) from raw.overture_poi")
    print("Overture %s · %d kayit okundu · %d alindi · %d kategori disi · %.0f sn"
          % (SURUM, len(satirlar), alinan, atlanan, time.time() - t0))
    print("tabloda %d -> %d (yeni %d)" % (once, sonra, sonra - once))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
