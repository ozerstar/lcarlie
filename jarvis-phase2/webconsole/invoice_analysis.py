"""Invoice contents → the two businesses (owner, 02.11.2026).

Every line (or, when lines could not be read, the whole invoice) carries a theme and a business:
lcarlie / lemos / ortak / belirsiz / grup. Shared ("ortak") costs are split by the period's clear
sales share; "belirsiz" sales (a bare "gıda takviyesi") wait for the owner and are not split;
"grup" (MOY ↔ Lemos) is shown apart, never counted as the company's own revenue or cost.
All amounts are net of VAT.
"""
from collections import defaultdict
from datetime import date

from expense_vault import ExpenseError, _connect

import invoice_topics

DEAD = ("Canceled", "Declined", "Draft", "Return")


def classify_all(owner):
    """(Re)classify every line and every line-less invoice; returns how many changed."""
    changed = 0
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT l.document_id, l.line_no, l.name, l.theme, l.business, l.product, i.box, i.party
            FROM core.jarvis_invoice_line l JOIN core.jarvis_invoice i USING (owner, document_id) WHERE l.owner=%s""", (owner,))
        for row in cur.fetchall():
            theme, business, product = invoice_topics.classify(row["box"], row["name"], row["party"])
            if (theme, business, product) != (row["theme"], row["business"], row["product"]):
                cur.execute("""UPDATE core.jarvis_invoice_line SET theme=%s, business=%s, product=%s
                    WHERE owner=%s AND document_id=%s AND line_no=%s""",
                            (theme, business, product, owner, row["document_id"], row["line_no"]))
                changed += 1
        cur.execute("""SELECT document_id, box, party, theme, business FROM core.jarvis_invoice i WHERE owner=%s
            AND NOT EXISTS (SELECT 1 FROM core.jarvis_invoice_line l WHERE l.owner=i.owner AND l.document_id=i.document_id)""",
                    (owner,))
        for row in cur.fetchall():
            theme, business, _ = invoice_topics.classify(row["box"], "", row["party"])
            if (theme, business) != (row["theme"], row["business"]):
                cur.execute("UPDATE core.jarvis_invoice SET theme=%s, business=%s WHERE owner=%s AND document_id=%s",
                            (theme, business, owner, row["document_id"]))
                changed += 1
    return changed


def _parts(owner, book, start, end):
    """One part per line, or one per line-less invoice: (box, theme, business, product, name, party, net, qty, day)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT i.document_id, i.box, i.issue_date, i.party, i.payable_cents, i.tax_cents, i.theme AS itheme, i.business AS ibusiness,
                l.name, l.theme, l.business, l.product, l.net_cents, l.quantity::float AS quantity
            FROM core.jarvis_invoice i LEFT JOIN core.jarvis_invoice_line l USING (owner, document_id)
            WHERE i.owner=%s AND i.book=%s AND i.issue_date >= %s AND i.issue_date < %s AND i.status <> ALL(%s)""",
                    (owner, book, start, end, list(DEAD)))
        for row in cur.fetchall():
            if row["name"] is None:
                yield {"doc": row["document_id"], "box": row["box"], "theme": row["itheme"] or "diger", "business": row["ibusiness"] or "ortak",
                       "product": "", "name": row["party"], "party": row["party"], "qty": 1,
                       "net": row["payable_cents"] - (row["tax_cents"] or 0), "day": row["issue_date"], "read": False}
            else:
                yield {"doc": row["document_id"], "box": row["box"], "theme": row["theme"] or "diger", "business": row["business"] or "ortak",
                       "product": row["product"], "name": row["name"], "party": row["party"], "qty": row["quantity"] or 0,
                       "net": row["net_cents"], "day": row["issue_date"], "read": True}


CHANNELS = {"dogrudan": "Doğrudan (muayenehane / etkinlik / kurumsal)", "wix": "Web sitesi (Wix)", "trendyol": "Trendyol"}


def _channel_parts(owner, start, end):
    """Wix / Trendyol lines that have no sales invoice of their own (the invoiced ones are counted
    through the invoice). Returns, discounts and coupons come in negative."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT invoice_document_id AS doc, channel FROM core.jarvis_channel_sale
            WHERE owner=%s AND invoice_document_id IS NOT NULL""", (owner,))
        invoiced = {row["doc"]: row["channel"] for row in cur.fetchall()}
        cur.execute("""SELECT channel, kind, sale_date, item, product, business, quantity::float AS quantity, net_cents
            FROM core.jarvis_channel_sale WHERE owner=%s AND invoice_document_id IS NULL AND sale_date >= %s AND sale_date < %s""",
                    (owner, start, end))
        parts = [{"doc": None, "box": "out", "channel": row["channel"],
                  "theme": "kargo" if row["kind"] == "shipping" else invoice_topics.classify("out", row["item"], "")[0],
                  "business": row["business"],
                  "product": row["product"] if row["kind"] in ("sale", "return") else "", "name": row["item"], "party": "",
                  "qty": (row["quantity"] or 0) * (-1 if row["kind"] == "return" else 1), "net": row["net_cents"],
                  "day": row["sale_date"], "read": True} for row in cur.fetchall()]
    return invoiced, parts


def analysis(owner, book="lemos", year=None, month=""):
    year = int(year or date.today().year)
    if month:
        try:
            first = date(year, int(month), 1)
        except ValueError:
            raise ExpenseError("Ay 1-12 olmalı.") from None
        start, end = first, date(year + (first.month == 12), first.month % 12 + 1, 1)
    else:
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    parts = list(_parts(owner, book, start, end))
    invoiced, extra = _channel_parts(owner, start, end) if book == "lemos" else ({}, [])
    for part in parts:
        part["channel"] = invoiced.get(part["doc"], "dogrudan") if part["box"] == "out" else ""
    parts += extra
    channels = defaultdict(lambda: {"net": 0, "from_invoice": 0, "orders_only": 0})
    channel_months = defaultdict(lambda: defaultdict(int))
    sales = defaultdict(int)       # business → net sales
    costs = defaultdict(int)       # business → direct net costs
    themes = defaultdict(lambda: {"in": 0, "out": 0})
    products = defaultdict(lambda: {"qty": 0.0, "net": 0, "lines": 0})
    bought_products = defaultdict(lambda: {"qty": 0.0, "net": 0})
    items_in = defaultdict(int)
    monthly = defaultdict(lambda: defaultdict(int))
    promo, supplements = defaultdict(int), {"in": defaultdict(int), "out": defaultdict(int)}
    unread = 0
    for p in parts:
        key = p["day"].strftime("%Y-%m")
        themes[p["theme"]][p["box"]] += p["net"]
        unread += not p["read"]
        if p["box"] == "out":
            sales[p["business"]] += p["net"]
            if p["business"] != "grup":
                channel = channels[p["channel"]]
                channel["net"] += p["net"]
                channel["from_invoice" if p["doc"] else "orders_only"] += p["net"]
                channel_months[key][p["channel"]] += p["net"]
            monthly[key][f"out_{p['business']}"] += p["net"]
            if p["product"]:
                products[p["product"]]["qty"] += p["qty"]
                products[p["product"]]["net"] += p["net"]
                products[p["product"]]["lines"] += 1
        else:
            costs[p["business"]] += p["net"]
            monthly[key][f"in_{p['business']}"] += p["net"]
            items_in[(p["name"] or p["party"])[:60]] += p["net"]
            if p["product"]:
                bought_products[p["product"]]["qty"] += p["qty"]
                bought_products[p["product"]]["net"] += p["net"]
        if p["theme"] == "promosyon_matbaa" and p["box"] == "in":
            promo[f"{(p['name'] or '')[:40]} · {p['party'][:30]}"] += p["net"]
        if p["theme"] == "takviye_ilac":
            supplements[p["box"]][(p["name"] or p["party"])[:50]] += p["net"]
    clear = sales["lcarlie"] + sales["lemos"]
    share = {b: (sales[b] / clear if clear else 0.5) for b in ("lcarlie", "lemos")}
    shared = costs["ortak"]
    split = {b: round(shared * share[b]) for b in ("lcarlie", "lemos")}
    result = {b: {"label": invoice_topics.BUSINESSES[b], "sales": sales[b], "direct_cost": costs[b],
                  "shared_cost": split[b], "share": round(share[b] * 100, 1),
                  "result": sales[b] - costs[b] - split[b]} for b in ("lcarlie", "lemos")}
    top = lambda d, n=12: sorted(({"name": k, "net": v} for k, v in d.items()), key=lambda x: -x["net"])[:n]
    return {
        "book": book, "year": year, "month": month, "start": start.isoformat(), "end": end.isoformat(),
        "businesses": result, "shared_cost": shared, "unclear_sales": sales["belirsiz"], "group": {
            "in": costs["grup"], "out": sales["grup"]},
        "themes": sorted(({"key": k, "label": invoice_topics.THEMES.get(k, k), **v} for k, v in themes.items()),
                         key=lambda x: -(x["in"] + x["out"])),
        "products_sold": sorted(({"name": k, **v} for k, v in products.items()), key=lambda x: -x["net"]),
        "products_bought": sorted(({"name": k, **v} for k, v in bought_products.items()), key=lambda x: -x["net"])[:15],
        "top_bought": top(items_in), "promo": top(promo, 15),
        "supplements": {"bought": top(supplements["in"], 10), "sold": top(supplements["out"], 10),
                        "bought_total": sum(supplements["in"].values()), "sold_total": sum(supplements["out"].values())},
        "monthly": [{"month": k, **v} for k, v in sorted(monthly.items())],
        "channels": [{"key": k, "label": CHANNELS[k], **v} for k, v in sorted(channels.items(), key=lambda kv: -kv[1]["net"])],
        "channel_monthly": [{"month": k, **v} for k, v in sorted(channel_months.items())],
        "total_sales": sum(v["net"] for v in channels.values()),
        "parts": len(parts), "unread": unread, "method": (
            "KDV hariç tutarlar. Kalemler içeriğine göre ayrıldı; ortak giderler (telefon, araç, ofis, etkinlik, genel "
            "promosyon) iki işe dönemin net satış payına göre bölüştürüldü. Ürünü yazmayan 'gıda takviyesi' satışları "
            "Lemos'un satışı sayıldı; MOY ile grup içi faturalar ayrı tutuldu. Wix ve Trendyol siparişlerinin faturası "
            "varsa fatura sayılır (sipariş yalnız kanalı söyler), yoksa sipariş eklenir; iade, indirim ve kuponlar düşülür. "
            "Trendyol tutarlarında KDV %20 varsayıldı."),
    }
