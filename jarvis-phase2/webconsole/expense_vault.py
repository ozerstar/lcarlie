"""Owner-scoped expense evidence: shared receipts and company invoices."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from zoneinfo import ZoneInfo

from personal_action_store import _connect

MAX_BYTES = 12 * 1024 * 1024
ZONE = ZoneInfo("Europe/Istanbul")
KINDS = {"receipt", "invoice"}
COMPANIES = {"lemos", "moy", "unknown"}


class ExpenseError(ValueError):
    pass


class ExpenseConflict(ExpenseError):
    pass


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ExpenseError("Belge kimliği geçersiz.")
    return value


def _text(value, label, limit=200):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ExpenseError(f"{label} geçersiz.")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ExpenseError(f"{label} geçersiz.")
    return value.strip()


def _money(value, label):
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{1,2}", raw):
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", raw):
        raw = raw.replace(",", ".")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ExpenseError(f"{label} geçersiz.") from exc
    if not number.is_finite() or number < 0 or number > 1_000_000_000 or number.as_tuple().exponent < -2:
        raise ExpenseError(f"{label} geçersiz.")
    return int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _day(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ExpenseError("Belge tarihi geçersiz.") from exc


def _mime(data):
    if data.startswith(b"%PDF-"):
        import fitz
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                if not 0 < len(pdf) <= 20:
                    raise ExpenseError("PDF en fazla 20 sayfa olabilir.")
        except ExpenseError:
            raise
        except Exception as exc:
            raise ExpenseError("PDF okunamadı.") from exc
        return "application/pdf"
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            # MPO: iPhone HDR photos are JPEGs carrying a second (gain map) frame
            mime = {"JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png",
                    "WEBP": "image/webp"}.get(image.format)
            if mime:
                return mime
            rejected = image.format
    except Exception as exc:
        print(f"[expense] görsel okunamadı: {data[:12].hex()} {exc}", file=sys.stderr)
        raise ExpenseError("Görsel okunamadı.") from exc
    print(f"[expense] desteklenmeyen biçim: {rejected}", file=sys.stderr)
    raise ExpenseError("JPG, PNG, WebP veya PDF yükleyin.")


def _heic_to_jpeg(data):
    """Gallery photos from phones are often HEIC; archive them as upright JPEG."""
    if data[4:8] != b"ftyp" or data[8:12] not in {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}:
        return data
    try:
        import pillow_heif
        from PIL import Image, ImageOps
        pillow_heif.register_heif_opener()
        image = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=90)
    except Exception as exc:
        raise ExpenseError("HEIC fotoğraf okunamadı; telefonda JPG olarak paylaşmayı deneyin.") from exc
    if len(buffer.getvalue()) > MAX_BYTES:
        raise ExpenseError("Dosya 12 MB veya daha küçük olmalı.")
    return buffer.getvalue()


def upload(owner, data, filename, kind, company="unknown", *, origin="upload",
           message_id="", attachment_id="", note=""):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ExpenseError("Dosya 12 MB veya daha küçük olmalı.")
    filename = _text(filename, "Dosya adı", 160)
    if not filename:
        raise ExpenseError("Dosya adı gerekli.")
    if kind not in KINDS or origin not in {"upload", "gmail"}:
        raise ExpenseError("Belge türü geçersiz.")
    if kind == "receipt":
        company = "common"
    elif company not in COMPANIES:
        raise ExpenseError("Fatura şirketi geçersiz.")
    data = _heic_to_jpeg(data)
    mime = _mime(data)
    digest = hashlib.sha256(data).hexdigest()
    doc_id = uuid.uuid4().hex
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_expense_document
            (document_id,owner,kind,company,origin,source_message_id,source_attachment_id,
             filename,mime_type,sha256,content,note,extracted)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING RETURNING document_id""",
            (doc_id, owner, kind, company, origin, message_id, attachment_id,
             filename, mime, digest, data, _text(note, "Not", 2000), Jsonb({})))
        row = cur.fetchone()
        if row is None:
            cur.execute("""SELECT document_id FROM core.jarvis_expense_document
                WHERE owner=%s AND sha256=%s""", (owner, digest))
            existing = cur.fetchone()
            if existing:
                return {"id": existing["document_id"], "reused": True}
            raise ExpenseConflict("Bu e-posta eki zaten kaydedildi.")
    return {"id": doc_id, "status": "uploaded", "reused": False}


