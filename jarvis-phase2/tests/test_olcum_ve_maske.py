#!/usr/bin/env python3
"""İki ölçülmüş hatanın geri gelmesini engelleyen kapılar.

1) ADRES KODLAMA. Ölçüm betiği Türkçe karakterli adresi kodlamıyordu ve
   sağlam bir sayfayı "erişilemiyor" diye işaretledi. Ölçenin kusuru,
   ölçülenin kusuru gibi raporlandı — bu ikisi ayrı şeydir.

2) GÜNLÜK MASKESİ. Meta webhook doğrulaması query'de anahtar taşıyor ve o
   anahtar journald'a açık metin düştü. Maske yazma anında olmalı; günlüğü
   sonradan temizlemek pratikte mümkün değil.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
import urllib.parse
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
OLCUM = Path("/opt/lcarlie/seo-araclari/sayfa-olcum.py")


def _yukle(ad: str, yol: Path):
    spec = importlib.util.spec_from_file_location(ad, yol)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


class AdresKodlama(unittest.TestCase):
    """Ölçüm betiği Türkçe karakterli adresi göndermeden önce kodlamalı."""

    def test_betik_kodlama_yapiyor(self):
        if not OLCUM.exists():
            self.skipTest("olcum betigi sunucuda degil")
        kaynak = OLCUM.read_text(encoding="utf-8")
        self.assertIn("urllib.parse.quote", kaynak,
                      "adres kodlanmiyor; Turkce karakterli sayfa 'erisilemiyor' "
                      "diye isaretlenir ve saglam sayfa bozuk sanilir")

    def test_kodlama_gercekten_calisiyor(self):
        yol = "/product-page/minisooth-bebek-pişik-kremi"
        kodlu = urllib.parse.quote(yol)
        self.assertNotIn("ş", kodlu)
        # urllib ham hali reddeder; kodlusu ASCII olmali
        kodlu.encode("ascii")

    def test_kodlama_zararsiz_adresi_bozmuyor(self):
        for yol in ("/product-page/babysol", "/vireon", "/"):
            self.assertEqual(yol, urllib.parse.quote(yol),
                             "ASCII adres degistirilmemeli")


class GunlukMaskesi(unittest.TestCase):
    """Hassas parametre günlüğe yazılmadan maskelenmeli."""

    @classmethod
    def setUpClass(cls):
        cls.H = _yukle("wc_app", KOK / "webconsole/app.py").Handler

    def test_webhook_anahtari_maskelenir(self):
        gizli = "0FYns0hCETevSNLRzvLp927dUS0BE2x"
        satir = (f"GET /webhook/meta?hub.mode=subscribe&hub.verify_token={gizli}"
                 "&hub.challenge=X HTTP/1.1")
        self.assertNotIn(gizli, self.H._gunluk_maskele(satir))

    def test_govdedeki_sifre_maskelenir(self):
        """'=' yoktu diye maske atlanıyordu; JSON gövdesi de denetlenmeli."""
        satir = '{"token":{"select":["email"]},"password":"TestPassword1!"}'
        self.assertNotIn("TestPassword1!", self.H._gunluk_maskele(satir))

    def test_zararsiz_parametre_korunur(self):
        """Her şeyi maskelemek günlüğü işe yaramaz hale getirir."""
        satir = "GET /api/activity?limit=60&gun=7 HTTP/1.1"
        self.assertEqual(satir, self.H._gunluk_maskele(satir))

    def test_maske_istegi_dusurmez(self):
        """Günlük yazımı hiçbir koşulda isteği bozmamalı."""
        for tuhaf in ("", "=", '":', "?a=", "%%%", "a" * 5000):
            self.H._gunluk_maskele(tuhaf)


class IPKaydiBilincli(unittest.TestCase):
    """IP tutmak KVKK kararıdır; sessizce açılmış olmamalı."""

    def test_karar_kodda_acik(self):
        kaynak = (KOK / "webconsole/app.py").read_text(encoding="utf-8")
        self.assertIn("ISTEMCI_IP_YAZ", kaynak)
        self.assertIn("KVKK", kaynak,
                      "IP kisisel veridir; neden tutuldugu kodda yazmali")


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=1).result
    print("SONUC:", "TUM KAPILAR GECTI" if r.wasSuccessful()
          else f"{len(r.failures) + len(r.errors)} SORUN")
    sys.exit(0 if r.wasSuccessful() else 1)
