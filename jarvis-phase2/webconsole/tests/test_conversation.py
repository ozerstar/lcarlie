import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

# Durum dizini, conversation (ve onunla gelen conversation_memory) ICE
# AKTARILMADAN ONCE gecici bir klasore alinir. Sirasi onemli:
# conversation_memory STATE_DIR'i modul yuklenirken bir kez okur, sonra
# degistirmek bir ise yaramaz.
#
# Bu dosya discover sirasinda ALFABETIK OLARAK ILK gelen test modulu;
# burada izole edilmezse butun surec uretim dizinine baglaniyor ve
# arkadan gelen modullerin kendi ayari gec kaliyor. 20.09.2026'da tam
# bunun yuzunden uretim sohbet dokumunun 369 satiri test fixture'i oldu
# ve model onlari baglamdan okuyup taklit etti.
os.environ.setdefault("JARVIS_STATE_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))

import conversation


class Evidence:
    def __init__(self, source, records): self.source, self.records = source, records


class Memory:
    def __init__(self): self.calls = []
    def _fetch(self, name):
        self.calls.append(name)
        data = {
            "crm_unanswered": [{"bekleme_saat": 12.5}, {"bekleme_saat": 3}],
            "sales_orders": [{"olcumde": True, "ciro_dogrulanmis_net": 100}],
            "advertising_performance": [{"pencere": 30, "harcama": 50}],
        }
        return Evidence("postgres:" + name, data[name])
    def get_executive_brief(self):
        self.calls.append("company_dashboard")
        return Evidence("postgres:company_dashboard", [{"proposed": 2, "approved": 3,
            "red_team_pending": 0, "unsafe_external_actions": 0}])


class Runtime:
    def __init__(self):
        self.runtime = type("Phase", (), {})()
        self.runtime.compiler = type("Compiler", (), {})()
        self.runtime.compiler.memory = Memory()


import contextlib
from unittest.mock import patch

from jarvis.adapter_factory import AdapterState


@contextlib.contextmanager
def _no_providers():
    """Force every model provider UNAVAILABLE, so the fail-closed path is
    exercised on purpose rather than by accident of the environment."""
    with patch("jarvis.model_layer.LocalProvider.state",
               return_value=AdapterState.UNAVAILABLE), \
         patch("jarvis.model_layer.ExternalProvider.state",
               return_value=AdapterState.UNAVAILABLE):
        yield


class Tests(unittest.TestCase):
    def test_simple(self):
        # A greeting is a real conversational turn now. It may cost a model
        # call; what must never change is that it takes no action.
        with _no_providers():
            result = conversation.route("Merhaba, sen ne yapabiliyorsun?", Runtime())
        self.assertEqual(("SIMPLE_CONVERSATION", "ANSWERED", 0),
                         (result["intent"], result["status"], result["model_calls"]))
        self.assertEqual(0, result["external_actions"])
        self.assertTrue(result["answer"])
    def test_crm_minimal_query(self):
        rt = Runtime(); result = conversation.route("Şirkette cevapsız müşteri var mı?", rt)
        self.assertEqual(["crm_unanswered"], rt.runtime.compiler.memory.calls)
        self.assertEqual(["postgres:crm_unanswered"], result["evidence_refs"])
        self.assertIn("2 cevapsız", result["answer"])
    def test_domains(self):
        self.assertEqual("sales", conversation.classify("kaç siparişimiz var").domain)
        self.assertEqual("advertising", conversation.classify("reklam harcamamız ne durumda").domain)
    def test_analysis_handoff(self):
        # "analiz et" is open-ended wording, so it now reaches synthesis. With
        # both providers forced down it must still answer from the
        # deterministic planner path rather than failing.
        with _no_providers():
            result = conversation.route("Satışlarımızı analiz et.", Runtime())
        self.assertIn(result["status"], ("PROPOSED", "AI_PROVIDER_UNAVAILABLE"))
        self.assertEqual(0, result["external_actions"])
    def test_research_is_honest_about_its_confidence(self):
        """Research runs for real now. Whatever it finds, it must never present
        a thin result as fact, and it must never fabricate a source."""
        result = conversation.route("Rakiplerimizi araştır.", Runtime())
        self.assertEqual("RESEARCH_REQUEST", result["intent"])
        # TIMEOUT da DURUST bir sonuctur ve listeye 20.09.2026'da eklendi:
        # arastirma artik gercekten calisiyor (Gemini grounding), yani agdan
        # sayfa indiriyor ve 45 sn'lik kaynak butcesini asabiliyor. O durumda
        # verilen cevap "Arastirma tamamlanamadi... bu, konuda kaynak olmadigi
        # anlamina GELMEZ" -- ince bir sonucu olgu gibi sunmuyor, kaynak da
        # uydurmuyor, yani bu testin korudugu iki kurali da cigneMIYOR.
        # Listeye alinmazsa test sinirda rastgele kirilir ve dagitim kapisini
        # kilitler.
        self.assertIn(result["status"],
                      ("ANSWERED", "LOW_CONFIDENCE", "DATA_UNAVAILABLE", "TIMEOUT"))
        self.assertEqual(0, result["external_actions"])
        if result["status"] == "ANSWERED":
            self.assertTrue(result["evidence_refs"])
    def test_action_proposed_only(self):
        result = conversation.route("Vireon fiyatını değiştir.", Runtime())
        self.assertEqual("ACTION_REQUEST", result["intent"]); self.assertEqual(0, result["external_actions"])
        self.assertTrue(result["approval_required"]); self.assertFalse(result["execution_started"])
        self.assertEqual("BLOCKED_EXTERNAL_ACTION", result["plan"]["status"])
    def test_provider_unavailable_fails_closed_not_silent(self):
        """Every provider down must degrade, never crash and never fabricate.

        An analysis request now falls back to the specialists' own deterministic
        findings rather than to silence, so the answer survives the model being
        gone -- it just stops being a narrative.
        """
        with _no_providers():
            analysis = conversation.route(
                "Cevapsız müşteri probleminin nedenlerini değerlendir", Runtime())
            general = conversation.route("Bana yaratıcı bir fikir ver", Runtime())
        for result in (analysis, general):
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(0, result["external_actions"])
            self.assertTrue(result["answer"])
        self.assertEqual("PROPOSED", analysis["status"])
        # Chat degrades to the deterministic introduction rather than silence.
        self.assertEqual("ANSWERED", general["status"])

    def test_counting_question_never_calls_a_model(self):
        result = conversation.route("Kaç cevapsız müşterimiz var?", Runtime())
        self.assertEqual(0, result["model_calls"])
        self.assertEqual("deterministic-local", result["model"])
    def test_contract(self):
        result = conversation.route("merhaba", Runtime())
        for key in ("request_id", "intent", "status", "answer", "evidence_refs", "missing_data",
                    "duration_ms", "model", "model_calls"): self.assertIn(key, result)
    def test_voice_same_boundary(self):
        result = conversation.route("Şirkette en önemli problem ne?", Runtime())
        self.assertEqual("ANALYSIS_REQUEST", result["intent"]); self.assertEqual(0, result["external_actions"])



class CevapDiliTurkceSabit(unittest.TestCase):
    """Cevap dili istemde SABIT tutulur.

    20.09.2026 sahip kararı: "türkçe konuşmasını istiyorum". İstem zaten
    "Türkçe yazarsın" diyordu ama bunu ton kaydının içinde söylüyordu;
    kullanıcının dili değişince modelin ona uyması serbest kalıyordu.
    Kural artık açık ve tek başına duruyor -- bu test onu orada tutar.

    Modelin çıktısı ölçülmüyor: model her koşuda farklı cümle kurar ve
    böyle bir test ağ ya da GPU yüzünden ilgisiz sebeplerle kırmızı
    yanardı. Ölçülen şey SÖZLEŞME: talimat istemde duruyor mu.
    """

    def test_istem_her_zaman_turkce_diyor(self):
        self.assertIn("HER ZAMAN Türkçe", conversation.CHAT_SYSTEM)

    def test_baska_dilde_sorulsa_bile_kurali_var(self):
        self.assertIn("İngilizce", conversation.CHAT_SYSTEM)

    def test_ton_kaydi_korundu(self):
        # Dil kuralı eklenirken ton kaydı düşmemeli: ikisi ayrı kararlar.
        for kural in ("Resmî", "siz", "En fazla 4 cümle"):
            self.assertIn(kural, conversation.CHAT_SYSTEM)


class DilNotuSoruyaBitisik(unittest.TestCase):
    """Dil notu soruya bitişik gider ve kayda karışmaz.

    Neden var: istemdeki "HER ZAMAN Türkçe" kuralı ÖLÇÜLDÜ ve 4B modelde
    yetmedi -- "What are our sales this month?" İngilizce cevaplandı.
    Not eklendikten sonra 16 turun 16'sı Türkçe geldi (8 Türkçe soru,
    8 yabancı soru, her biri 2 tur).

    Burada modelin çıktısı değil, notun DOĞRU YERE eklendiği ölçülüyor;
    çıktı testi model her koşuda farklı cümle kurduğu için kırılgan olurdu.
    """

    def test_not_sorunun_SONUNA_eklenir(self):
        # Kucuk modeller istemin basindaki kurali degil, soruya en yakin
        # talimati dinliyor -- notun sonda olmasinin sebebi bu.
        cikti = conversation._dil_notlu("Hello")
        self.assertTrue(cikti.startswith("Hello"))
        self.assertTrue(cikti.rstrip().endswith("(Yanıtını Türkçe yaz.)"))

    def test_turkce_soruya_da_eklenir(self):
        """Sınıflandırıcı bilerek yok: bir kez yazıldı ve yanıldı
        ("Which product should I promote?" Türkçe sanıldı)."""
        self.assertIn("Türkçe yaz", conversation._dil_notlu("Merhaba"))

    def test_iki_kez_eklenmez(self):
        bir = conversation._dil_notlu("Merhaba")
        self.assertEqual(bir, conversation._dil_notlu(bir))

    def test_bos_mesaj_patlatmaz(self):
        self.assertIn("Türkçe yaz", conversation._dil_notlu(""))

    def test_kullanicinin_cumlesi_bozulmaz(self):
        soru = "Bu ay satışlar nasıl?"
        self.assertTrue(conversation._dil_notlu(soru).startswith(soru))


class KelimeSiniriKoyanKalip(unittest.TestCase):
    """Boslukla yazilan kalip KELIME SINIRI ister.

    Yasanan hata: selamlasma tablosundaki "hi " kalibi Ingilizce is
    sorularini sohbet sayiyordu. _normalize'in son satiri
    " ".join(text.split()) bastaki/sondaki boslugu SILIYOR, yani "hi "
    kalibi "hi" oluyor ve w-hi-ch, t-hi-s icinde esleiyordu. Kalibi yazan
    kisi boslugu tam bunu onlemek icin koymustu.

    Sonuc gorunur degildi: soru sohbet sayilinca kanit toplanmiyor ve
    sirket rakamlari kanitsiz uretiliyordu.
    """

    def test_bosluklu_kalip_kelime_ortasinda_eslesmez(self):
        self.assertFalse(conversation._has("which product", ("hi ",)))
        self.assertFalse(conversation._has("this month", ("hi ",)))

    def test_bosluklu_kalip_tam_kelimede_eslesir(self):
        self.assertTrue(conversation._has("hi jarvis", ("hi ",)))
        self.assertTrue(conversation._has("say hi", ("hi ",)))

    def test_bosluksuz_kaliplarin_davranisi_DEGISMEDI(self):
        # Tablodaki yuzlerce kalip bosluksuz; alt dizgi eslemesi surmeli.
        self.assertTrue(conversation._has("satislarimiz", ("satis",)))
        self.assertTrue(conversation._has("reklamlar", ("reklam",)))


class IngilizceSirketSorusuKanitaGider(unittest.TestCase):
    """Sirket sorusu hangi dilde sorulursa sorulsun COMPANY_QUERY.

    OLCULDU: Ingilizce sorular tabloda karsiligi olmadigi icin
    GENERAL_REASONING'e dusuyordu -- kanit toplanmiyor, cevabi model
    uretiyordu. "What are our sales this month?" evidence_refs [] ile
    cevaplandi; dogru rakam vermesi kanittan degil, o rakamin sohbet
    gecmisinde bulunmasindandi.
    """

    def _intent(self, soru):
        return conversation.classify(soru).intent

    def test_ingilizce_satis_sorusu(self):
        for soru in ("What are our sales this month?",
                     "How many orders do we have?",
                     "Show me our revenue"):
            self.assertEqual(conversation.COMPANY_QUERY, self._intent(soru), soru)

    def test_ingilizce_reklam_sorusu(self):
        for soru in ("How much did we spend on ads?",
                     "What is our campaign budget?"):
            self.assertEqual(conversation.COMPANY_QUERY, self._intent(soru), soru)

    def test_ingilizce_urun_sorusu(self):
        for soru in ("Which product should I promote?",
                     "What is the price of VIREON?"):
            self.assertEqual(conversation.COMPANY_QUERY, self._intent(soru), soru)

    def test_TURKCE_davranis_bozulmadi(self):
        for soru in ("Bu ay satışlar nasıl?", "Reklam harcaması ne oldu?",
                     "Kaç sipariş var?", "Cevapsız müşteri mesajı var mı?",
                     "Son 30 günde kaç adet ürün sattık?"):
            self.assertEqual(conversation.COMPANY_QUERY, self._intent(soru), soru)

    def test_selamlasma_sohbet_KALIR(self):
        """Pozitif kontrol: her seyi COMPANY_QUERY yapan bir tablo da
        yukaridaki testleri gecerdi."""
        for soru in ("Merhaba Jarvis", "Naber", "Hello", "Hi", "Günaydın"):
            self.assertEqual(conversation.SIMPLE_CONVERSATION, self._intent(soru), soru)

    def test_eylem_istegi_firewall_yolunda_KALIR(self):
        for soru in ("VIREON fiyatını 100 TL artır", "Kampanyayı kapat"):
            self.assertEqual(conversation.ACTION_REQUEST, self._intent(soru), soru)

if __name__ == "__main__": unittest.main()
