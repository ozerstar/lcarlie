"""uyari_iddia_kapisi: gercek ihlalleri yakalar, mesru cumleyi yakalamaz."""
import importlib.util
import sys

import pathlib

# Yol __file__'dan turetilir; sabit uretim yolu testi kurulu surume baglar.
_BETIK = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "kreatif-brief.py"
spec = importlib.util.spec_from_file_location("kb", _BETIK)
kb = importlib.util.module_from_spec(spec)
sys.argv = ["kb"]
spec.loader.exec_module(kb)

vakalar = [
    # (cumle, yakalanmali, not)
    ("Kimyasal sprey değil, nazik bir seçim",              True,  "icermez kalibinin degilli hali"),
    ("Paraben içermeyen formül",                            True,  "adillik kriteri"),
    ("Yeni doğanlara da uygun, doktor önerisiyle başlayabilir", True, "kisit -> vaat"),
    ("Bebekler için de güvenli",                            True,  "kapsam genisletme"),
    # mesru olanlar
    ("Yeni doğanlarda doktor önerisi ile kullanılmalıdır",  False, "KUTUDAKI UYARI - kalmali"),
    ("Nemli veya kuru saça 15-20 cm mesafeden püskürtünüz", False, "kullanim talimati"),
    ("Tarak daha rahat geçiyor",                            False, "masum gozlem"),
    ("Günlük kullanıma uygundur",                           False, "onayli kutu ifadesi"),
    ("Alerjik reaksiyon durumunda doktora danışın",         False, "KUTUDAKI UYARI - kalmali"),
]

hata = 0
for cumle, yakalanmali, not_ in vakalar:
    s = kb.uyari_iddia_kapisi(cumle, "test")
    yakalandi = s is not None
    ok = yakalandi == yakalanmali
    hata += 0 if ok else 1
    print("%s %-52s yakalandi=%-5s %s" % (
        "OK  " if ok else "HATA", cumle[:52], yakalandi, not_))
print()
print("SONUC:", f"{len(vakalar)}/{len(vakalar)} DOGRU" if hata == 0 else f"{hata} VAKA YANLIS")
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
