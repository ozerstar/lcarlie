"""Wix and Trendyol sales next to the company's own sales invoices, counted once (02.11.2026).

Measured that day: 29 of 33 paid Wix orders already had a Lemos e-arşiv (LEM) invoice; only 2 of
27 Trendyol orders did. An order that matches a sales invoice is the invoice's — the invoice amount
counts and the order only names the channel. An order without an invoice is added on its own.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from expense_vault import _connect
from money_ledger import key_of

import invoice_topics

TRENDYOL_KINDS = {"Sale": "sale", "Return": "return", "Discount": "discount", "Coupon": "discount"}
TRENDYOL_VAT = Decimal("1.20")  # settlements carry no VAT; L'CARLIÉ cosmetics are 20 % (flagged vat_assumed)
FIRST_DAY = date(2026, 1, 1)


def _cents(value):
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal(1)))


def business_of(rows):
    """Each line by its product (TYA, 02.11.2026: Trendyol mostly sells Schüssler salts — the clinic's,
    not L'CARLIÉ); shipping, discounts and coupons follow the order's own sold lines."""
    by_order = {}
    for row in rows:
        if row["kind"] in ("sale", "return"):
            _, business, product = invoice_topics.classify("out", row["item"], "")
            row["product"], row["business"] = product, business
            by_order.setdefault((row["channel"], row["order_no"]), []).append((abs(row["gross"]), business))
    for row in rows:
        if row["kind"] not in ("sale", "return"):
            sold = by_order.get((row["channel"], row["order_no"]), [])
            row["product"] = ""
            row["business"] = max(sold)[1] if sold else ("lcarlie" if row["channel"] == "wix" else "lemos")
    return rows


def _store(cur, owner, rows):
    for row in business_of(rows):
        cur.execute("""INSERT INTO core.jarvis_channel_sale (owner,channel,order_no,line_no,kind,sale_date,customer,item,
                quantity,gross_cents,net_cents,vat_assumed,product,business)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (owner,channel,order_no,line_no,kind) DO UPDATE SET sale_date=EXCLUDED.sale_date,
                gross_cents=EXCLUDED.gross_cents, net_cents=EXCLUDED.net_cents, item=EXCLUDED.item, quantity=EXCLUDED.quantity,
                product=EXCLUDED.product, business=EXCLUDED.business, fetched_at=clock_timestamp()""",
                    (owner, row["channel"], row["order_no"], row["line_no"], row["kind"], row["day"], row["customer"][:120],
                     row["item"][:200], row["quantity"], row["gross"], row["net"], row["vat_assumed"], row["product"],
                     row["business"]))


def wix_rows(orders, items):
    """Paid, not archived, not internal. Lines share the order's own net/gross ratio (CR-012: Wix
    'toplam' includes VAT; split, never divide line by line); shipping is its own line."""
    by_order = {}
    for item in items:
        by_order.setdefault(item["siparis_id"], []).append(item)
    rows = []
    for order in orders:
        if order["odeme_durumu"] != "PAID" or order.get("arsivlendi") or order.get("ic_siparis"):
            continue
        gross = _cents(order["toplam"])
        if gross <= 0:
            continue
        ratio = Decimal(gross - _cents(order["kdv"])) / Decimal(gross)
        name = _buyer(order.get("ham") or {})
        shipping = _cents(order.get("kargo_bedeli"))
        lines = by_order.get(order["siparis_id"], [])
        line_gross = [_cents(i.get("net_toplam") if i.get("net_toplam") is not None else i.get("toplam")) for i in lines]
        target, total = gross - shipping, sum(line_gross) or 1
        common = {"channel": "wix", "order_no": str(order["siparis_no"] or order["siparis_id"]),
                  "day": order["olusturma"].date(), "customer": name, "vat_assumed": False}
        for item, part in zip(lines, line_gross, strict=True):
            share = round(target * part / total)
            rows.append({**common, "line_no": str(item["sira"]), "kind": "sale", "item": item["urun_adi"] or "",
                         "quantity": item.get("adet") or 0, "gross": share, "net": int(share * ratio)})
        if shipping:
            rows.append({**common, "line_no": "kargo", "kind": "shipping", "item": "Kargo ücreti", "quantity": 1,
                         "gross": shipping, "net": int(shipping * ratio)})
    return rows


def _buyer(ham):
    for path in (("billingInfo", "contactDetails"), ("shippingInfo", "logistics", "shippingDestination", "contactDetails")):
        node = ham
        for step in path:
            node = node.get(step) if isinstance(node, dict) else None
        if isinstance(node, dict) and (node.get("firstName") or node.get("lastName")):
            return f"{node.get('firstName', '')} {node.get('lastName', '')}".strip()
    return ""


def sync_wix(owner):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT siparis_id, siparis_no, olusturma, odeme_durumu, arsivlendi, ic_siparis, toplam, kdv,
                kargo_bedeli, ham FROM raw.wix_order WHERE olusturma >= %s""", (FIRST_DAY,))
        orders = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT siparis_id, sira, urun_adi, adet, toplam, net_toplam FROM raw.wix_order_item")
        items = [dict(r) for r in cur.fetchall()]
        rows = wix_rows(orders, items)
        _store(cur, owner, rows)
    return len(rows)


