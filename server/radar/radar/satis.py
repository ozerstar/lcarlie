"""Sabah özeti için satış verisi: lcarlie.shop (Wix) + Trendyol satıcı API'si -> data/satis_ozet.json.

Yalnız toplamlar yazılır (sipariş sayısı, ödenen tutar); müşteri adı/adres/telefon okunmaz, yazılmaz.

Wix: POST https://www.wixapis.com/ecom/v1/orders/search (izin: Read Orders). API anahtarı ile
     'Authorization: <anahtar>' + 'wix-site-id: <site>' başlıkları. 29.10.2026'da aynı sorgu Wix MCP
     üzerinden gerçek veriyle denendi: son 30 günde 2 sipariş (1 PAID 2.100 TL, 1 iptal).
Trendyol: GET https://apigw.trendyol.com/integration/order/sellers/{satıcıId}/orders
     Basic auth (API key:secret) ve zorunlu 'User-Agent: {satıcıId} - Self Integration'
     (developers.trendyol.com 'Getting Started'). Tarih aralığı en fazla 2 hafta. Anahtar girilmeden denenmedi.
"""
import base64
import datetime as dt
import json
import os
import urllib.request

from .util import iso, now, parse_dt

WIX_URL = "https://www.wixapis.com/ecom/v1/orders/search"
TY_URL = "https://apigw.trendyol.com/integration/order/sellers/{sid}/orders"


def _istek(url, govde=None, basliklar=None, timeout=30):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(basliklar or {})
    veri = json.dumps(govde).encode() if govde is not None else None
    req = urllib.request.Request(url, data=veri, headers=h, method="POST" if veri else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wix_siparisleri(anahtar, site_id, bas, istek=_istek):
    out, cursor = [], None
    for _ in range(20):
        paging = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        d = istek(WIX_URL, {"search": {"filter": {"createdDate": {"$gte": iso(bas)}}, "cursorPaging": paging}},
                  {"Authorization": anahtar, "wix-site-id": site_id})
        for o in d.get("orders") or []:
            out.append({"tarih": o.get("createdDate", ""), "odeme": o.get("paymentStatus"),
                        "tutar": float(((o.get("priceSummary") or {}).get("total") or {}).get("amount") or 0)})
        meta = d.get("metadata") or {}
        cursor = (meta.get("cursors") or {}).get("next")
        if not meta.get("hasNext") or not cursor:
            break
    return out


def trendyol_siparisleri(sid, anahtar, gizli, bas, son, istek=_istek):
    yetki = base64.b64encode(f"{anahtar}:{gizli}".encode()).decode()
    out, sayfa = [], 0
    while sayfa < 20:
        url = (TY_URL.format(sid=sid) + f"?startDate={int(bas.timestamp() * 1000)}&endDate={int(son.timestamp() * 1000)}"
               f"&page={sayfa}&size=200&orderByField=PackageLastModifiedDate&orderByDirection=DESC")
        d = istek(url, None, {"Authorization": f"Basic {yetki}", "User-Agent": f"{sid} - Self Integration"})
        for p in d.get("content") or []:
            out.append({"tarih": dt.datetime.fromtimestamp((p.get("orderDate") or 0) / 1000, dt.timezone.utc).isoformat(),
                        "odeme": p.get("status"), "tutar": float(p.get("totalPrice") or 0)})
        sayfa += 1
        if sayfa >= int(d.get("totalPages") or 0):
            break
    return out


def _ozetle(sips, dun_bas, dun_son, odendi):
    # Siparişler UTC gelir; "dün" Türkiye saatine göre hesaplanır.
    dun = [s for s in sips if (t := parse_dt(s["tarih"])) and dun_bas <= t.date() <= dun_son]
    hafta = sips
    return {"dun_siparis": len(dun), "dun_tutar": round(sum(s["tutar"] for s in dun if odendi(s)), 2),
            "7gun_siparis": len(hafta), "7gun_tutar": round(sum(s["tutar"] for s in hafta if odendi(s)), 2)}


def ozet(env=os.environ, istek=_istek, simdi=None):
    """Anahtarı olan kanalları toplar. Döner: (satış özeti sözlüğü, hatalar)."""
    t = simdi or now()
    dun = (t - dt.timedelta(days=1)).date()
    bas = t - dt.timedelta(days=7)
    sonuc, hatalar = {}, []
    if env.get("WIX_API_KEY") and env.get("WIX_SITE_ID"):
        try:
            s = wix_siparisleri(env["WIX_API_KEY"], env["WIX_SITE_ID"], bas, istek)
            o = _ozetle(s, dun, dun, lambda x: x["odeme"] == "PAID")
            sonuc["lcarlie.shop dün"] = f"{o['dun_siparis']} sipariş, {o['dun_tutar']:,.0f} TL ödenen"
            sonuc["lcarlie.shop 7 gün"] = f"{o['7gun_siparis']} sipariş, {o['7gun_tutar']:,.0f} TL ödenen"
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"wix: {str(e)[:150]}")
    if env.get("TRENDYOL_SATICI_ID") and env.get("TRENDYOL_API_KEY") and env.get("TRENDYOL_API_SECRET"):
        try:
            s = trendyol_siparisleri(env["TRENDYOL_SATICI_ID"], env["TRENDYOL_API_KEY"], env["TRENDYOL_API_SECRET"], bas, t, istek)
            o = _ozetle(s, dun, dun, lambda x: x["odeme"] not in ("Cancelled", "UnSupplied", "Returned"))
            sonuc["Trendyol dün"] = f"{o['dun_siparis']} sipariş, {o['dun_tutar']:,.0f} TL"
            sonuc["Trendyol 7 gün"] = f"{o['7gun_siparis']} sipariş, {o['7gun_tutar']:,.0f} TL"
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"trendyol: {str(e)[:150]}")
    return sonuc, hatalar


