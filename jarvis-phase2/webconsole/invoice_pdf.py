"""Lemos' e-invoice PDFs (GİB görünümü) → invoices with direction, totals and lines.

Owner, 02.11.2026: "gelen ve gidenleri karıştırma". Direction never comes from the file name or
order: the buyer is the "SAYIN" block; if Lemos' VKN is the buyer's, the invoice is incoming.
The supplier's own series is a second witness ("LMS…" = Lemos' own numbering → outgoing).
"""
import re
from datetime import date
from decimal import Decimal



def lemos_vkn(texts):
    """Lemos' own VKN, read from the files: the VKN printed in the LEMOS MEDİKAL block."""
    from collections import Counter
    seen = Counter()
    for text in texts:
        for at in [m.start() for m in re.finditer(r"LEMOS MED", text)]:
            found = re.search(r"VKN\s*:?\s*(\d{10})", text[at:at + 900])
            if found:
                seen[found[1]] += 1
    if not seen:
        raise ValueError("Lemos VKN dosyada bulunamadı")
    return seen.most_common(1)[0][0]
_ETTN = re.compile(r"ETTN\s*:?\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")
_ID = re.compile(r"(?:VKN|TCKN|Vergi\s*No|Vergi\s*Numaras[ıi]|VKN/TCKN)\s*[:：]?\s*(\d{10,11})\b", re.I)
_NO = re.compile(r"Fatura\s*No\s*:?\s*\n?\s*([A-Z0-9]{3}20\d{2}\d{9})", re.I)
_DAY = re.compile(r"Fatura\s*Tarihi\s*:?\s*\n?\s*(\d{2})[-./](\d{2})[-./](20\d{2})", re.I)
_TOTAL = re.compile(r"(?:Ödenecek\s*Tutar|Vergiler\s*Dahil\s*Toplam\s*Tutar)\s*:?\s*\n?\s*([\d.]+,\d{2})", re.I)
_VAT = re.compile(r"Hesaplanan\s*KDV(?:\s*\(%\s*[\d,]+\))?\s*:?\s*\n?\s*([\d.]+,\d{2})", re.I)


def _tl(text):
    return int(Decimal(text.replace(".", "").replace(",", ".")) * 100)


def split_invoices(pages):
    """Consecutive pages belong to one invoice until the next ETTN."""
    invoices, current = [], None
    for text in pages:
        found = _ETTN.search(text)
        if found and (current is None or found[1].lower() != current["ettn"]):
            current = {"ettn": found[1].lower(), "text": text}
            invoices.append(current)
        elif current is not None:
            current["text"] += "\n" + text
    return invoices


def _block_after(text, marker, size=700):
    at = text.find(marker)
    return text[at:at + size] if at >= 0 else ""


# Lemos' e-fatura and e-arşiv series (only Lemos issues these); TYA = e-arşiv Trendyol issues in
# Lemos' name for its Trendyol sales (owner sent them 02.11.2026, each carries the Trendyol order no)
OWN_SERIES = ("LMS", "LEM", "TYA")
_SAYIN = re.compile(r"\bsay[ıi]n\b", re.I)
_FORM = re.compile(r"(A\.?\s?Ş\.?|ANON[İI]M|L[İI]M[İI]TED|LTD|ŞT[İI]|DERNE[ĞG][İI]|[İI]ŞLETMES[İI]|T[İI]CARET|A\.S\.)", re.I)


def _money_any(text):
    """'36.480,00' (Turkish) or '1936.25' (TT Mobil) → kuruş."""
    if "," in text:
        return _tl(text)
    return int(Decimal(text) * 100)


_GOODS = re.compile(r"Mal\s*/?\s*Hizmet\s*Toplam\s*Tutar[ıi]\s*:?\s*\n?\s*:?\s*(\d[\d.]*,\d{2})", re.I)
_DISCOUNT = re.compile(r"Toplam\s*(?:[İI]skonto|[İI]ndirim)\s*:?\s*\n?\s*:?\s*(\d[\d.]*,\d{2})", re.I)
# every VAT rate has its own line: "Hesaplanan KDV(%20) 1.000,00 / Hesaplanan KDV(%1) 53,96";
# some issuers write "Hesaplanan KDV GERÇEK (%20.0)"
_VATS = re.compile(r"Hesaplanan\s*K\.?D\.?V\.?(?:\s*GER[ÇC]EK)?\s*(?:\(\s*%?\s*[\d.,]+\s*\)\s*)?:?\s*\n?\s*:?\s*(\d[\d.]*,\d{2})", re.I)

_MOBILE_VAT = re.compile(r"\bKDV\s*\(\s*\d+\s*%\s*\)\s*\(\s*Matrah[^)]*\)\s*\n?\s*(\d+\.\d{2})")


