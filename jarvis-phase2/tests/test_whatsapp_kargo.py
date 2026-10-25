import unittest

from jarvis import whatsapp_kargo


class SahteKargo:
    def __init__(self, items, has_more=False):
        self.items = items
        self.has_more = has_more
        self.calls = []

    def cagir(self, tool, args):
        self.calls.append((tool, args))
        return {"veri": {"items": self.items, "hasMore": self.has_more}}


def gonderi(phone="0555 123 45 67", status="SHIPPED", order="ORDER-1"):
    return {"type": "OUTGOING", "status": status, "orderNumber": order,
            "recipient": {"phone": phone},
            "shipmentInfo": {"handler": {"name": "Aras"}}}


class DogrulanmisKargo(unittest.TestCase):
    def test_tam_telefon_eslesirse_durum_verir(self):
        api = SahteKargo([gonderi()])
        metin, devir = whatsapp_kargo.durum_sor("905551234567", api=api)
        self.assertFalse(devir)
        self.assertIn("Kargoya verildi", metin)
        self.assertEqual(api.calls[0][1]["keyword"], "905551234567")

    def test_baska_telefonun_kargosunu_aciklamaz(self):
        metin, devir = whatsapp_kargo.durum_sor(
            "905551234567", api=SahteKargo([gonderi(phone="0555 000 00 00")]))
        self.assertTrue(devir)
        self.assertNotIn("Kargoya verildi", metin)

    def test_birden_cok_gonderide_siparis_numarasi_ister(self):
        metin, devir = whatsapp_kargo.durum_sor(
            "905551234567", api=SahteKargo([gonderi(), gonderi(order="ORDER-2")]))
        self.assertFalse(devir)
        self.assertIn("Sipariş numaranızı", metin)

    def test_siparis_numarasi_telefonla_birlikte_dogrulanir(self):
        metin, devir = whatsapp_kargo.durum_sor(
            "905551234567", "ORDER-2", api=SahteKargo([
                gonderi(order="ORDER-1"), gonderi(order="ORDER-2")]))
        self.assertFalse(devir)
        self.assertIn("Kargoya verildi", metin)

    def test_bilinmeyen_durumu_uydurmaz(self):
        metin, devir = whatsapp_kargo.durum_sor(
            "905551234567", api=SahteKargo([gonderi(status="UNKNOWN")]))
        self.assertTrue(devir)
        self.assertIn("doğrulayamadım", metin)

    def test_dogrulanmis_kargo_takip_numarasini_verir(self):
        kayit = gonderi()
        kayit["shipmentInfo"]["handlerShipmentCode"] = "TR12345"
        metin, devir = whatsapp_kargo.durum_sor("905551234567", api=SahteKargo([kayit]))
        self.assertFalse(devir)
        self.assertIn("Takip numaranız: TR12345", metin)


if __name__ == "__main__":
    unittest.main()
