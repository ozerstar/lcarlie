"""Rakip filtreleri ve şeffaf puanlama.

Her kriter ayrı değerlendirilir: gecti=True/False/None(bilinmiyor) + neden.
Marka, Özer'in filtrelerinden en az birine uyarsa aday olur.
"""
import datetime as dt
import re

from .db import jload
from .util import norm, now, parse_dt

RENKLI = ["ruj", "fondöten", "fondoten", "maskara", "rimel", "far paleti", "göz farı", "allık", "oje",
          "kapatıcı", "eyeliner", "highlighter", "pudra", "kontür", "dudak kalemi", "göz kalemi", "bb krem",
          "lipstick", "foundation", "mascara", "blush", "concealer", "nail polish", "makyaj"]
# Kapsam dışı ürün grupları (29.10.2026 gerçek taramada Dunhill parfüm ve Durex aday oldu).
KAPSAM_DISI = ["parfüm", "parfum", "edt", "edp", "eau de toilette", "eau de parfum", "kolonya", "deodorant",
               "prezervatif", "kondom", "kayganlaştırıcı", "tıraş bıçağı", "jilet", "diş fırçası", "tampon",
               "ped", "saç boyası", "oje", "vitamin", "takviye", "kapsül", "tablet", "mama",
               # 30.10.2026 Trendyol intim aramasında: ilaç/tıbbi cihaz formları
               "supozituar", "ovül", "vajinal ovül", "siğil"]
ILAC = ["reçeteli", "reçete ile", "beşeri tıbbi ürün", "ruhsatlı ilaç", "ilaç ruhsat", "etken madde mg"]
DOGAL = ["doğal", "bitkisel", "organik", "vegan", "botanik", "natural", "organic", "plant based",
         "ecocert", "cosmos", "bitki özlü", "doğal içerik"]
TEDAVI_BENZERI = ["merhem", "balsam", "balm", "onarıcı", "bariyer", "yatıştırıcı", "aktar", "şifalı",
                  "kaşıntı", "çatlak", "pişik", "nasır", "yara bakım", "sertleşmiş", "kızarıklık"]
KANAL = {"eczane": ["eczane", "eczanelerde", "pharmacy"], "rossmann": ["rossmann"],
         "gratis": ["gratis"], "watsons": ["watsons"]}
DOKTOR = ["dermatolog", "eczacı", "klinik", "doktor", "hekim", "dermokozmetik", "dermo kozmetik"]
YABANCI = ["kore", "k-beauty", "korean", "fransız", "french", "ithal", "almanya", "isviçre", "italya"]

AGIRLIK = {"fiyat_bandi": 25, "yeni_giris": 15, "dogal": 15, "tedavi_benzeri": 15, "kanal": 15,
           "buyume": 10, "reklam": 10, "doktor_eczaci": 10, "yabanci": 5}
OZER_FILTRELERI = ["fiyat_bandi", "yeni_giris", "dogal", "tedavi_benzeri", "kanal"]


def _has(text, words):
    """Kelime başı eşleşmesi (Türkçe ekleri kabul eder: 'eczanelerde' ~ 'eczane', 'yaratıcı' ≠ 'yara' değil)."""
    out = []
    for w in words:
        if re.search(r"(?<!\w)" + re.escape(norm(w)), text):
            out.append(w)
    return out


def _latest(conn, brand_id, kind, before=None):
    q = "SELECT * FROM observations WHERE brand_id=? AND kind=? AND verified=1"
    args = [brand_id, kind]
    if before:
        q += " AND fetched_at<=?"
        args.append(before)
    return conn.execute(q + " ORDER BY fetched_at DESC, id DESC LIMIT 1", args).fetchone()