IPTAL = ("NOT_PAID", "CANCELED", "CANCELLED", "Cancelled", "UnSupplied", "Returned", "UnDelivered")


def db_ozet(psql=None, simdi=None):
    """Jarvis'in sipariş nöbetçisinin yazdığı core.pazaryeri_siparis'ten toplamlar (anahtarsız).

    30.10.2026: Jarvis'te Wix/Trendyol/n11 anahtarları zaten girili; lcarlie-siparis-nobetci her 2 dakikada
    siparişleri bu tabloya yazıyor. Radar ayrı anahtar tutmaz. Yalnız sayı ve tutar okunur; müşteri alanı okunmaz.
    """
    def _psql(sql):
        import subprocess
        p = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At", "-U", "n8n", "-d", "n8n"],
                           input=sql, capture_output=True, text=True, timeout=45)
        if p.returncode:
            raise RuntimeError((p.stderr or p.stdout)[:200])
        return p.stdout
    psql = psql or _psql
    iptal = ",".join("'%s'" % d for d in IPTAL)
    sql = ("SELECT row_to_json(x) FROM (SELECT kanal, "
           "count(*) FILTER (WHERE (siparis_zamani AT TIME ZONE 'Europe/Istanbul')::date = "
           "(now() AT TIME ZONE 'Europe/Istanbul')::date - 1) AS dun, "
           f"coalesce(sum(tutar) FILTER (WHERE (siparis_zamani AT TIME ZONE 'Europe/Istanbul')::date = "
           f"(now() AT TIME ZONE 'Europe/Istanbul')::date - 1 AND durum NOT IN ({iptal})), 0) AS dun_tutar, "
           "count(*) FILTER (WHERE siparis_zamani >= now() - interval '7 days') AS yedi, "
           f"coalesce(sum(tutar) FILTER (WHERE siparis_zamani >= now() - interval '7 days' AND durum NOT IN ({iptal})), 0) "
           "AS yedi_tutar FROM core.pazaryeri_siparis GROUP BY kanal) x;")
    sonuc = {}
    for satir in psql(sql).splitlines():
        if not satir.strip():
            continue
        r = json.loads(satir)
        if r["yedi"] or r["dun"]:
            sonuc[f"{r['kanal']} dün"] = f"{r['dun']} sipariş, {float(r['dun_tutar']):,.0f} TL"
            sonuc[f"{r['kanal']} 7 gün"] = f"{r['yedi']} sipariş, {float(r['yedi_tutar']):,.0f} TL"
    if not sonuc:
        sonuc["Tüm kanallar"] = "son 7 günde sipariş yok"
    return sonuc


def yaz(cfg, env=os.environ, istek=_istek):
    if env.get("RADAR_SATIS_KAYNAGI", "jarvis") == "jarvis":
        try:
            sonuc, hatalar = db_ozet(), []
        except Exception as e:  # noqa: BLE001
            sonuc, hatalar = {}, [f"jarvis sipariş tablosu: {str(e)[:150]}"]
    else:
        sonuc, hatalar = ozet(env, istek)
    yol = os.path.join(os.path.dirname(cfg["db_path"]), "satis_ozet.json")
    if sonuc:
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False)
    elif os.path.exists(yol):
        os.remove(yol)   # eski rakam "bugünün" diye özete girmesin
    return {"yazilan": sonuc, "hatalar": hatalar,
            "durum": "anahtar yok (WIX_API_KEY/WIX_SITE_ID, TRENDYOL_*)" if not sonuc and not hatalar else "tamam"}
