#!/usr/bin/env python3
"""Kargoya verilecek pazaryeri paketlerini panele taşır (5 dakikada bir).

Sahip 13.11.2026: Trendyol'da 3, İdefix'te 1 paket hazırdı ama Jarvis'in KARGO
sekmesinde görünmüyordu. Sabah WhatsApp listesi (`kargo-sabah.py`) bu paketleri
zaten her kanalın kendi API'sinden okuyor; bu betik aynı okumayı gün boyu
yapar ve `state/kargo-bekleyen.json` dosyasına yazar. Panel o dosyayı okur.

Neden panel doğrudan sormuyor: pazaryeri anahtarları yalnız root'a açık,
panel ise yetkisiz `jarvis-web` kullanıcısıyla çalışıyor. Anahtarları panele
açmak yerine sonucu dosyaya yazıyoruz.

Çıkış: 0=hepsi okundu · 1=en az bir kanal okunamadı (dosya yine yazılır,
okunamayan kanal içinde adıyla durur).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis import kargo_bekleyen  # noqa: E402


def _sabah():
    # Dosya adında tire var; import edilemez, yoldan yüklenir.
    tanim = importlib.util.spec_from_file_location(
        "kargo_sabah", Path(__file__).with_name("kargo-sabah.py"))
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def main() -> int:
    satirlar, okunamayan = _sabah().topla()
    yol = kargo_bekleyen.yaz(satirlar, okunamayan)
    print("%d paket · okunamayan: %s · %s" % (
        len(satirlar), ", ".join(okunamayan) or "yok", yol))
    return 1 if okunamayan else 0


if __name__ == "__main__":
    sys.exit(main())
