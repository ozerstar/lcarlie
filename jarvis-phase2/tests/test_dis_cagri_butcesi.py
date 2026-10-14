# -*- coding: utf-8 -*-
"""Dış çağrı bütçesi kapısı.

🔴 SEBEBİ ÖLÇÜLMÜŞ BİR OLAY: 25.09.2026'da tek bir iş (`kreatif_brief`)
günün 521 başarılı dış model çağrısının 400'ünü yaptı; önceki gün TOPLAM
55 çağrı vardı. Üstelik iş 5 saatlik zaman aşımına uğrayıp öldürüldü --
yani o çağrıların büyük kısmından çıktı bile alınmadı.

Bu sınamalar üç şeyi kilitler:
  1. Bütçe SAYMAYA dayanır, tahmine değil (telemetriden okunur).
  2. Telemetri okunamıyorsa bütçe UYGULANMAZ -- ölçüm hatasını hizmet
     kesintisine çevirmek, koruma değil yeni bir arıza olurdu.
  3. Kapı yalnız DIŞ sağlayıcıya uygulanır; yerel kademeler serbesttir.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

_GECICI = tempfile.mkdtemp(prefix="butce-test-")
os.environ["JARVIS_STATE_DIR"] = _GECICI

from jarvis import model_layer as ML  # noqa: E402


def _yaz(kayitlar: list) -> None:
    yol = Path(_GECICI) / "kademe.jsonl"
    with open(yol, "w", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")
    ML._butce_onbellek.update({"gun": None, "_taze": 0})


def _kayit(gun: str, kademe: str, sonuc: str, is_anahtari: str) -> dict:
    return {"ts": gun + "T10:00:00+0300", "kademe": kademe, "sonuc": sonuc,
            "is_anahtari": is_anahtari, "model": "x"}


class ButceTemeli(unittest.TestCase):
    def setUp(self):
        os.environ["JARVIS_STATE_DIR"] = _GECICI
        ML._butce_onbellek.update({"gun": None, "toplam": 0, "isler": {},
                                   "_taze": 0})
        self._butce = ML.DIS_CAGRI_BUTCESI
        self._is = ML.IS_BASINA_BUTCE

    def tearDown(self):
        ML.DIS_CAGRI_BUTCESI = self._butce
        ML.IS_BASINA_BUTCE = self._is


class SayacTelemetridenOkur(ButceTemeli):
    def test_yalniz_bugun_ve_yalniz_dis_basarili(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        _yaz([
            _kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "a"),
            _kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "a"),
            _kayit(bugun, "EXTERNAL_MODEL", "HATA", "a"),      # sayilmaz
            _kayit(bugun, "EXTERNAL_MODEL", "ATLANDI", "a"),   # sayilmaz
            _kayit(bugun, "LOCAL_GPU", "BASARILI", "a"),       # yerel: sayilmaz
            _kayit("2000-01-01", "EXTERNAL_MODEL", "BASARILI", "a"),  # dun
        ])
        s = ML.dis_cagri_sayaci()
        self.assertEqual(s["toplam"], 2)
        self.assertEqual(s["isler"], {"a": 2})

    def test_is_bazinda_ayrisir(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        _yaz([_kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "a")] * 3
             + [_kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "b")])
        s = ML.dis_cagri_sayaci()
        self.assertEqual(s["isler"]["a"], 3)
        self.assertEqual(s["isler"]["b"], 1)


class KapiDogruYerdeKapanir(ButceTemeli):
    def test_gunluk_butce_dolunca_kapanir(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        _yaz([_kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "a")] * 5)
        ML.DIS_CAGRI_BUTCESI = 5
        ML.IS_BASINA_BUTCE = 0
        self.assertIsNotNone(ML.butce_doldu_mu("b"))

    def test_is_basina_butce_yalniz_o_isi_kapatir(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        _yaz([_kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "kacak")] * 10)
        ML.DIS_CAGRI_BUTCESI = 1000
        ML.IS_BASINA_BUTCE = 10
        # Kacak is kapanir...
        self.assertIsNotNone(ML.butce_doldu_mu("kacak"))
        # ...ama baska isler CALISMAYA DEVAM EDER. Tek isin tasmasi butun
        # ajansi durdurmamali.
        self.assertIsNone(ML.butce_doldu_mu("baska"))

    def test_butce_sifir_ise_sinirsiz(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        _yaz([_kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "a")] * 999)
        ML.DIS_CAGRI_BUTCESI = 0
        self.assertIsNone(ML.butce_doldu_mu("a"))


class OlcumHatasiKesintiye_Cevrilmez(ButceTemeli):
    """Sayamamak, reddetmek için gerekçe değildir."""

    def test_telemetri_yoksa_butce_uygulanmaz(self):
        yol = Path(_GECICI) / "kademe.jsonl"
        if yol.exists():
            yol.unlink()
        ML._butce_onbellek.update({"gun": None, "_taze": 0})
        ML.DIS_CAGRI_BUTCESI = 1
        # Dosya yok -> toplam 0 -> kapi acik kalir
        self.assertIsNone(ML.butce_doldu_mu("a"))

    def test_bozuk_satir_okumayi_durdurmaz(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        yol = Path(_GECICI) / "kademe.jsonl"
        with open(yol, "w", encoding="utf-8") as f:
            f.write("{bozuk json\n")
            f.write(json.dumps(_kayit(bugun, "EXTERNAL_MODEL", "BASARILI", "a"))
                    + "\n")
        ML._butce_onbellek.update({"gun": None, "_taze": 0})
        self.assertEqual(ML.dis_cagri_sayaci()["toplam"], 1)


class YerelKademelerSerbest(ButceTemeli):
    """Sahip kararı 25.09.2026: 'API bütçesi yedirtme, CPU GPU RAM serbest'."""

    def test_kapi_yalniz_dis_kademeye_bakar(self):
        import inspect
        kaynak = inspect.getsource(ML.ModelRouter.generate)
        self.assertIn('kademe == "EXTERNAL_MODEL"', kaynak,
                      "butce kapisi yerel kademeleri de kapatiyor olabilir")

    def test_yerel_cagri_sayaca_girmez(self):
        import time
        bugun = time.strftime("%Y-%m-%d")
        _yaz([_kayit(bugun, "LOCAL_GPU", "BASARILI", "a")] * 50
             + [_kayit(bugun, "LOCAL_MODEL", "BASARILI", "a")] * 50)
        self.assertEqual(ML.dis_cagri_sayaci()["toplam"], 0)


if __name__ == "__main__":
    unittest.main()
