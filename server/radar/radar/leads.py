"""B2B müşteri adayı bulma (Google Places API - Text Search) ve onaya düşen ilk mesaj taslağı."""
import os

from . import claims, outbox
from .util import http_post_json, iso, now

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ("places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
          "places.websiteUri,places.rating,places.googleMapsUri,places.primaryTypeDisplayName,places.businessStatus")


def _tip(q, p):
    t = ((p.get("primaryTypeDisplayName") or {}).get("text") or "").lower()
    ql = q.lower()
    if "eczane" in ql or "pharmacy" in t or "eczane" in t:
        return "eczane"
    if "klinik" in ql or "doktor" in ql or "doctor" in t or "clinic" in t:
        return "klinik"
    return "güzellik merkezi"


def draft_message(name, tip, book, tanitim=""):
    kamp = "\n".join("• " + k for k in book.campaigns[:3])
    # Üretim standardı / menşe gibi beyanlar yalnız sahibin config'e yazdığı onaylı cümleden gelir.
    tanitim = tanitim or f"L'CARLİÉ olarak {tip} iş ortaklarımıza bakım ürünlerimizi tanıtmak isteriz."
    body = (f"Merhaba {name} ekibi,\n\n"
            f"{tanitim}\n\n"
            f"Satış noktalarımıza sunduğumuz destekler:\n{kamp}\n\n"
            f"Uygun olursanız ürün kataloğumuzu ve fiyat listemizi iletebiliriz. Ürünlerin tamamı: lcarlie.shop\n\n"
            f"Saygılarımızla,\nL'CARLİÉ")
    return body, claims.check(body)


OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_TURLER = {"eczane": '["amenity"="pharmacy"]', "klinik": '["healthcare"="clinic"]["healthcare:speciality"~"dermatology"]',
              "güzellik merkezi": '["shop"="beauty"]'}


def _overpass(il, tur_filtresi, getir):
    q = (f'[out:json][timeout:90];area["name"="{il}"]["admin_level"="4"]->.a;'
         f'nwr{tur_filtresi}(area.a);out center tags;')
    return getir(OVERPASS, q).get("elements", [])


def _overpass_getir(url, sorgu):
    import json
    import urllib.parse
    import urllib.request
    req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": sorgu}).encode(),
                                 headers={"User-Agent": "LCarlieRadar/1.0"})
    with urllib.request.urlopen(req, timeout=150) as r:
        return json.loads(r.read().decode("utf-8"))


def osm_bul(conn, cfg, book, getir=_overpass_getir):
    """Google Places yerine OpenStreetMap (29.10.2026 ölçüldü: Ankara'da 1.802 eczane, 1.372'sinde telefon).

    Veri © OpenStreetMap katkıcıları (ODbL). İşletme kaydıdır; ilk mesaj yine onaya düşer.
    """
    lc = cfg["leads"]
    yeni, hatalar = 0, []
    for il in lc.get("osm_iller", ["Ankara"]):
        for tip in lc.get("osm_turler", ["eczane"]):
            if yeni >= lc["daily_limit"]:
                break
            try:
                els = _overpass(il, OSM_TURLER[tip], getir)
            except Exception as e:  # noqa: BLE001
                hatalar.append(f"{il}/{tip}: {e}")
                continue
            for e in sorted(els, key=lambda x: x.get("id", 0)):
                if yeni >= lc["daily_limit"]:
                    break
                tg = e.get("tags") or {}
                ad, tel = tg.get("name"), tg.get("phone") or tg.get("contact:phone")
                pid = f"osm:{e.get('type')}/{e.get('id')}"
                if not ad or conn.execute("SELECT 1 FROM leads WHERE place_id=?", (pid,)).fetchone():
                    continue
                adres = " ".join(x for x in (tg.get("addr:street"), tg.get("addr:housenumber"),
                                             tg.get("addr:district") or tg.get("addr:suburb"), il) if x)
                conn.execute("INSERT INTO leads(place_id,name,type,address,phone,website,rating,source_url,query,found_at)"
                             " VALUES(?,?,?,?,?,?,?,?,?,?)",
                             (pid, ad, tip, adres, tel, tg.get("website"), None,
                              f"https://www.openstreetmap.org/{e.get('type')}/{e.get('id')}", f"osm {il} {tip}", iso(now())))
                body, chk = draft_message(ad, tip, book, lc.get("lead_tanitim", ""))
                if tel and chk["durum"] != "YASAK":
                    outbox.enqueue(conn, "whatsapp", tel, body, f"Tanışma: {ad}", to_owner=False, ref=f"lead:{pid}")
                    conn.execute("UPDATE leads SET status='drafted' WHERE place_id=?", (pid,))
                yeni += 1
    conn.commit()
    return {"durum": "tamam" if not hatalar else "kısmi", "yeni": yeni, "hatalar": hatalar, "kaynak": "OpenStreetMap"}


def find(conn, cfg, book, post=http_post_json):
    lc = cfg["leads"]
    key = os.environ.get(lc["api_key_env"])
    if not lc.get("enabled"):
        return {"durum": "kapalı", "yeni": 0}
    if lc.get("kaynak", "osm") == "osm":
        return osm_bul(conn, cfg, book)
    if not key:
        return {"durum": f"API anahtarı yok ({lc['api_key_env']})", "yeni": 0, "hata": True}
    yeni, hatalar = 0, []
    for q in lc["queries"]:
        if yeni >= lc["daily_limit"]:
            break
        try:
            res = post(URL, {"textQuery": q, "languageCode": "tr", "regionCode": "TR"},
                       {"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
        except Exception as e:
            hatalar.append(f"{q}: {e}")
            continue
        for p in res.get("places", []):
            if yeni >= lc["daily_limit"]:
                break
            if p.get("businessStatus") not in (None, "OPERATIONAL"):
                continue
            if conn.execute("SELECT 1 FROM leads WHERE place_id=?", (p["id"],)).fetchone():
                continue  # daha önce bulundu
            name = (p.get("displayName") or {}).get("text", "?")
            tip = _tip(q, p)
            conn.execute("INSERT INTO leads(place_id,name,type,address,phone,website,rating,source_url,query,found_at)"
                         " VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (p["id"], name, tip, p.get("formattedAddress"), p.get("nationalPhoneNumber"),
                          p.get("websiteUri"), p.get("rating"), p.get("googleMapsUri"), q, iso(now())))
            body, chk = draft_message(name, tip, book, lc.get("lead_tanitim", ""))
            if p.get("nationalPhoneNumber") and chk["durum"] != "YASAK":
                outbox.enqueue(conn, "whatsapp", p["nationalPhoneNumber"], body, f"Tanışma: {name}",
                               to_owner=False, ref=f"lead:{p['id']}")
                conn.execute("UPDATE leads SET status='drafted' WHERE place_id=?", (p["id"],))
            yeni += 1
    conn.commit()
    return {"durum": "tamam" if not hatalar else "kısmi", "yeni": yeni, "hatalar": hatalar}
