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
                          _MOVEMENT_COLUMNS, net_links, plain)

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



# owner, 03.11.2026: "şahsımı, MOY'u, Lemos'u ve L'CARLIÉ'yi 4 farklı kurum gibi yap; şu anki hâlde her şey
# birbirine giriyor". Each kurum is a company of its own: what one kurum's account paid for another kurum
# (the row's scope says whose) is that other kurum's income or spending, and money between kurums is
# shown apart, never as anyone's income or spending.
ENTITIES = {"sahsi": "kisisel", "moy": "moy", "lemos": "lemos", "lcarlie": "lcarlie"}
ENTITY_LABELS = {"kisisel": "Şahsım", "moy": "MOY", "lemos": "Lemos", "lcarlie": "L'CARLIÉ"}
BETWEEN = "Kurumlar arası"


def entity_of(row):
    """Whose money a row is, as a kurum key (pure). L'CARLIÉ has no account: its scope decides."""
    book, scope = row.get("book", "kisisel"), row.get("scope") or ""
    if scope == "lcarlie":
        return "lcarlie"
    if book == "kisisel" and scope in ("lemos", "moy"):
        return scope
    return book


def between_of(row, pair_ids):
    """The other kurum when a row is money between kurums ("" when the company is not named), else None."""
    book, key, category = row.get("book", "kisisel"), row.get("party_key") or "", row.get("category") or ""
    if book == "kisisel":
        named = next((c for c in ("lemos", "moy") if _COMPANY[c].match(key)), None)
        if named or category in TO_OWNER or row["id"] in pair_ids:
            return named or ""
        return None
    other = "moy" if book == "lemos" else "lemos"
    if _COMPANY[other].match(key):
        return other
    if category in FROM_OWNER + TO_OWNER_OUT or key in OWNER_KEYS or row["id"] in pair_ids:
        return "kisisel"
    return None


def entity_view(rows, entity, pair_ids=frozenset()):
    """The rows of one kurum (pure): its own money counted, money between kurums set aside with its reason."""
    target = ENTITIES[entity]
    out = []
    for row in rows:
        owner, bank = entity_of(row), row.get("book", "kisisel")
        if target not in (owner, bank):
            continue
        r = dict(row, book=target, paid_from=bank if bank != target else "")
        if row.get("category") not in NOT_COUNTED:
            other = between_of(row, pair_ids)
            if other is not None:  # seen from this kurum the other side is the paying account, if not its own
                other = bank if bank != target else other
                r["internal"] = f"{BETWEEN} · {ENTITY_LABELS.get(other, 'şirket')}"
            elif owner != target:
                word = "ödeme" if row["direction"] == "out" else "tahsilat"
                r["internal"] = f"{BETWEEN} · {ENTITY_LABELS[owner]} adına {word}"
        out.append(r)
    return out

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


_BANKS = (("enpara", "Enpara"), ("deniz", "DenizBank"), ("ziraat", "Ziraat"), ("garanti", "Garanti"), ("akbank", "Akbank"),
          ("yapi ?kredi", "Yapı Kredi"), ("is ?bank|isbank", "İş Bankası"), ("qnb|finansbank", "QNB"), ("teb", "TEB"),
          ("vakif", "VakıfBank"), ("halk", "Halkbank"), ("kuveyt", "Kuveyt Türk"), ("albaraka", "Albaraka"))


def _bank(text):
    t = plain(text or "")
    return next((name for pattern, name in _BANKS if re.search(pattern, t)), "")


def owner_gaps(in_period, pair_ids, statement_starts):
    """Pure: company → owner money with no matching row in the owner's recorded accounts, by reason.

    Owner, 02.11.2026 asked about "şirketten size giden paranın bir kısmı görünmüyor". Measured: every
    MOY transfer after 19.06.2026 matched Enpara one to one; the ones before went to Enpara too, whose
    statement only starts on 19.06 — and two went to DenizBank, which is not in the ledger. The Lemos
    salary arrives with no Lemos-side row (paid from an account not in the ledger): a different gap."""
    shown = [r for r in in_period if r["internal"] == "Şirket ↔ şahsi aktarım"]
    sent = [r for r in shown if r.get("book", "kisisel") != "kisisel" and r["direction"] == "out"]
    own_banks = {_bank(account) for account in statement_starts} - {""}
    first = {}
    for account, day in statement_starts.items():
        bank = _bank(account)
        first[bank] = min(first.get(bank, day), day)
    gaps = {"no_statement": [], "other_bank": [], "unmatched": []}
    matched = 0
    for r in sent:
        if r["id"] in pair_ids:
            matched += r["amount_cents"]
            continue
        bank = _bank(r.get("description") or "") or _bank(r["party"])
        if bank and own_banks and bank not in own_banks:
            gaps["other_bank"].append((r, bank))
        elif bank in first and r["tx_date"] < first[bank]:
            gaps["no_statement"].append((r, bank))
        else:
            gaps["unmatched"].append((r, bank))

    def group(items):
        out = {}
        for r, bank in items:
            g = out.setdefault(bank or "?", {"bank": bank, "total": 0, "count": 0, "first": None, "last": None,
                                             "statement_from": first[bank].isoformat() if bank in first else None})
            g["total"] += r["amount_cents"]
            g["count"] += 1
            g["first"] = min(filter(None, (g["first"], r["tx_date"].isoformat())))
            g["last"] = max(filter(None, (g["last"], r["tx_date"].isoformat())))
        return sorted(out.values(), key=lambda g: -g["total"])

    arrived = [r for r in shown if r.get("book", "kisisel") == "kisisel" and r["direction"] == "in" and r["id"] not in pair_ids
               and r.get("category") != "sirketten"]
    no_company_side = {}
    for r in arrived:
        g = no_company_side.setdefault(r["party"], {"party": r["party"], "total": 0, "count": 0})
        g["total"] += r["amount_cents"]
        g["count"] += 1
    return {"company_to_owner": sum(r["amount_cents"] for r in sent), "matched": matched,
            "no_statement": group(gaps["no_statement"]), "other_bank": group(gaps["other_bank"]),
            "unmatched": group(gaps["unmatched"]),
            "no_company_side": sorted(no_company_side.values(), key=lambda g: -g["total"])}


