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
    # owner, 02.11.2026: own-name EFTs pay old credit cards at other banks, no new spending
    # there — real money out (those cards are not in the ledger, so nothing is counted twice)
    "kart_borcu": "Eski kart borcu ödemesi",
    # owner, 02.11.2026: some transfers he cannot place; counted as spending, shown apart
    "hatirlanmiyor": "Hatırlamıyorum",
}
IN_CATEGORIES = {
    "gelir": "Maaş / ücret geliri", "aile_gelen": "Aileden gelen", "tahsilat": "Tahsilat / satış",
    "iade": "İade / kampanya", "borc_donus": "Borç geri ödemesi", "diger_gelen": "Diğer gelen",
}
# alt kalem: owner, 02.11.2026 — "ofisin içinde kira, muhasebe ödemesi gibi ödemeler var"
SUBCATEGORIES = {
    "ofis": ["Kira", "Muhasebe", "Aidat", "Kırtasiye", "Temizlik", "Teknik servis", "Mobilya / ekipman"],
    "yemek": ["Restoran", "Paket servis", "Kafe", "İkram / misafir"],
    "market": ["Gıda", "Temizlik", "Ev"],
    "yazilim": ["Sunucu", "Yapay zekâ", "Web sitesi", "Abonelik", "Telefon uygulaması"],
    "reklam": ["Meta", "Google", "Influencer", "Basılı"],
    "sosyal_medya": ["Yönetim", "İçerik üretimi", "Çekim"],
    "personel": ["Maaş", "Günlük çalışan", "Prim", "SGK"],
    "hizmet": ["Muhasebe", "Hukuk", "Tasarım", "Danışmanlık", "Kurye"],
    "faturalar": ["Elektrik", "İnternet", "Telefon", "Su", "Doğalgaz"],
    "ulasim": ["Taksi", "Otopark", "Toplu taşıma", "Uçak", "Araç bakım"],
    "akaryakit": ["Benzin", "Motorin", "LPG"],
    "kargo": ["Kargo", "Kurye", "Nakliye"],
    "aile": ["Hediye", "Ev", "Çocuk"],
    "borc": ["Arkadaş", "Aile", "İş"],
    "kart_borcu": ["Başka banka kredi kartı", "Kredi", "Taksit"],
    "saglik": ["Doktor", "İlaç", "Bakım"],
    "eglence": ["Yemek / gece", "Etkinlik", "Tatil"],
    "kira": ["Ev", "İş yeri"],
    "gelir": ["Maaş", "Ücret", "Prim"],
    "tahsilat": ["Satış", "Müşteri", "Pazaryeri"],
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
            subcategory=CASE WHEN r.subcategory<>'' THEN r.subcategory ELSE m.subcategory END,
            receipt=CASE WHEN r.category='ic_transfer' OR r.scope='kisisel'
                              OR r.receipt_policy='not_needed' THEN 'not_needed'
                         WHEN m.receipt='not_needed' AND m.kind IN ('kart','fatura') THEN 'needed'
                         ELSE m.receipt END,
            updated_at=clock_timestamp()
            FROM core.jarvis_money_rule r
            WHERE r.owner=m.owner AND r.party_key=m.party_key AND m.owner=%s AND NOT m.manual
            AND (r.direction=m.direction OR r.category='ic_transfer')
            AND m.receipt<>'matched'
            AND (m.category IS DISTINCT FROM CASE WHEN r.category<>'' THEN r.category ELSE m.category END
                 OR m.scope IS DISTINCT FROM CASE WHEN r.scope<>'' THEN r.scope ELSE m.scope END
                 OR (r.subcategory<>'' AND m.subcategory IS DISTINCT FROM r.subcategory)
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
    sub_given = "subcategory" in body
    subcategory = _text(body.get("subcategory"), "Alt kalem", 40) if sub_given else ""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT party,party_key,kind,direction FROM core.jarvis_money_movement
            WHERE owner=%s AND movement_id=%s""", (owner, movement_id))
        row = cur.fetchone()
        if not row:
            raise ExpenseError("Hareket bulunamadı.")
        if category and category not in (INTERNAL,) and (category in IN_CATEGORIES) != (row["direction"] == "in"):
            raise ExpenseError("Gelen paraya gelir kategorisi, giden paraya gider kategorisi seçin.")
        receipt_sql = ("CASE WHEN %(category)s='ic_transfer' OR %(scope)s='kisisel' THEN "
                       "CASE WHEN receipt='matched' THEN receipt ELSE 'not_needed' END ELSE receipt END")
        cur.execute(f"""UPDATE core.jarvis_money_movement SET category=%(category)s,scope=%(scope)s,
            subcategory=CASE WHEN %(sub_given)s THEN %(sub)s ELSE subcategory END,
            note=CASE WHEN %(note)s<>'' THEN %(note)s ELSE note END,receipt={receipt_sql},
            manual=true,updated_at=clock_timestamp() WHERE owner=%(owner)s AND movement_id=%(id)s""",
            {"category": category, "scope": scope, "note": note, "owner": owner, "id": movement_id,
             "sub": subcategory, "sub_given": sub_given})
        if body.get("remember"):
            cur.execute("""INSERT INTO core.jarvis_money_rule (owner,party_key,direction,label,category,scope,subcategory)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (owner,party_key,direction) DO UPDATE SET
                category=EXCLUDED.category,scope=EXCLUDED.scope,
                subcategory=CASE WHEN %s THEN EXCLUDED.subcategory ELSE core.jarvis_money_rule.subcategory END,
                updated_at=clock_timestamp()""",
                (owner, row["party_key"], row["direction"], row["party"][:80], category, scope, subcategory, sub_given))
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
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (owner,party_key,direction) DO UPDATE SET
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
                    VALUES (%s,%s,%s,'not_needed') ON CONFLICT (owner,party_key,direction) DO UPDATE SET
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


def _months_back(day, count):
    first = day.replace(day=1)
    for _ in range(count):
        first = (first - timedelta(days=1)).replace(day=1)
    return first


def _previous_range(view, start):
    if view == "day":
        return start - timedelta(days=1), start
    if view == "week":
        return start - timedelta(days=7), start
    return (start - timedelta(days=1)).replace(day=1), start


def _median(values):
    ordered = sorted(values)
    if not ordered:
        return 0
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _money_text(cents):
    return f"{cents / 100:,.0f} ₺".replace(",", ".")


def _party(row):
    return row.get("party_key") or key_of(row["party"])


def build_report(rows, view, day, scope="", today=None, account=""):
    """Pure report over movement dicts (tx_date: date); report() feeds it from the DB.

    Beyond the period's totals it answers what finance apps answer first (Monarch,
    Copilot, Simplifi): versus the previous period, spending pace against the last
    period, six-month cash flow, unusual payments, recurring payments, month-end forecast.
    """
    today = today or datetime.now(ZONE).date()
    start, end = period_range(view, day)
    prev_start, prev_end = _previous_range(view, start)
    accounts = {}
    for row in rows:
        if start <= row["tx_date"] < end and row["category"] != INTERNAL and row["direction"] == "out":
            accounts[row["account"]] = accounts.get(row["account"], 0) + row["amount_cents"]
        else:
            accounts.setdefault(row["account"], 0)
    if account:
        rows = [row for row in rows if row["account"] == account]
    if scope:
        rows = [row for row in rows if (row["scope"] or "none") == scope]
    counted = [row for row in rows if row["category"] != INTERNAL]
    spend = [row for row in counted if row["direction"] == "out"]
    current = [row for row in rows if start <= row["tx_date"] < end]
    out = [row for row in spend if start <= row["tx_date"] < end]
    incoming = [row for row in counted if row["direction"] == "in" and start <= row["tx_date"] < end]
    prev_out = [row for row in spend if prev_start <= row["tx_date"] < prev_end]
    prev_in = [row for row in counted if row["direction"] == "in" and prev_start <= row["tx_date"] < prev_end]
    out_total = sum(row["amount_cents"] for row in out)
    in_total = sum(row["amount_cents"] for row in incoming)
    prev_out_total = sum(row["amount_cents"] for row in prev_out)
    prev_in_total = sum(row["amount_cents"] for row in prev_in)

    prev_by_category = {}
    for row in prev_out:
        prev_by_category[row["category"]] = prev_by_category.get(row["category"], 0) + row["amount_cents"]
    by_category = _bucket(out, "category", CATEGORIES)
    for item in by_category:
        item["previous"] = prev_by_category.get(item["key"], 0)

    # pace: cumulative spend by day of the period, this period against the previous one
    length = (end - start).days
    daily = [0] * length
    for row in out:
        daily[(row["tx_date"] - start).days] += row["amount_cents"]
    prev_daily = [0] * (prev_end - prev_start).days
    for row in prev_out:
        prev_daily[(row["tx_date"] - prev_start).days] += row["amount_cents"]

    def cumulative(values):
        total, result = 0, []
        for value in values:
            total += value
            result.append(total)
        return result

    elapsed = length if today >= end else max(0, (today - start).days + 1)
    forecast = round(out_total / elapsed * length) if view == "month" and today < end and elapsed >= 3 else None
    same_point_prev = sum(prev_daily[:elapsed]) if elapsed < length else prev_out_total

    # six-month cash flow and category mix, ending at the period's month
    month0 = _months_back(start, 5)
    months, cursor = [], month0
    while cursor <= start.replace(day=1):
        months.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    trend_end = (months[-1] + timedelta(days=32)).replace(day=1)
    trend_rows = [row for row in counted if month0 <= row["tx_date"] < trend_end]
    category_totals = {}
    for row in trend_rows:
        if row["direction"] == "out":
            category_totals[row["category"]] = category_totals.get(row["category"], 0) + row["amount_cents"]
    top_categories = [key for key, _ in sorted(category_totals.items(), key=lambda kv: -kv[1])[:5]]
    trend = []
    for month in months:
        nxt = (month + timedelta(days=32)).replace(day=1)
        in_month = [row for row in trend_rows if month <= row["tx_date"] < nxt]
        mix = dict.fromkeys(top_categories, 0)
        other = 0
        every = {}
        for row in in_month:
            if row["direction"] != "out":
                continue
            every[row["category"]] = every.get(row["category"], 0) + row["amount_cents"]
            if row["category"] in mix:
                mix[row["category"]] += row["amount_cents"]
            else:
                other += row["amount_cents"]
        scopes = dict.fromkeys(("lemos", "moy", "lcarlie", "kisisel", "none"), 0)
        for row in in_month:
            if row["direction"] == "out":
                scopes[row["scope"] or "none"] += row["amount_cents"]
        trend.append({"month": month.strftime("%Y-%m"), "scopes": scopes, "all": every,
                      "out": sum(r["amount_cents"] for r in in_month if r["direction"] == "out"),
                      "in": sum(r["amount_cents"] for r in in_month if r["direction"] == "in"),
                      "mix": [{"key": key, "total": mix[key]} for key in top_categories] + [{"key": "__other", "total": other}]})

    # weekday habit over the 90 days before the period end
    weekday = [0] * 7
    for row in spend:
        if end - timedelta(days=90) <= row["tx_date"] < end:
            weekday[row["tx_date"].weekday()] += row["amount_cents"]

    # recurring: same person/shop in 2+ months, every amount within ±35% of their median
    window = _months_back(end - timedelta(days=1), 5)
    pool = {}
    for row in spend:
        if window <= row["tx_date"] < end:
            pool.setdefault(_party(row), []).append(row)
    recurring = []
    for items in pool.values():
        months_seen = {row["tx_date"].strftime("%Y-%m") for row in items}
        median = _median([row["amount_cents"] for row in items])
        if len(months_seen) < 2 or not all(abs(row["amount_cents"] - median) <= 0.35 * median for row in items):
            continue
        last = max(items, key=lambda row: row["tx_date"])
        recurring.append({"party": last["party"], "category": last["category"], "scope": last["scope"],
                          "months": len(months_seen), "typical": round(median), "last_date": last["tx_date"].isoformat(),
                          "monthly_estimate": round(sum(row["amount_cents"] for row in items) / len(months_seen))})
    recurring.sort(key=lambda item: -item["monthly_estimate"])

    # unusual: far above what this person/shop or category usually costs (prior 120 days)
    history = [row for row in spend if start - timedelta(days=120) <= row["tx_date"] < start]
    unusual = []
    for row in sorted(out, key=lambda r: -r["amount_cents"]):
        party_hist = [r["amount_cents"] for r in history if _party(r) == _party(row)]
        cat_hist = [r["amount_cents"] for r in history if row["category"] and r["category"] == row["category"]]
        reason = ""
        if len(party_hist) >= 2 and row["amount_cents"] > 2.5 * _median(party_hist):
            reason = f"bu kişi/firma için olağan tutar {_money_text(_median(party_hist))}"
        elif len(cat_hist) >= 4 and row["amount_cents"] >= 100000 and row["amount_cents"] > 4 * _median(cat_hist):
            reason = f"{CATEGORIES.get(row['category'], row['category'])} için olağan tutar {_money_text(_median(cat_hist))}"
        if reason:
            unusual.append({"id": row["id"], "party": row["party"], "date": row["tx_date"].isoformat(),
                            "amount": row["amount_cents"], "reason": reason})
        if len(unusual) == 4:
            break

    insights = []
    versus = {"month": "geçen aya", "week": "geçen haftaya", "day": "önceki güne"}[view]
    if prev_out_total and out_total:
        if view == "month" and elapsed < length and same_point_prev:
            change = (out_total - same_point_prev) / same_point_prev * 100
            insights.append({"tone": "warn" if change > 10 else "good" if change < -10 else "info",
                             "title": f"Ayın ilk {elapsed} gününde {versus} göre %{abs(change):.0f} {'fazla' if change > 0 else 'az'}",
                             "text": f"Bu ay {_money_text(out_total)}; geçen ay aynı noktada {_money_text(same_point_prev)}."})
        elif not (view == "month" and elapsed < length):
            change = (out_total - prev_out_total) / prev_out_total * 100
            insights.append({"tone": "warn" if change > 10 else "good" if change < -10 else "info",
                             "title": f"Harcama {versus} göre %{abs(change):.0f} {'arttı' if change > 0 else 'azaldı'}",
                             "text": f"{_money_text(out_total)}; önceki dönem {_money_text(prev_out_total)}."})
    grew = [item for item in by_category if item["key"] and item["key"] != "hatirlanmiyor" and item["total"] > item["previous"]]
    if grew and prev_out_total:
        top = max(grew, key=lambda item: item["total"] - item["previous"])
        insights.append({"tone": "warn", "title": f"En çok büyüyen kalem: {top['label']}",
                         "text": (f"{_money_text(top['previous'])} → {_money_text(top['total'])} "
                                  f"(+{_money_text(top['total'] - top['previous'])})." if top["previous"] else
                                  f"Önceki dönemde yoktu; bu dönem {_money_text(top['total'])}.")})
    if forecast:
        insights.append({"tone": "info", "title": f"Bu tempoyla ay sonu yaklaşık {_money_text(forecast)}",
                         "text": f"{elapsed} günde {_money_text(out_total)}; günlük ortalama {_money_text(out_total / elapsed)}."})
    if in_total:
        rate = (in_total - out_total) / in_total * 100
        insights.append({"tone": "good" if rate >= 20 else "warn" if rate < 0 else "info",
                         "title": f"Birikim oranı %{rate:.0f}" if rate >= 0 else f"Gelenin %{-rate:.0f} fazlası harcandı",
                         "text": f"Gelen {_money_text(in_total)}, harcanan {_money_text(out_total)}; kendi hesaplar arası hariç."})
    unclear = sum(r["amount_cents"] for r in out if r["category"] in ("", "hatirlanmiyor"))
    if out_total and unclear / out_total >= 0.15:
        insights.append({"tone": "warn", "title": f"Harcamanın %{unclear * 100 / out_total:.0f} kadarı belirsiz",
                         "text": f"{_money_text(unclear)} ne için olduğu bilinmiyor ya da hatırlanmıyor."})
    if unusual:
        first = unusual[0]
        insights.append({"tone": "warn", "title": f"Olağandışı ödeme: {first['party']}",
                         "text": f"{_money_text(first['amount'])}; {first['reason']}."})

    movements = sorted(current, key=lambda r: (r["tx_date"], r["amount_cents"]), reverse=True)
    review = _review(view, start, out, incoming, out_total, in_total, prev_out_total, by_category, recurring,
                     unusual, forecast, elapsed, length)
    return {
        "review": review, "account": account,
        "accounts": [{"name": name, "out": total} for name, total in sorted(accounts.items(), key=lambda kv: -kv[1])],
        "view": view, "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "prev_start": prev_start.isoformat(), "prev_end": (prev_end - timedelta(days=1)).isoformat(),
        "out_total": out_total, "in_total": in_total, "prev_out_total": prev_out_total, "prev_in_total": prev_in_total,
        "same_point_prev": same_point_prev, "elapsed_days": elapsed, "length_days": length, "forecast": forecast,
        "active_days": sum(1 for value in daily if value),
        "internal_total": sum(r["amount_cents"] for r in current if r["category"] == INTERNAL and r["direction"] == "out"),
        "by_category": by_category,
        "by_scope": _bucket(out, "scope", SCOPES),
        "in_by_category": _bucket(incoming, "category", CATEGORIES),
        "top_parties": _bucket(out, "party", {})[:12],
        "series": [{"date": (start + timedelta(days=i)).isoformat(), "total": value} for i, value in enumerate(daily) if value],
        "pace": {"current": cumulative(daily)[:elapsed], "previous": cumulative(prev_daily)},
        "trend": trend,
        "trend_categories": [{"key": key, "label": CATEGORIES.get(key, key or "Belirlenmedi")} for key in top_categories],
        "weekday": weekday, "recurring": recurring[:12], "unusual": unusual, "insights": insights[:6],
        "largest": [{"id": r["id"], "party": r["party"], "date": r["tx_date"].isoformat(), "amount": r["amount_cents"],
                     "category": r["category"]} for r in sorted(out, key=lambda r: -r["amount_cents"])[:5]],
        "movements": [dict(r, tx_date=r["tx_date"].isoformat()) for r in movements[:500]],
    }


def _review(view, start, out, incoming, out_total, in_total, prev_out_total, by_category, recurring, unusual,
            forecast, elapsed, length):
    """The period in plain Turkish, built only from these numbers (nothing leaves the server)."""
    if not out and not incoming:
        return []
    name = {"month": start.strftime("%Y-%m"), "week": "bu hafta", "day": "bu gün"}[view]
    if view == "month":
        months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
                  "Kasım", "Aralık"]
        name = f"{months[start.month - 1]} {start.year}"
    sentences = []
    known = [item for item in by_category if item["key"] and item["key"] not in ("hatirlanmiyor", INTERNAL)]
    lead = f"{name} döneminde {_money_text(out_total)} harcandı"
    if prev_out_total and not (view == "month" and elapsed < length):
        change = (out_total - prev_out_total) / prev_out_total * 100
        lead += f"; bu, önceki döneme göre %{abs(change):.0f} {'daha fazla' if change > 0 else 'daha az'}"
    sentences.append(lead + ".")
    if known:
        top = known[:3]
        parts = [f"{item['label'].split(' /')[0].lower()} {_money_text(item['total'])}" for item in top]
        share = sum(item["total"] for item in top) * 100 / out_total if out_total else 0
        sentences.append(f"En büyük kalemler {', '.join(parts)}; üçü birlikte harcamanın %{share:.0f} kadarı.")
    moved = [item for item in known if item["previous"] and abs(item["total"] - item["previous"]) >= 50000]
    if moved:
        down = min(moved, key=lambda item: item["total"] - item["previous"])
        up = max(moved, key=lambda item: item["total"] - item["previous"])
        if up["total"] > up["previous"]:
            sentences.append(f"{up['label'].split(' /')[0]} {_money_text(up['total'] - up['previous'])} arttı.")
        if down["total"] < down["previous"]:
            sentences.append(f"{down['label'].split(' /')[0]} ise {_money_text(down['previous'] - down['total'])} azaldı.")
    if in_total:
        rate = (in_total - out_total) / in_total * 100
        sentences.append(f"Gelen {_money_text(in_total)}; " +
                         (f"gelirin %{rate:.0f} kadarı kenarda kaldı." if rate >= 0 else
                          f"harcama geliri {_money_text(out_total - in_total)} aştı."))
    if recurring:
        sentences.append(f"Düzenli ödemeler ayda yaklaşık {_money_text(sum(r['monthly_estimate'] for r in recurring))} tutuyor.")
    if unusual:
        sentences.append(f"Dikkat: {unusual[0]['party']} ödemesi ({_money_text(unusual[0]['amount'])}) olağanın çok üstünde.")
    if forecast:
        sentences.append(f"Bu tempoyla ay {_money_text(forecast)} civarında kapanır.")
    return sentences


# ---------------------------------------------------------------- bütçe
def budgets(owner):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT category, monthly_cents FROM core.jarvis_money_budget WHERE owner=%s", (owner,))
        return {row["category"]: row["monthly_cents"] for row in cur.fetchall()}


def set_budget(owner, category, monthly):
    if category not in OUT_CATEGORIES:
        raise ExpenseError("Kategori geçersiz.")
    import expense_vault
    raw = str(monthly or "").replace("₺", "").replace("TL", "").strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    cents = expense_vault._money(raw, "Bütçe") if raw else None
    with _connect() as conn, conn.cursor() as cur:
        if not cents:
            cur.execute("DELETE FROM core.jarvis_money_budget WHERE owner=%s AND category=%s", (owner, category))
            return {"category": category, "deleted": True}
        cur.execute("""INSERT INTO core.jarvis_money_budget (owner,category,monthly_cents) VALUES (%s,%s,%s)
            ON CONFLICT (owner,category) DO UPDATE SET monthly_cents=EXCLUDED.monthly_cents,updated_at=clock_timestamp()""",
            (owner, category, cents))
    return {"category": category, "monthly": cents}


def budget_status(rows, limits, day, today=None):
    """Spent this calendar month per budgeted category, against where you should be today."""
    today = today or datetime.now(ZONE).date()
    start, end = period_range("month", day)
    length = (end - start).days
    elapsed = length if today >= end else max(0, (today - start).days + 1) if today >= start else 0
    spent = {}
    for row in rows:
        if row["direction"] == "out" and row["category"] in limits and start <= row["tx_date"] < end:
            spent[row["category"]] = spent.get(row["category"], 0) + row["amount_cents"]
    result = []
    for category, limit in limits.items():
        used = spent.get(category, 0)
        result.append({"category": category, "label": CATEGORIES.get(category, category), "limit": limit, "spent": used,
                       "pct": round(used * 100 / limit), "expected_pct": round(elapsed * 100 / length),
                       "left": limit - used,
                       "state": "over" if used > limit else "warn" if used >= 0.8 * limit or
                       (elapsed and used / limit > elapsed / length + 0.15) else "ok"})
    return sorted(result, key=lambda item: -item["pct"])


def budget_alerts(owner, today=None):
    """80% and 100% crossings, once per category per month."""
    import expense_insights
    today = today or datetime.now(ZONE).date()
    limits = budgets(owner)
    if not limits:
        return []
    start, end = period_range("month", today)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT tx_date,direction,category,amount_cents FROM core.jarvis_money_movement
            WHERE owner=%s AND tx_date >= %s AND tx_date < %s""", (owner, start, end))
        rows = cur.fetchall()
    alerts = []
    for item in budget_status(rows, limits, today, today):
        level = 100 if item["spent"] > item["limit"] else 80 if item["spent"] >= 0.8 * item["limit"] else 0
        if not level or not expense_insights._claim_notice(owner, f"butce:{item['category']}:{start:%Y-%m}:{level}"):
            continue
        alerts.append({"title": f"{item['label']} bütçesi %{item['pct']}",
                       "body": (f"{_money_text(item['spent'])} / {_money_text(item['limit'])}; "
                                + ("bütçe aşıldı." if level == 100 else f"kalan {_money_text(item['left'])}."))})
    return alerts


