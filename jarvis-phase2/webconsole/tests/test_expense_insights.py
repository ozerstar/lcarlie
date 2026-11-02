#!/usr/bin/env python3
"""Kart hareketi okuma, kategori, abonelik ve e-postayla fiş alma.

Örnekler 02.11.2026'da sahibin gönderdiği gerçek belgelerden kısaltıldı
(kişi adları, kart ve hesap numaraları çıkarıldı):

  * Enpara kredi kartı ekstresi: okunan toplam, ekstre özetindeki
    "Harcamalar ve yansıyan taksitler 88.534,49 TL" ile kuruşu kuruşuna tuttu.
  * Enpara vadesiz hesap dökümü: işaretler TERS — harcama "-504,99 TL";
    maaş, aile transferi, EFT ve ATM satırları hiç saklanmaz.
  * Yapı Kredi uygulaması ekran görüntüsü (PaddleOCR çıktısı): gün, ay ve
    satıcı her ekranda farklı sırada.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

WEB = Path(__file__).resolve().parents[1]
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

import expense_insights  # noqa: E402
import expense_vault  # noqa: E402
import money_ledger  # noqa: E402

TODAY = date(2026, 11, 2)

CARD_STATEMENT = """Ekstre tarihi
10/10/2026
Ekstre borcu
190.435,81 TL
Son ödeme tarihi
20/10/2026
Ad soyad
X
Kart limiti
400.000,00 TL
İşlem tarihi
Açıklama
Taksit
Tutar
Bir önceki ekstre bakiyeniz
169.360,51 TL
16/09/2026
Ödeme - Enpara.com Cep Şubesi
- 67.745,00 TL
12/09/2026
KEYUBU İNTERNET
 449,88 TL
16/09/2026
5421886937 - VODAFONE - ODEME
 2.608,75 TL
25/09/2026
ANTHROPIC (20,00 USD)
 994,10 TL
01/10/2026
APPLE.COM/BILL
- 4.593,32 TL
10/10/2026
Alışveriş faizi
 3.753,17 TL
10/10/2026
Faizlerin KKDF’si*
 562,98 TL
11/09/2026
FACEBK *LBWFR5JER4
 2.908,29 TL
