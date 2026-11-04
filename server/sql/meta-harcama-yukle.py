#!/usr/bin/env python3
# =============================================================================
# L'CARLIE - META REKLAM HARCAMASI YUKLEYICI  (CR-005)
#
# 🔴 GERIYE DONUK PENCERE.  Meta rakamlari gecmise donuk degisir (gec
#    raporlanan gosterim, atif penceresi, fatura duzeltmesi). Bu yuzden
#    her calismada SON 28 GUN yeniden cekilir ve uzerine yazilir.
#    "Sadece dunu cek" yaklasimi, duzeltilen rakamlari sonsuza dek
#    yanlis birakir.
#
# 🔴 KAYNAGA ERISILEMEDI = FAILED.  "0 satir dondu" ise NO_DATA. Ikisi
#    asla ayni sayilmaz. Izin eksikse (#200) bu FAILED'dir - reklam
#    harcamasi yok demek DEGILDIR.
#
# 🔴 HESAP KIMLIGI SABIT DEGIL.  Uc reklam hesabi var ve varsayilan
#    acilan YANLIS olani (13.09 dersi). Hangi hesaplarin okunacagi
#    me/adaccounts'tan gelir; liste alinamazsa ELDE BILINEN kodlarla
#    dogrudan denenir ve bu durum raporlanir.
#
# Kullanim: python3 meta-harcama-yukle.py [--kuru] [--gun N] [--tam]
#           --kuru : yazmaz, yalniz raporlar
#           --gun N: son N gun (varsayilan 28)
#           --tam  : hesabin tum gecmisi (ilk calistirmada bir kez)
# =============================================================================
import json, subprocess, sys, re, datetime, collections

ENV = "/opt/lcarlie/n8n/.env"
KAP = "lcarlie-postgres"
G   = "https://graph.facebook.com/v21.0"

# 🔴 Hafizadaki uc hesap. me/adaccounts calismazsa yedek olarak kullanilir.
#    Dogrudan denenir cunku liste ucunun izni ayri olabiliyor.
# Hesap listesinin KAYNAGI core.meta_hesap_kayit'tir, bu satir degil.
# Onceki hali kodda sabitti ve tabloyla IKI AYRI GERCEK KOPYASI olusturuyordu;
# bu projede ayni kalip (jarvis firewall'un kendi izin listesi ile
# core.ai_action_type) bir kez kaymisti. Tabloya ulasilamazsa asagidaki liste
# yalnizca YEDEK olarak kullanilir -- boylece veritabani kapaliyken de cekim
# yapilir, ama normal halde tek kaynak tablodur.
YEDEK_HESAPLAR = ["1301171572214198", "560782561026922", "1601342818221781"]


def _kayit_defteri():
    """{hesap_id: operasyonel_durum}. Okunamazsa bos sozluk (yedege duser)."""
    rc, out, _err = psql(
        "SELECT hesap_id, operasyonel_durum FROM core.meta_hesap_kayit;", tA=True)
    if rc != 0 or not out:
        return {}
    defter = {}
    for satir in out.split("\n"):
        if "|" not in satir:
            continue
        hid, _, durum = satir.partition("|")
        defter[hid.strip()] = durum.strip()
    return defter



ALANLAR = ("date_start,date_stop,campaign_id,campaign_name,spend,impressions,"
           "reach,clicks,inline_link_clicks,cpm,cpc,ctr,frequency,"
           "account_currency,actions,action_values")

# 🔴 'business{name}' ISTENMEZ.  O alan business_management izni ister;
#    jetonumuzda bilerek YALNIZ ads_read var. Alani istemek TUM cagriyi
#    (#100) ile dusurur - yani portfolyo adi ugruna harcama verisini
#    kaybederiz. raw.meta_hesap.portfolyo bu yuzden NULL kalir.
ALANLAR_HESAP = "id,account_id,name,account_status,currency"

KURU = "--kuru" in sys.argv
TAM  = "--tam"  in sys.argv
GUN  = 28
if "--gun" in sys.argv:
    try: GUN = int(sys.argv[sys.argv.index("--gun") + 1])
    except Exception: pass

