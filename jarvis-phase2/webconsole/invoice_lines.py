"""Item lines of e-invoice PDFs whose layouts differ per issuer (Lemos, 02.11.2026).

Three readers, tried in order; a reader's lines are kept only when they add up to the invoice
(net + VAT = payable, or net × a legal VAT rate = payable). Nothing is guessed: an invoice whose
lines do not add up keeps its totals and gets no lines.
"""
import re
from decimal import Decimal, InvalidOperation

# Python's re.I does not fold Turkish İ/ı: "MİKTAR", "AÇIKLAMA", "ORANI" are spelled out (TYA, 02.11.2026)
_NAME = re.compile(r"mal\s*/?\s*hizmet$|malzeme\s*/\s*hizmet$|ürün|ÜRÜN|hizmet\s*/\s*ürün|açıklama|AÇIKLAMA|cinsi|malzeme|^hizmet$", re.I)
_QTY = re.compile(r"miktar|MİKTAR", re.I)
_NET = re.compile(r"(mal\s*/?\s*hizmet\s*tutar|malzeme\s*/\s*hizmet\s*tutar|tutar[ıi]?$|TUTARI?$|^toplam$|net\s*tutar)", re.I)
_PCT = re.compile(r"kdv\s*oran|KDV\s*ORAN|kdv\s*%|^kdv$|%\s*kdv", re.I)
VAT_RATES = (Decimal("1.01"), Decimal("1.08"), Decimal("1.10"), Decimal("1.18"), Decimal("1.20"))


def money(text):
    text = (text or "").replace("TL", "").replace("₺", "").strip()
    found = re.search(r"\d[\d.]*,\d{1,2}|\d+(?:\.\d{1,2})?", text)
    if not found:
        return None
    value = found.group(0)
    try:
        return int(Decimal(value.replace(".", "").replace(",", ".") if "," in value else value) * 100)
    except InvalidOperation:
        return None


def _quantity(text):
    found = re.match(r"\s*([\d.,]+)\s*(.*)", text or "")
    if not found:
        return Decimal(0), ""
    raw = found.group(1)
    try:
        value = Decimal(raw.replace(".", "").replace(",", ".") if "," in raw else raw)
    except InvalidOperation:
        value = Decimal(0)
    return value, found.group(2).strip()[:12]


def _pct(text):
    found = re.search(r"(\d+(?:[,.]\d+)?)", text or "")
    return Decimal(found.group(1).replace(",", ".")) if found else None


def from_tables(pages):
    """PyMuPDF table finder: header cells name the columns, so column order does not matter."""
    lines = []
    for page in pages:
        try:
            tables = page.find_tables()
        except Exception:  # noqa: BLE001 - a broken page must not stop the others
            continue
        for table in tables:
            rows = table.extract() or []
            for at, header in enumerate(rows[:3]):
                cells = [re.sub(r"\s+", " ", c or "").strip() for c in header]
                name = next((i for i, c in enumerate(cells) if _NAME.search(c)), None)
                qty = next((i for i, c in enumerate(cells) if _QTY.search(c)), None)
                if name is None or qty is None:
                    continue
                nets = [i for i, c in enumerate(cells) if _NET.search(c) and i != name]
                net = nets[-1] if nets else None
                pct = next((i for i, c in enumerate(cells) if _PCT.search(c)), None)
                for row in rows[at + 1:]:
                    cells_r = [re.sub(r"\s+", " ", c or "").strip() for c in row]
                    if len(cells_r) <= max(name, qty) or not cells_r[name] or re.search(r"toplam|matrah|hesaplanan|yalnız", cells_r[name], re.I):
                        continue
                    amount = money(cells_r[net]) if net is not None and net < len(cells_r) else None
                    if amount is None:
                        continue
                    quantity, unit = _quantity(cells_r[qty])
                    lines.append({"name": cells_r[name][:200], "quantity": quantity, "unit": unit, "net_cents": amount,
                                  "vat_percent": _pct(cells_r[pct]) if pct is not None and pct < len(cells_r) else None})
                break
    return lines


def from_text(text):
    """GİB-like layout as plain text: sıra / ad (one or more lines) / '1 Adet' / birim fiyat / %KDV / KDV / tutar."""
    tokens = [t.strip() for t in text.splitlines() if t.strip()]
    starts = [i for i, t in enumerate(tokens)
              if re.search(r"(mal|malzeme)\s*/?\s*hizmet\s*tutar[ıi]|^tutar[ıi]$|^TUTARI?$", t, re.I)]
    if not starts:
        return []
    qty_line = re.compile(r"^([\d.,]+)\s+([A-Za-zÇĞİÖŞÜçğıöşü.]+)$")
    lines, i = [], starts[0] + 1
    while i < len(tokens) - 3:
        at = next((k for k in range(i + 2, min(i + 6, len(tokens))) if qty_line.match(tokens[k])), None)
        if re.fullmatch(r"\d{1,3}", tokens[i]) and at is not None:
            name, quantity = " ".join(tokens[i + 1:at]), qty_line.match(tokens[at])
            j, money_tokens, pct = at + 1, [], None
            while j < len(tokens) and len(money_tokens) < 5:
                tok = tokens[j]
                if re.match(r"^%\s*[\d,]+$", tok):
                    pct = _pct(tok)
                elif re.fullmatch(r"\d[\d.]*,\d{2}\s*(TL)?", tok):
                    money_tokens.append(tok)
                elif re.fullmatch(r"\d{1,3}", tok) or re.search(r"genel açıklama|toplam|yalnız|hesaplanan|ARA TUTAR", tok, re.I):
                    break
                j += 1
            if money_tokens:
                quantity_value, unit = _quantity(f"{quantity.group(1)} {quantity.group(2)}")
                lines.append({"name": name[:200], "quantity": quantity_value, "unit": unit,
                              "net_cents": money(money_tokens[-1]), "vat_percent": pct})
            i = j
        else:
            i += 1
    return lines


def adds_up(lines, payable, tax):
    if not lines or not payable:
        return False
    net = sum(line["net_cents"] for line in lines)
    if net <= 0:
        return False
    slack = max(200, payable // 500)
    return (abs(net + tax - payable) <= slack or abs(net - payable) <= slack
            or any(abs(int(net * rate) - payable) <= slack for rate in VAT_RATES))


def read_lines(pages, text, payable, tax, party=""):
    """The first reader whose lines add up wins; numbered from 1, VAT amount filled from the rate."""
    candidates = [from_tables(pages), from_text(text)]
    if re.search(r"tt mob[İi]l", party, re.I) and payable:
        candidates.append([{"name": "Mobil hat faturası", "quantity": Decimal(1), "unit": "ay",
                            "net_cents": payable - tax, "vat_percent": None}])
    for lines in candidates:
        if adds_up(lines, payable, tax):
            net = sum(line["net_cents"] for line in lines)
            if tax and abs(net - payable) <= max(200, payable // 500):  # the column was VAT-inclusive (TYA)
                for line in lines:
                    line["net_cents"] = round(line["net_cents"] * (payable - tax) / net)
            for number, line in enumerate(lines, 1):
                line["line_no"] = number
                rate = line["vat_percent"]
                line["vat_cents"] = int(line["net_cents"] * rate / 100) if rate is not None else 0
            return lines
    return []
