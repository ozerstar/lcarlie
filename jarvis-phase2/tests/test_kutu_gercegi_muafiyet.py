"""Muafiyetin GERÇEK ihlalleri hâlâ yakaladığını kanıtlar."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("kb", "/opt/lcarlie/jarvis-phase2/scripts/kreatif-brief.py")
kb = importlib.util.module_from_spec(spec)
sys.argv = ["kb"]
spec.loader.exec_module(kb)

k = kb.kutu_gercegi("EASYCOMB")
urun_metni = (k.get("dayanak_metni") or "") + " EASYCOMB saç bakım spreyi"

vakalar = [
    ("Durulama gerektirmez",            False, "kutuda birebir yazıyor — GEÇMELİ"),
    ("Durulama gerektirmez, pratiktir", False, "aynı ifade cümle içinde — GEÇMELİ"),
    ("Gözenekleri tıkamaz",             True,  "model uydurması — TAKILMALI"),
    ("Yapışkanlık hissi bırakmaz",      True,  "model uydurması — TAKILMALI"),
    ("Soyulma riski yoktur",            True,  "model uydurması — TAKILMALI"),
    ("Saçı kırmaz",                     True,  "model uydurması — TAKILMALI"),
]

hata = 0
for cumle, takilmali, not_ in vakalar:
    sonuc = kb.dayanak_kapisi(cumle, urun_metni, {"15", "20"}, "test")
    takildi = sonuc is not None and sonuc.get("tur") == "olumsuz taahhüt"
    ok = takildi == takilmali
    hata += 0 if ok else 1
    print("%-4s %-34s takildi=%-5s  %s" % ("OK" if ok else "HATA", cumle, takildi, not_))
print()
print("SONUC:", "6/6 DOGRU" if hata == 0 else f"{hata} VAKA YANLIS")
sys.exit(1 if hata else 0)
