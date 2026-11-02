"""Belge tarafı: kategori, satıcı tanıma, aylık özet, abonelik, ay sonu hatırlatması.

Belgeler expense_vault'ta, para hareketleri money_ledger'da; bu modül
belgelerin üstüne okuma katmanıdır.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from expense_vault import ZONE, ExpenseError, _connect

# one category list for documents and money movements (money_ledger owns it)
from money_ledger import OUT_CATEGORIES as CATEGORIES  # noqa: E402

_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _plain(value):
    """OCR writes Turkish letters both ways (FIS / FİŞ): compare in ASCII."""
    return (value or "").replace("İ", "i").replace("I", "ı").casefold().translate(_ASCII)


# (category, pattern) on ASCII text; supplier is tried before the OCR body.
_RULES = [
    ("yazilim", r"anthropic|openai|chatgpt|canva|higgsfield|github|vercel|cloudflare|\bwix\b|natro|"
                r"google workspace|google cloud|microsoft|adobe|notion|zoom\.us|hosting|alan adi|domain|"
                r"abonelik|subscription|hetzner|contabo|digitalocean|freepik|envato|midjourney|"
                r"elevenlabs|runway|\bvds\b|sunucu|keyubu|google one|lm studio|netflix|apple\.com|"
                r"turkticaretnet"),
    ("reklam", r"meta platforms|facebook|facebk|instagram|google ads|reklam|tiktok"),
    ("faturalar", r"enerjisa|elektrik|dogalgaz|igdas|baskentgaz|\baski\b|turk telekom|turkcell|"
                  r"vodafone|superonline|turknet|internet/tv"),
    ("kargo", r"kargo|yurtici|\baras\b|\bmng\b|\bptt\b|surat|hepsijet|ups|dhl|fedex|kolay gelsin|sendeo"),
    ("akaryakit", r"opet|shell|petrol|\bbp\b|total ?energies|akaryakit|motorin|benzin|\blpg\b|aytemiz|alpet|sunpet"),
    ("ulasim", r"taksi|taxi|uber|bitaksi|otopark|\bhgs\b|\bogs\b|ego kart|ankarakart|metro|"
               r"turk hava|\bthy\b|pegasus|ajet|otobus|marti"),
    ("yemek", r"lokanta|restoran|restaurant|doner|lahmacun|pide|kebap|kebab|balik|cafe|kafe|kahve|"
              r"starbucks|burger|pizza|yemek|simit|firin|pastane|tatli|baklava|corba|kofte|mangal|"
              r"yemeksepeti|yemekpay|getir|\brest\b"),
    ("market", r"\bbim\b|a101|\bsok\b|migros|carrefour|macro ?center|file market|market|deterjan|"
               r"temizlik|bakkal|sarkuteri|tekel|gida"),
    ("ofis", r"kirtasiye|toner|kagit|matbaa|fotokopi|mobilya|ikea|teknosa|media ?markt|vatan bilgisayar"),
]

# Recurring vendors whose invoices arrive without a readable seller line.
_VENDORS = [
    ("Anthropic, PBC", r"anthropic"),
    ("Google Workspace", r"google workspace|google cloud emea"),
    ("OpenAI", r"openai"),
    ("Canva", r"canva"),
    ("Higgsfield", r"higgsfield"),
    ("Meta Platforms", r"meta platforms|facebook ads"),
    # card statement shows "KEYUBU İNTERNET" for exactly these VDS invoice amounts
    ("Keyubu İnternet (VDS sunucu)", r"keyubu|vds l-tr|abdulkadir azinc"),
    ("Wix.com", r"\bwix\b"),
    ("Netflix", r"netflix"),
    ("Apple", r"apple\.com"),
    ("Türk Telekom", r"turk telekom"),
    ("Vodafone", r"vodafone"),
    ("Enerjisa", r"enerjisa"),
    ("Çiçeksepeti", r"ciceksepeti"),
    ("Yemeksepeti", r"yemeksepeti"),
]


def categorize(supplier, text=""):
    for source in (_plain(supplier), _plain(text)):
        for category, pattern in _RULES:
            if source and re.search(pattern, source):
                return category
    return "diger"


def vendor(text):
    plain = _plain(text)
    for name, pattern in _VENDORS:
        if re.search(pattern, plain):
            return name
    return ""


def _month(period):
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ExpenseError("Ay geçersiz.")
    start = date(int(period[:4]), int(period[5:]), 1)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


# ---------------------------------------------------------------- özet
def summary(owner, period):
    """Category and company totals by document date (upload date if unread)."""
    start, end = _month(period)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT kind,company,category,currency,gross_cents,tax_cents,status,supplier,
            extracted->>'evidence' AS evidence
            FROM core.jarvis_expense_document WHERE owner=%s AND status<>'excluded'
            AND COALESCE(document_date,(created_at AT TIME ZONE 'Europe/Istanbul')::date) >= %s
            AND COALESCE(document_date,(created_at AT TIME ZONE 'Europe/Istanbul')::date) < %s""",
            (owner, start, end))
        rows = cur.fetchall()
    categories, companies, totals = {}, {}, {}
    missing = review = 0
    for row in rows:
        if row["gross_cents"] is None:
            missing += 1
            continue
        if row["status"] != "ready":
            review += 1
        category = row["category"] or categorize(row["supplier"], row["evidence"])
        currency = row["currency"]
        for bucket, key in ((categories, (category, currency)), (companies, (row["company"], currency)),
                            (totals, currency)):
            item = bucket.setdefault(key, {"gross": 0, "tax": 0, "count": 0})
            item["gross"] += row["gross_cents"]
            item["tax"] += row["tax_cents"] or 0
            item["count"] += 1
    return {
        "period": period,
        "totals": [dict(currency=key, **value) for key, value in sorted(totals.items())],
        "categories": sorted(({"category": key[0], "label": CATEGORIES.get(key[0], key[0]),
                               "currency": key[1], **value} for key, value in categories.items()),
                             key=lambda item: (item["currency"] != "TRY", -item["gross"])),
        "companies": sorted(({"company": key[0], "currency": key[1], **value}
                             for key, value in companies.items()),
                            key=lambda item: (item["currency"] != "TRY", -item["gross"])),
        "unread": missing, "unchecked": review,
    }


