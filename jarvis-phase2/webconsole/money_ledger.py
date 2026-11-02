"""Para hareketi defteri: nereye, kime, ne için, kimin hesabına ne kadar gitti.

Kaynak: banka hesap dökümü, kredi kartı ekstresi (PDF) veya banka
uygulamasının ekran görüntüsü. Sahip 02.11.2026'da transferlerin de
yorumlanmasını istedi ("aylık, haftalık, günlük nelere harcama yaptığımı
bilmek istiyorum"); bu yüzden kişisel transferler dahil her hareket saklanır.

Kendi hesapları arası para (kendi adına EFT, tatil hesabı, kart borcu ödemesi)
"ic_transfer" sayılır ve toplamlara girmez: kart borcunu ödemek, kartla
yapılan harcamayı ikinci kez saydırmamalı.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime, timedelta

from expense_vault import ZONE, ExpenseError, _connect, _id, _text

OUT_CATEGORIES = {
    "yemek": "Yemek / ikram", "market": "Market / temizlik", "akaryakit": "Akaryakıt",
    "ulasim": "Ulaşım / otopark", "kargo": "Kargo", "reklam": "Reklam",
    "sosyal_medya": "Sosyal medya hizmeti", "hizmet": "Hizmet / serbest çalışan",
    "personel": "Personel / maaş ödemesi", "yazilim": "Yazılım / sunucu / abonelik",
    "ofis": "Ofis / kırtasiye / teknik", "faturalar": "Elektrik / telefon / internet",
    "alisveris": "Online alışveriş", "giyim": "Giyim / aksesuar", "saglik": "Sağlık",
    "eglence": "Eğlence / dışarıda", "aile": "Aile", "borc": "Borç verme / ödeme",
    "kira": "Kira", "banka": "Banka faiz / masraf", "nakit": "Nakit çekim", "diger": "Diğer",
}
IN_CATEGORIES = {
    "gelir": "Maaş / ücret geliri", "aile_gelen": "Aileden gelen", "tahsilat": "Tahsilat / satış",
    "iade": "İade / kampanya", "borc_donus": "Borç geri ödemesi", "diger_gelen": "Diğer gelen",
}
INTERNAL = "ic_transfer"
CATEGORIES = {**OUT_CATEGORIES, **IN_CATEGORIES, INTERNAL: "Kendi hesapların arası"}
SCOPES = {"lemos": "Lemos", "moy": "MOY", "lcarlie": "L'CARLIÉ", "kisisel": "Kişisel / aile"}

_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def plain(value):
    return (value or "").replace("İ", "i").replace("I", "ı").casefold().translate(_ASCII)


def key_of(name):
    """Same person written "Othan/Orhan Talha Canal" or "Moy Danısmalık": letters only."""
    return re.sub(r"[^a-z0-9]", "", plain(name))[:24]


# ------------------------------------------------------------------ okuma
_AMOUNT = re.compile(r"(-\s?)?(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d{1,7}),(\d{2})\s*(?:TL|TRY)", re.I)
_DATE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2}|\d{2})(?!\d)")
_MONTHS = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7,
           "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
_NOISE = re.compile(r"kredi kartlarim|adios|premium|asil kart|son hareketler|kart hareket|volte|vlte|"
                    r"\*\*|ek ?kart|bekleyen|provizyon|yapi ?kredi|tapkred|toplam borc|asgari|"
                    r"hesap kesim|son odeme|^\W*\d{1,2}:\d{2}|ekstre|borcu|limit|minimum|kart numarasi|"
                    r"islem tarihi|^aciklama$|^taksit$|^tutar$|^hareket tipi$|^bakiye$|^tarih$|"
                    # the bank's type column alone on a line ("Para Çekme"), never the description
                    r"^(gelen transfer|giden transfer|encard|harcamasi|encard harcamasi|odeme|diger|"
                    r"iptal/iade|para cekme|masraf/ucret|vergi kesintisi|faiz gideri)$", re.I)
_HEADER = re.compile(r"limit|ekstre borcu|kart numarasi|ad soyad|minimum odeme|hesap adi|iban", re.I)


def _date_in(chunk, today):
    text = plain(chunk)
    numeric = _DATE.search(text)
    if numeric:
        year = int(numeric[3]) if len(numeric[3]) == 4 else 2000 + int(numeric[3])
        try:
            return date(year, int(numeric[2]), int(numeric[1]))
        except ValueError:
            pass
    month = re.search(r"\b(" + "|".join(_MONTHS) + r")\b", text)
    if not month:
        return None
    days = [(abs(match.start() - month.start()), int(match[1]))
            for match in re.finditer(r"(?<![\d.,*:/])\b([0-3]?\d)\b(?![\d.,*:%/])", text)
            if 1 <= int(match[1]) <= 31]
    if not days:
        return None
    number = _MONTHS[month[1]]
    year = re.search(r"\b(20\d{2})\b", text)
    year = int(year[1]) if year else (today.year if number <= today.month else today.year - 1)
    try:
        return date(year, number, min(days)[1])
    except ValueError:
        return None


def _score(text):
    letters = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text)
    upper = sum(letter.isupper() for letter in letters)
    # card merchants are printed in capitals; logo OCR noise ("achos Dremlam") is not
    return len(letters) + (20 if letters and upper / len(letters) >= 0.7 else 0)


def _merchant(chunk):
    best = ""
    for line in chunk.splitlines():
        if _NOISE.search(plain(line).strip()):
            continue
        cleaned = re.sub(r"\b(20\d{2}|[0-3]?\d)\b", " ", line)
        cleaned = re.sub(r"(?i)\b(" + "|".join(_MONTHS) + r"|şubat|mayıs|ağustos|eylül|kasım|aralık)\b", " ", cleaned)
        cleaned = re.sub(r"[^\wÇĞİÖŞÜçğıöşü&.\- /,()]", " ", cleaned)
        cleaned = re.sub(r"(?i)^tr\s+|\s+tr$", "", " ".join(cleaned.split())).strip(" .-/,")
        if plain(cleaned) in _MONTHS:
            continue
        if _score(cleaned) > _score(best):
            best = cleaned
    return best[:160]


def _kind(text, direction):
    """Movement type from the bank's own words."""
    # paying the card from your own account ("Ödeme - Enpara.com Cep Şubesi") is not spending
    if re.search(r"kredi karti odemesi|tatil hesab|odeme - .*cep subesi", text):
        return INTERNAL
    if re.search(r"iptal|iade|kampanya|enparali", text):  # "Ayın Enparalısı ... ATM kampanyası"
        return "iade"
    if re.search(r"giden transfer|gelen transfer|\beft\b|\bfast\b|havale", text):
        return "transfer"
    if re.search(r"para cekme|\batm\b", text):
        return "atm"
    if re.search(r"faiz|kkdf|bsmv|vergi kesintisi|masraf|ucret tahsil", text):
        return "banka"
    if re.search(r"faturasi", text):
        return "fatura"
    return "kart" if direction == "out" else "diger"


