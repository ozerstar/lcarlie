"""Manual company ledger. PostgreSQL is authoritative; money is integer kuruş.

No model, provider call, automatic posting or production migration runs here.
All posted documents are immutable. Corrections append an exact reversal.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from personal_action_store import _connect

KINDS = {
    "sale": (1, -1, "Ürün verdik / satış"),
    "purchase": (-1, 1, "Ürün aldık / alış"),
    "sale_return": (-1, 1, "Müşteriden iade aldık"),
    "purchase_return": (1, -1, "Tedarikçiye iade verdik"),
    "collection": (-1, 0, "Tahsilat aldık"),
    "payment": (1, 0, "Ödeme yaptık"),
    "opening_receivable": (1, 0, "Açılış alacağımız"),
    "opening_payable": (-1, 0, "Açılış borcumuz"),
    "gift_out": (0, -1, "Bedelsiz ürün verdik"),
    "gift_in": (0, 1, "Bedelsiz ürün aldık"),
}
GOODS = frozenset(k for k, v in KINDS.items() if v[1])
MAX_MONEY = 10**12  # per document, kuruş
ID = re.compile(r"^[0-9a-f]{32}$")
KEY = re.compile(r"^[A-Za-z0-9_.:-]{16,120}$")


class CariError(ValueError):
    pass


class CariNotFound(CariError):
    pass


class CariConflict(CariError):
    pass


def _text(value, label, limit=200, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise CariError(f"{label} geçersiz veya çok uzun.")
    value = value.strip()
    if required and not value:
        raise CariError(f"{label} gerekli.")
    return value


def _number(value, label, maximum, places=2):
    # Reject booleans, exponent notation, NaN, Infinity and locale ambiguities.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise CariError(f"{label} sayı olmalı; ondalık ayırıcı olarak nokta kullanın.")
    raw = str(value)
    if not re.fullmatch(r"\d{1,13}(?:\.\d{1," + str(places) + r"})?", raw):
        raise CariError(f"{label} geçersiz.")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise CariError(f"{label} geçersiz.") from exc
    if result > maximum:
        raise CariError(f"{label} izin verilen sınırı aşıyor.")
    return result


def _money(value, label):
    return int(_number(value, label, Decimal(MAX_MONEY) / 100) * 100)


def _day(value, label, optional=False):
    if optional and not value:
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CariError(f"{label} YYYY-AA-GG biçiminde olmalı.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise CariError(f"{label} geçersiz.") from exc


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise CariNotFound("Cari kayıt bulunamadı.")
    return value


def _key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise CariError("İstek kimliği gerekli.")
    return value


def calculate(body):
    """Validate a document and snapshot its prices; never trust client totals."""
    if not isinstance(body, dict) or body.get("kind") not in KINDS:
        raise CariError("Hareket türü geçersiz.")
    kind = body["kind"]
    result = {
        "kind": kind, "date": _day(body.get("date"), "İşlem tarihi"),
        "due_date": _day(body.get("due_date"), "Vade", optional=True),
        "reference": _text(body.get("reference", ""), "Belge numarası", 100),
        "note": _text(body.get("note", ""), "Açıklama", 2000),
        "items": [], "net_cents": 0, "tax_cents": 0, "unknown_tax": False,
        "currency": "TRY",
    }
    if kind in GOODS:
        items = body.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise CariError("1 ile 100 arasında ürün satırı ekleyin.")
        for item in items:
            if not isinstance(item, dict):
                raise CariError("Ürün satırı geçersiz.")
            name = _text(item.get("name"), "Ürün adı", 160, required=True)
            quantity = item.get("quantity")
            if type(quantity) is not int or not 1 <= quantity <= 100000:
                raise CariError("Adet pozitif tam sayı olmalı.")
            price = _money(item.get("unit_price"), "KDV hariç birim fiyat")
            discount = _number(item.get("discount", "0"), "İskonto", 100)
            rate = item.get("tax_rate")
            rate = None if rate is None else _number(rate, "KDV oranı", 100)
            if kind.startswith("gift_") and (price != 0 or discount != 0 or rate != 0):
                raise CariError("Bedelsiz teslimde fiyat, iskonto ve KDV oranı sıfır olmalı.")
            net = int((Decimal(price * quantity) * (100 - discount) / 100)
                      .quantize(Decimal(1), rounding=ROUND_HALF_UP))
            tax = 0 if rate is None else int((Decimal(net) * rate / 100)
                                             .quantize(Decimal(1), rounding=ROUND_HALF_UP))
            result["items"].append({
                "name": name, "quantity": quantity, "unit_price_cents": price,
                "discount": str(discount), "tax_rate": None if rate is None else str(rate),
                "net_cents": net, "tax_cents": tax,
            })
            # Optional reference price, never part of the receivable or tax.
            # Omit when absent so historical payload hashes remain unchanged.
            recommended = item.get("recommended_price")
            if recommended is not None and recommended != "":
                result["items"][-1]["recommended_price_cents"] = _money(
                    recommended, "Tavsiye edilen piyasa satış fiyatı")
            result["net_cents"] += net
            result["tax_cents"] += tax
            result["unknown_tax"] |= rate is None
    else:
        result["net_cents"] = _money(body.get("amount"), "Tutar")
        if result["net_cents"] <= 0:
            raise CariError("Tutar sıfırdan büyük olmalı.")
        if kind in ("collection", "payment"):
            method = body.get("payment_method")
            if method is not None:
                if method not in ("pos", "havale", "elden", "other"):
                    raise CariError("Ödeme yöntemi geçersiz.")
                result["payment_method"] = method
            target = body.get("applies_to")
            if target:
                result["applies_to"] = _id(target)
                if not method:
                    raise CariError("Eşleştirilen tahsilat veya ödeme için yöntem gerekli.")
        elif body.get("payment_method") or body.get("applies_to"):
            raise CariError("Ödeme bilgisi bu hareket türünde kullanılamaz.")
    total = result["net_cents"] + result["tax_cents"]
    if total > MAX_MONEY:
        raise CariError("Belge tutarı izin verilen sınırı aşıyor.")
    result["signed_cents"] = KINDS[kind][0] * total
    return result


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _public_entry(row):
    return {"id": row["entry_id"], "payload": row["payload"],
            "reverses": row["reverses"], "created_at": str(row["created_at"])}


def summarize(entries):
    """Company perspective: positive=our receivable, negative=our payable."""
    debit = credit = 0
    unknown = 0
    products = {}
    for row in entries:
        payload = row["payload"]
        sign = -1 if row.get("reverses") else 1
        amount = sign * payload["signed_cents"]
        debit += max(amount, 0)
        credit += max(-amount, 0)
        unknown += sign * bool(payload["unknown_tax"])
        goods_sign = KINDS[payload["kind"]][1] * sign
        for item in payload["items"]:
            key = item["name"].casefold()
            product = products.setdefault(key, {"name": item["name"], "given": 0, "received": 0})
            quantity = item["quantity"] * goods_sign
            product["given"] += max(-quantity, 0)
            product["received"] += max(quantity, 0)
    balance = debit - credit
    return {"debit_cents": debit, "credit_cents": credit, "balance_cents": balance,
            "unknown_tax_documents": unknown,
            "status": "Alacaklıyız" if balance > 0 else "Borçluyuz" if balance < 0 else
                      "KDV bekleniyor" if unknown > 0 else "Hesap kapalı",
            "products": list(products.values())}


def product_tables(entries):
    """Price-aware product summaries, separate from the account balance.

    Returns reduce their own sales/purchase family. Distinct prices, tax rates
    and optional reference prices stay on separate rows. Reversed documents
    are excluded together with their reversals; no current catalog price is
    substituted into a historical document.
    """
    reversed_ids = {row["reverses"] for row in entries if row.get("reverses")}
    groups = {family: {} for family in ("sale", "purchase", "gift")}
    families = {"sale": ("sale", 1), "sale_return": ("sale", -1),
                "purchase": ("purchase", 1), "purchase_return": ("purchase", -1),
                "gift_out": ("gift", 1), "gift_in": ("gift", -1)}
    for row in entries:
        if row.get("reverses") or row.get("id", row.get("entry_id")) in reversed_ids:
            continue
        p = row["payload"]
        if p["kind"] not in families:
            continue
        family, sign = families[p["kind"]]
        for item in p["items"]:
            recommended = item.get("recommended_price_cents")
            key = (item["name"].casefold(), item["unit_price_cents"],
                   Decimal(item["discount"]), item["tax_rate"], recommended)
            unit = int((Decimal(item["unit_price_cents"]) *
                        (100 - Decimal(item["discount"])) / 100)
                       .quantize(Decimal(1), rounding=ROUND_HALF_UP))
            line = groups[family].setdefault(key, {
                "name": item["name"], "quantity": 0, "net_cents": 0,
                "discounted_unit_price_cents": unit,
                "recommended_price_cents": recommended,
                "tax_rate": item["tax_rate"],
            })
            line["quantity"] += sign * item["quantity"]
            line["net_cents"] += sign * item["net_cents"]
    result = {}
    for family, lines in groups.items():
        rows = [line for line in lines.values() if line["quantity"] or line["net_cents"]]
        result[family] = {"rows": rows,
                          "quantity": sum(line["quantity"] for line in rows),
                          "net_cents": sum(line["net_cents"] for line in rows)}
    return result


def create_account(owner, body):
    if not isinstance(body, dict):
        raise CariError("Cari bilgileri geçersiz.")
    name = _text(body.get("name"), "Cari adı", 160, required=True)
    role = body.get("role", "customer")
    if role not in ("customer", "supplier", "both"):
        raise CariError("Cari türü geçersiz.")
    contact = _text(body.get("contact", ""), "İletişim", 200)
    note = _text(body.get("note", ""), "Not", 2000)
    tax_id, tax_office, address, email, phone = _account_details(body)
    from psycopg.errors import UniqueViolation
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO core.jarvis_cari_account
                (account_id,owner,name,name_key,role,contact,note,tax_id,tax_office,address,email,phone)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(owner,name_key) DO NOTHING RETURNING account_id""",
                        (uuid.uuid4().hex, owner, name, name.casefold(), role, contact,
                         note, tax_id, tax_office, address, email, phone))
            row = cur.fetchone()
            if row is None:
                raise CariConflict("Bu isimle bir cari zaten var. Mevcut hesabı açın.")
    except UniqueViolation as exc:
        raise CariConflict("Bu vergi veya kimlik numarasıyla bir cari zaten var.") from exc
    return {"id": row["account_id"]}