def evaluate(conn, brand_id, cfg, book):
    b = conn.execute("SELECT * FROM brands WHERE id=?", (brand_id,)).fetchone()
    texts = jload(b["texts"], [])
    prods = conn.execute("SELECT * FROM products WHERE brand_id=?", (brand_id,)).fetchall()
    blob = norm(" ".join(texts + [p["name"] for p in prods]))
    excl = [r["kw"] for r in conn.execute("SELECT kw FROM keywords WHERE kind='exclude'")]
    d = {}

    # --- Hariç tutma ---
    names = [norm(p["name"]) for p in prods] or [blob]
    renkli = sum(1 for n in names if _has(n, RENKLI))
    if renkli and renkli / len(names) >= 0.5:
        return {"durum": "filtered", "neden": "renkli kozmetik", "puan": 0, "kriterler": {}}
    kapsam_disi = sum(1 for n in names if _has(n, KAPSAM_DISI))
    if kapsam_disi and kapsam_disi / len(names) >= 0.5:
        return {"durum": "filtered", "neden": "kapsam dışı ürün grubu", "puan": 0, "kriterler": {}}
    if _has(blob, ILAC):
        return {"durum": "filtered", "neden": "ilaç / ruhsatlı ürün", "puan": 0, "kriterler": {}}
    hit = [k for k in excl if k in blob]
    if hit:
        return {"durum": "filtered", "neden": "hariç kelime: " + ", ".join(hit), "puan": 0, "kriterler": {}}

    # --- Fiyat bandı ---
    priced = []
    for p in prods:
        o = conn.execute("SELECT value_num, source_url FROM observations WHERE product_id=? AND kind='price' "
                         "AND verified=1 ORDER BY fetched_at DESC, id DESC LIMIT 1", (p["id"],)).fetchone()
        if o:
            band = book.band(o["value_num"], p["category"], cfg["price_band_min_ratio"],
                             trendyol="trendyol.com" in (o["source_url"] or ""))
            priced.append((p["name"], o["value_num"], band, o["source_url"]))
    if priced:
        ok = [x for x in priced if x[2]["bantta"]]
        share = len(ok) / len(priced)
        d["fiyat_bandi"] = (share >= 0.5, f"{len(ok)}/{len(priced)} ürün bizimle aynı bantta veya pahalı")
    else:
        d["fiyat_bandi"] = (None, "fiyat verisi yok")

    # --- Yeni giriş ---
    hint = parse_dt(b["first_seen_hint"])
    if hint:
        days = (now() - hint).days
        d["yeni_giris"] = (days <= cfg["new_entrant_days"], f"piyasaya giriş ~{days} gün önce")
    else:
        d["yeni_giris"] = (None, "giriş tarihi bilinmiyor")

    w = _has(blob, DOGAL)
    d["dogal"] = (bool(w), "anahtar: " + ", ".join(w) if w else "doğal vurgusu yok")
    w = _has(blob, TEDAVI_BENZERI)
    d["tedavi_benzeri"] = (bool(w), "anahtar: " + ", ".join(w) if w else "bakım/onarım vurgusu yok")

    ch = {o["value_text"] for o in conn.execute(
        "SELECT value_text FROM observations WHERE brand_id=? AND kind='channel'", (brand_id,))}
    found = sorted({k for k, ws in KANAL.items() if k in ch or _has(blob, ws)})
    d["kanal"] = (bool({"eczane", "rossmann"} & set(found)),
                  "kanallar: " + ", ".join(found) if found else "kanal bilgisi yok")

    # --- Benim eklemelerim ---
    rc = _latest(conn, brand_id, "review_count")
    if rc:
        old = _latest(conn, brand_id, "review_count",
                      before=(parse_dt(rc["fetched_at"]) - dt.timedelta(days=25)).isoformat())
        if old and old["value_num"]:
            g = (rc["value_num"] - old["value_num"]) / old["value_num"] * 100
            d["buyume"] = (g >= cfg["growth_pct_30d"], f"yorum sayısı ~30 günde %{g:.0f}")
        else:
            d["buyume"] = (None, "karşılaştırma için eski veri yok")
    else:
        d["buyume"] = (None, "yorum verisi yok")
    ad = _latest(conn, brand_id, "ad_count")
    d["reklam"] = ((ad["value_num"] >= cfg["ad_intensity_min"]), f"aktif reklam: {ad['value_num']:.0f}") if ad \
        else (None, "reklam verisi yok")
    w = _has(blob, DOKTOR)
    d["doktor_eczaci"] = (bool(w), "anahtar: " + ", ".join(w) if w else "klinik konumlandırma yok")
    origin = (b["origin"] or "").upper()
    w = _has(blob, YABANCI)
    yab = (origin not in ("", "TR")) or bool(w)
    d["yabanci"] = (yab, f"menşei: {origin or '?'}" + (f", anahtar: {', '.join(w)}" if w else ""))

    puan = sum(AGIRLIK[k] for k, (g, _) in d.items() if g)
    eslesen = [k for k in OZER_FILTRELERI if d[k][0]]
    ucuz_cok_satan = d["fiyat_bandi"][0] is False and d["buyume"][0] is True
    # Eczane kaynağından gelen her marka 'kanal' filtresini zaten geçiyor (29.10.2026 gerçek taramada
    # 21/21 marka aday oldu, diş macunu dahil). Kanal tek başına adaylık için yetmez.
    if eslesen == ["kanal"] and not cfg.get("kanal_tek_basina_yeterli", False):
        eslesen = []
    if eslesen:
        durum, neden = "candidate", "eşleşen filtreler: " + ", ".join(eslesen)
    elif ucuz_cok_satan:
        durum, neden = "candidate", "ucuz ama hızlı büyüyen (izleme listesi)"
    else:
        durum, neden = "unqualified", "filtrelerin hiçbirine uymadı"
    return {"durum": durum, "neden": neden, "puan": puan, "eslesen": eslesen,
            "ucuz_cok_satan": ucuz_cok_satan,
            "kriterler": {k: {"gecti": g, "not": n, "agirlik": AGIRLIK[k]} for k, (g, n) in d.items()},
            "fiyatlar": [{"urun": n, "fiyat": v, **bd, "kaynak": u} for n, v, bd, u in priced]}
