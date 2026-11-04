"""Expense evidence behavior on isolated PostgreSQL; never touches company data."""
import io
import os
import sys
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import expense_vault as vault


def sample_png(color="white"):
    target = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(target, format="PNG")
    return target.getvalue()


class ExpenseValidationTests(unittest.TestCase):
    def test_amounts_dates_and_company_evidence(self):
        self.assertEqual(vault._money("1.234,56", "Tutar"), 123456)
        self.assertEqual(vault._day("2026-10-25"), "2026-10-25")
        self.assertEqual(vault._company_from_buyer("LEMOS Medical A.Ş."), "lemos")
        self.assertEqual(vault._company_from_buyer("Murat Özer Yıldız"), "unknown")
        self.assertEqual(vault._company_from_buyer("moy.ozeryildiz@gmail.com"), "unknown")
        with self.assertRaises(vault.ExpenseError):
            vault._money("-50", "Tutar")
        self.assertIsNone(vault._mail_kind("TICKET12345.pdf", "Bilet - festival"))
        self.assertEqual(vault._mail_kind("Receipt-12345.pdf", "Your receipt"), "receipt")
        self.assertEqual(vault._mail_kind("5696384949.pdf", "Google faturanız"), "invoice")
        self.assertIsNone(vault._mail_kind("inline_0.png", "Faturanız", size=1478))
        self.assertIsNone(vault._mail_kind("image.jpg", "Fatura", size=5000))
        self.assertIsNone(vault._mail_kind("image.jpg", "Fatura", size=300000,
                                            disposition="inline"))
        self.assertEqual(vault._mail_kind("image.jpg", "Fatura", size=300000,
                                          disposition="attachment"), "invoice")

    def test_month_end_and_catchup(self):
        from tools import expense_jobs
        zone = ZoneInfo("Europe/Istanbul")
        self.assertEqual(expense_jobs.due_period(datetime(2026, 10, 31, 23, 55, tzinfo=zone)), "2026-10")
        self.assertEqual(expense_jobs.due_period(datetime(2026, 11, 1, 0, 10, tzinfo=zone)), "2026-10")
        self.assertIsNone(expense_jobs.due_period(datetime(2026, 10, 25, 23, 55, tzinfo=zone)))

    def test_machine_text_extracts_visible_totals_without_model_guessing(self):
        sample = ("Fatura No385280\nFatura Tarihi: 14 Ekim 2026\n"
                  "LEMOS Medical A.Ş.\nAra Toplam\n3119.90 ₺\n"
                  "20.00% KDV\n623.98 ₺\nToplam\n3743.88 ₺")
        parsed = vault._quick_extract(sample)
        self.assertEqual((parsed["invoice_number"], parsed["date"], parsed["gross"],
                          parsed["tax"], vault._company_from_buyer(parsed["buyer"])),
                         ("385280", "2026-10-14", "3743.88", "623.98", "lemos"))
        usd = vault._quick_extract("Bill to\n$100.00 paid on October 4, 2026\nTotal\n$100.00")
        self.assertEqual((usd["date"], usd["currency"], usd["gross"]),
                         ("2026-10-04", "USD", "100.00"))
        keyubu = vault._quick_extract("Fatura Sahibi\nLEMOS Medical A.Ş.\nSayın: Murat\nToplam\n88,26 ₺")
        self.assertEqual(vault._company_from_buyer(keyubu["buyer"]), "lemos")
        google = vault._quick_extract("30 Eyl 2026\nmoy.ozeryildiz@gmail.com\n₺142,40")
        self.assertEqual(google["date"], "2026-09-30")
        self.assertEqual(vault._company_from_buyer(google["buyer"]), "unknown")
        self.assertEqual(vault._quick_extract("TOPLAM $13x,00")["currency"], "TRY")

    def test_phone_exif_orientation_is_applied_before_ocr(self):
        from PIL import Image
        target = io.BytesIO()
        image = Image.new("RGB", (100, 200), "white")
        exif = Image.Exif()
        exif[274] = 6
        image.save(target, format="JPEG", exif=exif)
        output = ("Fatura Tarihi: 25.10.2026\nTOPLAM 35,00 TL\n" + "Satıcı adı\n" * 15).encode()
        with patch.object(vault.subprocess, "run") as run:
            run.return_value.stdout = output
            parsed, _ = vault._ocr(target.getvalue(), "image/jpeg")
            sent = Image.open(io.BytesIO(run.call_args.kwargs["input"]))
        self.assertEqual(sent.size, (200, 100))
        self.assertEqual(parsed["gross"], "35.00")