"""

ACCOUNT_STATEMENT = """Tarih
Hareket tipi
Açıklama
İşlem Tutarı
Bakiye
02.11.2026
Encard
Harcaması
YEMEKPAY/YEMEK SEPETI E  ISTANBUL     TR
-504,99 TL
40.904,53 TL
31.10.2026
Gelen Transfer
A, 2026 EKİM AYI ÜCRETİ
28.075,50 TL
41.409,52 TL
30.10.2026
Giden Transfer
B, Bireysel Ödeme, EFT (FAST) sorgu no: 1
-525,00 TL
0,69 TL
19.10.2026
Ödeme
Enpara.com kredi kartı ödemesi, C
-40.175,00 TL
28.310,69 TL
03.08.2026
Encard Harcaması
ZİRAAT BANKASI A.Ş. ATM sinden para çekme
-2.000,00 TL
1.000,00 TL
"""

SCREENSHOT = """02:27 VOLTE VLTE5
1 Kredi Kartlarim
Adios Premium
5258 64** **** 8111
Son Hareketler Kart Hareketlerine Git >
1 NKOLAY 2MRN GIDAI ANKARA
Kasim Tr
Ek Kart Bekleyen Provizyon
)60,00 TL
1 BIMBIM-C925 YAHYALARANKARATR
Kasim
EkKart
)721,50 TL
achos Dremlam oTapltredl
Ekim 31 ERMANTICARETANKARATR
EkKart
)225,00TL
ALTIN PETROL ANKARA TR
29
Ekim
2026 120,00TL
RENAULTCiHANOTOMOTiVANKAI
15 Ekim TR26710,75TLlik islemin2/3 taksid
"""


def rows(text):
    return [(item["date"].isoformat(), item["direction"], item["kind"], item["amount"], item["party"])
            for item in money_ledger.parse_statement(text, TODAY)]


class CardStatementTest(unittest.TestCase):
    def test_purchases_and_your_payment_back_in(self):
        got = rows(CARD_STATEMENT)
        out = [row for row in got if row[1] == "out" and row[2] == "kart"]
        self.assertEqual([row[3] for row in out], [44988, 260875, 99410, 290829])
        self.assertNotIn(40000000, [row[3] for row in got])  # kart limiti başlıkta
        payment = [row for row in got if row[3] == 6774500][0]
        self.assertEqual(payment[1], "in")  # kart borcunu ödemek karta giren para
        fees = [row for row in got if row[2] == "banka"]
        self.assertEqual(len(fees), 2)  # faiz + KKDF ayrı türde, harcama sanılmaz

    def test_foreign_amount_is_kept_for_dollar_invoices(self):
        anthropic = [item for item in money_ledger.parse_statement(CARD_STATEMENT, TODAY)
                     if "ANTHROPIC" in item["party"]][0]
        self.assertEqual((anthropic["foreign_currency"], anthropic["foreign_cents"]), ("USD", 2000))
        self.assertEqual(anthropic["account"], "Enpara kredi kartı")


class AccountStatementTest(unittest.TestCase):
    def test_every_movement_with_type_and_person(self):
        got = rows(ACCOUNT_STATEMENT)
        self.assertIn(("2026-11-02", "out", "kart", 50499, "YEMEKPAY/YEMEK SEPETI E ISTANBUL"), got)
        self.assertIn(("2026-10-31", "in", "transfer", 2807550, "A"), got)
        self.assertIn(("2026-10-30", "out", "transfer", 52500, "B"), got)
        self.assertIn(("2026-08-03", "out", "atm", 200000, "ZİRAAT BANKASI A.Ş. ATM sinden para çekme"), got)
        card_payment = [row for row in got if row[3] == 4017500][0]
        self.assertEqual(card_payment[2], "ic_transfer")  # kart borcu: harcama iki kez sayılmaz

    def test_balance_column_is_not_a_movement(self):
        self.assertNotIn(4090453, [row[3] for row in rows(ACCOUNT_STATEMENT)])

    def test_salary_is_income(self):
        salary = [item for item in money_ledger.parse_statement(ACCOUNT_STATEMENT, TODAY) if item["amount"] == 2807550][0]
        self.assertEqual(money_ledger._auto(salary)[0], "gelir")

    def test_two_identical_rows_same_day_are_two_movements(self):
        text = "\n".join(["Bakiye",
                          "10.08.2026", "Gelen Transfer", "DERYA E, Bireysel", "1.400,00 TL", "5.000,00 TL",
                          "10.08.2026", "Gelen Transfer", "DERYA E, Bireysel", "1.400,00 TL", "6.400,00 TL", ""])
        got = money_ledger.parse_statement(text, TODAY)
        self.assertEqual([item["ordinal"] for item in got], [1, 2])


class ScreenshotTest(unittest.TestCase):
    def test_day_month_order_varies_and_logo_noise_loses(self):
        got = rows(SCREENSHOT)
        self.assertEqual([(row[0], row[3], row[4]) for row in got[:4]], [
            ("2026-11-01", 6000, "NKOLAY 2MRN GIDAI ANKARA"),
            ("2026-11-01", 72150, "BIMBIM-C925 YAHYALARANKARATR"),
            ("2026-10-31", 22500, "ERMANTICARETANKARATR"),
            ("2026-10-29", 12000, "ALTIN PETROL ANKARA"),
        ])

    def test_installment_total_is_not_a_charge(self):
        renault = [item for item in money_ledger.parse_statement(SCREENSHOT, TODAY) if "RENAULT" in item["party"]]
        self.assertEqual([(item["kind"], money_ledger._auto(item)[1]) for item in renault], [("taksit", "ignored")])

    def test_pending_authorisation_is_noted(self):
        self.assertEqual(money_ledger.parse_statement(SCREENSHOT, TODAY)[0]["note"], "Bekleyen provizyon")

    def test_same_card_on_every_screenshot(self):
        accounts = {item["account"] for item in money_ledger.parse_statement(SCREENSHOT, TODAY)}
        self.assertEqual(accounts, {"Yapı Kredi kredi kartı ****8111"})


def movement(day, amount, party="X", category="yemek", direction="out", scope="kisisel"):
    return {"id": f"{day}{party}{amount}", "tx_date": date.fromisoformat(day), "direction": direction, "party": party,
            "party_key": money_ledger.key_of(party), "amount_cents": amount, "category": category, "scope": scope,
            "account": "A", "kind": "kart", "receipt": "not_needed", "note": "", "document_id": None,
            "foreign_currency": None, "foreign_cents": None}


class BuildReportTest(unittest.TestCase):
    ROWS = [
        movement("2026-09-07", 500000, "Sinem Ağca", "sosyal_medya"),
        movement("2026-10-08", 500000, "Sinem Ağca", "sosyal_medya"),
        movement("2026-10-20", 700000, "Sinem Ağca", "sosyal_medya"),
        movement("2026-09-03", 30000, "Yemekpay"), movement("2026-09-10", 32000, "Yemekpay"),
        movement("2026-10-02", 31000, "Yemekpay"), movement("2026-11-01", 29000, "Yemekpay"),
        movement("2026-11-02", 400000, "Yemekpay"),
        movement("2026-11-01", 4000000, "Kendim", "ic_transfer"),
        movement("2026-10-31", 2807550, "Maaş", "gelir", direction="in"),
    ]

    def test_internal_transfer_not_counted_and_pace_against_same_day(self):
        got = money_ledger.build_report(self.ROWS, "month", date(2026, 11, 2), today=date(2026, 11, 2))
        self.assertEqual(got["out_total"], 429000)          # 40.000 TL kendine transfer hariç
        self.assertEqual(got["elapsed_days"], 2)
        self.assertEqual(got["same_point_prev"], 31000)     # Ekim'in ilk 2 günü
        self.assertEqual(got["pace"]["current"], [29000, 429000])
        self.assertIsNone(got["forecast"])                  # 3 günden az: tahmin yok

    def test_recurring_and_unusual(self):
        got = money_ledger.build_report(self.ROWS, "month", date(2026, 11, 2), today=date(2026, 11, 2))
        self.assertEqual(got["unusual"][0]["party"], "Yemekpay")   # 4.000 TL, olağanı ~300 TL
        oct_report = money_ledger.build_report(self.ROWS, "month", date(2026, 10, 15), today=date(2026, 11, 2))
        self.assertEqual(oct_report["in_total"], 2807550)
        self.assertIn("Yemekpay", [item["party"] for item in oct_report["recurring"]])
        sinem = [item for item in oct_report["recurring"] if item["party"] == "Sinem Ağca"]
        self.assertEqual(sinem, [])  # 5.000 ve 7.000: tutarlar düzenli değil, abonelik sayılmaz

    def test_closed_month_compares_whole_months_and_forecast_mid_month(self):
        got = money_ledger.build_report(self.ROWS, "month", date(2026, 10, 15), today=date(2026, 10, 15))
        self.assertEqual(got["forecast"], round(got["out_total"] / 15 * 31))
        full = money_ledger.build_report(self.ROWS, "month", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertEqual(full["prev_out_total"], 562000)
        self.assertEqual(len(full["trend"]), 6)
        self.assertEqual(full["trend"][-1]["month"], "2026-10")

    def test_scope_filter(self):
        rows = self.ROWS + [movement("2026-10-10", 150000, "Derin", "personel", scope="lcarlie")]
        got = money_ledger.build_report(rows, "month", date(2026, 10, 1), scope="lcarlie", today=date(2026, 11, 2))
        self.assertEqual(got["out_total"], 150000)


class DeeperAnalysisTest(unittest.TestCase):
    ROWS = BuildReportTest.ROWS + [
        movement("2026-10-10", 150000, "Derin Kocatepe", "personel", scope="lcarlie"),
        movement("2026-10-12", 90000, "Opet", "akaryakit", scope="kisisel"),
    ]

    def test_scope_trend_per_month(self):
        got = money_ledger.build_report(self.ROWS, "month", date(2026, 10, 1), today=date(2026, 11, 2))
        october = got["trend"][-1]["scopes"]
        self.assertEqual(october["lcarlie"], 150000)
        self.assertEqual(october["kisisel"], 500000 + 700000 + 31000 + 90000)

    def test_family_is_its_own_scope(self):
        """Owner, 02.11.2026: "kişisel harcama ve aileyi de ayır"."""
        rows = self.ROWS + [movement("2026-10-20", 120000, "Göksel Çiçek", "aile", scope="aile")]
        got = money_ledger.build_report(rows, "month", date(2026, 10, 1), today=date(2026, 11, 2))
        october = got["trend"][-1]["scopes"]
        self.assertEqual(october["aile"], 120000)
        self.assertEqual(october["kisisel"], 500000 + 700000 + 31000 + 90000)
        only = money_ledger.build_report(rows, "month", date(2026, 10, 1), scope="aile", today=date(2026, 11, 2))
        self.assertEqual(only["out_total"], 120000)
        self.assertEqual(money_ledger.SCOPES["aile"], "Aile")

    def test_review_is_plain_turkish_from_numbers(self):
        got = money_ledger.build_report(self.ROWS, "month", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertTrue(got["review"][0].startswith("Ekim 2026 döneminde"))
        self.assertTrue(any("Gelen" in sentence for sentence in got["review"]))

    def test_budget_pace_and_states(self):
        limits = {"yemek": 30000, "akaryakit": 200000, "sosyal_medya": 1500000}
        got = {item["category"]: item for item in
               money_ledger.budget_status(self.ROWS, limits, date(2026, 10, 1), today=date(2026, 10, 15))}
        self.assertEqual(got["yemek"]["state"], "over")         # 310 / 300 TL
        self.assertEqual(got["akaryakit"]["state"], "ok")       # 900 / 2.000 TL, ayın yarısı
        self.assertEqual(got["sosyal_medya"]["state"], "warn")  # %80'e ayın ortasında ulaşıldı
        self.assertEqual(got["akaryakit"]["expected_pct"], 48)

    def test_category_detail(self):
        got = money_ledger.category_detail_from(self.ROWS, "sosyal_medya", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertEqual(got["total"], 1200000)
        self.assertEqual(got["count"], 2)
        self.assertEqual([m["total"] for m in got["trend"]][-2:], [500000, 1200000])
        self.assertEqual(got["parties"][0]["label"], "Sinem Ağca")


class DrillDownTest(unittest.TestCase):
    """Owner: "her yer tıklanabilir… ofisin içinde kira, muhasebe ödemesi gibi ödemeler var"."""

    def rows(self):
        office_rent = dict(movement("2026-10-02", 2500000, "Ev Sahibi", "ofis"), subcategory="Kira", account="Enpara hesap")
        office_acc = dict(movement("2026-10-05", 400000, "Muhasebeci", "ofis"), subcategory="Muhasebe", account="Enpara hesap")
        card = dict(movement("2026-10-06", 50000, "Kırtasiye", "ofis"), subcategory="", account="Yapı Kredi kredi kartı ****8111")
        salary = dict(movement("2026-10-31", 2807550, "Muharrem", "gelir", direction="in"), subcategory="", account="Enpara hesap")
        return [office_rent, office_acc, card, salary]

    def test_subcategory_breakdown_inside_a_category(self):
        got = money_ledger.category_detail_from(self.rows(), "ofis", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertEqual([(s["label"], s["total"]) for s in got["subcategories"]],
                         [("Kira", 2500000), ("Muhasebe", 400000), ("Alt kalem seçilmedi", 50000)])
        self.assertIn("Muhasebe", got["suggestions"])

    def test_income_category_opens_money_in(self):
        got = money_ledger.category_detail_from(self.rows(), "gelir", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertEqual((got["direction"], got["total"]), ("in", 2807550))

    def test_bank_filter_and_account_list(self):
        got = money_ledger.build_report(self.rows(), "month", date(2026, 10, 1), today=date(2026, 11, 2),
                                        account="Yapı Kredi kredi kartı ****8111")
        self.assertEqual(got["out_total"], 50000)
        self.assertEqual({a["name"] for a in got["accounts"]}, {"Enpara hesap", "Yapı Kredi kredi kartı ****8111"})

    def test_other_slice_has_every_category(self):
        got = money_ledger.build_report(self.rows(), "month", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertEqual(got["trend"][-1]["all"], {"ofis": 2950000})


class RuleFormTest(unittest.TestCase):
    def test_turkish_thousands_in_monthly_amount(self):
        cursor = mock.MagicMock()
        connection = mock.MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        with mock.patch.object(money_ledger, "_connect", return_value=connection), \
                mock.patch.object(money_ledger, "apply_rules", return_value=0):
            money_ledger.set_rule("o", {"party": "Sinem Ağca", "category": "sosyal_medya", "monthly": "12.000",
                                        "start_month": "2026-09"})
        self.assertEqual(cursor.execute.call_args[0][1][5], 1200000)


class AgreementTest(unittest.TestCase):
    """Sinem Ağca: 12.000/ay Eylül'den; 07.09 5.000, 08.10 5.000, 20.10 7.000.
    Sahip: Eylül 5+5+2 ile kapandı, Ekim'den 7.000 borç var."""

    def run_agreement(self, rule, payments, today):
        cursor = mock.MagicMock()
        cursor.fetchall.side_effect = [[rule], payments]
        connection = mock.MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        with mock.patch.object(money_ledger, "_connect", return_value=connection):
            return money_ledger.agreements("o", today)[0]

    def rule(self, **extra):
        base = {"party_key": "k", "label": "Sinem Ağca", "category": "sosyal_medya", "scope": "",
                "monthly_cents": 1200000, "start_month": date(2026, 9, 1), "end_month": None,
                "opening_cents": 0, "note": ""}
        return {**base, **extra}

    def test_sinem_owes_seven_thousand_for_october(self):
        payments = [{"tx_date": date(2026, 9, 7), "amount_cents": 500000},
                    {"tx_date": date(2026, 10, 8), "amount_cents": 500000},
                    {"tx_date": date(2026, 10, 20), "amount_cents": 700000}]
        got = self.run_agreement(self.rule(), payments, date(2026, 11, 2))
        months = {row["month"]: row for row in got["months"]}
        self.assertEqual(months["2026-09"]["open"], 0)
        self.assertEqual(months["2026-10"]["open"], 700000)
        self.assertEqual(got["owed_closed_months"], 700000)
        self.assertTrue(months["2026-11"]["current"])

    def test_ended_agreement_accrues_nothing_after(self):
        # Mina Dilara: Ekim'de çalışma yapılmadı, ödeme de yok -> borç yok
        rule = self.rule(label="Mina Dilara", monthly_cents=1000000, start_month=date(2026, 8, 1),
                         end_month=date(2026, 9, 1))
        payments = [{"tx_date": date(2026, 8, 3), "amount_cents": 1000000},
                    {"tx_date": date(2026, 9, 5), "amount_cents": 1000000}]
        got = self.run_agreement(rule, payments, date(2026, 11, 2))
        self.assertEqual([row["month"] for row in got["months"]], ["2026-08", "2026-09"])
        self.assertEqual(got["owed_closed_months"], 0)


