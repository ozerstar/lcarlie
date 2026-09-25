"""API once, yerel model yedek -- 24.09.2026'da sahip karariyla tersine dondu.

ESKI SOZLESME (artik gecersiz): masaustu GPU once gelirdi, kapaliysa sunucunun
kendi modeli cevaplardi ve "bir masaustu kapandi diye trafik disariya cikmasin"
kurali vardi. Gerekcesi hizdi.

NEDEN DEGISTI -- olculdu:
  gemini-3.5-flash-lite  0,63 sn · 0,30/2,50 USD/1M · 7 gunluk toplam 4,46 TL
  PC-2 RTX 5060          ~0,65 sn isinmis, ilk istekte 14 sn, gece kapali
  VDS CPU                7,45 jeton/sn -- bir paragraf ~30 sn
API hem hizli hem her zaman acik; yerel modelin bedeli para degil BAGIMLILIK
(tunel dusuyor, GPU'yu ComfyUI ile paylasmak gerekiyor).

Bu testler YENI sonucu civiler: API cevapliyorsa yerel kademeler hic
yoklanmaz; API dustugunde is DURMAZ, masaustune ve sonra sunucuya iner.
Yerel kademeler silinmedi -- bedava sigorta olarak duruyorlar.
"""
import os
import tempfile
import unittest

from jarvis.model_layer import (AdapterState, ModelRouter, ModelUnavailable,
                                TIER_EXTERNAL, TIER_GPU, TIER_LOCAL)


class _Provider:
    """Minimal stand-in: a tier, a health state, and an answer."""

    def __init__(self, name, tier, state=AdapterState.AVAILABLE, fails=False):
        self.name = name
        self.tier = tier
        self._state = state
        self._fails = fails
        self.calls = 0

    def state(self):
        return self._state

    def complete(self, messages, max_tokens):
        self.calls += 1
        if self._fails:
            raise OSError("provider down mid-request")
        return {"text": f"answer from {self.name}", "model": self.name}

    def stream(self, messages, max_tokens):
        self.calls += 1
        yield f"answer from {self.name}"


def _router(gpu_state=AdapterState.AVAILABLE, gpu_fails=False,
            external_state=AdapterState.AVAILABLE, external_fails=False):
    return ModelRouter(
        gpu=_Provider("gpu", TIER_GPU, gpu_state, gpu_fails),
        local=_Provider("local", TIER_LOCAL),
        external=_Provider("external", TIER_EXTERNAL, external_state,
                           external_fails))


MSG = [{"role": "user", "content": "Intimblanc nedir?"}]



class _UretimiKoru(unittest.TestCase):
    """🔴 Bu modul uretim telemetrisine YAZIYORDU.

    Olculdu 25.09.2026: kademe.jsonl'de `OSError: provider down mid-request`
    satirlari vardi -- kaynagi bu dosyanin 40. satirindaki test sahtesi.
    Yani dagitim sirasinda kosan testler, uretim OLCUM dosyasina sahte hata
    yaziyordu.

    Bu zararsiz bir kozmetik sorun DEGIL: panelin SISTEM sekmesindeki
    "model kademesi" gostergesi ve butun kademe analizi bu dosyadan
    okunuyor. Sahte hata, gercek ariza oranini sisirir ve yanlis teshise
    goturur -- nitekim 25.09'daki "66 OSError" sayimimin ne kadarinin
    gercek oldugu geriye donuk AYIRT EDILEMIYOR, cunku eski kayitlar
    sebep metni tasimiyordu.

    Ayni sinif kirlenme daha once de yasanmis (19 satir) ve
    test_kademe_kaydi.py'de bir koruma testi yazilmis; bu modul o
    korumanin disinda kalmis.
    """


class TelemetriIzolasyonu:
    """Her test sinifi icin: STATE_DIR gecici klasore alinir."""

    def setUp(self):
        self._eski_state = os.environ.get("JARVIS_STATE_DIR")
        self._eski_log = os.environ.pop("JARVIS_KADEME_LOG", None)
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["JARVIS_STATE_DIR"] = self._tmp.name
        super().setUp()

    def tearDown(self):
        super().tearDown()
        if self._eski_state is None:
            os.environ.pop("JARVIS_STATE_DIR", None)
        else:
            os.environ["JARVIS_STATE_DIR"] = self._eski_state
        if self._eski_log is not None:
            os.environ["JARVIS_KADEME_LOG"] = self._eski_log
        self._tmp.cleanup()


