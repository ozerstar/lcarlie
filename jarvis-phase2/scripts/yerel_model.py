"""İş üretici için ÜCRETSİZ model yönlendiricisi.

Sahip 26.10.2026: "para harcamasınlar, benim bilgisayarımda çalışsınlar".
Sıra:
  1. Sahibin PC'sindeki GPU modeli -- sunucuda 127.0.0.1:8098, PC'den ters SSH
     tüneliyle gelir (llama-server, Qwen3-4B-Instruct). PC kapalıysa düşer.
  2. Sunucunun kendi CPU modeli -- 127.0.0.1:8099 (yavaş ama ücretsiz).
  Hakem çağrıları (is_anahtari ...hakem) önce OpenRouter'ın ÜCRETSİZ 550B
  modeline gider: hem ücretsiz hem üreticiden farklı model ailesi.
Ücretli sağlayıcı YALNIZ IS_URETICI_UCRETLI=true ise son çare olarak denenir;
varsayılan kapalıdır. Sahip 12.11.2026'da açtı ve "API key kullanmasın" dedi:
son çare her zaman "hizli" kademesidir (Gemini, sonra OpenRouter); Claude ve
OpenAI'ye gitmez.

8K BAĞLAM: llama-server -c 8192 ile çalışıyor. İstem sığmazsa <veri>...</veri>
bloğu kısaltılır (talimat ve şema asla kısaltılmaz); çıktı bütçesi 2200 token.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

URLLER = [u.strip() for u in os.environ.get(
    "IS_URETICI_YEREL_URLLER", "http://127.0.0.1:8098/v1,http://127.0.0.1:8099/v1").split(",") if u.strip()]
BAGLAM = int(os.environ.get("IS_URETICI_YEREL_BAGLAM", "8192"))
CIKTI_TAVAN = int(os.environ.get("IS_URETICI_YEREL_CIKTI", "3000"))
# Günde birkaç kez çalışan ağır sentezler önce OpenRouter'ın ÜCRETSİZ 550B modeline gider
# (4B yerel model kaynak-iddia eşleştirmesinde zayıf kaldı: 26.10.2026 kreatif turunda 3/3 kart
# hakemden "kaynakla uyuşmuyor" diye döndü). Düşerse yerel modele iner.
GUCLU_ISLER = {x.strip() for x in os.environ.get(
    "IS_URETICI_GUCLU_ISLER", "rakip-sentez,kreatif-uret,b2b-plan,is-uretici-aylik").split(",") if x.strip()}
ZAMAN_ASIMI = float(os.environ.get("IS_URETICI_YEREL_ZAMAN_ASIMI", "900"))
KAR_TOKEN = 2.4   # Türkçe metinde ölçülü değil, temkinli tahmin: ~2.4 karakter/token
_VERI = re.compile(r"<veri>\n?(.*?)\n?</veri>", re.S)


def sigdir(mesajlar: list[dict], cikti: int) -> list[dict]:
    """İstem bağlama sığmıyorsa yalnız <veri> bloğunu kısaltır."""
    butce = int((BAGLAM - cikti - 400) * KAR_TOKEN)
    toplam = sum(len(m.get("content", "")) for m in mesajlar)
    if toplam <= butce:
        return mesajlar
    fazla = toplam - butce
    out = []
    for m in reversed(mesajlar):
        icerik = m.get("content", "")
        mt = _VERI.search(icerik) if fazla > 0 else None
        if mt:
            veri = mt.group(1)
            yeni = veri[:max(400, len(veri) - fazla)] + "\n[… bağlam sınırı nedeniyle kısaltıldı]"
            fazla -= len(veri) - len(yeni)
            icerik = icerik[:mt.start(1)] + yeni + icerik[mt.end(1):]
        out.append(dict(m, content=icerik))
    out.reverse()
    if sum(len(m["content"]) for m in out) > butce:  # hâlâ sığmıyorsa en baştan değil, sistemden sonrasını kes
        son = out[-1]
        out[-1] = dict(son, content=son["content"][-max(2000, butce - sum(len(m["content"]) for m in out[:-1])):])
    return out


def _llama(url: str, mesajlar: list[dict], cikti: int) -> tuple[str, dict]:
    govde = {"messages": mesajlar, "max_tokens": cikti, "temperature": 0.4,
             "response_format": {"type": "json_object"}, "stream": False}
    istek = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=json.dumps(govde).encode("utf-8"),
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as c:
        d = json.loads(c.read().decode("utf-8"))
    ch = (d.get("choices") or [{}])[0]
    return (ch.get("message") or {}).get("content") or "", d.get("usage") or {}


def yonlendirici(providers):
    ucretli = os.environ.get("IS_URETICI_UCRETLI", "false").lower() in ("1", "true", "evet")
    openrouter = next((p for p in providers.PROVIDERS if p.name == "openrouter"), None)

    def uret(mesajlar, max_tokens=1500, kademe=None, is_anahtari=None, **_):
        cikti = min(int(max_tokens), CIKTI_TAVAN)
        denemeler = []
        if openrouter and is_anahtari and (is_anahtari.endswith("hakem") or is_anahtari in GUCLU_ISLER):
            key = providers.load_env().get(openrouter.env_key)
            if key:
                basla = time.perf_counter()
                try:
                    text, finish, gt, ct = openrouter.call(key, openrouter.default_model, mesajlar, max(int(max_tokens), 800))
                    if (text or "").strip():
                        providers._record_usage(openrouter, openrouter.default_model, basla, is_anahtari=is_anahtari,
                                                kademe="ucretsiz", prompt_tokens=gt, completion_tokens=ct)
                        return {"text": text, "provider": "openrouter-ucretsiz", "model": openrouter.default_model}
                    denemeler.append("openrouter: boş")
                except Exception as e:  # noqa: BLE001
                    denemeler.append(f"openrouter: {providers.mask(str(e))[:80]}")
        sigan = sigdir(mesajlar, cikti)
        for url in URLLER:
            basla = time.perf_counter()
            try:
                text, kullanim = _llama(url, sigan, cikti)
            except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as e:
                denemeler.append(f"{url}: {str(e)[:80]}")
                continue
            if text.strip():
                kaynak = "pc-gpu" if ":8098" in url else ("sunucu-cpu" if ":8099" in url else url)
                return {"text": text, "provider": f"yerel-{kaynak}", "model": "Qwen3-4B-Instruct",
                        "prompt_tokens": kullanim.get("prompt_tokens"), "completion_tokens": kullanim.get("completion_tokens"),
                        "elapsed_s": round(time.perf_counter() - basla, 1)}
            denemeler.append(f"{url}: boş cevap")
        if ucretli:
            # Sahip 12.11: ucretli yedek yalniz Gemini kademesi (hizli); Claude/OpenAI
            # API anahtari is ureticide kullanilmaz.
            return providers.generate(mesajlar, max_tokens=max_tokens, kademe="hizli", is_anahtari=is_anahtari)
        raise RuntimeError("ücretsiz model yanıt vermedi (PC kapalı ve sunucu modeli düştü?): " + "; ".join(denemeler))
    return uret
