"""L'CARLIÉ ürün maliyet / kâr tablosu (sahip, 02.11.2026).

"Ürün ürün toplam adet maliyetleri, toplam satış rakamları ve maliyetin ne kadar karşılandığı — kârda mı
zararda mıyız ürün bağlamında görelim. Tester maliyetlerini ürün maliyetine yansıtalım. Harcama ekle
butonu: eklenen maliyet genel maliyete ya da seçtiğim ürüne etki etsin."

Costs, all VAT-exclusive (the company deducts the VAT):
  üretim   production invoice lines of the product (NEVA prices include box, label, packaging)
  tester   tester lines, charged to the product they are a tester of ("testerlar dağıtılıyor")
  genel    product-test / safety-report invoices (TTS, Regnovis ÜGR) + costs added as general, split over
           the products by the chosen key (equal by default: the reports are per product)
  özel     costs added for one product
Sales are the same rows the analysis pages use (invoices + Wix/Trendyol orders without an invoice).
"""
from __future__ import annotations

import math
import re
import uuid
from datetime import date, datetime, timedelta

import invoice_analysis
import invoice_topics
from expense_vault import ZONE, ExpenseError, _connect, _money, _text

ALLOCATIONS = {"esit": "Ürünlere eşit", "adet": "Üretim adedine göre", "ciro": "Satışa (ciroya) göre"}


def _spread(amount, weights):
    """amount over weights; rounding remainder to the largest share (sums to the kuruş)."""
    total = sum(weights.values())
    if not weights or not total:
        return {k: 0 for k in weights}
    out = {k: round(amount * w / total) for k, w in weights.items()}
    if out:
        out[max(out, key=lambda k: abs(out[k]))] += amount - sum(out.values())
    return out


def build(rows, extras, allocation="esit"):
    """Pure: product table from analysis rows (explore_rows) and the added costs."""
    if allocation not in ALLOCATIONS:
        raise ExpenseError("Dağıtım anahtarı geçersiz.")
    p = {}
    item = lambda name: p.setdefault(name, {"product": name, "produced": 0.0, "production": 0, "tester": 0, "tester_qty": 0.0,
                                            "general": 0, "special": 0, "sold": 0.0, "sales_net": 0, "sales_gross": 0,
                                            "first_made": None, "first_sold": None})
    general_items, tester_unassigned = [], 0
    for r in rows:
        if r["k"] != "lemos" or r["z"] == "grup":
            continue
        if r["b"] == "in" and r["t"] == "lcarlie_urun" and r["p"]:
            x = item(r["p"])
            x["produced"] += r["q"]
            x["production"] += r["v"]
            x["first_made"] = min(filter(None, (x["first_made"], r["m"])))
        elif r["b"] == "in" and r["t"] == "numune_tester":
            product = invoice_topics.product_of(r["n"])
            if product:
                x = item(product)
                x["tester"] += r["v"]
                x["tester_qty"] += r["q"]
            else:
                tester_unassigned += r["v"]
        elif r["b"] == "in" and r["t"] == "urun_test":
            general_items.append({"source": "fatura", "month": r["m"], "description": r["n"] or r["f"], "party": r["f"], "net": r["v"]})
        elif r["b"] == "out" and r["p"] and r["z"] == "lcarlie":
            x = item(r["p"])
            x["sold"] += r["q"]
            x["sales_net"] += r["v"]
            x["sales_gross"] += r["g"]
            x["first_sold"] = min(filter(None, (x["first_sold"], r["m"])))
    if tester_unassigned:
        general_items.append({"source": "tester", "month": "", "description": "Ürünü belli olmayan tester", "party": "", "net": tester_unassigned})
    for e in extras:
        if e["target"] == "urun":
            item(e["product"])["special"] += e["net_cents"]
        else:
            general_items.append({"source": "elle", "month": e["spent_on"][:7], "description": e["description"], "party": "", "net": e["net_cents"],
                                  "id": e["cost_id"]})
    general = sum(g["net"] for g in general_items)
    made = {k: v for k, v in p.items() if v["produced"] > 0}
    weights = {"esit": {k: 1 for k in made}, "adet": {k: v["produced"] for k, v in made.items()},
               "ciro": {k: max(v["sales_net"], 0) for k, v in made.items()}}[allocation]
    for k, share in _spread(general, weights).items():
        p[k]["general"] = share
    out = []
    for x in p.values():
        total = x["production"] + x["tester"] + x["general"] + x["special"]
        price = x["sales_net"] / x["sold"] if x["sold"] > 0 else 0
        remaining = max(0, total - x["sales_net"])
        out.append({**x, "total_cost": total, "profit": x["sales_net"] - total,
                    "coverage": round(x["sales_net"] / total * 100, 1) if total else None,
                    "unit_cost": round(total / x["produced"]) if x["produced"] else None,
                    "unit_production": round(x["production"] / x["produced"]) if x["produced"] else None,
                    "avg_price": round(price) if price else None, "remaining": remaining,
                    "units_to_breakeven": math.ceil(remaining / price) if remaining and price > 0 else (0 if not remaining else None),
                    "stock": x["produced"] - x["sold"]})
    out.sort(key=lambda x: -x["sales_net"])
    keys = ("production", "tester", "general", "special", "total_cost", "sales_net", "sales_gross", "profit", "remaining")
    totals = {k: sum(x[k] for x in out) for k in keys}
    totals.update({"produced": sum(x["produced"] for x in out), "sold": sum(x["sold"] for x in out), "tester_qty": sum(x["tester_qty"] for x in out),
                   "coverage": round(totals["sales_net"] / totals["total_cost"] * 100, 1) if totals["total_cost"] else None,
                   "products": len(out), "products_with_cost": len(made), "in_profit": sum(1 for x in out if x["profit"] >= 0 and x["total_cost"])})
    return {"products": out, "totals": totals, "general_items": general_items, "allocation": allocation, "allocations": ALLOCATIONS}


