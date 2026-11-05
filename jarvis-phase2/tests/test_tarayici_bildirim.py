"""Başarısız tarayıcı işi onay kuyruğuna girmez (sahip 05.11.2026).

"Başarısız olmuş işin neyini onaylayacağım?" -- onaylanacak eylem yoktur.
Başarısızlık bildirim olur; onay kuyruğu karar isteyen işlere kalır.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

YOL = Path(__file__).resolve().parents[1] / "scripts" / "tarayici-dongu.py"


def _yukle():
    spec = importlib.util.spec_from_file_location("tarayici_dongu", YOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


td = _yukle()


def _is(durum, hata=None):
    return {"is_id": 21, "hedef": "chatgpt_image", "isteyen": "tasarim-departmani",
            "durum": durum, "hata": hata, "deneme": 2, "istem": "IMAGE 1 = ürün fotoğrafı",
            "sonuc_metin": "", "sonuc_dosyalari": []}


class BasarisizIsOnayaGirmez(unittest.TestCase):
    def setUp(self):
        self.gecici = Path(tempfile.mkdtemp())
        self.yamalar = [mock.patch.object(td, "DURUM_KOK", self.gecici),
                        mock.patch.object(td, "yedek_dene", return_value=None),
                        mock.patch.object(td, "dosyalari_tasi", return_value=[]),
                        mock.patch.object(td, "alarm"),
                        mock.patch.object(td.tarayici, "_psql"),
                        mock.patch.object(td.subprocess, "run")]
        self.mocklar = [y.start() for y in self.yamalar]

    def tearDown(self):
        for y in self.yamalar:
            y.stop()

    def test_hata_onay_gorevi_acmaz_bildirim_yazar(self):
        sonuc = td.sonucu_sun(_is("HATA", "HandlerHatasi: gorsel uretilmedi (300 sn beklendi)"))
        self.assertTrue(sonuc["bildirim"])
        td.subprocess.run.assert_not_called()          # create-task YOK
        td.tarayici._psql.assert_called_once()          # iş yine SUNULDU işaretlenir
        kayit = json.loads((self.gecici / "tarayici-21.json").read_text(encoding="utf-8"))
        govde = kayit["bildirim"]["govde"]
        self.assertIn("görsel 5 dakika içinde üretilmedi", govde)
        self.assertIn("Onay gerekmez", govde)
        for kirli in ("HandlerHatasi", "300 sn", "chatgpt_image"):
            self.assertNotIn(kirli, govde)

    def test_insan_gerekli_de_onaya_girmez(self):
        self.assertTrue(td.sonucu_sun(_is("INSAN_GEREKLI", "oturum kapali"))["bildirim"])
        td.subprocess.run.assert_not_called()

    def test_tamamlanan_is_de_onaya_girmez_kreatife_yonlendirir(self):
        """Sonuçlar artık Kreatif > Tarayıcı sonuçları'nda görünür; onay kuyruğu karar içindir."""
        with mock.patch.object(td, "dosyalari_tasi", return_value=["gorsel-1.png", "gorsel-2.png", "ekran-21.png"]):
            sonuc = td.sonucu_sun(_is("BITTI"))
        td.subprocess.run.assert_not_called()
        td.alarm.assert_not_called()                     # başarı alarm değildir
        self.assertEqual(sonuc["dosya_adedi"], 2)
        kayit = json.loads((self.gecici / "tarayici-21.json").read_text(encoding="utf-8"))
        self.assertIn("2 görsel hazır", kayit["bildirim"]["govde"])
        self.assertIn("Kreatif", kayit["bildirim"]["govde"])


if __name__ == "__main__":
    unittest.main()
