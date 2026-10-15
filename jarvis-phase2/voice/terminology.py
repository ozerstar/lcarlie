"""Small, reviewed vocabulary for the local Turkish speech recognizer.

Keep this list bounded: too many hints can make Whisper insert product names
that the speaker did not say. It is a recognition hint, not a product catalog.
"""

NAMES = (
    "Jarvis", "L'CARLIE", "Lemos Medikal", "HYDRAVIE", "BABYSOFT",
    "KINESIS Plus", "VIREON FOR MEN", "INTIMBLANC", "LIFTELLE",
    "DERMAVASC", "SUNACNEA", "HAIR NOURISHER",
)


def whisper_options() -> dict[str, str]:
    names = ", ".join(NAMES)
    return {
        "initial_prompt": (
            "Türkçe bir Jarvis görüşmesi. Şirket ve ürün adları gerektiğinde "
            f"şöyle yazılır: {names}. Yalnız duyulan sözcükleri yaz."
        ),
        "hotwords": names,
    }
