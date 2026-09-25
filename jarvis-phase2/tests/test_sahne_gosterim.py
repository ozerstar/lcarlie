"""SAHNE_GOSTERIM_YASAGI: gercek ihlali yakalar, masum kelimeyi yakalamaz."""
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
    ("Saçın ucundan başlayarak tarakla dağıtıyor",      False, "baslayarak icinde 'yara'"),
    ("Tarak ile saç arasında bağlantı kuruluyor",        False, "baglanti icinde 'agla'"),
    ("Anne çocuğun saçını yavaşça tarıyor",              False, "tamamen masum"),
    ("Çocuğun saçı kırık ve yıpranmış görünüyor",        True,  "gercek hasar gosterimi"),
    ("Çocuk ağlamaya başlıyor",                          True,  "gercek aci gosterimi"),
    ("Kafa derisinde kızarıklık yakın planda",           True,  "gercek lezyon gosterimi"),
    ("Beyaz önlüklü bir uzman ürünü tanıtıyor",          True,  "saglik calisani algisi"),
    ("Yarası olan bölgeye uygulanıyor",                  True,  "'yarasi' cekimli hali"),
]

hata = 0
for cumle, yakalanmali, not_ in vakalar:
    es = kb.SAHNE_GOSTERIM_YASAGI.search(cumle)
    yakalandi = es is not None
    ok = yakalandi == yakalanmali
    hata += 0 if ok else 1
    isaret = "OK  " if ok else "HATA"
    print("%s %-46s yakalandi=%-5s (%s) %s" % (
        isaret, cumle[:46], yakalandi, es.group(0) if es else "-", not_))
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
