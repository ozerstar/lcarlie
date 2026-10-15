# -*- coding: utf-8 -*-
"""Akan sohbet DIS saglayicidan gelir ve modelini dogru bildirir.

BU TESTLER BIR OLCUMDEN DOGDU -- 16.10.2026.
`stream_text` yalniz GPU/yerel saglayiciyi akitabiliyordu. Dis saglayici akis
bilmedigi icin sohbet SESSIZCE yerel 4B modele dusuyordu: panelde 98 token
cercevesi geliyordu ama cevabi `Qwen3-4B` veriyordu, Claude degil. Sahibin
"cevaplar kotu" ve "yavas" sikayetlerinin tek sebebi buydu -- `_chat` yolundaki
kademe duzeltmesi panelin GERCEKTE kullandigi akan yola hic ugramiyordu.

Ustelik `stream_chat` modeli kim cevaplarsa cevaplasin `LOCAL_MODEL_NAME` diye
bildiriyordu; panel yanlis model soyluyordu.

Olculen sonuc: ilk parca 0,70 sn, model claude/claude-haiku-4-5-20251001.
"""
import unittest

from jarvis.model_layer import AdapterState, ModelRouter


class SahteAkitici:
    """providers.stream yerine gecer; hangi kademeyle cagrildigini kaydeder."""

    def __init__(self, parcalar=("Mer", "haba"), patla=False):
        self.parcalar, self.patla, self.cagrildi = parcalar, patla, 0
        self.son_kademe = None

    def __call__(self, messages, max_tokens=400, kademe=None, env=None):
        self.cagrildi += 1
        self.son_kademe = kademe
        if self.patla:
            raise RuntimeError("dis akis dustu")
        yield from self.parcalar


class SahteYerel:
    def __init__(self, durum=AdapterState.AVAILABLE):
        self._durum, self.cagrildi = durum, 0
        self.model = "YEREL-4B"

    def state(self):
        return self._durum

    def stream(self, messages, max_tokens):
        self.cagrildi += 1
        yield "yerel"


class _Temel(unittest.TestCase):
    """providers modulune yapilan yamalar HER durumda geri alinir.

    Geri almamak, sonraki test dosyalarina sahte saglayici sizdirirdi ve
    kirmizinin sebebi bu dosya oldugu halde baska yerde gorunurdu.
    """

    def setUp(self):
        self.r = ModelRouter(local=SahteYerel(), external=SahteYerel(),
                             gpu=SahteYerel())
        from jarvis import providers
        self.providers = providers
        self._eski_stream = providers.stream
        self._eski_model = providers.son_akis_modeli

    def tearDown(self):
        self.providers.stream = self._eski_stream
        self.providers.son_akis_modeli = self._eski_model

    def yama(self, akitici, model="claude/claude-haiku-4-5-20251001"):
        self.providers.stream = akitici
        self.providers.son_akis_modeli = lambda: model
        return akitici


class DIS_SAGLAYICI_ONCE(_Temel):
    def test_dis_akis_varsa_YEREL_CAGRILMAZ(self):
        self.yama(SahteAkitici())
        self.assertEqual("".join(self.r.stream_text("selam", "sistem")),
                         "Merhaba")
        self.assertEqual(self.r.gpu.cagrildi, 0, "dis akis varken GPU cagrilmis")
        self.assertEqual(self.r.local.cagrildi, 0)

    def test_model_adi_DIS_saglayicidan_okunur(self):
        self.yama(SahteAkitici())
        list(self.r.stream_text("selam", "sistem"))
        self.assertEqual(self.r.son_akis_modeli,
                         "claude/claude-haiku-4-5-20251001")

    def test_escalate_MUHAKEME_kademesine_cevrilir(self):
        sahte = self.yama(SahteAkitici())
        list(self.r.stream_text("selam", "sistem", escalate=True))
        self.assertEqual(sahte.son_kademe, "muhakeme")

    def test_escalate_yoksa_kademe_varsayilan(self):
        sahte = self.yama(SahteAkitici())
        list(self.r.stream_text("selam", "sistem", escalate=False))
        self.assertIsNone(sahte.son_kademe)


class DIS_DUSERSE_YERELE_INILIR(_Temel):
    def test_dis_hic_uretmeden_duserse_yerel_calisir(self):
        self.yama(SahteAkitici(patla=True))
        self.assertEqual("".join(self.r.stream_text("selam", "sistem")),
                         "yerel")
        self.assertEqual(self.r.gpu.cagrildi, 1)

    def test_yerel_cevaplayinca_model_adi_YEREL(self):
        self.yama(SahteAkitici(patla=True))
        list(self.r.stream_text("selam", "sistem"))
        self.assertEqual(self.r.son_akis_modeli, "YEREL-4B")


class YARIM_CEVAP_BIRLESTIRILMEZ(_Temel):
    """Dis saglayici YAZMAYA BASLADIKTAN sonra duserse, kalani baska modelden
    tamamlamak iki agzi birbirine karistirmak olur: musteri yarim cumleyi bir
    modelden, devamini bambaska bir modelden okur."""

    def test_yarida_dusen_akis_yerelle_tamamlanmaz(self):
        def yarim(messages, max_tokens=400, kademe=None, env=None):
            yield "Mer"
            raise RuntimeError("koptu")

        self.yama(yarim)
        self.assertEqual("".join(self.r.stream_text("selam", "sistem")), "Mer")
        self.assertEqual(self.r.gpu.cagrildi, 0,
                         "yarim cevap yerelle tamamlanmis")


if __name__ == "__main__":
    unittest.main()