def _account(text):
    lowered = plain(text)
    bank = ("Enpara" if "enpara" in lowered else "Yapı Kredi" if re.search(r"yapi ?kredi|adios|tapkred", lowered)
            else "Garanti" if "garanti" in lowered else "Banka")
    last4 = re.search(r"\*{2,}[\s*]*(\d{4})", text)
    # one screenshot shows "Kredi Kartlarım", the next only the masked number: same card
    # not "kredi kart": an account statement lists "Enpara.com kredi kartı ödemesi"
    card_statement = re.search(r"ekstre borcu|kredi karti ekstresi|kredi kartlarim", lowered)
    kind = ("kredi kartı" if card_statement or last4 else "hesap" if "bakiye" in lowered else "kart")
    return f"{bank} {kind}" + (f" ****{last4[1]}" if last4 else "")


def parse_statement(text, today=None):
    """Every "x,xx TL" closes one movement; its date, type and party are looked up in
    the text since the previous amount (screenshots order day/month/party differently).

    Account statement ("Bakiye" column): "-504,99 TL" is money out, unsigned is money
    in or the running balance. Card statement / app screenshot: unsigned is a
    purchase, "-" is your payment or a refund.
    """
    today = today or datetime.now(ZONE).date()
    whole = plain(text)
    account_mode = "bakiye" in whole and not re.search(r"ekstre borcu|kredi karti ekstresi", whole)
    account = _account(text)
    movements, last = [], 0
    for match in _AMOUNT.finditer(text):
        chunk = text[last:match.start()]
        line_start = text.rfind("\n", 0, match.start()) + 1
        last = match.end()
        dates = list(_DATE.finditer(chunk))
        if dates:
            chunk = chunk[dates[-1].start():]  # page header sits above the first row
        when = _date_in(chunk, today)
        lowered = plain(chunk)
        if not when or _HEADER.search(lowered):
            continue  # running balance, statement header, card limit
        negative = bool(match[1])
        direction = ("out" if negative else "in") if account_mode else ("in" if negative else "out")
        amount = int(match[2].replace(".", "")) * 100 + int(match[3])
        if not amount:
            continue
        after = plain(text[line_start:match.end() + 40])
        party = _merchant(chunk)
        if not party:
            continue
        kind = _kind(lowered, direction)
        if not account_mode and direction == "in" and kind == "diger":
            kind = "iade"  # money back on a card: "APPLE.COM/BILL - 4.593,32 TL"
        description = " ".join(chunk.split())[:300]
        # transfer description "Sinem Ağca, Bireysel Ödeme, EFT …": the person is before the comma
        if kind in ("transfer", INTERNAL) and "," in party:
            party = party.split(",")[0].strip()
        note = ""
        if re.search(r"taksi[td]", after + lowered):  # "taksit", "2/3 taksidi"; not "taksi"
            kind, note = "taksit", "Taksitli işlem; bu ayki taksit tutarı ayrıca görünmüyor."
        elif "bekleyen" in lowered:
            note = "Bekleyen provizyon"
        foreign = re.search(r"\((\d{1,6})[.,](\d{2})\s*(USD|EUR)\)", chunk)
        movements.append({"date": when, "direction": direction, "kind": kind, "party": party,
                          "description": description, "amount": amount, "account": account, "note": note,
                          "foreign_currency": foreign[3] if foreign else None,
                          "foreign_cents": int(foreign[1]) * 100 + int(foreign[2]) if foreign else None})
    # Two identical rows on one day ("Derya Erduğan 1.400 + 1.400") are two movements;
    # the same row on two overlapping screenshots is one. A per-file ordinal decides.
    seen = {}
    for item in movements:
        identity = (item["date"], item["direction"], item["amount"], key_of(item["party"]))
        seen[identity] = seen.get(identity, 0) + 1
        item["ordinal"] = seen[identity]
    return movements


