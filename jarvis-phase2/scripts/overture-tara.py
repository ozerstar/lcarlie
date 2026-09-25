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
import time

import duckdb

KAP = "lcarlie-postgres"

# 🔴 SURUM SABITLENMEZ. Ilk surumde koda yazilmisti (2026-08-19.0) ve iki gun
# once cikan 2026-09-23.0 kacirilmisti -- aylik tarama sonsuza kadar ayni eski
# veriyi cekerdi ve "tarandi" diye rapor ederdi. Guncellik bu isin can damari:
# kapanmis bir eczaneye gitmek, hic bilinmeyen bir eczaneden daha pahali.
#
# S3 klasor listesinden en yeni surum secilir. Liste okunamazsa HATA verilir,
# eski bir surume SESSIZCE dusulmez.
S3_KOK = "s3://overturemaps-us-west-2/release"


def en_yeni_surum(con) -> str:
    satirlar = con.execute(
        "SELECT file FROM glob('%s/*/theme=places/type=place/part-00000*')"
        % S3_KOK).fetchall()
    surumler = sorted({
        yol[0].split("/release/", 1)[1].split("/", 1)[0] for yol in satirlar})
    if not surumler:
        raise RuntimeError("Overture surum listesi bos -- S3 okunamadi")
    return surumler[-1]

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
    "pharmaceutical_company", "medical_device_manufactur",
    # Ad benzerligi tuzaklari: "counseling" ekledigimiz icin kariyer ve
    # kredi danismanligi da eslesirdi; "school" ekledigimiz icin kozmetoloji
    # OKULU ziyaret hedefi sanilirdi. Falcilik ise hic degil.
    "credit_and_debt", "cosmetology_school", "psychic_advising",
    "medical_research_institute",
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
    ("dental_clinic", "DIS"), ("dentist", "DIS"), ("dental", "DIS"),
    # --- eczane / takviye ---
    ("pharmacy", "ECZANE"), ("drugstore", "ECZANE"),
    ("medical_supply", "ECZANE"), ("surgical_appliances", "ECZANE"),
    ("vitamins_and_supplements", "ECZANE"), ("herbal", "ECZANE"),
    ("health_food_store", "ECZANE"),
    # --- yasli bakim (DERMABED, DERMAMOVERA, SERALIMBO, DERMAVASC) ---
    ("retirement_home", "HUZUREVI"), ("nursing_home", "HUZUREVI"),
    ("assisted_living", "HUZUREVI"), ("senior_citizen", "HUZUREVI"),
    ("skilled_nursing", "HUZUREVI"), ("home_health_care", "HUZUREVI"),
    ("hospice", "HUZUREVI"), ("elder", "HUZUREVI"),
    ("disability_services", "HUZUREVI"),
    # --- kres / anaokulu (bebek serisi) ---
    ("day_care_preschool", "KRES"), ("child_care_and_day_care", "KRES"),
    ("preschool", "KRES"), ("kindergarten", "KRES"), ("nursery_school", "KRES"),
    ("baby_gear_and_nursery_store", "BEBEK"),
    ("childrens_clothing_store", "BEBEK"), ("baby_store", "BEBEK"),
    # --- hastane ---
    ("hospital", "HASTANE"),
    # --- spor ---
    ("gymnastics_center", "SPOR"), ("fitness_trainer", "SPOR"),
    ("gym", "SPOR"), ("fitness", "SPOR"), ("pilates", "SPOR"),
    ("yoga_studio", "SPOR"), ("yoga", "SPOR"), ("crossfit", "SPOR"),
    ("martial_arts", "SPOR"),
    ("swimming_pool", "SPOR"), ("sports_club", "SPOR"),
    # --- kuafor / berber (HAIR NOURISHER) ---
    ("hair_salon", "KUAFOR"), ("barber", "KUAFOR"), ("nail_salon", "KUAFOR"),
    ("hair_removal", "KUAFOR"), ("laser_hair_removal", "KUAFOR"),
    ("hair_replacement", "KUAFOR"), ("hair_supply", "KUAFOR"),
    # --- guzellik / estetik ---
    ("beauty_salon", "GUZELLIK"), ("medical_spa", "GUZELLIK"),
    ("health_spa", "GUZELLIK"), ("spas", "GUZELLIK"), ("spa", "GUZELLIK"),
    ("day_spa", "GUZELLIK"), ("massage_spa", "GUZELLIK"),
    ("cosmetic", "GUZELLIK"), ("skin_care", "GUZELLIK"),
    ("massage", "GUZELLIK"), ("aromatherapy", "GUZELLIK"),
    ("tattoo", "GUZELLIK"), ("piercing", "GUZELLIK"),
    ("personal_care_service", "GUZELLIK"),
    ("beauty_supply", "GUZELLIK"), ("beauty_product_supplier", "GUZELLIK"),
    ("personal_or_beauty_service", "GUZELLIK"), ("tanning_salon", "GUZELLIK"),
    # --- optik (OPTYWAVE) ---
    ("eyewear_and_optician", "OPTIK"), ("optometrist", "OPTIK"),
    ("optician", "OPTIK"),
    # --- ayak (DERMACORN, DERMAGUARD) ---
    ("podiatry", "AYAK"), ("podiatrist", "AYAK"), ("foot_care", "AYAK"),
    # --- psikoloji (CALMORIS, MENTHALIS) ---
    ("psychologist", "PSIKOLOG"), ("psychotherapist", "PSIKOLOG"),
    ("psychology", "PSIKOLOG"), ("psychotherapy", "PSIKOLOG"),
    ("psychiatry", "PSIKOLOG"), ("counseling", "PSIKOLOG"),
    ("family_counseling", "PSIKOLOG"), ("speech_therapy", "PSIKOLOG"),
    ("counseling_and_mental_health", "PSIKOLOG"),
    ("mental_health", "PSIKOLOG"), ("speech_therapist", "PSIKOLOG"),
    # --- diyetisyen ---
    ("nutritionist", "DIYETISYEN"), ("dietitian", "DIYETISYEN"),
    ("nutrition_service", "DIYETISYEN"),
    # --- otel (SOFTGUARD, BUGUARD) ---
    ("hotel", "OTEL"), ("accommodation", "OTEL"), ("lodging", "OTEL"),
    ("resort", "OTEL"), ("motel", "OTEL"), ("hostel", "OTEL"),
    # --- klinik / tani ---
    ("diagnostic_services", "KLINIK"), ("imaging", "KLINIK"),
    ("laborator", "KLINIK"), ("dialysis", "KLINIK"),
    ("vision_or_eye_care", "OPTIK"), ("eyewear_store", "OPTIK"),
    ("eye_care", "KLINIK"),
    ("womens_health", "KLINIK"),
    ("physical_therapy", "KLINIK"), ("rehabilitation", "KLINIK"),
    ("outpatient_care_facility", "KLINIK"), ("health_care", "KLINIK"),
    ("naturopathic_medicine", "KLINIK"),
    ("reproductive_perinatal_and_womens_care", "KLINIK"),
    ("complementary_and_alternative_medicine", "KLINIK"),
    ("clinic", "KLINIK"), ("medical_center", "KLINIK"),
    ("health_and_medical", "KLINIK"), ("medical_service", "KLINIK"),
    # --- doktor / mauyenehane ---
    ("obstetrician", "DOKTOR"), ("gynecolog", "DOKTOR"),
    ("urolog", "DOKTOR"), ("neurolog", "DOKTOR"),
    ("pediatric", "DOKTOR"), ("dermatolog", "DOKTOR"),
    ("cardiolog", "DOKTOR"), ("orthoped", "DOKTOR"),
    ("doctor", "DOKTOR"), ("physician", "DOKTOR"), ("surgeon", "DOKTOR"),
]




