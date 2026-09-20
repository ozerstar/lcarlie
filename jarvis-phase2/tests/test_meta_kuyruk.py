"""Webhook kuyrugunu DB'ye aktaran betik: iki SESSIZ hata kilitleniyor.

Ikisi de 20.09.2026'da canli veriyle yakalandi ve ikisi de HATA VERMIYORDU:

1. CTE TUZAGI -- reklam referansi ayri bir CTE'de UPDATE ediliyordu.
   PostgreSQL'de ayni ifadedeki veri degistiren CTE'ler tek anlik
   goruntuyle calisir; biri digerinin yazdigi satiri GOREMEZ. Mesajlar
   yaziliyor, ad_id sessizce dusuyordu -- yani urun atamasinin tamami oluydu.

2. YALAN SAYAC -- psql `-tA` ile bile komut etiketini basiyor; catisan bir
   INSERT `INSERT 0 0` donduruyor ve bu BOS OLMAYAN bir satir. Kod buna
   bakip her tekrar calistirmada "4 mesaj yazildi" diyordu, oysa sifir
   satir yazilmisti. Kopya olusmuyordu (kisitlar tuttu) ama RAPOR YALAN
   SOYLUYORDU. Bu sinif hata bu projede bir cron'un iki gun olu kalmasini
   gizledi.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

_spec = importlib.util.spec_from_file_location(
    "meta_kuyruk_yukle", KOK / "scripts" / "meta-kuyruk-yukle.py")
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

KAYNAK = (KOK / "scripts" / "meta-kuyruk-yukle.py").read_text(encoding="utf-8")


class CteTuzagiGERI_GELMESIN(unittest.TestCase):
    def test_reklam_referansi_INSERT_in_icinde_yazilir(self):
        # ON CONFLICT DO UPDATE ile ayni ifadede cozulur; ayri bir
        # "UPDATE ... WHERE id = (SELECT id FROM k)" sessizce hicbir sey yapar.
        self.assertIn("ON CONFLICT (kanal, harici_id) DO UPDATE", KAYNAK)
        self.assertNotIn("WHERE id = (SELECT id FROM k)", KAYNAK)

    def test_tuzak_kaynakta_ACIKLANMIS(self):
        # Aciklama silinirse bir sonraki kisi ayni CTE'yi yeniden yazar.
        self.assertIn("GÖREMEZ", KAYNAK)


class SayacYALAN_SOYLEMESIN(unittest.TestCase):
    def test_yazildi_satirina_bakiliyor_dogruluk_degerine_DEGIL(self):
        self.assertIn('s.strip() == "yazildi"', KAYNAK)
        # Ciplak `if cikti:` geri gelirse sayac yine yalan soyler.
        self.assertNotIn("\n        if cikti:\n", KAYNAK)

    def test_zaten_vardi_ayri_sayiliyor(self):
        # "yazildi 0" ile "hic denenmedi" ayirt edilebilmeli.
        self.assertIn("zaten_vardi", KAYNAK)


class KuyrukOkumaDAYANIKLI(unittest.TestCase):
    def test_bozuk_satir_digerlerini_dusurmez(self):
        with tempfile.TemporaryDirectory() as gecici:
            kuyruk = Path(gecici) / "gelen.jsonl"
            kuyruk.write_text(
                json.dumps({"mesaj_id": "a"}) + "\n"
                + "{yarim kalmis\n"
                + json.dumps({"mesaj_id": "b"}) + "\n", encoding="utf-8")
            olaylar = mk.olaylari_oku(kuyruk)
            self.assertEqual([o["mesaj_id"] for o in olaylar], ["a", "b"])

    def test_dosya_yoksa_cokmez(self):
        self.assertEqual(mk.olaylari_oku(Path("/yok/olan/dosya.jsonl")), [])

    def test_kuyruk_silinmez_ARSIVLENIR(self):
        # Yukleme sonrasi bir sorun cikarsa olay elde kalsin.
        self.assertIn("shutil.move", KAYNAK)
        self.assertNotIn("os.remove(kuyruk)", KAYNAK)


class TirnakKACISI(unittest.TestCase):
    def test_tek_tirnak_ikilenir(self):
        self.assertEqual(mk._tirnak("O'Brien"), "'O''Brien'")

    def test_bos_ve_none_NULL_olur(self):
        self.assertEqual(mk._tirnak(None), "NULL")
        self.assertEqual(mk._tirnak(""), "NULL")

    def test_zaman_yoksa_uydurulmaz_simdi_kullanilir(self):
        # zaman NOT NULL; olayda yoksa alim zamani kullanilir, sifir degil.
        self.assertTrue(mk._zaman({"zaman_ms": 0}).startswith("2"))
        self.assertIn("T", mk._zaman({"zaman_ms": 1758000000000}))


if __name__ == "__main__":
    unittest.main()
