import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

DOSYA = Path(__file__).resolve().parent.parent / "scripts" / "whatsapp_oto_yanit.py"
SPEC = importlib.util.spec_from_file_location("whatsapp_oto_yanit", DOSYA)
MODUL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODUL)


class OtomatikYanitTesti(unittest.TestCase):
    def test_devir_yanitlari_sonra_insana_gider(self):
        for sinif in ("SAGLIK", "SIKAYET", "ANLASILMADI"):
            with self.subTest(sinif=sinif):
                self.assertEqual(MODUL.yanit_plani({
                    "sinif": sinif, "devredilmeli": True, "metin": "Taslak",
                }), (True, True))

    def test_durdurma_ve_engelli_icerik_gonderilmez(self):
        self.assertEqual(MODUL.yanit_plani({
            "sinif": "DURDURMA", "devredilmeli": True, "metin": "Taslak",
        }), (False, True))
        self.assertEqual(MODUL.yanit_plani({
            "sinif": "IDDIA_SORUSU", "devredilmeli": True, "metin": "",
        }), (False, True))
        self.assertEqual(MODUL.yanit_plani({
            "sinif": "FIYAT", "devredilmeli": False,
            "uretildi": True, "gonderilebilir": False, "metin": "Taslak",
        }), (False, True))

    def test_dogrulanmis_cevap_jarviste_kalir(self):
        self.assertEqual(MODUL.yanit_plani({
            "sinif": "ODEME_YONLENDIR", "devredilmeli": False,
            "uretildi": True, "gonderilebilir": True, "metin": "Ürün sayfası",
        }), (True, False))

    def test_anahtar_kapaliysa_veritabanina_bile_bakmaz(self):
        with patch.dict(os.environ, {"JARVIS_WHATSAPP_AUTO_REPLY": "0"}):
            with patch.object(MODUL, "adaylar") as adaylar:
                MODUL.main()
                adaylar.assert_not_called()

    def test_tekrar_claim_engellenirse_gondermez(self):
        with patch.object(MODUL, "sahiplen", return_value=False):
            with patch.object(MODUL.whatsapp, "gonder") as gonder:
                self.assertEqual(MODUL.isle({"mesaj_id": 1, "konusma_id": 2},
                                            "2026-10-15T00:00:00+03:00"), "atlandi")
                gonder.assert_not_called()

    def test_sikayet_cevaplanir_ve_sahibe_devredilir(self):
        with patch.object(MODUL, "sahiplen", return_value=True), \
             patch.object(MODUL, "hala_son", return_value=True), \
             patch.object(MODUL.gelen_kutusu, "taslak", return_value={
                 "sinif": "SIKAYET", "devredilmeli": True,
                 "metin": "Özür dileriz.", "sebep": "SAGLIK_SIKAYET",
             }), \
             patch.object(MODUL.gelen_kutusu, "telefon_bul", return_value="905550000000"), \
             patch.object(MODUL.whatsapp, "gonder", return_value={"wamid": "wamid.test"}) as gonder, \
             patch.object(MODUL.gelen_kutusu, "durum_yaz") as devret, \
             patch.object(MODUL, "bitir") as bitir:
            sonuc = MODUL.isle({"mesaj_id": 1, "konusma_id": 2},
                                "2026-10-15T00:00:00+03:00")
            self.assertEqual(sonuc, "sent_handoff")
            self.assertEqual(gonder.call_args.kwargs["onay_kaynagi"],
                             MODUL.whatsapp.ONAY_OTOMATIK)
            devret.assert_called_once_with(2, "INSANDA", "SAGLIK_SIKAYET")
            bitir.assert_called_once_with(1, "sent", "wamid.test")

    def test_son_mesaj_degismisse_gondermez(self):
        with patch.object(MODUL, "sahiplen", return_value=True), \
             patch.object(MODUL, "hala_son", return_value=False), \
             patch.object(MODUL.gelen_kutusu, "taslak", return_value={
                 "sinif": "FIYAT", "devredilmeli": False,
                 "uretildi": True, "gonderilebilir": True, "metin": "Taslak",
             }), \
             patch.object(MODUL.whatsapp, "gonder") as gonder, \
             patch.object(MODUL, "bitir") as bitir:
            self.assertEqual(MODUL.isle({"mesaj_id": 1, "konusma_id": 2},
                                         "2026-10-15T00:00:00+03:00"), "stale")
            gonder.assert_not_called()
            bitir.assert_called_once_with(1, "stale")


if __name__ == "__main__":
    unittest.main()
