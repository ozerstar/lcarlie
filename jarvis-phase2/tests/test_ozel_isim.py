"""Ozel isim istisnasi: etkinlik adini birakir, gercek iddiayi yakalar."""
import importlib.util
import pathlib
import sys

# Yol __file__'dan turetilir; sabit uretim yolu testi kurulu surume baglar.
_BETIK = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "itibar-tara.py"

spec = importlib.util.spec_from_file_location("it", _BETIK)
it = importlib.util.module_from_spec(spec)
sys.argv = ["it"]
spec.loader.exec_module(it)

VAKALAR = [
    # (cumle, bayrak_kalkmali_mi, not)
    ("Şifa Köprüsü Forumu'nda L'CARLİÉ Dikkat Çekti", False,
     "ETKINLIK ADI — bayrak kalkmamali"),
    ("Ankara'da düzenlenen Şifa Köprüsü Forumu'na katildi", False,
     "etkinlik adi, cumle icinde"),
    ("Sağlık Vakfı Şifa Ödülü'nü aldı", False,
     "odul adi"),
    ("Ürün cilde şifa verir", True,
     "GERCEK IDDIA — yakalanmali"),
    ("Kremin şifalı etkisi kanıtlandı", True,
     "gercek iddia"),
    ("sert kimyasallardan arındırılmış formül", True,
     "gercek iddia (icermez kalibi)"),
    ("Marka doğal içerikleriyle öne çıktı", False,
     "temiz cumle"),
]

hata = 0
for cumle, beklenir, not_ in VAKALAR:
    b = it.mevzuat_bayraklari(cumle)
    kalkti = bool(b)
    ok = kalkti == beklenir
    hata += 0 if ok else 1
    print("%s %-52s bayrak=%-22s %s" % (
        "OK  " if ok else "HATA", cumle[:52], str(b)[:22], not_))

print()
print("SONUC:", f"{len(VAKALAR)}/{len(VAKALAR)} DOGRU" if hata == 0
      else f"{hata} VAKA YANLIS")
# 🔴 EKLENDI 22.09.2026 - modul duzeyindeki sys.exit() kesfi kiriyordu.
#    `unittest discover` bu dosyayi ICE AKTARIR; sys.exit(0) SystemExit
#    firlatir ve discover bunu "ImportError: Failed to import test module"
#    diye raporlar. Denetimler GECTIGI halde paket kirmizi goruntu verip
#    deploy.sh'yi durduruyordu.
#
#    Yalnizca cikisi kosullamak YETMEZDI: o zaman denetim import sirasinda
#    kosar, basarisizsa 'HATA' basar ve unittest hicbir sey gormezdi.
#    Sessiz basarisizlik olmasin diye sonuc ayrica bir TestCase'e bagli.
if __name__ == "__main__":
    sys.exit(1 if hata else 0)


import unittest as _unittest  # noqa: E402


class DenetimSonucu(_unittest.TestCase):
    """Bu dosyanin kendi denetimleri unittest'e de gorunur olsun."""

    def test_butun_denetimler_gecti(self):
        self.assertEqual(hata, 0, f"{hata} denetim basarisiz")
