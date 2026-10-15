"""Keep clearly English model prose out of the Turkish assistant UI."""
from __future__ import annotations

import re
from typing import Callable

_ENGLISH = set("the and you your with from this that have will would should can are was were for about please here what how why there these those their our we they it is of to in on at by as".split())
_TURKISH = set("ve bir bu şu için ile olan olarak ben sen siz biz bugün yarın var yok daha nasıl neden ne hangi bunu sizin bana sana yapabilir önce sonra gerekir gerekiyor edildi edildiğinde".split())
_WORD = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]+")
REWRITE_SYSTEM = (
    "Sen yalnız Türkçe çeviri yapan bir düzeltmensin. Verilen asistan yanıtını sade, anlaşılır Türkçeye çevir. "
    "Sayıları, adları, bağlantıları ve doğrulanabilir bilgileri değiştirme; yeni bilgi ekleme. "
    "Yalnız çevrilmiş yanıtı yaz."
)
UNAVAILABLE = "Yanıt Türkçe hazırlanamadı. Lütfen yeniden deneyin."


def is_english_prose(value: str) -> bool:
    # Names, URLs and a few borrowed words must not trigger a rewrite.
    without_links = re.sub(r"https?://\S+|`[^`]+`", " ", value or "")
    words = [word.casefold() for word in _WORD.findall(without_links)]
    if len(words) < 8:
        return False
    english = sum(word in _ENGLISH for word in words)
    turkish = sum(word in _TURKISH for word in words)
    return english >= 4 and english >= turkish + 2


# Turkceye OZGU harfler. Ingilizce metinde bulunmazlar.
_TR_HARF = set("ışğüöçİŞĞÜÖÇ")


def looks_turkish(value: str) -> bool:
    """POZITIF Turkce kaniti var mi?

    🔴 NEDEN AYRI BIR ISLEV -- OLCULDU 16.10.2026.
    Akis kapisi `not is_english_prose(ornek)` ile aciliyordu, ama
    `is_english_prose` 8 kelimenin ALTINDA her zaman False doner: yani
    kisa ornekte "Ingilizce bulunmadi" bir kanit degil, SESSIZLIKTIR.
    Sonuc olculdu -- 70 ve 106 karakterlik iki cevap panelde HIC akmadi,
    140 karakter esigine hic ulasmadiklari icin tek blok geldi.

    Ustelik o tamponun kisa cevapta koruma degeri de YOKTU: `ensure()`
    ayni esigi kullandigi icin 8 kelimenin altindaki Ingilizce yanit
    zaten oldugu gibi gecerdi. Tampon korumuyordu, sadece geciktiriyordu.

    Burada aranan sey Ingilizcenin YOKLUGU degil, Turkcenin VARLIGI:
      - Turkce islev sozcugu (`_TURKISH`), veya
      - kucuk harfli bir kelimede Turkceye ozgu harf.
    Kucuk harf sarti bilincli: "Çankaya" veya "Müşteri Hizmetleri" gibi
    OZEL ADLAR Ingilizce bir cumlede de gecebilir ve kapiyi yanlislikla
    acardi; cekimli kucuk harfli kelime (`yardımcı`, `gidiyor`) gecmez.
    """
    without_links = re.sub(r"https?://\S+|`[^`]+`", " ", value or "")
    words = _WORD.findall(without_links)
    if any(word.casefold() in _TURKISH for word in words):
        return True
    return any(word == word.lower() and any(ch in _TR_HARF for ch in word)
               for word in words)


def ensure(value: str, rewrite: Callable[[str], str]) -> str:
    answer = (value or "").strip()
    if not is_english_prose(answer):
        return answer
    try:
        translated = rewrite(answer).strip()
    except Exception:  # noqa: BLE001 - model dusse de Ingilizce taslak
        # yayinlanmaz; her hata turu UNAVAILABLE demektir.
        return UNAVAILABLE
    return translated if translated and not is_english_prose(translated) else UNAVAILABLE
