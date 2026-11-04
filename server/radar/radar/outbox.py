"""Onay kapısı ve gönderim.

- Özer'e giden mesajlar (rapor, uyarı) otomatik onaylıdır.
- Üçüncü kişilere giden her mesaj (lead, müşteri) 'pending_approval' durumunda bekler;
  Özer `radar onayla-mesaj <id>` demeden ASLA gönderilmez.
"""
import json
import os
import smtplib
from email.mime.text import MIMEText

from .db import jdump
from .util import http_post_json, iso, now


def enqueue(conn, channel, recipient, body, subject="", to_owner=False, ref=""):
    status = "approved" if to_owner else "pending_approval"
    cur = conn.execute(
        "INSERT INTO outbox(created_at,channel,recipient,subject,body,needs_approval,status,ref) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (iso(now()), channel, recipient, subject, body, 0 if to_owner else 1, status, ref))
    conn.commit()
    return cur.lastrowid


def to_owner(conn, cfg, body, subject="", ref=""):
    ids = []
    o = cfg["owner"]
    if o.get("telegram_chat_id"):
        ids.append(enqueue(conn, "telegram", str(o["telegram_chat_id"]), body, subject, True, ref))
    if o.get("whatsapp"):
        ids.append(enqueue(conn, "whatsapp", o["whatsapp"], body, subject, True, ref))
    if o.get("email"):
        ids.append(enqueue(conn, "email", o["email"], body, subject, True, ref))
    if not ids:  # numara/e-posta girilmemişse yine de spool'a düşsün
        ids.append(enqueue(conn, "spool", "owner", body, subject, True, ref))
    return ids


def decide(conn, msg_id, approve):
    row = conn.execute("SELECT status FROM outbox WHERE id=?", (msg_id,)).fetchone()
    if not row or row["status"] != "pending_approval":
        return False
    conn.execute("UPDATE outbox SET status=?, decided_at=? WHERE id=?",
                 ("approved" if approve else "rejected", iso(now()), msg_id))
    conn.commit()
    return True


def _smtp(cfg, to, subject, body):
    d = cfg["delivery"]
    host, user, pw = (os.environ.get(d[k]) for k in ("smtp_host_env", "smtp_user_env", "smtp_pass_env"))
    if not (host and user and pw):
        raise RuntimeError("SMTP ayarlı değil")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject or "L'CARLİÉ Radar", user, to
    with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())


TELEGRAM_SINIR = 4000   # Bot API mesaj sınırı 4096 karakter


def _parcala(metin, sinir):
    parcalar, buf = [], ""
    for satir in metin.split("\n"):
        if len(buf) + len(satir) + 1 > sinir and buf:
            parcalar.append(buf)
            buf = ""
        buf = (buf + "\n" + satir) if buf else satir[:sinir]
    return parcalar + ([buf] if buf else [])


