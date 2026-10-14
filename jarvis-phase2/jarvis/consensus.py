"""Aynı soruyu birden çok kez sorar, cevapları karşılaştırır, en sağlamını seçer.

NEDEN -- SAHİBİN TALEBİ (20.09.2026)
"Aynı soruya farklı cevaplar olur ama bunun analiz edilip doğruluğu
araştırılıp en doğru cevabın bana gelmesi lazım."

Kayıtlı bir ölçüm de aynı yere bakıyordu: aynı soruya 33 farklı cevap
üretilmiş ve fiyatın 1.200 mü 2.400 mü olduğu belirsiz kalmıştı.

TEMEL İLKE: AYRIŞMA BİLGİDİR, GÜRÜLTÜ DEĞİL
Üç cevap aynı sayıyı veriyorsa güven yüksektir. Farklı sayılar veriyorsa
doğru davranış birini seçip diğerlerini gizlemek DEĞİL, "sistem bu konuda
kararsız" demektir. Kararsızlığı saklayan bir cevap, yanlış cevaptan daha
tehlikelidir: kullanıcı ona güvenir.

NEDEN SAYILAR ÜZERİNDEN
Farklı kelimelerle aynı şeyi söylemek çelişki değildir; farklı SAYI söylemek
çelişkidir. Metin benzerliği ölçmek Türkçede kırılgan (aynı kök, onlarca
yüzey biçimi); sayı karşılaştırması ise kesin.

NEDEN MODEL KULLANMIYOR
Cevapları bir modele "hangisi doğru" diye sormak, aynı belirsizliği bir kat
daha ekler. Karşılaştırma tamamen deterministiktir.

MALİYET
Örnek başına bir model çağrısı. Bu yüzden KOŞULLUDUR: ilk cevapta şirketle
ilgili sayı yoksa doğrulama hiç çalışmaz. Risk sayının olduğu yerdedir.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

# Varsayilan ornek sayisi. Tek sayi secilir ki cogunluk her zaman belirli olsun.
DEFAULT_SAMPLES = 3

# Sayi + varsa birimi. Turkce ayirici: binlik nokta, ondalik virgul.
#   "27.810,84 TL"  "%18,8"  "3 satir"  "1.200"
_NUMBER = re.compile(
    r"(?P<pct>%\s?)?(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<unit>%|TL|₺|adet|gün|gun|saat|kez|satır|satir)?",
    re.IGNORECASE)

# Sayi sayilmayacak baglamlar: tarih parcalari ve sira numaralari tek basina
# celiski uretmez ("2026", "1.") ve gereksiz ayrismaya yol acar.
_IGNORED = {"2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027"}


# Turkce binlik ayirici: nokta, ve ardindan TAM UC hane. "1.200" -> 1200.
# Bu desen olmadan "1.200 TL" ondalik sanilip 1,2 TL'ye donusuyordu ve iki
# farkli fiyat ayni sayi gibi karsilastiriliyordu. Test yakaladi.
_THOUSANDS = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def _canonical(raw: str) -> str:
    """'27.810,84' -> '27810.84', '1.200' -> '1200', '3.14' -> '3.14'.

    Kural: virgul varsa ondalik odur ve noktalar binliktir. Virgul yoksa
    nokta ancak TAM UC haneli gruplar olusturuyorsa binliktir; "3.14" gibi
    bir sayida ondalik kalir.
    """
    if "," in raw:
        value = raw.replace(".", "").replace(",", ".")
    elif _THOUSANDS.match(raw):
        value = raw.replace(".", "")
    else:
        value = raw
    try:
        number = float(value)
    except ValueError:
        return raw
    return f"{number:.10g}"


def numeric_claims(text: str) -> Counter:
    """Metindeki sayısal iddialar. Birim varsa sayının parçasıdır.

    "1.200 TL" ile "1.200 adet" ayni sayi degildir; birimi ayirmak
    yanlis celiski uretirdi.
    """
    claims: Counter = Counter()
    for match in _NUMBER.finditer(text or ""):
        raw = match.group("num")
        if raw in _IGNORED:
            continue
        unit = (match.group("unit") or "").upper().replace("₺", "TL")
        if match.group("pct"):
            unit = "%"
        claims[f"{_canonical(raw)}{unit}"] += 1
    return claims


@dataclass(frozen=True)
class Consensus:
    answer: str
    samples: int
    agreement: float
    agreed: tuple[str, ...] = ()
    disputed: tuple[dict[str, Any], ...] = ()
    all_answers: tuple[str, ...] = ()
    model_calls: int = 0
    note: str = ""
    errors: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "samples": self.samples,
                "agreement": round(self.agreement, 3),
                "agreed_claims": list(self.agreed),
                "disputed_claims": [dict(d) for d in self.disputed],
                "model_calls": self.model_calls, "note": self.note,
                "errors": list(self.errors)}


def compare(answers: list[str]) -> tuple[tuple[str, ...], tuple[dict[str, Any], ...], float]:
    """Cevapları sayısal iddia düzeyinde karşılaştırır.

    Doner: (uzlasilan iddialar, cekismeli iddialar, uzlasma orani)
    """
    if not answers:
        return (), (), 0.0
    per_answer = [set(numeric_claims(a)) for a in answers]
    universe: set[str] = set().union(*per_answer) if per_answer else set()
    if not universe:
        # Sayi yoksa celiski de yok. Bu bir uzlasma DEGILDIR, sadece
        # olculecek bir sey olmamasidir; oran 1.0 yazmak yaniltici olurdu.
        return (), (), 1.0

    majority = len(answers) // 2 + 1
    agreed, disputed = [], []
    for claim in sorted(universe):
        count = sum(1 for claims in per_answer if claim in claims)
        if count >= majority:
            agreed.append(claim)
        else:
            disputed.append({"claim": claim, "seen_in": count, "of": len(answers)})
    ratio = len(agreed) / len(universe) if universe else 1.0
    return tuple(agreed), tuple(disputed), ratio


def select(answers: list[str], agreed: tuple[str, ...],
           disputed: tuple[dict[str, Any], ...]) -> str:
    """Uzlaşılan iddiaları en çok, çekişmelileri en az taşıyan cevabı seçer.

    Esitlikte KISA olan tercih edilir: sahibin talimati "az, oz ve net".
    """
    if not answers:
        return ""
    disputed_set = {d["claim"] for d in disputed}
    agreed_set = set(agreed)

    def score(answer: str) -> tuple[int, int]:
        claims = set(numeric_claims(answer))
        return (len(claims & agreed_set) - 2 * len(claims & disputed_set),
                -len(answer))

    return max(answers, key=score)


def has_company_numbers(text: str) -> bool:
    """Doğrulamaya değer mi? Şirketle ilgili sayı yoksa çalıştırmaya gerek yok.

    Dogrulama her cevap icin ornek sayisi kadar model cagrisi demektir.
    Selamlasmada calistirmak sureyi uc katina cikarir ve hicbir sey korumaz.
    """
    return bool(numeric_claims(text))


def run(ask: Callable[[], str], first: str | None = None,
        samples: int = DEFAULT_SAMPLES) -> Consensus:
    """Aynı soruyu birkaç kez sorar ve sonucu karşılaştırır.

    `ask` her cagrildiginda yeni bir cevap uretmelidir. `first` verilirse
    ilk ornek olarak kullanilir ve bir cagri tasarruf edilir.

    Bir ornek hata verirse KAYDEDILIR ve diger orneklerle devam edilir; tek
    bir saglayici hatasi dogrulamayi tamamen iptal etmemeli.
    """
    answers: list[str] = []
    errors: list[str] = []
    calls = 0
    if first:
        answers.append(first)
    while len(answers) < max(1, samples):
        try:
            answers.append(ask())
            calls += 1
        except Exception as exc:  # noqa: BLE001 - tek ornek hatasi her seyi bitirmez
            errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
            break

    if len(answers) < 2:
        return Consensus(answer=answers[0] if answers else "", samples=len(answers),
                         agreement=0.0, all_answers=tuple(answers), model_calls=calls,
                         errors=tuple(errors),
                         note="Tek örnek alınabildi; karşılaştırma yapılamadı.")

    agreed, disputed, ratio = compare(answers)
    best = select(answers, agreed, disputed)
    if disputed:
        note = (f"{len(answers)} deneme, {len(disputed)} sayıda ayrışma var: "
                + ", ".join(d["claim"] for d in disputed[:4])
                + ". Bu rakamlar doğrulanmadan kullanılmamalı.")
    elif agreed:
        note = f"{len(answers)} denemenin {len(agreed)} sayısında tam uzlaşma."
    else:
        note = f"{len(answers)} deneme; karşılaştırılacak sayısal iddia yok."
    return Consensus(answer=best, samples=len(answers), agreement=ratio,
                     agreed=agreed, disputed=disputed, all_answers=tuple(answers),
                     model_calls=calls, note=note, errors=tuple(errors))
