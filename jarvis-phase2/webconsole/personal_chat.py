"""Personal mobile chat with its own history and no company tools."""
from __future__ import annotations

from typing import Any, Iterator

from jarvis import conversation_memory
from jarvis.model_layer import ModelRouter, ModelUnavailable

PERSONAL_SYSTEM = (
    "Sen kullanıcının kişisel Jarvis asistanısın. Her zaman sade ve kısa Türkçe yaz. "
    "Kişisel planlama, fikir üretme ve günlük sorularda yardımcı ol. "
    "Bu konuşmada şirket verilerine, iş görevlerine, onaylara veya telefon uygulamalarına "
    "erişimin yok. Bunları okuduğunu veya bir işlem yaptığını söyleme. "
    "Şirketin gerçek verisi sorulursa İş alanına geçmesini söyle. "
    "Bilmediğin bilgiyi uydurma."
)


def stream(message: str, username: str, router: Any | None = None) -> Iterator[dict]:
    text = (message or "").strip()[:2000]
    if not text:
        yield {"type": "error", "message": "Bir mesaj yazın."}
        return
    # Work uses the legacy `operator` thread. This thread is never read by it.
    thread = "personal_" + username
    history = conversation_memory.history(thread=thread)
    yield {"type": "stage", "label": "Kişisel yanıt hazırlanıyor"}
    chunks: list[str] = []
    try:
        model = router if router is not None else ModelRouter()
        for delta in model.stream_text(text, PERSONAL_SYSTEM, max_tokens=380, history=history):
            chunks.append(delta)
            yield {"type": "token", "delta": delta}
    except (ModelUnavailable, OSError, ValueError):
        yield {"type": "error", "message": "Şu anda yanıt veremiyorum. Biraz sonra tekrar deneyin."}
        return
    answer = "".join(chunks).strip()
    if not answer:
        yield {"type": "error", "message": "Yanıt tamamlanamadı. Tekrar deneyin."}
        return
    conversation_memory.record(text, answer, intent="PERSONAL", thread=thread)
    yield {"type": "done", "result": {"kind": "ANSWER", "source": "personal.chat", "text": answer}}
