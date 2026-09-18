"""Conversation memory: it must help, and it must never be a dependency."""
from __future__ import annotations

import importlib
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path


class MemoryTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        previous = os.environ.get("JARVIS_STATE_DIR")
        os.environ["JARVIS_STATE_DIR"] = self.tmp.name

        def restore():
            if previous is None:
                os.environ.pop("JARVIS_STATE_DIR", None)
            else:
                os.environ["JARVIS_STATE_DIR"] = previous

        self.addCleanup(restore)
        from jarvis import conversation_memory

        self.mem = importlib.reload(conversation_memory)
        self.addCleanup(lambda: importlib.reload(conversation_memory))


class TranscriptTests(MemoryTestBase):
    def test_an_exchange_comes_back_as_chat_messages(self):
        self.mem.record("Vireon kampanyası", "Tamam, bakıyorum", intent="AGENCY_REQUEST")
        history = self.mem.history()
        self.assertEqual(["user", "assistant"], [m["role"] for m in history])
        self.assertEqual("Vireon kampanyası", history[0]["content"])

    def test_order_is_oldest_first_so_the_last_thing_said_is_last(self):
        self.mem.record("birinci", "cevap bir")
        self.mem.record("ikinci", "cevap iki")
        self.assertEqual("ikinci", self.mem.history()[-2]["content"])

    def test_only_the_recent_window_is_returned(self):
        for index in range(20):
            self.mem.record(f"soru {index}", f"cevap {index}")
        history = self.mem.history(turns=3)
        self.assertLessEqual(len(history), 6)
        self.assertIn("soru 19", [m["content"] for m in history])
        self.assertNotIn("soru 0", [m["content"] for m in history])

    def test_the_budget_is_applied_from_the_newest_backwards(self):
        """One enormous answer in the past must not crowd out what was just
        said -- that is the failure that makes history useless."""
        self.mem.record("eski soru", "x" * 5000)
        self.mem.record("yeni soru", "kısa cevap")
        contents = [m["content"] for m in self.mem.history()]
        self.assertIn("yeni soru", contents)

    def test_the_transcript_is_trimmed_not_grown_forever(self):
        for index in range(self.mem.MAX_STORED_TURNS + 25):
            self.mem.record(f"s{index}", f"c{index}")
        self.assertLessEqual(self.mem.status()["turns"], self.mem.MAX_STORED_TURNS)

    def test_a_fresh_install_has_no_history_and_no_notes(self):
        self.assertEqual([], self.mem.history())
        self.assertEqual("", self.mem.notes_block())
        self.assertEqual({"turns": 0, "notes": 0}, self.mem.status())


class NoteTests(MemoryTestBase):
    def test_a_note_survives_the_transcript_window(self):
        self.mem.remember("Videolar sisteme yüklenmeyecek.")
        for index in range(30):
            self.mem.record(f"s{index}", f"c{index}")
        self.assertIn("Videolar sisteme yüklenmeyecek.", self.mem.notes())

    def test_notes_reach_the_prompt_only_when_there_are_some(self):
        self.assertEqual("", self.mem.notes_block())
        self.mem.remember("Operatörün adı Özer.")
        self.assertIn("Özer", self.mem.notes_block())

    def test_the_same_note_is_not_stored_twice(self):
        self.mem.remember("aynı not")
        self.mem.remember("aynı not")
        self.assertEqual(1, self.mem.status()["notes"])

    def test_a_note_can_be_removed(self):
        self.mem.remember("yanlış bilgi burada")
        self.assertEqual(1, self.mem.forget("yanlış bilgi"))
        self.assertEqual([], self.mem.notes())

    def test_empty_notes_are_refused(self):
        self.assertFalse(self.mem.remember("   "))
        self.assertEqual(0, self.mem.status()["notes"])

    def test_nothing_is_remembered_that_was_not_asked_for(self):
        """Recording a conversation must never create a durable note by
        itself: a memory that decides for itself is one nobody can correct."""
        self.mem.record("Bunu unutma: parolam 1234", "tamam")
        self.assertEqual([], self.mem.notes())


class ResilienceTests(MemoryTestBase):
    def test_a_corrupt_line_does_not_lose_the_rest(self):
        self.mem.record("iyi kayıt", "cevap")
        path = Path(self.tmp.name) / "conversation" / "operator.turns.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "{bozuk json\n", encoding="utf-8")
        self.assertTrue(self.mem.history())

    def test_an_unwritable_store_does_not_break_the_turn(self):
        """A conversation must not fail because its transcript did."""
        with unittest.mock.patch.object(self.mem, "_write", side_effect=OSError("disk")):
            self.mem.record("soru", "cevap")      # must not raise
            self.assertFalse(self.mem.remember("not"))

    def test_history_of_a_thread_that_never_spoke_is_empty(self):
        self.assertEqual([], self.mem.history(thread="bilinmeyen"))


if __name__ == "__main__":
    import unittest.mock  # noqa: F401

    unittest.main()
