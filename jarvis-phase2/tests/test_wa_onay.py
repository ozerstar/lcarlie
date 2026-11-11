# -*- coding: utf-8 -*-
"""WhatsApp onay hattının kapıları.

🔴 BU TESTLER AĞA ÇIKMAZ. Karar ve gönderim taklit edilir; testler yanlış
düğmenin karar VERMEDİĞİNİ ve ilk koşunun toplu mesaj ATMADIĞINI kanıtlar.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis import whatsapp

DOSYA = Path(__file__).resolve().parent.parent / "scripts" / "wa-onay.py"
SPEC = importlib.util.spec_from_file_location("wa_onay", DOSYA)
MODUL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODUL)

NONCE = "0123456789abcdef"
IZ = "a" * 64


def durum(**kayit):
    temel = {"durum": "gonderildi", "nonce": NONCE, "parmak_izi": IZ,
             "konu_ref": "2026-11-11.AI_OPS.x", "konu": "KURUL KARARI · AI_OPS"}
    temel.update(kayit)
    return {"oneriler": {"167": temel}}


def operator(parmak_izi=IZ, bekliyor=True, onaylandi=True):
    op = MagicMock()
    op.inspect.return_value = {"action_id": 167, "fingerprint": parmak_izi} if bekliyor else None
    op.decide.return_value = {"confirmed": onaylandi}
    return op


class KararTesti(unittest.TestCase):
    def test_dogru_dugme_parmak_iziyle_onaylar(self):
        op, d = operator(), durum()
        sonuc, cevap = MODUL.karar_ver(op, d, f"onay:167:{NONCE}")
        self.assertEqual(sonuc, "APPROVED")
        op.decide.assert_called_once_with(167, "APPROVED", "WhatsApp düğmesi (sahip)",
                                          expected_hash=IZ)
        self.assertEqual(d["oneriler"]["167"]["durum"], "karar:APPROVED")
        self.assertIn("onaylandı", cevap)

    def test_red_dugmesi_reddeder(self):
        op = operator()
        sonuc, _ = MODUL.karar_ver(op, durum(), f"red:167:{NONCE}")
        self.assertEqual(sonuc, "REJECTED")
        self.assertEqual(op.decide.call_args[0][1], "REJECTED")

    def test_yanlis_nonce_karar_vermez(self):
        op = operator()
        sonuc, _ = MODUL.karar_ver(op, durum(), "onay:167:ffffffffffffffff")
        self.assertEqual(sonuc, "nonce_tutmadi")
        op.decide.assert_not_called()

    def test_bilinmeyen_oneri_karar_vermez(self):
        op = operator()
        sonuc, _ = MODUL.karar_ver(op, durum(), f"onay:999:{NONCE}")
        self.assertEqual(sonuc, "nonce_tutmadi")
        op.decide.assert_not_called()

    def test_yazi_ile_onay_karar_vermez(self):
        op = operator()
        for yuk in ("Onayla", "onay:167", "onay:167:" + NONCE + "x", ""):
            self.assertEqual(MODUL.karar_ver(op, durum(), yuk)[0], "gecersiz")
        op.decide.assert_not_called()

    def test_degisen_oneri_karar_vermez(self):
        op = operator(parmak_izi="b" * 64)
        self.assertEqual(MODUL.karar_ver(op, durum(), f"onay:167:{NONCE}")[0], "degisti")
        op.decide.assert_not_called()

    def test_panelde_karara_baglanmis(self):
        op = operator(bekliyor=False)
        self.assertEqual(MODUL.karar_ver(op, durum(), f"onay:167:{NONCE}")[0], "bekleyen_degil")
        op.decide.assert_not_called()

    def test_ikinci_basis_tekrar_karar_vermez(self):
        op, d = operator(), durum()
        MODUL.karar_ver(op, d, f"onay:167:{NONCE}")
        self.assertEqual(MODUL.karar_ver(op, d, f"red:167:{NONCE}")[0], "tekrar")
        self.assertEqual(op.decide.call_count, 1)

    def test_kreatif_brief_whatsapptan_onaylanmaz(self):
        op = operator()
        d = durum(konu_ref="kreatif-brief:hafta-46")
        self.assertEqual(MODUL.karar_ver(op, d, f"onay:167:{NONCE}")[0], "panel_gerekli")
        op.decide.assert_not_called()

    def test_dogrulanamayan_karar_basarili_sayilmaz(self):
        op, d = operator(onaylandi=False), durum()
        self.assertEqual(MODUL.karar_ver(op, d, f"onay:167:{NONCE}")[0], "dogrulanamadi")
        self.assertEqual(d["oneriler"]["167"]["durum"], "gonderildi")


class GonderimTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.yama = patch.object(MODUL, "DURUM", Path(self.klasor.name) / "wa-onay.json")
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.klasor.cleanup()

    def bekleyen(self, *kimlikler):
        return [{"action_id": k, "action_type": "REQUEST_HUMAN_REVIEW", "fingerprint": IZ,
                 "payload": {"reason": "KURUL KARARI · AI_OPS\n\nMatrisi onaylamak\n\nDayanak: x",
                             "subject_ref": "s"}} for k in kimlikler]

    def test_ilk_kosu_toplu_mesaj_atmaz(self):
        op = MagicMock()
        op.list_pending.return_value = self.bekleyen(1, 2, 3)
        with patch.object(MODUL.whatsapp, "gonderme_acik", return_value=True), \
             patch.object(MODUL, "OperatorSession", return_value=op), \
             patch.object(MODUL.whatsapp, "sablon_gonder") as gonder:
            MODUL.main()
        gonder.assert_not_called()
        kayit = json.loads(MODUL.DURUM.read_text(encoding="utf-8"))
        self.assertEqual(sorted(kayit["oneriler"]), ["1", "2", "3"])

    def test_yeni_oneri_dugmeli_gider_ve_bir_kez_gider(self):
        op = MagicMock()
        op.list_pending.return_value = self.bekleyen(7)
        d = {"oneriler": {}}
        with patch.object(MODUL.whatsapp, "sablon_gonder",
                          return_value={"wamid": "wamid.x"}) as gonder:
            MODUL.yenileri_gonder(op, d)
            MODUL.yenileri_gonder(op, d)
        self.assertEqual(gonder.call_count, 1)
        degerler = gonder.call_args[0][2]
        self.assertEqual(degerler, ["#7", "KURUL KARARI · AI_OPS", "Matrisi onaylamak"])
        nonce = d["oneriler"]["7"]["nonce"]
        self.assertEqual(gonder.call_args[1]["dugme_yukleri"],
                         [f"onay:7:{nonce}", f"red:7:{nonce}"])
        self.assertTrue(MODUL.YUK.match(f"onay:7:{nonce}"))

    def test_mevzuat_takilirsa_ozetsiz_gider(self):
        op = MagicMock()
        op.list_pending.return_value = self.bekleyen(8)
        d = {"oneriler": {}}
        with patch.object(MODUL.whatsapp, "sablon_gonder", side_effect=[
                whatsapp.GondermeReddedildi("mevzuat kapisi: 1 bulgu"),
                {"wamid": "wamid.y"}]) as gonder:
            MODUL.yenileri_gonder(op, d)
        self.assertEqual(gonder.call_args[0][2][2], MODUL.MEVZUAT_YEDEK)
        self.assertEqual(d["oneriler"]["8"]["durum"], "gonderildi")

    def test_meta_hatasi_hemen_yeniden_denenmez(self):
        op = MagicMock()
        op.list_pending.return_value = self.bekleyen(9)
        d = {"oneriler": {}}
        with patch.object(MODUL.whatsapp, "sablon_gonder",
                          side_effect=whatsapp.GondermeReddedildi("Meta HTTP 404")) as gonder:
            MODUL.yenileri_gonder(op, d)
            MODUL.yenileri_gonder(op, d)
        self.assertEqual(gonder.call_count, 1)
        self.assertEqual(d["oneriler"]["9"]["durum"], "hata")


class SablonDugmeTesti(unittest.TestCase):
    def test_dugme_bileseni(self):
        self.assertEqual(whatsapp.dugme_bilesenleri(["onay:1:x", "red:1:x"]), [
            {"type": "button", "sub_type": "quick_reply", "index": "0",
             "parameters": [{"type": "payload", "payload": "onay:1:x"}]},
            {"type": "button", "sub_type": "quick_reply", "index": "1",
             "parameters": [{"type": "payload", "payload": "red:1:x"}]}])

    def test_sahip_otomatik_musteri_cevabindan_dislanir(self):
        kaynak = (Path(__file__).resolve().parent.parent / "scripts"
                  / "whatsapp_oto_yanit.py").read_text(encoding="utf-8")
        self.assertIn("k.harici_id <> {gelen_kutusu._tirnak(SAHIP_TELEFON)}", kaynak)


if __name__ == "__main__":
    unittest.main()
