#!/usr/bin/env python3
# =============================================================================
# L'CARLIE - KIMLIK MANTIGI DOGRULAMASI  (CR-003 madde 5)
#
# 🔴 KALICI YAZMA YOK. Gercek Wix musteri verisi yalnizca TEK BIR PSQL
#    OTURUMUNDAKI gecici tabloya yuklenir, siniflandirma orada calisir,
#    oturum bitince veri kaybolur. core.customer bu asamada BOS kalir -
#    tam ETL CR-004'un isi.
#
# 🔴 PII EKRANA/LOGA BASILMAZ. Yalnizca sayimlar ve MASKELI ornekler.
#
# 🔴 "0 satir = SUCCESS" DEGIL. Her kontrol SUCCESS / NO_DATA / PARTIAL /
#    FAILED dondurur.
# =============================================================================
import json, subprocess, re, sys, collections

ENV = "/opt/lcarlie/n8n/.env"
PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
        "-v", "ON_ERROR_STOP=1", "-tA", "-F", "|"]

def env(k):
    t = open(ENV).read()
    m = re.search(r"^" + k + r"=(.*)$", t, re.M)
    return m.group(1).strip() if m else ""

def wix_orders():
    r = subprocess.run(["curl", "-s", "--max-time", "40", "-X", "POST",
        "https://www.wixapis.com/stores/v2/orders/query",
        "-H", "Authorization: " + env("WIX_API_KEY"),
        "-H", "wix-site-id: " + env("WIX_SITE_ID"),
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"query": {"paging": {"limit": 100}}})],
        capture_output=True, text=True)
    if r.returncode != 0:
        return None, "curl basarisiz"
    try:
        return json.loads(r.stdout).get("orders") or [], None
    except Exception as e:
        return None, "JSON ayristirilamadi: %s" % e

