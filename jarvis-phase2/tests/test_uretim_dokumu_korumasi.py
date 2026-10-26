"""Test süreci üretim sohbet dökümüne yazamaz.

NEDEN VAR
20.09.2026: kullanıcı Jarvis'e sesle "Merhaba Jarvis" dedi, Jarvis
"Stub reply" diye cevap verdi -- hem Türkçe hem İngilizce soruda. Sebep
modelde değildi; iki test modülü (`test_conversation.py`,
`test_web_chat.py`) `JARVIS_STATE_DIR`'i izole etmediği için fixture'ları
ÜRETİM dökümüne yazılmıştı: 383 satırın 369'u test verisiydi.
`conversation_memory.history()` son turları modele bağlam olarak verir,
model de geçmişte "stub reply" dediğini görüp taklit etti.

Sızıntı tamamen sessizdi: hata yok, uyarı yok, yalnız bozulan cevaplar.
Tek görünür iz, dökümü elle okumaktı.

Bu testler kapının GERÇEKTEN kapandığını ölçer. "Yeşil test hiçbir şeye
bakmamış olabilir" dersi gereği, ayrıca izinli yolun hâlâ AÇIK olduğu da
sınanır -- yoksa her şeyi yasaklayan bir kapı da bu testi geçerdi.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]


def _modulu_yukle(state_dir: str):
    """conversation_memory'yi verilen STATE_DIR ile yeniden yükler.

    STATE_DIR modül seviyesinde bir kez okunuyor; bu testin ölçtüğü şey
    zaten tam olarak o okuma, bu yüzden reload şart.
    """
    onceki = os.environ.get("JARVIS_STATE_DIR")
    os.environ["JARVIS_STATE_DIR"] = state_dir
    try:
        import jarvis.conversation_memory as cm
        return importlib.reload(cm)
    finally:
        if onceki is None:
            os.environ.pop("JARVIS_STATE_DIR", None)
        else:
            os.environ["JARVIS_STATE_DIR"] = onceki


class UretimDizininiKorur(unittest.TestCase):
    """unittest yüklüyken üretim dizinine yazma yasak."""

    def setUp(self):
        # Other legacy test modules replace sys.argv globally. This guard
        # must test the actual unittest entry point independent of order.
        previous_argv = sys.argv
        sys.argv = ["python -m unittest"]
        self.addCleanup(setattr, sys, "argv", previous_argv)
        # Bu suite bittiğinde modül geçici bir dizine bağlı kalsın ki
        # sonraki testler kazara üretime bakmasın.
        self.addCleanup(_modulu_yukle, tempfile.mkdtemp(prefix="jarvis-test-"))

    def test_uretim_dizininde_record_GURULTULU_patlar(self):
        cm = _modulu_yukle(str(cm_uretim_yolu()))
        with self.assertRaises(cm.UretimDokumuneTestYazamaz):
            cm.record("test sorusu", "stub reply")

    def test_uretim_dizininde_remember_GURULTULU_patlar(self):
        cm = _modulu_yukle(str(cm_uretim_yolu()))
        with self.assertRaises(cm.UretimDokumuneTestYazamaz):
            cm.remember("test notu")

    def test_uretim_dizininde_forget_GURULTULU_patlar(self):
        cm = _modulu_yukle(str(cm_uretim_yolu()))
        with self.assertRaises(cm.UretimDokumuneTestYazamaz):
            cm.forget("test")

    def test_hata_NE_YAPILACAGINI_soyler(self):
        """Patlayan testi düzeltecek kişi, sebebi tahmin etmek zorunda
        kalmamalı -- mesaj çözümü içermeli."""
        cm = _modulu_yukle(str(cm_uretim_yolu()))
        with self.assertRaises(cm.UretimDokumuneTestYazamaz) as yakala:
            cm.record("x", "y")
        mesaj = str(yakala.exception)
        self.assertIn("JARVIS_STATE_DIR", mesaj)
        self.assertIn("ÖNCE", mesaj)

    def test_OKUMA_yasak_degil(self):
        """Yasak yalnız YAZMA. Okuma yasaklansaydı testler üretimin
        gerçek durumunu hiç göremezdi ve kapı fazla geniş olurdu."""
        cm = _modulu_yukle(str(cm_uretim_yolu()))
        self.assertIsInstance(cm.notes(), list)     # patlamamalı
        self.assertIsInstance(cm.history(), list)
        self.assertIsInstance(cm.status(), dict)


class IzinliYolAcikKalir(unittest.TestCase):
    """Pozitif kontrol: kapı her şeyi yasaklamıyor, yalnız o tek şeyi."""

    def setUp(self):
        self.gecici = tempfile.mkdtemp(prefix="jarvis-test-")
        self.cm = _modulu_yukle(self.gecici)
        self.addCleanup(_modulu_yukle, tempfile.mkdtemp(prefix="jarvis-test-"))

    def test_gecici_dizine_yazma_calisir(self):
        self.cm.record("soru", "cevap")
        self.assertEqual(self.cm.status()["turns"], 1)

    def test_gecici_dizine_not_yazilir(self):
        self.assertTrue(self.cm.remember("bir not"))
        self.assertEqual(self.cm.notes(), ["bir not"])

    def test_yazilan_yer_gercekten_gecici_dizin(self):
        """Yazdı diyor ama nereye? Üretim dosyasına dokunmadığı ölçülür."""
        self.cm.record("soru", "cevap")
        yazilan = self.cm._path("operator", "turns")
        self.assertTrue(str(yazilan).startswith(self.gecici), yazilan)


def cm_uretim_yolu() -> Path:
    """Modülün üretim saydığı dizin -- sabit yazmak yerine ondan sorulur."""
    import jarvis.conversation_memory as cm
    return cm._VARSAYILAN_STATE


if __name__ == "__main__":
    unittest.main()
