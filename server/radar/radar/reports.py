"""Raporlar: günlük rakip bölümü, aylık değişim raporu, sağlık kontrolü ve birleşik sabah özeti.
Rapora giren her bilgi bir kaynak linkiyle gelir."""
import datetime as dt
import json
import os
import shutil
import sqlite3

from . import outbox
from .db import jdump, jload
from .util import iso, now, parse_dt

ETIKET = {"fiyat_bandi": "Fiyat bandı", "yeni_giris": "Yeni giriş", "dogal": "Doğal içerik",
          "tedavi_benzeri": "Bakım/onarım (ilaç değil)", "kanal": "Eczane/Rossmann", "buyume": "Hızlı büyüme",
          "reklam": "Yoğun reklam", "doktor_eczaci": "Klinik konumlandırma", "yabanci": "Yurt dışı"}


def _link(conn, brand_id):
    r = conn.execute("SELECT source_url FROM observations WHERE brand_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1",
                     (brand_id,)).fetchone()
    return r["source_url"] if r else None


def brand_line(conn, b):
    d = jload(b["detail"], {})
    tags = [ETIKET[k] for k, v in d.get("kriterler", {}).items() if v.get("gecti")]
    if d.get("ucuz_cok_satan"):
        tags.append("Ucuz ama çok satan")
    link = _link(conn, b["id"])
    return f"• {b['name']} — puan {b['score']} [{', '.join(tags) or '-'}] (#{b['id']})\n  {link}"


def daily_competitors(conn, cfg, mark=True):
    lines = []
    cands = conn.execute("SELECT * FROM brands WHERE status='candidate' AND reported_at IS NULL "
                         "ORDER BY score DESC LIMIT ?", (cfg["daily_top_n"],)).fetchall()
    if cands:
        lines.append("🆕 Yeni aday markalar (onayınızı bekliyor):")
        lines += [brand_line(conn, b) for b in cands]
        yeni = [b["name"] for b in cands if jload(b["detail"], {}).get("kriterler", {}).get("yeni_giris", {}).get("gecti")]
        if yeni:
            lines.append("⚠️ Bugün yeni giren: " + ", ".join(yeni))
    old = conn.execute("SELECT COUNT(*) n FROM brands WHERE status='candidate' AND first_seen<?",
                       (iso(now() - dt.timedelta(days=cfg["candidate_reminder_days"])),)).fetchone()["n"]
    if old:
        lines.append(f"⏳ {old} aday {cfg['candidate_reminder_days']} günden uzun süredir onay bekliyor (radar adaylar).")
    al = conn.execute("SELECT * FROM alerts WHERE briefed=0 ORDER BY id").fetchall()
    if al:
        lines.append("📌 Teyitli değişiklikler:")
        lines += [f"• {a['text']}\n  {' | '.join(jload(a['sources'], []))}" for a in al]
    pend = conn.execute("SELECT COUNT(*) n FROM pending_changes WHERE status='pending'").fetchone()["n"]
    if pend:
        lines.append(f"🔁 {pend} değişiklik ikinci tarama ile teyit bekliyor.")
    if mark:
        for b in cands:
            conn.execute("UPDATE brands SET reported_at=? WHERE id=?", (iso(now()), b["id"]))
        conn.execute("UPDATE alerts SET briefed=1 WHERE briefed=0")
        conn.commit()
    return lines


