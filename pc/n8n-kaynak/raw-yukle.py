#!/usr/bin/env python3
# =============================================================================
# L'CARLIE - RAW KATMANI YUKLEYICI  (CR-004 Faz 1)
#
# Wix siparisleri + BasitKargo gonderilerini raw katmanina aynalar.
#
# 🔴 TEMEL KURALLAR
#    1. "0 kayit yazildi" SUCCESS DEGIL. Kaynaga ERISILEMEDIYSE -> FAILED,
#       erisildi ama kayit yoksa -> NO_DATA. Ikisi ASLA ayni sayilmaz.
#    2. EKSIK CEKIM SESSIZ GECMEZ. Cekilen sayi kaynaktaki sayiyla
#       tutmuyorsa -> PARTIAL.
#    3. IDEMPOTENT. Ikinci calistirmada yeni satir olusmaz, sadece UPDATE.
#    4. PII EKRANA/LOGA BASILMAZ. Sayimlar ve maskelenmis ornekler yeter.
#    5. Yazma isi SQL fonksiyonlarinda (raw-cikarma.sql). Bu betik yalniz
#       CEKER ve STAGE eder - cikarma kurali degisirse kaynaga hic dokunulmaz.
#
# 🔴 BASITKARGO SAYFALAMA UYARISI (16.09.2026 olculdu)
#    /api/v2/order/filter DUZ DIZI dondurur; toplam sayi alani YOKTUR.
#    Ustelik page=0 ile page=1 AYNI sayfayi verir (1-tabanli, 0 takma ad).
#    Bu yuzden tek "buyuk sayfa" cekimine GUVENILMEZ: ayrica 20'lik
#    sayfalarla gezilip id kumeleri KARSILASTIRILIR. Fark varsa PARTIAL.
#
# Kullanim:  python3 /opt/lcarlie/raw-yukle.py [--kuru]
#            --kuru : veritabanina YAZMAZ, yalniz cekip raporlar
# =============================================================================
import json, subprocess, sys, os, re, tempfile, datetime, collections

ENV  = "/opt/lcarlie/n8n/.env"
KAP  = "lcarlie-postgres"
KURU = "--kuru" in sys.argv

def env(k):
    try:
        t = open(ENV).read()
    except Exception as e:
        return ""
    m = re.search(r"^" + re.escape(k) + r"=(.*)$", t, re.M)
    return m.group(1).strip() if m else ""