def _account_details(body):
    tax_id = _text(body.get("tax_id", ""), "Vergi/kimlik numarası", 20)
    if tax_id and not re.fullmatch(r"\d{10,11}", tax_id):
        raise CariError("Vergi/kimlik numarası 10 veya 11 rakam olmalı.")
    tax_office = _text(body.get("tax_office", ""), "Vergi dairesi", 160)
    address = _text(body.get("address", ""), "Adres", 1000)
    email = _text(body.get("email", ""), "E-posta", 200)
    phone = _text(body.get("phone", ""), "Telefon", 50)
    return tax_id, tax_office, address, email, phone


def update_account(owner, account_id, body):
    """Edit account metadata and selected catalog covers, never ledger history."""
    account_id = _id(account_id)
    if not isinstance(body, dict):
        raise CariError("Cari bilgileri geçersiz.")
    name = _text(body.get("name"), "Cari adı", 160, required=True)
    role = body.get("role")
    if role not in ("customer", "supplier", "both"):
        raise CariError("Cari türü geçersiz.")
    contact = _text(body.get("contact", ""), "İletişim", 200)
    note = _text(body.get("note", ""), "Not", 2000)
    tax_id, tax_office, address, email, phone = _account_details(body)
    covers = body.get("covers", {})
    if not isinstance(covers, dict) or len(covers) > 100:
        raise CariError("Ürün görselleri geçersiz.")
    if covers:
        import katalog
        catalog = {product.get("slug"): product.get("gorseller", [])
                   for product in katalog.katalog().get("urunler", [])}
        for slug, cover in covers.items():
            if not isinstance(slug, str) or not isinstance(cover, str) or \
                    cover not in catalog.get(slug, []):
                raise CariError("Seçilen ürün görseli katalogda bulunamadı.")
    from psycopg.types.json import Jsonb
    from psycopg.errors import UniqueViolation
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                        (owner + ':' + account_id,))
            cur.execute("""UPDATE core.jarvis_cari_account
                SET name=%s,name_key=%s,role=%s,contact=%s,note=%s,covers=%s,
                    tax_id=%s,tax_office=%s,address=%s,email=%s,phone=%s
                WHERE owner=%s AND account_id=%s RETURNING account_id""",
                        (name, name.casefold(), role, contact, note, Jsonb(covers),
                         tax_id, tax_office, address, email, phone, owner, account_id))
            if cur.fetchone() is None:
                raise CariNotFound("Cari kayıt bulunamadı.")
    except UniqueViolation as exc:
        raise CariConflict("Bu isimle bir cari zaten var.") from exc
    return {"id": account_id}


