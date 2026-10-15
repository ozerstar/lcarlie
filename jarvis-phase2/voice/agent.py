"""Self-hosted WebRTC voice worker using local Turkish STT and Piper TTS.

Only this worker can call the loopback chat bridge. The browser gets a short
LiveKit room token, never a database or tool credential.
"""
from __future__ import annotations

import asyncio
from io import BytesIO
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import time
from typing import AsyncIterable
from urllib.request import Request, urlopen
import uuid
import wave

import numpy as np
from faster_whisper import WhisperModel
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, ModelSettings, llm, stt, utils
from livekit.plugins import silero
from terminology import normalize_transcript, whisper_options


MODEL_PATH = Path(os.environ.get("JARVIS_WHISPER_MODEL", "/opt/lcarlie/jarvis-voice-agent/models/small"))
BRIDGE_URL = os.environ.get("JARVIS_VOICE_BRIDGE_URL", "http://127.0.0.1:8091/api/voice/agent-turn")
PIPER_URL = "http://127.0.0.1:5000/synthesize"
log = logging.getLogger("jarvis.voice")


def _transcribe(model: WhisperModel, buffer: utils.AudioBuffer) -> str:
    merged = utils.merge_frames(buffer)
    if merged.num_channels != 1:
        raise ValueError("voice input must be mono")
    if merged.sample_rate != 16000:
        resampler = rtc.AudioResampler(merged.sample_rate, 16000)
        frames = [*resampler.push(merged), *resampler.flush()]
        pcm = b"".join(bytes(frame.data) for frame in frames)
    else:
        pcm = bytes(merged.data)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size < 1600:
        return ""
    segments, _info = model.transcribe(samples, language="tr", beam_size=1,
                                       best_of=1, condition_on_previous_text=False,
                                       vad_filter=False, **whisper_options())
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return normalize_transcript(text)[:2000]


class TurkishWhisper(stt.STT):
    def __init__(self, model: WhisperModel):
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        self._model = model

    @property
    def model(self) -> str:
        return "faster-whisper-small-tr"

    @property
    def provider(self) -> str:
        return "local"

    async def _recognize_impl(self, buffer, *, language, conn_options):
        text = await asyncio.to_thread(_transcribe, self._model, buffer)
        log.info("transcription completed; characters=%s", len(text))
        return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                               alternatives=[stt.SpeechData(language="tr", text=text)])


class BridgeLLM(llm.LLM):
    """Marks reply generation as available; JarvisVoiceAgent owns the actual node."""

    @property
    def model(self) -> str:
        return "jarvis-chat-bridge"

    @property
    def provider(self) -> str:
        return "local"

    def chat(self, **kwargs):
        raise RuntimeError("Only JarvisVoiceAgent.llm_node may run")


def _ask_jarvis(owner: str, mode: str, message: str, turn_id: str,
                chat_id: str | None = None) -> str:
    payload = json.dumps({"owner": owner, "mode": mode, "message": message,
                          "turn_id": turn_id, "chat_id": chat_id}, ensure_ascii=False,
                         separators=(",", ":")).encode()
    when = str(int(time.time()))
    secret = os.environ["LIVEKIT_API_SECRET"]
    signature = hmac.new(secret.encode(), when.encode() + b"." + payload,
                         hashlib.sha256).hexdigest()
    request = Request(BRIDGE_URL, data=payload, method="POST", headers={
        "Content-Type": "application/json", "X-Voice-Time": when,
        "X-Voice-Signature": signature,
    })
    with urlopen(request, timeout=78) as response:
        result = json.load(response)
    return str(result.get("text") or "Yanıt tamamlanamadı.")[:4000]


def _synthesize(text: str) -> tuple[int, bytes]:
    payload = json.dumps({"text": text[:800]}, ensure_ascii=False).encode()
    request = Request(PIPER_URL, data=payload, method="POST",
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        data = response.read(4_000_001)
    if len(data) > 4_000_000 or not data.startswith(b"RIFF"):
        raise ValueError("Piper returned invalid audio")
    with wave.open(BytesIO(data)) as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError("Piper returned unsupported audio")
        return audio.getframerate(), audio.readframes(audio.getnframes())


class JarvisVoiceAgent(Agent):
    def __init__(self, owner: str, mode: str, chat_id: str | None = None):
        super().__init__(instructions="Türkçe konuş. Dış işlem yapmadan önce Jarvis onay kurallarını uygula.")
        self.owner = owner
        self.mode = mode
        self.chat_id = chat_id

    async def llm_node(self, chat_ctx, tools, model_settings: ModelSettings) -> AsyncIterable[str]:
        question = next((item.text_content for item in reversed(chat_ctx.items)
                         if getattr(item, "role", "") == "user" and item.text_content), "")
        if not question:
            yield "Söylediğinizi anlayamadım. Lütfen tekrar söyleyin."
            return
        try:
            answer = await asyncio.to_thread(_ask_jarvis, self.owner, self.mode,
                                             question, str(uuid.uuid4()), self.chat_id)
        except Exception:
            log.exception("chat bridge unavailable")
            answer = "Bağlantı koptu. İşlem durumunu kontrol edin; isteğiniz yeniden gönderilmedi."
        yield answer

    async def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings) -> AsyncIterable[rtc.AudioFrame]:
        answer = "".join([str(part) async for part in text]).strip()
        if not answer:
            return
        for start in range(0, len(answer), 700):
            rate, pcm = await asyncio.to_thread(_synthesize, answer[start:start + 700])
            width = 2
            chunk_size = rate // 50 * width
            for offset in range(0, len(pcm), chunk_size):
                chunk = pcm[offset:offset + chunk_size]
                if len(chunk) < width:
                    break
                yield rtc.AudioFrame(data=chunk, sample_rate=rate, num_channels=1,
                                     samples_per_channel=len(chunk) // width)


server = AgentServer(num_idle_processes=1, initialize_process_timeout=90,
                     host="127.0.0.1", port=8081)


def prewarm(proc) -> None:
    if not MODEL_PATH.is_dir():
        raise RuntimeError(f"Whisper model missing: {MODEL_PATH}")
    proc.userdata["whisper"] = WhisperModel(str(MODEL_PATH), device="cpu",
                                           compute_type="int8", cpu_threads=2)
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session()
async def voice_session(ctx) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    try:
        identity = json.loads(participant.metadata or "{}")
    except json.JSONDecodeError:
        return
    owner, mode, chat_id = identity.get("owner"), identity.get("mode"), identity.get("chat_id")
    if not isinstance(owner, str) or not owner or len(owner) > 100 or mode not in ("work", "personal"):
        return
    if chat_id is not None and (not isinstance(chat_id, str) or len(chat_id) != 36):
        return
    session = AgentSession(stt=TurkishWhisper(ctx.proc.userdata["whisper"]),
                           vad=ctx.proc.userdata["vad"], llm=BridgeLLM(), tts=None,
                           min_endpointing_delay=0.4, max_endpointing_delay=1.5)
    @session.on("user_state_changed")
    def on_user_state(event):
        log.info("user voice state: %s", event.new_state)
    await session.start(agent=JarvisVoiceAgent(owner, mode, chat_id), room=ctx.room)


if __name__ == "__main__":
    from livekit.agents import cli
    cli.run_app(server)
