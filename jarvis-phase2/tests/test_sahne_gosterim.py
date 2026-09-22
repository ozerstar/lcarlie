"""SAHNE_GOSTERIM_YASAGI: gercek ihlali yakalar, masum kelimeyi yakalamaz."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("kb", "/opt/lcarlie/jarvis-phase2/scripts/kreatif-brief.py")
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
sys.exit(1 if hata else 0)