class CategoryTest(unittest.TestCase):
    def test_real_merchants(self):
        cases = {"BIM BIRLESIK MAGAZALAR A.S.": "market", "ALTIN PETROL ANKARA": "akaryakit",
                 "EGO KART-ARAC ICI GECIS ANKARA": "ulasim", "İVEDİK DÖNER": "yemek",
                 "FACEBK *LBWFR5JER4": "reklam", "KEYUBU İNTERNET": "yazilim",
                 "7049564866 - TURK TELEKOM INTERNET/TV (": "faturalar",
                 "KADIOĞLU KIRTASİYE PAZARL": "ofis", "SAPKACI UMIT": "diger"}
        for merchant, category in cases.items():
            self.assertEqual(expense_insights.categorize(merchant), category, merchant)

    def test_vendor_from_invoice_body_when_seller_line_missing(self):
        self.assertEqual(expense_insights.vendor("Ek Ram (Ultra) VDS L-TR 7GB"), "Keyubu İnternet (VDS sunucu)")
        self.assertEqual(expense_insights.vendor("₺142,40 Google Workspace TRY"), "Google Workspace")


class MailIntakeTest(unittest.TestCase):
    def test_phone_photo_mailed_with_subject_fis_is_a_receipt(self):
        self.assertEqual(expense_vault._mail_kind("IMG_1234.jpg", "fiş", size=2_000_000), "receipt")
        self.assertEqual(expense_vault._mail_kind("IMG_1234.HEIC", "Fis", size=2_000_000), "receipt")

    def test_logo_and_signature_images_are_skipped(self):
        # 26.10'da kaybolan süzgeç: dokuz "inline_0.png" fatura kuyruğuna düşmüştü
        self.assertIsNone(expense_vault._mail_kind("inline_0.png", "fatura"))
        self.assertIsNone(expense_vault._mail_kind("image.png", "fatura", size=4_000))
        self.assertIsNone(expense_vault._mail_kind("photo.jpg", "fatura", disposition="inline"))

    def test_invoice_pdf_still_invoice(self):
        self.assertEqual(expense_vault._mail_kind("Fatura-379829.pdf", "Faturanız"), "invoice")


