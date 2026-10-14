"""Model layer: local-first, evidence-grounded synthesis.

    DETERMINISTIC -> LOCAL_MODEL -> EXTERNAL_MODEL

Escalation is by need, not by habit. A question Company Memory can answer
exactly never reaches a model; `should_use_model()` is the gate and the
conversational router asks it before anything else. A question that genuinely
requires open-ended reasoning gets the local model first, and only a failure
or an explicit high-complexity request escalates outward.

Grounding is structural, not a request in the prompt. `evidence_refs` on the
answer are copied from the evidence the caller supplied -- they are never
parsed out of the model's text -- so a model cannot invent a source that was
not read. It can only interpret, relate, summarise and propose options over
evidence that already exists.

Provider states reuse jarvis.adapter_factory.AdapterState, so a model
provider is describable in the same vocabulary as every other capability and
can be handed to the existing routing boundary unchanged.

No new secret system: the external key is read at call time from the Kimi
config that is already on this host, and never logged, returned or persisted.
Nothing here can take an external business action; the layer has no path to
one.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .adapter_factory import AdapterState

from . import answer_guard, is_sinifi, kademe_kaydi

# The GPU box reaches the server through a reverse SSH tunnel, so from
# here it is just another loopback port. When the desktop is off the
# tunnel is gone, the health check fails, and the chain moves on.
GPU_URL = os.environ.get("JARVIS_GPU_MODEL_URL", "http://127.0.0.1:8098/v1")
LOCAL_URL = os.environ.get("JARVIS_LOCAL_MODEL_URL", "http://127.0.0.1:8099/v1")
LOCAL_MODEL = os.environ.get("JARVIS_LOCAL_MODEL", "Qwen3-4B-Instruct-2507-Q4_K_M")
GPU_MODEL = os.environ.get("JARVIS_GPU_MODEL", LOCAL_MODEL)
EXTERNAL_URL = os.environ.get("JARVIS_EXTERNAL_MODEL_URL", "https://openrouter.ai/api/v1")
EXTERNAL_MODEL = os.environ.get("JARVIS_EXTERNAL_MODEL",
                                "nvidia/nemotron-3-super-120b-a12b:free")
KIMI_CONFIG = os.environ.get("JARVIS_KIMI_CONFIG", "/root/kimi-sandbox-home/config.toml")

# Context budget. The model gets the question and the evidence that bears on
# it -- never a Company Memory dump. These caps are what keep a 4B model on a
# 4-core host answering in seconds rather than minutes.
MAX_EVIDENCE_ITEMS = 12
MAX_EVIDENCE_CHARS = 6000
# 320 Turkce icin dardi (sondan eklemeli dil kelime basina daha cok token
# yer) ve cevaplar cumle ortasinda kesiliyordu. Amac uzun cevap degil TAM
# cevap; istem kisa yazmayi zaten soyluyor.
MAX_ANSWER_TOKENS = int(os.environ.get("JARVIS_MODEL_MAX_TOKENS", "512"))
# Below this a reply is not an answer; it is the small model giving up.
MIN_USEFUL_ANSWER_CHARS = 24
# A knowledge-backed answer on this CPU can legitimately take a minute.
# Timing out and serving the canned fallback after that much work is the
# worst outcome available: slow is recoverable, discarded is not.
LOCAL_TIMEOUT_S = float(os.environ.get("JARVIS_LOCAL_MODEL_TIMEOUT_S", "240"))
EXTERNAL_TIMEOUT_S = 90.0

TIER_DETERMINISTIC = "DETERMINISTIC"
TIER_GPU = "LOCAL_GPU"
TIER_LOCAL = "LOCAL_MODEL"
TIER_EXTERNAL = "EXTERNAL_MODEL"

GROUNDING_SYSTEM = (
    "Sen L'CARLIÉ şirketinin analiz asistanısın. Kurallar:\n"
    "1. Şirketle ilgili HER sayı ve olgu yalnızca sana verilen KANIT bölümünden "
    "gelebilir. Kanıtta olmayan bir rakam, tarih, ürün veya müşteri bilgisi ÜRETME.\n"
    "2. Bir şeyi bilmiyorsan 'bu veri yok' de. Tahmin etme.\n"
    "3. Genel ticari muhakeme yapabilirsin, ama onu şirket verisi gibi sunma.\n"
    "4. Hiçbir işlemi uygulayamazsın; öneri üretirsin, kararı insan verir.\n"
    # Dil kurali burada da ACIK olmak zorunda. "Turkce yaz" listenin
    # son maddesiydi ve OLCULDU: Ingilizce sorulan "What are our sales
    # this month?" Ingilizce cevaplandi -- model sorunun diline uydu.
    # CHAT_SYSTEM ile ayni kural, ayni sebeple (sahip karari 20.09.2026).
    "5. HER ZAMAN Türkçe yaz: kısa ve net. Soru İngilizce ya da başka bir "
    "dilde sorulsa bile cevap Türkçe olur."
)


_SENTENCE_END = (".", "!", "?", "\u2026")


def _end_cleanly(text: str, finish_reason: str | None) -> str:
    """Token sınırında kesilen cevabı son TAM cümlede bitirir.

    Siniri yukseltmek tek basina yetmez: her sinir bir gun dolar ve o gun
    kullanici yine yarim kelime gorur. Burada kesilme TESPIT edilir ve cikti
    son cumle sonuna kadar kirpilir.

    Kirpma metnin %40'indan azini birakacaksa yapilmaz (tek uzun cumle
    kesilmistir; kirpmak cevabi yok eder). O durumda metin korunur ve sonuna
    acik bir isaret konur -- sessizce yarim birakmaktan iyidir.
    """
    if finish_reason != "length" or not text:
        return text
    stripped = text.rstrip()
    cut = max(stripped.rfind(end) for end in _SENTENCE_END)
    if cut > len(stripped) * 0.4:
        return stripped[:cut + 1]
    return stripped + " […]"


def _accepts_deep(func) -> bool:
    """Bu `complete` uyarlaması `deep` parametresini tanıyor mu?"""
    try:
        import inspect
        return "deep" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


class ModelUnavailable(RuntimeError):
    """No provider could answer. Always caught -- Jarvis falls back, never fails."""


@dataclass
class ModelResult:
    answer: str
    evidence_refs: tuple[str, ...]
    confidence: str
    missing_data: tuple[str, ...]
    model: str | None
    tier: str
    model_calls: int
    duration_ms: float
    first_token_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    context_chars: int = 0
    provider_states: dict[str, str] = field(default_factory=dict)
    # Kademe kaniti: kucuk modelin cevabinda bulunan kusurlar. Bos tuple
    # "kusur yok" demek; None "hic bakilmadi" demek. Ikisi ayri durumdur
    # ve karistirilmasi gecmiste hata uretti.
    yukseltme_kusurlari: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        data["missing_data"] = list(self.missing_data)
        if self.yukseltme_kusurlari is not None:
            data["yukseltme_kusurlari"] = list(self.yukseltme_kusurlari)
        return data


# --- deterministic gate -------------------------------------------------
# Wording that asks for a COUNT or a STATE has an exact answer in Company
# Memory; sending it to a model would be slower, less accurate and would
# invent precision. Wording that asks WHY, or for an assessment, does not.
_EXACT_ANSWER_TERMS = (
    "kaç", "kac", "ne kadar", "toplam", "sayısı", "sayisi", "listele",
    "how many", "total",
)
_REASONING_TERMS = (
    "neden", "niçin", "nicin", "niye", "değerlendir", "degerlendir", "yorumla",
    "öneri", "oneri", "tavsiye", "ne yapmalı", "ne yapmali", "karşı çık",
    "karsi cik", "itiraz", "risk", "strateji", "açıkla", "acikla", "karşılaştır",
    "karsilastir", "birlikte değerlendir", "birlikte degerlendir", "analiz et",
    "en önemli", "en onemli", "problem", "sorun", "fırsat", "firsat",
    "why", "assess", "evaluate", "recommend",
)


# Katlama TEK yerde tanımlı: jarvis.is_sinifi.fold. Burada ikinci bir kopya
# tutmak, ölçülen "RAKİP" -> "raki̇p" hatasını iki yerde düzeltmek demekti.
# `should_use_model` de bundan faydalanır: "LİSTELE" artık eşleşiyor.
_fold = is_sinifi.fold


# Eski hâli burada bir KELİME LİSTESİ tutuyordu. Liste iyi seçilmişti ama tek
# savunmaydı ve ölçülen boşluk şuydu: "Bu krem hangi ürünle kullanılır?" hiçbir
# terime takılmıyor, 280 karakterin altında -> küçük modele düşüyordu. Sahibin
# kararına girecek bilgi, kalitesi ölçülmemiş modelden geliyordu.
#
# Karar artık `jarvis.is_sinifi` kapısında: "bu soru zor mu" (tahmin) yerine
# "bu cevap neye dönüşüyor" (olgu) sorulur. Terimler oraya taşındı ve
# araştırma/değerlendirme terimleriyle genişletildi.


def needs_escalation(message: str, *, amac: str | None = None) -> bool:
    """Bu iş güçlü modele mi gitmeli?

    Karar girdisi, yayın adayı ve müşteriye giden metin güçlü modele gider.
    Mekanik iş (sınıflandırma, özet, biçim) ve olgu sorusu gitmez.

    `amac` çağıran tarafın beyanıdır ve tahminden üstündür: kreatif hattı
    reklam metni ürettiğini bilir, metnin taranmasına gerek yoktur.
    """
    return is_sinifi.guclu_model_gerekir(is_sinifi.siniflandir(message, amac=amac))


def should_use_model(message: str) -> bool:
    """True only when the question genuinely needs open-ended reasoning.

    A counting question answered by a model is a regression, not a feature:
    Company Memory already knows the exact number.
    """
    text = _fold(message)
    if any(_fold(term) in text for term in _REASONING_TERMS):
        return True
    if any(_fold(term) in text for term in _EXACT_ANSWER_TERMS):
        return False
    return False


# --- providers ----------------------------------------------------------
def _post(url: str, body: dict[str, Any], timeout: float,
          headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class LocalProvider:
    """llama.cpp server on loopback. No key, no egress, no cost."""

    name = "local"
    tier = TIER_LOCAL
    # A dead tunnel must be discovered fast: the GPU box being off is the
    # normal case at night, not an exception worth waiting on.
    health_timeout_s = 3.0

    def __init__(self, url: str = LOCAL_URL, model: str = LOCAL_MODEL):
        self.url = url.rstrip("/")
        self.model = model

    def state(self) -> AdapterState:
        try:
            health = self.url.rsplit("/v1", 1)[0] + "/health"
            with urllib.request.urlopen(health, timeout=self.health_timeout_s) as response:
                ok = json.loads(response.read()).get("status") == "ok"
            return AdapterState.AVAILABLE if ok else AdapterState.DEGRADED
        except Exception:  # noqa: BLE001 - an unreachable provider is a state
            return AdapterState.UNAVAILABLE

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        data = _post(f"{self.url}/chat/completions",
                     # cache_prompt: the system prompt is identical every turn.
                     # Re-evaluating it cost 4485 ms; cached it costs 159 ms.
                     {"messages": messages, "max_tokens": max_tokens,
                      "temperature": 0.3, "stream": False, "cache_prompt": True},
                     timeout=LOCAL_TIMEOUT_S)
        usage = data.get("usage") or {}
        choice = data["choices"][0]
        # finish_reason HIC okunmuyordu: token siniri dolunca model cumlenin
        # ortasinda duruyor, kod bunu normal bir cevap saniyordu. Kullanicinin
        # "cevap yarida kesiliyor" sikayeti tam olarak buydu.
        return {"text": _end_cleanly(choice["message"]["content"],
                                     choice.get("finish_reason")),
                "model": self.model,
                "finish_reason": choice.get("finish_reason"),
                "truncated": choice.get("finish_reason") == "length",
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}


    def stream(self, messages: list[dict[str, str]], max_tokens: int):
        """Yield text deltas as they are produced.

        Generation speed is unchanged -- about 7 tokens a second on this host.
        What changes is that the first words arrive in well under a second
        instead of after the whole answer is finished.
        """
        body = json.dumps({"messages": messages, "max_tokens": max_tokens,
                           "temperature": 0.3, "stream": True,
                           "cache_prompt": True}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=LOCAL_TIMEOUT_S) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                try:
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                text = delta.get("content")
                if text:
                    yield text


class ExternalProvider:
    """OpenRouter, using the key already on this host.

    The key is read from the existing Kimi config at call time and never
    logged, returned or written anywhere. This adds no secret store; if the
    file is absent the provider is simply UNAVAILABLE.
    """

    name = "external"
    tier = TIER_EXTERNAL

    # A 429 is not a per-call accident, it is a quota that stays exhausted.
    # Remembering it keeps every later escalation from paying seconds to
    # rediscover the same answer.
    RATE_LIMIT_COOLDOWN_S = 900

    def __init__(self, url: str = EXTERNAL_URL, model: str = EXTERNAL_MODEL):
        self.url = url.rstrip("/")
        self.model = model
        self._rate_limited_until = 0.0

    def _multi_keys(self) -> bool:
        """Çok sağlayıcılı zincirde kullanılabilir anahtar var mı?"""
        try:
            from .providers import available
            return bool(available())
        except Exception:  # noqa: BLE001
            return False

    def _key(self) -> str | None:
        try:
            with open(KIMI_CONFIG, encoding="utf-8") as kaynak:
                text = kaynak.read()
        except OSError:
            return None
        block = re.search(r"\[providers\.openrouter\](.*?)(\n\[|\Z)", text, re.S)
        if not block:
            return None
        found = re.search(r'api_key\s*=\s*"([^"]+)"', block.group(1))
        return found.group(1) if found else None

    def state(self) -> AdapterState:
        if not self._key() and not self._multi_keys():
            return AdapterState.UNAVAILABLE
        if time.time() < self._rate_limited_until:
            return AdapterState.RATE_LIMITED
        return AdapterState.AVAILABLE

    def complete(self, messages: list[dict[str, str]], max_tokens: int,
                 deep: bool = False,
                 is_anahtari: str | None = None) -> dict[str, Any]:
        # Once cok saglayicili zincir: OLCULDU (20.09.2026) --
        #   gemini 1,0 s | openrouter 2,2 s | [ucretli] claude 2,3 s, openai 4,5 s
        # Ucretli saglayici yalniz deep=True ile denenir. Zincir hicbir cevap
        # veremezse asagidaki eski OpenRouter yolu aynen calisir.
        try:
            from .providers import NoProvider, generate as _multi_generate
        except Exception:  # noqa: BLE001 - modul yoklugu bir durumdur
            _multi_generate = None  # type: ignore[assignment]
        if _multi_generate is not None:
            try:
                out = _multi_generate(messages, max_tokens=max_tokens, deep=deep,
                                      is_anahtari=is_anahtari)
            except NoProvider:
                out = None
            except Exception:  # noqa: BLE001 - zincir hatasi eski yolu engellemez
                out = None
            if out:
                self.model = f"{out['provider']}/{out['model']}"
                return {"text": _end_cleanly(out["text"], out.get("finish_reason")),
                        "model": self.model,
                        "provider": out["provider"], "paid": out["paid"],
                        "finish_reason": out.get("finish_reason"),
                        "truncated": out.get("truncated", False),
                        "elapsed_s": out.get("elapsed_s"),
                        "prompt_tokens": None, "completion_tokens": None}

        key = self._key()
        if not key:
            raise ModelUnavailable("no external provider credential available")
        try:
            data = _post(f"{self.url}/chat/completions",
                         {"model": self.model, "messages": messages,
                          "max_tokens": max_tokens, "temperature": 0.3},
                         timeout=EXTERNAL_TIMEOUT_S,
                         headers={"Authorization": f"Bearer {key}"})
        except urllib.error.HTTPError as exc:
            # 429 is the documented free-tier condition; it is a state, not a bug.
            if exc.code == 429:
                self._rate_limited_until = time.time() + self.RATE_LIMIT_COOLDOWN_S
                raise ModelUnavailable("external provider RATE_LIMITED") from None
            raise ModelUnavailable(f"external provider HTTP_{exc.code}") from None
        usage = data.get("usage") or {}
        choice = data["choices"][0]
        # finish_reason HIC okunmuyordu: token siniri dolunca model cumlenin
        # ortasinda duruyor, kod bunu normal bir cevap saniyordu. Kullanicinin
        # "cevap yarida kesiliyor" sikayeti tam olarak buydu.
        return {"text": _end_cleanly(choice["message"]["content"],
                                     choice.get("finish_reason")),
                "model": self.model,
                "finish_reason": choice.get("finish_reason"),
                "truncated": choice.get("finish_reason") == "length",
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}


# --- context compilation ------------------------------------------------
def compile_context(evidence: Iterable[dict[str, Any]]) -> tuple[str, tuple[str, ...], int]:
    """Only what bears on the question, under a hard budget.

    Returns the rendered block, the refs it was built from, and its size.
    Refs travel separately from the text precisely so the answer's refs can be
    the ones we READ, not the ones a model wrote.
    """
    lines: list[str] = []
    refs: list[str] = []
    used = 0
    for item in list(evidence)[:MAX_EVIDENCE_ITEMS]:
        ref = str(item.get("ref") or item.get("source") or "unknown")
        summary = str(item.get("summary") or item.get("detail") or "")
        rendered = f"- {ref}: {summary}"
        if used + len(rendered) > MAX_EVIDENCE_CHARS:
            break
        lines.append(rendered)
        used += len(rendered)
        if ref not in refs:
            refs.append(ref)
    return "\n".join(lines), tuple(refs), used


# ── DIS CAGRI BUTCESI ────────────────────────────────────────────────────
#
# 🔴 SEBEBI OLCULMUS BIR OLAY. 25.09.2026'da tek bir is (`kreatif_brief`)
# gunun 521 basarili dis model cagrisinin 400'unu yapti; onceki gun
# TOPLAM 55 cagri vardi. Yirmi kat. Is 5 saatlik zaman asimina ugrayip
# olduruldu, yani bu cagrilarin buyuk kismindan CIKTI DA ALINMADI.
#
# Birim maliyet kucuk (olculdu: 7 gunde 4,46 TL); sorun HACIM ve
# GORUNMEZLIK. Kacak bir dongu gece boyunca bütceyi yiyebilir ve kimse
# sabaha kadar fark etmez.
#
# KAPI SAYMAYA DAYANIR, TAHMINE DEGIL: kademe telemetrisi zaten her
# denemeyi yaziyor (state/kademe.jsonl). Butce o dosyadan okunur.
#
# BUTCE DOLUNCA NE OLUR: dis saglayici o istek icin ATLANIR ve telemetriye
# `gerekce=BUTCE_DOLDU` yazilir. Sessizce bos cevap donmez -- "soramadim"
# ile "cevap yok" bu projede ayri durumlardir.
#
# 0 = sinirsiz (varsayilan degil). Degisiklik icin JARVIS_DIS_CAGRI_BUTCESI.
DIS_CAGRI_BUTCESI = int(os.environ.get("JARVIS_DIS_CAGRI_BUTCESI", "600"))

# Tek bir isin gunluk payi. `kreatif_brief` 400 cagri yapti; hicbir tek is
# gunluk butcenin yarisindan fazlasini tek basina yiyememeli.
IS_BASINA_BUTCE = int(os.environ.get("JARVIS_IS_BASINA_BUTCE", "150"))

_butce_onbellek: dict = {"gun": None, "toplam": 0, "isler": {}}


def dis_cagri_sayaci(bugun: str | None = None) -> dict:
    """Bugunku basarili dis model cagrilari -- telemetriden OKUNUR."""
    import json as _json

    gun = bugun or time.strftime("%Y-%m-%d")
    if _butce_onbellek["gun"] == gun and _butce_onbellek.get("_taze", 0) > time.time():
        return {"toplam": _butce_onbellek["toplam"],
                "isler": dict(_butce_onbellek["isler"])}

    toplam, isler = 0, {}
    try:
        yol = kademe_kaydi._yol()
        if yol.is_file():
            with open(yol, encoding="utf-8") as f:
                for satir in f:
                    satir = satir.strip()
                    if not satir or gun not in satir:
                        continue
                    try:
                        k = _json.loads(satir)
                    except ValueError:
                        continue
                    if (k.get("ts") or "")[:10] != gun:
                        continue
                    if k.get("kademe") != "EXTERNAL_MODEL":
                        continue
                    if k.get("sonuc") != kademe_kaydi.SONUC_BASARILI:
                        continue
                    toplam += 1
                    anahtar = k.get("is_anahtari") or "(yok)"
                    isler[anahtar] = isler.get(anahtar, 0) + 1
    except Exception:  # noqa: BLE001 - sayamamak butceyi kapatmaz
        # Telemetri okunamiyorsa butce UYGULANMAZ. Okunamayan bir olcume
        # dayanip istegi reddetmek, olcum hatasini hizmet kesintisine
        # cevirmek olurdu.
        return {"toplam": -1, "isler": {}}

    _butce_onbellek.update({"gun": gun, "toplam": toplam, "isler": isler,
                            "_taze": time.time() + 20})
    return {"toplam": toplam, "isler": dict(isler)}


def butce_doldu_mu(is_anahtari: str | None) -> str | None:
    """Doluysa SEBEBI dondurur, degilse None."""
    if DIS_CAGRI_BUTCESI <= 0:
        return None
    sayac = dis_cagri_sayaci()
    if sayac["toplam"] < 0:
        return None                     # sayilamadi -> engelleme
    if sayac["toplam"] >= DIS_CAGRI_BUTCESI:
        return "BUTCE_DOLDU gunluk %d" % DIS_CAGRI_BUTCESI
    if is_anahtari and IS_BASINA_BUTCE > 0:
        kendi = sayac["isler"].get(is_anahtari, 0)
        if kendi >= IS_BASINA_BUTCE:
            return "BUTCE_DOLDU is basina %d (%s)" % (IS_BASINA_BUTCE, is_anahtari)
    return None


def _cevaplayan_model(sonuc: object, yedek: "str | None") -> "str | None":
    """Cevabi GERCEKTEN veren modelin adi.

    🔴 OLCULEN HATA (25.09.2026). Kayit `getattr(provider, "model")`
    yaziyordu; bu, saglayici NESNESININ yapilandirilmis modelidir, cagri
    YAPILMADAN once okunur. Dis saglayici kendi icinde bir zincir
    isletiyor (gemini -> openrouter -> ucretli), dolayisiyla cevabi
    genellikle baska bir model veriyor.

    Uretimde olculdu: cevap `gemini/gemini-3.5-flash-lite`den geldi,
    telemetriye `nvidia/nemotron-3-super-120b-a12b:free` yazildi.

    Bu kozmetik degil: "hangi model calisiyor" ve "ne kadar ucretli
    cagri gitti" analizlerinin tek kaynagi bu alan. Yanlis ad, yanlis
    maliyet demektir.

    Sonuc sozluk degilse ya da model tasimiyorsa yapilandirilmis ada
    DONULUR -- bos birakmak, eski kayitlarla kiyasi imkansiz kilardi.
    """
    if isinstance(sonuc, dict):
        ad = sonuc.get("model")
        if ad:
            return str(ad)[:120]
    return yedek


def _hata_gerekcesi(istisna: BaseException) -> str:
    """Istisnanin SINIFI + SEBEBI. Anahtar sizmaz.

    🔴 NEDEN VAR. Eski hali yalnizca `type(istisna).__name__` yaziyordu.
    25.09.2026'da olculdu: dis kademede 66 kez `OSError` kaydi vardi ve
    hicbiri NE oldugunu soylemiyordu -- DNS mi, baglanti reddi mi, zaman
    asimi mi, sertifika mi? Teshis edilemeyen bir hata, olculmemis hata
    kadar degersizdir.

    Mesaj `providers.mask()` uzerinden gecer: hata metinlerinde API
    anahtari gorunebilir ve telemetri dosyasi sifresizdir. Ikinci bir
    maskeleyici YAZILMADI -- tek dogru yer zaten orasi.

    Sinir 200 karakter: yigin izi degil, sebep isteniyor.
    """
    ad = type(istisna).__name__
    try:
        from .providers import mask
        metin = mask(str(istisna) or "")
    except Exception:  # noqa: BLE001 - maskeleyici yoksa metni HIC yazma
        metin = ""
    if not metin:
        return ad
    # Bazi istisnalar str()'inde sinif adini zaten tasir; tekrarlama.
    if metin.startswith(ad):
        return metin[:200]
    return (ad + ": " + metin)[:200]


class ModelRouter:
    """Local first, external only on failure or explicit escalation."""

    def __init__(self, local: Any | None = None, external: Any | None = None,
                 gpu: Any | None = None):
        # Same class, different endpoint: the GPU box is reached over the
        # reverse tunnel and is otherwise an ordinary llama.cpp server.
        if gpu is not None:
            self.gpu = gpu
        else:
            self.gpu = LocalProvider(url=GPU_URL, model=GPU_MODEL)
            self.gpu.name = "gpu"
            self.gpu.tier = TIER_GPU
        self.local = local if local is not None else LocalProvider()
        self.external = external if external is not None else ExternalProvider()

    def provider_states(self) -> dict[str, str]:
        return {"gpu": self.gpu.state().value,
                "local": self.local.state().value,
                "external": self.external.state().value}

    def _chain(self, escalate: bool) -> list[Any]:
        """API once, yerel model yedek.

        24.09.2026'da sahip karariyla ters cevrildi. Onceki sira yerel-onceydi
        ve gerekcesi hizdi; olcum bu gerekceyi zayiflatti:

          gemini-3.5-flash-lite  0,63 sn  ·  0,30/2,50 USD/1M jeton
          PC-2 RTX 5060          ~0,65 sn isinmis, ilk istekte 14 sn
          VDS CPU                5,9-7,45 jeton/sn -- pratikte kullanilamaz

        Olculmus maliyet: 7 gunde 4,46 TL. API hem hizli hem her zaman acik.
        Yerel modelin asil bedeli para degil BAGIMLILIK: PC acilip kapaniyor,
        tunel dusuyor, GPU'yu ComfyUI ile paylasmak gerekiyor -- 24.09'da
        olculdu, gorsel uretilirken butun ajans 30 dakikaya kadar
        7,45 jeton/sn'ye dusuyordu.

        Yerel kademeler YEDEK olarak kaliyor: API ayakta oldugu surece hic
        yoklanmiyorlar (dongu ilk basarili kademede durur), yani bedava
        sigorta. Anahtar biterse ya da kota dolarsa is durmaz.
        """
        return [self.external, self.gpu, self.local]

    def generate(self, messages: list[dict[str, str]], max_tokens: int,
                 escalate: bool = False,
                 is_anahtari: str | None = None) -> tuple[dict[str, Any], str, int]:
        attempts = 0
        for provider in self._chain(escalate):
            uc = getattr(provider, "name", type(provider).__name__)
            kademe = getattr(provider, "tier", None)
            model_adi = getattr(provider, "model", None)
            durum = provider.state()
            # 🔴 BUTCE KAPISI yalniz DIS saglayiciya uygulanir; yerel
            # kademeler (CPU/GPU/RAM) serbest -- sahip karari 25.09.2026:
            # "API butcesi yedirtme, CPU GPU RAM serbest".
            if durum == AdapterState.AVAILABLE and kademe == "EXTERNAL_MODEL":
                sebep = butce_doldu_mu(is_anahtari)
                if sebep:
                    kademe_kaydi.kaydet(
                        uc=uc, kademe=kademe, model=model_adi,
                        sonuc=kademe_kaydi.SONUC_ATLANDI, gerekce=sebep,
                        deneme=attempts + 1, escalate=escalate,
                        is_anahtari=is_anahtari)
                    continue
            if durum != AdapterState.AVAILABLE:
                # Atlanan kademe de bir olcumdur: makinenin kapali olmasi ile
                # acikken cevap verememesi ayni sey degil.
                kademe_kaydi.kaydet(
                    uc=uc, kademe=kademe, model=model_adi,
                    sonuc=kademe_kaydi.SONUC_ATLANDI,
                    gerekce=getattr(durum, "value", str(durum)),
                    deneme=attempts + 1, escalate=escalate,
                    is_anahtari=is_anahtari)
                continue
            attempts += 1
            basladi = time.perf_counter()
            try:
                # `escalate` iki sey demek: dis saglayiciyi ONCE dene, VE
                # gerekirse UCRETLI saglayiciya kadar in. Ucretli saglayici
                # baska hicbir yoldan cagrilmaz.
                #
                # `deep` yalnizca destekleyen saglayiciya gecirilir: testlerdeki
                # sahte saglayicilar ve eski uyarlayicilar bu parametreyi
                # tanimiyor ve TypeError firlatirdi. Imza kontrolu, hatayi
                # yutmaktan iyidir -- yutsaydik gercek bir TypeError de
                # saglayici dustu diye gorunurdu.
                if provider is self.external and _accepts_deep(provider.complete):
                    result = provider.complete(messages, max_tokens, deep=escalate,
                                               is_anahtari=is_anahtari)
                else:
                    result = provider.complete(messages, max_tokens)
                kademe_kaydi.kaydet(
                    uc=uc, kademe=kademe,
                    model=_cevaplayan_model(result, model_adi),
                    sonuc=kademe_kaydi.SONUC_BASARILI,
                    gecikme_ms=round((time.perf_counter() - basladi) * 1000, 1),
                    deneme=attempts, escalate=escalate,
                    is_anahtari=is_anahtari)
                return result, provider.tier, attempts
            except (ModelUnavailable, urllib.error.URLError, TimeoutError, OSError,
                    KeyError, ValueError) as istisna:
                kademe_kaydi.kaydet(
                    uc=uc, kademe=kademe, model=model_adi,
                    sonuc=kademe_kaydi.SONUC_HATA,
                    gecikme_ms=round((time.perf_counter() - basladi) * 1000, 1),
                    gerekce=_hata_gerekcesi(istisna),
                    deneme=attempts, escalate=escalate,
                    is_anahtari=is_anahtari)
                continue
        kademe_kaydi.kaydet(
            uc="-", kademe=None, sonuc=kademe_kaydi.SONUC_ZINCIR_TUKENDI,
            deneme=attempts, escalate=escalate, is_anahtari=is_anahtari)
        raise ModelUnavailable("no model provider could answer")

    # -- the two capabilities this layer exposes ------------------------
    def synthesize(self, question: str, evidence: Iterable[dict[str, Any]],
                   missing_data: Iterable[str] = (), escalate: bool = False,
                   max_tokens: int = MAX_ANSWER_TOKENS,
                   system: str | None = None,
                   history: list[dict[str, str]] | None = None,
                   known_products: tuple[str, ...] = ()) -> ModelResult:
        started = time.perf_counter()
        block, refs, size = compile_context(evidence)
        missing = tuple(missing_data)
        if not block and system is not None:
            # Conversation, not analysis: no evidence block to wrap around it.
            user = question
        else:
            user = (f"KANIT:\n{block or '(kanıt yok)'}\n\n"
                    + (f"EKSİK VERİ: {', '.join(missing)}\n\n" if missing else "")
                    + f"SORU: {question}")
        # Prior turns sit between the system prompt and the new question, so
        # "onu değil, diğerini" has something to refer back to.
        messages = ([{"role": "system", "content": system or GROUNDING_SYSTEM}]
                    + list(history or [])
                    + [{"role": "user", "content": user}])
        if system is None:
            try:
                from .improvement import Store
                previous_lessons = Store().context(question)
                if previous_lessons:
                    messages[-1]["content"] += "\n\n" + previous_lessons
            except Exception:  # noqa: BLE001 - optional memory cannot break synthesis
                pass
        states = self.provider_states()
        try:
            result, tier, calls = self.generate(messages, max_tokens, escalate)
        except ModelUnavailable as exc:
            raise ModelUnavailable(str(exc)) from None

        # KADEME: küçük model cevapladı, doğrulayıcı bakar, tutmazsa yükselt.
        #
        # Eski hâli yalnız UZUNLUĞA bakıyordu: 24 karakterden uzun her cevap
        # "başarılı" sayılıyordu. Oysa ölçülen kusurlar uzun cevaplarda
        # yaşandı -- uydurma ürün adı, soruyu tekrar etme, samimi hitap.
        # Doğrulayıcı answer_guard.kusurlar(): sıfır model çağrısı.
        #
        # Yalnız ESASLI kusur yükseltir. Emoji/samimi hitap için ikinci bir
        # ücretli çağrı yapmak israf olurdu; onları formalize() bedavaya
        # düzeltiyor. yukseltme_kusurlari sonuca yazılır ki neyin neden
        # yükseldiği ölçülebilsin -- eşik ancak veriyle kalibre edilir.
        # 🔴 None = BAKILMADI, () = bakildi ve kusur bulunmadi. Ilk yazimda
        # ikisini de () yapmistim; kendi testim yakaladi. Bu ayrimi kaybetmek
        # bu projenin tekrar eden kok hatasi: yoklugun SEBEBINI bilmeden
        # yoklugu bir cumleye cevirmek. "Kusursuz cevap" ile "dis saglayici
        # kapali oldugu icin hic bakilmadi" ayni sey degildir.
        yukseltme_kusurlari: tuple[str, ...] | None = None
        # 🔴 KADEME KOSULU KALDIRILDI (24.09.2026). Eskiden bu kapi yalniz
        # cevap YEREL bir kademeden geldiginde calisirdi; mantik "zayif yerel
        # model kotu cevap verirse guclu dis modele yukselt" idi. Zincir
        # API-once yapilinca tier HER ZAMAN EXTERNAL oldu ve kapi sessizce
        # OLU KODA dondu: uydurma urun, cok kisa cevap, hicbiri yakalanmiyordu.
        # Musteriye giden metni koruyan kapi buydu.
        #
        # Denetim artik cevabin nereden geldigine bakmaz -- kusur kusurdur.
        # Yukseltme de kademe degistirmek degil, ayni kademede daha guclu
        # (gerekirse ucretli) saglayiciya inmek demektir: deep=True.
        if not escalate and self.external.state() == AdapterState.AVAILABLE:
            bulgular = answer_guard.kusurlar(
                result.get("text") or "", soru=question,
                known_products=tuple(known_products or ()),
                min_karakter=MIN_USEFUL_ANSWER_CHARS)
            yukseltme_kusurlari = tuple(bulgular)
            if answer_guard.yukseltilmeli(bulgular):
                try:
                    # deep=True olmadan ayni saglayiciya ayni soruyu
                    # tekrar sormak olurdu; yukseltmenin anlami ucretli
                    # saglayiciya inme izni vermektir.
                    if _accepts_deep(self.external.complete):
                        retry = self.external.complete(messages, max_tokens,
                                                       deep=True)
                    else:
                        retry = self.external.complete(messages, max_tokens)
                    result, tier, calls = retry, TIER_EXTERNAL, calls + 1
                except (ModelUnavailable, urllib.error.URLError, TimeoutError,
                        OSError, KeyError, ValueError):
                    pass

        # Confidence follows the EVIDENCE, not the model's self-assessment: a
        # fluent answer over one source is not more trustworthy than a terse
        # one over five.
        if not refs:
            confidence = "LOW"
        elif missing:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH" if len(refs) >= 3 else "MEDIUM"

        return ModelResult(
            answer=result["text"].strip(),
            evidence_refs=refs,               # what we read, never what it wrote
            confidence=confidence, missing_data=missing,
            model=result.get("model"), tier=tier, model_calls=calls,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            context_chars=size, provider_states=states,
            yukseltme_kusurlari=yukseltme_kusurlari,
        )

    def stream_text(self, question: str, system: str, max_tokens: int = 160,
                    history: list[dict[str, str]] | None = None):
        """Stream a conversational reply. Falls back to a single block when the
        local provider is not the one answering."""
        messages = ([{"role": "system", "content": system}]
                    + list(history or [])
                    + [{"role": "user", "content": question}])
        streamer = (self.gpu if self.gpu.state() == AdapterState.AVAILABLE
                    else self.local)
        if streamer.state() == AdapterState.AVAILABLE:
            produced = False
            try:
                for delta in streamer.stream(messages, max_tokens):
                    produced = True
                    yield delta
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                if produced:
                    return
            else:
                return
        result, _tier, _calls = self.generate(messages, max_tokens)
        yield result["text"]

    def decompose_query(self, request: str, count: int = 3) -> list[str]:
        """Generic QUERY_DECOMPOSITION capability: one research request ->
        focused search queries. A contract only -- this layer runs no search."""
        messages = [
            {"role": "system", "content":
             "Araştırma isteklerini odaklı arama sorgularına bölersin. "
             "SADECE JSON dizisi döndür, başka metin yazma."},
            {"role": "user", "content":
             f'İsteği {count} odaklı arama sorgusuna böl. Format: ["sorgu1", ...]\n'
             f"İstek: {request}"},
        ]
        result, _tier, _calls = self.generate(messages, 220)
        text = result["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        queries: list[str] = []
        for item in parsed:
            if isinstance(item, str):
                queries.append(item)
            elif isinstance(item, dict):
                for key in ("sorgu", "query", "q"):
                    if isinstance(item.get(key), str):
                        queries.append(item[key])
                        break
        return queries[:count]
