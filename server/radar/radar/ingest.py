"""Jarvis ajanlarının topladığı gözlemleri doğrulayıp veritabanına alır.

Kurallar (hatasızlık):
 1. Kaynak linki + tarama zamanı olmayan gözlem REDDEDİLİR.
 2. Sayısal gözlemde (fiyat, yorum, reklam sayısı) sayı, sayfadan kopyalanan alıntıda
    (excerpt) geçmek zorunda; geçmiyorsa uydurma sayılır ve reddedilir.
 3. İzlenen markada kritik değişiklik (büyük fiyat farkı, yeni ürün) önce 'bekleyen'
    olur; FARKLI bir taramada aynı değer görülürse onaylanır ve uyarı üretilir.
 4. Reddedilen / filtrelenen marka bir daha aday olmaz.
"""
import datetime as dt
import uuid

from . import outbox, rules
from .db import jdump, jload
from .util import iso, norm, now, number_in_text, parse_dt, valid_url

KINDS = {"price", "product", "channel", "ad_count", "review_count", "follower_count", "claim", "not_found"}
NUMERIC = {"price", "ad_count", "review_count", "follower_count"}
MONITORED = ("active", "passive")


def validate(o, cfg, t_now):
    k = o.get("kind")
    if k not in KINDS:
        return f"bilinmeyen tür: {k}"
    if not valid_url(o.get("source_url")):
        return "kaynak linki yok/geçersiz"
    t = parse_dt(o.get("fetched_at"))
    if not t:
        return "tarama zamanı yok/geçersiz"
    if t > t_now + dt.timedelta(minutes=10):
        return "tarama zamanı gelecekte"
    if t < t_now - dt.timedelta(days=cfg["max_obs_age_days"]):
        return "gözlem çok eski"
    if k in NUMERIC:
        try:
            v = float(o.get("value"))
        except (TypeError, ValueError):
            return "sayısal değer yok"
        if v < 0:
            return "negatif değer"
        if k == "price":
            lo, hi = cfg["price_range_tl"]
            if not lo <= v <= hi:
                return f"fiyat makul aralık dışında ({lo}-{hi} TL)"
            if not o.get("product"):
                return "fiyat için ürün adı gerekli"
        if not o.get("excerpt"):
            return "sayfa alıntısı (excerpt) gerekli"
        if not number_in_text(v, o["excerpt"]):
            return "değer alıntıda geçmiyor (uydurma şüphesi)"
    if k == "product" and not o.get("product"):
        return "ürün adı gerekli"
    if k in ("channel", "claim") and not o.get("value"):
        return "değer gerekli"
    return None


def _upsert_brand(conn, bb, t):
    nn = norm(bb["name"])
    row = conn.execute("SELECT * FROM brands WHERE norm_name=?", (nn,)).fetchone()
    texts = [x for x in (bb.get("texts") or []) if x]
    if row is None:
        cur = conn.execute(
            "INSERT INTO brands(name,norm_name,first_seen,last_seen,website,instagram,trendyol_url,origin,"
            "first_seen_hint,texts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (bb["name"].strip(), nn, iso(t), iso(t), bb.get("website"), bb.get("instagram"),
             bb.get("trendyol_url"), bb.get("origin"), bb.get("first_seen_hint"), jdump(texts[:50])))
        return conn.execute("SELECT * FROM brands WHERE id=?", (cur.lastrowid,)).fetchone(), True
    old = jload(row["texts"], [])
    merged = (old + [x for x in texts if x not in old])[-50:]
    conn.execute(
        "UPDATE brands SET last_seen=?, texts=?, website=COALESCE(?,website), instagram=COALESCE(?,instagram),"
        " trendyol_url=COALESCE(?,trendyol_url), origin=COALESCE(?,origin),"
        " first_seen_hint=COALESCE(first_seen_hint,?) WHERE id=?",
        (iso(t), jdump(merged), bb.get("website"), bb.get("instagram"), bb.get("trendyol_url"),
         bb.get("origin"), bb.get("first_seen_hint"), row["id"]))
    return conn.execute("SELECT * FROM brands WHERE id=?", (row["id"],)).fetchone(), False


def _product(conn, brand_id, name, category, t):
    nn = norm(name)
    row = conn.execute("SELECT id FROM products WHERE brand_id=? AND norm_name=?", (brand_id, nn)).fetchone()
    if row:
        conn.execute("UPDATE products SET last_seen=?, category=COALESCE(?,category) WHERE id=?",
                     (iso(t), category, row["id"]))
        return row["id"], False
    cur = conn.execute("INSERT INTO products(brand_id,name,norm_name,category,first_seen,last_seen) "
                       "VALUES(?,?,?,?,?,?)", (brand_id, name.strip(), nn, category, iso(t), iso(t)))
    return cur.lastrowid, True