def env(k):
    try: t = open(ENV).read()
    except Exception: return ""
    m = re.search(r"^" + re.escape(k) + r"=(.*)$", t, re.M)
    return m.group(1).strip() if m else ""

JETON = env("META_ADS_TOKEN")

def psql(script, tA=False):
    cmd = ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
           "-v", "ON_ERROR_STOP=1"]
    if tA: cmd += ["-tA", "-F", "|"]
    p = subprocess.run(cmd, input=script, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def _kacir(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')

def curl_config(url, parametreler=None):
    """🔴 JETON KOMUT SATIRINA YAZILMAZ.  Komut satiri argumanlari sunucudaki
       her kullaniciya 'ps' ile gorunur; jeton oraya konursa sizar. curl'un
       -K secenegi yapilandirmayi STDIN'den okur, orada gorunmez.
       Ayrica her parametre AYRI --data-urlencode olmali: hepsini tek
       parcada kodlamak '=' ve '&' karakterlerini de kodlar ve istegi bozar."""
    satirlar = ['--silent', '--show-error', '--max-time 90', '--get',
                'url = "%s"' % _kacir(url),
                'header = "Authorization: Bearer %s"' % _kacir(JETON)]
    for k, v in (parametreler or {}).items():
        satirlar.append('data-urlencode = "%s=%s"' % (_kacir(k), _kacir(v)))
    return "\n".join(satirlar) + "\n"

def curl_calistir(yapilandirma):
    r = subprocess.run(["curl", "-K", "-"], input=yapilandirma,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, "curl rc=%d %s" % (r.returncode, (r.stderr or "").strip()[:100])
    try:
        return json.loads(r.stdout), None
    except Exception as e:
        return None, "JSON ayristirilamadi: %s" % e

def graph(yol, parametreler):
    """(veri, hata) doner. hata None degilse ERISILEMEDI demektir."""
    d, h = curl_calistir(curl_config("%s/%s" % (G, yol), parametreler))
    if h: return None, h
    if isinstance(d, dict) and "error" in d:
        e = d["error"]
        return None, "Graph %s: %s" % (e.get("code"), (e.get("message") or "")[:150])
    return d, None

def sayfalari_topla(yol, parametreler):
    """Graph sayfalamasini sonuna kadar takip eder."""
    hepsi, d, h = [], None, None
    d, h = graph(yol, parametreler)
    if h: return None, h
    while True:
        hepsi.extend(d.get("data") or [])
        sonraki = (d.get("paging") or {}).get("next")
        if not sonraki or len(hepsi) > 20000: break
        # Sonraki sayfanin URL'si jetonu ICINDE tasir - yine stdin uzerinden.
        d, e = curl_calistir(curl_config(sonraki))
        if e: return hepsi, "sayfalama kesildi: %s" % e
        if "error" in d:
            return hepsi, "sayfalama kesildi: %s" % (d["error"].get("message") or "")[:120]
    return hepsi, None

def stage_yaz(kayitlar, cagri):
    """JSON satirlarini gecici tabloya COPY edip cikarma fonksiyonunu calistirir."""
    if not kayitlar: return 0, 0, None
    satirlar = [json.dumps(o, ensure_ascii=False).replace("\\", "\\\\") for o in kayitlar]
    script = ("BEGIN;\n"
              "CREATE TEMP TABLE _stage(j jsonb) ON COMMIT DROP;\n"
              "COPY _stage(j) FROM STDIN;\n"
              + "\n".join(satirlar) + "\n\\.\n"
              "\\echo '--SONUC--'\n"
              "SELECT sonuc, count(*) FROM (SELECT " + cagri + " AS sonuc FROM _stage) x GROUP BY 1;\n"
              "COMMIT;\n")
    rc, out, err = psql(script, tA=True)
    if rc != 0:
        return 0, 0, (err.split("\n")[0][:200] if err else "psql rc=%d" % rc)
    say, blok = {"INSERT": 0, "UPDATE": 0}, False
    for s in out.split("\n"):
        if s.strip() == "--SONUC--": blok = True; continue
        if not blok: continue
        p = s.split("|")
        if len(p) == 2 and p[0].strip() in say: say[p[0].strip()] = int(p[1])
    return say["INSERT"], say["UPDATE"], None

def log_yaz(kaynak, durum, okunan, yazilan, guncellenen, mesaj, baslangic):
    if KURU: return
    # 🔴 ONCE KIRP, SONRA KAC.  Tersi yapilinca 900. karakter iki tirnagin
    #    ortasina denk gelebilir, dizge kapanmaz ve gunluk satiri yazilamaz -
    #    tam da "kayit yok" ile "kaydedemedik" ayrimini tutan tablo.
    m = (mesaj or "")[:900].replace("'", "''")
    rc, _, err = psql(
        "INSERT INTO raw.yukleme_log (kaynak,durum,okunan,yazilan,guncellenen,mesaj,baslangic) "
        "VALUES ('%s','%s',%s,%s,%s,'%s','%s');" %
        (kaynak, durum,
         "NULL" if okunan is None else okunan,
         "NULL" if yazilan is None else yazilan,
         "NULL" if guncellenen is None else guncellenen,
         m, baslangic.isoformat()))
    if rc != 0:
        print("  HATA  yukleme_log yazilamadi: %s" % err.split("\n")[0][:150])
        sonuclar.append("FAILED")

sonuclar = []
def bildir(ad, durum, detay):
    sonuclar.append(durum)
    isaret = {"SUCCESS": "ok   ", "NO_DATA": "veri ", "PARTIAL": "kismi", "FAILED": "HATA "}[durum]
    print("  %s %-16s %s" % (isaret, ad, detay))

# =============================================================================
print("\n=== META REKLAM HARCAMASI %s ===" % ("(KURU - YAZILMAZ)" if KURU else ""))
t0 = datetime.datetime.now(datetime.timezone.utc)

if not JETON:
    # 🔴 Jeton yoksa bu bir YAPILANDIRMA HATASIDIR, "veri yok" degil.
    bildir("jeton", "FAILED", "META_ADS_TOKEN .env'de yok")
    log_yaz("meta_reklam", "FAILED", None, 0, 0, "META_ADS_TOKEN tanimli degil", t0)
    print("\nSUCCESS=0  NO_DATA=0  PARTIAL=0  FAILED=1\n")
    sys.exit(1)

# --- 1) Hesaplar -------------------------------------------------------------
# Kayit defteri BURADA okunur: _kayit_defteri() psql()'i cagiriyor ve
# psql yukarida tanimlaniyor. Dosyanin basinda okunsaydi calisma
# aninda NameError verirdi -- py_compile bunu gostermez.
KAYIT = _kayit_defteri()
BILINEN_HESAPLAR = sorted(KAYIT) if KAYIT else list(YEDEK_HESAPLAR)
# Reklam YAYINLAMADIGI kayitli hesap: okunamamasi BEKLENEN durumdur.
BEKLENEN_ERISILMEZ = {h for h, d in KAYIT.items() if d == "INACTIVE_EXCLUDED"}

hesaplar, erisilemeyen, liste_notu = [], [], ""
beklenen_bos = []   # kayitli INACTIVE_EXCLUDED hesaplar
d, h = graph("me/adaccounts", {"fields": ALANLAR_HESAP, "limit": "50"})
if h:
    # 🔴 me/adaccounts business_management ister; jetonda YOK. Bu bir ariza
    #    DEGIL, bilincli bir dar yetki secimi. Hesaplara DOGRUDAN erisilir.
    liste_notu = "me/adaccounts yok (%s) - bilinen kodlarla dogrudan" % h[:60]
else:
    hesaplar = d.get("data") or []
    liste_notu = "me/adaccounts ile %d hesap" % len(hesaplar)

# 🔴 LISTE BASARILI DONSE BILE EKSIK OLABILIR (16.09 denetiminde bulundu).
#    Onceki hali BILINEN_HESAPLAR'a yalnizca me/adaccounts BASARISIZ olursa
#    bakiyordu. Liste basarili ama EKSIK donunce (bugunku durum: 3 hesaptan
#    1'i) digerleri hic denenmiyor, "erisilemeyen" bos kaliyor ve durum
#    SUCCESS oluyordu. Sonuc: panel karma ROAS'i EKSIK HARCAMAYLA uretiyor,
#    yani ROAS oldugundan YUKSEK gorunuyordu. Reklam verimliligi konusunda
#    iyimser yanilmak, en pahali yanilma turudur.
#    Artik bilinen kodlarla KUME FARKI aliniyor ve eksik olan her hesap
#    ayrica deneniyor; yine erisilemiyorsa durum PARTIAL.
_var = {str(a.get("account_id") or re.sub(r"^act_", "", a.get("id", ""))) for a in hesaplar}
for a in BILINEN_HESAPLAR:
    if a in _var:
        continue
    d2, h2 = graph("act_" + a, {"fields": ALANLAR_HESAP})
    if d2 and not h2:
        hesaplar.append(d2)
    elif a in BEKLENEN_ERISILMEZ:
        # Kayit defterinde INACTIVE_EXCLUDED: reklam yayinlamiyor, okunacak
        # harcama YOK. Yazilir ama ARIZA SAYILMAZ.
        beklenen_bos.append(a)
    else:
        erisilemeyen.append("%s (%s)" % (a, (h2 or "bos yanit")[:50]))

if not hesaplar:
    bildir("reklam hesabi", "FAILED", "hicbir hesaba erisilemedi | %s" % liste_notu)
    log_yaz("meta_reklam", "FAILED", 0, 0, 0, liste_notu, t0)
    print("\nSUCCESS=0  NO_DATA=0  PARTIAL=0  FAILED=1\n")
    sys.exit(1)

if not KURU:
    y, g, hh = stage_yaz(hesaplar, "raw.meta_hesap_yaz(j)")
    if hh: bildir("reklam hesabi", "FAILED", "yazma hatasi: %s" % hh)
    else:  bildir("reklam hesabi", "SUCCESS", "%d hesap (yeni=%d guncel=%d) | %s" % (len(hesaplar), y, g, liste_notu))
else:
    bildir("reklam hesabi", "SUCCESS", "%d hesap | %s" % (len(hesaplar), liste_notu))

for a in hesaplar:
    print("       %-20s %-28s durum=%s %s" % (
        str(a.get("account_id") or a.get("id")), (a.get("name") or "")[:28],
        a.get("account_status"), a.get("currency") or ""))
# 🔴 Erisilemeyen hesaplar SESSIZ GECILMEZ. Uc reklam hesabi var; hangisinin
#    okunmadigi yazili olmazsa "harcamamiz bu kadar" yanilgisi dogar.
for e in erisilemeyen:
    print("       ATLANDI %s" % e)
# Beklenen bosluk da GORUNUR yazilir -- sessiz gecmek, kapsamanin neden
# 1/3 oldugunu okuyanin bilememesi demekti. Alarm uretmez, bilgi verir.
for b in beklenen_bos:
    print("       KAPSAM DISI %s (kayit defteri: INACTIVE_EXCLUDED, "
          "reklam yayinlamiyor)" % b)

# --- 2) Harcama --------------------------------------------------------------
bugun = datetime.date.today()
if TAM:
    zaman = {"date_preset": "maximum"}
    pencere = "tum gecmis"
else:
    bas = bugun - datetime.timedelta(days=GUN)
    zaman = {"time_range": json.dumps({"since": bas.isoformat(), "until": bugun.isoformat()})}
    pencere = "son %d gun (%s..%s)" % (GUN, bas, bugun)

toplam_okunan = toplam_yeni = toplam_guncel = 0
kismi = []
for a in hesaplar:
    hid = str(a.get("account_id") or re.sub(r"^act_", "", a.get("id", "")))
    p = {"fields": ALANLAR, "level": "campaign", "time_increment": "1", "limit": "500"}
    p.update(zaman)
    satirlar, h = sayfalari_topla("act_%s/insights" % hid, p)
    if satirlar is None:
        bildir("harcama %s" % hid, "FAILED", "erisilemedi: %s" % h)
        continue
    if h:
        kismi.append("%s: %s" % (hid, h))
    if not satirlar:
        # Kaynak erisildi, o pencerede yayin yok -> NO_DATA (ariza degil)
        bildir("harcama %s" % hid, "NO_DATA", "%s icinde kayit yok" % pencere)
        continue
    toplam_okunan += len(satirlar)
    if KURU:
        tut = sum(float(s.get("spend") or 0) for s in satirlar)
        bildir("harcama %s" % hid, "SUCCESS", "%d satir, %.2f harcama - KURU" % (len(satirlar), tut))
        continue
    y, g, hh = stage_yaz(satirlar, "raw.meta_harcama_yaz(j, %s)" % ("'" + hid.replace("'", "''") + "'"))
    if hh:
        bildir("harcama %s" % hid, "FAILED", "yazma hatasi: %s" % hh)
        continue
    toplam_yeni += y; toplam_guncel += g
    bildir("harcama %s" % hid, "PARTIAL" if h else "SUCCESS",
           "%d satir (yeni=%d guncel=%d) %s" % (len(satirlar), y, g, pencere))

# 🔴 Erisilemeyen hesap varsa durum SUCCESS OLAMAZ. Okunmayan bir hesabin
#    harcamasi da okunmuyor demektir; toplam eksik, ROAS yanlis.
durum = "FAILED" if "FAILED" in sonuclar else \
        ("PARTIAL" if (kismi or erisilemeyen) else
         ("NO_DATA" if toplam_okunan == 0 else "SUCCESS"))
# 🔴 BEKLENEN BOSLUK ALARM DEGILDIR.
#    Onceki hali okunamayan HER bilinen hesabi PARTIAL sayiyordu ve her
#    sabah "eksik harcama, ROAS oldugundan YUKSEK gorunur" diye alarm
#    uretiyordu. OLCULDU: bu alarm 36 kez caldi ve 20.09'da bir oturumun
#    sahibe gereksiz bir Meta islemi (acik soru #96) acmasina yol acti --
#    oysa core.meta_hesap_kayit o iki hesabi 16.09'da INACTIVE_EXCLUDED
#    isaretlemis, mart.meta_kapsama da "veri acigi DEGIL" diyordu.
#    Yanlis alarm yalnizca gurultu degildir: dikkati gercek isten calar.
#    Guvenlik niyeti KORUNDU -- kayit defterinde ACTIVE olan ya da hic
#    tanimadigimiz bir hesap okunamiyorsa alarm AYNEN calisir.
if erisilemeyen:
    bildir("hesap kapsamasi", "PARTIAL",
           "%d/%d hesap okunuyor - eksik harcama, ROAS oldugundan YUKSEK gorunur"
           % (len(hesaplar), len(hesaplar) + len(erisilemeyen)))
elif beklenen_bos:
    bildir("hesap kapsamasi", "SUCCESS",
           "aktif hesaplarin tamami okunuyor; %d hesap kayit defterinde "
           "INACTIVE_EXCLUDED (okunacak harcama yok)" % len(beklenen_bos))
msj = "%s | okunan=%d yeni=%d guncel=%d | %s" % (pencere, toplam_okunan, toplam_yeni,
                                                 toplam_guncel, liste_notu)
if erisilemeyen: msj += " | ATLANAN HESAP: " + "; ".join(erisilemeyen)
if kismi: msj += " | KISMI: " + "; ".join(kismi)
log_yaz("meta_reklam", durum, toplam_okunan, toplam_yeni, toplam_guncel, msj, t0)

say = collections.Counter(sonuclar)
print("\n" + "-" * 62)
print("SUCCESS=%d  NO_DATA=%d  PARTIAL=%d  FAILED=%d" %
      (say["SUCCESS"], say["NO_DATA"], say["PARTIAL"], say["FAILED"]))
print("-" * 62 + "\n")
sys.exit(1 if say["FAILED"] else (3 if say["PARTIAL"] else (2 if say["NO_DATA"] else 0)))