# Kisa anahtarlar ALT DIZE olarak aranmaz: "spa" yazsaydik
# "spanish_restaurant" de eslesir ve listeye lokanta girerdi. Bu uzunlugun
# altindakiler yalnizca TAM esitlikle tutar.
ALT_DIZE_EN_AZ = 6


def _esle(metin: str) -> str | None:
    for parca, tur in KATEGORI:
        if parca == metin:
            return tur
    for parca, tur in KATEGORI:
        if len(parca) >= ALT_DIZE_EN_AZ and parca in metin:
            return tur
    return None


def tur_bul(kategori: str, alt) -> str | None:
    """Birincil kategoriye gore tur. Alternatifler YALNIZ birincil
    eslesmediginde bakilir -- ayni kategori her zaman ayni ture gitsin."""
    birincil = str(kategori or "").lower()
    for parca in DISLANAN:
        if parca in birincil:
            return None
    tur = _esle(birincil)
    if tur:
        return tur
    for a in (alt or []):
        metin = str(a).lower()
        if any(d in metin for d in DISLANAN):
            continue
        tur = _esle(metin)
        if tur:
            return tur
    return None


SORGU_KALIP = """
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
FROM read_parquet('{S3}')
WHERE bbox.xmin BETWEEN %f AND %f
  AND bbox.ymin BETWEEN %f AND %f
  AND categories.primary IS NOT NULL
  AND names.primary IS NOT NULL
""" % (SINIR["xmin"], SINIR["xmax"], SINIR["ymin"], SINIR["ymax"])



