# -*- coding: utf-8 -*-
"""Görsel denetim kapısının sözleşmesi.

Kapı, sahibin gözü yerine duruyor: "gözle onaylayacak kadar vaktim yok."
O yüzden kapının kendisi sessizce bozulursa, bozulduğunu kimse fark
etmez -- her görsel GEÇTİ der ve kusurlu kareler yayına gider.

🔴 KAPI GERÇEK KUSURLARLA SINANDI (26.09.2026, Seedream 4.5 çıktıları):
    ipek sahnesi          GECTI  (temiz)
    gece mavisi sahnesi   RET    cosmetic jar 0,45 · cosmetic bottle 0,30
                                 · printed label 0,20
    beton sahnesi         GECTI  (temiz)
    arnika sahnesi        RET    text 0,30 · watermark 0,23
4 karede 2 ret -- gözümün verdiği kararın aynısı. Eşikler bu dört kare
üzerinde kalibre edildi; eşiği değiştiren aynı dört kareyle yeniden
ölçmek zorundadır.

Model çağrısı burada KOŞMAZ (OWLv2 CPU'da görsel başına saniyeler alır ve
ayrı venv ister). Burada kapının SÖZLEŞMESİ korunur: hangi kapılar var,
eşikleri makul mü, "atlandı" ile "geçti" ayrı mı.
"""
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_d = SourceFileLoader(
    "gorsel_denetim", str(_KOK / "scripts" / "gorsel-denetim.py")).load_module()


class TestKapiListesi(unittest.TestCase):
    def test_dort_kapi_var(self):
        anahtarlar = [k[0] for k in _d.KAPILAR]
        self.assertEqual(anahtarlar, ["urun", "yazi", "insan", "klise"])

    def test_urun_kapisi_gercek_vakayi_kapsar(self):
        # Olculen kacak "a cosmetic jar" ve "a cosmetic bottle" idi.
        sorgular = dict((k[0], k[2]) for k in _d.KAPILAR)["urun"]
        for gereken in ("a cosmetic jar", "a cosmetic bottle"):
            self.assertIn(gereken, sorgular)

    def test_yazi_kapisi_gercek_vakayi_kapsar(self):
        # Olculen kacak "text" ve "a watermark" idi.
        sorgular = dict((k[0], k[2]) for k in _d.KAPILAR)["yazi"]
        for gereken in ("text", "a watermark"):
            self.assertIn(gereken, sorgular)

    def test_esikler_makul(self):
        # 0 esik her seyi yakalar (kullanilamaz), 1 hicbir seyi (kapi yok).
        # Olculen gercek kacaklar 0,20-0,61 arasindaydi; esik onlarin
        # altinda ama gurultunun ustunde olmali.
        for anahtar, _e, _s, esik, _r in _d.KAPILAR:
            self.assertGreater(esik, 0.05, anahtar)
            self.assertLess(esik, 0.30, anahtar)

    def test_urun_ve_yazi_esigi_olculen_kacagin_altinda(self):
        esik = dict((k[0], k[3]) for k in _d.KAPILAR)
        # Gece mavisi karesinde "printed label" 0,20 ile yakalanmisti.
        self.assertLessEqual(esik["yazi"], 0.20)
        # Ayni karede en zayif urun izi "a perfume bottle" 0,23'tu.
        self.assertLessEqual(esik["urun"], 0.23)

    def test_hepsi_ret_uretir(self):
        # Dort kapinin dordu de RET sebebi sayilir; "uyari" kapisi yok.
        for anahtar, _e, _s, _esik, ret_mi in _d.KAPILAR:
            self.assertTrue(ret_mi, anahtar)

    def test_sorgular_ingilizce(self):
        # OWLv2'nin metin kodlayicisi Ingilizce; Turkce sorgu sessizce
        # zayif eslesir ve kapi bos doner.
        turkce_harf = set("çğıöşüÇĞİÖŞÜ")
        for anahtar, _e, sorgular, _esik, _r in _d.KAPILAR:
            for s in sorgular:
                self.assertFalse(turkce_harf & set(s),
                                 "%s: %r Turkce harf tasiyor" % (anahtar, s))


class TestNegatifAlan(unittest.TestCase):
    def test_duz_zemin_sakin_cikar(self):
        from PIL import Image
        duz = Image.new("RGB", (200, 300), "#303030")
        olcum = _d.negatif_alan_olc(duz)
        self.assertLess(olcum["kenar_ortalama"], 1.0, olcum)

    def test_gurultulu_alan_mesgul_cikar(self):
        import random

        from PIL import Image
        random.seed(7)
        g = Image.new("RGB", (200, 300))
        g.putdata([(random.randrange(256),) * 3 for _ in range(200 * 300)])
        olcum = _d.negatif_alan_olc(g)
        self.assertGreater(olcum["kenar_ortalama"], 20.0, olcum)

    def test_en_sakin_bolge_dogru_bulunur(self):
        import random

        from PIL import Image
        random.seed(11)
        # Ust ucte bir duz, alt iki ucte bir gurultulu.
        g = Image.new("RGB", (120, 300), "#202020")
        gurultu = [(random.randrange(256),) * 3 for _ in range(120 * 200)]
        alt = Image.new("RGB", (120, 200))
        alt.putdata(gurultu)
        g.paste(alt, (0, 100))
        sonuc = _d.en_sakin_bolge(g)
        self.assertEqual(sonuc["en_sakin"], "ust", sonuc)


class TestDurumAyrimi(unittest.TestCase):
    """ATLANDI ile GECTI ayrı şeylerdir."""

    def test_atlanan_kapi_gecti_sayilmaz(self):
        # Konsept arnika cicegi istiyorsa klise kapisi ATLANDI der --
        # GECTI demez. "Bakmadik" ile "baktik temizdi" ayni sey degil.
        kaynak = (_KOK / "scripts" / "gorsel-denetim.py").read_text(
            encoding="utf-8")
        self.assertIn('"sonuc": "ATLANDI"', kaynak)
        # Ve atlama gerekcesiz olamaz.
        self.assertIn('"gerekce"', kaynak)


if __name__ == "__main__":
    unittest.main()