def list_accounts(owner):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT a.account_id AS id,a.name,a.role,a.contact,
            COALESCE(SUM(e.signed_cents),0) AS balance_cents,
            COALESCE(SUM(CASE WHEN e.unknown_tax THEN
                CASE WHEN e.reverses IS NULL THEN 1 ELSE -1 END ELSE 0 END),0)
                AS unknown_tax_documents
            FROM core.jarvis_cari_account a LEFT JOIN core.jarvis_cari_entry e
            ON (e.owner,e.account_id)=(a.owner,a.account_id)
            WHERE a.owner=%s GROUP BY a.account_id ORDER BY lower(a.name),a.account_id""", (owner,))
        return {"accounts": [dict(row, balance_cents=int(row["balance_cents"]),
                                  unknown_tax_documents=int(row["unknown_tax_documents"]))
                             for row in cur.fetchall()]}


def portfolio(owner, as_of=None):
    """Read-only dated summary; unmatched cash does not settle a document."""
    when = (_day(as_of, "Rapor tarihi") if as_of is not None else
            datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat())
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cur.execute("""SELECT account_id AS id,name,role FROM core.jarvis_cari_account
            WHERE owner=%s ORDER BY lower(name),account_id""", (owner,))
        accounts = [dict(row) for row in cur.fetchall()]
        cur.execute("""SELECT account_id,entry_id,payload,reverses,created_at
            FROM core.jarvis_cari_entry WHERE owner=%s AND document_date<=%s
            ORDER BY document_date,created_at,entry_id""", (owner, when))
        rows = cur.fetchall()
    return portfolio_from_entries(accounts, rows, when)


def portfolio_from_entries(accounts, rows, as_of):
    """Deterministic projection; all values remain integer kuruş."""
    when = _day(as_of, "Rapor tarihi")
    grouped = {a["id"]: [] for a in accounts}
    for row in rows:
        if row["account_id"] in grouped and row["payload"]["date"] <= when:
            grouped[row["account_id"]].append(row)
    totals = {"receivable_cents": 0, "payable_cents": 0, "collections_cents": 0,
              "payments_cents": 0, "sales_net_cents": 0, "purchases_net_cents": 0,
              "unknown_tax_documents": 0, "account_count": len(accounts)}
    balances, due_reviews, missing_information = [], [], []
    for account in accounts:
        entries = grouped[account["id"]]
        summary = summarize(entries)
        balances.append(dict(account, **{k: summary[k] for k in
            ("balance_cents", "status", "unknown_tax_documents")}))
        totals["receivable_cents"] += max(summary["balance_cents"], 0)
        totals["payable_cents"] += max(-summary["balance_cents"], 0)
        totals["unknown_tax_documents"] += summary["unknown_tax_documents"]
        reversed_ids = {row.get("reverses") for row in entries if row.get("reverses")}
        effective = [row for row in entries if not row.get("reverses") and
                     row.get("entry_id", row.get("id")) not in reversed_ids]
        allocations = settlements(entries)
        # Keep unmatched account adjustments visible for manual reconciliation.
        has_adjustments = any(row["payload"]["kind"] in
            ("collection", "payment", "sale_return", "purchase_return") for row in effective)
        for row in effective:
            p = row["payload"]
            kind = p["kind"]
            if kind in ("collection", "payment"):
                totals["collections_cents" if kind == "collection" else "payments_cents"] += p["net_cents"]
            if kind in ("sale", "sale_return"):
                totals["sales_net_cents"] += (1 if kind == "sale" else -1) * p["net_cents"]
            if kind in ("purchase", "purchase_return"):
                totals["purchases_net_cents"] += (1 if kind == "purchase" else -1) * p["net_cents"]
            if kind in ("sale", "purchase") and (p["unknown_tax"] or not p["reference"]):
                missing_information.append({"account_id": account["id"],
                    "account_name": account["name"], "entry_id": row.get("entry_id", row.get("id")),
                    "date": p["date"], "unknown_tax": p["unknown_tax"],
                    "missing_reference": not p["reference"]})
            allocation = allocations.get(row.get("entry_id", row.get("id")))
            if (p["due_date"] and kind in
                    ("sale", "purchase", "opening_receivable", "opening_payable")):
                if allocation and allocation["remaining_cents"] <= 0:
                    continue
                due_reviews.append({"account_id": account["id"], "account_name": account["name"],
                    "entry_id": row.get("entry_id", row.get("id")),
                    "due_date": p["due_date"], "reference": p["reference"],
                    "kind": kind, "document_cents": abs(p["signed_cents"]),
                    "remaining_cents": allocation["remaining_cents"] if allocation else abs(p["signed_cents"]),
                    "overdue": p["due_date"] < when,
                    "unknown_tax": p["unknown_tax"], "settlement_verified": bool(allocation and allocation["paid_cents"]),
                    "has_account_adjustments": has_adjustments,
                    "review_reason": "Eşleşmemiş tahsilat veya iadeler ayrıca kontrol edilmeli."})
    balances.sort(key=lambda a: (-abs(a["balance_cents"]), a["name"]))
    due_reviews.sort(key=lambda row: (row["due_date"], row["account_name"], row["entry_id"]))
    return {"as_of": when, "totals": totals, "accounts": balances,
            "due_reviews": due_reviews, "missing_information": missing_information,
            "due_review_note": "Eşleştirilmiş ödemeler düşülür. Eşleşmemiş ödeme ve iadeler belge durumuna yansımaz.",
            "cash_note": "Tahsilat ve ödeme, seçilen tarihe kadar girilmiş cari hareketlerdir; banka bakiyesi değildir."}


def statement(owner, account_id):
    account_id = _id(account_id)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT account_id AS id,name,role,contact,note,covers,
            tax_id,tax_office,address,email,phone
            FROM core.jarvis_cari_account WHERE owner=%s AND account_id=%s""", (owner, account_id))
        account = cur.fetchone()
        if account is None:
            raise CariNotFound("Cari kayıt bulunamadı.")
        cur.execute("""SELECT entry_id,payload,reverses,created_at
            FROM core.jarvis_cari_entry WHERE owner=%s AND account_id=%s
            ORDER BY document_date,created_at,entry_id""", (owner, account_id))
        entries = [_public_entry(row) for row in cur.fetchall()]
    return {"account": dict(account), "entries": entries, "summary": summarize(entries),
            "settlements": settlements(entries), "product_tables": product_tables(entries)}


