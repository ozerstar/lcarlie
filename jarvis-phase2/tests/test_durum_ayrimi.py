#!/usr/bin/env python3
"""KALIP AVCISI — 'iki ayrı durumu tek etikete sıkıştırma' hatasını yakalar.

🔴 NEDEN VAR. 22.09.2026'da aynı hata ÜÇ KEZ yapıldı:
  1. `opinions()` — kaynağı okunan ama konuşma işlevi olmayan üyeye
     "VERİ YOK" dedi. Veri vardı (93 satır); eksik olan koddu.
  2. `_say_meta_reklam_kreatifci` — "0 tasarım şablonu" dedi. O üye şablon
     tablosunu HİÇ OKUMUYOR; sıfır, yokluk değil BAKMAMA demekti.
  3. `_say_baglanti_denetcisi` — CONNECTED olmayan her kaynağı "KOPUK"
     saydı. Aralarında kısmi çalışan ve sahip kararıyla elle girilen
     kaynaklar vardı.

Ortak kök: **bir yokluğu, sebebini kontrol etmeden cümleye çevirmek.**
Sahip 22.09.2026: "Bu kalıbı kullandırtmayacak kadar iş ver o zaman."

Bu sınav üç kapı kurar:
  A. Konuşmacı KENDİ okumadığı kaynağı sayamaz.
  B. Boş veriyle dolu veri AYNI cümleyi üretemez.
  C. Durum etiketleri birbirinden ayrı kalmalı.
"""
from __future__ import annotations

import inspect
import os
import re
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis import roster  # noqa: E402
from jarvis.memory import CompanyMemory  # noqa: E402

hata = 0


def bildir(gecti: bool, baslik: str, ayrinti: str = "") -> None:
    global hata
    if not gecti:
        hata += 1
    print(f"{'OK  ' if gecti else 'HATA'} {baslik}")
    if ayrinti and not gecti:
        print(f"       {ayrinti}")


# =====================================================================
# A. Konuşmacı kendi okumadığı kaynağı sayamaz
# =====================================================================
print("=== A · KONUŞMACI KENDİ OKUMADIĞI KAYNAĞI SAYAMAZ ===")
# rows.get("X") çağrılarını kaynak koddan çıkar
CAGRI = re.compile(r'rows\.get\(\s*[\'"]([a-z0-9_]+)[\'"]')

for uye in roster.ROSTER:
    konusmaci = roster.SPEAKERS.get(uye.key)
    if konusmaci is None:
        continue
    try:
        kaynak_kod = inspect.getsource(konusmaci)
    except (OSError, TypeError):
        continue
    kullanilan = set(CAGRI.findall(kaynak_kod))
    # Yardımcı fonksiyon çağırıyorsa onun okuduklarını da ekle
    for ad in re.findall(r"\b(_[a-z_]+)\(rows\)", kaynak_kod):
        yardimci = getattr(roster, ad, None)
        if yardimci is not None:
            try:
                kullanilan |= set(CAGRI.findall(inspect.getsource(yardimci)))
            except (OSError, TypeError):
                pass
    bildirilen = set(getattr(uye, "reads", ()) or ())
    fazla = kullanilan - bildirilen
    bildir(not fazla, f"{uye.name[:40]:<40} okuduğu: {len(bildirilen)}",
           f"reads'te OLMAYAN kaynağı okuyor: {sorted(fazla)} — "
           "bu kaynak hiç gelmeyeceği için sıfır sayılır ve 'yok' diye "
           "raporlanır")

# =====================================================================
# B. Boş veriyle dolu veri aynı cümleyi üretemez
# =====================================================================
print()
print("=== B · BOŞ VERİ İLE DOLU VERİ AYNI CÜMLEYİ ÜRETEMEZ ===")
hafiza = CompanyMemory(host=None)
onbellek: dict[str, list] = {}


def oku(q: str) -> list:
    if q not in onbellek:
        try:
            onbellek[q] = list(hafiza._fetch(q).records)
        except Exception:  # noqa: BLE001
            onbellek[q] = []
    return onbellek[q]


sinanan = 0
for uye in roster.ROSTER:
    konusmaci = roster.SPEAKERS.get(uye.key)
    okur = tuple(getattr(uye, "reads", ()) or ())
    if konusmaci is None or not okur:
        continue
    dolu = {q: oku(q) for q in okur}
    if not any(dolu.values()):
        continue          # kaynağı gerçekten boş; bu sınav onu kapsamaz
    bos = {q: [] for q in okur}
    try:
        c_dolu, c_bos = konusmaci(dolu), konusmaci(bos)
    except Exception as e:  # noqa: BLE001
        bildir(False, f"{uye.name[:40]:<40} boş veriyle ÇÖKTÜ", str(e)[:90])
        continue
    sinanan += 1
    bildir(c_dolu != c_bos, f"{uye.name[:40]:<40} veriye tepki veriyor",
           "boş veri ile dolu veri AYNI cümleyi üretti — bu üye verisine "
           "bakmıyor, sabit cümle kuruyor")
print(f"  ({sinanan} üye sınandı)")

# =====================================================================
# C. Durum etiketleri ayrı kalmalı
# =====================================================================
print()
print("=== C · DURUM ETİKETLERİ BİRBİRİNDEN AYRI ===")
etiketler = {
    "SPEAKS": roster.SPEAKS,
    "NO_DATA": roster.NO_DATA,
    "NEEDS_RESEARCH": roster.NEEDS_RESEARCH,
    "NEEDS_INPUT": roster.NEEDS_INPUT,
}
if hasattr(roster, "ISLEV_YOK"):
    etiketler["ISLEV_YOK"] = roster.ISLEV_YOK
bildir(len(set(etiketler.values())) == len(etiketler),
       f"{len(etiketler)} durum etiketi, hepsi farklı",
       f"aynı metne düşen etiketler var: {etiketler}")
bildir("ISLEV_YOK" in etiketler,
       "'işlev yazılmadı' durumu ayrı bir etiket",
       "veri yokluğu ile işlev yokluğu aynı etikete düşüyor")

print()
print("SONUC:", "TUM KAPILAR GECTI" if hata == 0 else f"{hata} IHLAL")
if __name__ == "__main__":
    sys.exit(1 if hata else 0)

class DurumKapisiTests(unittest.TestCase):
    def test_all_evidence_and_status_gates_pass(self):
        self.assertEqual(0, hata, f"{hata} roster evidence/status violations")
