"""MOY's e-invoices from Uyumsoft, line by line, and which bank movement paid each one.

Owner, 02.11.2026: "fatura entegrasyonu sayesinde gelen ve giden şirket faturalarını ve
içeriklerini görerek neye ne harcadığımızı görmeyi sağlar". Some MOY invoices are paid from
his personal Enpara, some from the company's TEB account (not in the ledger yet), so a payment
is looked for in every book. The web side only reads; fetching runs in the root job, which
alone can read the Uyumsoft password.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from expense_vault import ExpenseError, _connect
from money_ledger import BOOKS, OUT_CATEGORIES, key_of, plain

_CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
_CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"
PAY_TOLERANCE = 100        # 1 TL: card rounding
PAY_WINDOW = (-5, 60)      # paid up to 5 days before the invoice date, up to 60 days after
FIRST_DAY = date(2025, 1, 1)

# supplier / line words → spending heading (the owner's own rule for the supplier wins)
_GUESS = (
    # order matters: "KEYUBU İNTERNET VE BİLİŞİM" sells domains, "FİL GRUP DİJİTAL REKLAM" prints ads
    ("reklam", r"reklam|dijital baski|meta platforms|facebook|tiktok"),
    ("yazilim", r"keyubu|uyumsoft|yazilim|bilisim|hosting|domain|alan adi|sunucu|lisans|google|microsoft|apple|adobe"),
    ("faturalar", r"enerjisa|elektrik|ttnet|turk telekom|turkcell|vodafone|superonline|dogalgaz|igdas|\baski\b|internet|telefon"),
    ("akaryakit", r"akaryakit|petrol|opet|shell|motorin|benzin|ikmal"),
    ("kargo", r"kargo|lojistik|yurtici|aras|surat"),
    ("ofis", r"bilgisayar|kirtasiye|ofis|ambalaj|mobilya|teknik servis|kagitcilik|mukavva|promosyon|matbaa|sunger"),
    ("market", r"gida|market|ihtiyac|iht\."),
    ("yemek", r"restoran|lokanta|cafe|kafe|yemek"),
    ("ulasim", r"turizm|seyahat|otel|enuygun|havayol|thy|pegasus"),
    ("hizmet", r"danismanlik|musavir|muhasebe|hukuk|trendyol|hepsiburada|kargo hizmet"),
)


def _money(text):
    try:
        return int((Decimal((text or "0").strip()) * 100).quantize(Decimal(1)))
    except InvalidOperation:
        return 0


def parse_ubl(data):
    """The invoice's own lines: name, quantity, unit, net amount, VAT % and VAT amount."""
    root = ElementTree.fromstring(data)
    lines = []
    for number, line in enumerate(root.findall(f"{_CAC}InvoiceLine"), 1):
        quantity = line.find(f"{_CBC}InvoicedQuantity")
        tax = line.find(f"{_CAC}TaxTotal")
        percent = tax.find(f".//{_CBC}Percent") if tax is not None else None
        lines.append({
            "line_no": number,
            "name": (line.findtext(f"{_CAC}Item/{_CBC}Name") or line.findtext(f"{_CAC}Item/{_CBC}Description") or "").strip()[:200],
            "quantity": Decimal((quantity.text or "0").strip()) if quantity is not None else Decimal(0),
            "unit": (quantity.get("unitCode") or "") if quantity is not None else "",
            "net_cents": _money(line.findtext(f"{_CBC}LineExtensionAmount")),
            "vat_percent": Decimal(percent.text.strip()) if percent is not None and (percent.text or "").strip() else None,
            "vat_cents": _money(tax.findtext(f"{_CBC}TaxAmount")) if tax is not None else 0,
        })
    return lines


def guess_category(party, lines, rules=None):
    import re
    if rules and key_of(party) in rules:
        return rules[key_of(party)]
    text = plain(" ".join([party] + [line["name"] for line in lines]))
    for category, pattern in _GUESS:
        if re.search(pattern, text):
            return category
    return "diger"


def _names_meet(a, b):
    """'KEYUBU İNTERNET VE BİLİŞİM…' and the card line 'KEYUBU INTERNET': same first letters."""
    a, b = key_of(a), key_of(b)
    return len(a) >= 4 and len(b) >= 4 and (a[:6] in b or b[:6] in a)


