"""Owner-scoped invoice evidence, local OCR and controlled ledger import."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import traceback
import threading
import urllib.request
import uuid
from io import BytesIO

import cari
from personal_action_store import _connect

MAX_BYTES = 8 * 1024 * 1024
MIMES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def _validate_file(data, filename):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise cari.CariError("Dosya 8 MB veya daha küçük olmalı.")
    filename = cari._text(filename, "Dosya adı", 160, required=True)
    if data.startswith(b"%PDF-"):
        mime = "application/pdf"
    else:
        from PIL import Image
        try:
            with Image.open(BytesIO(data)) as img:
                img.verify()
                mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(img.format)
        except Exception as exc:
            raise cari.CariError("Görsel veya PDF okunamadı.") from exc
        if mime not in MIMES:
            raise cari.CariError("JPG, PNG, WebP veya PDF yükleyin.")
    return filename, mime


def _pdf_text(data):
    import fitz
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if not 0 < len(pdf) <= 5:
                raise cari.CariError("Fatura PDF en fazla 5 sayfa olabilir.")
            pages = [page.get_text() for page in pdf]
            invoice_numbers = set()
            for page_text in pages:
                invoice_numbers.update(match.group(1).upper() for match in re.finditer(
                    r"Fatura\s+(?:No|Numarası):\s*([A-Z0-9]{12,25})\b", page_text, re.I))
            if len(invoice_numbers) > 1:
                raise cari.CariError(
                    "PDF birden fazla fatura içeriyor; faturaları ayrı dosyalar olarak yükleyin.")
            text = "\n".join(pages)
            if len(text.strip()) >= 120:
                return text[:30000], None
            page = pdf[0]
            image = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False).tobytes("png")
            return text[:30000], image
    except cari.CariError:
        raise
    except Exception as exc:  # noqa: BLE001 - failed OCR remains reviewable
        raise cari.CariError("PDF okunamadı.") from exc


def _ocr(data, mime):
    text, image = _pdf_text(data) if mime == "application/pdf" else ("", data)
    if image:
        try:
            ocr = subprocess.run(["tesseract", "stdin", "stdout", "-l", "tur+eng"],
                input=image, capture_output=True, timeout=25, check=True)
            text = (text + "\n" + ocr.stdout.decode("utf-8", errors="replace")).strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        if len(text) >= 120:
            image = None
    prompt = ("Türkçe fatura verisini yalnız geçerli JSON olarak çıkar. Tahmin etme; okunmayan alana boş değer yaz. "
        "Şema: {\"seller\":{\"name\":\"\",\"tax_id\":\"\",\"tax_office\":\"\",\"address\":\"\",\"email\":\"\",\"phone\":\"\"},"
        "\"buyer\":{aynı alanlar},\"invoice_number\":\"\",\"date\":\"YYYY-MM-DD\",\"due_date\":\"YYYY-MM-DD veya boş\","
        "\"currency\":\"TRY\",\"total\":\"ondalık sayı\",\"items\":[{\"name\":\"\",\"quantity\":1,"
        "\"unit_price\":\"KDV hariç ondalık sayı\",\"discount\":\"yüzde ondalık sayı\","
        "\"tax_rate\":\"yüzde ondalık sayı veya null\"}]} "
        "SAYIN bölümündeki alıcı bilgilerini buyer alanına, faturayı düzenleyeni seller alanına yaz. "
        "Birim fiyat KDV dahilse veya miktar kesin değilse boş bırak. "
        "Faturada yazan satırları aynen kullan. Fatura toplamını yazılı genel toplamdan al.")
    message = {"role": "user", "content": prompt + ("\nPDF metni:\n" + text if text else "")}
    if image:
        message["images"] = [base64.b64encode(image).decode("ascii")]
    model = (os.environ.get("JARVIS_LOCAL_VISION_MODEL", "qwen3-vl:2b") if image else
             os.environ.get("JARVIS_LOCAL_TEXT_MODEL", "qwen3:1.7b"))
    payload = json.dumps({"model": model,
        "stream": False, "think": False, "format": "json", "messages": [message],
        "options": {"temperature": 0, "num_predict": 768}},
        ensure_ascii=False).encode()
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", payload,
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        answer = json.loads(response.read(1000000))
    result = json.loads(answer["message"]["content"])
    if not isinstance(result, dict):
        raise ValueError("Fatura alanları okunamadı.")
    result["_evidence_text"] = text[:30000]
    return result


def _company(value):
    normalized = re.sub(r"[^a-z0-9]", "", str(value).casefold().replace("ı", "i")
                        .replace("é", "e").replace("ü", "u"))
    return "lcarlie" in normalized or "lcarli" in normalized


def _decimal_text(value):
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{1,2}", raw):
        return raw.replace(".", "").replace(",", ".")
    if re.fullmatch(r"\d+,\d{1,2}", raw):
        return raw.replace(",", ".")
    return raw


def _invoice_date(value):
    raw = str(value or "").strip()
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    return cari._day(f"{match[3]}-{match[2]}-{match[1]}" if match else raw, "Fatura tarihi")


def _evidence_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold().replace("ı", "i")
                  .replace("é", "e").replace("ü", "u").replace("ş", "s")
                  .replace("ğ", "g").replace("ç", "c").replace("ö", "o"))


def _candidate(raw, automatic=False):
    """Return validated accounting candidate; ambiguity stays in review."""
    if not isinstance(raw, dict):
        raise cari.CariError("Fatura alanları eksik.")
    seller, buyer = raw.get("seller"), raw.get("buyer")
    if not isinstance(seller, dict) or not isinstance(buyer, dict):
        raise cari.CariError("Satıcı ve alıcı bilgileri gerekli.")
    seller_own, buyer_own = _company(seller.get("name")), _company(buyer.get("name"))
    if seller_own == buyer_own:
        raise cari.CariError("L’CARLIÉ’nin satıcı mı alıcı mı olduğu belirlenemedi.")
    counterparty = buyer if seller_own else seller
    name = cari._text(counterparty.get("name", ""), "Cari adı", 160, required=True)
    if automatic and ("çağrı" in name.casefold() or "cagri" in name.casefold()):
        raise cari.CariError("Çağrı hareketleri otomatik oluşturulmaz; inceleme gerekir.")
    kind = "sale" if seller_own else "purchase"
    items = raw.get("items")
    if not isinstance(items, list) or not items:
        raise cari.CariError("Faturada doğrulanabilir ürün satırı yok.")
    clean_items = []
    for item in items:
        if not isinstance(item, dict):
            raise cari.CariError("Ürün satırı okunamadı.")
        raw_quantity = item.get("quantity")
        if isinstance(raw_quantity, bool) or not re.fullmatch(r"[1-9]\d*", str(raw_quantity)):
            raise cari.CariError("Ürün adedi kesin tam sayı olarak okunamadı.")
        quantity = int(raw_quantity)
        clean_items.append({"name": item.get("name"), "quantity": quantity,
            "unit_price": _decimal_text(item.get("unit_price", "")),
            "discount": _decimal_text(item.get("discount", "0")),
            "tax_rate": None if item.get("tax_rate") is None else _decimal_text(item["tax_rate"])})
    body = {"kind": kind, "date": _invoice_date(raw.get("date")),
        "due_date": _invoice_date(raw["due_date"]) if raw.get("due_date") else "",
        "reference": raw.get("invoice_number") or "", "note": "Fatura görselinden aktarıldı",
        "items": clean_items}
    if not body["reference"]:
        raise cari.CariError("Fatura numarası okunamadı.")
    calculated = cari.calculate(body)
    if calculated["unknown_tax"]:
        raise cari.CariError("KDV oranı eksik; fatura incelemesi gerekli.")
    if raw.get("currency") != "TRY":
        raise cari.CariError("Yalnız TL fatura otomatik kaydedilir.")
    total = cari._money(_decimal_text(raw.get("total", "")), "Fatura toplamı")
    if total != abs(calculated["signed_cents"]):
        raise cari.CariError("Fatura toplamı ürün ve KDV toplamıyla uyuşmuyor.")
    evidence = _evidence_key(raw.get("_evidence_text", ""))
    if automatic:
        if len(evidence) < 80:
            raise cari.CariError("Fatura metni ikinci OCR ile doğrulanamadı; inceleme gerekli.")
        for label, value in (("Satıcı", seller.get("name")), ("Alıcı", buyer.get("name")),
                             ("Fatura numarası", body["reference"])):
            if not value or _evidence_key(value) not in evidence:
                raise cari.CariError(f"{label} belge metninde doğrulanamadı.")
        total_marks = {str(raw.get("total", "")), str(raw.get("total", "")).replace(".", ",")}
        if not any(_evidence_key(mark) in evidence for mark in total_marks):
            raise cari.CariError("Genel toplam belge metninde doğrulanamadı.")
        for item in body["items"]:
            if _evidence_key(item["name"]) not in evidence:
                raise cari.CariError("Ürün adı belge metninde doğrulanamadı.")
            price_marks = {item["unit_price"], item["unit_price"].replace(".", ",")}
            if not any(_evidence_key(mark) in evidence for mark in price_marks):
                raise cari.CariError("Birim fiyat belge metninde doğrulanamadı.")
    details = {key: str(counterparty.get(key) or "").strip() for key in
               ("tax_id", "tax_office", "address", "email", "phone")}
    if automatic and any(details.values()):
        raise cari.CariError("Faturadaki cari kimlik ve iletişim bilgilerini kontrol edin.")
    cari._account_details(details)
    return name, kind, details, body, calculated


def list_documents(owner, account_id=None):
    with _connect() as conn, conn.cursor() as cur:
        if account_id:
            account_id = cari._id(account_id)
            cur.execute("""SELECT document_id AS id,account_id,entry_id,source,filename,mime_type,
                status,extracted,created_at FROM core.jarvis_cari_document
                WHERE owner=%s AND account_id=%s ORDER BY created_at DESC LIMIT 100""",
                (owner, account_id))
        else:
            cur.execute("""SELECT document_id AS id,account_id,entry_id,source,filename,mime_type,
                status,extracted,created_at FROM core.jarvis_cari_document
                WHERE owner=%s ORDER BY created_at DESC LIMIT 100""", (owner,))
        return {"documents": [dict(row, created_at=str(row["created_at"])) for row in cur.fetchall()]}


def content(owner, document_id):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT filename,mime_type,content FROM core.jarvis_cari_document
            WHERE owner=%s AND document_id=%s""", (owner, cari._id(document_id)))
        row = cur.fetchone()
        if not row:
            raise cari.CariNotFound("Belge bulunamadı.")
        return row["mime_type"], bytes(row["content"])


