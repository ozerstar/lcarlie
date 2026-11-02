"""Finans Merkezi: the three books in one view without counting money twice (owner, 02.11.2026).

Owner: "şirketler arası transferler konsolide gelir veya gider olarak sayılmamalı; şahsi hesap
hareketleri şirket giderlerine karıştırılmamalı". Nothing here changes how a single book is counted —
money_ledger still decides that. Only when two books are shown together is the money that moved between
them (owner ↔ company, Lemos ↔ MOY) set aside as internal, and it stays visible with its reason.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from expense_vault import ZONE, ExpenseError, _connect
from money_ledger import (BOOKS, CATEGORIES, IN_CATEGORIES, NOT_COUNTED, OUT_CATEGORIES, SCOPES, _links,
                          _MOVEMENT_COLUMNS, net_links)

WORKSPACES = {"tumu": ("kisisel", "lemos", "moy"), "sirketler": ("lemos", "moy"), "sahsi": ("kisisel",),
              "lemos": ("lemos",), "moy": ("moy",)}
OWNER_KEYS = ("muratozeryildiz",)
_COMPANY = {"lemos": re.compile(r"^lemos"), "moy": re.compile(r"^moydan")}
# owner ↔ company money, named from each side
TO_OWNER = ("sirketten",)              # personal book: came from a company
FROM_OWNER = ("ortaktan",)             # company book: came from the owner
TO_OWNER_OUT = ("ortaga",)             # company book: sent to the owner
VIEWS = ("day", "week", "month", "year", "range")


def period(view, day, start=None, end=None):
    """[start, end) of the period and of the one before it, same length."""
    if view == "day":
        s, e = day, day + timedelta(days=1)
    elif view == "week":
        s = day - timedelta(days=day.weekday())
        e = s + timedelta(days=7)
    elif view == "month":
        s = day.replace(day=1)
        e = (s + timedelta(days=32)).replace(day=1)
    elif view == "year":
        s, e = date(day.year, 1, 1), date(day.year + 1, 1, 1)
    elif view == "range":
        if not start or not end or end < start:
            raise ExpenseError("Başlangıç ve bitiş tarihi gerekli; bitiş başlangıçtan önce olamaz.")
        if (end - start).days > 1100:
            raise ExpenseError("En fazla üç yıllık aralık seçilebilir.")
        s, e = start, end + timedelta(days=1)
    else:
        raise ExpenseError("Dönem gün, hafta, ay, yıl ya da tarih aralığı olmalı.")
    if view == "month":
        ps = (s - timedelta(days=1)).replace(day=1)
        return s, e, ps, s
    if view == "year":
        return s, e, date(s.year - 1, 1, 1), s
    return s, e, s - (e - s), s


def internal_reason(row, books, pair_ids):
    """Why a row is money between the shown books (None: it is real income or spending). Pure."""
    if len(books) < 2:
        return None
    book, key, category = row.get("book", "kisisel"), row.get("party_key") or "", row.get("category") or ""
    companies = [b for b in books if b != "kisisel"]
    if "kisisel" in books and companies:
        if row["id"] in pair_ids:
            return "Şirket ↔ şahsi aktarım"
        if book == "kisisel" and (category in TO_OWNER or any(_COMPANY[c].match(key) for c in companies)):
            return "Şirket ↔ şahsi aktarım"
        if book in companies and (category in FROM_OWNER + TO_OWNER_OUT or key in OWNER_KEYS):
            return "Şirket ↔ şahsi aktarım"
    if "lemos" in books and "moy" in books and book in ("lemos", "moy"):
        other = "moy" if book == "lemos" else "lemos"
        if _COMPANY[other].match(key):
            return "Grup içi (Lemos ↔ MOY)"
    return None


def _month_keys(end, count=12):
    last = (end - timedelta(days=1)).replace(day=1)
    keys = []
    for _ in range(count):
        keys.append(last.strftime("%Y-%m"))
        last = (last - timedelta(days=1)).replace(day=1)
    return keys[::-1]


def _group(rows, key, labels=None):
    out = {}
    for row in rows:
        name = row.get(key) or ""
        item = out.setdefault(name, {"key": name, "label": (labels or {}).get(name, name or "Belirlenmedi"),
                                     "total": 0, "count": 0})
        item["total"] += row["amount_cents"]
        item["count"] += 1
    return sorted(out.values(), key=lambda item: -item["total"])


def summarize(rows, books, start, end, prev_start, prev_end, pair_ids=frozenset()):
    """Pure: everything the overview pages show, from movement dicts (tx_date: date)."""
    marked = []
    for row in (r for r in rows if r.get("book", "kisisel") in books):
        reason = None if row["category"] in NOT_COUNTED else internal_reason(row, books, pair_ids)
        marked.append(dict(row, internal=reason))
    counted = [r for r in marked if r["category"] not in NOT_COUNTED and not r["internal"]]
    current = [r for r in counted if start <= r["tx_date"] < end]
    previous = [r for r in counted if prev_start <= r["tx_date"] < prev_end]
    total = lambda rs, d: sum(r["amount_cents"] for r in rs if r["direction"] == d)
    out_rows = [r for r in current if r["direction"] == "out"]
    in_rows = [r for r in current if r["direction"] == "in"]
    months = _month_keys(end)
    monthly = {m: {"month": m, "in": 0, "out": 0} for m in months}
    for r in counted:
        m = r["tx_date"].strftime("%Y-%m")
        if m in monthly:
            monthly[m][r["direction"]] += r["amount_cents"]
    per_book = {b: {"key": b, "label": BOOKS[b], "in": 0, "out": 0} for b in books}
    for r in current:
        per_book[r.get("book", "kisisel")][r["direction"]] += r["amount_cents"]
    accounts = {}
    for r in marked:
        a = accounts.setdefault((r.get("book", "kisisel"), r["account"]), {
            "book": r.get("book", "kisisel"), "book_label": BOOKS[r.get("book", "kisisel")], "name": r["account"],
            "count": 0, "last": None, "in": 0, "out": 0})
        a["count"] += 1
        a["last"] = max(a["last"] or r["tx_date"], r["tx_date"])
        if start <= r["tx_date"] < end and r["category"] not in NOT_COUNTED and not r["internal"]:
            a[r["direction"]] += r["amount_cents"]
    in_period = [r for r in marked if start <= r["tx_date"] < end]
    internal = [r for r in in_period if r["internal"] or r["category"] in NOT_COUNTED]
    in_total, out_total = total(current, "in"), total(current, "out")
    # both sides of owner ↔ company money: when they differ, one side's account is not in the ledger
    # (2026: MOY sent the owner 904 bin TL, his recorded accounts show 300 bin) — said, not hidden
    side = lambda book_is_personal, d: sum(r["amount_cents"] for r in in_period if r["internal"] == "Şirket ↔ şahsi aktarım"
                                           and (r.get("book", "kisisel") == "kisisel") == book_is_personal and r["direction"] == d)
    owner_flow = {"company_to_owner": side(False, "out"), "owner_received": side(True, "in"),
                  "owner_to_company": side(True, "out"), "company_received": side(False, "in")}
    return {
        "owner_flow": owner_flow,
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "prev_start": prev_start.isoformat(), "prev_end": (prev_end - timedelta(days=1)).isoformat(),
        "books": list(books), "in_total": in_total, "out_total": out_total, "net": in_total - out_total,
        "prev_in_total": total(previous, "in"), "prev_out_total": total(previous, "out"),
        "count": len(current), "internal_total": sum(r["amount_cents"] for r in internal), "internal_count": len(internal),
        "by_category": _group(out_rows, "category", CATEGORIES),
        "in_by_category": _group(in_rows, "category", CATEGORIES),
        "by_scope": _group(out_rows, "scope", SCOPES), "by_book": list(per_book.values()),
        "top_parties": _group(out_rows, "party")[:15],
        "monthly": [monthly[m] for m in months],
        "accounts": sorted(({**a, "last": a["last"].isoformat() if a["last"] else None} for a in accounts.values()),
                           key=lambda a: (list(BOOKS).index(a["book"]), -(a["in"] + a["out"]))),
        "movements": [dict(r, tx_date=r["tx_date"].isoformat()) for r in
                      sorted(in_period, key=lambda r: (r["tx_date"], r["amount_cents"]), reverse=True)],
    }


def overview(owner, workspace="tumu", view="month", day=None, start=None, end=None):
    if workspace not in WORKSPACES:
        raise ExpenseError("Çalışma alanı geçersiz.")
    if view not in VIEWS:
        raise ExpenseError("Dönem geçersiz.")
    books = WORKSPACES[workspace]
    try:
        day = date.fromisoformat(day) if day else datetime.now(ZONE).date()
        start = date.fromisoformat(start) if start else None
        end = date.fromisoformat(end) if end else None
    except ValueError:
        raise ExpenseError("Tarih geçersiz.") from None
    s, e, ps, pe = period(view, day, start, end)
    since = min(ps, date.fromisoformat(_month_keys(e)[0] + "-01"))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT {_MOVEMENT_COLUMNS} FROM core.jarvis_money_movement
            WHERE owner=%s AND book = ANY(%s) AND tx_date >= %s AND tx_date < %s""", (owner, list(books), since, e))
        rows = [dict(row) for row in cur.fetchall()]  # before _links(), which reuses the cursor
        links = _links(cur, owner)
        cur.execute("""SELECT company_id, personal_id FROM core.jarvis_money_transfer
            WHERE owner=%s AND status <> 'rejected'""", (owner,))
        pairs = frozenset(i for row in cur.fetchall() for i in (row["company_id"], row["personal_id"]))
    result = summarize(net_links(rows, links), books, s, e, ps, pe, pairs)
    result.update({"workspace": workspace, "view": view, "categories": CATEGORIES, "out_categories": OUT_CATEGORIES,
                   "in_categories": IN_CATEGORIES, "scopes": SCOPES, "book_labels": BOOKS,
                   "not_counted": list(NOT_COUNTED)})
    return result
