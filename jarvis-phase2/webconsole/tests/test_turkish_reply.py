import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat
import personal_chat
import turkish_reply


class TurkishReplyTests(unittest.TestCase):
    def test_english_prose_is_rewritten(self):
        draft = "Here is your plan for today and this is what you should do next."
        self.assertTrue(turkish_reply.is_english_prose(draft))
        self.assertEqual(turkish_reply.ensure(draft, lambda _: "Bugün önce planınızı gözden geçirin."),
                         "Bugün önce planınızı gözden geçirin.")

    def test_names_and_turkish_prose_are_preserved(self):
        answer = "Bugün Google Drive dosyanızı ve Open WebUI ayarlarınızı gözden geçirebilirsiniz."
        self.assertFalse(turkish_reply.is_english_prose(answer))
        self.assertEqual(turkish_reply.ensure(answer, lambda _: self.fail("unnecessary rewrite")), answer)

    def test_failed_rewrite_does_not_publish_english(self):
        draft = "Here is your plan for today and this is what you should do next."
        self.assertEqual(turkish_reply.ensure(draft, lambda _: draft), turkish_reply.UNAVAILABLE)

    def test_personal_stream_never_emits_english_draft(self):
        class Router:
            def stream_text(self, question, system, max_tokens, history):
                yield ("Bugün önceliklerinizi yazın." if system == turkish_reply.REWRITE_SYSTEM else
                       "Here is your plan for today and this is what you should do next.")
        with patch.object(personal_chat.conversation_memory, "history", return_value=[]), \
             patch.object(personal_chat.conversation_memory, "record"), \
             patch.object(personal_chat.mobile_features, "memory_search", return_value={"notes": []}), \
             patch.object(personal_chat.mobile_features, "personal_notes", return_value=[]), \
             patch.object(personal_chat.mobile_features, "contacts", return_value=[]), \
             patch.object(personal_chat.google_workspace, "status", return_value={"connected": False}):
            events = list(personal_chat.stream("Bugün ne yapayım?", "owner", Router()))
        self.assertEqual([event["delta"] for event in events if event["type"] == "token"],
                         ["Bugün önceliklerinizi yazın."])

    def test_work_stream_holds_draft_until_checked(self):
        draft = "Here is your plan for today and this is what you should do next."
        frames = iter([{"type": "token", "delta": draft},
                       {"type": "done", "result": {"text": draft, "kind": "ANSWER"}}])
        with patch.object(chat.conversation, "classify", return_value=type("Decision", (), {"intent": chat.conversation.SIMPLE_CONVERSATION})()), \
             patch.object(chat.conversation, "stream_chat", return_value=frames), \
             patch.object(chat, "_turkish_result", return_value={"text": "Bugün planınızı yazın.", "kind": "ANSWER"}), \
             patch.object(chat, "_remember"):
            events = list(chat.stream("Merhaba", None, None))
        self.assertEqual([event["delta"] for event in events if event["type"] == "token"],
                         ["Bugün planınızı yazın."])


class PozitifTurkceKanitiTests(unittest.TestCase):
    """Akis kapisi POZITIF kanitla acilir -- eklendi 16.10.2026.

    Olculen kusur: kapi `len >= 140 and not is_english_prose(...)` ile
    aciliyordu, ama `is_english_prose` 8 kelimenin ALTINDA her zaman False
    doner. Yani kisa ornekte "Ingilizce bulunmadi" kanit degil sessizlikti
    ve kapi hic acilmiyordu: 70 ve 106 karakterlik iki cevap panelde
    parca=1 geldi, ilk kelime 0,80 yerine 1,20 sn'de gorundu.
    """

    def test_turkce_islev_sozcugu_kaniti_sayilir(self):
        for ornek in ("Merhaba! Size nasıl yardımcı olabilirim?",
                      "Selam, bugün ne yapalım?",
                      "Tarak daha rahat geçiyor"):
            with self.subTest(ornek=ornek):
                self.assertTrue(turkish_reply.looks_turkish(ornek))

    def test_kucuk_harfli_turkce_harf_kaniti_sayilir(self):
        # Islev sozcugu yok; kanit `olacağım` kelimesindeki ğ ve ı.
        self.assertTrue(turkish_reply.looks_turkish("Elbette, yardımcı olacağım"))

    def test_INGILIZCE_cumledeki_OZEL_AD_kapiyi_ACMAZ(self):
        """🔴 Bu testin sebebi bilincli bir tasarim secimi.

        Turkceye ozgu harf OZEL ADLARDA da gecer ve "herhangi bir kelimede
        Turkce harf" kurali Ingilizce bir cumleyi Turkce sanip kapiyi
        acardi. Kucuk harf sarti tam bunu engelliyor.
        """
        for ornek in ("Your Çankaya store performance improved this quarter.",
                      "The Müşteri Hizmetleri team should review this today.",
                      "Hello, how can I help you with your campaign today?"):
            with self.subTest(ornek=ornek):
                self.assertFalse(turkish_reply.looks_turkish(ornek))

    def test_bos_ve_baglanti_girdisi_kanit_uretmez(self):
        self.assertFalse(turkish_reply.looks_turkish(""))
        self.assertFalse(turkish_reply.looks_turkish("https://lcarlie.shop/ürün-şişe"))


class KisaCevapAkisiTests(unittest.TestCase):
    def _akit(self, parcalar, sonuc_metni):
        frames = [{"type": "token", "delta": p} for p in parcalar]
        frames.append({"type": "done",
                       "result": {"text": "".join(parcalar), "kind": "ANSWER"}})
        karar = type("Decision", (), {"intent": chat.conversation.SIMPLE_CONVERSATION})()
        with patch.object(chat.conversation, "classify", return_value=karar),              patch.object(chat.conversation, "stream_chat", return_value=iter(frames)),              patch.object(chat, "_turkish_result",
                          return_value={"text": sonuc_metni, "kind": "ANSWER"}),              patch.object(chat, "_remember"):
            olaylar = list(chat.stream("Merhaba", None, None))
        return [o["delta"] for o in olaylar if o["type"] == "token"]

    def test_KISA_turkce_cevap_ARTIK_akiyor(self):
        parcalar = ["Merhaba", "! Nasıl", " yardımcı", " olabilirim?"]
        deltalar = self._akit(parcalar, "".join(parcalar))
        self.assertGreater(len(deltalar), 1,
                           "kisa Turkce cevap yine tek blok geldi")
        self.assertEqual("".join(deltalar), "".join(parcalar))

    def test_UZUN_ingilizce_taslak_HALA_tamponlanir(self):
        """Kapinin diger yonu: hizlandirma korumayi bozmamali."""
        parcalar = ["Here is your plan ", "for today and this ",
                    "is what you should ", "do next with the data."]
        deltalar = self._akit(parcalar, "Bugün planınızı yazın.")
        self.assertEqual(deltalar, ["Bugün planınızı yazın."],
                         "Ingilizce taslak kullaniciya sizdi")


if __name__ == "__main__":
    unittest.main()
