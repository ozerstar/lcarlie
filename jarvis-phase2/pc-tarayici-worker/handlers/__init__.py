# -*- coding: utf-8 -*-
"""Handler kutugu: hedef adi -> arayuzu suren modul.

`worker.py` buradan baska hicbir yerde secici gormez. Yeni bir hedef
eklemek, buraya bir satir ve `handlers/` altina bir dosya eklemektir.

🔴 HEDEF ADLARI VERITABANINDAKI CHECK ILE AYNI OLMAK ZORUNDA
   (`core.tarayici_isi.hedef`). Burada olup orada olmayan bir ad,
   kuyruga hic giremez; orada olup burada olmayan bir ad ise
   "handler yok" diye HATA'ya duser -- sessizce atlanmaz.
"""
from __future__ import annotations

from hatalar import HandlerHatasi

KAYIT: dict[str, str] = {
    "chatgpt_image": "handlers.chatgpt_image",
    "chatgpt_chat": "handlers.chatgpt_chat",
    "claude_chat": "handlers.claude_chat",
}


def getir(hedef: str):
    """Hedefin handler modulunu dondurur."""
    yol = KAYIT.get(hedef)
    if not yol:
        raise HandlerHatasi(
            "hedef icin handler yok: %r (bilinen: %s)"
            % (hedef, ", ".join(sorted(KAYIT))))
    import importlib
    return importlib.import_module(yol)
