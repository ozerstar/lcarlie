"""Daily Gmail intake and idempotent month-end evidence delivery."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webconsole"))
sys.path.insert(1, str(ROOT))  # jarvis.haberci (push)
import expense_insights  # noqa: E402
import expense_vault  # noqa: E402
import invoice_analysis  # noqa: E402
import money_invoices  # noqa: E402
import money_ledger  # noqa: E402
from personal_action_store import _connect  # noqa: E402

ZONE = ZoneInfo("Europe/Istanbul")
OWNER = os.environ.get("JARVIS_EXPENSE_OWNER", "operator")
DESTINATION = "moy.ozeryildiz@gmail.com"
SENDER = "info@lcarlie.com.tr"
PART_LIMIT = 12 * 1024 * 1024


def due_period(now=None):
    now = now or datetime.now(ZONE)
    tomorrow = (now + timedelta(days=1)).date()
    if tomorrow.month != now.month:
        return now.strftime("%Y-%m")
    if now.day <= 3:
        return (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return None


def _rows(period):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id,kind,company,filename,mime_type,document_date,
            supplier,buyer,invoice_number,currency,gross_cents,tax_cents,note,status,origin,
            related_document_id,
            created_at FROM core.jarvis_expense_document WHERE owner=%s AND status<>'excluded'
            AND to_char(created_at AT TIME ZONE 'Europe/Istanbul','YYYY-MM')=%s
            ORDER BY created_at,document_id""", (OWNER, period))
        return [dict(row) for row in cur.fetchall()]


def _folder(row):
    if row["kind"] == "receipt":
        return "ORTAK_FISLER"
    if row["status"] != "ready" or row["company"] == "unknown":
        return "INCELEME_GEREKEN_FATURALAR"
    return "LEMOS_FATURALAR" if row["company"] == "lemos" else "MOY_FATURALAR"


def _summary_csv(period):
    """Category / company totals by document date, for the accountant's first look."""
    data = expense_insights.summary(OWNER, period)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["bolum", "ad", "para_birimi", "toplam", "kdv", "belge_sayisi"])
    for item in data["categories"]:
        writer.writerow(["kategori", item["label"], item["currency"], f"{item['gross']/100:.2f}",
                         f"{item['tax']/100:.2f}", item["count"]])
    for item in data["companies"]:
        writer.writerow(["sirket", item["company"], item["currency"], f"{item['gross']/100:.2f}",
                         f"{item['tax']/100:.2f}", item["count"]])
    writer.writerow(["not", f"tutari okunamayan belge: {data['unread']}", "", "", "", ""])
    return out.getvalue()


def _push(title, body, tag):
    from jarvis import haberci
    try:
        return haberci.push_gonder(title, body, tag)
    except Exception as exc:  # noqa: BLE001 - a missed push must not stop intake
        return f"push gönderilemedi: {str(exc)[:120]}"


def _archive(rows, period, part):
    memory = io.BytesIO()
    manifest = io.StringIO()
    writer = csv.writer(manifest)
    def safe_cell(value):
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
    writer.writerow(["klasor", "belge", "tur", "sirket", "tarih", "satici", "alici",
                     "fatura_no", "para_birimi", "toplam", "kdv", "durum", "kaynak",
                     "iliskili_fatura_id", "not"])
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        def put(name, data):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        for row in rows:
            folder = _folder(row)
            basename = Path(row["filename"].replace("\\", "/")).name[:100]
            safe = "".join(c for c in basename if c.isalnum() or c in ".-_ ") or "belge"
            path = f"{folder}/{row['document_id'][:8]}-{safe}"
            _, _, raw = expense_vault.content(OWNER, row["document_id"])
            put(path, raw)
            writer.writerow([safe_cell(value) for value in [folder, path, row["kind"], row["company"],
                str(row["document_date"] or ""), row["supplier"], row["buyer"],
                row["invoice_number"], row["currency"],
                "" if row["gross_cents"] is None else f"{row['gross_cents']/100:.2f}",
                "" if row["tax_cents"] is None else f"{row['tax_cents']/100:.2f}",
                row["status"], row["origin"], row["related_document_id"], row["note"]]])
        put("BELGE_LISTESI.csv", "\ufeff" + manifest.getvalue())
        put("GIDER_OZETI.csv", "\ufeff" + _summary_csv(period))
        put("ACIKLAMA.txt", (
            f"{period} / parça {part}\nFişler ortak; faturalar LEMOS ve MOY olarak ayrılır.\n"
            "İnceleme klasöründeki belgelerde şirket veya OCR bilgisi henüz doğrulanmadı.\n"
            "Bu arşiv muhasebeci incelemesi içindir; vergi indirimi kararı içermez.\n"))
    return memory.getvalue()