class ReminderTest(unittest.TestCase):
    def test_only_in_last_three_days_and_once(self):
        lines = {"counts": {"open": 3, "matched": 1, "ignored": 0}, "open_total": 123450}
        totals = {"unread": 1, "unchecked": 2}
        with mock.patch.object(money_ledger, "receipt_lines", return_value=lines), \
                mock.patch.object(expense_insights, "summary", return_value=totals), \
                mock.patch.object(expense_insights, "_claim_notice", side_effect=[True, False]) as claim:
            self.assertIsNone(expense_insights.reminder("o", date(2026, 11, 20)))
            notice = expense_insights.reminder("o", date(2026, 11, 28))
            self.assertIn("3 kart harcamasının fişi yok (1.234,50 TL)", notice["body"])
            self.assertIsNone(expense_insights.reminder("o", date(2026, 11, 29)))
            self.assertEqual(claim.call_count, 2)



class FlowLinkTest(unittest.TestCase):
    """Owner, 02.11.2026: money that comes in and leaves within two days belongs together."""

    def test_passed_on_to_a_third_party_is_neither_income_nor_spending(self):
        # 08.07: MOY 159.980 in; Can Bostan 100.000 + own savings 50.000 + 10.000 out the same day
        rows = [movement("2026-07-08", 15998000, "MOY DAN.TEK.ORG", "", "in", ""),
                movement("2026-07-08", 10000000, "Ahmet Can Bostan", "hizmet"),
                movement("2026-07-08", 5000000, "tatil hesabıma", "ic_transfer", scope=""),
                movement("2026-07-08", 1000000, "tatil hesabıma 2", "ic_transfer", scope=""),
                movement("2026-07-10", 1000000, "Erkan Azazi", "hatirlanmiyor")]
        found = money_ledger.find_links(rows)
        self.assertEqual([(l["out_id"], l["amount_cents"], l["kind"]) for l in found],
                         [(rows[1]["id"], 10000000, "aracilik")])
        links = [dict(l, status="auto") for l in found]
        net = money_ledger.net_links(rows, links)
        got = money_ledger.build_report(net, "month", date(2026, 7, 1), today=date(2026, 8, 1))
        self.assertEqual(got["in_total"], 5998000)           # 59.980 TL stayed with us
        self.assertEqual(got["out_total"], 1000000)          # only Erkan; Can Bostan was MOY's business
        self.assertEqual(got["passthrough_total"], 10000000)
        flows = money_ledger.flow_groups(net, links, date(2026, 7, 1), date(2026, 8, 1))
        self.assertEqual(flows[0]["amount"], 15998000)
        self.assertEqual(flows[0]["outs"][0]["party"], "Ahmet Can Bostan")

    def test_paying_own_debts_is_explanation_only(self):
        # 23.06: MOY 100.000 + 20.000 in; Orhan (debt) 70.000 + own card 48.000 + 2.000 out
        rows = [movement("2026-06-23", 10000000, "MOY", "", "in", ""), movement("2026-06-23", 2000000, "MOY", "", "in", ""),
                movement("2026-06-23", 7000000, "Orhan Talha Canal", "borc"),
                movement("2026-06-23", 4800000, "Murat Özer Yıldız", "kart_borcu"),
                movement("2026-06-23", 1200000, "Murat Özer Yıldız ", "kart_borcu"),
                movement("2026-06-23", 200000, "Sümeyye Bozkurt", "hatirlanmiyor")]
        found = money_ledger.find_links(rows)
        self.assertEqual({l["kind"] for l in found}, {"kullanim"})
        self.assertEqual(sum(l["amount_cents"] for l in found), 12000000)
        net = money_ledger.net_links(rows, [dict(l, status="auto") for l in found])
        self.assertEqual(sum(r["amount_cents"] for r in net if r["direction"] == "out"), 13200000)

    def test_salary_support_spent_the_same_day_is_not_cancelled(self):
        rows = [movement("2026-10-02", 5000000, "MERAL YILDIZ", "gelir_destegi", "in"),
                movement("2026-10-02", 5000000, "Moy Danışmanlık", "ofis", scope="moy")]
        self.assertEqual(money_ledger.find_links(rows)[0]["kind"], "kullanim")

    def test_rejected_match_never_comes_back_and_small_money_is_ignored(self):
        rows = [movement("2026-07-08", 10000000, "MOY", "", "in", ""), movement("2026-07-09", 10000000, "Can Bostan", "hizmet")]
        first = money_ledger.find_links(rows)[0]
        self.assertEqual(money_ledger.find_links(rows, [dict(first, status="rejected")]), [])
        self.assertEqual(money_ledger.find_links(rows, [dict(first, status="auto")]), [])
        late = [rows[0], movement("2026-07-11", 10000000, "Can Bostan", "hizmet")]
        self.assertEqual(money_ledger.find_links(late), [])  # three days later: not the same money
        small = [movement("2026-07-04", 100000, "Orhan", "", "in", ""), movement("2026-07-05", 100600, "Macit", "diger")]
        self.assertEqual(money_ledger.find_links(small), [])

    def test_coincidences_from_the_live_dry_run_are_not_matched(self):
        # Lemos salary 66.666: card payment 64.188 + savings — only 2.500 to a person
        salary = [movement("2026-06-30", 6666600, "LEMOS", "", "in", ""),
                  movement("2026-06-30", 6418800, "Enpara kart", "ic_transfer", scope=""),
                  movement("2026-07-02", 250000, "Macit", "diger")]
        self.assertEqual(money_ledger.find_links(salary), [])
        sale = [movement("2026-09-08", 600000, "Ömer", "tahsilat", "in"), movement("2026-09-10", 600000, "Mehmet", "personel")]
        self.assertEqual(money_ledger.find_links(sale), [])  # under 10.000 TL