# 🔴 IKI SEMA. Overture 2026-09-23.0'da `categories` sutunu KALDIRILDI, yerine
# `taxonomy` (STRUCT: primary, hierarchy, alternates) geldi. Kategori ADLARI da
# degisti: dentist -> dental_clinic, spas -> spa, accommodation -> lodging.
# Surum sabitlemek veriyi dondurur; korlemesine en yeniyi almak aylik isi
# SESSIZCE cokertir. Dogru olan, hangi sutunun var oldugunu okuyup ona gore
# sormak.
SORGU_ESKI = """
SELECT id, names.primary AS ad,
       categories.primary AS kategori,
       categories.alternate AS alt_kategoriler,
       bbox.xmin AS boylam, bbox.ymin AS enlem,
       phones[1] AS telefon, emails[1] AS eposta, websites[1] AS website,
       socials[1] AS sosyal, addresses[1].freeform AS adres,
       addresses[1].locality AS ilce, confidence AS guven
FROM read_parquet('{S3}')
WHERE bbox.xmin BETWEEN %f AND %f AND bbox.ymin BETWEEN %f AND %f
  AND categories.primary IS NOT NULL AND names.primary IS NOT NULL
""" % (SINIR["xmin"], SINIR["xmax"], SINIR["ymin"], SINIR["ymax"])

SORGU_YENI = """
SELECT id, names.primary AS ad,
       taxonomy.primary AS kategori,
       taxonomy.alternates AS alt_kategoriler,
       bbox.xmin AS boylam, bbox.ymin AS enlem,
       phones[1] AS telefon, emails[1] AS eposta, websites[1] AS website,
       socials[1] AS sosyal, addresses[1].freeform AS adres,
       addresses[1].locality AS ilce, confidence AS guven
FROM read_parquet('{S3}')
WHERE bbox.xmin BETWEEN %f AND %f AND bbox.ymin BETWEEN %f AND %f
  AND taxonomy.primary IS NOT NULL AND names.primary IS NOT NULL
  AND coalesce(operating_status, '') <> 'permanently_closed'
""" % (SINIR["xmin"], SINIR["xmax"], SINIR["ymin"], SINIR["ymax"])


def sorgu_sec(con, s3: str) -> str:
    """Hangi sema? Sutun listesine BAKILIR, tahmin edilmez.

    Overture 2026-09-23.0'da `categories` kaldirilip `taxonomy` geldi.
    Surum sabitlemek veriyi dondurur, korlemesine en yeniyi almak aylik isi
    sessizce cokertir; dogru olan hangi sutunun var oldugunu okumak.
    """
    sutunlar = {r[0] for r in con.execute(
        "DESCRIBE SELECT * FROM read_parquet('%s') LIMIT 0" % s3).fetchall()}
    if "taxonomy" in sutunlar:
        return SORGU_YENI.replace("{S3}", s3)
    if "categories" in sutunlar:
        return SORGU_ESKI.replace("{S3}", s3)
    raise RuntimeError("tanimsiz Overture semasi: ne taxonomy ne categories var")


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



def gorunumu_tazele() -> None:
    """Maddileştirilmiş hedef görünümlerini yeniden kurar.

    CONCURRENTLY: tazeleme sürerken panel okumaya devam eder. Tarama
    gece koşuyor olsa bile sahadaki kişi listeyi kaybetmemeli.
    """
    sql = ("REFRESH MATERIALIZED VIEW CONCURRENTLY mart.saha_tum;\n"
           "REFRESH MATERIALIZED VIEW CONCURRENTLY mart.saha_kaynak;\n")
    sonuc = psql("", girdi=sql)
    if sonuc.returncode != 0:
        # Sessizce gecilemez: tazelenmemis gorunum, taranmamis veriyle
        # AYNI gorunur ama "tarandi" diye raporlanir.
        print("UYARI: gorunum tazelenemedi -- panel ESKI veriyi gosterir")
        print((sonuc.stderr or "").strip()[:400])
    else:
        print("gorunum tazelendi (mart.saha_tum, mart.saha_kaynak)")

def main() -> int:
    t0 = time.time()
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';"
                " SET memory_limit='8GB';")
    try:
        surum = en_yeni_surum(con)
        s3 = "%s/%s/theme=places/type=place/*.parquet" % (S3_KOK, surum)
        satirlar = con.execute(sorgu_sec(con, s3)).fetchall()
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
          % (surum, len(satirlar), alinan, atlanan, time.time() - t0))
    print("tabloda %d -> %d (yeni %d)" % (once, sonra, sonra - once))
    gorunumu_tazele()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