def trendyol_rows(settlements, names):
    rows = []
    for kind, item in settlements:
        amount = Decimal(str(item.get("credit") or 0)) - Decimal(str(item.get("debt") or 0))
        when = item.get("orderDate") or item.get("transactionDate") or 0
        gross = _cents(amount)
        rows.append({"channel": "trendyol", "order_no": str(item.get("orderNumber") or item.get("id")),
                     "line_no": str(item.get("id")), "kind": TRENDYOL_KINDS[kind],  # one settlement row each
                     "day": datetime.fromtimestamp(when / 1000, timezone.utc).date(), "customer": "",
                     "item": names.get(str(item.get("barcode") or ""), str(item.get("barcode") or "")),
                     "quantity": 1 if kind in ("Sale", "Return") else 0, "gross": gross,
                     "net": int(Decimal(gross) / TRENDYOL_VAT), "vat_assumed": True})
    return rows


def sync_trendyol(owner, client, *, today=None):
    """client = jarvis.pazaryeri (env_oku, _istek). Read-only; 14-day windows, polite to the 429 limit."""
    import base64
    env = client.env_oku("/etc/lcarlie/trendyol.env")
    seller = env["TRENDYOL_SELLER_ID"]
    auth = base64.b64encode(f"{env['TRENDYOL_API_KEY']}:{env['TRENDYOL_API_SECRET']}".encode()).decode()
    head = {"Authorization": "Basic " + auth, "User-Agent": f"{seller} - SelfIntegration", "Content-Type": "application/json"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT max(sale_date) AS last FROM core.jarvis_channel_sale WHERE owner=%s AND channel='trendyol'", (owner,))
        last = cur.fetchone()["last"]
        cur.execute("SELECT barkod, ad FROM raw.trendyol_urun")
        names = {str(r["barkod"]): r["ad"] or "" for r in cur.fetchall()}
    start = datetime.combine(max(FIRST_DAY, (last or FIRST_DAY) - timedelta(days=45)), datetime.min.time(), timezone.utc)
    end = datetime.combine((today or date.today()) + timedelta(days=1), datetime.min.time(), timezone.utc)
    found, failed = [], []
    for kind in TRENDYOL_KINDS:
        cursor = start
        while cursor < end:
            stop = min(cursor + timedelta(days=14), end)
            for attempt in range(3):
                try:
                    data = json.loads(client._istek(
                        f"https://apigw.trendyol.com/integration/finance/che/sellers/{seller}/settlements"
                        f"?startDate={int(cursor.timestamp() * 1000)}&endDate={int(stop.timestamp() * 1000)}"
                        f"&transactionType={kind}&page=0&size=500", head))
                    found += [(kind, item) for item in data.get("content") or []]
                    break
                except RuntimeError as exc:
                    if "429" not in str(exc) or attempt == 2:
                        failed.append(f"{kind} {cursor:%Y-%m-%d}: {str(exc)[:80]}")
                        break
                    time.sleep(5 * (attempt + 1))
            time.sleep(1)
            cursor = stop
    rows = trendyol_rows(found, names)
    with _connect() as conn, conn.cursor() as cur:
        _store(cur, owner, rows)
    return {"rows": len(rows), "failed": failed}


def find_invoices(orders, invoices, used=()):
    """Pure. orders: [{channel, order_no, day, gross, customer}] (sales only); invoices: Lemos sales
    invoices. Same amount (±1 TL) within -3..+20 days; when the order names a buyer, the name must
    meet the invoice's too; with a name, ±5 % also counts (kargo/rounding). One to one."""
    taken, found = set(used), {}
    by_number = {inv.get("order_no"): inv for inv in invoices if inv.get("order_no")}
    for order in orders:  # the invoice names the order (TYA): no guessing at all
        inv = by_number.get(order["order_no"])
        if inv and inv["document_id"] not in taken:
            taken.add(inv["document_id"])
            found[(order["channel"], order["order_no"])] = inv["document_id"]
    for order in sorted(orders, key=lambda o: (o["day"], o["order_no"])):
        if (order["channel"], order["order_no"]) in found:
            continue
        best = None
        for inv in invoices:
            gap = (inv["issue_date"] - order["day"]).days
            if inv["document_id"] in taken or not -3 <= gap <= 20:
                continue
            exact = abs(inv["payable_cents"] - order["gross"]) <= 100
            named = order["customer"] and _meet(inv["party"], order["customer"])
            if (exact and (named or not order["customer"])) or (named and abs(inv["payable_cents"] - order["gross"]) <= order["gross"] // 20):
                if best is None or abs(gap) < best[0]:
                    best = (abs(gap), inv)
        if best:
            taken.add(best[1]["document_id"])
            found[(order["channel"], order["order_no"])] = best[1]["document_id"]
    return found


def _meet(a, b):
    a, b = key_of(a), key_of(b)
    return len(a) >= 4 and len(b) >= 4 and (a[:7] in b or b[:7] in a)


def match_invoices(owner, book="lemos"):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT channel, order_no, min(sale_date) AS day, sum(gross_cents)::bigint AS gross, max(customer) AS customer
            FROM core.jarvis_channel_sale WHERE owner=%s AND kind IN ('sale','shipping') GROUP BY 1,2""", (owner,))
        orders = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT document_id, issue_date, party, payable_cents, order_no FROM core.jarvis_invoice
            WHERE owner=%s AND book=%s AND box='out'""", (owner, book))
        invoices = [dict(r) for r in cur.fetchall()]
        found = find_invoices(orders, invoices)
        cur.execute("UPDATE core.jarvis_channel_sale SET invoice_document_id=NULL WHERE owner=%s", (owner,))
        for (channel, number), document in found.items():
            cur.execute("""UPDATE core.jarvis_channel_sale SET invoice_document_id=%s
                WHERE owner=%s AND channel=%s AND order_no=%s""", (document, owner, channel, number))
    return {"orders": len(orders), "with_invoice": len(found)}