def list_documents(owner, period=None):
    if period is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(period)):
        raise ExpenseError("Ay geçersiz.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id AS id,kind,company,origin,filename,mime_type,
            document_date,supplier,buyer,invoice_number,currency,gross_cents,tax_cents,
            note,status,extracted,created_at,updated_at
            FROM core.jarvis_expense_document WHERE owner=%s
            AND (%s::text IS NULL OR to_char(created_at AT TIME ZONE 'Europe/Istanbul','YYYY-MM')=%s)
            ORDER BY created_at DESC,document_id DESC LIMIT 500""", (owner, period, period))
        rows = [dict(row, document_date=str(row["document_date"]) if row["document_date"] else "",
                     created_at=row["created_at"].isoformat(),
                     updated_at=row["updated_at"].isoformat()) for row in cur.fetchall()]
        cur.execute("""SELECT period,part,status,document_count,sent_at,error
            FROM core.jarvis_expense_dispatch WHERE owner=%s
            ORDER BY period DESC,part DESC LIMIT 24""", (owner,))
        runs = [dict(row, sent_at=row["sent_at"].isoformat() if row["sent_at"] else "")
                for row in cur.fetchall()]
    return {"documents": rows, "dispatches": runs}


def content(owner, document_id):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT filename,mime_type,content FROM core.jarvis_expense_document
            WHERE owner=%s AND document_id=%s""", (owner, _id(document_id)))
        row = cur.fetchone()
    if not row:
        raise ExpenseError("Belge bulunamadı.")
    return row["filename"], row["mime_type"], bytes(row["content"])


