"""sistem.py sozlesmesi.

Bu testlerin asil isi tek bir seyi kilitlemek: YOKLUGUN SEBEBI AYRILIR.
Bir PC'nin verisi yoksa bunun iki ayri sebebi olabilir (hic rapor
gelmemis / rapor eskimis) ve ikisini ayni cumleye cevirmek bu projede
tekrar eden bir kok hatadir. Bir de "bayat" bir raporun makinenin KAPALI
oldugunu KANITLAMADIGI -- panelin bunu iddia etmemesi gerekiyor.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sistem  # noqa: E402


class RaporTazeligi(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "hosts").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _yaz(self, ad, govde, yas_s=0):
        yol = self.state / "hosts" / (ad + ".json")
        yol.write_text(json.dumps(govde), encoding="utf-8")
        if yas_s:
            eski = time.time() - yas_s
            os.utime(yol, (eski, eski))
        return yol

    def test_dosya_yoksa_RAPOR_YOK(self):
        m = sistem._rapor_oku(self.state, "pc1")
        self.assertEqual(m["durum"], "RAPOR_YOK")
        self.assertIsNone(m["veri"])
        self.assertIn("toplayici", m["sebep"])

    def test_taze_dosya_TAZE(self):
        self._yaz("pc1", {"cpu_yuzde": 5})
        m = sistem._rapor_oku(self.state, "pc1")
        self.assertEqual(m["durum"], "TAZE")
        self.assertEqual(m["veri"]["cpu_yuzde"], 5)
        self.assertIsNone(m["sebep"])

    def test_eski_dosya_BAYAT_ama_veriyi_birakir(self):
        """Bayat rapor SILINMEZ: son bilinen deger, hicbir degerden iyidir."""
        self._yaz("pc2", {"cpu_yuzde": 71}, yas_s=sistem.BAYAT_ESIGI_S + 60)
        m = sistem._rapor_oku(self.state, "pc2")
        self.assertEqual(m["durum"], "BAYAT")
        self.assertEqual(m["veri"]["cpu_yuzde"], 71)
        self.assertGreater(m["yas_s"], sistem.BAYAT_ESIGI_S)

    def test_BAYAT_makinenin_kapali_oldugunu_IDDIA_ETMEZ(self):
        """Yoklugun sebebini bilmeden cumleye cevirmek yasak.

        "PC-2 kapali" demek bir IDDIA'dir ve elimizde onu destekleyen
        olcum yok -- itme de basarisiz olmus olabilir. Sebep metni bunu
        acikca soylemek zorunda.
        """
        self._yaz("pc2", {}, yas_s=sistem.BAYAT_ESIGI_S + 5)
        sebep = sistem._rapor_oku(self.state, "pc2")["sebep"]
        self.assertIn("kanitlamaz", sebep.lower())

    def test_bozuk_json_OKUNAMADI(self):
        (self.state / "hosts" / "pc1.json").write_text("{yarim", encoding="utf-8")
        m = sistem._rapor_oku(self.state, "pc1")
        self.assertEqual(m["durum"], "OKUNAMADI")
        self.assertIsNone(m["veri"])


class Politika(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dosya_yokken_varsayilan_okunur_ve_YAZILMAZ(self):
        p = sistem.politika_oku(self.state)
        self.assertEqual(p["kaynak"], "varsayilan")
        self.assertFalse((self.state / "kaynak_politikasi.json").exists())

    def test_sahibin_karari_varsayilan_olarak_gecerli(self):
        """PC-2'den YALNIZ ekran karti kullanilir (24.09.2026 karari)."""
        a = sistem.politika_oku(self.state)["anahtarlar"]
        self.assertTrue(a["pc2_gpu"]["acik"])
        self.assertFalse(a["pc2_cpu_ram"]["acik"])
        self.assertEqual(a["pc2_cpu_ram"]["kilit"], "ozel_izin")
        self.assertTrue(a["sunucu_cpu_ram"]["acik"])
        self.assertTrue(a["pc1_cpu_ram"]["acik"])

    def test_siralama_sunucu_pc1_pc2(self):
        self.assertEqual(sistem.politika_oku(self.state)["siralama"],
                         ["sunucu", "pc1", "pc2_gpu"])

    def test_cevirme_kalici_ve_kim_cevirdigi_yazili(self):
        sistem.politika_yaz(self.state, "pc2_cpu_ram", True, "ozer",
                            ozel_izin=True)
        a = sistem.politika_oku(self.state)["anahtarlar"]["pc2_cpu_ram"]
        self.assertTrue(a["acik"])
        self.assertEqual(a["degistiren"], "ozer")
        self.assertTrue(a["degistirildi"])
        self.assertTrue(sistem.izinli_mi(self.state, "pc2_cpu_ram"))

    def test_kilitli_anahtar_IZINSIZ_acilmaz(self):
        """Kilit sunum katmaninda degil, ZORLAYAN katmanda olmali.

        Ilk halinde 'ozel_izin' kilidi yalnizca panelin iki adimli onay
        ekraninda vardi; politika_yaz() onu hic denetlemiyordu. Panel
        disindaki her cagiran (PC-2 masaustu kisayollarini besleyen
        politika-yaz.sh dahil) kilitli anahtari tek adimda acabiliyordu.
        """
        with self.assertRaises(sistem.KilitliAnahtar):
            sistem.politika_yaz(self.state, "pc2_cpu_ram", True, "kisayol")
        # Reddedilen yazim DOSYAYA DOKUNMAMALI.
        self.assertFalse(sistem.izinli_mi(self.state, "pc2_cpu_ram"))

    def test_kilitli_anahtar_ACIK_izinle_acilir(self):
        sistem.politika_yaz(self.state, "pc2_cpu_ram", True, "ozer",
                            ozel_izin=True)
        self.assertTrue(sistem.izinli_mi(self.state, "pc2_cpu_ram"))

    def test_kilitli_anahtari_KAPATMAK_izin_istemez(self):
        """Yon onemli: guvenli yone giden hareket engellenmez."""
        sistem.politika_yaz(self.state, "pc2_cpu_ram", True, "ozer",
                            ozel_izin=True)
        sistem.politika_yaz(self.state, "pc2_cpu_ram", False, "ozer")
        self.assertFalse(sistem.izinli_mi(self.state, "pc2_cpu_ram"))

    def test_kilitsiz_anahtar_izin_istemez(self):
        sistem.politika_yaz(self.state, "pc1_cpu_ram", True, "kisayol")
        self.assertTrue(sistem.izinli_mi(self.state, "pc1_cpu_ram"))

    def test_bilinmeyen_anahtar_SESSIZCE_yutulmaz(self):
        with self.assertRaises(ValueError):
            sistem.politika_yaz(self.state, "pc3_gpu", True, "ozer")

    def test_sonradan_eklenen_anahtar_eski_dosyada_KAYBOLMAZ(self):
        """Eski bir politika dosyasi yeni bir anahtari bilmez.

        O anahtarin "kapali" gorunup sessizce devre disi kalmasi en kotu
        sonuc olurdu; varsayilan degeriyle gelmeli.
        """
        (self.state / "kaynak_politikasi.json").write_text(
            json.dumps({"anahtarlar": {"sunucu_cpu_ram": {"acik": False}}}),
            encoding="utf-8")
        a = sistem.politika_oku(self.state)["anahtarlar"]
        self.assertFalse(a["sunucu_cpu_ram"]["acik"])      # kayitli deger korunur
        self.assertTrue(a["pc2_gpu"]["acik"])              # eksik anahtar varsayilana duser
        self.assertIn("pc1_gpu", a)

    def test_bozuk_dosya_varsayilana_duser_cokmez(self):
        (self.state / "kaynak_politikasi.json").write_text("{bozuk", encoding="utf-8")
        p = sistem.politika_oku(self.state)
        self.assertEqual(p["kaynak"], "varsayilan")
        self.assertTrue(p["anahtarlar"]["pc2_gpu"]["acik"])