def sql(script):
    p = subprocess.run(PSQL, input=script, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def maske(v):
    """PII maskele: son 4 hane / e-postanin ilk harfi."""
    if not v: return "(bos)"
    if "@" in v:
        a, b = v.split("@", 1); return a[:1] + "***@" + b
    return "***" + v[-4:] if len(v) > 4 else "***"

sonuclar = []
def kontrol(ad, durum, detay=""):
    sonuclar.append((ad, durum, detay))
    isaret = {"SUCCESS": "ok  ", "NO_DATA": "veri", "PARTIAL": "kismi", "FAILED": "HATA"}[durum]
    print("  %-5s %-52s %s" % (isaret, ad, detay))

print("\n=== 1) KAYNAK VERI ===")
ords, hata = wix_orders()
if ords is None:
    # 🔴 Kaynaga ERISILEMEDI -> NO_DATA degil FAILED.
    kontrol("Wix siparis verisi alindi", "FAILED", hata)
    sys.exit(1)
if len(ords) == 0:
    kontrol("Wix siparis verisi alindi", "NO_DATA", "kaynak erisildi, kayit yok")
    sys.exit(1)
kontrol("Wix siparis verisi alindi", "SUCCESS", "%d siparis" % len(ords))

# --- Alicilari cikar ---------------------------------------------------------
alicilar = {}   # buyer_id -> (telefon_ham, eposta_ham)
for o in ords:
    b = o.get("buyerInfo") or {}
    bid = b.get("id")
    if not bid: continue
    alicilar.setdefault(bid, (b.get("phone"), b.get("email")))

tel_ham = [v[0] for v in alicilar.values() if v[0]]
eps_ham = [v[1] for v in alicilar.values() if v[1]]
print("     tekil alici=%d  telefon=%d  eposta=%d" % (len(alicilar), len(tel_ham), len(eps_ham)))

# =============================================================================
print("\n=== 2) NORMALIZASYON (gecici tablo, kalici yazma YOK) ===")
# =============================================================================
satirlar = []
for bid, (t, e) in alicilar.items():
    satirlar.append("(%s,%s,%s)" % (
        "'" + bid.replace("'", "''") + "'",
        "NULL" if not t else "'" + t.replace("'", "''") + "'",
        "NULL" if not e else "'" + e.replace("'", "''") + "'"))

script = """
BEGIN;
CREATE TEMP TABLE gecici_alici(buyer_id text, tel_ham text, eps_ham text) ON COMMIT DROP;
INSERT INTO gecici_alici VALUES %s;

\\echo '--SAYIM--'
SELECT
  count(*),
  count(*) FILTER (WHERE tel_ham IS NOT NULL),
  count(*) FILTER (WHERE tel_ham IS NOT NULL AND core.telefon_e164(tel_ham) IS NOT NULL),
  count(*) FILTER (WHERE tel_ham IS NOT NULL AND core.telefon_e164(tel_ham) IS NULL),
  count(DISTINCT core.telefon_e164(tel_ham)) FILTER (WHERE core.telefon_e164(tel_ham) IS NOT NULL),
  count(*) FILTER (WHERE eps_ham IS NOT NULL AND core.eposta_normal(eps_ham) IS NOT NULL),
  count(DISTINCT core.eposta_normal(eps_ham)) FILTER (WHERE core.eposta_normal(eps_ham) IS NOT NULL)
FROM gecici_alici;

\\echo '--GECERSIZ--'
SELECT tel_ham, length(regexp_replace(tel_ham,'\\D','','g'))
FROM gecici_alici
WHERE tel_ham IS NOT NULL AND core.telefon_e164(tel_ham) IS NULL;

\\echo '--CAKISMA--'
SELECT core.telefon_e164(tel_ham), count(DISTINCT buyer_id), string_agg(DISTINCT left(buyer_id,8), ',')
FROM gecici_alici
WHERE core.telefon_e164(tel_ham) IS NOT NULL
GROUP BY 1 HAVING count(DISTINCT buyer_id) > 1;

\\echo '--EPOSTA-CAKISMA--'
SELECT core.eposta_normal(eps_ham), count(DISTINCT buyer_id)
FROM gecici_alici
WHERE core.eposta_normal(eps_ham) IS NOT NULL
GROUP BY 1 HAVING count(DISTINCT buyer_id) > 1;

\\echo '--BICIM--'
SELECT CASE
         WHEN tel_ham LIKE '+90%%' THEN 'E164 (+90...)'
         WHEN tel_ham LIKE '0%%'   THEN 'yerel 0XXX'
         WHEN tel_ham LIKE '90%%'  THEN '90XXX (artisiz)'
         ELSE 'diger' END, count(*)
FROM gecici_alici WHERE tel_ham IS NOT NULL GROUP BY 1 ORDER BY 2 DESC;
COMMIT;
""" % (",".join(satirlar))

rc, out, err = sql(script)
if rc != 0:
    kontrol("Normalizasyon sorgusu", "FAILED", err.split("\n")[0][:120]); sys.exit(1)

bloklar = {}
ad = None
for satir in out.split("\n"):
    if satir.startswith("--") and satir.endswith("--"):
        ad = satir.strip("-"); bloklar[ad] = []
    elif ad and satir.strip() and not satir.startswith(("BEGIN", "COMMIT", "CREATE", "INSERT")):
        bloklar[ad].append(satir)

s = (bloklar.get("SAYIM") or ["0|0|0|0|0|0|0"])[0].split("|")
alici, tel_var, tel_ok, tel_bad, tel_tekil, eps_ok, eps_tekil = [int(x) for x in s]

kontrol("Telefon normalizasyonu calisti", "SUCCESS" if tel_ok else "NO_DATA",
        "%d/%d gecerli, %d tekil E.164" % (tel_ok, tel_var, tel_tekil))
kontrol("E-posta normalizasyonu calisti", "SUCCESS" if eps_ok else "NO_DATA",
        "%d gecerli, %d tekil" % (eps_ok, eps_tekil))

print("\n     telefon bicim dagilimi:")
for b in bloklar.get("BICIM", []):
    p = b.split("|");  print("       %-20s %s" % (p[0], p[1]))

# =============================================================================
print("\n=== 3) SINIFLANDIRMA ===")
# =============================================================================
gecersizler = bloklar.get("GECERSIZ", [])
if gecersizler:
    for g in gecersizler:
        p = g.split("|")
        print("     INVALID: %s  (%s hane)" % (maske(p[0]), p[1]))
    kontrol("INVALID ayirt edildi", "SUCCESS", "%d gecersiz telefon, normalize EDILMEDI" % len(gecersizler))
else:
    kontrol("INVALID ayirt edildi", "NO_DATA", "gecersiz telefon bulunmadi")

cakismalar = bloklar.get("CAKISMA", [])
if cakismalar:
    for c in cakismalar:
        p = c.split("|")
        print("     CONFLICT: %s -> %s ayri buyer_id (%s)" % (maske(p[0]), p[1], p[2]))
    kontrol("CONFLICT tespit edildi", "SUCCESS", "%d telefon birden fazla aliciya bagli" % len(cakismalar))
else:
    kontrol("CONFLICT tespit edildi", "NO_DATA", "telefon cakismasi yok")

eps_cak = bloklar.get("EPOSTA-CAKISMA", [])
kontrol("E-posta cakismasi kontrolu", "SUCCESS" if not eps_cak else "PARTIAL",
        "cakisma yok" if not eps_cak else "%d e-posta cakismasi" % len(eps_cak))

matched = tel_tekil - len(cakismalar)
kontrol("MATCHED sayimi", "SUCCESS" if matched > 0 else "NO_DATA",
        "%d telefon tek aliciya baglaniyor" % matched)

eksik = len(alicilar) - tel_var
kontrol("UNKNOWN (telefonsuz alici)", "SUCCESS" if eksik >= 0 else "FAILED",
        "%d alicida telefon yok -> UNKNOWN" % eksik)

# =============================================================================
print("\n=== 4) BEKLENEN DEGERLERLE KARSILASTIRMA (CR-001 olcumu) ===")
# =============================================================================
beklenen = [
    ("tekil telefon (ham rakam)", None),
    ("gecersiz 9 haneli telefon", 1, len(gecersizler)),
    ("ayni telefon birden fazla aliciya bagli", 1, len(cakismalar)),
    ("farkli telefon bicimi sayisi", 3, len(bloklar.get("BICIM", []))),
]
for b in beklenen:
    if b[1] is None: continue
    ad_, bek, ger = b
    kontrol("CR-001 ile tutarli: %s" % ad_,
            "SUCCESS" if ger == bek else "PARTIAL",
            "beklenen=%s gercek=%s" % (bek, ger))

# =============================================================================
print("\n=== 5) KALICI TABLOLAR BOS MU (tam ETL CR-004) ===")
# =============================================================================
rc, out, err = sql("SELECT (SELECT count(*) FROM core.customer) || '|' || "
                   "(SELECT count(*) FROM core.customer_identity) || '|' || "
                   "(SELECT count(*) FROM core.identity_conflict);")
if rc == 0 and out:
    c, i, k = out.split("|")
    kontrol("core tablolari bu asamada bos", "SUCCESS" if c == "0" else "PARTIAL",
            "customer=%s identity=%s conflict=%s" % (c, i, k))
else:
    kontrol("core tablolari okunabildi", "FAILED", err[:100])

# --- Ozet --------------------------------------------------------------------
say = collections.Counter(d for _, d, _ in sonuclar)
print("\n" + "-" * 58)
print("SUCCESS=%d  NO_DATA=%d  PARTIAL=%d  FAILED=%d" %
      (say["SUCCESS"], say["NO_DATA"], say["PARTIAL"], say["FAILED"]))
print("-" * 58 + "\n")
sys.exit(1 if say["FAILED"] else 0)
