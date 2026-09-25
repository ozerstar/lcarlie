# -*- coding: utf-8 -*-
"""Basılı katalogda fiyat GÖRÜNMEZ — sahip kararı 25.09.2026.

Basılı fiyat, bir yıl sonra da aynı sözü vermeye devam eder. Fiyatı
temsilci söyler, panelden okuyarak; kademe fiyatları veritabanında ve
KATALOG sekmesinde durur, basıma giden sayfaya girmez.

🔴 KARAR YAZIYLA KORUNMAZ, TESTLE KORUNUR. Bu kural yalnız bilgi
dosyasında yazsaydı, birkaç ay sonra "kataloğa fiyat eklemek faydalı
olur" diye sessizce geri gelirdi -- eksik görünen bir alan, doldurulmayı
davet eder.

NE ÖLÇÜLÜYOR: tasarım betikleri fiyat alanını OKUYOR MU. Okumuyorsa
basamaz. Üretilmiş PDF'in içinden metin çıkarıp aramak daha doğrudan
olurdu ama sunucuda PDF metin ayıklayıcı yok (pdftotext ve pypdf ikisi de
kurulu değil); bu yüzden ölçüm kaynak kodu seviyesinde yapılıyor ve
sınırı budur: betik fiyatı başka bir dosyadan okuyup geçirirse bu test
görmez. O yolu kapatan şey, `katalog_mimari.py`'nin ürün sözlüğünü
doğrudan katalog.json'dan alması.
"""
import ast
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

# Basima giden sayfayi ureten betikler. katalog-uret.py BURADA DEGIL:
# o veri katmanini kurar, fiyati panel icin tasimasi dogrudur.
TASARIM_BETIKLERI = [
    "scripts/katalog-tasarim.py",
    "scripts/katalog_mimari.py",
]

# Fiyat tasiyan alan adlari. Turkce alt dize tuzagina dikkat: "fiyat"
# kelimesi yorum satirlarinda gecebilir ("fiyata gore siralanmaz"), bu
# yuzden yorum ve metin degil, YALNIZ ALAN ERISIMI aranir.
FIYAT_ALANLARI = {
    "fiyat", "psf", "bayi", "bayi_fiyat", "psf_kaynagi",
    "isk30_haric", "isk30_dahil", "isk40_haric", "isk40_dahil",
    "trendyol",
}


def okunan_alanlar(yol: Path) -> set:
    """Betiğin sözlükten okuduğu alan adları.

    d["fiyat"] ve d.get("fiyat") biçimlerinin ikisi de yakalanır.
    Yorumlar ve docstring'ler kapsam dışıdır: onlar kod değildir.
    """
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    bulunan = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Subscript) and isinstance(d.slice, ast.Constant):
            if isinstance(d.slice.value, str):
                bulunan.add(d.slice.value)
        elif (isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "get"
                and d.args
                and isinstance(d.args[0], ast.Constant)
                and isinstance(d.args[0].value, str)):
            bulunan.add(d.args[0].value)
    return bulunan


class TestBaskidaFiyatYok(unittest.TestCase):
    def test_tasarim_betikleri_fiyat_okumuyor(self):
        for ad in TASARIM_BETIKLERI:
            yol = KOK / ad
            self.assertTrue(yol.is_file(), "betik yok: %s" % ad)
            ihlal = okunan_alanlar(yol) & FIYAT_ALANLARI
            self.assertEqual(
                ihlal, set(),
                "%s fiyat alani okuyor: %s — basili katalogda fiyat "
                "gorunmez (sahip karari 25.09.2026). Fiyati temsilci "
                "soyler." % (ad, sorted(ihlal)))

    def test_olcum_gercekten_bir_sey_okuyor(self):
        """Ölçüm harness'i sessizce boş dönmesin.

        Alan çıkarımı bozulursa her betik 'temiz' görünür ve test yeşil
        yanarken hiçbir şeyi korumaz. Önce okuyucunun çalıştığı kanıtlanır.
        """
        toplam = set()
        for ad in TASARIM_BETIKLERI:
            toplam |= okunan_alanlar(KOK / ad)
        self.assertGreater(len(toplam), 10,
                           "alan cikarimi calismiyor gibi: %s" % sorted(toplam))

    def test_kural_bilgi_dosyasinda_yazili(self):
        # Testi okumayan biri kurali bilgi dosyasinda bulabilmeli.
        metin = (KOK / "knowledge" / "42-katalog-yonetimi.md").read_text(
            encoding="utf-8")
        self.assertIn("Fiyat basılmaz", metin)


if __name__ == "__main__":
    unittest.main()
