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


class AktarimTest(unittest.TestCase):
    """JSONL -> Postgres aktarimi: neyin gittigi ve neyin GITMEDIGI.

    🔴 Hedef tablo core.ai_provider_attempt DEGIL. O tabloyu
    mart.ai_provider_score okuyor ve "deneme" sayisi ile basari oranini
    ondan cikariyor; ATLANDI satirlari HIC DENENMEMIS kademeleri anlatir.
    Oraya yazmak, kapali duran bir makineyi "basarisiz saglayici" gibi
    gosterip mevcut yonlendirme skorlarini bozardi. Bu yuzden ayri tablo:
    core.kademe_denemesi.
    """

    def setUp(self):
        self._dizin = tempfile.TemporaryDirectory()
        self._onceki = os.environ.get("JARVIS_KADEME_LOG")
        self.gunluk = Path(self._dizin.name) / "kademe.jsonl"
        os.environ["JARVIS_KADEME_LOG"] = str(self.gunluk)

    def tearDown(self):
        if self._onceki is None:
            os.environ.pop("JARVIS_KADEME_LOG", None)
        else:
            os.environ["JARVIS_KADEME_LOG"] = self._onceki
        self._dizin.cleanup()

    def test_ayni_kayit_ayni_hash_farkli_kayit_farkli(self):
        """Tekrar calistirmak guvenli olmali: kimlik ICERIKTEN gelir.

        Filigran/ofset tutulsaydi dosya donduruldugunde yaniltirdi.
        """
        a = {"ts": "2026-09-24T21:00:00+0300", "uc": "external", "sonuc": "BASARILI"}
        b = {"sonuc": "BASARILI", "uc": "external", "ts": "2026-09-24T21:00:00+0300"}
        c = {"ts": "2026-09-24T21:00:01+0300", "uc": "external", "sonuc": "BASARILI"}
        self.assertEqual(kademe_kaydi.satir_hash(a), kademe_kaydi.satir_hash(b),
                         "anahtar sirasi kimligi degistiremez")
        self.assertNotEqual(kademe_kaydi.satir_hash(a), kademe_kaydi.satir_hash(c))

    def test_ts_ya_da_sonuc_yoksa_satir_gitmez(self):
        """NOT NULL sutuna bos deger gonderip BUTUN aktarimi dusurmemeli."""
        csv_metni = kademe_kaydi.aktarim_csv([
            {"ts": "2026-09-24T21:00:00+0300", "uc": "x", "sonuc": "BASARILI"},
            {"uc": "x", "sonuc": "BASARILI"},          # ts yok
            {"ts": "2026-09-24T21:00:00+0300", "uc": "x"},  # sonuc yok
        ])
        self.assertEqual(len([s for s in csv_metni.splitlines() if s.strip()]), 1)

    def test_tirnak_ve_virgul_kacisi(self):
        """Model adinda tirnak, gerekcede virgul olabilir -- elle kacis yazmak
        bu projede daha once bozulmus bir yontem."""
        csv_metni = kademe_kaydi.aktarim_csv([{
            "ts": "2026-09-24T21:00:00+0300", "uc": "x", "sonuc": "HATA",
            "model": 'a,b "tirnakli"', "gerekce": "bir, iki",
        }])
        import csv as _csv
        import io as _io
        satirlar = list(_csv.reader(_io.StringIO(csv_metni)))
        self.assertEqual(len(satirlar), 1)
        self.assertEqual(satirlar[0][3], 'a,b "tirnakli"')
        self.assertEqual(satirlar[0][6], "bir, iki")

    def test_sutun_sayisi_sabit(self):
        """COPY sutun sayisina gore hizalanir; kayan tek sutun her satiri bozar."""
        csv_metni = kademe_kaydi.aktarim_csv([
            {"ts": "2026-09-24T21:00:00+0300", "uc": "x", "sonuc": "BASARILI"},
            {"ts": "2026-09-24T21:00:01+0300", "uc": "y", "sonuc": "ATLANDI",
             "kademe": "LOCAL_GPU", "model": "m", "gecikme_ms": 5.5,
             "gerekce": "UNAVAILABLE", "deneme": 2, "escalate": True,
             "is_anahtari": "sohbet"},
        ])
        import csv as _csv
        import io as _io
        for satir in _csv.reader(_io.StringIO(csv_metni)):
            self.assertEqual(len(satir), len(kademe_kaydi.AKTARIM_SUTUNLARI))

    def test_eksik_alanlar_BOS_gider_sifir_degil(self):
        """Bos alan CSV'de bos kalir -> COPY onu NULL yapar.

        0 yazsaydik "gecikme olculmedi" ile "gecikme sifirdi" ayni gorunurdu.
        """
        import csv as _csv
        import io as _io
        csv_metni = kademe_kaydi.aktarim_csv([
            {"ts": "2026-09-24T21:00:00+0300", "uc": "x", "sonuc": "ATLANDI"}])
        satir = list(_csv.reader(_io.StringIO(csv_metni)))[0]
        self.assertEqual(satir[5], "", "gecikme_ms bos kalmali, 0 degil")
        self.assertEqual(satir[7], "", "deneme bos kalmali, 0 degil")

    def test_tum_kayitlar_eskiden_yeniye(self):
        kademe_kaydi.kaydet(uc="a", sonuc=kademe_kaydi.SONUC_BASARILI)
        kademe_kaydi.kaydet(uc="b", sonuc=kademe_kaydi.SONUC_BASARILI)
        hepsi = kademe_kaydi.tum_kayitlar()
        self.assertEqual([k["uc"] for k in hepsi], ["a", "b"],
                         "son_kayitlar YENIDEN eskiye, tum_kayitlar ESKIDEN yeniye")

    def test_bozuk_satir_aktarimi_durdurmaz(self):
        self.gunluk.parent.mkdir(parents=True, exist_ok=True)
        self.gunluk.write_text(
            '{"ts":"2026-09-24T21:00:00+0300","uc":"a","sonuc":"BASARILI"}\n'
            'bu json degil\n'
            '{"ts":"2026-09-24T21:00:01+0300","uc":"b","sonuc":"HATA"}\n',
            encoding="utf-8")
        self.assertEqual(len(kademe_kaydi.tum_kayitlar()), 2)

    def test_dosya_yoksa_bos(self):
        self.assertEqual(kademe_kaydi.tum_kayitlar(), [])
        self.assertEqual(kademe_kaydi.aktarim_csv([]), "")


if __name__ == "__main__":
    unittest.main()