def settlements(entries):
    """Explicit allocations only; an unmatched cash entry never pays an invoice."""
    reversed_ids = {row["reverses"] for row in entries if row.get("reverses")}
    effective = [row for row in entries if not row.get("reverses") and
                 row.get("id", row.get("entry_id")) not in reversed_ids]
    paid = {}
    for row in effective:
        p = row["payload"]
        if p.get("applies_to") and p["kind"] in ("collection", "payment"):
            paid[p["applies_to"]] = paid.get(p["applies_to"], 0) + p["net_cents"]
    result = {}
    for row in effective:
        p = row["payload"]
        if p["kind"] not in ("sale", "purchase", "opening_receivable", "opening_payable"):
            continue
        total = abs(p["signed_cents"])
        allocated = paid.get(row.get("id", row.get("entry_id")), 0)
        result[row.get("id", row.get("entry_id"))] = {"paid_cents": allocated, "remaining_cents": max(0, total - allocated),
            "status": "paid" if allocated >= total else "partial" if allocated else "unpaid",
            "unknown_tax": p["unknown_tax"]}
    return result


def _check_allocation(cur, owner, account_id, payload, exclude_id=None):
    target = payload.get("applies_to")
    if not target:
        return
    cur.execute("""SELECT entry_id,payload FROM core.jarvis_cari_entry
        WHERE owner=%s AND account_id=%s AND entry_id=%s AND reverses IS NULL""",
        (owner, account_id, target))
    row = cur.fetchone()
    if not row:
        raise CariNotFound("Eşleştirilecek belge bulunamadı.")
    allowed = ("sale", "opening_receivable") if payload["kind"] == "collection" else ("purchase", "opening_payable")
    if row["payload"]["kind"] not in allowed:
        raise CariError("Ödeme türü seçilen belgeyle uyuşmuyor.")
    cur.execute("""SELECT entry_id FROM core.jarvis_cari_entry WHERE owner=%s AND account_id=%s
        AND reverses=%s""", (owner, account_id, target))
    if cur.fetchone():
        raise CariConflict("İptal edilmiş belgeye ödeme eşleştirilemez.")
    cur.execute("""SELECT c.entry_id,c.payload FROM core.jarvis_cari_entry c
        WHERE c.owner=%s AND c.account_id=%s AND c.reverses IS NULL
          AND c.payload->>'applies_to'=%s AND c.entry_id<>%s
          AND NOT EXISTS (SELECT 1 FROM core.jarvis_cari_entry r
              WHERE r.owner=c.owner AND r.account_id=c.account_id AND r.reverses=c.entry_id)""",
        (owner, account_id, target, exclude_id or ""))
    paid = sum(r["payload"]["net_cents"] for r in cur.fetchall())
    if paid + payload["net_cents"] > abs(row["payload"]["signed_cents"]):
        raise CariConflict("Eşleştirilen ödemeler belge tutarını aşamaz.")


