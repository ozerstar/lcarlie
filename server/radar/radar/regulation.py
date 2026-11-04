"""Mevzuat takibi: TİTCK duyuru sayfalarında yeni satır çıkınca kaydeder."""
import hashlib

from .db import jdump
from .util import html_to_text, http_get, iso, now

ILGILI = ["kozmetik", "ürün güvenlik", "etiket", "reklam", "tanıtım", "beyan", "ÜTS", "üts", "piyasa gözetim"]


def check(conn, cfg, get=http_get):
    out = {"degisen": [], "hata": []}
    for url in cfg["regulation"]["urls"]:
        try:
            text = html_to_text(get(url))
        except Exception as e:
            out["hata"].append(f"{url}: {e}")
            conn.execute("INSERT INTO source_health(run_id,source,ok,error,checked_at) VALUES(?,?,?,?,?)",
                         ("mevzuat", url, 0, str(e), iso(now())))
            continue
        conn.execute("INSERT INTO source_health(run_id,source,ok,error,checked_at) VALUES(?,?,?,?,?)",
                     ("mevzuat", url, 1, None, iso(now())))
        h = hashlib.sha256(text.encode()).hexdigest()
        row = conn.execute("SELECT * FROM reg_pages WHERE url=?", (url,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO reg_pages(url,last_hash,last_text,last_checked) VALUES(?,?,?,?)",
                         (url, h, text, iso(now())))
            continue  # ilk tarama = taban
        if row["last_hash"] != h:
            old = set(row["last_text"].splitlines())
            new_lines = [l for l in text.splitlines() if l not in old and len(l) > 15]
            onemli = [l for l in new_lines if any(k.lower() in l.lower() for k in ILGILI)]
            lines = (onemli or new_lines)[:10]
            if lines:
                conn.execute("INSERT INTO reg_changes(url,found_at,lines) VALUES(?,?,?)",
                             (url, iso(now()), jdump(lines)))
                out["degisen"].append(url)
            conn.execute("UPDATE reg_pages SET last_hash=?, last_text=?, last_changed=? WHERE url=?",
                         (h, text, iso(now()), url))
        conn.execute("UPDATE reg_pages SET last_checked=? WHERE url=?", (iso(now()), url))
    conn.commit()
    return out