class SunucuBellegi(unittest.TestCase):
    """Sanal makinede `free`'nin "used" degeri uygulamalarin kullanimi DEGIL.

    24.09.2026'da sunucuda olculdu: balon 15,25 GB almisti ve panel ham
    yuzdeyi gosterseydi "sunucunun RAM'i bitti" diye yanlis bir karara
    goturur. Ust politika "once sunucu RAM'i" dedigi icin bu sayinin
    dogru olmasi ayrica onemli.
    """

    def test_balon_okunamazsa_DUZELTILEMEDI_der_tahmin_uretmez(self):
        eski = sistem._balon_gib
        sistem._balon_gib = lambda: None
        try:
            s = sistem.sunucu_bellek_gercegi({"percent": 90.5, "used_gib": 21.2,
                                              "total_gib": 23.47})
        finally:
            sistem._balon_gib = eski
        self.assertEqual(s["durum"], "DUZELTILEMEDI")
        self.assertNotIn("gercek_yuzde", s)
        self.assertIn("HAM", s["not"])

    def test_balon_varsa_gercek_toplam_dusulur(self):
        eski_b, eski_r = sistem._balon_gib, sistem._surec_rss_gib
        sistem._balon_gib = lambda: 15.25
        sistem._surec_rss_gib = lambda: 7.2
        try:
            s = sistem.sunucu_bellek_gercegi({"percent": 90.5, "used_gib": 21.2,
                                              "total_gib": 23.47})
        finally:
            sistem._balon_gib, sistem._surec_rss_gib = eski_b, eski_r
        self.assertEqual(s["durum"], "BALON_VAR")
        self.assertAlmostEqual(s["gercek_toplam_gib"], 8.22, places=2)
        self.assertAlmostEqual(s["gercek_bos_gib"], 1.02, places=2)
        # Ham %90,5 ile gercek %87,6 farkli sayilardir; ikisi de raporlanir.
        self.assertEqual(s["ham_yuzde"], 90.5)
        self.assertGreater(s["gercek_yuzde"], 80)

    def test_balon_sifirsa_ham_degerler_gercek_sayilir(self):
        eski_b, eski_r = sistem._balon_gib, sistem._surec_rss_gib
        sistem._balon_gib = lambda: 0.0
        sistem._surec_rss_gib = lambda: 8.66
        try:
            s = sistem.sunucu_bellek_gercegi({"percent": 12.0, "used_gib": 5.0,
                                              "total_gib": 43.1})
        finally:
            sistem._balon_gib, sistem._surec_rss_gib = eski_b, eski_r
        self.assertEqual(s["durum"], "BALON_YOK")
        self.assertEqual(s["gercek_toplam_gib"], 43.1)