@unittest.skipUnless(os.environ.get("CARI_TEST_DSN"), "isolated PostgreSQL not configured")
class ExpensePostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        dsn = os.environ["CARI_TEST_DSN"]
        with psycopg.connect(dsn) as conn:
            if conn.execute("SELECT current_database()").fetchone()[0] != "jarvis_cari_test":
                raise RuntimeError("Refusing to truncate non-test database")
            conn.execute("TRUNCATE core.jarvis_expense_dispatch,core.jarvis_expense_document")
        def connect():
            conn = psycopg.connect(dsn, row_factory=dict_row)
            conn.execute("SET ROLE jarvis_web")
            return conn
        patcher = patch.object(vault, "_connect", connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_owner_scope_shared_receipt_dedupe_and_update(self):
        saved = vault.upload("alice", sample_png(), "market.png", "receipt", "lemos")
        self.assertFalse(saved["reused"])
        self.assertEqual(vault.list_documents("alice")["documents"][0]["company"], "common")
        self.assertTrue(vault.upload("alice", sample_png(), "market.png", "receipt")["reused"])
        with self.assertRaises(vault.ExpenseError):
            vault.content("bob", saved["id"])
        vault.update("alice", saved["id"], {"kind": "receipt", "company": "common",
            "document_date": "2026-10-25", "supplier": "Market", "buyer": "",
            "invoice_number": "", "currency": "TRY", "gross": "120,50",
            "tax": "10,00", "note": "Günlük", "status": "ready"})
        row = vault.list_documents("alice")["documents"][0]
        self.assertEqual((row["gross_cents"], row["tax_cents"], row["status"]),
                         (12050, 1000, "ready"))
        self.assertEqual(vault.content("alice", saved["id"])[2], sample_png())

    def test_ocr_suggestion_never_autofiles_as_ready(self):
        saved = vault.upload("alice", sample_png("blue"), "fatura.png", "invoice", "unknown")
        parsed = {"supplier": "Satıcı", "buyer": "LEMOS Medical", "date": "2026-10-25",
                  "invoice_number": "ABC2026000000001", "currency": "TRY",
                  "gross": "300.00", "tax": "50.00"}
        with patch.object(vault, "_ocr", return_value=(parsed, "LEMOS Medical invoice")):
            vault.process("alice", saved["id"])
        row = vault.list_documents("alice")["documents"][0]
        self.assertEqual((row["company"], row["status"], row["gross_cents"]),
                         ("lemos", "review", 30000))

    def test_receipt_links_only_to_one_invoice_in_same_owner(self):
        receipt = vault.upload("alice", sample_png("red"), "fis.png", "receipt")
        other_receipt = vault.upload("alice", sample_png("blue"), "fis2.png", "receipt")
        invoice = vault.upload("alice", sample_png("green"), "fatura.png", "invoice", "lemos")
        foreign_invoice = vault.upload("bob", sample_png("yellow"), "foreign.png", "invoice", "moy")
        body = {"kind": "receipt", "company": "common", "document_date": "2026-10-25",
                "currency": "TRY", "gross": "100.00", "tax": "", "supplier": "Test",
                "buyer": "", "invoice_number": "", "note": "", "status": "ready",
                "related_document_id": invoice["id"]}
        vault.update("alice", receipt["id"], body)
        self.assertEqual(vault.list_documents("alice")["documents"][-1]["related_document_id"], invoice["id"])
        with self.assertRaises(vault.ExpenseError):
            vault.update("alice", other_receipt["id"], dict(body, related_document_id=foreign_invoice["id"]))
        with self.assertRaises(vault.ExpenseConflict):
            vault.update("alice", other_receipt["id"], body)
        vault.update("alice", receipt["id"], dict(body, related_document_id=""))
        vault.update("alice", other_receipt["id"], body)

    def test_pdf_preview_is_image_and_owner_scoped(self):
        import fitz
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 72), "Invoice test")
            raw = pdf.tobytes()
        saved = vault.upload("alice", raw, "invoice.pdf", "invoice", "unknown")
        mime, image = vault.preview("alice", saved["id"])
        self.assertEqual(mime, "image/png")
        self.assertTrue(image.startswith(b"\x89PNG"))
        with self.assertRaises(vault.ExpenseError):
            vault.preview("bob", saved["id"])

    def test_failed_delivery_requires_user_retry_and_cannot_resend_sent(self):
        from tools import expense_jobs
        with patch.object(expense_jobs, "_connect", vault._connect), \
             patch.object(expense_jobs, "OWNER", "alice"):
            period = "2026-10"
            digest = "a" * 64
            self.assertTrue(expense_jobs._claim(period, 1, digest, 1))
            expense_jobs._mark(period, 1, "failed", "test failure")
            self.assertFalse(expense_jobs._claim(period, 1, digest, 1))
            self.assertEqual(vault.request_dispatch_retry("alice", period, 1)["status"], "retry_requested")
            self.assertTrue(expense_jobs._claim(period, 1, digest, 1))
            expense_jobs._mark(period, 1, "sent")
            with self.assertRaises(vault.ExpenseError):
                vault.request_dispatch_retry("alice", period, 1)

    def test_monthly_archive_separates_receipts_and_invoices_once(self):
        from tools import expense_jobs
        receipt = vault.upload("alice", sample_png("red"), "fis.png", "receipt")
        invoice = vault.upload("alice", sample_png("green"), "fatura.png", "invoice", "moy")
        for doc_id, kind, company in ((receipt["id"], "receipt", "common"),
                                      (invoice["id"], "invoice", "moy")):
            vault.update("alice", doc_id, {"kind": kind, "company": company,
                "document_date": "2026-10-25", "currency": "TRY", "gross": "100.00",
                "tax": "", "supplier": "Test", "buyer": "", "invoice_number": "",
                "note": "", "status": "ready"})
        with patch.object(expense_jobs, "_connect", vault._connect), \
             patch.object(expense_jobs, "OWNER", "alice"):
            period = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m")
            rows = expense_jobs._rows(period)
            self.assertEqual(len(rows), 2)
            payload = expense_jobs._archive(rows, period, 1)
            self.assertEqual(payload, expense_jobs._archive(rows, period, 1))
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.startswith("ORTAK_FISLER/") for name in names))
                self.assertTrue(any(name.startswith("MOY_FATURALAR/") for name in names))
                self.assertIn("BELGE_LISTESI.csv", names)
            digest = "a" * 64
            self.assertTrue(expense_jobs._claim(period, 1, digest, 2))
            self.assertFalse(expense_jobs._claim(period, 1, digest, 2))
            expense_jobs._mark(period, 1, "sent")
            self.assertEqual(vault.list_documents("alice")["dispatches"][0]["status"], "sent")