def upload(owner, data, filename, source="invoice", account_id=None, entry_id=None):
    filename, mime = _validate_file(data, filename)
    if source not in ("invoice", "attachment"):
        raise cari.CariError("Belge türü geçersiz.")
    if source == "attachment" and not account_id:
        raise cari.CariError("Ek için cari seçin.")
    if account_id:
        account_id = cari._id(account_id)
    if entry_id:
        entry_id = cari._id(entry_id)
    digest = hashlib.sha256(data).hexdigest()
    doc_id = uuid.uuid4().hex
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        if source == "invoice":
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                        (owner + ':invoice-file:' + digest,))
        if account_id:
            cur.execute("SELECT 1 FROM core.jarvis_cari_account WHERE owner=%s AND account_id=%s",
                        (owner, account_id))
            if not cur.fetchone():
                raise cari.CariNotFound("Cari bulunamadı.")
        if entry_id:
            cur.execute("""SELECT 1 FROM core.jarvis_cari_entry WHERE owner=%s
                AND account_id=%s AND entry_id=%s""", (owner, account_id, entry_id))
            if not cur.fetchone():
                raise cari.CariNotFound("Hareket bulunamadı.")
        if source == "invoice":
            cur.execute("""SELECT document_id FROM core.jarvis_cari_document
                WHERE owner=%s AND sha256=%s AND source='invoice'""", (owner, digest))
            existing = cur.fetchone()
            if existing:
                raise cari.CariConflict("Bu fatura dosyası zaten yüklendi: " + existing["document_id"])
        cur.execute("""INSERT INTO core.jarvis_cari_document
            (document_id,owner,account_id,entry_id,source,filename,mime_type,sha256,content,status,extracted)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'uploaded',%s)""",
            (doc_id, owner, account_id, entry_id, source, filename, mime, digest, data, Jsonb({})))
    return {"id": doc_id, "status": "uploaded"}


