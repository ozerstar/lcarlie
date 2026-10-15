"""A dropped chat connection must never execute the same request twice."""
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import chat_turns


class ChatTurnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(chat_turns, "DB_PATH", Path(self.tmp.name) / "turns.sqlite3")
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def _finished(self, turn_id):
        for _ in range(100):
            frames, status = chat_turns.read_after(turn_id, "owner", 0)
            if status != "RUNNING":
                return frames, status
            time.sleep(0.01)
        self.fail("chat worker did not finish")

    def test_reconnect_replays_frames_without_running_model_twice(self):
        turn_id = str(uuid.uuid4())
        called = []
        gate = threading.Event()

        def events():
            called.append(1)
            yield {"type": "stage", "label": "Hazırlanıyor"}
            gate.wait(1)
            yield {"type": "token", "delta": "Merhaba"}
            yield {"type": "done", "result": {"text": "Merhaba"}}

        chat_turns.start_or_resume(turn_id, "owner", "personal", "Selam", events)
        chat_turns.start_or_resume(turn_id, "owner", "personal", "Selam", events)
        gate.set()
        frames, status = self._finished(turn_id)
        self.assertEqual(status, "DONE")
        self.assertEqual([frame["type"] for frame in frames], ["stage", "token", "done"])
        self.assertEqual(len(called), 1)
        remaining, _ = chat_turns.read_after(turn_id, "owner", frames[0]["seq"])
        self.assertEqual([frame["type"] for frame in remaining], ["token", "done"])
        chat_turns.start_or_resume(turn_id, "owner", "personal", None, events)
        self.assertEqual(len(called), 1)

    def test_owner_and_message_are_bound_to_turn(self):
        turn_id = str(uuid.uuid4())
        chat_turns.start_or_resume(turn_id, "owner", "work", "Birinci", lambda: iter([
            {"type": "done", "result": {"text": "Tamam"}}]))
        self._finished(turn_id)
        with self.assertRaises(ValueError):
            chat_turns.start_or_resume(turn_id, "other", "work", None, lambda: iter(()))
        with self.assertRaises(ValueError):
            chat_turns.start_or_resume(turn_id, "owner", "work", "İkinci", lambda: iter(()))
        with self.assertRaises(ValueError):
            chat_turns.read_after(turn_id, "other", 0)

    def test_restarted_server_marks_inflight_turn_uncertain(self):
        turn_id = str(uuid.uuid4())
        with chat_turns._db() as db:
            db.execute("INSERT INTO turns VALUES (?,?,?,?,?,?,?)", (
                turn_id, "owner", "work", "hash", "RUNNING", time.time(), time.time()))
        chat_turns.start_or_resume(turn_id, "owner", "work", None, lambda: iter(()))
        frames, status = chat_turns.read_after(turn_id, "owner", 0)
        self.assertEqual(status, "UNCERTAIN")
        self.assertEqual(frames[-1]["type"], "error")


if __name__ == "__main__":
    unittest.main()
