#!/usr/bin/env python3
"""Kisa omurlu Meta kullanici jetonunu stdin'den alir; uzun omurlu kullanici jetonuna,
oradan suresiz SAYFA jetonuna cevirir; izinleri dogrular; /opt/lcarlie/n8n/.env icindeki
FB_PAGE_YORUM_TOKEN'i (yalniz yorum okuma) yedekleyip yazar; FB_PAGE_TOKEN'a DOKUNMAZ. Jeton ekrana/loga YAZILMAZ."""
import json, shutil, sys, time, urllib.parse, urllib.request
from pathlib import Path

ENV = Path("/opt/lcarlie/n8n/.env")
SAYFA_ID = "1222783064240254"  # L'carlie Natural Cosmetics (panoda goruldu, asagida dogrulanir)
GEREKLI = {"pages_read_user_content", "pages_read_engagement"}
G = "https://graph.facebook.com/v21.0/"

def env(k):
    for s in ENV.read_text(encoding="utf-8").splitlines():
        if s.startswith(k + "="):
            return s.split("=", 1)[1].strip()
    return ""

def get(yol, **q):
    with urllib.request.urlopen(G + yol + "?" + urllib.parse.urlencode(q), timeout=30) as r:
        return json.load(r)

kisa = sys.stdin.read().strip()
if not kisa or " " in kisa:
    sys.exit("HATA: stdin'de jeton yok (panoya kopyaladin mi?)")
app_id, sir = env("META_APP_ID") or "2243528976504995", env("META_APP_SECRET")
if not sir:
    sys.exit("HATA: META_APP_SECRET yok")
try:
    uzun = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
               client_secret=sir, fb_exchange_token=kisa)["access_token"]
    sayfalar = get("me/accounts", access_token=uzun, fields="id,name,access_token", limit=100)["data"]
except urllib.error.HTTPError as e:
    sys.exit(f"HATA: Meta {e.code}: {json.load(e).get('error', {}).get('message', '')[:160]}")
s = next((p for p in sayfalar if p["id"] == SAYFA_ID), None) or (sayfalar[0] if len(sayfalar) == 1 else None)
if not s:  # Isletme sayfasi me/accounts'ta gorunmeyebilir: dogrudan sor
    try:
        s = get(SAYFA_ID, access_token=uzun, fields="id,name,access_token")
        if "access_token" not in s:
            s = None
    except urllib.error.HTTPError as e:
        print("dogrudan sayfa sorgusu:", json.load(e).get("error", {}).get("message", "")[:160])
        s = None
if not s:
    sys.exit("HATA: sayfa bulunamadi; gorulenler: " + ", ".join(p["name"] for p in sayfalar))
jeton = s["access_token"]
d = get("debug_token", input_token=jeton, access_token=f"{app_id}|{sir}")["data"]
eksik = GEREKLI - set(d.get("scopes", []))
print(f"Sayfa: {s['name']} ({s['id']}) tip={d.get('type')} bitis={d.get('expires_at')} gecerli={d.get('is_valid')}")
if eksik:
    sys.exit("HATA: yeni jetonda eksik izin: " + ", ".join(sorted(eksik)) + " — .env DEGISMEDI")
yedek = ENV.with_name(".env.yedek-fbjeton-" + time.strftime("%Y%m%d-%H%M%S"))
shutil.copy2(ENV, yedek)
satirlar = [l for l in ENV.read_text(encoding="utf-8").splitlines() if not l.startswith("FB_PAGE_YORUM_TOKEN=")]
satirlar.append("FB_PAGE_YORUM_TOKEN=" + jeton)
ENV.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
print(f"TAMAM: FB_PAGE_YORUM_TOKEN yazildi (yedek {yedek.name}); izin sayisi {len(d.get('scopes', []))}")