def find_payments(invoices, movements, links=()):
    """Pure: an incoming invoice gets at most one outgoing movement (we paid), a sales invoice
    one incoming movement (the customer paid), with the same amount (±1 TL), the same name and
    a date that fits; a movement settles one invoice. The amount alone is not enough: 3 of 9
    amount-only matches were coincidences (02.11.2026)."""
    taken = {link["movement_id"] for link in links if link["status"] != "rejected"}
    settled = {link["document_id"] for link in links if link["status"] != "rejected"}
    refused = {(link["document_id"], link["movement_id"]) for link in links if link["status"] == "rejected"}
    found = []
    for invoice in sorted(invoices, key=lambda i: (i["issue_date"], i["document_id"])):
        if invoice["document_id"] in settled:
            continue
        wanted, best = ("out" if invoice["box"] == "in" else "in"), None
        for move in movements:
            gap = (move["tx_date"] - invoice["issue_date"]).days
            if (move["direction"] != wanted or move["movement_id"] in taken
                    or (invoice["document_id"], move["movement_id"]) in refused
                    or abs(move["amount_cents"] - invoice["payable_cents"]) > PAY_TOLERANCE
                    or not PAY_WINDOW[0] <= gap <= PAY_WINDOW[1]
                    or not _names_meet(invoice["party"], move["party"])):
                continue
            if best is None or abs(gap) < best[0]:
                best = (abs(gap), move)
        if best:
            taken.add(best[1]["movement_id"])
            found.append({"document_id": invoice["document_id"], "movement_id": best[1]["movement_id"]})
    return found


# ------------------------------------------------------------------ yazma (root işi)
def sync_uyumsoft(owner, source, *, book="moy", today=None):
    """source = tools/uyumsoft (read-only client). New invoices are stored with their lines;
    known ones only get their status refreshed, their UBL is never fetched twice."""
    today = today or date.today()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT document_id FROM core.jarvis_invoice WHERE owner=%s", (owner,))
        known = {row["document_id"] for row in cur.fetchall()}
        cur.execute("SELECT max(issue_date) AS last FROM core.jarvis_invoice WHERE owner=%s AND book=%s", (owner, book))
        last = cur.fetchone()["last"]
        cur.execute("SELECT party_key, category FROM core.jarvis_money_rule WHERE owner=%s AND category<>''", (owner,))
        rules = {row["party_key"]: row["category"] for row in cur.fetchall() if row["category"] in OUT_CATEGORIES}
    start = max(FIRST_DAY, (last or FIRST_DAY) - timedelta(days=45))  # late status changes / late arrivals
    result = {"listed": 0, "added": 0, "skipped": []}
    for box, call_box, scenario in (("in", "inbox", "eInvoice"), ("out", "outbox", "eInvoice"), ("out", "outbox", "eArchive")):
        page = 0
        while True:
            got = source.invoice_list(call_box, start, today, page=page, size=100, scenario=scenario)
            for item in got["items"]:
                result["listed"] += 1
                document = item.get("DocumentId") or ""
                if not document:
                    continue
                if document in known:
                    with _connect() as conn, conn.cursor() as cur:
                        cur.execute("UPDATE core.jarvis_invoice SET status=%s WHERE owner=%s AND document_id=%s",
                                    (item.get("Status", "")[:40], owner, document))
                    continue
                try:
                    ubl = source.invoice_ubl(call_box, document)
                    lines = parse_ubl(ubl)
                except (OSError, ElementTree.ParseError, source.UyumsoftError) as exc:
                    result["skipped"].append(f"{item.get('InvoiceId', document)}: {type(exc).__name__}"[:200])
                    continue
                _store(owner, book, box, scenario, item, ubl, lines, rules)
                known.add(document)
                result["added"] += 1
            page += 1
            if page >= int(got["page"].get("TotalPages") or 1):
                break
    result["payments"] = match_payments(owner)
    return result