def update(owner, document_id, body):
    if not isinstance(body, dict):
        raise ExpenseError("Belge bilgileri geçersiz.")
    kind = body.get("kind")
    company = body.get("company")
    if kind not in KINDS:
        raise ExpenseError("Belge türü geçersiz.")
    if kind == "receipt":
        company = "common"
    elif company not in COMPANIES:
        raise ExpenseError("Fatura şirketi geçersiz.")
    status = body.get("status", "ready")
    if status not in {"review", "ready", "excluded"}:
        raise ExpenseError("Belge durumu geçersiz.")
    currency = _text(body.get("currency") or "TRY", "Para birimi", 3).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ExpenseError("Para birimi geçersiz.")
    gross = _money(body.get("gross"), "Toplam")
    tax = _money(body.get("tax"), "KDV")
    if gross is not None and tax is not None and tax > gross:
        raise ExpenseError("KDV toplamdan büyük olamaz.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_expense_document SET
            kind=%s,company=%s,document_date=%s,supplier=%s,buyer=%s,
            invoice_number=%s,currency=%s,gross_cents=%s,tax_cents=%s,
            note=%s,status=%s,updated_at=clock_timestamp()
            WHERE owner=%s AND document_id=%s RETURNING document_id""",
            (kind, company, _day(body.get("document_date")),
             _text(body.get("supplier"), "Satıcı", 200),
             _text(body.get("buyer"), "Alıcı", 200),
             _text(body.get("invoice_number"), "Fatura numarası", 100),
             currency, gross, tax, _text(body.get("note"), "Not", 2000),
             status, owner, _id(document_id)))
        if cur.fetchone() is None:
            raise ExpenseError("Belge bulunamadı.")
    return {"id": document_id, "status": status}


_MONTHS = {"ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
           "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
           "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
           "kasim": 11, "aralık": 12, "aralik": 12, "january": 1, "february": 2,
           "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
           "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
           "oca": 1, "şub": 2, "sub": 2, "nis": 4, "haz": 6,
           "tem": 7, "ağu": 8, "agu": 8, "eyl": 9, "eki": 10, "kas": 11, "ara": 12}


def _quick_extract(text):
    """Conservative extraction from machine text; all fields still need review."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {"supplier": "", "buyer": "", "date": "", "invoice_number": "",
              "currency": "TRY", "gross": "", "tax": ""}
    dates = []
    for index, line in enumerate(lines):
        low = line.casefold()
        if "fatura tarih" in low or "invoice date" in low or "date of issue" in low:
            dates.extend((line, lines[index + 1] if index + 1 < len(lines) else ""))
    dates.extend(lines[:25])
    for candidate in dates:
        iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", candidate)
        dmy = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", candidate)
        named = re.search(r"\b(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(20\d{2})\b", candidate, re.I)
        english = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})\b", candidate, re.I)
        try:
            if iso:
                result["date"] = date(int(iso[1]), int(iso[2]), int(iso[3])).isoformat()
            elif dmy:
                result["date"] = date(int(dmy[3]), int(dmy[2]), int(dmy[1])).isoformat()
            elif named and named[2].casefold() in _MONTHS:
                result["date"] = date(int(named[3]), _MONTHS[named[2].casefold()], int(named[1])).isoformat()
            elif english and english[1].casefold() in _MONTHS:
                result["date"] = date(int(english[3]), _MONTHS[english[1].casefold()], int(english[2])).isoformat()
        except ValueError:
            continue
        if result["date"]:
            break
    for index, line in enumerate(lines):
        match = re.search(r"(?:fatura\s*(?:no|numarası)|invoice\s*(?:number|no))\s*[:#-]?\s*([A-Z0-9-]{5,40})", line, re.I)
        if match:
            result["invoice_number"] = match[1]
            break
        if re.fullmatch(r"(?:Fatura No|Fatura numarası|Invoice number)", line, re.I) and index + 1 < len(lines):
            candidate = lines[index + 1]
            if re.fullmatch(r"[A-Z0-9-]{5,40}", candidate, re.I):
                result["invoice_number"] = candidate
                break
    if "$" in text or re.search(r"\bUSD\b", text):
        result["currency"] = "USD"
    amounts = []
    money_pattern = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2})(?!\d)")
    for line in lines:
        if not any(mark in line for mark in ("₺", "$", " TL", " TRY", " USD")):
            continue
        for match in money_pattern.finditer(line):
            raw = match[1]
            if "," in raw and "." in raw and raw.rfind(".") > raw.rfind(","):
                raw = raw.replace(",", "")
            try:
                value = _money(raw, "Tutar")
            except ExpenseError:
                continue
            if value is not None:
                amounts.append(value)
    if amounts:
        result["gross"] = f"{max(amounts)/100:.2f}"
    for index, line in enumerate(lines):
        if re.search(r"\bKDV\b|\bVAT\b", line, re.I) and not re.search(r"registration|numarası|number", line, re.I):
            for next_line in lines[index:index + 3]:
                if any(mark in next_line for mark in ("₺", "$", " TL", " TRY", " USD")):
                    match = money_pattern.search(next_line)
                    if match:
                        try:
                            result["tax"] = f"{_money(match[1], 'KDV')/100:.2f}"
                        except ExpenseError:
                            pass
                        break
            if result["tax"]:
                break
    for index, line in enumerate(lines[:30]):
        if re.fullmatch(r"(?:fatura sahibi|bill to|billed to|alıcı)", line, re.I):
            if index + 1 < len(lines):
                result["buyer"] = lines[index + 1][:200]
                break
    if not result["buyer"]:
        for line in lines[:30]:
            if re.search(r"\bLEMOS\b", line, re.I) and "@" not in line:
                result["buyer"] = line[:200]
                break
            if re.search(r"\bMOY\b", line, re.I) and "@" not in line:
                result["buyer"] = line[:200]
                break
    return result


_RECEIPT_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d{1,6})\s?[.,]\s?(\d{2})(?!\d)")
_RECEIPT_TOTAL = re.compile(r"\bTOPLAM\b|^TOP\b|TUTAR|KRED[İI]|KART|NAK[İI]T|EFT[- ]?POS", re.I)
_RECEIPT_TAX = re.compile(r"KDV", re.I)
# "Ödenecek KDV Dahil Tutar" is the total, not the tax
_RECEIPT_GROSS_WITH_KDV = re.compile(r"DENECEK|KDV\s*DAH", re.I)
# The slip's own printed VAT total; mixed-rate slips (BİM: %1 + %20) fit no single rate
_RECEIPT_PRINTED_TAX = re.compile(r"TOP\w*\s*KDV|^KDV\b", re.I)
_VAT_RATES = (1, 10, 20)


