#!/usr/bin/env python3
# =============================================================================
# L'CARLIE - URUN KATALOGU YUKLEYICI  (CR-006)
#
# Wix urun katalogunu raw.wix_urun'e aynalar ve maliyet degisimlerini
# core.urun_maliyet'e VERSIYONLAYARAK yazar.
#
# 🔴 MALIYET VERSIYONLAMA BURADA ONEMLI:
#    Wix tek deger tutar. Sahip bir urunun alis fiyatini guncelledigi an
#    eski deger Wix'te kaybolur. Bu betik gunde bir calisip degisimi
#    yakalar; yakalayamazsa o degisim TARIHSIZ kalir ve gecmis marj
#    hesabi bozulur. Bu yuzden gunluk calismasi ihmal edilemez.
#
# 🔴 "0 urun dondu" = NO_DATA, "kaynaga erisilemedi" = FAILED.
#
# Kullanim: python3 urun-yukle.py [--kuru]
# =============================================================================
import json, subprocess, sys, re, datetime, collections

ENV  = "/opt/lcarlie/n8n/.env"
KAP  = "lcarlie-postgres"
KURU = "--kuru" in sys.argv

def env(k):
    try: t = open(ENV).read()
    except Exception: return ""
    m = re.search(r"^" + re.escape(k) + r"=(.*)$", t, re.M)
    return m.group(1).strip() if m else ""