def _store(owner, book, box, scenario, item, ubl, lines, rules):
    issue = (item.get("ExecutionDate") or item.get("CreateDateUtc") or "")[:10]
    party = (item.get("TargetTitle") or "").strip()[:200]
    category = "tahsilat" if box == "out" else guess_category(party, lines, rules)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_invoice (owner,document_id,book,box,scenario,number,issue_date,party,
                party_key,party_vkn,payable_cents,tax_cents,currency,status,category,ubl)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (owner, item["DocumentId"], book, box, scenario, item.get("InvoiceId", "")[:40],
             datetime.fromisoformat(issue).date(), party, key_of(party), item.get("TargetTcknVkn", "")[:11],
             _money(item.get("PayableAmount")), _money(item.get("TaxTotal")),
             (item.get("DocumentCurrencyCode") or "TRY")[:3], item.get("Status", "")[:40], category, ubl))
        for line in lines:
            cur.execute("""INSERT INTO core.jarvis_invoice_line (owner,document_id,line_no,name,quantity,unit,net_cents,
                    vat_percent,vat_cents) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (owner, item["DocumentId"], line["line_no"], line["name"], line["quantity"], line["unit"][:10],
                 line["net_cents"], line["vat_percent"], line["vat_cents"]))


def reguess(owner):
    """After the guesses change: re-guess incoming invoices still carrying an automatic heading."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT party_key, category FROM core.jarvis_money_rule WHERE owner=%s AND category<>''", (owner,))
        rules = {row["party_key"]: row["category"] for row in cur.fetchall() if row["category"] in OUT_CATEGORIES}
        cur.execute("""SELECT i.document_id, i.party, i.category, coalesce(array_agg(l.name) FILTER (WHERE l.name IS NOT NULL), '{}') AS names
            FROM core.jarvis_invoice i LEFT JOIN core.jarvis_invoice_line l USING (owner, document_id)
            WHERE i.owner=%s AND i.box='in' AND NOT i.category_set GROUP BY 1,2,3""", (owner,))
        changed = 0
        for row in cur.fetchall():
            new = guess_category(row["party"], [{"name": n} for n in row["names"]], rules)
            if new != row["category"]:
                cur.execute("UPDATE core.jarvis_invoice SET category=%s WHERE owner=%s AND document_id=%s",
                            (new, owner, row["document_id"]))
                changed += 1
        return changed


def import_pdf(owner, book, rows):
    """Invoices read from e-invoice PDFs (Lemos, 02.11.2026): same tables as Uyumsoft, no UBL.
    Rows without a direction, date or total are never filed — the caller lists them."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT party_key, category FROM core.jarvis_money_rule WHERE owner=%s AND category<>''", (owner,))
        rules = {row["party_key"]: row["category"] for row in cur.fetchall() if row["category"] in OUT_CATEGORIES}
        added = 0
        for row in rows:
            if row["box"] not in ("in", "out") or not row["date"] or row["payable_cents"] is None:
                continue
            category = "tahsilat" if row["box"] == "out" else guess_category(row["party"], row["lines"], rules)
            cur.execute("""INSERT INTO core.jarvis_invoice (owner,document_id,book,box,scenario,number,issue_date,party,
                    party_key,party_vkn,payable_cents,tax_cents,currency,status,category)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'TRY','PDF',%s) ON CONFLICT DO NOTHING RETURNING document_id""",
                (owner, row["ettn"], book, row["box"], "eArchive" if row["number"].upper().startswith("LEM") else "eInvoice",
                 row["number"][:40], row["date"], row["party"], key_of(row["party"]), row["party_vkn"][:11],
                 row["payable_cents"], row["tax_cents"], category))
            if cur.fetchone() is None:
                continue
            added += 1
            for line in row["lines"]:
                cur.execute("""INSERT INTO core.jarvis_invoice_line (owner,document_id,line_no,name,quantity,unit,net_cents,
                        vat_percent,vat_cents) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (owner, row["ettn"], line["line_no"], line["name"], line["quantity"], line["unit"][:10],
                     line["net_cents"], line["vat_percent"], line["vat_cents"]))
    return {"added": added, "payments": match_payments(owner)}