# ---------------------------------------------------------- abonelikler
def _subscription_key(row):
    name = row["supplier"] or vendor(row["evidence"])
    return name, _plain(name)[:12]


def subscriptions(owner, today=None):
    """Vendors billed in two or more different months within 13 months."""
    today = today or datetime.now(ZONE).date()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id,kind,supplier,currency,gross_cents,document_date,
            extracted->>'evidence' AS evidence FROM core.jarvis_expense_document
            WHERE owner=%s AND status<>'excluded' AND gross_cents IS NOT NULL
            AND document_date >= %s ORDER BY document_date""",
            (owner, today - timedelta(days=400)))
        rows = cur.fetchall()
    groups = {}
    for row in rows:
        # Anthropic sends an invoice AND a receipt for one payment: count invoices only
        if row["kind"] == "receipt" and re.search(r"invoice number", _plain(row["evidence"])):
            continue
        name, key = _subscription_key(row)
        if not key or categorize(name, row["evidence"]) != "yazilim":
            continue
        groups.setdefault((key, row["currency"]), {"name": name, "rows": []})["rows"].append(row)
    result = []
    for (_, currency), group in groups.items():
        months = {}
        for row in group["rows"]:
            month = row["document_date"].strftime("%Y-%m")
            months[month] = months.get(month, 0) + row["gross_cents"]
        if len(months) < 2:
            continue
        ordered = sorted(months.items())
        last_month, last = ordered[-1]
        previous = ordered[-2][1]
        recent = [value for month, value in ordered if month >= (today - timedelta(days=95)).strftime("%Y-%m")]
        change = round((last - previous) * 100 / previous, 1) if previous else None
        result.append({
            "name": group["name"], "currency": currency, "months": len(months),
            "last_month": last_month, "last": last, "previous": previous, "change_pct": change,
            "monthly_avg": round(sum(recent or [last]) / len(recent or [last])),
            "increase": bool(change is not None and change > 5),
        })
    return sorted(result, key=lambda item: (item["currency"] != "TRY", -item["monthly_avg"]))


# ------------------------------------------------------------ bildirim
def _claim_notice(owner, key):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_expense_notice (owner,notice_key) VALUES (%s,%s)
            ON CONFLICT DO NOTHING RETURNING notice_key""", (owner, key[:200]))
        return cur.fetchone() is not None


def reminder(owner, today=None):
    """Last three days of the month: what still keeps the package incomplete."""
    today = today or datetime.now(ZONE).date()
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if (month_end - today).days > 2:
        return None
    import money_ledger
    period = today.strftime("%Y-%m")
    lines = money_ledger.receipt_lines(owner, period)
    totals = summary(owner, period)
    parts = []
    if lines["counts"]["open"]:
        parts.append(f"{lines['counts']['open']} kart harcamasının fişi yok "
                     f"({lines['open_total'] / 100:,.2f} TL)".replace(",", "X").replace(".", ",").replace("X", "."))
    if totals["unread"]:
        parts.append(f"{totals['unread']} belgenin tutarı okunamadı")
    if totals["unchecked"]:
        parts.append(f"{totals['unchecked']} belge kontrol bekliyor")
    if not parts or not _claim_notice(owner, f"hatirlatma:{period}"):
        return None
    return {"title": "Ay sonu fiş kontrolü", "body": "; ".join(parts) + ". Paket ayın son günü gidiyor."}


def subscription_alerts(owner, today=None):
    alerts = []
    for item in subscriptions(owner, today):
        if not item["increase"]:
            continue
        key = f"abonelik:{_plain(item['name'])[:40]}:{item['last_month']}"
        if not _claim_notice(owner, key):
            continue
        sign = "$" if item["currency"] == "USD" else "₺"
        alerts.append({"title": f"{item['name']} faturası arttı",
                       "body": f"{item['last_month']}: {sign}{item['last'] / 100:.2f} "
                               f"(önceki ay {sign}{item['previous'] / 100:.2f}, %{item['change_pct']})"})
    return alerts


def backfill(owner):
    """Fill empty supplier/category on documents read before these rules existed."""
    filled = 0
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id,supplier,category,extracted->>'evidence' AS evidence
            FROM core.jarvis_expense_document WHERE owner=%s AND (supplier='' OR category='')""", (owner,))
        for row in cur.fetchall():
            supplier = row["supplier"] or vendor(row["evidence"])
            category = row["category"] or (categorize(supplier, row["evidence"]) if row["evidence"] else "")
            if (supplier, category) == (row["supplier"], row["category"]):
                continue
            cur.execute("""UPDATE core.jarvis_expense_document SET
                supplier=CASE WHEN supplier='' THEN %s ELSE supplier END,
                category=CASE WHEN category='' THEN %s ELSE category END
                WHERE owner=%s AND document_id=%s""", (supplier, category, owner, row["document_id"]))
            filled += 1
    return filled