def _auto(item):
    """Category and receipt need before any owner rule is applied."""
    import expense_insights
    kind, direction = item["kind"], item["direction"]
    if kind == INTERNAL:
        return INTERNAL, "not_needed"
    if direction == "in":
        if kind == "iade":
            return "iade", "not_needed"
        return ("gelir" if re.search(r"ucret|maas", plain(item["description"])) else ""), "not_needed"
    if kind == "banka":
        return "banka", "not_needed"
    if kind == "atm":
        return "nakit", "not_needed"
    if kind == "transfer":
        return "", "not_needed"  # a person: the owner is asked what it was for
    category = expense_insights.categorize(item["party"], item["description"])
    return ("" if category == "diger" else category), ("ignored" if kind == "taksit" else "needed")


# ------------------------------------------------------------------ kayıt
def _read_file(data, mime):
    import expense_vault
    if mime == "application/pdf":
        import fitz
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ExpenseError("PDF şifreli. Bankanın şifresini açıp kaydettiğiniz kopyayı veya "
                                   "ekran görüntüsünü yükleyin.")
            text = "\n".join(page.get_text() for page in pdf)
            if len(text.strip()) >= 80:
                return text
            image = pdf[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
    else:
        image = data
    return expense_vault._paddle(image) or expense_vault._tesseract(image, 2400)


def upload(owner, data, filename):
    import expense_vault
    if not isinstance(data, bytes) or not 0 < len(data) <= expense_vault.MAX_BYTES:
        raise ExpenseError("Dosya 12 MB veya daha küçük olmalı.")
    filename = _text(filename, "Dosya adı", 160) or "ekstre"
    data = expense_vault._heic_to_jpeg(data)
    mime = expense_vault._mime(data)
    digest = hashlib.sha256(data).hexdigest()
    movements = parse_statement(_read_file(data, mime))
    if not movements:
        raise ExpenseError("Bu dosyada para hareketi okunamadı. Hesap dökümü, kart ekstresi PDF'i veya "
                           "hareket listesinin ekran görüntüsünü yükleyin.")
    added = 0
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_money_upload (owner,sha256,filename,mime_type,content,line_count)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (owner, digest, filename, mime, data, len(movements)))
        for item in movements:
            category, receipt = _auto(item)
            cur.execute("""INSERT INTO core.jarvis_money_movement
                (movement_id,owner,source_sha256,account,tx_date,direction,kind,party,party_key,
                 description,amount_cents,foreign_currency,foreign_cents,ordinal,category,receipt,note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING movement_id""",
                (uuid.uuid4().hex, owner, digest, item["account"], item["date"], item["direction"], item["kind"],
                 item["party"], key_of(item["party"]), item["description"], item["amount"],
                 item["foreign_currency"], item["foreign_cents"], item["ordinal"], category, receipt, item["note"]))
            added += cur.fetchone() is not None
    apply_rules(owner)
    matched = match_receipts(owner)
    return {"read": len(movements), "added": added, "already": len(movements) - added, "matched": matched,
            "account": movements[0]["account"]}


