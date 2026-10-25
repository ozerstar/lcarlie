import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DOSYA = Path(__file__).resolve().parent.parent / "scripts" / "whatsapp_oto_yanit.py"
SPEC = importlib.util.spec_from_file_location("whatsapp_oto_yanit", DOSYA)
MODUL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODUL)


class OtomatikYanitTesti(unittest.TestCase):
    def test_uzayan_claim_gonderim_kaydiyla_eslesirse_tekrarlamaz(self):
        with tempfile.TemporaryDirectory() as directory:
            defter = Path(directory) / "send.jsonl"
            defter.write_text(json.dumps({"kaynak_mesaj_id": 17,
                                          "sonuc": "GONDERILDI", "wamid": "wamid.x"}) + "\n")
            with patch.object(MODUL.whatsapp, "DEFTER", defter), \
                 patch.object(MODUL, "uzayan_claimler", return_value=[{
                     "mesaj_id": 17, "konusma_id": 9, "devir_durumu": "JARVIS",
                     "son_mesaj": True,
                 }]), patch.object(MODUL, "bitir") as bitir, \
                 patch.object(MODUL.whatsapp, "gonder") as gonder:
                MODUL.uzayanlari_incele()
                bitir.assert_called_once_with(17, "sent", "wamid.x")
                gonder.assert_not_called()

    def test_uzayan_claim_kanitsizsa_insana_devredilir(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODUL.whatsapp, "DEFTER", Path(directory) / "yok"), \
                 patch.object(MODUL, "uzayan_claimler", return_value=[{
                     "mesaj_id": 17, "konusma_id": 9, "devir_durumu": "JARVIS",
                     "son_mesaj": True,
                 }]), patch.object(MODUL, "bitir") as bitir, \
                 patch.object(MODUL.gelen_kutusu, "_calistir") as db, \
                 patch.object(MODUL.whatsapp, "gonder") as gonder:
                MODUL.uzayanlari_incele()
                bitir.assert_called_once_with(17, "uncertain", "")
                self.assertIn("OTOMATIK_YANIT_BELIRSIZ", db.call_args.args[0])
                gonder.assert_not_called()

    def test_gonderim_hatasi_otomatik_tekrar_gondermez(self):
        with patch.object(MODUL, "sahiplen", return_value=True), \
             patch.object(MODUL, "hala_son", return_value=True), \
             patch.object(MODUL.gelen_kutusu, "taslak", return_value={
                 "sinif": "KARGO_TAKIP", "devredilmeli": False,
                 "uretildi": True, "gonderilebilir": True, "metin": "Hazırlanıyor",
             }), patch.object(MODUL.gelen_kutusu, "telefon_bul", return_value="905550000000"), \
             patch.object(MODUL.whatsapp, "gonder", side_effect=RuntimeError("network")) as gonder, \
             patch.object(MODUL, "gonderim_kaydi", return_value=None), \
             patch.object(MODUL, "bitir") as bitir, \
             patch.object(MODUL.gelen_kutusu, "durum_yaz") as devret:
            sonuc = MODUL.isle({"mesaj_id": 17, "konusma_id": 9},
                                "2026-10-15T00:00:00+03:00")
        self.assertEqual(sonuc, "uncertain_handoff")
        bitir.assert_called_once_with(17, "uncertain", "")
        devret.assert_called_once()
        gonder.assert_called_once()

    def test_aktif_sohbette_her_tetikte_tarar(self):
        with patch.object(MODUL, "aktif_sohbet_var", return_value=True), \
             patch.object(MODUL, "IDLE_SCAN_MARKER", Path("/nonexistent/idle-marker")):
            self.assertTrue(MODUL.tarama_gerekli())

    def test_bosken_dakikada_bir_tarar(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "idle"
            with patch.object(MODUL, "IDLE_SCAN_MARKER", marker), \
                 patch.object(MODUL, "aktif_sohbet_var", return_value=False), \
                 patch.object(MODUL.time, "time", return_value=1000):
                self.assertTrue(MODUL.tarama_gerekli())
                MODUL.bos_tarama_kaydet()
                self.assertFalse(MODUL.tarama_gerekli())
            os.utime(marker, (900, 900))
            with patch.object(MODUL, "IDLE_SCAN_MARKER", marker), \
                 patch.object(MODUL, "aktif_sohbet_var", return_value=False), \
                 patch.object(MODUL.time, "time", return_value=1000):
                self.assertTrue(MODUL.tarama_gerekli())

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