def process_document(owner, document_id):
    """Run local OCR after upload; never leave a slow model on the HTTP request."""
    document_id = cari._id(document_id)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT status,source,mime_type,content FROM core.jarvis_cari_document
            WHERE owner=%s AND document_id=%s""", (owner, document_id))
        row = cur.fetchone()
    if not row or row["source"] != "invoice":
        raise cari.CariNotFound("Fatura bulunamadı.")
    if row["status"] != "uploaded":
        return {"id": document_id, "status": row["status"]}
    try:
        extracted = _ocr(bytes(row["content"]), row["mime_type"])
    except Exception as exc:  # noqa: BLE001 - keep the uploaded invoice for manual review
        extracted = {"error": "Fatura otomatik okunamadı: " + str(exc)[:160]}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_cari_document SET extracted=%s,status='review',
            updated_at=clock_timestamp() WHERE owner=%s AND document_id=%s""",
            (Jsonb(extracted), owner, document_id))
    try:
        result = approve(owner, document_id, extracted, automatic=True)
        return dict(result, extracted=extracted)
    except (cari.CariError, ValueError) as exc:
        return {"id": document_id, "status": "review", "reason": str(exc), "extracted": extracted}


_running = set()
_running_lock = threading.Lock()
_ocr_slot = threading.Semaphore(1)