def sync_gmail_statements(owner, *, days=120):
    """Banks mail the monthly statement ("10.10.2026 tarihli Enpara Kredi Kartı
    ekstreniz"); read those PDFs so the owner never uploads them by hand."""
    import base64
    import urllib.parse

    import expense_vault
    import google_workspace
    token_info = google_workspace._read(google_workspace._path(owner), {})
    if "https://www.googleapis.com/auth/gmail.readonly" not in token_info.get("scope", []):
        raise ExpenseError("Gmail okuma izni gerekli.")
    token = google_workspace._access_token(owner)
    after = (datetime.now(ZONE).date() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = (f'after:{after} has:attachment filename:pdf '
             '{ekstre ekstreniz "hesap hareketleri" "hesap özeti" "hesap hareketleriniz"} -in:spam -in:trash')
    listing = expense_vault._gmail_json("messages?" + urllib.parse.urlencode({"q": query, "maxResults": "50"}), token)
    result = {"files": 0, "added": 0, "skipped": []}
    for item in listing.get("messages", []):
        message = expense_vault._gmail_json("messages/" + urllib.parse.quote(item["id"]) + "?format=full", token)
        stack = [message.get("payload") or {}]
        while stack:
            part = stack.pop()
            stack.extend(part.get("parts") or [])
            filename = part.get("filename") or ""
            attachment = (part.get("body") or {}).get("attachmentId")
            if not attachment or not filename.casefold().endswith(".pdf"):
                continue
            if not re.search(r"ekstre|hareket|ozet|özet|statement", plain(filename)):
                continue
            blob = expense_vault._gmail_json("messages/" + urllib.parse.quote(item["id"]) + "/attachments/" +
                                            urllib.parse.quote(attachment), token).get("data") or ""
            data = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
            digest = hashlib.sha256(data).hexdigest()
            with _connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM core.jarvis_money_upload WHERE owner=%s AND sha256=%s", (owner, digest))
                if cur.fetchone():
                    continue
            try:
                found = upload(owner, data, filename)
            except ExpenseError as exc:
                result["skipped"].append(f"{filename}: {exc}"[:200])
                continue
            result["files"] += 1
            result["added"] += found["added"]
    return result


def apply_rules(owner):
    """Owner's answers ("Sinem Ağca = sosyal medya, L'CARLIÉ") override the guess."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_money_movement m SET
            category=CASE WHEN r.category<>'' THEN r.category ELSE m.category END,
            scope=CASE WHEN r.scope<>'' THEN r.scope ELSE m.scope END,
            receipt=CASE WHEN r.category='ic_transfer' OR r.scope='kisisel'
                              OR r.receipt_policy='not_needed' THEN 'not_needed'
                         WHEN m.receipt='not_needed' AND m.kind IN ('kart','fatura') THEN 'needed'
                         ELSE m.receipt END,
            updated_at=clock_timestamp()
            FROM core.jarvis_money_rule r
            WHERE r.owner=m.owner AND r.party_key=m.party_key AND m.owner=%s AND NOT m.manual
            AND m.receipt<>'matched'
            AND (m.category IS DISTINCT FROM CASE WHEN r.category<>'' THEN r.category ELSE m.category END
                 OR m.scope IS DISTINCT FROM CASE WHEN r.scope<>'' THEN r.scope ELSE m.scope END
                 OR (r.receipt_policy='not_needed' AND m.receipt='needed'))""", (owner,))
        return cur.rowcount


