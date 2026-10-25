"""Owner-scoped expense evidence: shared receipts and company invoices."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
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
            mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(image.format)
            if mime:
                return mime
    except Exception as exc:
        raise ExpenseError("Görsel okunamadı.") from exc
    raise ExpenseError("JPG, PNG, WebP veya PDF yükleyin.")


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


def _ocr(data, mime):
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
    if image:
        try:
            run = subprocess.run(["tesseract", "stdin", "stdout", "-l", "tur+eng"],
                input=image, capture_output=True, timeout=30, check=True)
            text = (text + "\n" + run.stdout.decode("utf-8", "replace"))[:30000]
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
    if len(text.strip()) >= 120:
        return _quick_extract(text), text[:30000]
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
        parsed, evidence = _ocr(bytes(row["content"]), row["mime_type"])
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
            cur.execute("""UPDATE core.jarvis_expense_document SET
                supplier=CASE WHEN supplier='' THEN %s ELSE supplier END,
                buyer=CASE WHEN buyer='' THEN %s ELSE buyer END,
                invoice_number=CASE WHEN invoice_number='' THEN %s ELSE invoice_number END,
                document_date=COALESCE(document_date,%s),
                gross_cents=COALESCE(gross_cents,%s),tax_cents=COALESCE(tax_cents,%s),
                currency=%s,company=%s,extracted=%s,status='review',
                updated_at=clock_timestamp() WHERE owner=%s AND document_id=%s
                AND status IN ('uploaded','review')""",
                (data["supplier"], data["buyer"], data["invoice_number"],
                 data["document_date"], data["gross_cents"], data["tax_cents"],
                 data["currency"], data["company"], Jsonb(data["extracted"]),
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
