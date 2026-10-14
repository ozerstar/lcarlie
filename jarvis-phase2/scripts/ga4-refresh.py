#!/usr/bin/env python3
# =============================================================================
# L'CARLIE — GA4 ETL  (dönüşüm ölçümünün eksik halkası)
#
# NEDEN VAR
# Site GA4'e veri gönderiyor (G-KCPFLRG2RV) ama veritabanına hiç
# çekilmiyordu: raw.yukleme_log'da ga4 kaydı yoktu. raw.ga4_event şeması
# ve mart.ga4_siparis_mutabakat görünümü hazırdı, veri yoktu.
#
# 🔴 SIR KOMUT SATIRINA YAZILMAZ. Servis hesabı JSON'u dosyadan okunur,
#    hiçbir yerde print edilmez, DB'ye yazılmaz. (meta-reklam-yukle.py
#    ile aynı kural.)
#
# 🔴 BU BİR TOPLU (AGGREGATED) ÇEKİMDİR, HAM OLAY DEĞİL.
#    GA4 Data API ham olay satırı vermez; boyut+metrik kırılımı verir.
#    raw.ga4_event satırları bu yüzden "bir günün bir kırılımı"dır ve
#    kanit_durumu='GA4_AGGREGATE' ile işaretlenir. Ham olay istenirse
#    BigQuery export gerekir (ayrı GCP projesi, ayrı karar).
#
# İKİ RAPOR ÇEKİLİR
#   1. Huni    : date × eventName -> eventCount
#                (page_view, view_item, add_to_cart, begin_checkout, purchase)
#   2. Satın alma: date × transactionId × source/medium/campaign
#                -> purchaseRevenue, transactions
#      transactionId, Wix sipariş numarasıyla eşleşecek olan alandır;
#      mart.ga4_siparis_mutabakat tam bunu bekliyor.
#
# Cikis: 0=SUCCESS 1=FAILED 2=NO_DATA 3=PARTIAL
# =============================================================================
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jarvis.data_completion import ga4_replace_sql

KURU = "--kuru" in sys.argv
GUN = int(os.environ.get("GA4_GUN", "60"))
KAP = os.environ.get("LCARLIE_KAP", "lcarlie-postgres")
ANAHTAR = os.environ.get("GA4_KEY_FILE", "/etc/lcarlie/ga4.json")
AYAR = os.environ.get("GA4_ENV_FILE", "/etc/lcarlie/ga4.env")


def env(k):
    """Once ayar dosyasi, sonra ortam. Sir komut satirina hic girmez."""
    for yol in (AYAR, "/opt/lcarlie/n8n/.env"):
        try:
            with open(yol, encoding="utf-8") as f:
                for s in f:
                    if s.startswith(k + "="):
                        return s.split("=", 1)[1].strip()
        except OSError:
            pass
    return os.environ.get(k)


def psql(sql, girdi=None):
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        input=girdi, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout.strip()


def _q(s):
    return "'" + str(s).replace("'", "''") + "'"


def _dq(s):
    """Dolar-tirnak: buyuk JSON'u guvenle SQL'e gomer."""
    tag, i = "j0", 0
    while ("$%s$" % tag) in s:
        i += 1
        tag = "j%d" % i
    return "$%s$%s$%s$" % (tag, s, tag)


def log_yaz(durum, okunan, yazilan, mesaj):
    # Mesajda sir ASLA olmaz.
    psql("INSERT INTO raw.yukleme_log (kaynak,durum,okunan,yazilan,"
         "guncellenen,mesaj,baslangic,bitis) VALUES "
         "('ga4',%s,%d,%d,0,%s,now(),now())"
         % (_q(durum), okunan, yazilan, _q(mesaj[:400])))


# ----------------------------------------------------------------- kimlik
def erisim_jetonu(sa):
    """Servis hesabi JWT'sini access token'a cevirir.

    Google'in standart iki adimi: RS256 imzali JWT uret, token ucunda
    degis. Kutuphane olarak PyJWT + cryptography kullanilir (ikisi de
    sistem python'unda mevcut, olculdu).
    """
    import jwt as pyjwt
    import requests

    simdi = int(time.time())
    iddia = {
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/analytics.readonly",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": simdi,
        "exp": simdi + 3600,
    }
    imzali = pyjwt.encode(iddia, sa["private_key"], algorithm="RS256")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": imzali,
    })
    if r.status_code != 200:
        # Google'in hata metni jeton icermez; yine de kisaltilir.
        raise RuntimeError("token alinamadi HTTP %d: %s"
                           % (r.status_code, r.text[:200]))
    return r.json()["access_token"]