def kisa_ozet(conn, cfg):
    """WhatsApp şablonu için 5 tek satırlık değer: tarih, rakip, müşteri adayı, onay bekleyen, satış.

    Meta şablon değerinde satır sonu/sekme olamaz ve her değer en çok 1024 bayt; tam özet Jarvis panelinde.
    """
    t = now()
    gun = iso(t - dt.timedelta(hours=26))
    ad = conn.execute("SELECT name, score FROM brands WHERE status='candidate' AND first_seen>=? "
                      "ORDER BY score DESC LIMIT 4", (gun,)).fetchall()
    toplam_aday = conn.execute("SELECT COUNT(*) n FROM brands WHERE status='candidate'").fetchone()["n"]
    al = conn.execute("SELECT COUNT(*) n FROM alerts WHERE created_at>=?", (gun,)).fetchone()["n"]
    rakip = (f"{len(ad)} yeni aday" + (": " + ", ".join(f"{b['name']} ({b['score']})" for b in ad) if ad else "")
             + (f"; {al} teyitli fiyat/ürün değişikliği" if al else ""))
    fs = [r["source"] for r in conn.execute("SELECT DISTINCT source FROM source_health WHERE ok=0 AND checked_at>=?",
                                            (gun,)).fetchall()][:4]
    if fs:
        rakip += "; taranamayan: " + ", ".join(fs)
    ld = conn.execute("SELECT COUNT(*) n FROM leads WHERE found_at>=?", (gun,)).fetchone()["n"]
    musteri = f"{ld} yeni eczane/klinik adayı" if ld else "yeni aday yok"
    bekleyen = len(outbox.pending(conn))
    onay = f"{bekleyen} mesaj taslağı, {toplam_aday} aday marka"
    satis = "satış özeti yok"
    yol = os.path.join(os.path.dirname(cfg["db_path"]), "satis_ozet.json")
    if os.path.exists(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                satis = "; ".join(f"{k}: {v}" for k, v in json.load(f).items())
        except (OSError, ValueError):
            pass
    return [" ".join(str(x).split())[:1000] or "-" for x in (t.strftime("%d.%m.%Y"), rakip, musteri, onay, satis)]


def morning_brief(conn, cfg, mark=True):
    t = now()
    parts = [f"☀️ L'CARLİÉ Sabah Özeti — {t.strftime('%d.%m.%Y')}"]
    satis = os.path.join(os.path.dirname(cfg["db_path"]), "satis_ozet.json")
    if os.path.exists(satis):  # Jarvis satış verisini buraya yazarsa özete girer
        try:
            with open(satis, encoding="utf-8") as f:
                s = json.load(f)
            parts.append("🛒 Satış: " + "; ".join(f"{k}: {v}" for k, v in s.items()))
        except (OSError, ValueError):
            parts.append("🛒 Satış özeti okunamadı.")
    rk = daily_competitors(conn, cfg, mark)
    parts.append("\n".join(["🔎 RAKİP RADARI"] + (rk or ["Bugün yeni bulgu yok."])))
    leads = conn.execute("SELECT * FROM leads WHERE briefed=0 ORDER BY id").fetchall()
    if leads:
        ls = ["🤝 YENİ MÜŞTERİ ADAYLARI"] + [f"• {l['name']} ({l['type']}) — {l['address']}\n  {l['source_url']}"
                                             for l in leads[:10]]
        parts.append("\n".join(ls))
    rc = conn.execute("SELECT * FROM reg_changes WHERE briefed=0").fetchall()
    if rc:
        parts.append("\n".join(["📜 MEVZUAT (TİTCK) DEĞİŞİKLİĞİ"] +
                               [f"• {x}" for r in rc for x in jload(r["lines"], [])[:5]] +
                               [r["url"] for r in rc]))
    cd = conn.execute("SELECT status, COUNT(*) n FROM content_drafts WHERE briefed=0 GROUP BY status").fetchall()
    if cd:
        parts.append("✍️ İçerik: " + ", ".join(f"{r['n']} {r['status']}" for r in cd) + " (radar icerik)")
    pa = outbox.pending(conn)
    if pa:
        parts.append(f"✅ ONAY BEKLEYEN {len(pa)} mesaj (radar mesajlar → radar onayla-mesaj <id>)")
    fs = conn.execute("SELECT DISTINCT source FROM source_health WHERE ok=0 AND checked_at>=?",
                      (iso(t - dt.timedelta(days=1)),)).fetchall()
    if fs:
        parts.append("⚠️ Taranamayan kaynaklar: " + ", ".join(r["source"] for r in fs))
    if mark:
        conn.execute("UPDATE leads SET briefed=1 WHERE briefed=0")
        conn.execute("UPDATE reg_changes SET briefed=1 WHERE briefed=0")
        conn.execute("UPDATE content_drafts SET briefed=1 WHERE briefed=0")
        conn.commit()
    return "\n\n".join(parts)


# ---------------- Aylık ----------------

def _snapshot(conn, brand_id):
    data = {"fiyat": {}, "fiyat_kaynak": {}, "urunler": [], "kanallar": [], "reklam": None, "yorum": None, "takipci": None}
    for p in conn.execute("SELECT * FROM products WHERE brand_id=?", (brand_id,)):
        o = conn.execute("SELECT value_num, source_url FROM observations WHERE product_id=? AND kind='price' AND verified=1"
                         " ORDER BY fetched_at DESC, id DESC LIMIT 1", (p["id"],)).fetchone()
        seen = conn.execute("SELECT 1 FROM observations WHERE product_id=? AND verified=1 LIMIT 1", (p["id"],)).fetchone()
        if seen:
            data["urunler"].append(p["name"])
        if o:
            data["fiyat"][p["name"]] = o["value_num"]
            data["fiyat_kaynak"][p["name"]] = o["source_url"]
    data["kanallar"] = sorted({r["value_text"] for r in conn.execute(  # son 45 günde görülen kanallar
        "SELECT value_text FROM observations WHERE brand_id=? AND kind='channel' AND fetched_at>=?",
        (brand_id, iso(now() - dt.timedelta(days=45))))})
    for k, key in (("ad_count", "reklam"), ("review_count", "yorum"), ("follower_count", "takipci")):
        o = conn.execute("SELECT value_num FROM observations WHERE brand_id=? AND kind=? ORDER BY fetched_at DESC, id DESC LIMIT 1",
                         (brand_id, k)).fetchone()
        data[key] = o["value_num"] if o else None
    data["urunler"].sort()
    return data


def _diff(a, b):
    """a = önceki ay, b = bu ay → (değişiklik listesi, önem puanı)"""
    ch, w = [], 0
    for n, v in b["fiyat"].items():
        if n in a["fiyat"] and abs(v - a["fiyat"][n]) > a["fiyat"][n] * 0.01:
            pct = (v - a["fiyat"][n]) / a["fiyat"][n] * 100
            ch.append(f"Fiyat: {n} {a['fiyat'][n]:,.0f} → {v:,.0f} TL (%{pct:+.0f})  {b['fiyat_kaynak'].get(n, '')}")
            w += min(abs(pct), 50) / 10
    new = sorted(set(b["urunler"]) - set(a["urunler"]))
    gone = sorted(set(a["urunler"]) - set(b["urunler"]))
    if new:
        ch.append("Yeni ürün: " + ", ".join(new)); w += 3 * len(new)
    if gone:
        ch.append("Görülmeyen ürün: " + ", ".join(gone)); w += 1
    ka, kb = set(a["kanallar"]), set(b["kanallar"])
    if kb - ka:
        ch.append("Yeni kanal: " + ", ".join(sorted(kb - ka))); w += 2
    if ka - kb:
        ch.append("Kanaldan çıkış: " + ", ".join(sorted(ka - kb))); w += 2
    for key, lbl in (("reklam", "Aktif reklam"), ("yorum", "Yorum"), ("takipci", "Takipçi")):
        x, y = a.get(key), b.get(key)
        if x and y is not None and abs(y - x) / x >= 0.2:
            ch.append(f"{lbl}: {x:,.0f} → {y:,.0f} (%{(y - x) / x * 100:+.0f})"); w += 1.5
    return ch, w


def monthly(conn, cfg, month=None):
    month = month or now().strftime("%Y-%m")
    rows, top = [], []
    for b in conn.execute("SELECT * FROM brands WHERE status IN ('active','passive') ORDER BY name").fetchall():
        snap = _snapshot(conn, b["id"])
        conn.execute("INSERT OR REPLACE INTO snapshots(brand_id,month,data) VALUES(?,?,?)", (b["id"], month, jdump(snap)))
        prev = conn.execute("SELECT data FROM snapshots WHERE brand_id=? AND month<? ORDER BY month DESC LIMIT 1",
                            (b["id"], month)).fetchone()
        if not prev:
            rows.append((b["name"], ["İlk aylık kayıt (karşılaştırma gelecek ay)"]))
            continue
        ch, w = _diff(jload(prev["data"]), snap)
        if ch:
            conn.execute("UPDATE brands SET quiet_months=0, status='active' WHERE id=?", (b["id"],))
            rows.append((b["name"], ch))
            top.append((w, b["name"], ch[0]))
        else:
            q = b["quiet_months"] + 1
            st = "passive" if q >= cfg["passive_after_quiet_months"] else b["status"]
            conn.execute("UPDATE brands SET quiet_months=?, status=? WHERE id=?", (q, st, b["id"]))
            rows.append((b["name"], [f"Değişiklik yok ({q}. sessiz ay)" + (" → pasife alındı" if st == "passive" else "")]))
    conn.commit()
    top.sort(reverse=True)
    md = [f"# L'CARLİÉ Rakip Aylık Rapor — {month}", "", "## Öne çıkan 5 değişiklik"]
    md += [f"{i}. **{n}** — {c}" for i, (_, n, c) in enumerate(top[:5], 1)] or ["Bu ay kayda değer değişiklik yok."]
    md += ["", "## Marka bazlı detay"]
    for n, ch in rows:
        md.append(f"### {n}")
        md += [f"- {c}" for c in ch]
    text = "\n".join(md)
    os.makedirs(cfg["reports_dir"], exist_ok=True)
    path = os.path.join(cfg["reports_dir"], f"aylik-{month}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    summary = f"📊 Aylık rakip raporu ({month})\n" + "\n".join(
        f"{i}. {n}: {c}" for i, (_, n, c) in enumerate(top[:5], 1)) if top else f"📊 Aylık rapor ({month}): kayda değer değişiklik yok."
    outbox.to_owner(conn, cfg, summary, f"Aylık rakip raporu {month}", ref=f"aylik:{month}")
    return path, text


# ---------------- Sağlık / yedek ----------------

def health(conn, cfg):
    t = now()
    week = iso(t - dt.timedelta(days=7))
    out = []
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    out.append(f"Veritabanı bütünlüğü: {ic}")
    for r in conn.execute("SELECT source, SUM(ok) ok, COUNT(*) n, MAX(CASE WHEN ok=1 THEN checked_at END) last_ok "
                          "FROM source_health WHERE checked_at>=? GROUP BY source", (week,)):
        fail = r["n"] - r["ok"]
        state = "✅" if fail == 0 else ("⚠️" if r["ok"] else "❌")
        out.append(f"{state} {r['source']}: {r['ok']}/{r['n']} başarılı, son başarı: {r['last_ok'] or 'yok'}")
    last_obs = conn.execute("SELECT MAX(fetched_at) t FROM observations").fetchone()["t"]
    if not last_obs or parse_dt(last_obs) < t - dt.timedelta(days=3):
        out.append(f"❌ Son 3 günde hiç gözlem gelmedi (son: {last_obs or 'hiç'}) — Jarvis tarama ajanı çalışmıyor olabilir.")
    rej = conn.execute("SELECT COUNT(*) n FROM observations WHERE fetched_at>=?", (week,)).fetchone()["n"]
    out.append(f"Son 7 günde kabul edilen gözlem: {rej}")
    bdir = cfg["backup"]["dir"]
    bks = sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []
    out.append(f"Son yedek: {bks[-1] if bks else '❌ yedek yok'}")
    return "\n".join(out)


def backup(conn, cfg):
    d = cfg["backup"]["dir"]
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"radar-{now().strftime('%Y%m%d-%H%M')}.db")
    dst = sqlite3.connect(path)
    conn.backup(dst)
    dst.close()
    files = sorted(f for f in os.listdir(d) if f.startswith("radar-"))
    for f in files[:-cfg["backup"]["keep"]]:
        os.remove(os.path.join(d, f))
    return path