def match_payments(owner):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id, box, issue_date, party, payable_cents FROM core.jarvis_invoice
            WHERE owner=%s AND status NOT IN ('Canceled','Declined','Return','Draft')""", (owner,))
        invoices = [dict(row) for row in cur.fetchall()]
        cur.execute("""SELECT movement_id, direction, tx_date, party, amount_cents FROM core.jarvis_money_movement
            WHERE owner=%s""", (owner,))
        movements = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT document_id, movement_id, status FROM core.jarvis_invoice_payment WHERE owner=%s", (owner,))
        links = [dict(row) for row in cur.fetchall()]
        found = find_payments(invoices, movements, links)
        for link in found:
            cur.execute("""INSERT INTO core.jarvis_invoice_payment (owner,document_id,movement_id)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""", (owner, link["document_id"], link["movement_id"]))
            # paid from his own pocket for the company: show it under that company unless he chose one
            cur.execute("""UPDATE core.jarvis_money_movement m SET scope=i.book, updated_at=clock_timestamp()
                FROM core.jarvis_invoice i
                WHERE m.owner=%s AND m.movement_id=%s AND m.book='kisisel' AND coalesce(m.scope,'')=''
                  AND i.owner=m.owner AND i.document_id=%s AND i.box='in'""",
                        (owner, link["movement_id"], link["document_id"]))
        return len(found)


# ------------------------------------------------------------------ okuma (sayfa)
def invoices(owner, book="moy", month=""):
    if book not in BOOKS:
        raise ExpenseError("Defter bilinmiyor.")
    try:
        first = datetime.strptime(month, "%Y-%m").date() if month else date.today().replace(day=1)
    except ValueError:
        raise ExpenseError("Ay YYYY-AA biçiminde olmalı.") from None
    after = (first + timedelta(days=32)).replace(day=1)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT i.document_id, i.box, i.scenario, i.number, i.issue_date, i.party, i.party_vkn,
                i.payable_cents, i.tax_cents, i.currency, i.status, i.category,
                p.movement_id, p.status AS pay_status, m.account AS pay_account, m.book AS pay_book,
                m.tx_date AS pay_date, m.amount_cents AS pay_cents
            FROM core.jarvis_invoice i
            LEFT JOIN core.jarvis_invoice_payment p ON p.owner=i.owner AND p.document_id=i.document_id AND p.status<>'rejected'
            LEFT JOIN core.jarvis_money_movement m ON m.owner=p.owner AND m.movement_id=p.movement_id
            WHERE i.owner=%s AND i.book=%s AND i.issue_date >= %s AND i.issue_date < %s
            ORDER BY i.issue_date DESC, i.number DESC""", (owner, book, first, after))
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute("""SELECT document_id, line_no, name, quantity::float AS quantity, unit, net_cents,
                vat_percent::float AS vat_percent, vat_cents FROM core.jarvis_invoice_line
            WHERE owner=%s AND document_id = ANY(%s) ORDER BY document_id, line_no""",
                    (owner, [row["document_id"] for row in rows]))
        lines = {}
        for line in cur.fetchall():
            lines.setdefault(line["document_id"], []).append(dict(line))
        cur.execute("""SELECT to_char(issue_date,'YYYY-MM') AS month, box, count(*)::int AS count,
                sum(payable_cents)::bigint AS total FROM core.jarvis_invoice
            WHERE owner=%s AND book=%s AND issue_date >= %s AND status NOT IN ('Canceled','Declined','Draft')
            GROUP BY 1,2 ORDER BY 1""", (owner, book, (first - timedelta(days=330)).replace(day=1)))
        months = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT count(*)::int AS n, max(fetched_at) AS last FROM core.jarvis_invoice WHERE owner=%s AND book=%s",
                    (owner, book))
        meta = dict(cur.fetchone())
    counted = [row for row in rows if row["status"] not in ("Canceled", "Declined", "Draft")]
    by_category = {}
    for row in counted:
        if row["box"] == "in":
            by_category[row["category"]] = by_category.get(row["category"], 0) + row["payable_cents"]
    for row in rows:
        row["lines"] = lines.get(row["document_id"], [])
        row["pay_label"] = (f"{row['pay_account']}{' · şahsi' if row['pay_book'] == 'kisisel' else ''}"
                            if row["movement_id"] else "")
    return {
        "book": book, "month": first.strftime("%Y-%m"), "connected": meta["n"] > 0,
        "last_fetch": meta["last"], "invoices": rows, "months": months,
        "in_total": sum(r["payable_cents"] for r in counted if r["box"] == "in"),
        "out_total": sum(r["payable_cents"] for r in counted if r["box"] == "out"),
        "unpaid": sum(1 for r in counted if r["box"] == "in" and not r["movement_id"]),
        "uncollected": sum(1 for r in counted if r["box"] == "out" and not r["movement_id"]),
        "source": "uyumsoft" if book == "moy" else "pdf",
        "by_category": sorted(({"key": k, "label": OUT_CATEGORIES.get(k, k), "total": v} for k, v in by_category.items()),
                              key=lambda x: -x["total"]),
        "categories": OUT_CATEGORIES,
    }


def set_payment(owner, body):
    """'Bu ödeme bu faturanın değil' → never suggested again; 'doğru' → kept for good."""
    action = body.get("action")
    if action not in ("ok", "reject"):
        raise ExpenseError("İşlem ok ya da reject olmalı.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_invoice_payment SET status=%s, updated_at=clock_timestamp()
            WHERE owner=%s AND document_id=%s AND movement_id=%s""",
                    ("ok" if action == "ok" else "rejected", owner, str(body.get("document_id", ""))[:64],
                     str(body.get("movement_id", ""))[:64]))
        if not cur.rowcount:
            raise ExpenseError("Eşleşme bulunamadı.")
    return {"ok": True}


def set_category(owner, body):
    category = body.get("category")
    if category not in OUT_CATEGORIES:
        raise ExpenseError("Kategori bilinmiyor.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_invoice SET category=%s, category_set=true
            WHERE owner=%s AND document_id=%s AND box='in'""",
                    (category, owner, str(body.get("document_id", ""))[:64]))
        if not cur.rowcount:
            raise ExpenseError("Fatura bulunamadı.")
    return {"ok": True}
