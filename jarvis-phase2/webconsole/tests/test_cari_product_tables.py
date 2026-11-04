"""Financial presentation: price snapshots and product totals are not balances."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cari


def entry(identifier, kind='sale', quantity=3, price='125.50', discount='0',
          recommended=None, tax='20'):
    body = {'kind': kind, 'date': '2026-10-24', 'items': [
        {'name': 'Deneme ürün', 'quantity': quantity, 'unit_price': price,
         'discount': discount, 'tax_rate': tax}]}
    if recommended is not None:
        body['items'][0]['recommended_price'] = recommended
    return {'id': identifier, 'payload': cari.calculate(body)}


class CariProductTableTests(unittest.TestCase):
    def test_reference_price_is_optional_and_does_not_change_money_or_tax(self):
        old = entry('old')['payload']
        priced = entry('priced', recommended='500.25')['payload']
        self.assertNotIn('recommended_price_cents', old['items'][0])
        self.assertEqual(priced['items'][0]['recommended_price_cents'], 50025)
        self.assertEqual((old['net_cents'], old['tax_cents'], old['signed_cents']),
                         (priced['net_cents'], priced['tax_cents'], priced['signed_cents']))
        blank = entry('blank', recommended='')['payload']
        self.assertEqual(old, blank)

    def test_reference_price_validation_and_explicit_zero(self):
        self.assertEqual(entry('zero', recommended='0')['payload']['items'][0]
                         ['recommended_price_cents'], 0)
        for price in (True, -1, 'NaN', '1e4', '12.345', '9999999999999'):
            with self.subTest(price=price), self.assertRaises(cari.CariError):
                entry('bad', recommended=price)

    def test_return_reduces_sales_quantity_and_price_snapshot_total(self):
        result = cari.product_tables([entry('sale'), entry('return', 'sale_return', quantity=1)])
        self.assertEqual((result['sale']['quantity'], result['sale']['net_cents']), (2, 25100))
        self.assertEqual(result['sale']['rows'][0]['discounted_unit_price_cents'], 12550)
        self.assertIsNone(result['sale']['rows'][0]['recommended_price_cents'])

    def test_reversed_documents_and_their_reversals_disappear_from_table(self):
        sale = entry('sale')
        reversal = dict(sale, id='reversal', reverses='sale')
        data = cari.product_tables([sale, reversal])['sale']
        self.assertEqual(data, {'rows': [], 'quantity': 0, 'net_cents': 0})

    def test_mixed_prices_and_tax_rates_remain_separate(self):
        docs = [entry('a'), entry('b', price='200'), entry('c', tax=None),
                entry('d', recommended='500'), entry('e')]
        rows = cari.product_tables(docs)['sale']['rows']
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['quantity'], 6)
        self.assertEqual(sum(row['net_cents'] for row in rows),
                         sum(doc['payload']['net_cents'] for doc in docs))

    def test_product_total_keeps_sale_and_purchase_apart_and_ignores_collection(self):
        collection = {'id': 'cash', 'payload': cari.calculate(
            {'kind': 'collection', 'date': '2026-10-24', 'amount': '100'})}
        docs = [entry('sale'), entry('purchase', 'purchase'), collection]
        result = cari.product_tables(docs)
        self.assertEqual(result['sale']['net_cents'], 37650)
        self.assertEqual(result['purchase']['net_cents'], 37650)
        self.assertEqual(cari.summarize(docs)['balance_cents'], -10000)

    def test_rounding_preserves_document_line_total_instead_of_multiplying_display(self):
        result = cari.product_tables([entry('round', price='0.05', discount='10', tax='0')])['sale']
        self.assertEqual(result['rows'][0]['discounted_unit_price_cents'], 5)
        self.assertEqual(result['net_cents'], 14)

    def test_gifts_have_their_own_quantity_without_receivable(self):
        docs = [entry('gift', 'gift_out', price='0', tax='0'),
                entry('received', 'gift_in', quantity=1, price='0', tax='0')]
        result = cari.product_tables(docs)
        self.assertEqual((result['gift']['quantity'], result['gift']['net_cents']), (2, 0))
        self.assertEqual(result['sale']['quantity'], 0)
        self.assertEqual(cari.summarize(docs)['balance_cents'], 0)


if __name__ == '__main__':
    unittest.main()