class ExcludeTest(unittest.TestCase):
    """Owner: "Can için gelip giden parayı o ayki harcama kaleminden çıkartabilmeliyim"."""

    def test_excluded_and_passed_rows_are_shown_but_not_counted(self):
        rows = [movement("2026-10-03", 300000, "Can", "hizmet"), movement("2026-10-04", 200000, "Ali", "haric"),
                movement("2026-10-05", 100000, "Veli", "aracilik"), movement("2026-10-06", 50000, "Para", "haric", "in")]
        got = money_ledger.build_report(rows, "month", date(2026, 10, 1), today=date(2026, 11, 2))
        self.assertEqual(got["out_total"], 300000)
        self.assertEqual(got["in_total"], 0)
        self.assertEqual(len(got["movements"]), 4)
        self.assertEqual(money_ledger.category_detail_from(rows, "haric", date(2026, 10, 1))["count"], 2)



class BookTest(unittest.TestCase):
    """Owner, 02.11.2026: Lemos (QNB) and MOY (Enpara Şirketim) accounts stay in their own books."""

    def test_own_statement_naming_lemos_as_counterparty_stays_personal(self):
        text = ("Hesap adı Murat Özer Yıldız Vadesiz TL\n02.10.2026 Gelen Transfer LEMOS MEDİKAL SAĞLIK 13.333,00 TL "
                "Gelen Transfer MOY DAN.TEK.ORG.SAN.VE TİC.AŞ. 100.000,00 TL")
        self.assertEqual(money_ledger.book_of(text), "kisisel")

    def test_company_accounts_are_recognised(self):
        self.assertEqual(money_ledger.book_of("QNB 146275187 no'lu hesabınızın Günlük hareketleri"), "lemos")
        self.assertEqual(money_ledger.book_of("Enpara Şirketim <bilgi@enpara.com> 2026 Eylül ayı Moy Danışmanlık A.ş."), "moy")
        self.assertEqual(money_ledger.book_of("herhangi bir metin", "lemos"), "lemos")
        with self.assertRaises(money_ledger.ExpenseError):
            money_ledger.book_of("x", "baska")