def match_receipts(owner):
    """Money out that needs a receipt + document of the same amount within ±3 days.
    A foreign charge ("ANTHROPIC (20,00 USD) 994,10 TL") matches the dollar invoice."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT movement_id,tx_date,amount_cents,foreign_currency,foreign_cents
            FROM core.jarvis_money_movement WHERE owner=%s AND receipt='needed' AND direction='out'
            ORDER BY tx_date""", (owner,))
        rows = cur.fetchall()
        matched = 0
        for row in rows:
            currency, amount = ((row["foreign_currency"], row["foreign_cents"]) if row["foreign_currency"]
                                else ("TRY", row["amount_cents"]))
            cur.execute("""SELECT d.document_id FROM core.jarvis_expense_document d
                WHERE d.owner=%s AND d.status<>'excluded' AND d.currency=%s AND d.gross_cents=%s
                AND d.document_date BETWEEN %s AND %s
                AND NOT EXISTS (SELECT 1 FROM core.jarvis_money_movement m
                                WHERE m.owner=d.owner AND m.document_id=d.document_id)
                ORDER BY abs(d.document_date - %s::date), d.kind='invoice' DESC LIMIT 1""",
                (owner, currency, amount, row["tx_date"] - timedelta(days=3), row["tx_date"] + timedelta(days=3),
                 row["tx_date"]))
            document = cur.fetchone()
            if document:
                cur.execute("""UPDATE core.jarvis_money_movement SET receipt='matched',document_id=%s,
                    updated_at=clock_timestamp() WHERE owner=%s AND movement_id=%s AND receipt='needed'""",
                    (document["document_id"], owner, row["movement_id"]))
                matched += 1
    return matched