def tax_of(text, payable):
    """VAT of the whole invoice (owner, 02.11.2026: "rakamlarda hata istemiyorum").

    Only the last "Hesaplanan KDV" was read before, so an invoice with %20 and %1 lost the %20, and
    layouts that print labels and amounts in two columns lost it all - the invoice then counted with
    VAT as cost. Witness: goods − discount + VAT = payable. When the VAT lines cannot be read, the
    difference between the payable and the goods total is the tax. Returns (tax_cents, how)."""
    vats = [_tl(v) for v in _VATS.findall(text)]
    # TT Mobil: "KDV (20%) (Matrah 1385.79 TL ) 277.16"; ÖİV and the licence fee are not VAT, they stay cost
    mobile = _MOBILE_VAT.findall(text)
    if mobile and not vats:
        return sum(_money_any(v) for v in mobile), "kdv"
    goods = _GOODS.search(text)
    if goods is None or payable is None:
        return (sum(vats), "kdv") if vats else (0, "okunamadi")
    net = _tl(goods[1]) - (_tl(_DISCOUNT.search(text)[1]) if _DISCOUNT.search(text) else 0)
    if vats and abs(net + sum(vats) - payable) <= 100:
        return sum(vats), "kdv"
    if vats and net + sum(vats) < payable:
        return sum(vats), "kdv_diger_vergi"  # accommodation tax etc. stays in the cost
    if 0 <= payable - net <= payable * 0.21 + 100:
        return payable - net, "fark"
    return (sum(vats), "kdv_tutarsiz") if vats else (0, "okunamadi")


def read(invoice, lemos):
    text = invoice["text"]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    number = (re.search(r"Fatura\s*(?:No|Numaras[ıi])\s*:?\s*\n?\s*:?\s*([A-Z]{2,3}[0-9]{6,16})", text, re.I) or [None, ""])[1]
    own_series = number.upper().startswith(OWN_SERIES)
    sayin = next((i for i, l in enumerate(lines) if _SAYIN.search(l)), None)
    buyer_area = lines[sayin:sayin + 6] if sayin is not None else []
    ids = _ID.findall(text)
    # TT Mobil prints "Vergi Dairesi ve VKN : DOĞANBEY VER <no>": the number alone is the witness
    lemos_anywhere = lemos in ids or re.search(rf"(?<!\d){lemos}(?!\d)", text) is not None
    lemos_buys = any("LEMOS" in l.upper() for l in buyer_area) or (sayin is None and lemos_anywhere and not own_series)
    if own_series and not any("LEMOS" in l.upper() for l in buyer_area):
        box = "out"
    elif not own_series and (lemos_buys or lemos_anywhere):
        box = "in"
    else:
        box = None  # the witnesses disagree: shown apart, never filed
    if box == "out":
        rest = re.sub(r"^\s*say[ıi]n\s*,?\s*", "", lines[sayin], flags=re.I) if sayin is not None else ""
        party = rest or next((l for l in buyer_area[1:] if not re.match(r"(adres|tel|vkn|tckn|vergi)", l, re.I)), "")
    else:
        party = _seller(lines, buyer_area)
    # "31 - 10 - 2026" (BST) and "10- 09- 202600:00:00" (GSF) are written with spaces
    day = (re.search(r"(?:Fatura|Düzenle(?:me|nme))\s*Tarihi\s*:?\s*\n?\s*:?\s*(\d{2})\s*[-./]\s*(\d{2})\s*[-./]\s*(20\d{2})", text, re.I)
           or re.search(r"(?:Fatura|Düzenle(?:me|nme))\s*Tarihi\s*:?\s*\n?\s*:?\s*(20\d{2})-(\d{2})-(\d{2})", text, re.I)
           or re.search(r"(?<!\d)(\d{2})[./-](\d{2})[./-](20\d{2})(?!\d)", text))
    if day and len(day[1]) == 4:  # ISO 2026-10-12
        day = [None, day[3], day[2], day[1]]
    total = re.findall(r"(?:Ödenecek\s*Tutar|Vergiler\s*Dahil\s*Toplam\s*Tutar)\s*:?\s*\n?\s*:?\s*(\d[\d.]*,\d{2}|\d+\.\d{2})", text, re.I)
    order = re.search(r"(?:Sipariş|SİPARİŞ)\s*(?:No|NO)\s*:?\s*(\d{6,})", text)
    payable = _money_any(total[-1]) if total else None
    found_lines = parse_lines(text)
    if payable is None or abs(sum(l["net_cents"] + l["vat_cents"] for l in found_lines) - payable) > 100:
        found_lines = []  # only lines that add up to the invoice are kept
    return {"ettn": invoice["ettn"], "box": box, "number": number,
            "date": date(int(day[3]), int(day[2]), int(day[1])) if day else None,
            "party": party.strip()[:200], "party_vkn": next((i for i in ids if i != lemos), ""),
            "payable_cents": payable, "tax_cents": tax_of(text, payable)[0],
            "lines": found_lines, "order_no": order.group(1) if order else "",
            "witness": {"buyer_is_lemos": lemos_buys, "own_series": own_series}}


