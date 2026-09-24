#!/usr/bin/env python3
"""Kademe telemetrisi — ne yazıldığı değil, NE AYIRT EDİLDİĞİ sınanır.

🔴 NEDEN VAR. 24.09.2026'da sunucu yeniden başladı, PC-2'nin ters tüneli
düştü ve sistem 65 jeton/sn yerine 7,45 jeton/sn kademede koşmaya devam etti.
Dokuz kat yavaşlama. Panel görmedi, alarm çalmadı — çünkü hangi kademenin
cevap verdiğini hiçbir yer kaydetmiyordu.

Asıl risk, kaydın hiç tutulmaması değil; kapalı makine ile arızalı makinenin
aynı satıra yazılması. O zaman panel "GPU çalışmıyor" der, biz de gece kapanan
bir kutuyu arıza sanıp yanlış yere bakarız. Bu, durum ayrımı sınavındaki kök
hatanın aynısıdır: bir yokluğu sebebini bilmeden cümleye çevirmek.

Dört durum birbirinden ayrı tutulur:
  BASARILI         cevabı bu kademe üretti
  HATA             kademe denendi ve düştü (makine açık, cevap veremedi)
  ATLANDI          kademe hiç denenmedi (makine kapalı — arıza DEĞİL)
  ZINCIR_TUKENDI   hiçbir kademe cevap veremedi (sessiz kalmamalı)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import kademe_kaydi  # noqa: E402
from jarvis.adapter_factory import AdapterState  # noqa: E402
from jarvis.model_layer import ModelRouter, ModelUnavailable  # noqa: E402


class SahteSaglayici:
    """Gerçek sağlayıcı sözleşmesinin sınanan yüzeyi."""

    def __init__(self, ad, kademe, durum, cevap=None, patlat=None):
        self.name = ad
        self.tier = kademe
        self.model = ad + "-model"
        self._durum = durum
        self._cevap = cevap
        self._patlat = patlat

    def state(self):
        return self._durum

    def complete(self, messages, max_tokens):
        if self._patlat is not None:
            raise self._patlat
        return self._cevap


class KademeKaydiTest(unittest.TestCase):

    def setUp(self):
        self._dizin = tempfile.TemporaryDirectory()
        self._onceki = os.environ.get("JARVIS_KADEME_LOG")
        self.gunluk = Path(self._dizin.name) / "alt" / "kademe.jsonl"
        os.environ["JARVIS_KADEME_LOG"] = str(self.gunluk)

    def tearDown(self):
        if self._onceki is None:
            os.environ.pop("JARVIS_KADEME_LOG", None)
        else:
            os.environ["JARVIS_KADEME_LOG"] = self._onceki
        self._dizin.cleanup()

    def oku(self):
        if not self.gunluk.exists():
            return []
        return [json.loads(s) for s in
                self.gunluk.read_text(encoding="utf-8").splitlines() if s.strip()]

    @staticmethod
    def yol(gpu, local, external):
        return ModelRouter(gpu=gpu, local=local, external=external)

    @staticmethod
    def kapali(ad, kademe):
        return SahteSaglayici(ad, kademe, AdapterState.UNAVAILABLE)

    def test_basarili_kademe_yazilir(self):
        gpu = SahteSaglayici("gpu", "LOCAL_GPU", AdapterState.AVAILABLE,
                             cevap={"text": "tamam"})
        self.yol(gpu, self.kapali("local", "LOCAL_MODEL"),
                 self.kapali("external", "EXTERNAL_MODEL")
                 ).generate([{"role": "user", "content": "selam"}], 32)

        basarili = [k for k in self.oku()
                    if k["sonuc"] == kademe_kaydi.SONUC_BASARILI]
        self.assertEqual(len(basarili), 1)
        self.assertEqual(basarili[0]["uc"], "gpu")
        self.assertEqual(basarili[0]["kademe"], "LOCAL_GPU")
        self.assertIsInstance(basarili[0]["gecikme_ms"], (int, float))

    def test_kapali_makine_ATLANDI_yazilir_HATA_degil(self):
        gpu = self.kapali("gpu", "LOCAL_GPU")
        local = SahteSaglayici("local", "LOCAL_MODEL", AdapterState.AVAILABLE,
                               cevap={"text": "vds cevapladi"})
        self.yol(gpu, local, self.kapali("external", "EXTERNAL_MODEL")
                 ).generate([{"role": "user", "content": "selam"}], 32)

        kayitlar = self.oku()
        gpu_kaydi = [k for k in kayitlar if k["uc"] == "gpu"]
        self.assertEqual(len(gpu_kaydi), 1)
        self.assertEqual(gpu_kaydi[0]["sonuc"], kademe_kaydi.SONUC_ATLANDI)
        self.assertNotEqual(gpu_kaydi[0]["sonuc"], kademe_kaydi.SONUC_HATA)
        self.assertTrue(gpu_kaydi[0]["gerekce"])
        yerel = [k for k in kayitlar if k["uc"] == "local"][0]
        self.assertEqual(yerel["sonuc"], kademe_kaydi.SONUC_BASARILI)

    def test_acik_ama_dusen_kademe_HATA_yazilir(self):
        gpu = SahteSaglayici("gpu", "LOCAL_GPU", AdapterState.AVAILABLE,
                             patlat=TimeoutError("zaman asimi"))
        local = SahteSaglayici("local", "LOCAL_MODEL", AdapterState.AVAILABLE,
                               cevap={"text": "yedek"})
        self.yol(gpu, local, self.kapali("external", "EXTERNAL_MODEL")
                 ).generate([{"role": "user", "content": "selam"}], 32)

        gpu_kaydi = [k for k in self.oku() if k["uc"] == "gpu"][0]
        self.assertEqual(gpu_kaydi["sonuc"], kademe_kaydi.SONUC_HATA)
        self.assertEqual(gpu_kaydi["gerekce"], "TimeoutError")

    def test_zincir_tukenirse_yazilir(self):
        with self.assertRaises(ModelUnavailable):
            self.yol(self.kapali("gpu", "LOCAL_GPU"),
                     self.kapali("local", "LOCAL_MODEL"),
                     self.kapali("external", "EXTERNAL_MODEL")
                     ).generate([{"role": "user", "content": "selam"}], 32)

        kayitlar = self.oku()
        self.assertTrue(any(k["sonuc"] == kademe_kaydi.SONUC_ZINCIR_TUKENDI
                            for k in kayitlar))
        self.assertEqual(
            len([k for k in kayitlar
                 if k["sonuc"] == kademe_kaydi.SONUC_ATLANDI]), 3)

    def test_yazma_hatasi_cevabi_dusurmez(self):
        os.environ["JARVIS_KADEME_LOG"] = "/proc/olmayan/dizin/kademe.jsonl"
        gpu = SahteSaglayici("gpu", "LOCAL_GPU", AdapterState.AVAILABLE,
                             cevap={"text": "yine de cevap"})
        sonuc, kademe, _ = self.yol(
            gpu, self.kapali("local", "LOCAL_MODEL"),
            self.kapali("external", "EXTERNAL_MODEL"),
        ).generate([{"role": "user", "content": "selam"}], 32)
        self.assertEqual(sonuc, {"text": "yine de cevap"})
        self.assertEqual(kademe, "LOCAL_GPU")

    def test_ozet_eksik_alani_baska_uca_yazmaz(self):
        kademe_kaydi.kaydet(uc="gpu", sonuc=kademe_kaydi.SONUC_BASARILI,
                            gecikme_ms=120.0)
        kademe_kaydi.kaydet(uc="gpu", sonuc=kademe_kaydi.SONUC_ATLANDI)
        kademe_kaydi.kaydet(sonuc=kademe_kaydi.SONUC_HATA)

        ozet = kademe_kaydi.ozet(kademe_kaydi.son_kayitlar(50))
        self.assertEqual(ozet["toplam"], 3)
        self.assertEqual(ozet["dagilim"]["gpu"][kademe_kaydi.SONUC_BASARILI], 1)
        self.assertEqual(ozet["dagilim"]["gpu"][kademe_kaydi.SONUC_ATLANDI], 1)
        self.assertIn("bilinmiyor", ozet["dagilim"])
        self.assertEqual(ozet["ortalama_gecikme_ms"]["gpu"], 120.0)

    def test_son_kayitlar_yeniden_eskiye(self):
        kademe_kaydi.kaydet(uc="gpu", sonuc=kademe_kaydi.SONUC_ATLANDI)
        kademe_kaydi.kaydet(uc="local", sonuc=kademe_kaydi.SONUC_BASARILI)
        self.assertEqual(kademe_kaydi.son_kayitlar(50)[0]["uc"], "local")

    def test_dosya_yoksa_bos_liste(self):
        self.assertEqual(kademe_kaydi.son_kayitlar(50), [])
        self.assertEqual(kademe_kaydi.ozet([])["toplam"], 0)


if __name__ == "__main__":
    unittest.main()
