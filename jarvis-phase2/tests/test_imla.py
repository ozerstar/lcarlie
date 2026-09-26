"""Imla kapisi: gercek hatayi yakalar, mesru kelimeyi yakalamaz."""
from tests import betik_yolu
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("kb", betik_yolu("kreatif-brief.py"))
kb = importlib.util.module_from_spec(spec)
sys.argv = ["kb"]
spec.loader.exec_module(kb)

YAKALANMALI = [
    ("nazik bakımlaşır", "bakımlaşır"),
    ("Aaa kızlar şunayem değil mi", "şunayem"),
    ("saç titleri akademisi", "titleri"),
]
YAKALANMAMALI = [
    "Tarak daha rahat geçiyor",
    "Durulama gerektirmez",
    "EASYCOMB saç bakım spreyi",
    "Cildim sabah daha bakımlı görünüyor",
    "Nemli veya kuru saça 15-20 cm mesafeden püskürtünüz",
    "Aloe vera ve jojoba yağı içerir",
    "Günlük bakım rutinime ekledim",
]

hata = 0
print("--- YAKALANMALI ---")
for cumle, beklenen in YAKALANMALI:
    bulunan = kb.imla_denetimi([cumle])
    ok = beklenen in bulunan
    hata += 0 if ok else 1
    print(f"{'OK  ' if ok else 'HATA'} {cumle[:44]:<44} -> {bulunan}")

print("--- YAKALANMAMALI (yanlis pozitif testi) ---")
for cumle in YAKALANMAMALI:
    bulunan = kb.imla_denetimi([cumle])
    ok = not bulunan
    hata += 0 if ok else 1
    print(f"{'OK  ' if ok else 'HATA'} {cumle[:44]:<44} -> {bulunan}")

toplam = len(YAKALANMALI) + len(YAKALANMAMALI)
print()
print("SONUC:", f"{toplam}/{toplam} DOGRU" if hata == 0 else f"{hata}/{toplam} YANLIS")
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
