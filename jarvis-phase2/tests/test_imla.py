"""Imla kapisi: gercek hatayi yakalar, mesru kelimeyi yakalamaz."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("kb", "/opt/lcarlie/jarvis-phase2/scripts/kreatif-brief.py")
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
sys.exit(1 if hata else 0)