# ---------------- Jarvis paneli ----------------

def panel(conn, cfg):
    """Jarvis 'Üretilenler' sayfası için salt-okunur özet (data/panel.json).

    Panel SQLite'a doğrudan bağlanmaz (WAL dosyası yazma izni ister); Radar her işten sonra
    bu dosyayı yeniler. Kişi verisi (lead telefonu/adresi) dosyaya yazılmaz, yalnız sayısı.
    """
    t = now()
    son = conn.execute("SELECT body, created_at FROM outbox WHERE ref LIKE 'ozet:%' ORDER BY id DESC LIMIT 1").fetchone()
    adaylar = [{"id": b["id"], "ad": b["name"], "puan": b["score"], "satir": brand_line(conn, b)}
               for b in conn.execute("SELECT * FROM brands WHERE status='candidate' ORDER BY score DESC LIMIT 20")]
    uyarilar = [{"metin": a["text"], "kaynak": jload(a["sources"], []), "zaman": a["created_at"]}
                for a in conn.execute("SELECT * FROM alerts WHERE created_at>=? ORDER BY id DESC LIMIT 20",
                                      (iso(t - dt.timedelta(days=14)),))]
    mevzuat = [{"url": r["url"], "satirlar": jload(r["lines"], [])[:5], "zaman": r["found_at"]}
               for r in conn.execute("SELECT * FROM reg_changes ORDER BY id DESC LIMIT 5")]
    saglik = [{"kaynak": r["source"], "basarili": r["ok"], "toplam": r["n"]}
              for r in conn.execute("SELECT source, SUM(ok) ok, COUNT(*) n FROM source_health WHERE checked_at>=? "
                                    "GROUP BY source ORDER BY source", (iso(t - dt.timedelta(days=7)),))]
    izlenen = conn.execute("SELECT COUNT(*) n FROM brands WHERE status IN ('active','passive')").fetchone()["n"]
    d = {"uretim": iso(t), "sabah_ozeti": dict(son) if son else None, "adaylar": adaylar, "uyarilar": uyarilar,
         "mevzuat": mevzuat, "kaynak_sagligi": saglik, "izlenen_marka": izlenen,
         "onay_bekleyen_mesaj": len(outbox.pending(conn))}
    yol = os.path.join(os.path.dirname(cfg["db_path"]), "panel.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(gecici, yol)
    return yol
