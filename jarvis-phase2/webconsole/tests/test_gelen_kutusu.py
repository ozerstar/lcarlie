# -*- coding: utf-8 -*-
"""Gelen kutusu: devir durumu yazma yolunun testleri.

🔴 BU TESTLER BIR KUSURDAN DOGDU. `durum_yaz` ilk halinde
`SELECT row_to_json(x) FROM (UPDATE ... RETURNING) x` uretiyordu.
PostgreSQL veri degistiren ifadeyi alt sorguda kabul etmez; yalniz CTE
icinde kabul eder. Okuma yollarinin hepsi calistigi icin kusur ancak
URETIMDE YAZMA denendiginde gorundu. Hic denenmeseydi panel kurulmus
sayilacakti ve devir dugmesi ilk tiklamada patlayacakti.

Testler veritabani ISTEMEZ: `_calistir` degistirilerek uretilen SQL
yakalanir ve bicimi denetlenir.
"""
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

import gelen_kutusu as GK  # noqa: E402


class SQLYakalayan:
    """`_calistir` yerine gecer: SQL'i saklar, sahte satir dondurur."""

    def __init__(self, donus=None):
        self.sorgular = []
        self.donus = donus if donus is not None else [
            {"id": 1, "devir_durumu": "JARVIS", "devir_sebep": None,
             "devir_zaman": "2026-10-15T00:00:00+03:00"}]

    def __call__(self, sql):
        self.sorgular.append(sql)
        return self.donus


class DevirYazmaSQLiCTEdir(unittest.TestCase):
    def setUp(self):
        self.gercek = GK._calistir
        self.yakala = SQLYakalayan()
        GK._calistir = self.yakala

    def tearDown(self):
        GK._calistir = self.gercek

    def test_update_CTE_icinde_alt_sorguda_DEGIL(self):
        GK.durum_yaz(1, "JARVIS")
        sql = self.yakala.sorgular[0]
        sade = " ".join(sql.split())
        self.assertIn("WITH", sade,
                      "UPDATE bir CTE icinde olmali; alt sorguda PostgreSQL reddeder")
        self.assertNotIn("FROM ( UPDATE", sade,
                         "veri degistiren ifade alt sorguya konmus")

    def test_gecersiz_durum_veritabanina_GITMEZ(self):
        with self.assertRaises(GK.KutuHatasi):
            GK.durum_yaz(1, "SACMA")
        self.assertEqual(self.yakala.sorgular, [],
                         "gecersiz durum icin sorgu uretilmemeli")

    def test_tirnak_kacirilir(self):
        GK.durum_yaz(1, "INSANDA", "O'Brien")
        self.assertIn("'O''Brien'", self.yakala.sorgular[0])

    def test_konusma_yoksa_hata(self):
        GK._calistir = SQLYakalayan(donus=[])
        with self.assertRaises(GK.KutuHatasi):
            GK.durum_yaz(999999, "JARVIS")


class SuzgecDOGRULANIR(unittest.TestCase):
    def setUp(self):
        self.gercek = GK._calistir
        self.yakala = SQLYakalayan(donus=[])
        GK._calistir = self.yakala

    def tearDown(self):
        GK._calistir = self.gercek

    def test_gecersiz_durum_suzgeci_reddedilir(self):
        with self.assertRaises(GK.KutuHatasi):
            GK.konusmalar(durum="SACMA")

    def test_limit_ustten_sinirlanir(self):
        GK.konusmalar(limit=99999)
        self.assertIn("LIMIT 200", self.yakala.sorgular[0])

    def test_bozuk_limit_varsayilana_duser(self):
        GK.konusmalar(limit="abc")
        self.assertIn("LIMIT %d" % GK.VARSAYILAN_LIMIT, self.yakala.sorgular[0])


if __name__ == "__main__":
    unittest.main()