def _alert(conn, cfg, level, text, sources, instant):
    conn.execute("INSERT INTO alerts(created_at,level,text,sources) VALUES(?,?,?,?)",
                 (iso(now()), level, text, jdump(sources)))
    if instant:
        outbox.to_owner(conn, cfg, f"⚡ L'CARLİÉ Radar uyarısı\n{text}\nKaynak: {' | '.join(sources)}",
                        "Radar uyarısı")


def _pending(conn, brand_id, product_id, kind):
    return conn.execute("SELECT * FROM pending_changes WHERE brand_id=? AND product_id IS ? AND kind=? "
                        "AND status='pending'", (brand_id, product_id, kind)).fetchone()


def _change_detect(conn, cfg, brand, pid, pname, obs_id, o, run_id, is_new_product, rep):
    """İzlenen markada kritik değişiklik → çift doğrulama."""
    t = iso(now())
    kind = o["kind"]
    if pid is None:
        return
    if is_new_product:  # izlenen markada yeni ürün → ikinci taramada teyit beklenir
        conn.execute("UPDATE observations SET verified=0 WHERE id=?", (obs_id,))
        conn.execute("INSERT INTO pending_changes(brand_id,product_id,kind,old_value,new_value,first_obs_id,"
                     "first_run_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (brand["id"], pid, "product", None, None, obs_id, run_id, t))
        rep["bekleyen"] += 1
        return
    pprod = _pending(conn, brand["id"], pid, "product")
    if pprod:
        if pprod["first_run_id"] == run_id:
            conn.execute("UPDATE observations SET verified=0 WHERE id=?", (obs_id,))
            return
        conn.execute("UPDATE pending_changes SET status='confirmed', resolved_at=? WHERE id=?", (t, pprod["id"]))
        conn.execute("UPDATE observations SET verified=1 WHERE product_id=? AND run_id=?", (pid, pprod["first_run_id"]))
        _alert(conn, cfg, "yuksek", f"{brand['name']}: yeni ürün → {pname}", [o["source_url"]], True)
        rep["onaylanan"] += 1
    if kind != "price":
        return
    v = float(o["value"])
    last = conn.execute("SELECT value_num FROM observations WHERE product_id=? AND kind='price' AND verified=1 "
                        "AND id<>? ORDER BY fetched_at DESC, id DESC LIMIT 1", (pid, obs_id)).fetchone()
    pend = _pending(conn, brand["id"], pid, "price")
    if last is None:
        return  # ilk fiyat = taban
    old = last["value_num"]
    pct = (v - old) / old * 100
    if pend:
        if pend["first_run_id"] == run_id:
            conn.execute("UPDATE observations SET verified=0 WHERE id=?", (obs_id,))
            return
        if abs(v - pend["new_value"]) <= pend["new_value"] * 0.01:
            conn.execute("UPDATE pending_changes SET status='confirmed', resolved_at=? WHERE id=?", (t, pend["id"]))
            conn.execute("UPDATE observations SET verified=1 WHERE id IN (?,?)", (obs_id, pend["first_obs_id"]))
            big_drop = pct <= -cfg["instant_alert_price_drop_pct"]
            yon = "indirim" if pct < 0 else "zam"
            _alert(conn, cfg, "yuksek" if big_drop else "orta",
                   f"{brand['name']} / {pname}: {old:,.0f} → {v:,.0f} TL ({yon} %{abs(pct):.0f})",
                   [o["source_url"]], big_drop)
            rep["onaylanan"] += 1
        elif abs(v - old) <= old * 0.01:
            conn.execute("UPDATE pending_changes SET status='discarded', resolved_at=? WHERE id=?", (t, pend["id"]))
        else:
            conn.execute("UPDATE pending_changes SET new_value=?, first_obs_id=?, first_run_id=?, created_at=? "
                         "WHERE id=?", (v, obs_id, run_id, t, pend["id"]))
            conn.execute("UPDATE observations SET verified=0 WHERE id=?", (obs_id,))
        return
    if abs(pct) >= cfg["critical_price_change_pct"]:
        conn.execute("UPDATE observations SET verified=0 WHERE id=?", (obs_id,))
        conn.execute("INSERT INTO pending_changes(brand_id,product_id,kind,old_value,new_value,first_obs_id,"
                     "first_run_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (brand["id"], pid, "price", old, v, obs_id, run_id, t))
        rep["bekleyen"] += 1


def ingest(conn, payload, cfg, book):
    t_now = now()
    run_id = payload.get("run_id") or uuid.uuid4().hex[:12]
    source = payload.get("source", "bilinmiyor")
    conn.execute("INSERT OR IGNORE INTO runs(id,job,source,started_at) VALUES(?,?,?,?)",
                 (run_id, payload.get("job", "tarama"), source, iso(t_now)))
    for s in payload.get("source_status", []):
        conn.execute("INSERT INTO source_health(run_id,source,ok,error,checked_at) VALUES(?,?,?,?,?)",
                     (run_id, s.get("source", source), 1 if s.get("ok") else 0, s.get("error"), iso(t_now)))
    rep = {"run_id": run_id, "kabul": 0, "red": [], "yeni_marka": [], "atlanan": [], "bekleyen": 0, "onaylanan": 0}

    for bb in payload.get("brands", []):
        if not bb.get("name"):
            rep["red"].append({"neden": "marka adı yok"})
            continue
        ex = conn.execute("SELECT status, status_reason FROM brands WHERE norm_name=?", (norm(bb["name"]),)).fetchone()
        if ex and ex["status"] in ("rejected", "filtered"):
            rep["atlanan"].append(f"{bb['name']} ({ex['status']}: {ex['status_reason']})")
            continue
        good = []
        for o in bb.get("observations", []):
            err = validate(o, cfg, t_now)
            if err:
                rep["red"].append({"marka": bb["name"], "tur": o.get("kind"), "urun": o.get("product"), "neden": err})
            else:
                good.append(o)
        brand, created = _upsert_brand(conn, bb, t_now)
        monitored = brand["status"] in MONITORED
        for o in good:
            pid, is_new = (None, False)
            if o.get("product"):
                pid, is_new = _product(conn, brand["id"], o["product"], o.get("category"), t_now)
            if o["kind"] == "not_found":
                continue  # 'bulunamadı' kaydı: veri değil, sadece sayılır
            vnum = float(o["value"]) if o["kind"] in NUMERIC else None
            vtxt = None if o["kind"] in NUMERIC else (str(o.get("value") or "") or None)
            if o["kind"] == "channel" and vtxt:
                vtxt = norm(vtxt)
            cur = conn.execute(
                "INSERT INTO observations(brand_id,product_id,kind,value_num,value_text,source_url,fetched_at,"
                "run_id,excerpt,verified) VALUES(?,?,?,?,?,?,?,?,?,1)",
                (brand["id"], pid, o["kind"], vnum, vtxt, o["source_url"], iso(parse_dt(o["fetched_at"])),
                 run_id, (o.get("excerpt") or "")[:500]))
            rep["kabul"] += 1
            if monitored:
                _change_detect(conn, cfg, brand, pid, o.get("product"), cur.lastrowid, o, run_id, is_new, rep)

        if not monitored and brand["status"] not in ("candidate",):
            ev = rules.evaluate(conn, brand["id"], cfg, book)
            conn.execute("UPDATE brands SET status=?, status_reason=?, score=?, detail=? WHERE id=?",
                         (ev["durum"], ev["neden"], ev["puan"], jdump(ev), brand["id"]))
            if ev["durum"] == "candidate":
                rep["yeni_marka"].append(f"{brand['name']} (puan {ev['puan']})")
        else:
            ev = rules.evaluate(conn, brand["id"], cfg, book)
            if ev["durum"] == "filtered" and brand["status"] == "candidate":
                conn.execute("UPDATE brands SET status='filtered', status_reason=? WHERE id=?",
                             (ev["neden"], brand["id"]))
            else:
                conn.execute("UPDATE brands SET score=?, detail=? WHERE id=?",
                             (ev["puan"], jdump(ev), brand["id"]))
    conn.commit()
    return rep


def expire_pending(conn, cfg):
    limit = iso(now() - dt.timedelta(days=cfg["pending_expire_days"]))
    n = conn.execute("UPDATE pending_changes SET status='expired', resolved_at=? WHERE status='pending' "
                     "AND created_at<?", (iso(now()), limit)).rowcount
    conn.commit()
    return n


def recheck_list(conn):
    """İkinci doğrulama taraması için Jarvis'e verilecek liste."""
    rows = conn.execute(
        "SELECT pc.id, b.name brand, p.name product, pc.kind, pc.old_value, pc.new_value, o.source_url "
        "FROM pending_changes pc JOIN brands b ON b.id=pc.brand_id LEFT JOIN products p ON p.id=pc.product_id "
        "JOIN observations o ON o.id=pc.first_obs_id WHERE pc.status='pending'").fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]