def _kacir(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')

def psql(script, tA=False):
    cmd = ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n",
           "-v", "ON_ERROR_STOP=1"]
    if tA: cmd += ["-tA", "-F", "|"]
    p = subprocess.run(cmd, input=script, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def _wix(yol, govde=None):
    """(veri, hata). Wix'e tek istek; anahtar komut satirina KONMAZ (stdin)."""
    yap = [
        '--silent', '--show-error', '--max-time 60',
        'write-out = "\\n%{http_code}"',
        'request = %s' % ("POST" if govde is not None else "GET"),
        'url = "https://www.wixapis.com%s"' % yol,
        'header = "Authorization: %s"' % _kacir(env("WIX_API_KEY")),
        'header = "wix-site-id: %s"' % _kacir(env("WIX_SITE_ID")),
        'header = "Content-Type: application/json"',
    ]
    if govde is not None:
        yap.append('data = "%s"' % _kacir(json.dumps(govde)))
    r = subprocess.run(["curl", "-K", "-"], input="\n".join(yap) + "\n",
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, "curl rc=%d" % r.returncode
    parca = r.stdout.rsplit("\n", 1)
    if len(parca) != 2: return None, "yanit bicimi beklenmedik"
    govde_, kod = parca
    if kod != "200": return None, "HTTP %s %s" % (kod, govde_[:160])
    try: return json.loads(govde_), None
    except Exception as e: return None, "JSON ayristirilamadi: %s" % e


def _tutar(d):
    try: return float((d or {}).get("amount"))
    except (TypeError, ValueError): return None


def v1_sekli(u, varyant, stok):
    """Wix Catalog V3 urununu raw.wix_urun_yaz + mart.urun_karti'nin okudugu
    V1 SEKLINE cevirir. Gorunumler (urun_karti, fiyat_gercegi ...) ham'dan
    priceData.price / priceData.discountedPrice / stock.quantity /
    media.items / description / sku / visible okuyor; sekli korumak hicbir
    gorunumu degistirmeden veriyi yeniden akitir. V3'un kendisi 'v3' altinda.
    """
    satis = _tutar((u.get("actualPriceRange") or {}).get("minValue"))
    liste = _tutar((u.get("compareAtPriceRange") or {}).get("minValue"))
    maliyet = _tutar((u.get("costRange") or {}).get("minValue"))
    para = u.get("currency") or "TRY"
    return {
        "id": u.get("id"),
        "name": u.get("name"),
        "slug": u.get("slug"),
        "visible": bool(u.get("visible")),
        "sku": (varyant or {}).get("sku"),
        "description": u.get("plainDescription") or "",
        # V1: price = liste (ustu cizili), discountedPrice = satis. Indirim yoksa ikisi esit.
        "priceData": {"price": liste or satis, "discountedPrice": satis, "currency": para},
        "price": {"price": satis, "currency": para},
        "costRange": {"minValue": maliyet} if maliyet is not None else {},
        "stock": {"trackInventory": stok["takip"], "quantity": stok["adet"],
                  "inStock": (u.get("inventory") or {}).get("availabilityStatus") == "IN_STOCK"},
        "media": {"items": ((u.get("media") or {}).get("itemsInfo") or {}).get("items") or []},
        "_kaynak": "wix-catalog-v3",
        "v3": u,
    }


def urunleri_cek():
    """(urunler, toplam, hata).

    🔴 03.11.2026: SITE WIX CATALOG V3'E GECTI. V1 /stores/v1/products/query
       28.10'dan beri 501 donuyordu; raw.wix_urun (Jarvis'in musteriye
       soyledigi fiyat ve marjdaki maliyet) 6 gun guncellenmedi.
       V3'te: fiyat/maliyet urunun ARALIK alanlarinda, SKU varyantta (sorgu
       varyant dondurmez -> urun basina GET), stok ayri envanter servisinde.
    """
    hepsi, govde = [], {"query": {"cursorPaging": {"limit": 100}},
                        "fields": ["MERCHANT_DATA", "CURRENCY", "PLAIN_DESCRIPTION", "URL"]}
    for _ in range(50):
        d, h = _wix("/stores/v3/products/query", govde)
        if h: return None, None, h
        hepsi.extend(d.get("products") or [])
        imlec = ((d.get("pagingMetadata") or {}).get("cursors") or {}).get("next")
        if not (d.get("pagingMetadata") or {}).get("hasNext") or not imlec: break
        # Imlec query ICINDE: disina konursa Wix ilk sayfayi tekrar dondurur.
        govde = {"query": {"cursorPaging": {"limit": 100, "cursor": imlec}},
                 "fields": govde["fields"]}
    else:
        return None, None, "sayfalama 5000'i asti"

    stok = collections.defaultdict(lambda: {"takip": False, "adet": 0})
    govde = {"query": {"cursorPaging": {"limit": 100}}}
    for _ in range(100):
        d, h = _wix("/stores/v3/inventory-items/query", govde)
        if h: return None, None, "envanter: " + h
        for k in d.get("inventoryItems") or []:
            s = stok[k.get("productId")]
            s["takip"] = s["takip"] or bool(k.get("trackQuantity"))
            s["adet"] += int(k.get("quantity") or 0)
        imlec = ((d.get("pagingMetadata") or {}).get("cursors") or {}).get("next")
        if not (d.get("pagingMetadata") or {}).get("hasNext") or not imlec: break
        govde = {"query": {"cursorPaging": {"limit": 100, "cursor": imlec}}}

    sonuc = []
    for u in hepsi:
        d, h = _wix("/stores/v3/products/%s" % u["id"])
        if h: return None, None, "urun %s: %s" % (u["id"], h)
        varyantlar = ((d.get("product") or {}).get("variantsInfo") or {}).get("variants") or []
        sonuc.append(v1_sekli(u, varyantlar[0] if varyantlar else None, stok[u["id"]]))
    return sonuc, len(hepsi), None

def stage_yaz(kayitlar):
    satirlar = [json.dumps(o, ensure_ascii=False).replace("\\", "\\\\") for o in kayitlar]
    script = ("BEGIN;\n"
              "CREATE TEMP TABLE _stage(j jsonb) ON COMMIT DROP;\n"
              "COPY _stage(j) FROM STDIN;\n"
              + "\n".join(satirlar) + "\n\\.\n"
              "\\echo '--SONUC--'\n"
              "SELECT sonuc, count(*) FROM (SELECT raw.wix_urun_yaz(j) AS sonuc FROM _stage) x GROUP BY 1;\n"
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

def log_yaz(durum, okunan, yazilan, guncellenen, mesaj, baslangic):
    if KURU: return
    # 🔴 ONCE KIRP, SONRA KAC.  Tersi yapilinca 900. karakter iki tirnagin
    #    ortasina denk gelebilir, dizge kapanmaz ve gunluk satiri yazilamaz -
    #    tam da "kayit yok" ile "kaydedemedik" ayrimini tutan tablo.
    m = (mesaj or "")[:900].replace("'", "''")
    rc, _, err = psql(
        "INSERT INTO raw.yukleme_log (kaynak,durum,okunan,yazilan,guncellenen,mesaj,baslangic) "
        "VALUES ('wix_urun','%s',%s,%s,%s,'%s','%s');" %
        (durum, "NULL" if okunan is None else okunan,
         "NULL" if yazilan is None else yazilan,
         "NULL" if guncellenen is None else guncellenen, m, baslangic.isoformat()))
    if rc != 0:
        print("  HATA  yukleme_log yazilamadi: %s" % err.split("\n")[0][:150])
        sonuclar.append("FAILED")

sonuclar = []
def bildir(ad, durum, detay):
    sonuclar.append(durum)
    isaret = {"SUCCESS": "ok   ", "NO_DATA": "veri ", "PARTIAL": "kismi", "FAILED": "HATA "}[durum]
    print("  %s %-14s %s" % (isaret, ad, detay))

print("\n=== URUN KATALOGU %s ===" % ("(KURU - YAZILMAZ)" if KURU else ""))
t0 = datetime.datetime.now(datetime.timezone.utc)

urunler, toplam, hata = urunleri_cek()
if urunler is None:
    bildir("wix urun", "FAILED", "kaynaga erisilemedi: %s" % hata)
    log_yaz("FAILED", None, 0, 0, hata, t0)
    print("\nSUCCESS=0  NO_DATA=0  PARTIAL=0  FAILED=1\n"); sys.exit(1)
if not urunler:
    bildir("wix urun", "NO_DATA", "kaynak erisildi, urun yok")
    log_yaz("NO_DATA", 0, 0, 0, "kaynak erisildi, kayit yok", t0)
    print("\nSUCCESS=0  NO_DATA=1  PARTIAL=0  FAILED=0\n"); sys.exit(2)  # sozlesme: NO_DATA=2

eksik = (toplam is not None and len(urunler) != toplam)
maliyetli = sum(1 for u in urunler if (u.get("costRange") or {}).get("minValue"))

if KURU:
    bildir("wix urun", "PARTIAL" if eksik else "SUCCESS",
           "%d urun (kaynakta %s), %d tanesinde maliyet - KURU" % (len(urunler), toplam, maliyetli))
else:
    y, g, h = stage_yaz(urunler)
    if h:
        bildir("wix urun", "FAILED", "yazma hatasi: %s" % h)
        log_yaz("FAILED", len(urunler), 0, 0, h, t0)
        print("\nSUCCESS=0  NO_DATA=0  PARTIAL=0  FAILED=1\n"); sys.exit(1)
    durum = "PARTIAL" if eksik else "SUCCESS"
    msj = "cekilen=%d kaynakta=%s yeni=%d guncellenen=%d maliyetli=%d" % (
        len(urunler), toplam, y, g, maliyetli)
    if eksik: msj = "🔴 EKSIK CEKIM. " + msj
    bildir("wix urun", durum, msj)
    log_yaz(durum, len(urunler), y, g, msj, t0)

    # Maliyet versiyon ozeti
    rc, out, _ = psql(
        "SELECT count(*) || '|' || count(*) FILTER (WHERE gecerli_bitis IS NULL) || '|' || "
        "count(DISTINCT urun_id) FROM core.urun_maliyet;", tA=True)
    if rc == 0 and out:
        t, aktif, u = out.split("|")
        print("       maliyet kaydi: %s (aktif %s, %s urun)" % (t, aktif, u))

# 🔴 Kapsama her calismada yazilir: "marj var" ile "marj olculdu" ayri seyler.
rc, out, _ = psql(
    "SELECT coalesce(round(100.0*sum(satir_ciro) FILTER (WHERE maliyeti_biliniyor)"
    "/nullif(sum(satir_ciro),0),1),0) FROM mart.siparis_kalem WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS');", tA=True)
if rc == 0 and out:
    print("       ciro kapsamasi: %%%s'inin maliyeti biliniyor" % out.strip())

say = collections.Counter(sonuclar)
print("\n" + "-" * 62)
print("SUCCESS=%d  NO_DATA=%d  PARTIAL=%d  FAILED=%d" %
      (say["SUCCESS"], say["NO_DATA"], say["PARTIAL"], say["FAILED"]))
print("-" * 62 + "\n")
sys.exit(1 if say["FAILED"] else (3 if say["PARTIAL"] else (2 if say["NO_DATA"] else 0)))