def _seller(lines, buyer_area):
    """The supplier: a 'Satıcı' label wins; else the first company-looking line that is not Lemos."""
    def looks_like_name(line):
        letters = [c for c in line if c.isalpha()]
        return (len(letters) >= 5 and sum(c.isupper() for c in letters) / len(letters) > 0.6
                and "LEMOS" not in line.upper() and not re.search(r"[:@]|www\.", line))

    for i, line in enumerate(lines[:-1]):
        if re.match(r"sat[ıi]c[ıi]\s*(\(.*\))?\s*:?\s*$", line, re.I):
            name = next((n for n in lines[i + 1:i + 5] if looks_like_name(n)), "")
            if name:
                return name
    for i, line in enumerate(lines):
        if line in buyer_area or "LEMOS" in line.upper() or not _FORM.search(line) or len(line) < 6:
            continue
        if re.match(r"(vergi|ticaret ?sicil|mersis|adres|e-posta|web|tel|özelleştirme|not\b|bu fatura|ve tic)", line, re.I):
            continue
        # invoice notes: "e-Arşiv izni kapsamında elektronik ortamda iletilmiştir" ("iletilmiştir" holds "ŞTİ")
        if re.search(r"e-?ar[şs]iv\s*izni|elektronik\s*ortamda|irsaliye\s*yerine|yaz[ıi]\s*ile", line, re.I):
            continue
        # payment notes name the bank ("T.C. Ziraat Bankası AŞ" was read as NEVA's name, 26.06.2026)
        if re.search(r"banka(s[ıi])?\b|\biban\b|katılım\s*bank", line, re.I):
            continue
        prev = lines[i - 1] if i else ""
        head = prev if prev.isupper() and not _FORM.search(prev) and "LEMOS" not in prev.upper() and not re.search(r"[:\d]", prev) else ""
        return f"{head} {line}".strip()
    return ""


_QTY = re.compile(r"^([\d.,]+)\s+([A-Za-zÇĞİÖŞÜçğıöşü.]+)$")
_PCT = re.compile(r"^%\s*([\d,]+)$")
_MONEY = re.compile(r"^([\d.]+,\d{2})\s*(?:TL)?$")


def parse_lines(text):
    """GİB table: sıra / ad / miktar birim / birim fiyat / … / %KDV / KDV tutarı / tutar."""
    tokens = [t.strip() for t in text.splitlines() if t.strip()]
    try:
        start = max(i for i, t in enumerate(tokens) if re.fullmatch(r"Tutarı", t)) + 1
    except ValueError:
        return []
    lines, i = [], start
    while i < len(tokens) - 2:
        if re.fullmatch(r"\d{1,3}", tokens[i]) and not _QTY.match(tokens[i + 1]):
            name, j = tokens[i + 1], i + 2
            quantity = _QTY.match(tokens[j]) if j < len(tokens) else None
            if not quantity:
                i += 1
                continue
            j += 1
            pct, vat, money = None, 0, []
            while j < len(tokens) and not re.fullmatch(r"\d{1,3}", tokens[j]) and len(money) < 6:
                tok = tokens[j].replace(" TL", "").replace("TL", "").strip()
                if _PCT.match(tokens[j]):
                    pct = Decimal(_PCT.match(tokens[j])[1].replace(",", "."))
                elif re.fullmatch(r"\d[\d.]*,\d{2}", tok) or re.fullmatch(r"\d[\d.]*", tok):
                    money.append(tok)
                elif re.search(r"Mal Hizmet Toplam|Toplam İskonto|Hesaplanan", tokens[j], re.I):
                    break
                j += 1
            if money:
                net = _tl(money[-1]) if "," in money[-1] else int(money[-1].replace(".", "")) * 100
                vat = _tl(money[-2]) if pct is not None and len(money) >= 2 and "," in money[-2] else 0
                lines.append({"line_no": len(lines) + 1, "name": name[:200],
                              "quantity": Decimal(quantity[1].replace(".", "").replace(",", ".")),
                              "unit": quantity[2][:10], "net_cents": net, "vat_percent": pct, "vat_cents": vat})
            i = j
        else:
            i += 1
    return lines