def post_entry(owner, account_id, body):
    account_id = _id(account_id)
    if not isinstance(body, dict):
        raise CariError("Hareket geçersiz.")
    key = _key(body.get("request_id"))
    payload = calculate(body)
    digest = _digest(payload)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        # Serialize per account: response retries and reversal checks are atomic.
        # Advisory locks keep the web role INSERT/SELECT-only. SELECT FOR UPDATE
        # would require UPDATE privilege even though no account is changed.
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                    (owner + ':' + account_id,))
        cur.execute("""SELECT account_id FROM core.jarvis_cari_account
            WHERE owner=%s AND account_id=%s""", (owner, account_id))
        if cur.fetchone() is None:
            raise CariNotFound("Cari kayıt bulunamadı.")
        cur.execute("""SELECT entry_id,payload_hash FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND request_id=%s""", (owner, account_id, key))
        previous = cur.fetchone()
        if previous:
            if previous["payload_hash"] != digest:
                raise CariConflict("Bu istek kimliği başka bir hareket için kullanılmış.")
            return {"id": previous["entry_id"], "reused": True}
        _check_allocation(cur, owner, account_id, payload)
        entry_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO core.jarvis_cari_entry
            (entry_id,owner,account_id,request_id,payload_hash,document_date,
             payload,signed_cents,unknown_tax)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (entry_id, owner, account_id, key, digest, payload["date"],
                     Jsonb(payload), payload["signed_cents"], payload["unknown_tax"]))
    return {"id": entry_id, "reused": False}


