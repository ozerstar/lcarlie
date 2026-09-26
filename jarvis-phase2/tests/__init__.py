"""Test paketi ortak yardimcilari.

NEDEN BU DOSYA VAR
  1) Dizini paket yapar; test modulleri birbirini duz adla ice aktarabilsin
     diye TESTS_DIR de sys.path'e eklenir.
  2) Testler 3.11+ olan TestCase.enterContext'e yazilmisti. EnterContextMixin
     ayni isi 3.10'da addCleanup ile kurar; 3.11+ ortamda stdlib'in gercek
     metodu devreye girer, davranis birebir korunur.
  3) Bazi testler betikleri mutlak /opt/lcarlie yolundan yukluyordu.
     betik_yolu() once repo agacina bakar, bulamazsa eski mutlak yola duser --
     boylece uretim agacinda davranis degismez.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PAKET_KOK = TESTS_DIR.parent
URETIM_KOK = Path("/opt/lcarlie/jarvis-phase2")

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))


def betik_yolu(ad: str) -> str:
    """scripts/<ad> icin once repo agacini, sonra uretim agacini dener."""
    aday = PAKET_KOK / "scripts" / ad
    if aday.is_file():
        return str(aday)
    uretim = URETIM_KOK / "scripts" / ad
    if uretim.is_file():
        return str(uretim)
    return str(aday)


_ENTERCONTEXT_MEVCUT = hasattr(unittest.TestCase, "enterContext")


class EnterContextMixin:
    """3.11+ ortamda stdlib metodu; 3.10'da addCleanup ile ayni davranis."""

    if _ENTERCONTEXT_MEVCUT:
        enterContext = unittest.TestCase.enterContext  # type: ignore[attr-defined]
    else:
        def enterContext(self, cm):  # type: ignore[misc]
            sonuc = cm.__enter__()
            self.addCleanup(cm.__exit__, None, None, None)
            return sonuc