class GmailRetryTest(unittest.TestCase):
    """02.11.2026: a stalled TLS handshake to Google stopped the whole statement sync."""

    def test_network_hiccup_is_retried_but_a_refusal_is_not(self):
        import io
        import urllib.error
        from unittest import mock
        import expense_vault
        ok = mock.MagicMock()
        ok.__enter__.return_value = io.BytesIO(b'{"messages": []}')
        with mock.patch("urllib.request.urlopen", side_effect=[urllib.error.URLError("handshake timed out"), ok]) as op,                 mock.patch("time.sleep"):
            self.assertEqual(expense_vault._gmail_json("messages", "t"), {"messages": []})
        self.assertEqual(op.call_count, 2)
        refused = urllib.error.HTTPError("u", 401, "no", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=refused) as op, mock.patch("time.sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                expense_vault._gmail_json("messages", "t")
        self.assertEqual(op.call_count, 1)



QNB_DAILY = """Hesap Hareketleri
29/10/2026
:
IBAN
TR680011100000000146275187
Hesap Adı
TL Bereketli Ticari Hesap
28/10/2026 - 28/10/2026
LEMOS MEDİKAL SAĞLIK İŞ GÜVENLİĞİ İNŞAAT
İşlem Tarihi
Kanal*
İşlem Açıklaması
Tutar
Bakiye
DEVREDEN BAKİYE
4,107.67
28/10/2026
ŞB
Transfer İşlemleri - Gönderen: PAYTR ÖDEME VE ELEKTRONİK PARA KURULUŞU
ANONİM ŞİRKETİ Sorgu No: 4047043 - PAYTR NET TUTAR
2,014.74
6,122.41
28/10/2026
MB
Transfer İşlemleri - Alıcı: SİNEM AĞCA Sorgu No: 4047099
-1,500.00
4,622.41
Bu doküman bilgi amaçlı hazırlanmıştır.
Sayfa: 1/1
"""

QNB_KMH = """Aylık KMH Faiz Oranı
: 4.25 %
Son Ödeme Tarihi
: 31/07/2026
Toplam Bakiye
:54,993.79 TL
İŞLEM TARİHİ
AÇIKLAMA
TUTAR
BAKİYE
DEVREDEN BAKİYENİZ
4,000.00 +
01/07/2026
Gönderen: PAYTR ÖDEME VE ELEKTRONİK PARA KURULUŞU ANONİ
360.41 +
4,360.41 +
03/07/2026
İşyeri:132600000013961 (Satış) N003 Yurt İçi Kredi Kart
7,710.00 +
12,070.41 +
09/07/2026
Bereketli Ticari Hesaba giden tutar (Faiz oranı %40.5)
2,070.41 -
10,000.00 +
"""


class QnbStatementTest(unittest.TestCase):
    """Lemos' QNB statements (02.11.2026): "2,014.74" amounts, the balance tells the direction."""

    def test_daily_statement(self):
        rows = money_ledger.parse_statement(QNB_DAILY)
        self.assertEqual([(r["direction"], r["amount"], r["party"]) for r in rows],
                         [("in", 201474, "PAYTR ÖDEME VE ELEKTRONİK PARA KURULUŞU ANONİM ŞİRKETİ"), ("out", 150000, "SİNEM AĞCA")])
        self.assertEqual(rows[0]["category"], "tahsilat")
        self.assertEqual(rows[0]["account"], "QNB Bereketli Ticari Hesap")
        self.assertEqual(rows[0]["date"], date(2026, 10, 28))

    def test_kmh_statement_with_sweeps_and_pos(self):
        rows = money_ledger.parse_statement(QNB_KMH)
        self.assertEqual([(r["direction"], r["amount"], r["kind"], r["category"]) for r in rows],
                         [("in", 36041, "transfer", "tahsilat"), ("in", 771000, "diger", "tahsilat"),
                          ("out", 207041, "ic_transfer", "")])
        self.assertEqual(rows[0]["account"], "QNB Bereketli Ticari Hesap")  # same account as the dailies

    def test_daily_and_kmh_rows_get_the_same_key(self):
        daily = money_ledger._qnb_row(date(2026, 7, 31), ["Mevduat İşlemleri - Faiz Tahakkuku"], -785, "A")
        kmh = money_ledger._qnb_row(date(2026, 7, 31), ["Faiz Tahakkuku"], -785, "A")
        self.assertEqual(money_ledger.key_of(daily["party"]), money_ledger.key_of(kmh["party"]))

    def test_company_card_payments_have_one_name(self):
        text = QNB_DAILY.replace("Transfer İşlemleri - Alıcı: SİNEM AĞCA Sorgu No: 4047099",
                                 "Kart İşlemleri - 3901 ile biten QNB KOBİ kart ödemesi")
        self.assertEqual(money_ledger.parse_statement(text)[1]["party"], "QNB kredi kartı ödemesi ****3901")
        self.assertEqual(money_ledger.parse_statement(text)[1]["category"], "kart_borcu")

    def test_empty_company_statement_has_no_movement(self):
        text = ("Moy Danışmanlık A.ş. Enpara Şirketim Günlük Hesap 0,00 TL\nFirmanızın Eylül - 2026 döneminde Enpara "
                "Şirketim Günlük hesabına ait hareketi bulunmamaktadır.\n09/10/2026 itibarıyla SWIFT ücreti 1.500,00 TL")
        self.assertEqual(money_ledger.parse_statement(text), [])

    def test_personal_statements_still_use_the_old_reader(self):
        self.assertTrue(money_ledger.parse_statement(SCREENSHOT, TODAY))


if __name__ == "__main__":
    unittest.main()
