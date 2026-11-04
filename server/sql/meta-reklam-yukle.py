#!/usr/bin/env python3
# =============================================================================
# L'CARLIE - META AD-LEVEL + CREATIVE ETL  (CR-016 corrective patch)
#
# 🔴 KAMPANYA ETL'INE DOKUNMAZ. meta-harcama-yukle.py oldugu gibi calisir;
#    bu betik onun YANINA ad/creative seviyesini ceker.
#
# 🔴 JETON: META_ADS_TOKEN.  META_SYSTEM_TOKEN reklam icin KULLANILMAZ
#    (core.jeton_otorite'de yazili; CR-016'da bu hata yapildi).
#
# 🔴 SECRET KOMUT SATIRINA YAZILMAZ - requests ile header'da gider,
#    hicbir yerde print edilmez, DB'ye yazilmaz.
#
# Cikis: 0=SUCCESS 1=FAILED 2=NO_DATA 3=PARTIAL
# =============================================================================
import os, sys, json, datetime, urllib.parse, urllib.request, subprocess

G = "https://graph.facebook.com/v21.0"
GUN = int(os.environ.get("META_GUN", "30"))
KURU = "--kuru" in sys.argv
KAP = os.environ.get("LCARLIE_KAP", "lcarlie-postgres")

def env(k):
    try:
        with open("/opt/lcarlie/n8n/.env", encoding="utf-8") as f:
            for s in f:
                if s.startswith(k + "="):
                    return s.split("=", 1)[1].strip()
    except OSError:
        pass
    return os.environ.get(k)

JETON = env("META_ADS_TOKEN")
if not JETON:
    print("HATA: META_ADS_TOKEN yok", file=sys.stderr); sys.exit(1)

def psql(sql, girdi=None):
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        input=girdi, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout.strip()

def _dq(s):
    """Dolar-tirnak: buyuk JSON'u guvenle SQL'e gomer. Etiket cakismasi
    olmasin diye icerikte gecmeyen bir etiket secilir."""
    tag = "j0"
    i = 0
    while ("$%s$" % tag) in s:
        i += 1; tag = "j%d" % i
    return "$%s$%s$%s$" % (tag, s, tag)

def psql_dosya(sql):
    """Buyuk SQL'i stdin'den gonderir (-f -): argv sinirina takilmaz."""
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1", "-tA", "-f", "-"],
        input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout.strip()

def cek(yol, params):
    """Sayfalama ile tum satirlari toplar. Hata olursa (None, mesaj) doner."""
    out, url = [], "%s/%s?%s" % (G, yol, urllib.parse.urlencode(params))
    while url:
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer %s" % JETON)   # 🔴 argv'de degil
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
        except Exception as e:
            govde = ""
            if hasattr(e, "read"):
                try: govde = json.loads(e.read().decode()).get("error", {}).get("message", "")
                except Exception: pass
            return None, (govde or str(e))[:160]
        if "error" in d:
            return None, str(d["error"].get("message"))[:160]
        out.extend(d.get("data", []))
        url = (d.get("paging") or {}).get("next")
    return out, None

def bildir(kaynak, durum, mesaj, okunan=0, yazilan=0):
    # 🔴 Mesajda jeton/secret ASLA olmaz.
    # 🔴 raw.log_yaz() fonksiyonu YOK (varsayilmisti, hata verdi);
    #    dogrudan raw.yukleme_log tablosuna yazilir.
    psql("INSERT INTO raw.yukleme_log (kaynak,durum,okunan,yazilan,guncellenen,"
         "mesaj,baslangic,bitis) VALUES (%s,%s,%d,%d,0,%s,now(),now())"
         % (_q(kaynak), _q(durum), okunan, yazilan, _q(mesaj)))

def _q(s):
    return "'" + str(s).replace("'", "''") + "'"