def _extras(owner):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT cost_id, spent_on, description, net_cents, vat_cents, target, product, note, created_at
            FROM core.jarvis_product_cost WHERE owner=%s ORDER BY spent_on DESC, created_at DESC""", (owner,))
        return [dict(r, spent_on=r["spent_on"].isoformat(), created_at=r["created_at"].isoformat()) for r in cur.fetchall()]


def report(owner, allocation="esit"):
    end = datetime.now(ZONE).date() + timedelta(days=1)
    rows = invoice_analysis.explore_rows(owner, date(2020, 1, 1), end)
    extras = _extras(owner)
    result = build(rows, extras, allocation)
    result["extras"] = extras
    result["product_names"] = sorted({x["product"] for x in result["products"]} | set(invoice_topics.LCARLIE_PRODUCTS.values()))
    return result


def add_cost(owner, body):
    """A cost the invoices do not show (or not yet): general, or for one product."""
    try:
        spent_on = date.fromisoformat(str(body.get("date") or ""))
    except ValueError:
        raise ExpenseError("Tarih geçersiz.") from None
    description = _text(body.get("description"), "Açıklama", 200)
    if not description:
        raise ExpenseError("Ne için harcandığını yazın.")
    raw = str(body.get("amount") or "").replace("₺", "").replace("TL", "").strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    amount = _money(raw, "Tutar")
    if not amount or amount <= 0:
        raise ExpenseError("Tutar gerekli.")
    rate = body.get("vat_rate")
    rate = 0 if rate in (None, "") else float(rate)
    if rate not in (0, 1, 10, 20):
        raise ExpenseError("KDV oranı 0, 1, 10 ya da 20 olmalı.")
    if body.get("vat_included"):  # tutar KDV dahil girildi
        net = round(amount / (1 + rate / 100))
    else:
        net = amount
    vat = round(net * rate / 100)
    target = body.get("target")
    if target not in ("genel", "urun"):
        raise ExpenseError("Genel maliyet mi, ürüne özel mi seçin.")
    product = (body.get("product") or "").strip() if target == "urun" else None
    if target == "urun" and product not in set(invoice_topics.LCARLIE_PRODUCTS.values()):
        raise ExpenseError("Ürün listeden seçilmeli.")
    cost_id = uuid.uuid4().hex
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_product_cost (cost_id,owner,spent_on,description,net_cents,vat_cents,target,product,note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (cost_id, owner, spent_on, description, net, vat, target, product, _text(body.get("note"), "Not", 300)))
    return {"id": cost_id, "net_cents": net, "vat_cents": vat}


def delete_cost(owner, cost_id):
    if not re.fullmatch(r"[0-9a-f]{32}", str(cost_id or "")):
        raise ExpenseError("Kayıt bulunamadı.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM core.jarvis_product_cost WHERE owner=%s AND cost_id=%s", (owner, cost_id))
        if not cur.rowcount:
            raise ExpenseError("Kayıt bulunamadı.")
    return {"ok": True}