# ----------------------------------------------------------- kategori detayı
def category_detail_from(rows, key, day, scope="", today=None, account="", month=None):
    """Everything behind one slice: 6-month trend, sub-items, payees, editable movements.

    Works for spending and income categories (owner: "borç verme kısmına tıkladığımda
    neler olduğunu görebilmek istiyorum"); `month` opens a past bar of the 6-month chart.
    """
    today = today or datetime.now(ZONE).date()
    anchor = date(int(month[:4]), int(month[5:7]), 1) if month else day
    start, end = period_range("month", anchor)
    if account:
        rows = [row for row in rows if row["account"] == account]
    if scope:
        rows = [row for row in rows if (row["scope"] or "none") == scope]
    wanted = "" if key == "__none" else key
    direction = "in" if wanted in IN_CATEGORIES else "out"
    picked = [row for row in rows if (row["category"] or "") == wanted and
              (row["direction"] == direction or wanted == INTERNAL)]
    months, cursor = [], _months_back(start, 5)
    while cursor <= start:
        months.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    trend = []
    for item in months:
        nxt = (item + timedelta(days=32)).replace(day=1)
        inside = [row for row in picked if item <= row["tx_date"] < nxt]
        trend.append({"month": item.strftime("%Y-%m"), "total": sum(r["amount_cents"] for r in inside), "count": len(inside)})
    current = [row for row in picked if start <= row["tx_date"] < end]
    window = [row for row in picked if months[0] <= row["tx_date"] < end]
    totals = [item["total"] for item in trend[:-1] if item["total"]]
    subs = {}
    for row in current:
        name = row.get("subcategory") or ""
        entry = subs.setdefault(name, {"key": name, "label": name or "Alt kalem seçilmedi", "total": 0, "count": 0})
        entry["total"] += row["amount_cents"]
        entry["count"] += 1
    return {
        "key": key, "label": CATEGORIES.get(wanted, "Belirlenmedi"), "month": start.strftime("%Y-%m"),
        "direction": direction, "total": sum(r["amount_cents"] for r in current), "count": len(current),
        "average_ticket": round(sum(r["amount_cents"] for r in window) / len(window)) if window else 0,
        "monthly_average": round(sum(totals) / len(totals)) if totals else 0,
        "trend": trend, "suggestions": SUBCATEGORIES.get(wanted, []),
        "subcategories": sorted(subs.values(), key=lambda item: -item["total"]),
        "parties": _bucket(current or window, "party", {})[:8],
        "movements": [dict(r, tx_date=r["tx_date"].isoformat()) for r in
                      sorted(current, key=lambda r: (r["tx_date"], r["amount_cents"]), reverse=True)[:200]],
    }