def start_processing(owner, document_id):
    document_id = cari._id(document_id)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source,status FROM core.jarvis_cari_document
            WHERE owner=%s AND document_id=%s""", (owner, document_id))
        row = cur.fetchone()
    if not row or row["source"] != "invoice":
        raise cari.CariNotFound("Fatura bulunamadı.")
    if row["status"] != "uploaded":
        return
    key = (owner, document_id)
    with _running_lock:
        if key in _running:
            return
        _running.add(key)
    def run():
        try:
            with _ocr_slot:
                process_document(owner, document_id)
        except Exception:  # noqa: BLE001 - worker failures must leave evidence for retry
            traceback.print_exc()
        finally:
            with _running_lock:
                _running.discard(key)
    threading.Thread(target=run, name="cari-invoice-ocr", daemon=True).start()


def approve(owner, document_id, extracted=None, automatic=False):
    """Validated import, account, movement and document link in one transaction."""
    document_id = cari._id(document_id)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (owner + ':invoice:' + document_id,))
        cur.execute("""SELECT status,source,extracted,account_id,entry_id FROM core.jarvis_cari_document
            WHERE owner=%s AND document_id=%s""", (owner, document_id))
        doc = cur.fetchone()
        if not doc or doc["source"] != "invoice":
            raise cari.CariNotFound("Fatura bulunamadı.")
        if doc["status"] == "posted":
            return {"id": document_id, "status": "posted", "account_id": doc["account_id"], "entry_id": doc["entry_id"], "reused": True}
        if doc["status"] == "rejected":
            raise cari.CariConflict("Reddedilen fatura kaydedilemez.")
        raw = extracted if extracted is not None else doc["extracted"]
        name, kind, details, body, payload = _candidate(raw, automatic=automatic)
        # Exact tax ID wins; then exact normalized name. Never silently merge conflicting identities.
        tax_id = details["tax_id"]
        cur.execute("""SELECT account_id,name,tax_id FROM core.jarvis_cari_account
            WHERE owner=%s AND ((%s<>'' AND tax_id=%s) OR name_key=%s)""",
            (owner, tax_id, tax_id, name.casefold()))
        matches = cur.fetchall()
        if len({r["account_id"] for r in matches}) > 1:
            raise cari.CariConflict("Fatura cari kimliği iki farklı hesapla uyuşuyor.")
        if matches:
            account = matches[0]
            if tax_id and account["tax_id"] and account["tax_id"] != tax_id:
                raise cari.CariConflict("Cari vergi numarası faturayla uyuşmuyor.")
            account_id = account["account_id"]
            # Enrich only blanks, retaining user edits and existing contact data.
            cur.execute("""UPDATE core.jarvis_cari_account SET
                role=CASE WHEN role='both' OR role=%s THEN role ELSE 'both' END,
                tax_id=CASE WHEN tax_id='' THEN %s ELSE tax_id END,
                tax_office=CASE WHEN tax_office='' THEN %s ELSE tax_office END,
                address=CASE WHEN address='' THEN %s ELSE address END,
                email=CASE WHEN email='' THEN %s ELSE email END,
                phone=CASE WHEN phone='' THEN %s ELSE phone END
                WHERE owner=%s AND account_id=%s""",
                ('customer' if kind == 'sale' else 'supplier', tax_id, details["tax_office"],
                 details["address"], details["email"], details["phone"], owner, account_id))
        else:
            account_id = uuid.uuid4().hex
            cur.execute("""INSERT INTO core.jarvis_cari_account
                (account_id,owner,name,name_key,role,contact,note,tax_id,tax_office,address,email,phone)
                VALUES (%s,%s,%s,%s,%s,'','Fatura aktarımıyla oluşturuldu',%s,%s,%s,%s,%s)""",
                (account_id, owner, name, name.casefold(),
                 'customer' if kind == 'sale' else 'supplier',
                 tax_id, details["tax_office"], details["address"], details["email"], details["phone"]))
        cur.execute("""SELECT entry_id FROM core.jarvis_cari_entry WHERE owner=%s AND account_id=%s
            AND payload->>'reference'=%s AND payload->>'kind'=%s AND reverses IS NULL LIMIT 1""",
            (owner, account_id, body["reference"], kind))
        if cur.fetchone():
            raise cari.CariConflict("Bu fatura numarası bu caride zaten kayıtlı.")
        entry_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO core.jarvis_cari_entry
            (entry_id,owner,account_id,request_id,payload_hash,document_date,payload,signed_cents,unknown_tax)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (entry_id, owner, account_id, 'invoice:' + document_id,
             cari._digest(payload), payload["date"], Jsonb(payload),
             payload["signed_cents"], payload["unknown_tax"]))
        cur.execute("""UPDATE core.jarvis_cari_document SET account_id=%s,entry_id=%s,status='posted',
            extracted=%s,updated_at=clock_timestamp() WHERE owner=%s AND document_id=%s""",
            (account_id, entry_id, Jsonb(raw), owner, document_id))
    return {"id": document_id, "status": "posted", "account_id": account_id,
            "entry_id": entry_id, "automatic": automatic}
