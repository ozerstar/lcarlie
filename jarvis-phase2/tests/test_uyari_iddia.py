"""uyari_iddia_kapisi: gercek ihlalleri yakalar, mesru cumleyi yakalamaz."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("kb", "/opt/lcarlie/jarvis-phase2/scripts/kreatif-brief.py")
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
sys.exit(1 if hata else 0)
