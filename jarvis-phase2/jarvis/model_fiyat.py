"""Model liste fiyatları — TARİHLİ ve KAYNAKLI.

Sahip 22.09.2026: *"bunların ortalama token fiyatlarını da yanlarına yaz
bilelim."*

🔴 `usage.py` BİLEREK FİYAT TUTMUYORDU. Oradaki gerekçe hâlâ geçerli:
*"Buraya sabit fiyat yazmak, bir gün sessizce yanlış rakam göstermek
demektir."* Sahip rakamı istedi; o yüzden gerekçeyi çürütmüyoruz, ETKİSİZ
HALE GETİRİYORUZ:

  1. Her fiyatın yanında ALINDIĞI TARİH ve KAYNAK URL'si durur.
  2. Panel fiyatı değil, fiyatın TARİHİNİ de gösterir.
  3. Tablo eskirse (`BAYATLIK_GUN`) panel "bu rakamlar eskimiş olabilir"
     uyarısı basar. Sessizce yanlış göstermez.
  4. Tabloda OLMAYAN bir model için maliyet HESAPLANMAZ; "fiyat tanımsız"
     yazar. Tahmin edilmez.

🔴 BUNLAR ÖLÇÜM DEĞİL, SAĞLAYICININ İLAN ETTİĞİ LİSTE FİYATIDIR.
Gerçek fatura; indirim, önbellek (prompt caching), toplu iş (batch) ve
bölge çarpanlarıyla farklı çıkar. Panel bunu "tahmini" diye etiketler.
Kesin rakam sağlayıcının kendi faturasındadır; defter o faturayı
DOĞRULAMAK için vardır.
"""
from __future__ import annotations

from datetime import date, datetime

# Fiyatların resmî sayfalardan alındığı gün.
GECERLILIK = date(2026, 9, 22)
# Bu kadar günden eskiyse panel uyarır.
BAYATLIK_GUN = 60

# USD başına TL. Kur da eskir; kendi tarihini taşır.
USD_TRY = 48.37
USD_TRY_TARIH = date(2026, 9, 22)
USD_TRY_KAYNAK = "TCMB gösterge kuru"

# (sağlayıcı, model) -> 1 MİLYON token başına USD
# Anahtar modelin TAM adıdır: "gemini-3.5-flash" ile "gemini-3.5-flash-lite"
# apayrı fiyatlardır (1,50 vs 0,30) ve karıştırmak beş kat hata demektir.
FIYAT: dict[tuple[str, str], dict] = {
    ("gemini", "gemini-3.6-flash"): {
        "girdi": 0.75,
        "cikti": 3.75,
        "kaynak": "https://ai.google.dev/gemini-api/docs/pricing",
        "not": ("22.09.2026 tarifesi. 🔴 1 OCAK 2027'DE İKİ KATINA ÇIKIYOR: "
                "girdi 1.50, çıktı 7.50. gemini-2.5-flash yeni kullanıcılara "
                "kapandığı için (404) buna geçildi."),
    },
    ("gemini", "gemini-3.5-flash-lite"): {
        "girdi": 0.30, "cikti": 2.50,
        "kaynak": "https://ai.google.dev/gemini-api/docs/pricing",
        "not": "ücretli katman; ücretsiz katmanda veri eğitimde kullanılır",
    },
    # 🔴 GORSEL MODELI. Cikti fiyati metin modellerinin ~50 katidir
    # (120 $/1M) cunku tek gorsel ~1200 token sayiliyor. Bir gorsel
    # ~7 TL; dort gorselluk parti ~28 TL. Metin tarafinin 7 gunluk
    # toplami 4,46 TL oldugu dusunulurse, asil maliyet BURADA.
    ("gemini", "gemini-3-pro-image"): {
        "girdi": 2.00, "cikti": 120.00,
        "kaynak": "https://ai.google.dev/gemini-api/docs/pricing",
        "not": "gorsel uretimi; 512/1K/2K fiyati ayni (olculdu), 4K ~2 kati",
    },
    ("claude", "claude-haiku-4-5-20251001"): {
        "girdi": 1.00, "cikti": 5.00,
        "kaynak": "https://platform.claude.com/docs/en/about-claude/pricing",
        "not": "önbellek okuması 0,10 $/M — panel bunu ayırt edemez",
    },
    ("openai", "gpt-5-mini"): {
        "girdi": 0.25, "cikti": 2.00,
        "kaynak": "https://developers.openai.com/api/docs/pricing",
        "not": "en az 800 çıktı token ister, yoksa boş döner",
    },
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"): {
        "girdi": 0.0, "cikti": 0.0,
        "kaynak": "openrouter.ai — ':free' son eki",
        "not": "ücretsiz katman; kota ve hız sınırı var",
    },
}

# Defterde model adı bazen genelleşiyor ("openrouter/free"); eşleşmeyi
# kaybetmemek için takma adlar.
TAKMA_AD: dict[tuple[str, str], tuple[str, str]] = {
    ("openrouter", "openrouter/free"):
        ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
}


def _anahtar(saglayici: str, model: str) -> tuple[str, str]:
    a = ((saglayici or "").strip().lower(), (model or "").strip())
    return TAKMA_AD.get(a, a)


def bayat_mi(bugun: date | None = None) -> int:
    """Fiyat tablosu kaç gün önce güncellendi."""
    # Sunucu saati ile kaynak sayfanin tarihi bir gun oynayabiliyor;
    # eksi gun sayisi panelde sacma gorunur. Taban sifir.
    return max(0, ((bugun or datetime.now().date()) - GECERLILIK).days)


def fiyat(saglayici: str, model: str) -> dict | None:
    """Liste fiyatı; tanımsızsa None. TAHMİN ÜRETMEZ."""
    return FIYAT.get(_anahtar(saglayici, model))


def maliyet(saglayici: str, model: str, girdi_token: int | None,
            cikti_token: int | None) -> dict | None:
    """Bir satırın tahmini maliyeti.

    Token sayısı bilinmiyorsa None döner: 0 döndürmek "bedava" demek
    olurdu ve bu yanlış olurdu. Defterde `tokens_known` alanı tam da bu
    ayrımı tutuyor.
    """
    f = fiyat(saglayici, model)
    if f is None or girdi_token is None or cikti_token is None:
        return None
    usd = (girdi_token * f["girdi"] + cikti_token * f["cikti"]) / 1_000_000.0
    return {
        "usd": round(usd, 6),
        "try": round(usd * USD_TRY, 4),
        "girdi_m": f["girdi"],
        "cikti_m": f["cikti"],
        "kaynak": f["kaynak"],
    }


def ozet_bilgisi() -> dict:
    """Panelin fiyat tablosunun kendisi hakkında söyleyeceği şey."""
    gun = bayat_mi()
    return {
        "gecerlilik": GECERLILIK.isoformat(),
        "gun_gecti": gun,
        "bayat": gun > BAYATLIK_GUN,
        "usd_try": USD_TRY,
        "usd_try_tarih": USD_TRY_TARIH.isoformat(),
        "usd_try_kaynak": USD_TRY_KAYNAK,
        "uyari": ("Bunlar sağlayıcının İLAN ETTİĞİ liste fiyatlarıdır, "
                  "ölçüm değildir. Gerçek fatura indirim, önbellek ve "
                  "toplu iş çarpanlarıyla farklı çıkar."),
    }
