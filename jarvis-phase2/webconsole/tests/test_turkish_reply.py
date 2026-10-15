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


if __name__ == "__main__":
    unittest.main()
