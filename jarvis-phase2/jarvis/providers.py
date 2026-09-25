"""Dış model sağlayıcıları: ölçülmüş sırayla, ucuzdan pahalıya.

NEDEN VAR
Jarvis'in model katmanı tek bir dış sağlayıcı tanıyordu (OpenRouter) ve
anahtarını kimi-sandbox yapılandırmasından okuyordu. Oysa sunucuda
/opt/lcarlie/orchestrator/.env içinde altı sağlayıcının anahtarı duruyor:
GEMINI, GROQ, NVIDIA, OPENAI, ANTHROPIC, OPENROUTER. Hiçbiri Jarvis
tarafından kullanılmıyordu.

ÖLÇÜLDÜ (20.09.2026, aynı tarafsız soru, şirket verisi gönderilmeden):
  GEMINI  gemini-3.5-flash-lite      0,9-1,2 s   tam Türkçe, doğru muhakeme
  CLAUDE  haiku-4.5                  2,3 s       en iyi cevap
  OPENROUTER nemotron-550b:free      2,2 s       çok iyi
  OPENAI  gpt-5-mini                 4,5 s       çalışıyor (max_completion_tokens)
  NVIDIA  nemotron-3.5-lightning     2-13 s      "Here's a thinking process" sızdırıyor
  GROQ    --                         HTTP 403    Cloudflare 1010, erişim yok

SIRA NEDEN BÖYLE
Sahibin kuralı (20.09.2026): "ücretsizleri kullan, çok karmaşık işlemler
için ücretlilere git." Sıra buna göre: önce ucuz ve hızlı olan, sonra
ücretsiz yedek, en son pahalı olan.

🔴 GEMINI DE PARA HARCAR — `paid=False` OLMASI BUNU DEĞİŞTİRMEZ.
Sahip 22.09.2026'da düzeltti: *"gemini de ücretli bu arada."* Haklı ve bu
modülün eski açıklaması yanıltıcıydı ("önce ücretsiz olan" diyordu).
Gemini anahtarı FATURALI (aşağıdaki veri sınırı notunun dayanağı da bu),
yani her çağrı ücretlendirilir: 1M token başına 0,30 $ girdi / 2,50 $ çıktı.
Ölçüldü: 7 günde 4,46 TL'nin 4,14 TL'si Gemini'den geldi.

`paid` alanı MALİYET DEĞİL YÖNLENDİRME bayrağıdır: "yalnızca `deep=True`
ile denensin" demektir. Gemini'ye `paid=True` verilirse normal akışta hiç
çağrılmaz ve sistem susar. Panel bu yüzden "para harcıyor mu" bilgisini bu
alandan değil, `model_fiyat` tablosundaki birim fiyattan türetir.

⚠️ `deep=True` "daha güçlü modele git" DEMEK DEĞİL: sıra yine baştan başlar
ve ilk başarılı cevapta durur. Gemini cevap verdiği sürece Claude/OpenAI'ye
sıra gelmez.

Sunucudaki PROVIDER_ORDER değişkeni nvidia ile başlıyordu -- ölçümde en kötü
performans gösteren sağlayıcı. Bu modül o sırayı kullanmaz, ölçülmüş sırayı
kullanır.

ANAHTARLAR
Değerleri okunur ama HİÇBİR YERE yazılmaz: log, hata mesajı ve dönüş
sözlüğü anahtar içermez. Hata metinleri maskelenir.

VERİ SINIRI: GEMINI ANAHTARI FATURALI (sahip teyidi, 20.09.2026)
Google'ın ÜCRETSİZ katmanı, gönderilen içeriği ürün geliştirmede kullanır ve
insan denetçilerin okumasına izin verir; kendi şartları "hassas veya gizli
bilgi göndermeyin" der. ÜCRETLİ (faturalı) katmanda bu geçerli değildir.

Sahip hesabın faturalı olduğunu teyit etti; şirket verisi bu yüzden
Gemini'ye gönderilebiliyor. FATURALANDIRMA KAPATILIRSA bu gerekçe düşer ve
Gemini zincirden çıkarılmalı, yerine OpenRouter (2,2 s, ücretsiz) birinci
sıraya alınmalıdır.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

ENV_PATH = os.environ.get("JARVIS_PROVIDER_ENV", "/opt/lcarlie/orchestrator/.env")
TIMEOUT_S = float(os.environ.get("JARVIS_PROVIDER_TIMEOUT_S", "60"))

# Anahtar bicimleri; hata metinlerinde gorunurse maskelenir.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{4}|AIza[A-Za-z0-9_-]{4}|gsk_[A-Za-z0-9_-]{4}|"
    r"xai-[A-Za-z0-9_-]{4})[A-Za-z0-9_-]+")


def mask(text: str) -> str:
    """Anahtar sızıntısına karşı son savunma. Hata metinleri buradan geçer."""
    return _SECRET.sub(r"\1…", text or "")


def load_env(path: str = ENV_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out


def _post(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


# --------------------------------------------------------------- cagiricilar
def _openai_style(url: str, key: str, model: str, messages: list[dict[str, str]],
                  max_tokens: int, new_style: bool = False) -> tuple[str, str, int | None, int | None]:
    # OLCULDU: gpt-5-mini `max_tokens` kabul etmiyor, HTTP 400 donuyor;
    # `max_completion_tokens` istiyor. Eski modeller tersine.
    limit = ({"max_completion_tokens": max_tokens} if new_style
             else {"max_tokens": max_tokens, "temperature": 0.3})
    data = _post(url, {"model": model, "messages": messages, **limit},
                 {"Authorization": f"Bearer {key}"})
    choice = (data.get("choices") or [{}])[0]
    usage = data.get("usage") or {}
    return ((choice.get("message") or {}).get("content", ""),
            str(choice.get("finish_reason") or ""),
            usage.get("prompt_tokens"), usage.get("completion_tokens"))


def _gemini(key: str, model: str, messages: list[dict[str, str]],
            max_tokens: int) -> tuple[str, str, int | None, int | None]:
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    user = "\n\n".join(m["content"] for m in messages if m.get("role") != "system")
    body: dict[str, Any] = {
        "contents": [{"parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/"
                 f"{model}:generateContent?key={key}", body, {})
    candidate = (data.get("candidates") or [{}])[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    # Gemini token alanlari farkli adlarda gelir; tek bicime indirilmezse
    # defter saglayicilar arasinda karsilastirilamaz olur.
    meta = data.get("usageMetadata") or {}
    return ("".join(p.get("text", "") for p in parts),
            str(candidate.get("finishReason") or ""),
            meta.get("promptTokenCount"), meta.get("candidatesTokenCount"))


def _anthropic(key: str, model: str, messages: list[dict[str, str]],
               max_tokens: int) -> tuple[str, str, int | None, int | None]:
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    turns = [m for m in messages if m.get("role") != "system"]
    body: dict[str, Any] = {"model": model, "max_tokens": max_tokens,
                            "messages": turns}
    if system:
        body["system"] = system
    data = _post("https://api.anthropic.com/v1/messages", body,
                 {"x-api-key": key, "anthropic-version": "2023-06-01"})
    parts = data.get("content") or []
    usage = data.get("usage") or {}
    return ("".join(p.get("text", "") for p in parts if p.get("type") == "text"),
            str(data.get("stop_reason") or ""),
            usage.get("input_tokens"), usage.get("output_tokens"))


@dataclass(frozen=True)
class Provider:
    name: str
    env_key: str
    default_model: str
    call: Callable[..., tuple[str, str, int | None, int | None]]
    paid: bool = False
    note: str = ""
    # Akil yuruten modeller butcenin bir kismini gorunmeyen ic dusunceye
    # harcar. OLCULDU: gpt-5-mini 220 token ile 0 kelime dondu
    # (finish_reason=length), 800 token ile duzgun cevap verdi. Bu sessiz
    # bir hata sinifi: istisna yok, hata kodu yok, yalniz bos metin.
    min_tokens: int = 0


# Sira OLCULMUSTUR, tahmin degil. Ucretsiz ve hizli olan once.
PROVIDERS: tuple[Provider, ...] = (
    Provider("gemini", "GEMINI_API_KEY", "gemini-3.5-flash-lite",
             lambda k, m, msg, t: _gemini(k, m, msg, t),
             note="0,9-1,2 s olculdu; en hizli"),
    Provider("openrouter", "OPENROUTER_API_KEY",
             "nvidia/nemotron-3-ultra-550b-a55b:free",
             lambda k, m, msg, t: _openai_style(
                 "https://openrouter.ai/api/v1/chat/completions", k, m, msg, t),
             note="2,2 s; 550B ucretsiz"),
    Provider("claude", "ANTHROPIC_API_KEY", "claude-haiku-4-5-20251001",
             lambda k, m, msg, t: _anthropic(k, m, msg, t),
             paid=True, note="2,3 s; olcumde en iyi cevap -- UCRETLI"),
    Provider("openai", "OPENAI_API_KEY", "gpt-5-mini",
             lambda k, m, msg, t: _openai_style(
                 "https://api.openai.com/v1/chat/completions", k, m, msg, t,
                 new_style=True),
             paid=True, min_tokens=800,
             note="9,7 s (800 token ile); max_completion_tokens gerekir -- UCRETLI"),
    # NVIDIA ve GROQ bilerek disarida: NVIDIA "Here's a thinking process"
    # sizdiriyor ve kesiliyor, GROQ HTTP 403/1010 donuyor (olculdu).
)


# ══════════════════════════════════════════════════════════════════════
# İŞ KADEMELERİ — hangi iş hangi modelle yapılır
#
# 🔴 Bu liste FİYAT sırası değil, YETENEK sırasıdır. Her kademenin kendi
# birinci tercihi ve kendi yedekleri vardır. Sistemin susmaması için her
# kademenin sonunda mutlaka çalıştığı kanıtlanmış bir sağlayıcı durur.
KADEME: dict[str, tuple[str, ...]] = {
    # Yüksek hacim, düşük risk. 79 çağrıda 0 hata ile ölçüldü.
    "hizli": ("gemini", "openrouter"),
    # Müşteriye giden metin ve karar besleyen analiz. Claude birinci:
    # 20.09 ölçümünde en iyi cevabı o verdi. gpt-5-mini ikinci ve daha
    # ucuz. Gemini EN SONDA duruyor -- kalite tercihi değil, sistemin
    # susmaması için son çare.
    "muhakeme": ("claude", "openai", "gemini", "openrouter"),
}
VARSAYILAN_KADEME = "hizli"


def _kademe_sirasi(kademe: str) -> tuple:
    """Kademenin sağlayıcı nesnelerini sırayla döndürür."""
    adlar = KADEME.get(kademe) or KADEME[VARSAYILAN_KADEME]
    sozluk = {p.name: p for p in PROVIDERS}
    return tuple(sozluk[a] for a in adlar if a in sozluk)


def _record_usage(provider, model: str, started: float, *,
                  is_anahtari: str | None = None, kademe: str | None = None,
                  prompt_tokens: int | None = None,
                  completion_tokens: int | None = None,
                  ok: bool = True, error: str = "") -> None:
    """Maliyet defterine yazar. Defter bozulursa çağrı ENGELLENMEZ."""
    try:
        from .usage import record
        record(provider.name, model, provider.paid,
               is_anahtari=is_anahtari, kademe=kademe,
               prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
               elapsed_s=round(time.perf_counter() - started, 2),
               ok=ok, error=error)
    except Exception:  # noqa: BLE001 - maliyet kaydi cagriyi durduramaz
        pass


class NoProvider(RuntimeError):
    """Hiçbir sağlayıcı yanıt veremedi."""


def available(env: dict[str, str] | None = None) -> list[str]:
    cfg = env if env is not None else load_env()
    return [p.name for p in PROVIDERS if cfg.get(p.env_key)]


def generate(messages: list[dict[str, str]], max_tokens: int = 400,
             deep: bool = False, env: dict[str, str] | None = None,
             kademe: str | None = None,
             is_anahtari: str | None = None) -> dict[str, Any]:
    """İŞİN KADEMESİNE göre model seçer, düşerse yedeğe iner.

    `kademe="hizli"`     sınıflandırma, sorgu üretimi, kısa özet
    `kademe="muhakeme"`  müşteriye giden metin, karar besleyen analiz

    🔴 `deep=True` ARTIK GERÇEKTEN ÇALIŞIYOR. Eskiden "ücretliyi de dene"
    demekti ama sıra yine gemini'den başladığı için hiçbir etkisi yoktu:
    gemini cevap verince zincir orada duruyordu. Ölçüldü -- 79 gemini
    çağrısına karşılık 1 claude, oysa dört çağrı yeri `escalate=True`
    istiyordu. Şimdi `deep=True` doğrudan MUHAKEME kademesini seçer ve
    o kademenin birinci tercihi Claude'dur.

    Her denemenin sonucu `attempts` icinde raporlanir -- hangi saglayici
    neden dustu gorunur olmadan siralama duzeltilemez.
    """
    cfg = env if env is not None else load_env()
    attempts: list[dict[str, str]] = []
    if kademe is None and is_anahtari:
        # 🔴 KADEMEYI KOD DEGIL KAYIT DEFTERI BELIRLER. Defter okunamazsa
        # modul kendi gomulu emniyetine duser; sistem susmaz.
        try:
            from .kademe_kayit import kademe as _kayittan
            kademe = _kayittan(is_anahtari)
        except Exception:  # noqa: BLE001 - defter cagriyi durduramaz
            kademe = None
    if kademe is None:
        kademe = "muhakeme" if deep else VARSAYILAN_KADEME
    sira = _kademe_sirasi(kademe)

    for provider in sira:
        key = cfg.get(provider.env_key)
        if not key:
            attempts.append({"provider": provider.name, "result": "anahtar yok"})
            continue
        model = cfg.get(f"{provider.name.upper()}_MODEL") or provider.default_model
        started = time.perf_counter()
        budget = max(max_tokens, provider.min_tokens)
        try:
            text, finish, giris_tok, cikis_tok = provider.call(
                key, model, messages, budget)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:120]
            except Exception:  # noqa: BLE001
                pass
            # 🔴 SEBEP DEFTERE DE YAZILIR. Onceki hali yalniz "HTTP 400"
            # kaydediyordu; saglayicinin acikladigi sebep `attempts` icinde
            # cagirana donuyor ve orada KAYBOLUYORDU. Olculdu 25.09.2026:
            # 7 gunde 284 basarisiz Claude cagrisi (401 cagrinin %71'i,
            # 283'u kreatif_brief) ve hicbirinin sebebi bilinmiyordu --
            # defterdeki tek bilgi "HTTP 400" idi.
            # `detail` zaten mask() ile anahtardan arindiriliyor.
            gerekce = f"HTTP {exc.code}: {mask(detail)}" if detail else f"HTTP {exc.code}"
            attempts.append({"provider": provider.name, "result": gerekce})
            _record_usage(provider, model, started, ok=False,
                          error=gerekce,
                          is_anahtari=is_anahtari, kademe=kademe)
            continue
        except Exception as exc:  # noqa: BLE001 - bir saglayici digerini engellemez
            attempts.append({"provider": provider.name,
                             "result": mask(f"{type(exc).__name__}: {exc}")[:120]})
            continue

        if not (text or "").strip():
            attempts.append({"provider": provider.name, "result": "bos cevap"})
            continue
        gecen = round(time.perf_counter() - started, 2)
        _record_usage(provider, model, started, prompt_tokens=giris_tok,
                      completion_tokens=cikis_tok,
                      is_anahtari=is_anahtari, kademe=kademe)
        return {"text": text, "provider": provider.name, "model": model,
                "kademe": kademe, "is_anahtari": is_anahtari,
                "paid": provider.paid, "finish_reason": finish,
                "truncated": finish.lower() in {"length", "max_tokens"},
                "prompt_tokens": giris_tok, "completion_tokens": cikis_tok,
                "elapsed_s": gecen,
                "attempts": attempts}

    raise NoProvider(f"[{kademe}] hiçbir dış sağlayıcı yanıt vermedi: "
                     + "; ".join(f"{a['provider']}={a['result']}" for a in attempts))