def reverse_entry(owner, account_id, body):
    account_id = _id(account_id)
    if not isinstance(body, dict):
        raise CariError("Düzeltme geçersiz.")
    original_id = _id(body.get("entry_id"))
    key = _key(body.get("request_id"))
    reason = _text(body.get("reason"), "Düzeltme gerekçesi", 500, required=True)
    when = _day(body.get("date"), "Düzeltme tarihi")
    digest = _digest({"entry_id": original_id, "reason": reason, "date": when})
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                    (owner + ':' + account_id,))
        cur.execute("""SELECT account_id FROM core.jarvis_cari_account
            WHERE owner=%s AND account_id=%s""", (owner, account_id))
        if cur.fetchone() is None:
            raise CariNotFound("Cari kayıt bulunamadı.")
        cur.execute("""SELECT entry_id,payload_hash FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND request_id=%s""", (owner, account_id, key))
        previous = cur.fetchone()
        if previous:
            if previous["payload_hash"] != digest:
                raise CariConflict("Bu istek kimliği başka bir hareket için kullanılmış.")
            return {"id": previous["entry_id"], "reused": True}
        cur.execute("""SELECT payload,reverses FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND entry_id=%s""", (owner, account_id, original_id))
        original = cur.fetchone()
        if original is None:
            raise CariNotFound("Hareket bulunamadı.")
        if original["reverses"]:
            raise CariConflict("Ters kayıt tekrar ters çevrilemez; yeni hareket ekleyin.")
        if when < original["payload"]["date"]:
            raise CariError("Düzeltme tarihi asıl hareketten önce olamaz.")
        cur.execute("""SELECT entry_id FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND reverses=%s""", (owner, account_id, original_id))
        if cur.fetchone():
            raise CariConflict("Bu hareket zaten ters kayıtla düzeltildi.")
        if original["payload"]["kind"] in ("sale", "purchase", "opening_receivable", "opening_payable"):
            cur.execute("""SELECT 1 FROM core.jarvis_cari_entry c WHERE c.owner=%s AND c.account_id=%s
                AND c.reverses IS NULL AND c.payload->>'applies_to'=%s
                AND NOT EXISTS (SELECT 1 FROM core.jarvis_cari_entry r
                    WHERE r.owner=c.owner AND r.account_id=c.account_id AND r.reverses=c.entry_id) LIMIT 1""",
                (owner, account_id, original_id))
            if cur.fetchone():
                raise CariConflict("Önce bu belgeye bağlı ödemeleri düzeltin veya iptal edin.")
        payload = dict(original["payload"], date=when, note=reason, due_date="")
        entry_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO core.jarvis_cari_entry
            (entry_id,owner,account_id,request_id,payload_hash,document_date,
             payload,signed_cents,unknown_tax,reverses)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (entry_id, owner, account_id, key, digest, when, Jsonb(payload),
                     -payload["signed_cents"], payload["unknown_tax"], original_id))
    return {"id": entry_id, "reused": False}


