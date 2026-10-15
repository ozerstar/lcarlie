import base64
import io
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import hashlib
import hmac

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import voice_bridge


class VoiceBridgeTests(unittest.TestCase):
    def test_short_lived_room_token_is_bound_to_owner_and_mode(self):
        with patch.dict(voice_bridge.os.environ, {
            "LIVEKIT_API_KEY": "testkey", "LIVEKIT_API_SECRET": "s" * 64,
            "JARVIS_REALTIME_VOICE": "true"}), \
             patch.object(voice_bridge, "ready", return_value=True):
            result = voice_bridge.issue_session("özer", "personal")
        parts = result["token"].split(".")
        self.assertEqual(len(parts), 3)
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        self.assertEqual(json.loads(claims["metadata"]), {"owner": "özer", "mode": "personal"})
        self.assertEqual(claims["video"]["room"], result["room"])
        self.assertFalse(claims["video"]["canPublishData"])
        self.assertLessEqual(claims["exp"] - claims["iat"], 300)

    def test_agent_signature_requires_loopback_and_recent_time(self):
        body = b'{"message":"Merhaba"}'
        when = str(int(time.time()))
        signature = hmac.new(b"s" * 64, when.encode() + b"." + body, hashlib.sha256).hexdigest()
        with patch.dict(voice_bridge.os.environ, {"LIVEKIT_API_SECRET": "s" * 64}):
            self.assertTrue(voice_bridge.verify_agent(body, when, signature, "127.0.0.1"))
            self.assertFalse(voice_bridge.verify_agent(body, when, signature, "172.18.0.2"))
            self.assertFalse(voice_bridge.verify_agent(body, str(int(when) - 60), signature, "127.0.0.1"))

    def test_agent_turn_reuses_durable_chat(self):
        body = json.dumps({"owner": "owner", "mode": "personal", "message": "Merhaba",
                           "turn_id": "11111111-1111-4111-8111-111111111111"}).encode()

        class Handler:
            headers = {"Content-Length": str(len(body)), "X-Voice-Time": "1", "X-Voice-Signature": "ok"}
            client_address = ("127.0.0.1", 1)
            rfile = io.BytesIO(body)
            sent = None

            def _send_json(self, status, payload):
                self.sent = (status, payload)

        handler = Handler()
        with patch.object(app.voice_bridge, "verify_agent", return_value=True), \
             patch.object(app.chat_turns, "start_or_resume") as start, \
             patch.object(app.chat_turns, "read_after", return_value=(
                 [{"seq": 1, "type": "done", "result": {"text": "Merhaba Özer."}}], "DONE")):
            app.Handler._handle_voice_agent_turn(handler)
        self.assertEqual(handler.sent[0], 200)
        self.assertEqual(handler.sent[1]["text"], "Merhaba Özer.")
        self.assertEqual(start.call_args.args[:3], ("11111111-1111-4111-8111-111111111111",
                                                    "owner", "personal"))


if __name__ == "__main__":
    unittest.main()
