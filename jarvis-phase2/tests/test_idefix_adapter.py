import base64
import json
import unittest
from unittest.mock import patch

from jarvis import pazaryeri


class IdefixAdapterTests(unittest.TestCase):
    @patch("jarvis.pazaryeri._istek")
    @patch("jarvis.pazaryeri.env_oku")
    def test_reads_official_shipment_endpoint_and_maps_order(self, env_oku, istek):
        env_oku.return_value = {
            "IDEFIX_API_KEY": "api-key",
            "IDEFIX_API_SECRET": "api-secret",
            "IDEFIX_SELLER_ID": "vendor-7",
        }
        istek.return_value = json.dumps({"items": [{
            "id": 710, "orderNumber": "IDE-710", "status": "shipment_ready",
            "orderDate": "2026-11-05T10:00:00+03:00", "totalPrice": 150,
            "discountedTotalPrice": 140, "customerContactName": "Test Buyer",
            "shippingAddress": {"city": "İstanbul"},
            "cargoCompany": "Yurtiçi Kargo",
            "items": [{"productName": "Vireon", "barcode": "8690001"}],
        }]}).encode()

        result = pazaryeri.idefix()

        self.assertEqual(len(result), 1)
        order = result[0]
        self.assertEqual((order.kanal, order.siparis_no, order.paket_no),
                         ("idefix", "IDE-710", "710"))
        self.assertEqual((order.durum, order.tutar, order.musteri_ad, order.sehir),
                         ("shipment_ready", 140.0, "Test Buyer", "İstanbul"))
        self.assertEqual(order.kalemler, [{"ad": "Vireon", "adet": 1, "barkod": "8690001"}])
        url, headers = istek.call_args.args
        self.assertTrue(url.startswith("https://merchantapi.idefix.com/oms/vendor-7/list?"))
        self.assertEqual(headers["X-API-KEY"], base64.b64encode(b"api-key:api-secret").decode())

    @patch("jarvis.pazaryeri.env_oku", return_value={"IDEFIX_API_KEY": ""})
    def test_missing_credentials_keep_channel_closed(self, _env_oku):
        with self.assertRaises(pazaryeri.KanalKapali):
            pazaryeri.idefix()


if __name__ == "__main__":
    unittest.main()
