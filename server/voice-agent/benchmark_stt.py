"""Compare Turkish STT with and without reviewed vocabulary hints.

Run with --synthetic for a repeatable smoke check. For a real accuracy check,
pass consented WAV recordings; recordings are read locally and never uploaded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

from faster_whisper import WhisperModel
import numpy as np
from terminology import normalize_transcript, whisper_options


SAMPLE_PHRASES = (
    "Jarvis, HYDRAVIE satışlarını göster.",
    "L'CARLIE için BABYSOFT ürününü incele.",
    "KINESIS Plus stok durumunu söyle.",
)


def synthetic_sample(text: str, destination: Path) -> None:
    request = Request("http://127.0.0.1:5000/synthesize",
                      data=json.dumps({"text": text}, ensure_ascii=False).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=20) as response:
        audio = response.read(4_000_001)
    if len(audio) > 4_000_000 or not audio.startswith(b"RIFF"):
        raise ValueError("Synthetic speech response is not a small WAV file")
    destination.write_bytes(audio)


def recognize(model: WhisperModel, path: Path, *, hints: bool) -> tuple[str, float]:
    started = time.monotonic()
    options = whisper_options() if hints else {}
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1",
         "-ar", "16000", "-"], capture_output=True, check=True)
    samples = np.frombuffer(decoded.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = model.transcribe(samples, language="tr", beam_size=1, best_of=1,
                                   condition_on_previous_text=False, vad_filter=False,
                                   **options)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if hints:
        text = normalize_transcript(text)
    return text, round(time.monotonic() - started, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="*", type=Path, help="Locally stored WAV samples")
    parser.add_argument("--synthetic", action="store_true", help="Create Piper speech samples")
    parser.add_argument("--model", default="/opt/lcarlie/jarvis-voice-agent/models/small")
    args = parser.parse_args()
    if not args.audio and not args.synthetic:
        parser.error("Provide WAV files or --synthetic")
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=2)
    with tempfile.TemporaryDirectory(prefix="jarvis-stt-") as directory:
        samples = [(path.name, path) for path in args.audio]
        if args.synthetic:
            for index, phrase in enumerate(SAMPLE_PHRASES, 1):
                path = Path(directory) / f"sample-{index}.wav"
                synthetic_sample(phrase, path)
                samples.append((phrase, path))
        for label, path in samples:
            plain, plain_seconds = recognize(model, path, hints=False)
            hinted, hinted_seconds = recognize(model, path, hints=True)
            print(json.dumps({"sample": label, "plain": plain, "hinted": hinted,
                              "plain_seconds": plain_seconds,
                              "hinted_seconds": hinted_seconds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
