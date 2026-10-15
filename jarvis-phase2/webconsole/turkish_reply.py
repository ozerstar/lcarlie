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


def ensure(value: str, rewrite: Callable[[str], str]) -> str:
    answer = (value or "").strip()
    if not is_english_prose(answer):
        return answer
    try:
        translated = rewrite(answer).strip()
    except Exception:  # Model failure should not publish the English draft.
        return UNAVAILABLE
    return translated if translated and not is_english_prose(translated) else UNAVAILABLE