_MOVEMENT_COLUMNS = """movement_id AS id,account,tx_date,direction,kind,party,party_key,amount_cents,
            foreign_currency,foreign_cents,category,subcategory,scope,receipt,document_id,note"""


def category_detail(owner, key, day=None, scope="", account="", month=""):
    if key != "__none" and key not in CATEGORIES:
        raise ExpenseError("Kategori geçersiz.")
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ExpenseError("Ay geçersiz.")
    day = _parse_day(day)
    anchor = date(int(month[:4]), int(month[5:7]), 1) if month else day
    start, end = period_range("month", anchor)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT {_MOVEMENT_COLUMNS} FROM core.jarvis_money_movement
            WHERE owner=%s AND tx_date >= %s AND tx_date < %s""", (owner, _months_back(start, 5), end))
        rows = [dict(row) for row in cur.fetchall()]
    return category_detail_from(rows, key, day, scope, account=account, month=month or None)


def report(owner, view="month", day=None, scope="", account=""):
    day = _parse_day(day)
    start, end = period_range(view, day)
    if scope and scope not in SCOPES and scope != "none":
        raise ExpenseError("Hesap başlığı geçersiz.")
    since = min(_months_back(start, 5), _previous_range(view, start)[0], end - timedelta(days=120))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT {_MOVEMENT_COLUMNS}
            FROM core.jarvis_money_movement WHERE owner=%s AND tx_date >= %s AND tx_date < %s
            ORDER BY tx_date DESC, amount_cents DESC""", (owner, since, end))
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute("""SELECT count(*) AS n, coalesce(sum(amount_cents),0) AS total
            FROM core.jarvis_money_movement WHERE owner=%s AND category=''""", (owner,))
        unknown = cur.fetchone()
    result = build_report(rows, view, day, scope, account=account)
    result["unknown_all"] = {"count": unknown["n"], "total": unknown["total"]}
    result["budgets"] = budget_status(rows, budgets(owner), day)
    return result