class ApiFirstTest(TelemetriIzolasyonu, unittest.TestCase):

    def test_api_answers_and_local_rungs_are_never_touched(self):
        """Asil kazanc burada: masaustu ACIK olsa bile yoklanmaz."""
        router = _router()
        _result, tier, _calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_EXTERNAL)
        self.assertEqual(router.gpu.calls, 0)
        self.assertEqual(router.local.calls, 0)

    def test_api_down_falls_back_to_the_desktop(self):
        """Yerel kademeler sigorta: API dustugunde is DURMAZ."""
        router = _router(external_state=AdapterState.UNAVAILABLE)
        _result, tier, _calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_GPU)
        self.assertEqual(router.local.calls, 0)

    def test_api_and_desktop_down_leaves_the_always_on_server(self):
        router = _router(external_state=AdapterState.UNAVAILABLE,
                         gpu_state=AdapterState.UNAVAILABLE)
        _result, tier, _calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_LOCAL)

    def test_api_dies_mid_request_and_the_desktop_finishes_the_job(self):
        """Saglik "evet" dedi, istek ile cevap arasinda dustu."""
        router = _router(external_fails=True)
        result, tier, calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_GPU)
        self.assertEqual(result["text"], "answer from gpu")
        self.assertEqual(calls, 2)

    def test_escalation_still_means_the_external_model(self):
        # Both local rungs run the same 4B weights: the GPU is a speed tier,
        # not a capability tier, so "this needs a stronger model" still leaves.
        router = _router()
        _result, tier, _calls = router.generate(MSG, 64, escalate=True)
        self.assertEqual(tier, TIER_EXTERNAL)

    def test_chain_is_api_first_and_escalate_no_longer_reorders(self):
        """escalate artik SIRAYI degistirmiyor -- dis saglayici zaten basta.

        Anlami daraldi: yalnizca "ucretli modele kadar inebilirsin" demek.
        Sira ikiye ayrilmadigi icin iki cagri da ayni listeyi vermeli; aksi
        halde escalate sessizce yerel kademeleri one alirdi.
        """
        router = _router()
        self.assertEqual([p.name for p in router._chain(False)],
                         ["external", "gpu", "local"])
        self.assertEqual([p.name for p in router._chain(True)],
                         ["external", "gpu", "local"])

    def test_states_report_all_three_rungs(self):
        router = _router(gpu_state=AdapterState.UNAVAILABLE)
        self.assertEqual(router.provider_states(),
                         {"gpu": "UNAVAILABLE", "local": "AVAILABLE",
                          "external": "AVAILABLE"})

    def test_everything_down_is_an_error_not_a_silent_empty_answer(self):
        router = ModelRouter(
            gpu=_Provider("gpu", TIER_GPU, AdapterState.UNAVAILABLE),
            local=_Provider("local", TIER_LOCAL, AdapterState.UNAVAILABLE),
            external=_Provider("external", TIER_EXTERNAL, AdapterState.UNAVAILABLE))
        with self.assertRaises(ModelUnavailable):
            router.generate(MSG, 64)


class StreamingFollowsTheSameOrderTest(TelemetriIzolasyonu, unittest.TestCase):

    def test_streaming_prefers_the_gpu(self):
        router = _router()
        out = "".join(router.stream_text("Intimblanc nedir?", "sistem"))
        self.assertEqual(out, "answer from gpu")
        self.assertEqual(router.local.calls, 0)

    def test_streaming_falls_back_when_the_desktop_is_off(self):
        router = _router(gpu_state=AdapterState.UNAVAILABLE)
        out = "".join(router.stream_text("Intimblanc nedir?", "sistem"))
        self.assertEqual(out, "answer from local")


class SuppliedProviderKeepsItsIdentityTest(TelemetriIzolasyonu, unittest.TestCase):

    def test_injected_gpu_is_not_renamed(self):
        # The router labels the provider it builds itself; one handed in by a
        # caller (or a test) keeps the name and tier it arrived with.
        mine = _Provider("custom", "CUSTOM_TIER")
        router = ModelRouter(gpu=mine)
        self.assertEqual(router.gpu.name, "custom")
        self.assertEqual(router.gpu.tier, "CUSTOM_TIER")


class CevaplayanModel(TelemetriIzolasyonu, unittest.TestCase):
    """Telemetri, cevabi VEREN modeli yazmali.

    Eski hali saglayici nesnesinin yapilandirilmis modelini yaziyordu ve
    bu, cagri yapilmadan once okunuyordu. Dis saglayici kendi icinde bir
    zincir isletiyor, dolayisiyla cevabi genellikle baska bir model
    veriyor. Uretimde olculdu (25.09.2026): cevap
    gemini/gemini-3.5-flash-lite'dan geldi, telemetriye
    nvidia/nemotron-3-super-120b-a12b:free yazildi.

    Yanlis model adi = yanlis maliyet analizi. Bu alan "hangi model
    calisiyor" ve "ne kadar ucretli cagri gitti" sorularinin TEK kaynagi.
    """

    def test_sonuctaki_model_yazilir(self):
        from jarvis.model_layer import _cevaplayan_model
        self.assertEqual(
            _cevaplayan_model({"model": "gemini/gemini-3.5-flash-lite"},
                              "nvidia/yapilandirilmis"),
            "gemini/gemini-3.5-flash-lite")

    def test_sonuc_model_tasimiyorsa_YAPILANDIRILMISA_duser(self):
        from jarvis.model_layer import _cevaplayan_model
        self.assertEqual(_cevaplayan_model({}, "yerel/qwen3-4b"), "yerel/qwen3-4b")
        self.assertEqual(_cevaplayan_model({"model": None}, "yerel/qwen3-4b"),
                         "yerel/qwen3-4b")

    def test_sonuc_sozluk_degilse_PATLAMAZ(self):
        from jarvis.model_layer import _cevaplayan_model
        for tuhaf in (None, "metin", 42, [1, 2]):
            self.assertEqual(_cevaplayan_model(tuhaf, "yedek"), "yedek")

    def test_cok_uzun_ad_kirpilir(self):
        from jarvis.model_layer import _cevaplayan_model
        uzun = "a" * 500
        self.assertLessEqual(len(_cevaplayan_model({"model": uzun}, None)), 120)


if __name__ == "__main__":
    unittest.main()