class Gorunum(unittest.TestCase):

    def test_uc_makine_de_her_zaman_var(self):
        with tempfile.TemporaryDirectory() as t:
            g = sistem.gorunum(Path(t), {"cpu": {}, "ram": {}, "disk": {}})
            self.assertEqual(set(g["makineler"]), {"sunucu", "pc1", "pc2"})
            # Eksik PC panelden DUSMEZ; sebebiyle birlikte gorunur kalir.
            self.assertEqual(g["makineler"]["pc1"]["durum"], "RAPOR_YOK")
            self.assertTrue(g["makineler"]["pc1"]["sebep"])


class SaglikGostergeleri(unittest.TestCase):
    """Gostergelerin tek isi: sessiz arizayi gorunur kilmak.

    25.09.2026'da bes ariza bulundu ve besi de sessizdi. Bu testlerin
    korudugu asil kural, gostergenin KENDISININ sessizce yalan
    soylememesi: olculemeyen bir sey icin sifir YAZILMAZ.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # --- "soramadim" asla "sifir" olmaz -------------------------------
    def test_sorgu_patlarsa_SORULAMADI_der_sifir_YAZMAZ(self):
        def patlayan_sql(_q):
            raise RuntimeError("permission denied for table ai_task")

        g = sistem._gosterge_kuyruk(patlayan_sql)
        self.assertEqual(g["durum"], "SORULAMADI")
        self.assertIn("permission denied", g["sebep"])
        # En onemli iddia: sayi alanlari HIC olusmamali.
        for alan in ("askida_kira", "bekleyen"):
            self.assertNotIn(alan, g, alan + " olculemedigi halde yazilmis")

    def test_sql_verilmezse_SORULAMADI(self):
        self.assertEqual(sistem._gosterge_kuyruk(None)["durum"], "SORULAMADI")
        self.assertEqual(sistem._gosterge_siparis(None)["durum"], "SORULAMADI")

    def test_kademe_dosyasi_yoksa_SORULAMADI(self):
        g = sistem._gosterge_model_kademesi(self.state)
        self.assertEqual(g["durum"], "SORULAMADI")
        self.assertNotIn("basarili", g)

    # --- kuyruk --------------------------------------------------------
    def test_askida_kira_BOZUK_sayilir(self):
        """Kirasi dolmus is = bir isci oldu, is sonsuza kadar kayboldu.

        25.09'dan once ai_claim_task bunlari HIC geri almiyordu; bir is
        4 gun LEASED kaldi ve hicbir yerde gorunmedi.
        """
        g = sistem._gosterge_kuyruk(lambda _q: [{
            "task_states": {"OPEN": 1}, "stale_red_team_leases": 2,
            "stale_action_leases": 0}])
        self.assertEqual(g["durum"], "BOZUK")
        self.assertEqual(g["askida_kira"], 2)

    def test_kuyruk_GOREMEDIGINI_soyler(self):
        """Eksik olcumu gizlemek, olcmemekten kotudur.

        Panelin rolu core.ai_task'i goremiyor; gosterge bunu YAZMALI,
        yoksa okuyan kisi kuyrugun tamamen denetlendigini sanir.
        """
        g = sistem._gosterge_kuyruk(lambda _q: [{
            "task_states": {}, "stale_red_team_leases": 0,
            "stale_action_leases": 0}])
        self.assertTrue(g.get("goremedigi"), "olcum bosluu yazilmamis")
        self.assertIn("ai_task", g["goremedigi"])

    def test_task_states_metin_gelirse_cozulur(self):
        """psql JSON'u bazen metin olarak doner; sayac bozulmamali."""
        g = sistem._gosterge_kuyruk(lambda _q: [{
            "task_states": '{"OPEN": 25}', "stale_red_team_leases": 0,
            "stale_action_leases": 0}])
        self.assertEqual(g["bekleyen"], 25)
        self.assertEqual(g["durum"], "ZAYIF")

    # --- siparis: esikler OLCULEN dagilimdan ---------------------------
    def test_siparis_esikleri_olculen_dagilimdan(self):
        """medyan 4 · 90. yuzdelik 18 · gecmisteki en uzun 32 (30 siparisli gun).

        Esigi medyana koymak her ay oten, dolayisiyla kimsenin bakmadigi
        bir alarm uretirdi.
        """
        def sql_gun(gun):
            return lambda _q: [{"gun": gun, "son_gun": "2026-09-12"}]

        self.assertEqual(sistem._gosterge_siparis(sql_gun(13))["durum"], "IYI")
        self.assertEqual(sistem._gosterge_siparis(sql_gun(18))["durum"], "ZAYIF")
        self.assertEqual(sistem._gosterge_siparis(sql_gun(33))["durum"], "BOZUK")

    def test_siparis_KAPSAMINI_soyler(self):
        """Bu sayi yalniz Wix. 'Hic satis yok' demek YANLIS olurdu."""
        g = sistem._gosterge_siparis(lambda _q: [{"gun": 5, "son_gun": "2026-09-20"}])
        self.assertIn("Wix", g["kapsam"])
        self.assertIn("Trendyol", g["kapsam"])

    # --- model kademesi ------------------------------------------------
    def _kademe_yaz(self, kayitlar):
        yol = self.state / "kademe.jsonl"
        yol.write_text("\n".join(json.dumps(k) for k in kayitlar), encoding="utf-8")

    def test_zincir_cogunlukla_tukeniyorsa_BOZUK(self):
        self._kademe_yaz([{"sonuc": "ZINCIR_TUKENDI", "ts": "t"}] * 6
                         + [{"sonuc": "BASARILI", "ts": "t"}] * 2)
        self.assertEqual(sistem._gosterge_model_kademesi(self.state)["durum"], "BOZUK")

    def test_zincir_bazen_tukeniyorsa_ZAYIF(self):
        self._kademe_yaz([{"sonuc": "ZINCIR_TUKENDI", "ts": "t"}]
                         + [{"sonuc": "BASARILI", "ts": "t"}] * 20)
        self.assertEqual(sistem._gosterge_model_kademesi(self.state)["durum"], "ZAYIF")

    def test_hic_tukenmiyorsa_IYI(self):
        self._kademe_yaz([{"sonuc": "BASARILI", "ts": "t"}] * 5)
        self.assertEqual(sistem._gosterge_model_kademesi(self.state)["durum"], "IYI")

    def test_bozuk_satir_gostergeyi_cokertmez(self):
        yol = self.state / "kademe.jsonl"
        yol.write_text('{yarim\n{"sonuc": "BASARILI", "ts": "t"}', encoding="utf-8")
        self.assertEqual(sistem._gosterge_model_kademesi(self.state)["durum"], "IYI")

    # --- gorunum butunlugu ---------------------------------------------
    def test_bes_gosterge_her_zaman_doner(self):
        """Biri patlasa bile digerleri gorunmeli."""
        g = sistem.saglik_gostergeleri(self.state, sql=None)
        self.assertEqual(set(g), {"kuyruk", "tuneller", "model_kademesi",
                                  "mutabakat", "siparis"})
        for ad, v in g.items():
            self.assertIn("durum", v, ad + " durum tasimiyor")

    def test_her_gosterge_NEYI_yakaladigini_soyler(self):
        """Neden orada oldugunu bilmeyen gostergeye kimse bakmaz."""
        g = sistem.saglik_gostergeleri(self.state, sql=lambda _q: [])
        for ad, v in g.items():
            if v["durum"] == "SORULAMADI":
                self.assertTrue(v.get("sebep"), ad + " sebebini yazmamis")
            else:
                self.assertTrue(v.get("yakaladigi"), ad + " ne yakaladigini yazmamis")


if __name__ == "__main__":
    unittest.main()