def _parts(rows):
    parts = []
    current = []
    size = 0
    for row in rows:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT octet_length(content) AS bytes FROM core.jarvis_expense_document
                WHERE owner=%s AND document_id=%s""", (OWNER, row["document_id"]))
            length = cur.fetchone()["bytes"]
        if current and size + length > PART_LIMIT:
            parts.append(current)
            current = []
            size = 0
        current.append(row)
        size += length
    if current or not parts:
        parts.append(current)
    return parts


def _claim(period, part, digest, count):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_expense_dispatch
            (owner,period,part,status,package_sha256,document_count)
            VALUES (%s,%s,%s,'sending',%s,%s)
            ON CONFLICT (owner,period,part) DO UPDATE SET
                status='sending',package_sha256=EXCLUDED.package_sha256,
                document_count=EXCLUDED.document_count,error=''
            WHERE core.jarvis_expense_dispatch.status='retry_requested'
            RETURNING part""", (OWNER, period, part, digest, count))
        return cur.fetchone() is not None


def _mark(period, part, status, error=""):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_expense_dispatch SET status=%s,error=%s,
            sent_at=CASE WHEN %s='sent' THEN clock_timestamp() ELSE NULL END
            WHERE owner=%s AND period=%s AND part=%s AND status='sending'""",
            (status, error[:500], status, OWNER, period, part))


def deliver(period):
    if not period or len(period) != 7:
        raise ValueError("month required")
    rows = _rows(period)
    parts = _parts(rows)
    results = []
    for index, group in enumerate(parts, 1):
        archive = _archive(group, period, index)
        digest = hashlib.sha256(archive).hexdigest()
        if not _claim(period, index, digest, len(group)):
            results.append({"part": index, "status": "already claimed"})
            continue
        message = EmailMessage()
        message["From"] = SENDER
        message["To"] = DESTINATION
        message["Subject"] = f"{period} Lemos / MOY fiş ve faturaları ({index}/{len(parts)})"
        counts = {folder: sum(_folder(row) == folder for row in group)
                  for folder in ("LEMOS_FATURALAR", "MOY_FATURALAR", "ORTAK_FISLER",
                                 "INCELEME_GEREKEN_FATURALAR")}
        message.set_content("Aylık belge paketi ektedir.\n" +
            "\n".join(f"{folder}: {number}" for folder, number in counts.items()) +
            "\n\nBelgelerin asılları ve alan listesi ZIP içindedir. Muhasebeciye iletmeden önce inceleyin.")
        message.add_attachment(archive, maintype="application", subtype="zip",
                               filename=f"LEMOS-MOY-{period}-{index}.zip")
        try:
            run = subprocess.run(["/usr/bin/msmtp", "--from=" + SENDER, "-t"],
                input=message.as_bytes(), capture_output=True, timeout=120)
            if run.returncode:
                raise RuntimeError(f"msmtp exit {run.returncode}: " +
                                   run.stderr.decode("utf-8", "replace")[:160])
        except Exception as exc:  # noqa: BLE001 - uncertain sends never retry automatically
            _mark(period, index, "failed", str(exc))
            raise
        _mark(period, index, "sent")
        results.append({"part": index, "status": "sent", "documents": len(group)})
    return results


def retry_pending():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT period FROM core.jarvis_expense_dispatch
            WHERE owner=%s AND status='retry_requested' ORDER BY period""", (OWNER,))
        periods = [row["period"] for row in cur.fetchall()]
    return {period: deliver(period) for period in periods}


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sync":
        # Gmail is the fragile step (30-31.10: TLS timeouts; 02.11: token refresh HTTP 400).
        # It used to take the whole job down; now OCR, matching and alerts run regardless,
        # and the unit still exits non-zero so the failure stays visible.
        gmail_failed = False
        for label, step in (("invoices", lambda: expense_vault.sync_gmail(OWNER)),
                            ("statements", lambda: money_ledger.sync_gmail_statements(OWNER))):
            try:
                print({label: step()})
            except Exception as exc:  # noqa: BLE001 - GoogleError, URLError, ExpenseError alike
                gmail_failed = True
                print({label: "gmail_unavailable", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
        try:  # MOY e-faturaları, salt okuma (02.11.2026); Uyumsoft düşerse gerisi yine koşar
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import uyumsoft
            print({"uyumsoft": money_invoices.sync_uyumsoft(OWNER, uyumsoft)})
        except Exception as exc:  # noqa: BLE001 - UyumsoftError, URLError, missing password file alike
            print({"uyumsoft": "unavailable", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
        try:  # Wix + Trendyol satışları, salt okuma (02.11.2026); biri düşerse gerisi yine koşar
            import channel_sales
            from jarvis import pazaryeri
            print({"channels": {"wix": channel_sales.sync_wix(OWNER),
                                "trendyol": channel_sales.sync_trendyol(OWNER, pazaryeri),
                                "invoices": channel_sales.match_invoices(OWNER)}})
        except Exception as exc:  # noqa: BLE001 - HTTP, 429, missing env alike
            print({"channels": "unavailable", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
        print({"ocr": expense_vault.process_pending(OWNER)})
        print({"backfill": expense_insights.backfill(OWNER), "rules": money_ledger.apply_rules(OWNER), "links": money_ledger.link_flows(OWNER), "transfers": money_ledger.link_transfers(OWNER),
               "receipts_matched": money_ledger.match_receipts(OWNER),
               "invoice_payments": money_invoices.match_payments(OWNER), "invoice_topics": invoice_analysis.classify_all(OWNER)})
        for alert in money_ledger.budget_alerts(OWNER) + expense_insights.subscription_alerts(OWNER):
            print({"alert": alert["title"], "push": _push(alert["title"], alert["body"], "gider-uyari")})
        if gmail_failed:
            raise SystemExit("Gmail okunamadı; Jarvis > Fiş ve Faturalar > Gmail bağlantısını yenileyin.")
    elif command == "remind":
        notice = expense_insights.reminder(OWNER)
        print({"reminder": notice and notice["body"],
               "push": notice and _push(notice["title"], notice["body"], "gider-ay-sonu")})
    elif command == "deliver":
        period = due_period()
        print({"period": period, "results": deliver(period) if period else []})
    elif command == "dry-run":
        period = sys.argv[2] if len(sys.argv) > 2 else datetime.now(ZONE).strftime("%Y-%m")
        rows = _rows(period)
        print({"period": period, "documents": len(rows),
               "parts": len(_parts(rows)), "folders": {name: sum(_folder(row) == name for row in rows)
               for name in ("LEMOS_FATURALAR", "MOY_FATURALAR", "ORTAK_FISLER",
                            "INCELEME_GEREKEN_FATURALAR")}})
    elif command == "retry-pending":
        print(retry_pending())
    else:
        raise SystemExit("usage: expense_jobs.py sync|remind|deliver|dry-run|retry-pending [YYYY-MM]")


if __name__ == "__main__":
    main()