# --------------------------------------------------------- sınıflandırma
def classify(owner, movement_id, body):
    """Answer to "bu ne için?". remember=True turns it into a rule for that person/shop."""
    movement_id = _id(movement_id)
    category = body.get("category") or ""
    scope = body.get("scope") or ""
    if category and category not in CATEGORIES:
        raise ExpenseError("Kategori geçersiz.")
    if scope and scope not in SCOPES:
        raise ExpenseError("Hesap başlığı geçersiz.")
    note = _text(body.get("note"), "Not", 300)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT party,party_key,kind FROM core.jarvis_money_movement
            WHERE owner=%s AND movement_id=%s""", (owner, movement_id))
        row = cur.fetchone()
        if not row:
            raise ExpenseError("Hareket bulunamadı.")
        receipt_sql = ("CASE WHEN %(category)s='ic_transfer' OR %(scope)s='kisisel' THEN "
                       "CASE WHEN receipt='matched' THEN receipt ELSE 'not_needed' END ELSE receipt END")
        cur.execute(f"""UPDATE core.jarvis_money_movement SET category=%(category)s,scope=%(scope)s,
            note=CASE WHEN %(note)s<>'' THEN %(note)s ELSE note END,receipt={receipt_sql},
            manual=true,updated_at=clock_timestamp() WHERE owner=%(owner)s AND movement_id=%(id)s""",
            {"category": category, "scope": scope, "note": note, "owner": owner, "id": movement_id})
        if body.get("remember"):
            cur.execute("""INSERT INTO core.jarvis_money_rule (owner,party_key,label,category,scope)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (owner,party_key) DO UPDATE SET
                category=EXCLUDED.category,scope=EXCLUDED.scope,updated_at=clock_timestamp()""",
                (owner, row["party_key"], row["party"][:80], category, scope))
    changed = apply_rules(owner) if body.get("remember") else 0
    return {"id": movement_id, "applied_to": changed}


def set_rule(owner, body):
    """Agreement with a person: "Sinem Ağca, sosyal medya, L'CARLIÉ, aylık 12.000 TL, Eylül'den"."""
    party = _text(body.get("party"), "Kişi / firma", 80)
    if not party:
        raise ExpenseError("Kişi veya firma adı gerekli.")
    category, scope = body.get("category") or "", body.get("scope") or ""
    if category and category not in CATEGORIES:
        raise ExpenseError("Kategori geçersiz.")
    if scope and scope not in SCOPES:
        raise ExpenseError("Hesap başlığı geçersiz.")
    import expense_vault

    def tl(value, label):
        raw = str(value or "").replace("₺", "").replace("TL", "").strip()
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):  # "12.000" is twelve thousand, not 12,000 kuruş
            raw = raw.replace(".", "")
        return expense_vault._money(raw, label)
    monthly = tl(body.get("monthly"), "Aylık tutar")
    opening = tl(body.get("opening"), "Açılış borcu") if body.get("opening") else 0
    def month(field, label):
        value = body.get(field)
        if not value:
            return None
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(value)):
            raise ExpenseError(f"{label} geçersiz.")
        return date(int(value[:4]), int(value[5:]), 1)
    start, end = month("start_month", "Başlangıç ayı"), month("end_month", "Bitiş ayı")
    if start and end and end < start:
        raise ExpenseError("Bitiş ayı başlangıçtan önce olamaz.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_money_rule
            (owner,party_key,label,category,scope,monthly_cents,start_month,end_month,opening_cents,note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (owner,party_key) DO UPDATE SET
            label=EXCLUDED.label,category=EXCLUDED.category,scope=EXCLUDED.scope,
            monthly_cents=EXCLUDED.monthly_cents,start_month=EXCLUDED.start_month,
            end_month=EXCLUDED.end_month,opening_cents=EXCLUDED.opening_cents,note=EXCLUDED.note,
            updated_at=clock_timestamp()""",
            (owner, key_of(party), party, category, scope, monthly, start, end, opening or 0,
             _text(body.get("note"), "Not", 300)))
    return {"party": party, "applied_to": apply_rules(owner)}


def set_receipt(owner, movement_id, action, document_id=None, remember=False):
    """remember=True on "fişi gerekmiyor": that shop never asks for a receipt again
    (Netflix, Yemeksepeti, EGO) - the missing-receipt list keeps only business costs."""
    movement_id = _id(movement_id)
    with _connect() as conn, conn.cursor() as cur:
        if action == "ignore":
            cur.execute("""UPDATE core.jarvis_money_movement SET receipt='not_needed',document_id=NULL,
                updated_at=clock_timestamp() WHERE owner=%s AND movement_id=%s
                RETURNING movement_id,party,party_key""", (owner, movement_id))
            row = cur.fetchone()
            if not row:
                raise ExpenseError("Hareket bulunamadı.")
            if remember:
                cur.execute("""INSERT INTO core.jarvis_money_rule (owner,party_key,label,receipt_policy)
                    VALUES (%s,%s,%s,'not_needed') ON CONFLICT (owner,party_key) DO UPDATE SET
                    receipt_policy='not_needed',updated_at=clock_timestamp()""",
                    (owner, row["party_key"], row["party"][:80]))
        elif action == "reopen":
            cur.execute("""UPDATE core.jarvis_money_movement SET receipt='needed',document_id=NULL,
                updated_at=clock_timestamp() WHERE owner=%s AND movement_id=%s RETURNING movement_id""",
                (owner, movement_id))
            if not cur.fetchone():
                raise ExpenseError("Hareket bulunamadı.")
        elif action == "match":
            document_id = _id(document_id)
            cur.execute("SELECT 1 FROM core.jarvis_expense_document WHERE owner=%s AND document_id=%s",
                        (owner, document_id))
            if not cur.fetchone():
                raise ExpenseError("Belge bulunamadı.")
            cur.execute("""UPDATE core.jarvis_money_movement SET receipt='matched',document_id=%s,
                updated_at=clock_timestamp() WHERE owner=%s AND movement_id=%s RETURNING movement_id""",
                (document_id, owner, movement_id))
            if not cur.fetchone():
                raise ExpenseError("Hareket bulunamadı.")
        else:
            raise ExpenseError("İşlem geçersiz.")
    changed = apply_rules(owner) if action == "ignore" and remember else 0
    return {"id": movement_id, "action": action, "applied_to": changed}


