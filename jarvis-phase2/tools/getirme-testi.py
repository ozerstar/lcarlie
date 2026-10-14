"""Musteri urunu adiyla degil TARIFIYLE arar. Getirme bunu bulabiliyor mu."""
import sys

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis.company_knowledge import shared

KONTROL = [
    ("sporcu bakim kremi", "KINESIS"),
    ("bebek bez bolgesi kremi", "MINISOOTH"),
    ("gece bakim kremi", "SERALIMBO"),
    ("ayak ve tirnak kremi", "DERMAGUARD"),
    ("yuz temizleme kopugu", "LUCIDERM"),
    ("dudak balmi", "LIPVORA"),
    ("sac bakim yagi", "HAIR"),
    ("gogus ve dekolte kremi", "LIFTELLE"),
    ("masaj kremi", "MOVERA"),
    ("agiz bakim spreyi", "ORAGARDE"),
    ("gunes kremi", "SOL"),
    ("dis macunu", "SMILE"),
]

ck = shared()
dogru = 0
for soru, beklenen in KONTROL:
    r = ck.retrieve(soru)
    ad = getattr(r[0], "konu", "") if r else "(bulunamadi)"
    ok = beklenen.lower() in ad.lower()
    dogru += ok
    print("  %-4s %-26s -> %s" % ("OK" if ok else "HATA", soru, ad[:54]))
print()
print("  %d/%d dogru" % (dogru, len(KONTROL)))
