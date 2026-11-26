"""AJANLAR sayfasi hiz kilidi (26.11.2026).

Olcum: /api/panel/ajanlar 11-16 sn suruyordu. Iki sebep vardi:
  1. ekip gorusleri (roster.opinions, 47 sorgu) ayni istekte IKI KEZ
     hesaplaniyordu (_team_opinions + _team_by_department);
  2. sorgular SIRAYLA okunuyordu; en yavas uc gorunum toplamin yarisiydi.
Bu testler ikisinin geri gelmesini engeller. Veri onbelleklenmez: her
istek yeniden okur, yalniz ayni istek icinde ayni sorgu bir kez gider.
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
from jarvis import roster  # noqa: E402


class SayanBellek:
    """Her sorguyu sayan, istenirse bekleyen sahte sirket bellegi."""

    def __init__(self, gecikme: float = 0.0, bozuk: tuple = ()):
        self.gecikme = gecikme
        self.bozuk = set(bozuk)
        self.sayac: dict = {}
        self._kilit = threading.Lock()
        self.ayni_anda = 0
        self.en_cok_ayni_anda = 0

    def _fetch(self, query):
        with self._kilit:
            self.sayac[query] = self.sayac.get(query, 0) + 1
            self.ayni_anda += 1
            self.en_cok_ayni_anda = max(self.en_cok_ayni_anda, self.ayni_anda)
        try:
            if self.gecikme:
                time.sleep(self.gecikme)
            if query in self.bozuk:
                raise RuntimeError("okunamadi: " + query)
            kayit = [{"kod": "X", "ad": "X"}] if query == "departments" else []
            return SimpleNamespace(source=f"postgres:{query}",
                                   authority="CANONICAL_COMPANY_MEMORY",
                                   records=kayit)
        finally:
            with self._kilit:
                self.ayni_anda -= 1


class AjanlarTekHesapTests(unittest.TestCase):
    def test_gorusler_bir_kez_ve_her_sorgu_bir_kez_okunur(self):
        bellek = SayanBellek()
        gercek = roster.opinions
        cagri = []

        def sayan_opinions(memory, *a, **k):
            cagri.append(1)
            return gercek(memory, *a, **k)

        with patch.object(app, "_memory", bellek), \
             patch.object(roster, "opinions", sayan_opinions):
            sonuc = app._panel_ajanlar()
        self.assertEqual(len(cagri), 1, "ekip gorusleri istekte bir kez hesaplanmali")
        tekrar = {q: n for q, n in bellek.sayac.items() if n > 1}
        self.assertEqual(tekrar, {}, f"ayni istekte tekrar okunan sorgu: {tekrar}")
        self.assertIn("departments", bellek.sayac)
        # Yanit sozlesmesi degismedi.
        for alan in ("team", "departmanlar", "role_reality", "roles",
                     "providers", "engines"):
            self.assertIn(alan, sonuc)
        self.assertTrue(sonuc["team"])

    def test_sorgular_paralel_okunur(self):
        # 47 sorgu x 0,1 sn sirali = ~4,7 sn; paralelde ~0,6 sn.
        bellek = SayanBellek(gecikme=0.1)
        with patch.object(app, "_memory", bellek):
            basla = time.perf_counter()
            app._panel_ajanlar()
            sure = time.perf_counter() - basla
        self.assertGreater(bellek.en_cok_ayni_anda, 1, "sorgular sirayla okunuyor")
        sirali = 0.1 * len(bellek.sayac)
        self.assertLess(sure, sirali / 3,
                        f"{sure:.2f} sn; sirali okuma ~{sirali:.1f} sn olurdu")

    def test_okunamayan_sorgu_gizlenmez(self):
        sorgular = app._team_queries()
        bozuk = next(q for q in sorgular if q != "departments")
        bellek = SayanBellek(bozuk=(bozuk,))
        sarili = app._OnceFetchedMemory(bellek, sorgular)
        with self.assertRaises(RuntimeError):
            sarili._fetch(bozuk)
        # Hata da onbelleklenmez, istek disina tasinmaz: yeni istek yeniden okur.
        app._OnceFetchedMemory(bellek, [bozuk])
        self.assertEqual(bellek.sayac[bozuk], 2)

    def test_listede_olmayan_sorgu_dogrudan_okunur(self):
        bellek = SayanBellek()
        sarili = app._OnceFetchedMemory(bellek, [])
        sarili._fetch("system")
        sarili._fetch("system")
        self.assertEqual(bellek.sayac["system"], 1)


class PanelRoluJitKapaliTests(unittest.TestCase):
    """mart.ekonomi_gunluk 943 ms'nin 860 ms'i JIT derlemesiydi (26.11 olcum).

    Goc 082 panel rolunde JIT'i kapatir. Bu test gocun ve yalniz panel
    rolunu hedefledigini kilitler (n8n gibi baska rollere dokunmaz).
    """

    def test_goc_082_yalniz_panel_rolunde_jit_kapatir(self):
        goc = (Path(__file__).resolve().parents[2] / "migrations"
               / "082_jarvis_web_jit_kapali.sql")
        komutlar = [s.strip() for s in goc.read_text(encoding="utf-8").splitlines()
                    if s.strip() and not s.strip().startswith("--")]
        self.assertEqual(komutlar, ["ALTER ROLE jarvis_web SET jit = off;"])


if __name__ == "__main__":
    unittest.main()
