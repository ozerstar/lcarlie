"""Small, reviewed vocabulary for the local Turkish speech recognizer.

Keep this list bounded: too many hints can make Whisper insert product names
that the speaker did not say. It is a recognition hint, not a product catalog.
"""
import re

NAMES = (
    "Jarvis", "L'CARLIE", "Lemos Medikal", "HYDRAVIE", "BABYSOFT",
    "KINESIS Plus", "VIREON FOR MEN", "INTIMBLANC", "LIFTELLE",
    "DERMAVASC", "SUNACNEA", "HAIR NOURISHER",
)

# Observed in the local Turkish STT check. Keep corrections exact and rare;
# broad fuzzy matching could turn an ordinary request into a product request.
_OBSERVED_VARIANTS = {
    "hidalve": "HYDRAVIE",
    "hidravu": "HYDRAVIE",
    "hidraube": "HYDRAVIE",
    "hidrolye": "HYDRAVIE",
    "lecerle": "L'CARLIE",
    "lejarla": "L'CARLIE",
}
_VARIANT_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(value) for value in _OBSERVED_VARIANTS) + r")(?!\w)",
    re.IGNORECASE,
)


def normalize_transcript(text: str) -> str:
    return _VARIANT_PATTERN.sub(lambda match: _OBSERVED_VARIANTS[match.group().casefold()], text)


def whisper_options() -> dict[str, str]:
    names = ", ".join(NAMES)
    return {
        "initial_prompt": (
            "Türkçe bir Jarvis görüşmesi. Şirket ve ürün adları gerektiğinde "
            f"şöyle yazılır: {names}. Yalnız duyulan sözcükleri yaz."
        ),
        "hotwords": names,
    }