def psql(script, tA=False):
    """SQL calistir. (rc, stdout, stderr) doner."""
    cmd = ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
           "-v", "ON_ERROR_STOP=1"]
    if tA: cmd += ["-tA", "-F", "|"]
    p = subprocess.run(cmd, input=script, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def _kacir(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')

def istek(url, basliklar, govde, saniye=60):
    """POST at. (veri, hata) doner. hata None degilse ERISILEMEDI demektir.

    🔴 API ANAHTARI KOMUT SATIRINA YAZILMAZ.  Onceki hali basliklari
       '-H' argumani olarak geciriyordu; komut satiri argumanlari /proc
       uzerinden sunucudaki HER surece gorunur ('ps aux' yeter). Yani
       WIX_API_KEY ve BASITKARGO_TOKEN sizabilir durumdaydi.
       curl'un -K secenegi yapilandirmayi STDIN'den okur, orada gorunmez.
       (Bu desen meta-harcama-yukle.py'de zaten dogru yazilmisti; buraya
       kopyalanmamisti - 16.09.2026 denetiminde yakalandi.)
    """
    satirlar = ['--silent', '--show-error', '--max-time %d' % saniye,
                # 🔴 TEK yuzde: bu satir bir % bicimlemesinin icinde DEGIL,
                #    duz dizge. '%%' yazmak curl'e literal '%%{http_code}'
                #    gonderir ve HTTP kodu hic cozulmez.
                'write-out = "\\n%{http_code}"',
                'request = POST',
                'url = "%s"' % _kacir(url)]
    for b in basliklar:
        satirlar.append('header = "%s"' % _kacir(b))
    satirlar.append('data = "%s"' % _kacir(json.dumps(govde)))
    r = subprocess.run(["curl", "-K", "-"], input="\n".join(satirlar) + "\n",
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, "curl rc=%d" % r.returncode
    parca = r.stdout.rsplit("\n", 1)
    if len(parca) != 2:
        return None, "yanit bicimi beklenmedik"
    govde_metin, kod = parca
    if kod != "200":
        return None, "HTTP %s" % kod
    try:
        return json.loads(govde_metin), None
    except Exception as e:
        return None, "JSON ayristirilamadi: %s" % e

# =============================================================================
# CEKIM
# =============================================================================
def cek_wix():
    """(kayitlar, toplam_kaynakta, hata) doner."""
    bas = ["Authorization: " + env("WIX_API_KEY"),
           "wix-site-id: " + env("WIX_SITE_ID"),
           "Content-Type: application/json"]
    url = "https://www.wixapis.com/stores/v2/orders/query"
    hepsi, gorulen, offset, toplam = [], set(), 0, None
    while True:
        d, h = istek(url, bas, {"query": {"paging": {"limit": 100, "offset": offset}}})
        if h: return None, None, h
        if toplam is None:
            toplam = d.get("totalResults")
        # 🔴 metadata.items ISTENEN limiti yansitir, DONEN sayiyi degil.
        #    Sayfalamayi ona gore kurmak sonsuz donguye sokar.
        sayfa = d.get("orders") or []
        if not sayfa: break
        for o in sayfa:
            if o.get("id") and o["id"] not in gorulen:
                gorulen.add(o["id"]); hepsi.append(o)
        offset += len(sayfa)
        if toplam is not None and offset >= toplam: break
        if offset > 5000: return None, None, "sayfalama 5000'i asti, durduruldu"
    return hepsi, toplam, None

def cek_bk():
    """(kayitlar, capraz_kontrol_notu, hata) doner."""
    bas = ["Authorization: Bearer " + env("BASITKARGO_TOKEN"),
           "Content-Type: application/json"]
    url = "https://basitkargo.com/api/v2/order/filter"

    def sayfa(p, s):
        d, h = istek(url, bas, {"page": p, "size": s})
        if h: return None, h
        if not isinstance(d, list): return None, "beklenen dizi, gelen %s" % type(d).__name__
        return d, None

    # 1) Toplu cekim: buyuk sayfa, ardindan sonraki sayfalar bosalana kadar
    toplu, p = {}, 0
    while True:
        d, h = sayfa(p if p else 0, 500)
        if h: return None, None, h
        if not d: break
        for o in d:
            if o.get("id"): toplu[o["id"]] = o
        if len(d) < 500: break
        p = (p + 1) if p else 2   # 🔴 page=1, page=0'in takma adi - atlanir
        if p > 40: return None, None, "toplu sayfalama 40 sayfayi asti"

    # 2) Capraz kontrol: 20'lik sayfalarla bagimsiz gezinti
    capraz, s, p = set(), 20, 1
    while True:
        d, h = sayfa(p, s)
        if h:
            # 🔴 YAPILAMAYAN DOGRULAMA "BASARI" DEGILDIR (16.09 denetimi).
            #    Onceki hali bu notu dondururdu ama tutarsizlik testi notun
            #    '🔴' ile baslamasina bakiyordu -> durum SUCCESS oluyordu.
            #    Sayfalama dogrulamasi BasitKargo'daki TEK eksik-cekim
            #    korumasi; yapilamadiginda "veri tam" denmis olurdu.
            return list(toplu.values()), "🔴 CAPRAZ KONTROL YAPILAMADI: %s" % h, None
        for o in d:
            if o.get("id"): capraz.add(o["id"])
        if len(d) < s: break
        p += 1
        if p > 100: break

    a, b = set(toplu), capraz
    if a == b:
        not_ = "capraz kontrol tutarli (%d id, iki bagimsiz sayfalama)" % len(a)
    else:
        not_ = ("🔴 CAPRAZ KONTROL TUTMADI: toplu=%d sayfali=%d "
                "yalniz-toplu=%d yalniz-sayfali=%d" %
                (len(a), len(b), len(a - b), len(b - a)))
        # 🔴 Yorum "birlesim alinir" diyordu ama govde bostu (pass) - yani
        #    kayitlar atiliyordu. Yorumla kod celisiyordu. Artik sayfali
        #    gezintide gorulup toplu cekimde olmayan her id TEKIL olarak
        #    aranir; bulunursa gercekten birlesime katilir.
        for i in sorted(b - a):
            d3, h3 = sayfa(1, 500)
            if d3:
                for o in d3:
                    if o.get("id") == i:
                        toplu[i] = o
                        break
            if i not in toplu:
                not_ += " | govdesi alinamayan id: %s" % i
    return list(toplu.values()), not_, None

# =============================================================================
# YAZMA
# =============================================================================
def stage_yaz(kayitlar, fonksiyon):
    """Kayitlari gecici tabloya COPY ile yukleyip cikarma fonksiyonunu calistirir.
       (yazilan, guncellenen, hata) doner."""
    # COPY TEXT bicimi: ters bolu kacisi gerekir. json.dumps ciktisinda
    # HAM satirsonu/sekme BULUNMAZ (hepsi \n \t olarak kacirilmistir),
    # bu yuzden tek yapilacak ters bolulari ikilemektir.
    satirlar = [json.dumps(o, ensure_ascii=False).replace("\\", "\\\\") for o in kayitlar]
    script = (
        "BEGIN;\n"
        "CREATE TEMP TABLE _stage(j jsonb) ON COMMIT DROP;\n"
        "COPY _stage(j) FROM STDIN;\n"
        + "\n".join(satirlar) + "\n\\.\n"
        "\\echo '--SONUC--'\n"
        "SELECT sonuc, count(*) FROM (SELECT %s(j) AS sonuc FROM _stage) x GROUP BY 1;\n"
        "COMMIT;\n" % fonksiyon)
    rc, out, err = psql(script, tA=True)
    if rc != 0:
        return 0, 0, (err.split("\n")[0][:200] if err else "psql rc=%d" % rc)
    say = {"INSERT": 0, "UPDATE": 0}
    bloktayiz = False
    for satir in out.split("\n"):
        if satir.strip() == "--SONUC--": bloktayiz = True; continue
        if not bloktayiz: continue
        p = satir.split("|")
        if len(p) == 2 and p[0].strip() in say:
            say[p[0].strip()] = int(p[1])
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
    # 🔴 Gunluge yazamamak sessiz gecmez - yoksa "kayit yok" ile
    #    "kaydedemedik" ayirt edilemez hale gelir.
    if rc != 0:
        print("  HATA  yukleme_log yazilamadi: %s" % (err.split("\n")[0][:150]))
        sonuclar.append("FAILED")

# =============================================================================
# AKIS
# =============================================================================
sonuclar = []
def bildir(kaynak, durum, detay):
    sonuclar.append(durum)
    isaret = {"SUCCESS": "ok   ", "NO_DATA": "veri ", "PARTIAL": "kismi", "FAILED": "HATA "}[durum]
    print("  %s %-14s %s" % (isaret, kaynak, detay))

print("\n=== RAW YUKLEME %s ===" % ("(KURU CALISMA - YAZILMAZ)" if KURU else ""))

# --- WIX ---------------------------------------------------------------------
t0 = datetime.datetime.now(datetime.timezone.utc)
ords, toplam, hata = cek_wix()
if ords is None:
    bildir("wix", "FAILED", "kaynaga erisilemedi: %s" % hata)
    log_yaz("wix", "FAILED", None, 0, 0, hata, t0)
elif not ords:
    bildir("wix", "NO_DATA", "kaynak erisildi, siparis yok")
    log_yaz("wix", "NO_DATA", 0, 0, 0, "kaynak erisildi, kayit yok", t0)
else:
    eksik = (toplam is not None and len(ords) != toplam)
    if KURU:
        bildir("wix", "PARTIAL" if eksik else "SUCCESS",
               "%d siparis cekildi (kaynakta %s) - KURU, yazilmadi" % (len(ords), toplam))
    else:
        y, g, h = stage_yaz(ords, "raw.wix_order_yaz")
        if h:
            bildir("wix", "FAILED", "yazma hatasi: %s" % h)
            log_yaz("wix", "FAILED", len(ords), 0, 0, h, t0)
        else:
            durum = "PARTIAL" if eksik else "SUCCESS"
            msj = "cekilen=%d kaynakta=%s yeni=%d guncellenen=%d" % (len(ords), toplam, y, g)
            if eksik: msj = "🔴 EKSIK CEKIM. " + msj
            bildir("wix", durum, msj)
            log_yaz("wix", durum, len(ords), y, g, msj, t0)

# --- BASITKARGO --------------------------------------------------------------
t0 = datetime.datetime.now(datetime.timezone.utc)
gnd, capraz, hata = cek_bk()
if gnd is None:
    bildir("basitkargo", "FAILED", "kaynaga erisilemedi: %s" % hata)
    log_yaz("basitkargo", "FAILED", None, 0, 0, hata, t0)
elif not gnd:
    bildir("basitkargo", "NO_DATA", "kaynak erisildi, gonderi yok")
    log_yaz("basitkargo", "NO_DATA", 0, 0, 0, "kaynak erisildi, kayit yok", t0)
else:
    tutarsiz = capraz.startswith("🔴")
    if KURU:
        bildir("basitkargo", "PARTIAL" if tutarsiz else "SUCCESS",
               "%d gonderi cekildi - KURU, yazilmadi" % len(gnd))
    else:
        y, g, h = stage_yaz(gnd, "raw.bk_shipment_yaz")
        if h:
            bildir("basitkargo", "FAILED", "yazma hatasi: %s" % h)
            log_yaz("basitkargo", "FAILED", len(gnd), 0, 0, h, t0)
        else:
            durum = "PARTIAL" if tutarsiz else "SUCCESS"
            msj = "cekilen=%d yeni=%d guncellenen=%d | %s" % (len(gnd), y, g, capraz)
            bildir("basitkargo", durum, msj)
            log_yaz("basitkargo", durum, len(gnd), y, g, msj, t0)
    print("       %s" % capraz)

# --- OZET --------------------------------------------------------------------
say = collections.Counter(sonuclar)
print("\n" + "-" * 62)
print("SUCCESS=%d  NO_DATA=%d  PARTIAL=%d  FAILED=%d" %
      (say["SUCCESS"], say["NO_DATA"], say["PARTIAL"], say["FAILED"]))
print("-" * 62 + "\n")
# 🔴 ORTAK CIKIS SOZLESMESI (16.09 denetimi):
#      0 = SUCCESS · 1 = FAILED · 2 = NO_DATA · 3 = PARTIAL
#    Onceki hali NO_DATA icin de 1 donuyordu; cagiran bunu "ETL basarisiz"
#    alarmina cevirirdi - oysa "kaynak erisildi, kayit yok" bir ariza degil.
#    PARTIAL ise 0 donuyordu, yani BILINEN eksik cekim "basarili" gorunuyordu.
#    Bu iki yanlis, Kural 1'in iki ayri yonden ihlaliydi.
sys.exit(1 if say["FAILED"] else (3 if say["PARTIAL"] else (2 if say["NO_DATA"] else 0)))