def _telegram(post, chat_id, text):
    """https://core.telegram.org/bots/api#sendmessage -- token .env'de TELEGRAM_BOT_TOKEN."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN yok")
    for parca in _parcala(text, TELEGRAM_SINIR):
        r = post(f"https://api.telegram.org/bot{token}/sendMessage",
                 {"chat_id": chat_id, "text": parca, "disable_web_page_preview": True})
        if not r.get("ok"):
            raise RuntimeError(f"telegram: {r.get('description')}")


def _waha(post, numara, text):
    """WAHA (github.com/devlikeapro/waha): POST /api/sendText {session, chatId, text}, başlık X-Api-Key."""
    url = os.environ["WAHA_URL"].rstrip("/") + "/api/sendText"
    chat = "".join(c for c in numara if c.isdigit()) + "@c.us"
    post(url, {"session": os.environ.get("WAHA_SESSION", "default"), "chatId": chat, "text": text},
         {"X-Api-Key": os.environ.get("WAHA_API_KEY", "")})


def _jarvis_whatsapp(conn, cfg, m, calistir=None):
    """Sahibe giden WhatsApp: Jarvis'in kendi whatsapp modülü (deploy/jarvis_whatsapp.py köprüsü).

    Köprü yalnız sahibin numarasına gönderir; 24 saat penceresi açıksa tam metin, değilse onaylı şablon.
    """
    import subprocess
    from . import reports
    kisa = reports.kisa_ozet(conn, cfg) if (m["ref"] or "").startswith("ozet:") else \
        [now().strftime("%d.%m.%Y"), (m["subject"] or "Radar")[:200], " ".join(m["body"].split())[:900], "-", "-"]
    girdi = json.dumps({"telefon": m["recipient"], "metin": m["body"], "kisa": kisa}, ensure_ascii=False)
    komut = os.environ["JARVIS_WHATSAPP_CMD"].split()
    if calistir:
        cikti = calistir(komut, girdi)
    else:
        p = subprocess.run(komut, input=girdi, capture_output=True, text=True, timeout=120)
        cikti = p.stdout
    try:
        sonuc = json.loads((cikti or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"whatsapp köprüsü cevap vermedi: {(cikti or '')[:150]}")
    if not sonuc.get("gonderildi"):
        raise RuntimeError(f"whatsapp ({sonuc.get('yol')}): {sonuc.get('sebep') or 'gönderilmedi'}")
    return sonuc


def send_approved(conn, cfg, post=http_post_json):
    """Yalnızca 'approved' mesajları gönderir. Her mesaj Jarvis için spool klasörüne de yazılır."""
    spool = cfg["delivery"]["spool_dir"]
    os.makedirs(spool, exist_ok=True)
    hook = os.environ.get(cfg["delivery"]["webhook_env"])
    sent, errors = 0, []
    for m in conn.execute("SELECT * FROM outbox WHERE status='approved' ORDER BY id").fetchall():
        rec = {k: m[k] for k in m.keys()}
        if m["channel"] == "email" and not os.environ.get(cfg["delivery"]["smtp_user_env"]):
            conn.execute("UPDATE outbox SET status='skipped' WHERE id=?", (m["id"],))
            errors.append(f"#{m['id']} email: SMTP ayarlı değil, atlandı")
            continue
        try:
            with open(os.path.join(spool, f"{m['id']:06d}.json"), "w", encoding="utf-8") as f:
                f.write(jdump(rec))
            if m["channel"] == "email":
                _smtp(cfg, m["recipient"], m["subject"], m["body"])
            elif m["channel"] == "telegram":
                _telegram(post, m["recipient"], m["body"])
            elif m["channel"] == "whatsapp" and m["needs_approval"] == 0 and os.environ.get("JARVIS_WHATSAPP_CMD"):
                _jarvis_whatsapp(conn, cfg, m)
            elif m["channel"] == "whatsapp" and os.environ.get("WAHA_URL"):
                _waha(post, m["recipient"], m["body"])
            elif m["channel"] == "whatsapp" and hook:
                post(hook, {"to": m["recipient"], "text": m["body"], "outbox_id": m["id"]})
            elif m["channel"] == "whatsapp":
                raise RuntimeError("WhatsApp gönderici yok (WAHA_URL veya JARVIS_WHATSAPP_WEBHOOK)")
            conn.execute("UPDATE outbox SET status='sent', sent_at=? WHERE id=?", (iso(now()), m["id"]))
            sent += 1
        except Exception as e:  # gönderilemeyen mesaj approved kalır, sonraki çalışmada tekrar denenir
            errors.append(f"#{m['id']} {m['channel']}: {e}")
    conn.commit()
    return sent, errors


def pending(conn):
    return conn.execute("SELECT * FROM outbox WHERE status='pending_approval' ORDER BY id").fetchall()


def dump(rows):
    return json.dumps([{k: r[k] for k in r.keys()} for r in rows], ensure_ascii=False, indent=1)