def rapor(jeton, pid, boyutlar, metrikler, bas, bit):
    import requests
    r = requests.post(
        "https://analyticsdata.googleapis.com/v1beta/properties/%s:runReport" % pid,
        timeout=60,
        headers={"Authorization": "Bearer " + jeton,
                 "Content-Type": "application/json"},
        json={
            "dateRanges": [{"startDate": bas, "endDate": bit}],
            "dimensions": [{"name": d} for d in boyutlar],
            "metrics": [{"name": m} for m in metrikler],
            "limit": 100000,
        })
    if r.status_code != 200:
        raise RuntimeError("runReport HTTP %d: %s" % (r.status_code, r.text[:250]))
    j = r.json()
    if int(j.get("rowCount", 0)) > len(j.get("rows", [])):
        raise RuntimeError("GA4 report truncated; snapshot retained")
    basliklar = [d["name"] for d in j.get("dimensionHeaders", [])] + \
                [m["name"] for m in j.get("metricHeaders", [])]
    satirlar = []
    for s in j.get("rows", []):
        degerler = [d.get("value") for d in s.get("dimensionValues", [])] + \
                   [m.get("value") for m in s.get("metricValues", [])]
        satirlar.append(dict(zip(basliklar, degerler, strict=True)))
    return satirlar


# ------------------------------------------------------------------- ana
def main():
    pid = env("GA4_PROPERTY_ID")
    if not pid:
        print("HATA: GA4_PROPERTY_ID yok (%s icinde beklenir)" % AYAR,
              file=sys.stderr)
        return 1
    try:
        with open(ANAHTAR, encoding="utf-8") as f:
            sa = json.load(f)
    except OSError as e:
        print("HATA: servis hesabi okunamadi (%s): %s" % (ANAHTAR, e.strerror),
              file=sys.stderr)
        return 1
    for alan in ("client_email", "private_key"):
        if alan not in sa:
            print("HATA: servis hesabi JSON'unda %s yok" % alan, file=sys.stderr)
            return 1

    bit = datetime.date.today()
    bas = bit - datetime.timedelta(days=GUN)
    b, e = bas.isoformat(), bit.isoformat()

    try:
        jeton = erisim_jetonu(sa)
    except Exception as exc:                                  # noqa: BLE001
        print("HATA: %s" % exc, file=sys.stderr)
        if not KURU:
            log_yaz("FAILED", 0, 0, "kimlik: %s" % exc)
        return 1

    okunan = yazilan = 0
    hata = []

    # --- 1. HUNI: gun x olay
    try:
        huni = rapor(jeton, pid, ["date", "eventName"], ["eventCount"], b, e)
        okunan += len(huni)
    except Exception as exc:                                  # noqa: BLE001
        huni = []
        hata.append("huni: %s" % exc)

    # --- 2. SATIN ALMA: gun x islem x kaynak
    try:
        alim = rapor(jeton, pid,
                     ["date", "transactionId", "sessionSource",
                      "sessionMedium", "sessionCampaignName"],
                     ["purchaseRevenue", "transactions"], b, e)
        okunan += len(alim)
    except Exception as exc:                                  # noqa: BLE001
        alim = []
        hata.append("satin alma: %s" % exc)

    if not okunan:
        mesaj = "; ".join(hata) or "GA4 bu aralikta satir dondurmedi"
        print("VERI YOK: %s" % mesaj)
        if not KURU:
            log_yaz("NO_DATA", 0, 0, mesaj)
        return 2

    if KURU:
        print("KURU CALISMA -- hicbir sey yazilmadi")
        print("  huni satiri      : %d" % len(huni))
        print("  satin alma satiri: %d" % len(alim))
        if hata:
            print("  HATALAR: %s" % "; ".join(hata))
        return 0

    if hata:
        log_yaz("PARTIAL", okunan, 0, "Snapshot retained; a GA4 report failed")
        print("PARTIAL: previous snapshot retained")
        return 3
    sql, yazilan = ga4_replace_sql(huni, alim, b, e)
    psql(sql)
    print("SUCCESS: %d read, %d staged in atomic snapshot" % (okunan, yazilan))
    return 0



if __name__ == "__main__":
    sys.exit(main())
