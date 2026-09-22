#!/usr/bin/env python3
"""RAKİP FİYAT TARAMASI — grounded arama ile, İDDİA olarak.

NEDEN VAR / ÖNCEKİ HÜKMÜN DÜZELTİLMESİ
20.09.2026'da "rakip fiyatı alınamıyor" diye ölçülmüştü ve o ölçüm DOĞRUYDU:
Trendyol/Hepsiburada/N11/akakçe/cimri hepsi bu sunucuya 403 döner, satıcı
API'sinin dokuz ucu yalnız kendi verimizi verir. Eksik olan parça şuydu:
Google Search grounding sayfayı BİZİM ÇEKMEMİZİ gerektirmez — içerik
Google'ın dizininden gelir. Ölçüldü: aynı gün grounded sorgu, marka adı ve
TL fiyatıyla altı rakip ürün döndürdü.

🔴 BU BİR ÖLÇÜM DEĞİL, İDDİADIR. Fiyatı biz görmedik; bir model, aramanın
   getirdiği kaynaklardan okuduğunu söyledi. Üç sonucu var ve üçü de kodda:
     1. seviye asla FACT olmaz -> INTERPRETATION olarak kaydedilir
     2. kaynak URL'leri kayıtla birlikte taşınır, kayıtsız satır yazılmaz
     3. core.pazar_bulgu'ya YAZMAZ. Orası insan beyanı içindir; makine
        çıkarımını oraya yazmak, sistemin kendi iddiasını kendi kanıtına
        çevirmesi olurdu. Araştırma akışına yazar; panoda ve müdürün
        kanıtında zaten "DIŞ KAYNAK (şirket ölçümü değil, iddia)" etiketiyle
        görünür.

🔴 FİYATI BULUNAMAYAN ÜRÜN UYDURULMAZ. Model "kaynakta fiyat yazmıyor"
   diyorsa o satır fiyatsız geçer; boş bırakmak, yanlış rakam yazmaktan
   iyidir.

Çıkış: 0=çalıştı · 1=hata · 2=hiç sonuç yok
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis import providers  # noqa: E402

AKIS = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "departman_arastirma.jsonl"
MODEL = os.environ.get("RAKIP_FIYAT_MODEL", "gemini-3.5-flash-lite")

# Taranacak kategoriler. Kendi ürün adımız DEĞİL, KATEGORİ yazılır: rakip
# ürünler bizim marka adımızla aranmaz.
KATEGORILER = (
    "erkek genital bolge bakim kremi",
    "kadin intim bolge bakim ve beyazlatici krem",
)

SORU = (
    "{kategori} kategorisinde Trendyol, Hepsiburada ve diger Turk "
    "pazaryerlerinde satilan urunlerin GUNCEL fiyatlari nedir? "
    "Her satirda MARKA + URUN + ml + TL fiyat olsun. "
    "SADECE kaynakta acikca yazan fiyatlari ver; fiyati yazmayan urun icin "
    "'fiyat kaynakta yok' yaz, TAHMIN ETME."
)


def _grounded(soru: str) -> tuple[str, list[str]]:
    env = providers.load_env()
    key = env.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY yok")
    govde = {"contents": [{"parts": [{"text": soru}]}],
             "tools": [{"google_search": {}}]}
    istek = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
        f":generateContent?key={key}",
        data=json.dumps(govde).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=90) as cevap:
        d = json.loads(cevap.read().decode("utf-8"))
    aday = (d.get("candidates") or [{}])[0]
    metin = ""
    for p in ((aday.get("content") or {}).get("parts") or []):
        metin += p.get("text") or ""
    gm = aday.get("groundingMetadata") or {}
    urller = []
    for ch in (gm.get("groundingChunks") or []):
        u = ((ch.get("web") or {}).get("uri")) or ""
        if u:
            urller.append(u)
    return metin, urller


# "146,50 TL" / "531 TL" / "945,00 TL"
FIYAT = re.compile(r"(\d[\d.]*(?:,\d{1,2})?)\s*TL", re.IGNORECASE)


def satirlari_ayikla(metin: str) -> list[dict]:
    """Yalniz ICINDE TL FIYATI GECEN satirlari alir.

    🔴 Fiyatsiz satir ATILIR, tahmin edilmez. Modelin 'fiyat kaynakta yok'
       dedigi urun kayda girmez -- girseydi fiyatsiz bir satir ileride
       'fiyat 0' diye okunabilirdi.
    """
    cikti = []
    for ham in metin.splitlines():
        s = ham.strip().lstrip("*-• ").strip()
        if len(s) < 12:
            continue
        bulunan = FIYAT.findall(s)
        if not bulunan:
            continue
        cikti.append({"satir": s[:300], "fiyatlar": bulunan[:3]})
    return cikti


def main() -> int:
    simdi = datetime.now(timezone.utc).isoformat(timespec="seconds")
    kayitlar: list[dict] = []
    for kategori in KATEGORILER:
        try:
            metin, urller = _grounded(SORU.format(kategori=kategori))
        except Exception as hata:  # noqa: BLE001
            print(f"  HATA {kategori}: {str(hata)[:140]}", file=sys.stderr)
            continue
        satirlar = satirlari_ayikla(metin)
        print(f"  {kategori}: {len(satirlar)} fiyatli satir · {len(urller)} kaynak")
        if not urller:
            # 🔴 Kaynaksiz fiyat iddiasi KAYDEDILMEZ.
            print("    kaynak yok -> kaydedilmedi", file=sys.stderr)
            continue
        for s in satirlar:
            kayitlar.append({
                "zaman": simdi,
                "departman": "COMPETITOR_INT",
                "konu": f"rakip fiyat taramasi: {kategori}",
                "baslik": s["satir"],
                "url": urller[0],
                "yayinci": "google search grounding",
                "kaynak_tipi": "GROUNDED_IDDIA",
                "gorulme": simdi,
                "alaka": 1.0,
                "enjeksiyon": False,
                "ozet": ("MODEL IDDIASI, olcum degil. Fiyat kaynaktan okundugu "
                         "SOYLENIYOR; dogrulanmasi icin kaynak acilmali. "
                         "Kaynaklar: " + " ".join(urller[:4]))[:400],
            })

    if not kayitlar:
        print("hicbir fiyat satiri kaydedilmedi", file=sys.stderr)
        return 2

    AKIS.parent.mkdir(parents=True, exist_ok=True)
    with AKIS.open("a", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")
    print(f"rakip fiyat taramasi · {len(kayitlar)} fiyat satiri kaydedildi "
          f"(seviye: IDDIA, olcum DEGIL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