def summarize(rows, books, start, end, prev_start, prev_end, pair_ids=frozenset(), statement_starts=None, labels=BOOKS):
    """Pure: everything the overview pages show, from movement dicts (tx_date: date)."""
    marked = []
    for row in (r for r in rows if r.get("book", "kisisel") in books):
        reason = None if row["category"] in NOT_COUNTED else (row.get("internal") or internal_reason(row, books, pair_ids))
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
    per_book = {b: {"key": b, "label": labels[b], "in": 0, "out": 0} for b in books}
    for r in current:
        per_book[r.get("book", "kisisel")][r["direction"]] += r["amount_cents"]
    accounts = {}
    for r in marked:
        bank = r.get("paid_from") or r.get("book", "kisisel")
        a = accounts.setdefault((bank, r["account"]), {
            "book": bank, "book_label": labels[bank], "name": r["account"],
            "count": 0, "last": None, "in": 0, "out": 0})
        a["count"] += 1
        a["last"] = max(a["last"] or r["tx_date"], r["tx_date"])
        if start <= r["tx_date"] < end and r["category"] not in NOT_COUNTED and not r["internal"]:
            a[r["direction"]] += r["amount_cents"]
    in_period = [r for r in marked if start <= r["tx_date"] < end]
    internal = [r for r in in_period if r["internal"] or r["category"] in NOT_COUNTED]
    in_total, out_total = total(current, "in"), total(current, "out")
    owner_flow = owner_gaps(in_period, pair_ids, statement_starts or {})
    between = {}
    for r in in_period:
        if (r["internal"] or "").startswith(BETWEEN):
            g = between.setdefault(r["internal"], {"label": r["internal"][len(BETWEEN) + 3:], "in": 0, "out": 0, "count": 0})
            g[r["direction"]] += r["amount_cents"]
            g["count"] += 1
    return {
        "owner_flow": owner_flow,
        "between": sorted(between.values(), key=lambda g: -(g["in"] + g["out"])),
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
                           key=lambda a: (list(labels).index(a["book"]), -(a["in"] + a["out"]))),
        "movements": [dict(r, tx_date=r["tx_date"].isoformat()) for r in
                      sorted(in_period, key=lambda r: (r["tx_date"], r["amount_cents"]), reverse=True)],
    }


def overview(owner, workspace="tumu", view="month", day=None, start=None, end=None):
    entity = workspace in ENTITIES
    if workspace not in WORKSPACES and not entity:
        raise ExpenseError("Çalışma alanı geçersiz.")
    if view not in VIEWS:
        raise ExpenseError("Dönem geçersiz.")
    books = tuple(BOOKS) if entity else WORKSPACES[workspace]
    try:
        day = date.fromisoformat(day) if day else datetime.now(ZONE).date()
        start = date.fromisoformat(start) if start else None
        end = date.fromisoformat(end) if end else None
    except ValueError:
        raise ExpenseError("Tarih geçersiz.") from None
    s, e, ps, pe = period(view, day, start, end)
    since = min(ps, date.fromisoformat(_month_keys(e)[0] + "-01"))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT {_MOVEMENT_COLUMNS}, description FROM core.jarvis_money_movement
            WHERE owner=%s AND book = ANY(%s) AND tx_date >= %s AND tx_date < %s""", (owner, list(books), since, e))
        rows = [dict(row) for row in cur.fetchall()]  # before _links(), which reuses the cursor
        links = _links(cur, owner)
        cur.execute("""SELECT company_id, personal_id FROM core.jarvis_money_transfer
            WHERE owner=%s AND status <> 'rejected'""", (owner,))
        pairs = frozenset(i for row in cur.fetchall() for i in (row["company_id"], row["personal_id"]))
        # when each personal account's statements begin: money sent before that cannot be seen arriving
        cur.execute("""SELECT account, min(tx_date) AS first FROM core.jarvis_money_movement
            WHERE owner=%s AND book='kisisel' GROUP BY account""", (owner,))
        starts = {row["account"]: row["first"] for row in cur.fetchall()}
    rows, labels = net_links(rows, links), BOOKS
    if entity:
        rows, books, labels = entity_view(rows, workspace, pairs), (ENTITIES[workspace],), ENTITY_LABELS
    result = summarize(rows, books, s, e, ps, pe, pairs, starts, labels)
    result.update({"workspace": workspace, "view": view, "categories": CATEGORIES, "out_categories": OUT_CATEGORIES,
                   "in_categories": IN_CATEGORIES, "scopes": SCOPES, "book_labels": labels,
                   "not_counted": list(NOT_COUNTED)})
    return result
