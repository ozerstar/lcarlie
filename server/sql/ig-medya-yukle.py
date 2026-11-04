#!/usr/bin/env python3
# =============================================================================
# L'CARLIE - INSTAGRAM ORGANIK ICERIK ETL  (20.09.2026)
#
# 🔴 JETON: IG_ACCESS_TOKEN OLU (olculdu: "Cannot parse access token", 190).
#    Sayfa jetonu FB_PAGE_TOKEN calisiyor ve suresiz; IG is hesabi sayfaya
#    bagli oldugu icin ayni jetonla okunuyor. Once FB_PAGE_TOKEN denenir,
#    olmazsa META_SYSTEM_TOKEN.
#
# 🔴 SECRET KOMUT SATIRINA YAZILMAZ - URL'de degil, dosyadan okunur ve
#    hicbir yerde print edilmez.
#
# 🔴 SADECE OKUR. Gonderi paylasma, silme, yorum yazma kod yolu YOKTUR.
#
# Cikis: 0=SUCCESS 1=FAILED 2=NO_DATA 3=PARTIAL
# =============================================================================
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

G = "https://graph.facebook.com/v21.0"
KAP = os.environ.get("LCARLIE_KAP", "lcarlie-postgres")
ENV = "/opt/lcarlie/n8n/.env"
SAYFA_SINIRI = int(os.environ.get("IG_SAYFA_SINIRI", "10"))   # 10 x 50 = 500 gonderi tavani
KURU = "--kuru" in sys.argv

ALANLAR = ("id,caption,media_type,media_product_type,timestamp,"
           "like_count,comments_count,permalink,thumbnail_url")


def env(anahtar):
    try:
        with open(ENV, encoding="utf-8") as f:
            for satir in f:
                if satir.startswith(anahtar + "="):
                    return satir.split("=", 1)[1].strip()
    except OSError:
        pass
    return os.environ.get(anahtar)


def psql(sql, girdi=None):
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1", "-tA", "-f", "-"],
        input=(sql if girdi is None else sql + "\n" + girdi),
        capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:400])
    return p.stdout.strip()


def cek(url):
    istek = urllib.request.Request(url)
    with urllib.request.urlopen(istek, timeout=40) as c:
        return json.loads(c.read().decode("utf-8"))


IG_USER = env("IG_USER_ID")
if not IG_USER:
    print("HATA: IG_USER_ID yok", file=sys.stderr)
    sys.exit(1)

# Calisan jetonu bul. Hangi jetonun calistigini YAZAR ama jetonu yazmaz.
jeton = None
kullanilan = None
for ad in ("FB_PAGE_TOKEN", "META_SYSTEM_TOKEN", "IG_ACCESS_TOKEN"):
    t = env(ad)
    if not t:
        continue
    try:
        sonuc = cek(f"{G}/{IG_USER}?fields=username&"
                    + urllib.parse.urlencode({"access_token": t}))
        if sonuc.get("username"):
            jeton, kullanilan = t, ad
            break
    except Exception:  # noqa: BLE001 - olu jeton bir DURUMDUR, arıza degil
        continue

if not jeton:
    print("HATA: hicbir jeton Instagram'i okuyamadi "
          "(FB_PAGE_TOKEN / META_SYSTEM_TOKEN / IG_ACCESS_TOKEN)", file=sys.stderr)
    sys.exit(1)

# --- sayfalari dolas ---------------------------------------------------------
kayitlar = []
url = (f"{G}/{IG_USER}/media?limit=50&fields={ALANLAR}&"
       + urllib.parse.urlencode({"access_token": jeton}))
sayfa = 0
eksik_sayfa = False
while url and sayfa < SAYFA_SINIRI:
    try:
        veri = cek(url)
    except Exception as hata:  # noqa: BLE001
        print(f"  UYARI sayfa {sayfa+1} okunamadi: {str(hata)[:120]}", file=sys.stderr)
        eksik_sayfa = True
        break
    kayitlar.extend(veri.get("data") or [])
    url = ((veri.get("paging") or {}).get("next")) or None
    sayfa += 1

if not kayitlar:
    print("  meta ig-organik   veri yok")
    sys.exit(2)

print(f"  ok    jeton {kullanilan} · {len(kayitlar)} gonderi · {sayfa} sayfa")

if KURU:
    print(f"  KURU  yazilmadi ({len(kayitlar)} gonderi okundu)")
    sys.exit(3 if eksik_sayfa else 0)

# --- yaz ---------------------------------------------------------------------
# 🔴 Tek psql oturumunda temp tablo + upsert. COPY yerine satir satir INSERT
#    kullanilmiyor: 500 satira kadar tek ifade yeterli ve caption'daki
#    tirnak/satir sonu dert olmasin diye her deger jsonb icinden cikariliyor.
satirlar = []
for r in kayitlar:
    satirlar.append(json.dumps({
        "medya_id": r.get("id"),
        "ig_user_id": IG_USER,
        "tur": r.get("media_type"),
        "urun_tipi": r.get("media_product_type"),
        "metin": r.get("caption") or "",
        "zaman": r.get("timestamp"),
        "begeni": r.get("like_count"),
        "yorum": r.get("comments_count"),
        "baglanti": r.get("permalink"),
        "kucuk_gorsel": r.get("thumbnail_url"),
        "ham": r,
    }, ensure_ascii=False))

govde = ",".join("(" + "'" + s.replace("'", "''") + "'::jsonb)" for s in satirlar)
sql = f"""
BEGIN;
CREATE TEMP TABLE gecici_ig (j jsonb) ON COMMIT DROP;
INSERT INTO gecici_ig (j) VALUES {govde};
INSERT INTO raw.ig_medya
  (medya_id, ig_user_id, tur, urun_tipi, metin, zaman, begeni, yorum,
   baglanti, kucuk_gorsel, ham, cekim_at)
SELECT j->>'medya_id', j->>'ig_user_id', j->>'tur', j->>'urun_tipi',
       j->>'metin', (j->>'zaman')::timestamptz,
       nullif(j->>'begeni','')::bigint, nullif(j->>'yorum','')::bigint,
       j->>'baglanti', j->>'kucuk_gorsel', j->'ham', now()
  FROM gecici_ig
ON CONFLICT (medya_id) DO UPDATE SET
  tur=EXCLUDED.tur, urun_tipi=EXCLUDED.urun_tipi, metin=EXCLUDED.metin,
  zaman=EXCLUDED.zaman, begeni=EXCLUDED.begeni, yorum=EXCLUDED.yorum,
  baglanti=EXCLUDED.baglanti, kucuk_gorsel=EXCLUDED.kucuk_gorsel,
  ham=EXCLUDED.ham, cekim_at=now();
SELECT count(*) FROM raw.ig_medya;
COMMIT;
"""
try:
    cikti = psql(sql)
except RuntimeError as hata:
    print(f"HATA: yazilamadi: {hata}", file=sys.stderr)
    sys.exit(1)

# 🔴 SON SATIRI ALMA: psql cikisinda en son 'COMMIT' duruyor ve sayac yerine
#    onu yazdirmistik. Sayi olan SON satiri al.
toplam = next((s for s in reversed(cikti.strip().splitlines()) if s.strip().isdigit()), "?")
durum = "partial" if eksik_sayfa else "ok"
print(f"  {durum}    ig-organik  {len(kayitlar)} gonderi yazildi | tabloda {toplam}")
sys.exit(3 if eksik_sayfa else 0)