def _receipt_amounts(line):
    values = []
    for match in _RECEIPT_AMOUNT.finditer(line):
        try:
            value = _money(match[1].replace(".", "") + "." + match[2], "Tutar")
        except ExpenseError:
            continue
        if value:
            values.append(value)
    return values


def _receipt_extract(text):
    """Turkish cash-register slip (ÖKC fişi): TOPLAM/TOPKDV, dd/mm/yy dates.

    Photo OCR misreads digits (700,00 -> "700 , 20"), so every total-like line
    votes and a total whose VAT matches a printed KDV amount wins.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {}
    totals, taxes, printed = [], [], []
    for index, line in enumerate(lines):
        near = lines[max(0, index - 1):index + 2]
        own = _receipt_amounts(line)
        if _RECEIPT_TAX.search(line) and not _RECEIPT_GROSS_WITH_KDV.search(line):
            taxes.extend(value for candidate in near for value in _receipt_amounts(candidate))
            if _RECEIPT_PRINTED_TAX.search(line):
                printed.extend(own)
        elif _RECEIPT_TOTAL.search(line) or _RECEIPT_GROSS_WITH_KDV.search(line):
            found = own or [value for candidate in near for value in _receipt_amounts(candidate)]
            # the payable/total line outvotes a card line misread as 721.60
            weight = 2 if re.search(r"DENECEK|KDV\s*DAH\w*\s*TUTAR|\bTOPLAM\b|^TOP\b", line, re.I) else 1
            totals.extend(found * weight)
    if printed:
        taxes = printed
    pair = None
    for gross in sorted(set(totals), key=lambda value: (-totals.count(value), -value)):
        for tax in set(taxes):
            if tax < gross and any(abs(gross * rate / (100 + rate) - tax) <= 1 for rate in _VAT_RATES):
                pair = (gross, tax)
                break
        if pair:
            break
    if pair:
        result["gross"], result["tax"] = (f"{value / 100:.2f}" for value in pair)
        result["vat_match"] = True
    elif totals:
        gross = max(set(totals), key=lambda value: (totals.count(value), value))
        result["gross"] = f"{gross / 100:.2f}"
        smaller = [value for value in taxes if value < gross]
        if smaller:
            result["tax"] = f"{max(smaller, key=taxes.count) / 100:.2f}"
    today = datetime.now(ZONE).date()
    for line in lines:
        # PaddleOCR may glue the time on: "01.11.202620:34"
        for match in re.finditer(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2}(?=\d{1,2}:\d{2})|20\d{2}(?!\d)|\d{2}(?!\d))", line):
            year = int(match[3]) if len(match[3]) == 4 else 2000 + int(match[3])
            try:
                found = date(year, int(match[2]), int(match[1]))
            except ValueError:
                continue
            if today - timedelta(days=3 * 365) <= found <= today + timedelta(days=1):
                result["date"] = found.isoformat()
                break
        if "date" in result:
            break
    number = re.search(r"F[İI][ŞS]\s*NO\s*[:.]?\s*(\d{1,8})", text, re.I)
    if number:
        result["invoice_number"] = number[1]
    # colon forms first: "SAAT 3 20:19:22" must not become 03:20
    for pattern in (r"SAAT\s*[:.]?\s*(?:\d\s+)?(\d{1,2})[:.](\d{2})(?!\d)",
                    r"(?<![\d:])(\d{1,2}):(\d{2})(?::\d{2})?(?![\d:])",
                    r"SAAT\s*[:.]?\s*(\d{1,2}) (\d{2})(?!\d)"):
        for match in re.finditer(pattern, text, re.I):
            if int(match[1]) < 24 and int(match[2]) < 60:
                result["time"] = f"{int(match[1]):02d}:{match[2]}"
                break
        if "time" in result:
            break
    # seller is in the header, above the first priced line (the bank "A.Ş." is below)
    priced = next((index for index, line in enumerate(lines) if _receipt_amounts(line)), len(lines))
    head = [line for line in lines[:min(priced, 12)]
            if not re.search(r"FATURA|F[İI][ŞS]\b|E-?AR[ŞS]", line, re.I)]
    legal = [line for line in head if re.search(r"\bA\.?\s?[ŞS]\b|\bLTD\b|\b[ŞS]T[İI]\b|\bT[İI]C\b", line, re.I)]
    for line in legal or head[:8]:
        if len(re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", line)) >= 6 and not re.search(r"\d{3}", line):
            result["supplier"] = line[:200]
            break
    result["currency"] = "EUR" if re.search(r"\bEUR\b", text) else "USD" if re.search(r"\bUSD\b", text) else "TRY"
    return result


def _prepare_image(data, side):
    """Phone photos store rotation in EXIF; OCR and the vision model need it applied."""
    from PIL import Image, ImageOps
    image = ImageOps.exif_transpose(Image.open(BytesIO(data)))
    image.thumbnail((side, side))
    return image


PADDLE_PYTHON = "/opt/lcarlie/ocr-venv/bin/python"
PADDLE_SCRIPT = "/opt/lcarlie/ocr/paddle_ocr.py"
PADDLE_CACHE = "/opt/lcarlie/ocr/cache"


def _paddle(image):
    """PaddleOCR (separate venv): reads curled, faint slips tesseract garbles.

    Measured on four real slips: dates 3/4 vs 1/4, seller names readable.
    Empty string when the engine is missing or fails; tesseract then runs.
    """
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".img") as handle:
        handle.write(image)
        handle.flush()
        try:
            run = subprocess.run([PADDLE_PYTHON, PADDLE_SCRIPT, handle.name], capture_output=True,
                timeout=240, check=True,
                env={"PATH": "/usr/bin:/bin", "HOME": PADDLE_CACHE, "PADDLE_PDX_CACHE_HOME": PADDLE_CACHE,
                     "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True", "OMP_NUM_THREADS": "2",
                     "LANG": os.environ.get("LANG", "C.UTF-8")})
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            print(f"[expense] paddleocr kullanılamadı: {str(exc)[:160]}", file=sys.stderr)
            return ""
    return run.stdout.decode("utf-8", "replace")


def _tesseract(image, side):
    try:
        buffer = BytesIO()
        _prepare_image(image, side).convert("L").save(buffer, "PNG")
        image = buffer.getvalue()
    except Exception:  # noqa: BLE001 - unreadable image still goes to OCR as uploaded
        pass
    try:
        run = subprocess.run(["tesseract", "stdin", "stdout", "-l", "tur+eng"],
            input=image, capture_output=True, timeout=60, check=True)
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return run.stdout.decode("utf-8", "replace")


def _ocr(data, mime, kind="invoice"):
    import fitz
    text = ""
    image = None
    if mime == "application/pdf":
        with fitz.open(stream=data, filetype="pdf") as pdf:
            text = "\n".join(pdf[index].get_text() for index in range(min(len(pdf), 5)))[:30000]
            if len(text.strip()) < 120:
                image = pdf[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
    else:
        image = data
    readings = []
    if image:
        paddle = _paddle(image) if kind == "receipt" else ""
        if paddle.strip() and _receipt_extract(paddle).get("gross"):
            readings.append(paddle)
        else:
            # Tesseract twice: 3600 px keeps digits on long slips (BİM 721,50 was
            # unreadable at 2400) but 2400 kept a fiş no that 3600 lost.
            for side in (2400, 3600) if kind == "receipt" else (2400,):
                readings.append(_tesseract(image, side))
            if paddle.strip():
                readings.insert(0, paddle)
        text = (text + "\n" + readings[0])[:30000]
    if len(text.strip()) >= 120:
        parsed = _quick_extract(text)
        if kind == "receipt":
            candidates = [_receipt_extract(reading) for reading in readings if reading.strip()]
            candidates = candidates or [_receipt_extract(text)]
            best = max(candidates, key=lambda found: (bool(found.get("vat_match")),
                                                      bool(found.get("gross")), len(found)))
            for found in candidates:
                parsed.update({key: value for key, value in found.items() if value})
            parsed.update({key: value for key, value in best.items() if value})
        return parsed, text[:30000]
    if image:
        buffer = BytesIO()
        _prepare_image(image, 1280).convert("RGB").save(buffer, "JPEG", quality=85)
        image = buffer.getvalue()
    prompt = ("Fiş veya faturadan yalnız görünen veriyi JSON olarak çıkar; tahmin etme. "
              "Şema: {\"supplier\":\"\",\"buyer\":\"\",\"date\":\"YYYY-MM-DD veya boş\","
              "\"invoice_number\":\"\",\"currency\":\"TRY\",\"gross\":\"0.00 veya boş\","
              "\"tax\":\"0.00 veya boş\"}. SAYIN bölümü alıcıdır. "
              "Genel toplamı seç; vergi matrahını toplam sanma."
              "\nBelge metni:\n" + text)
    message = {"role": "user", "content": prompt}
    if image and len(text.strip()) < 120:
        message["images"] = [base64.b64encode(image).decode("ascii")]
    model = "qwen3-vl:2b" if "images" in message else "qwen3:1.7b"
    payload = json.dumps({"model": model, "stream": False, "think": False,
        "format": "json", "messages": [message],
        "options": {"temperature": 0, "num_predict": 400}}, ensure_ascii=False).encode()
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", payload,
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = json.loads(response.read(800000))["message"]["content"]
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ExpenseError("Belge bilgileri okunamadı.")
    return parsed, text[:30000]


def _duplicate_reason(new, other):
    """Same amount and date is not enough: six real invoices share 360,00 TL.

    Returns (sure, reason) when `other` looks like the same document, else None.
    A differing receipt/invoice number rules a duplicate out.
    """
    new_number, other_number = new.get("number") or "", other.get("number") or ""
    if new_number and other_number:
        return (True, "aynı fiş/fatura no " + new_number) if new_number == other_number else None
    new_time, other_time = new.get("time") or "", other.get("time") or ""
    if new_time and new_time == other_time:
        return True, "aynı saat " + new_time
    # a differing time is not proof: OCR read BİM's 20:35 as 20:34
    def name(value):  # OCR mixes I/ı/İ: "OVALI" and "Ovalı" are the same shop
        return re.sub(r"\W", "", (value or "").casefold().replace("ı", "i").replace("i̇", "i"))[:6]
    new_name, other_name = name(new.get("supplier")), name(other.get("supplier"))
    if new_name and other_name and new_name != other_name:
        return None
    return False, "aynı tutar ve tarih"


def _find_duplicate(cur, owner, document_id, kind, data):
    if data["gross_cents"] is None or data["document_date"] is None:
        return None
    cur.execute("""SELECT document_id,filename,created_at,supplier,invoice_number,
        extracted->'fields'->>'time' AS time FROM core.jarvis_expense_document
        WHERE owner=%s AND kind=%s AND document_id<>%s AND status<>'excluded'
        AND gross_cents=%s AND document_date=%s ORDER BY created_at LIMIT 20""",
        (owner, kind, document_id, data["gross_cents"], data["document_date"]))
    new = {"number": data["invoice_number"], "time": data["extracted"]["fields"].get("time"),
           "supplier": data["supplier"]}
    possible = None
    for row in cur.fetchall():
        found = _duplicate_reason(new, {"number": row["invoice_number"], "time": row["time"],
                                        "supplier": row["supplier"]})
        if found:
            match = {"id": row["document_id"], "filename": row["filename"],
                     "uploaded_at": row["created_at"].isoformat(), "sure": found[0], "reason": found[1]}
            if found[0]:
                return match
            possible = possible or match
    return possible


def _company_from_buyer(buyer):
    if "@" in str(buyer):
        return "unknown"
    normalized = re.sub(r"[^a-z0-9]", "", str(buyer).casefold()
                        .replace("ı", "i").replace("ö", "o"))
    if "lemos" in normalized:
        return "lemos"
    if re.search(r"\bmoy\b", str(buyer), re.I):
        return "moy"
    return "unknown"


def process(owner, document_id, *, force=False):
    document_id = _id(document_id)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT content,mime_type,kind,company,status,filename FROM core.jarvis_expense_document
            WHERE owner=%s AND document_id=%s""", (owner, document_id))
        row = cur.fetchone()
    if not row:
        raise ExpenseError("Belge bulunamadı.")
    if row["status"] != "uploaded" and not (force and row["status"] == "review"):
        return {"id": document_id, "status": row["status"]}
    try:
        parsed, evidence = _ocr(bytes(row["content"]), row["mime_type"], row["kind"])
        parsed.setdefault("time", "")
        if not parsed.get("invoice_number") and row["kind"] == "invoice":
            filename_number = re.search(r"(?:fatura|invoice)[-_ ]([A-Z0-9-]{5,40})", row["filename"], re.I)
            if filename_number:
                parsed["invoice_number"] = filename_number[1].rsplit(".", 1)[0]
        day = _day(parsed.get("date"))
        gross = _money(parsed.get("gross"), "Toplam")
        tax = _money(parsed.get("tax"), "KDV")
        company = ("common" if row["kind"] == "receipt" else
                   row["company"] if row["company"] != "unknown" else
                   _company_from_buyer(parsed.get("buyer")))
        if gross is not None and tax is not None and tax > gross:
            tax = None
        data = {"supplier": _text(parsed.get("supplier"), "Satıcı", 200),
                "buyer": _text(parsed.get("buyer"), "Alıcı", 200),
                "invoice_number": _text(parsed.get("invoice_number"), "Fatura numarası", 100),
                "document_date": day, "gross_cents": gross, "tax_cents": tax,
                "currency": parsed.get("currency") if parsed.get("currency") in {"TRY", "EUR", "USD"} else "TRY",
                "company": company, "extracted": {"fields": parsed, "evidence": evidence[:5000]}}
    except Exception as exc:  # noqa: BLE001 - original always remains available
        data = {"extracted": {"error": str(exc)[:180]}}
    with _connect() as conn, conn.cursor() as cur:
        if "supplier" in data:
            # Same slip photographed twice: a sure match is left out of the package,
            # a possible one only gets a warning; both stay editable in the archive.
            duplicate = _find_duplicate(cur, owner, document_id, row["kind"], data)
            status, note = "review", ""
            if duplicate:
                data["extracted"]["duplicate"] = duplicate
                if duplicate["sure"]:
                    status = "excluded"
                    note = f"Tekrar: {duplicate['filename']} ile aynı belge ({duplicate['reason']})."
            cur.execute("""UPDATE core.jarvis_expense_document SET
                supplier=CASE WHEN supplier='' THEN %s ELSE supplier END,
                buyer=CASE WHEN buyer='' THEN %s ELSE buyer END,
                invoice_number=CASE WHEN invoice_number='' THEN %s ELSE invoice_number END,
                document_date=COALESCE(document_date,%s),
                gross_cents=COALESCE(gross_cents,%s),tax_cents=COALESCE(tax_cents,%s),
                currency=%s,company=%s,extracted=%s,status=%s,
                note=CASE WHEN note='' THEN %s ELSE note END,
                updated_at=clock_timestamp() WHERE owner=%s AND document_id=%s
                AND status IN ('uploaded','review')""",
                (data["supplier"], data["buyer"], data["invoice_number"],
                 data["document_date"], data["gross_cents"], data["tax_cents"],
                 data["currency"], data["company"], Jsonb(data["extracted"]), status, note,
                 owner, document_id))
        else:
            cur.execute("""UPDATE core.jarvis_expense_document SET extracted=%s,
                status='review',updated_at=clock_timestamp()
                WHERE owner=%s AND document_id=%s AND status IN ('uploaded','review')""",
                (Jsonb(data["extracted"]), owner, document_id))
    return {"id": document_id, "status": "review"}


