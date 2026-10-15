import unittest
import sys
import io
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import personal_chat
import app


class FakeRouter:
    def __init__(self):
        self.messages = None

    def stream_text(self, question, system, max_tokens, history):
        self.messages = (question, system, history)
        yield "Bugün kısa bir plan yapalım."


class PersonalChatTests(unittest.TestCase):
    def test_personal_thread_and_no_company_context(self):
        router = FakeRouter()
        with patch.object(personal_chat.conversation_memory, "history", return_value=[]) as history, \
             patch.object(personal_chat.conversation_memory, "record") as record:
            events = list(personal_chat.stream("Bugün ne yapayım?", "owner", router))
        history.assert_called_once_with(thread="personal_owner")
        self.assertEqual(record.call_args.kwargs["thread"], "personal_owner")
        self.assertIn("şirket verilerine", router.messages[1])
        self.assertEqual(events[-1]["result"]["source"], "personal.chat")

    def test_empty_message_never_calls_model_or_memory(self):
        with patch.object(personal_chat.conversation_memory, "history") as history:
            events = list(personal_chat.stream(" ", "owner", FakeRouter()))
        history.assert_not_called()
        self.assertEqual(events[0]["type"], "error")

    def test_drive_search_uses_requested_file_name(self):
        with patch.object(personal_chat.google_workspace, "status", return_value={"connected": True}), \
             patch.object(personal_chat.google_workspace, "drive_files", return_value=[]) as finder:
            events = list(personal_chat.stream("Drive'da bul katalog", "owner"))
        finder.assert_called_once_with("owner", "katalog")
        self.assertEqual(events[-1]["result"]["source"], "personal.google_drive")

    def test_personal_api_never_invokes_work_router(self):
        class FakeHandler:
            wfile = io.BytesIO()
            def send_response(self, _code): pass
            def send_header(self, _name, _value): pass
            def end_headers(self): pass
            def _current_session(self):
                return type("Session", (), {"username": "owner"})()

        handler = FakeHandler()
        with patch.object(app, "_read_json_body", return_value={"message": "Merhaba", "mode": "personal"}), \
             patch.object(app.personal_chat, "stream", return_value=iter([{"type": "done", "result": {"text": "Merhaba"}}])) as personal, \
             patch.object(app.chat, "stream") as work:
            app.Handler._handle_chat_stream(handler)
        personal.assert_called_once_with("Merhaba", "owner")
        work.assert_not_called()
        self.assertEqual(json.loads(handler.wfile.getvalue().decode())["type"], "done")


if __name__ == "__main__":
    unittest.main()
