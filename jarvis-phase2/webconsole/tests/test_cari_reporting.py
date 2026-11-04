import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cari


def entry(account, identifier, kind, amount='100', when='2026-02-10', due='', reverses=None):
    body = {'kind': kind, 'date': when, 'due_date': due}
    if kind in cari.GOODS:
        body['items'] = [{'name': 'Example', 'quantity': 1, 'unit_price': amount, 'tax_rate': '0'}]
    else:
        body['amount'] = amount
    return {'account_id': account, 'entry_id': identifier, 'payload': cari.calculate(body),
            'reverses': reverses}


class PortfolioTests(unittest.TestCase):
    accounts = [{'id': 'a', 'name': 'Customer', 'role': 'customer'},
                {'id': 'b', 'name': 'Supplier', 'role': 'supplier'}]

    def report(self, rows, when='2026-02-15'):
        return cari.portfolio_from_entries(self.accounts, rows, when)

    def test_different_accounts_are_never_netted_against_one_another(self):
        result = self.report([entry('a', 's', 'sale'), entry('b', 'p', 'purchase', '80')])
        self.assertEqual(result['totals']['receivable_cents'], 10000)
        self.assertEqual(result['totals']['payable_cents'], 8000)

    def test_report_date_excludes_future_collection_and_reversal(self):
        sale = entry('a', 's', 'sale')
        future = entry('a', 'c', 'collection', when='2026-02-20')
        reversed_sale = entry('a', 'r', 'sale', when='2026-02-21', reverses='s')
        before = self.report([sale, future, reversed_sale])
        self.assertEqual(before['totals']['receivable_cents'], 10000)
        self.assertEqual(before['totals']['sales_net_cents'], 10000)
        after = self.report([sale, future, reversed_sale], '2026-02-22')
        self.assertEqual(after['totals']['payable_cents'], 10000)
        self.assertEqual(after['totals']['sales_net_cents'], 0)

    def test_reversed_cash_entry_does_not_inflate_collection_totals(self):
        rows = [entry('a', 'c', 'collection', '30'),
                entry('a', 'r', 'collection', '30', reverses='c')]
        result = self.report(rows)
        self.assertEqual(result['totals']['collections_cents'], 0)
        self.assertEqual(result['totals']['receivable_cents'], 0)
        self.assertEqual(result['totals']['payable_cents'], 0)

    def test_fully_paid_account_still_does_not_claim_specific_document_is_unpaid(self):
        rows = [entry('a', 's', 'sale', due='2026-02-11'), entry('a', 'c', 'collection')]
        result = self.report(rows)
        self.assertEqual(result['totals']['receivable_cents'], 0)
        self.assertEqual(len(result['due_reviews']), 1)
        review = result['due_reviews'][0]
        self.assertFalse(review['settlement_verified'])
        self.assertTrue(review['has_account_adjustments'])
        self.assertEqual(review['remaining_cents'], 10000)

    def test_due_today_is_not_overdue_and_reversed_document_is_not_a_candidate(self):
        rows = [entry('a', 'today', 'sale', due='2026-02-15'),
                entry('a', 'old', 'sale', due='2026-02-11'),
                entry('a', 'rev', 'sale', reverses='old')]
        due = self.report(rows)['due_reviews']
        self.assertEqual([row['entry_id'] for row in due], ['today'])
        self.assertFalse(due[0]['overdue'])

    def test_sales_and_purchases_are_net_of_returns_but_not_opening_balances(self):
        rows = [entry('a', 's', 'sale', '100'), entry('a', 'r', 'sale_return', '25'),
                entry('b', 'p', 'purchase', '90'), entry('b', 'pr', 'purchase_return', '10'),
                entry('a', 'o', 'opening_receivable', '50'), entry('b', 'pay', 'payment', '40')]
        t = self.report(rows)['totals']
        self.assertEqual(t['sales_net_cents'], 7500)
        self.assertEqual(t['purchases_net_cents'], 8000)
        self.assertEqual(t['payments_cents'], 4000)

    def test_unknown_tax_and_zero_balance_remain_explicit(self):
        row = entry('a', 's', 'sale')
        row['payload']['items'][0]['tax_rate'] = None
        row['payload']['unknown_tax'] = True
        result = self.report([row, entry('a', 'c', 'collection')])
        self.assertEqual(result['totals']['unknown_tax_documents'], 1)
        account = next(a for a in result['accounts'] if a['id'] == 'a')
        self.assertEqual(account['status'], 'KDV bekleniyor')

    def test_unmapped_accounts_are_not_included_and_dates_are_validated(self):
        result = self.report([entry('unknown', 's', 'sale')])
        self.assertEqual(result['totals']['receivable_cents'], 0)
        with self.assertRaises(cari.CariError):
            self.report([], '2026-02-30')


if __name__ == '__main__':
    unittest.main()