_running = set()
_running_lock = threading.Lock()
_ocr_slot = threading.Semaphore(1)


def start_processing(owner, document_id, *, force=False):
    key = (owner, _id(document_id))
    with _running_lock:
        if key in _running:
            return
        _running.add(key)
    def run():
        try:
            with _ocr_slot:
                process(owner, document_id, force=force)
        finally:
            with _running_lock:
                _running.discard(key)
    threading.Thread(target=run, name="expense-ocr", daemon=True).start()


def _gmail_json(path, token):
    request = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/" + path,
        headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read(20_000_000))


def _mail_kind(filename, subject):
    lowered = filename.casefold()
    if not lowered.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp")):
        return None
    if not any(word in lowered + " " + subject.casefold() for word in
               ("fatura", "invoice", "receipt", "fiş", "fis", "makbuz")):
        return None
    return ("receipt" if any(word in lowered for word in
            ("receipt", "fiş", "fis", "makbuz")) else "invoice")


def sync_gmail(owner, *, days=90):
    """Read invoice attachments only. Requires the owner's Gmail read scope."""
    import google_workspace
    token_info = google_workspace._read(google_workspace._path(owner), {})
    if "https://www.googleapis.com/auth/gmail.readonly" not in token_info.get("scope", []):
        raise ExpenseError("Gmail fatura okuma izni gerekli. Jarvis'te Google bağlantısını yenileyin.")
    token = google_workspace._access_token(owner)
    after = (datetime.now(ZONE).date() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"after:{after} has:attachment {{fatura invoice receipt fiş makbuz e-arşiv e-fatura}} -in:spam -in:trash"
    page = ""
    added = reused = 0
    seen_numbered_files = set()
    for _ in range(5):
        params = {"q": query, "maxResults": "100"}
        if page:
            params["pageToken"] = page
        listing = _gmail_json("messages?" + urllib.parse.urlencode(params), token)
        for item in listing.get("messages", []):
            message_id = item["id"]
            message = _gmail_json("messages/" + urllib.parse.quote(message_id) + "?format=full", token)
            headers = {header.get("name", "").casefold(): header.get("value", "")
                       for header in (message.get("payload") or {}).get("headers", [])}
            subject = headers.get("subject", "").casefold()
            sender = headers.get("from", "").casefold()
            stack = [message.get("payload") or {}]
            while stack:
                part = stack.pop()
                stack.extend(part.get("parts") or [])
                filename = part.get("filename") or ""
                lowered = filename.casefold()
                body = part.get("body") or {}
                attachment_id = body.get("attachmentId") or ""
                kind = _mail_kind(filename, subject)
                if not kind or not attachment_id:
                    continue
                numbered = re.search(r"\d{5,}", lowered)
                if numbered:
                    key = (sender, lowered)
                    if key in seen_numbered_files:
                        continue
                    seen_numbered_files.add(key)
                if int(body.get("size") or 0) > MAX_BYTES:
                    continue
                path = "messages/" + urllib.parse.quote(message_id) + "/attachments/" + urllib.parse.quote(attachment_id)
                blob = _gmail_json(path, token).get("data") or ""
                data = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
                try:
                    result = upload(owner, data, filename, kind, "unknown", origin="gmail",
                                    message_id=message_id, attachment_id=attachment_id)
                except ExpenseError:
                    continue
                if result.get("reused"):
                    reused += 1
                else:
                    added += 1
                    process(owner, result["id"])
        page = listing.get("nextPageToken") or ""
        if not page:
            break
    return {"added": added, "reused": reused}


def process_pending(owner, limit=10):
    """Recover OCR jobs after a service restart or one-time mail import."""
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ExpenseError("İşlem sınırı geçersiz.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id FROM core.jarvis_expense_document
            WHERE owner=%s AND status='uploaded' ORDER BY created_at LIMIT %s""", (owner, limit))
        ids = [row["document_id"] for row in cur.fetchall()]
    completed = failed = 0
    for document_id in ids:
        try:
            process(owner, document_id)
            completed += 1
        except Exception:  # noqa: BLE001 - retain the original for the next run
            failed += 1
    return {"completed": completed, "failed": failed}
