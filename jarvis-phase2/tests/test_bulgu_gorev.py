"""bulgu-gorev.py: bulgudan ise giden koprunun mantigi.

NEDEN VAR
Bu betik ONAY KUYRUGUNA is acar. Iki yonde de bozulabilir:
  - fazla acarsa sahip ayni seye onlarca kez bakar (kuyruk bogulur)
  - az acarsa gercek bir ariza hic ise donusmez
Ilk kuru kosuda tam bunun ilki oldu: 23 kategori 404'u 23 AYRI is
acmaya kalkti. Gruplama o yuzden eklendi; bu testler onu bekcilik eder.

🔴 VERITABANI YOK. Yalniz saf fonksiyonlar sinaniyor; test hicbir is
   acmaz, hicbir kayit yazmaz.
"""
from __future__ import annotations
from tests import betik_yolu

import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

BETIK = pathlib.Path(betik_yolu("bulgu-gorev.py"))


def _yukle():
    spec = importlib.util.spec_from_file_location("bulgu_gorev", BETIK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bg = _yukle()


def _bulgu(sebep, url, kod="site_erisim", onem="CRITICAL", imza=None):
    return {
        "signature": imza or f"{kod}:{url}",
        "reason": sebep,
        "evidence": {"url": url},
        "signal_code": kod,
        "severity": onem,
        "observed_at": "2026-09-22T09:00:00+00:00",
    }


class Sablon(unittest.TestCase):
    """Adres ve sayilar cikarilinca geriye ORTAK sablon kalmali."""

    def test_farkli_adresler_ayni_sablona_iner(self):
        a = bg._sablon("/category/yuz-bakimi HTTP 404 donuyor.")
        b = bg._sablon("/category/sac-bakimi HTTP 404 donuyor.")
        self.assertEqual(a, b)

    def test_farkli_olgular_ayni_sablona_INMEZ(self):
        """🔴 TERS YON: her seyi tek sablona indiren kod, ayri sorunlari
        tek ise gomer ve biri gorunmez olur."""
        a = bg._sablon("/category/x HTTP 404 donuyor.")
        b = bg._sablon("TLS sertifikasi 12 gun sonra bitiyor.")
        self.assertNotEqual(a, b)

    def test_sebep_icindeki_tam_url_de_temizlenir(self):
        """🔴 Mutasyon testi bu bosluu buldu.

        site_seo bulgusunun sebebi meta-refresh iceriginde TAM bir URL
        tasiyor. O kademe silinse bile eski testler geciyordu; iki farkli
        hedefe yonlendiren iki sayfa AYRI is acardi.
        """
        a = bg._sablon("x HTTP 200 donuyor ama meta-refresh (0; URL='https://a.example/p')")
        b = bg._sablon("x HTTP 200 donuyor ama meta-refresh (0; URL='https://b.example/q')")
        self.assertEqual(a, b)

    def test_tam_url_iceren_bulgular_gruplanir(self):
        bulgular = [
            _bulgu(f"s{i} HTTP 200 donuyor ama meta-refresh "
                   f"(0; URL='https://hedef{i}.example/p')",
                   f"https://x/s{i}", kod="site_seo", onem="WARNING")
            for i in range(4)
        ]
        grup = bg._grupla(bulgular)
        self.assertEqual(len(grup), 1)
        self.assertEqual(grup[0]["evidence"]["grup_sayisi"], 4)

    def test_durum_kodu_farki_sablonu_ayirmaz(self):
        """404 ile 500 ayni SABLON: ikisi de '<yol> HTTP <n> donuyor'.
        Ayirmak isteniyorsa sablon degil KOD degismeli."""
        self.assertEqual(bg._sablon("/a HTTP 404 donuyor."),
                         bg._sablon("/b HTTP 500 donuyor."))


class Gruplama(unittest.TestCase):
    def test_yirmi_uc_ayni_sorun_TEK_ise_iner(self):
        """Olculmus vaka: 23 kategori sayfasi 404 donuyordu."""
        bulgular = [_bulgu(f"/category/k{i} HTTP 404 donuyor.",
                           f"https://x/category/k{i}") for i in range(23)]
        grup = bg._grupla(bulgular)
        self.assertEqual(len(grup), 1)
        self.assertEqual(grup[0]["evidence"]["grup_sayisi"], 23)

    def test_gruplanan_sebep_adresleri_TASIR(self):
        """Onaylayan insan hangi adreslerin etkilendigini gormeli."""
        bulgular = [_bulgu(f"/category/k{i} HTTP 404 donuyor.",
                           f"https://x/category/k{i}") for i in range(5)]
        grup = bg._grupla(bulgular)
        self.assertIn("https://x/category/k0", grup[0]["reason"])

    def test_farkli_sorunlar_AYRI_kalir(self):
        """🔴 TERS YON: hepsini tek gruba atan kod ustteki testi de gecerdi."""
        bulgular = [
            _bulgu("/a HTTP 404 donuyor.", "https://x/a"),
            _bulgu("TLS sertifikasi 12 gun sonra bitiyor.", "https://x",
                   kod="site_erisim", onem="WARNING"),
        ]
        self.assertEqual(len(bg._grupla(bulgular)), 2)

    def test_tek_bulgu_gruplanmaz_ve_imzasi_KORUNUR(self):
        """Tek bulgu sarilirsa imzasi degisir ve 'islenen' kaydi tutmaz;
        ayni bulgu her kosuda yeniden is acar."""
        b = _bulgu("/a HTTP 404 donuyor.", "https://x/a")
        grup = bg._grupla([b])
        self.assertEqual(len(grup), 1)
        self.assertEqual(grup[0]["signature"], b["signature"])

    def test_grup_imzasi_KARARLI(self):
        """Ayni girdi ayni imzayi vermezse tekillik kontrolu ise yaramaz
        ve ayni sorun her gun yeni is acar."""
        bulgular = [_bulgu(f"/c/k{i} HTTP 404 donuyor.", f"https://x/c/k{i}")
                    for i in range(7)]
        self.assertEqual(bg._grupla(bulgular)[0]["signature"],
                         bg._grupla(list(reversed(bulgular)))[0]["signature"])

    def test_farkli_onem_ayri_gruplanir(self):
        bulgular = [
            _bulgu("/a HTTP 404 donuyor.", "https://x/a", onem="CRITICAL"),
            _bulgu("/b HTTP 404 donuyor.", "https://x/b", onem="WARNING"),
        ]
        self.assertEqual(len(bg._grupla(bulgular)), 2)


class Slug(unittest.TestCase):
    def test_ayni_imza_ayni_slug(self):
        self.assertEqual(bg._slug("site_erisim:https://x/a"),
                         bg._slug("site_erisim:https://x/a"))

    def test_slug_dosya_adina_uygun(self):
        s = bg._slug("site_erisim:https://x/category/yüz-bakımı")
        self.assertRegex(s, r"^[a-z0-9][a-z0-9_-]*$")

    def test_yol_kacisi_uretmez(self):
        """🔴 Slug bir dosya adina donusuyor; '..' ve '/' gecmemeli."""
        s = bg._slug("../../etc/passwd")
        self.assertNotIn("/", s)
        self.assertNotIn("..", s)

    def test_bos_girdide_bile_gecerli_slug(self):
        self.assertRegex(bg._slug(""), r"^[a-z0-9][a-z0-9_-]*$")


class Sartname(unittest.TestCase):
    """Dongu sartnameyi okuyup ONAY KUYRUGUNA yazacak."""

    def setUp(self):
        self.gecici = pathlib.Path(tempfile.mkdtemp())
        self.eski = bg.SARTNAME_DIZIN
        bg.SARTNAME_DIZIN = self.gecici

    def tearDown(self):
        bg.SARTNAME_DIZIN = self.eski
        shutil.rmtree(self.gecici, ignore_errors=True)

    def test_sartname_payload_ve_reason_icerir(self):
        """🔴 payload.reason yoksa dongu KENDI yer tutucusunu koyar ve
        onay kuyruguna ici bos bir oneri duser. agency_store.py bunu
        kendi docstring'inde kusur diye tarif ediyor."""
        yol = bg._sartname_yaz("deneme-slug", _bulgu("/a HTTP 404 donuyor.", "https://x/a"))
        spec = json.loads(yol.read_text(encoding="utf-8"))
        self.assertIn("payload", spec)
        self.assertTrue(spec["payload"].get("reason", "").strip())
        self.assertTrue(spec["payload"].get("subject_ref", "").strip())

    def test_sartname_kaniti_TASIR(self):
        yol = bg._sartname_yaz("deneme2", _bulgu("/a HTTP 404 donuyor.", "https://x/a"))
        spec = json.loads(yol.read_text(encoding="utf-8"))
        self.assertIn("https://x/a", spec["payload"]["reason"])

    def test_sartname_dosya_adi_slug(self):
        yol = bg._sartname_yaz("abc-def", _bulgu("/a HTTP 404 donuyor.", "https://x/a"))
        self.assertEqual(yol.name, "abc-def.json")


class IzinListesi(unittest.TestCase):
    def test_site_ve_panel_kodlari_izinli(self):
        for k in ("site_erisim", "site_seo", "site_gerileme",
                  "panel_erisim", "panel_butunluk"):
            self.assertIn(k, bg.IZINLI_KODLAR)

    def test_bilinmeyen_kod_izinli_DEGIL(self):
        """🔴 Acik liste: yeni bir sinyal kendiliginden is acmaya baslamasin."""
        self.assertNotIn("rastgele_yeni_sinyal", bg.IZINLI_KODLAR)

    def test_INFO_seviyesi_is_acmaz(self):
        """Bilgi notu icin insan mesaisi harcanmaz."""
        self.assertNotIn("INFO", bg.IZINLI_ONEM)


if __name__ == "__main__":
    unittest.main()