# ----------------------------------------------------------------- rapor
def period_range(view, day):
    if view == "day":
        return day, day + timedelta(days=1)
    if view == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    if view == "month":
        start = day.replace(day=1)
        return start, (start + timedelta(days=32)).replace(day=1)
    raise ExpenseError("Görünüm gün, hafta veya ay olmalı.")


def _parse_day(value):
    try:
        return date.fromisoformat(str(value)) if value else datetime.now(ZONE).date()
    except ValueError as exc:
        raise ExpenseError("Tarih geçersiz.") from exc


def _bucket(rows, key, labels):
    out = {}
    for row in rows:
        name = row[key] or ""
        item = out.setdefault(name, {"key": name, "label": labels.get(name, name or "Belirlenmedi"),
                                     "total": 0, "count": 0})
        item["total"] += row["amount_cents"]
        item["count"] += 1
    return sorted(out.values(), key=lambda item: -item["total"])


def report(owner, view="month", day=None, scope=""):
    day = _parse_day(day)
    start, end = period_range(view, day)
    if scope and scope not in SCOPES and scope != "none":
        raise ExpenseError("Hesap başlığı geçersiz.")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT movement_id AS id,account,tx_date,direction,kind,party,amount_cents,
            foreign_currency,foreign_cents,category,scope,receipt,document_id,note
            FROM core.jarvis_money_movement WHERE owner=%s AND tx_date >= %s AND tx_date < %s
            ORDER BY tx_date DESC, amount_cents DESC""", (owner, start, end))
        rows = [dict(row, tx_date=row["tx_date"].isoformat()) for row in cur.fetchall()]
        cur.execute("""SELECT count(*) AS n, coalesce(sum(amount_cents),0) AS total
            FROM core.jarvis_money_movement WHERE owner=%s AND category='' AND direction='out'""", (owner,))
        unknown = cur.fetchone()
    if scope:
        rows = [row for row in rows if (row["scope"] or "none") == scope]
    counted = [row for row in rows if row["category"] != INTERNAL]
    out = [row for row in counted if row["direction"] == "out"]
    incoming = [row for row in counted if row["direction"] == "in"]
    series = {}
    for row in out:
        bucket = row["tx_date"] if view != "day" else row["tx_date"]
        series[bucket] = series.get(bucket, 0) + row["amount_cents"]
    parties = _bucket(out, "party", {})[:15]
    return {
        "view": view, "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "out_total": sum(row["amount_cents"] for row in out),
        "in_total": sum(row["amount_cents"] for row in incoming),
        "internal_total": sum(row["amount_cents"] for row in rows if row["category"] == INTERNAL and row["direction"] == "out"),
        "by_category": _bucket(out, "category", CATEGORIES),
        "by_scope": _bucket(out, "scope", SCOPES),
        "in_by_category": _bucket(incoming, "category", CATEGORIES),
        "top_parties": parties,
        "series": [{"date": key, "total": value} for key, value in sorted(series.items())],
        "movements": rows[:400],
        "unknown_all": {"count": unknown["n"], "total": unknown["total"]},
    }


def questions(owner, limit=25):
    """Money out with no known purpose, biggest first; one row per person/shop."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (party_key) movement_id AS id,party,party_key,kind,account,
            tx_date,amount_cents,
            sum(amount_cents) OVER (PARTITION BY party_key) AS party_total,
            count(*) OVER (PARTITION BY party_key) AS party_count
            FROM core.jarvis_money_movement WHERE owner=%s AND direction='out' AND category=''
            ORDER BY party_key, amount_cents DESC""", (owner,))
        rows = [dict(row, tx_date=row["tx_date"].isoformat()) for row in cur.fetchall()]
    return sorted(rows, key=lambda row: -row["party_total"])[:limit]


def agreements(owner, today=None):
    """Monthly agreements: what was due, what was paid (oldest month first), what is owed."""
    today = today or datetime.now(ZONE).date()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT party_key,label,category,scope,monthly_cents,start_month,end_month,
            opening_cents,note FROM core.jarvis_money_rule
            WHERE owner=%s AND monthly_cents IS NOT NULL AND monthly_cents>0 ORDER BY label""", (owner,))
        rules = cur.fetchall()
        result = []
        for rule in rules:
            start = rule["start_month"] or today.replace(day=1)
            cur.execute("""SELECT tx_date,amount_cents FROM core.jarvis_money_movement
                WHERE owner=%s AND party_key=%s AND direction='out' AND tx_date >= %s ORDER BY tx_date""",
                (owner, rule["party_key"], start - timedelta(days=10)))
            payments = cur.fetchall()
            months = []
            cursor = start
            this_month = today.replace(day=1)
            # an ended agreement accrues nothing after its last month (Mina Dilara: no work in October)
            last_month = min(this_month, rule["end_month"]) if rule["end_month"] else this_month
            while cursor <= last_month:
                months.append(cursor)
                cursor = (cursor + timedelta(days=32)).replace(day=1)
            pool = sum(payment["amount_cents"] for payment in payments) - (rule["opening_cents"] or 0)
            rows = []
            for month in months:
                covered = max(0, min(rule["monthly_cents"], pool))
                pool -= covered
                rows.append({"month": month.strftime("%Y-%m"), "due": rule["monthly_cents"], "paid": covered,
                             "open": rule["monthly_cents"] - covered, "current": month == this_month})
            closed = [row for row in rows if not row["current"]]
            result.append({
                "party": rule["label"], "category": rule["category"], "scope": rule["scope"],
                "ended": rule["end_month"].strftime("%Y-%m") if rule["end_month"] else "",
                "monthly": rule["monthly_cents"], "note": rule["note"],
                "paid_total": sum(payment["amount_cents"] for payment in payments),
                "owed_closed_months": sum(row["open"] for row in closed),
                "this_month": next((row for row in rows if row["current"]), None),
                "months": rows, "advance": max(pool, 0),
                "payments": [{"date": payment["tx_date"].isoformat(), "amount": payment["amount_cents"]}
                             for payment in payments],
            })
    return result