def questions(owner, limit=40):
    """Money with no known purpose, biggest first; one row per person/shop and direction.

    Money in was never asked (owner, 02.11.2026: "geçen aylık paranın nereden geldiği neden
    belirlenmedi"), so 670.000 TL of income stayed "Belirlenmedi".
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (party_key, direction) movement_id AS id,party,party_key,kind,account,
            direction,tx_date,amount_cents,
            sum(amount_cents) OVER (PARTITION BY party_key, direction) AS party_total,
            count(*) OVER (PARTITION BY party_key, direction) AS party_count
            FROM core.jarvis_money_movement WHERE owner=%s AND category=''
            ORDER BY party_key, direction, amount_cents DESC""", (owner,))
        rows = [dict(row, tx_date=row["tx_date"].isoformat()) for row in cur.fetchall()]
    return sorted(rows, key=lambda row: -row["party_total"])[:limit]


def agreements(owner, today=None):
    """Monthly agreements: what was due, what was paid (oldest month first), what is owed."""
    today = today or datetime.now(ZONE).date()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT party_key,label,category,scope,monthly_cents,start_month,end_month,
            opening_cents,note FROM core.jarvis_money_rule
            WHERE owner=%s AND direction='out' AND monthly_cents IS NOT NULL AND monthly_cents>0 ORDER BY label""", (owner,))
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
