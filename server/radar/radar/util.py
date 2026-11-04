"""Ortak yardımcılar: zaman, Türkçe normalize, sayı ayrıştırma, HTTP."""
import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request

TZ = dt.timezone(dt.timedelta(hours=3))  # Türkiye (UTC+3, yaz saati yok)
UA = "Mozilla/5.0 (compatible; LCarlieRadar/1.0)"


def now():
    return dt.datetime.now(TZ).replace(microsecond=0)


def iso(t):
    return t.isoformat()


def parse_dt(s):
    """ISO tarih/saat ayrıştırır; saat dilimi yoksa Türkiye saati kabul eder."""
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=TZ)
    return t.astimezone(TZ)


def tr_lower(s):
    return (s or "").replace("I", "ı").replace("İ", "i").lower()


def katla(s):
    """Eşleştirme anahtarı: Türkçe küçült, sonra ı/i farkını kaldır.

    Yabancı marka ve ürün adları büyük harfle yazılınca 'ORGANIC' -> 'organıc' oluyor ve
    'organic' anahtarıyla eşleşmiyordu (29.10.2026 ölçüldü: LIPSTICK, KLINIK, ORGANIC kaçıyordu).
    Her iki taraf da bu fonksiyondan geçtiği için Türkçe kelimelerde kayıp yok.
    """
    return tr_lower(s).replace("ı", "i")


def norm(s):
    s = katla(s)
    s = re.sub(r"[^\w\s+]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


_NUM = re.compile(r"\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")


def _parse_num(tok):
    tok = tok.replace(" ", "")
    if "," in tok and "." in tok:          # 1.450,90 (TR)  /  1,450.90 (EN)
        if tok.rfind(",") > tok.rfind("."):
            tok = tok.replace(".", "").replace(",", ".")
        else:
            tok = tok.replace(",", "")
    elif "," in tok:
        tail = tok.split(",")[-1]
        tok = tok.replace(",", "") if len(tail) == 3 else tok.replace(",", ".")
    elif "." in tok:
        parts = tok.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            tok = tok.replace(".", "")
    try:
        return float(tok)
    except ValueError:
        return None


def find_numbers(text):
    out = []
    for m in _NUM.finditer(text or ""):
        v = _parse_num(m.group(0))
        if v is not None:
            out.append(v)
    return out


def number_in_text(value, text, tol=0.01):
    return any(abs(n - float(value)) <= tol for n in find_numbers(text))


def valid_url(u):
    try:
        p = urllib.parse.urlparse(u or "")
    except ValueError:
        return False
    return p.scheme in ("http", "https") and "." in (p.netloc or "")


def html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw or "")
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    lines = [re.sub(r"[ \t\xa0]+", " ", html.unescape(l)).strip() for l in raw.splitlines()]
    return "\n".join(l for l in lines if l)


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def http_post_json(url, payload, headers=None, timeout=30):
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))