# --- Hangi hesaplar? ---------------------------------------------------------
# 🔴 me/adaccounts CALISMIYOR (business_management yok). Bu yuzden hesap
#    listesi DB'den okunur; kesif yapilamaz, bilinen ID sorgulanir.
hesaplar = [h for h in psql("SELECT hesap_id FROM raw.meta_hesap;").splitlines() if h]
if not hesaplar:
    print("HATA: raw.meta_hesap bos"); sys.exit(1)

bas = datetime.date.today() - datetime.timedelta(days=GUN)
bit = datetime.date.today()
zaman = json.dumps({"since": bas.isoformat(), "until": bit.isoformat()})

ALANLAR = ("account_id,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
           "spend,impressions,reach,clicks,inline_link_clicks,ctr,cpc,cpm,frequency,"
           "actions,action_values")

toplam_ad = toplam_kr = 0
kismi = []
for hid in hesaplar:
    # --- 1) Ad-level gunluk performans ---
    satir, hata = cek("act_%s/insights" % hid, {
        "level": "ad", "fields": ALANLAR, "time_increment": "1",
        "time_range": zaman, "limit": "500"})
    if satir is None:
        kismi.append("%s: %s" % (hid, hata))
        continue
    if KURU:
        print("  KURU act_%s -> %d ad satiri" % (hid, len(satir)))
    else:
        # 🔴 TOPLU YAZIM.  Satir basina bir `docker exec` 291 ayri surec
        #    demekti. COPY FROM STDIN ise `-c` ile calismiyor
        #    ("unexpected COPY_IN result"). Cozum: JSON DIZISI tek sorguda,
        #    stdin'den (-f -) gonderilir; argv uzunluk siniri da asilmaz.
        psql_dosya("SELECT count(raw.meta_reklam_yaz(j, %s)) "
                   "FROM jsonb_array_elements(%s::jsonb) j;"
                   % (_q(hid), _dq(json.dumps(satir))))
        toplam_ad += len(satir)

    # --- 2) Kreatif metadatasi ---
    kr, hata2 = cek("act_%s/ads" % hid, {
        "fields": ("id,name,status,effective_status,created_time,updated_time,"
                   "adset_id,campaign_id,"
                   "creative{id,name,status,title,body,call_to_action_type,"
                   # 🔴 object_story_spec / asset_feed_spec OLMADAN reklamin
                   #    NEREYE gittigi hicbir yerde kayitli olmuyor.
                   #    02.10.2026: K+01 reklaminin hedefi ancak elle
                   #    sorularak bulundu -- bir daha olmasin.
                   "object_type,thumbnail_url,video_id,url_tags,"
                   "object_story_spec,asset_feed_spec}"),
        "limit": "200"})
    if kr is None:
        kismi.append("%s kreatif: %s" % (hid, hata2))
        continue
    if not KURU:
        psql_dosya("SELECT count(raw.meta_kreatif_yaz(j)) "
                   "FROM jsonb_array_elements(%s::jsonb) j;" % _dq(json.dumps(kr)))
        toplam_kr += len(kr)

# --- Durum ------------------------------------------------------------------
# 🔴 KAPSAMA HER ZAMAN YAZILIR: 1/3 hesap okunuyorsa sonuc PARTIAL'dir,
#    veri gelmis olsa bile SUCCESS DEGIL.
kapsama = "%d/3 hesap" % len(hesaplar)
if toplam_ad == 0 and not KURU:
    durum, kod = "NO_DATA", 2
elif kismi or len(hesaplar) < 3:
    durum, kod = "PARTIAL", 3
else:
    durum, kod = "SUCCESS", 0

mesaj = "son %d gun | ad satiri=%d kreatif=%d | kapsama=%s" % (GUN, toplam_ad, toplam_kr, kapsama)
if kismi:
    mesaj += " | eksik: " + "; ".join(kismi)[:200]
if not KURU:
    bildir("meta_reklam_ad", durum, mesaj, toplam_ad, toplam_ad)
print("  %-6s meta ad-level   %s" % (durum.lower(), mesaj))
sys.exit(kod)