def receipt_lines(owner, period):
    """For the documents page: money out that needs (or found) a receipt."""
    start = date(int(period[:4]), int(period[5:]), 1)
    end = (start + timedelta(days=32)).replace(day=1)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT m.movement_id AS id,m.tx_date,m.party AS merchant,m.amount_cents,
            m.receipt AS status,m.note,m.document_id,m.account,d.filename,d.supplier
            FROM core.jarvis_money_movement m LEFT JOIN core.jarvis_expense_document d
            ON d.owner=m.owner AND d.document_id=m.document_id
            WHERE m.owner=%s AND m.direction='out' AND m.kind IN ('kart','fatura','taksit')
            AND m.category<>'ic_transfer' AND m.tx_date >= %s AND m.tx_date < %s
            ORDER BY m.tx_date DESC, m.party""", (owner, start, end))
        rows = [dict(row, tx_date=row["tx_date"].isoformat()) for row in cur.fetchall()]
    counts = {"open": sum(row["status"] == "needed" for row in rows),
              "matched": sum(row["status"] == "matched" for row in rows),
              "ignored": sum(row["status"] in ("not_needed", "ignored") for row in rows)}
    return {"lines": rows, "counts": counts,
            "open_total": sum(row["amount_cents"] for row in rows if row["status"] == "needed")}