def correct_entry(owner, account_id, body):
    """Append reversal and replacement together, or append neither."""
    account_id = _id(account_id)
    if not isinstance(body, dict):
        raise CariError("Düzeltme geçersiz.")
    original_id = _id(body.get("entry_id"))
    key = _key(body.get("request_id"))
    reason = _text(body.get("reason"), "Düzeltme gerekçesi", 500, required=True)
    when = _day(body.get("correction_date"), "Düzeltme tarihi")
    replacement = calculate(body.get("replacement"))
    digest = _digest({"entry_id": original_id, "reason": reason,
                      "date": when, "replacement": replacement})
    replacement_key = _digest({"correction_request": key})
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                    (owner + ':' + account_id,))
        cur.execute("""SELECT account_id FROM core.jarvis_cari_account
            WHERE owner=%s AND account_id=%s""", (owner, account_id))
        if cur.fetchone() is None:
            raise CariNotFound("Cari kayıt bulunamadı.")
        cur.execute("""SELECT entry_id,payload_hash FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND request_id=%s""", (owner, account_id, key))
        previous = cur.fetchone()
        if previous:
            if previous["payload_hash"] != digest:
                raise CariConflict("Bu istek kimliği başka bir düzeltme için kullanılmış.")
            cur.execute("""SELECT entry_id FROM core.jarvis_cari_entry
                WHERE owner=%s AND account_id=%s AND request_id=%s""",
                        (owner, account_id, replacement_key))
            posted = cur.fetchone()
            if posted is None:
                raise CariConflict("Düzeltme kaydı tamamlanmamış; destek ekibine bildirin.")
            return {"id": posted["entry_id"], "reused": True}
        cur.execute("""SELECT payload,reverses FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND entry_id=%s""", (owner, account_id, original_id))
        original = cur.fetchone()
        if original is None:
            raise CariNotFound("Hareket bulunamadı.")
        if original["reverses"]:
            raise CariConflict("Ters kayıt düzeltilemez.")
        if when < original["payload"]["date"]:
            raise CariError("Düzeltme tarihi asıl hareketten önce olamaz.")
        cur.execute("""SELECT entry_id FROM core.jarvis_cari_entry
            WHERE owner=%s AND account_id=%s AND reverses=%s""", (owner, account_id, original_id))
        if cur.fetchone():
            raise CariConflict("Bu hareket zaten düzeltildi.")
        if original["payload"]["kind"] in ("sale", "purchase", "opening_receivable", "opening_payable"):
            cur.execute("""SELECT 1 FROM core.jarvis_cari_entry c WHERE c.owner=%s AND c.account_id=%s
                AND c.reverses IS NULL AND c.payload->>'applies_to'=%s
                AND NOT EXISTS (SELECT 1 FROM core.jarvis_cari_entry r
                    WHERE r.owner=c.owner AND r.account_id=c.account_id AND r.reverses=c.entry_id) LIMIT 1""",
                (owner, account_id, original_id))
            if cur.fetchone():
                raise CariConflict("Önce bu belgeye bağlı ödemeleri düzeltin veya iptal edin.")
        _check_allocation(cur, owner, account_id, replacement, exclude_id=original_id)
        reversal = dict(original["payload"], date=when, note=reason, due_date="")
        reversal_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO core.jarvis_cari_entry
            (entry_id,owner,account_id,request_id,payload_hash,document_date,
             payload,signed_cents,unknown_tax,reverses)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (reversal_id, owner, account_id, key, digest, when, Jsonb(reversal),
                     -reversal["signed_cents"], reversal["unknown_tax"], original_id))
        new_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO core.jarvis_cari_entry
            (entry_id,owner,account_id,request_id,payload_hash,document_date,
             payload,signed_cents,unknown_tax)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (new_id, owner, account_id, replacement_key, _digest(replacement),
                     replacement["date"], Jsonb(replacement), replacement["signed_cents"],
                     replacement["unknown_tax"]))
    return {"id": new_id, "reused": False}
