"""Kitle kapisi: yanlis kitleyi yakalar, dogru kitleyi engellemez."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("kb", "/opt/lcarlie/jarvis-phase2/scripts/kreatif-brief.py")
kb = importlib.util.module_from_spec(spec)
sys.argv = ["kb"]
spec.loader.exec_module(kb)

YASAK = ["çocuk", "cocuk", "bebek", "ebeveyn", "anne", "baba", "okul", "servis"]

VAKALAR = [
    # (cumle, yakalanmali, not)
    ("Sabah uyandıktan sonra çocuğun saç derisi rahatsız", True, "unsuz yumusamasi k->g"),
    ("Çocuklarının saçını taramak isteyen ebeveynler", True, "duz kok"),
    ("Servis kapıda, saç hâlâ taranmadı", True, "okul kurgusu"),
    ("Bebek saçı için nazik formül", True, "bebek"),
    ("Annesinin yanında oturuyor", True, "anne cekimli"),
    ("Okulda geç kaldı", True, "okul"),
    ("Sabah aynada saçım donuk görünüyordu", False, "yetiskin, temiz"),
    ("Tarak daha rahat geçiyor, durulama gerektirmez", False, "urun ifadesi"),
    ("Kendi saç bakım rutinime ekledim", False, "yetiskin rutini"),
    ("Nemli veya kuru saça 15-20 cm mesafeden püskürtünüz", False, "kullanim talimati"),
    ("Akşama çıkışım var, saçım hazır değil", False, "yetiskin ani"),
]

hata = 0
for cumle, yakalanmali, not_ in VAKALAR:
    s = kb.kitle_kapisi(cumle, YASAK, "test")
    yakalandi = s is not None
    ok = yakalandi == yakalanmali
    hata += 0 if ok else 1
    print("%s %-50s -> %-9s %s" % (
        "OK  " if ok else "HATA", cumle[:50],
        s["yakalanan"] if s else "-", not_))

print()
print("SONUC:", f"{len(VAKALAR)}/{len(VAKALAR)} DOGRU" if hata == 0 else f"{hata} YANLIS")
sys.exit(1 if hata else 0)
