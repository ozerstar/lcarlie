# -*- coding: utf-8 -*-
"""KONUŞMADAN ÜRÜN ATAMA — müşteri hangi ürünü söylediyse onu hatırlar.

NEDEN BÖYLE, BAŞKA YOLU YOK (15.10.2026'da ölçüldü)
Ürün ataması üç yoldan gelebilirdi; ikisi kapalı çıktı:

  1. REKLAM REFERANSI — kapalı. Reklamların CTA dağılımı: SHOP_NOW 30,
     VIEW_INSTAGRAM_PROFILE 25, SEE_DETAILS 9, ORDER_NOW 5,
     MESSAGE_PAGE 5, LEARN_MORE 1. **WhatsApp CTA'sı YOK** ve reklamların
     tamamı duraklatılmış. Yani `referral.source_id` hiç gelmiyor.
     (Webhook o alanı yine de okuyor; reklam açılırsa veri kaybolmasın.)
  2. MESAJ METNİNDEN ÇIKARIM — neredeyse kapalı. 1.034 konuşmanın
     **yalnız 11'inde (%1,1)** katalogdaki bir ürün adı geçiyor.
  3. MÜŞTERİNİN KENDİ CEVABI — AÇIK. Jarvis "hangi ürün?" diye soruyor,
     müşteri söylüyor. Bu modül o cevabı yakalar ve konuşmaya yazar.

🔴 TAHMİN ETMEZ, EŞLEŞTİRİR. Katalogdaki ayırt edici ada birebir bakar.
Benzer/yakın isim aramaz: yanlış ürünün fiyatını söylemek, fiyat
söylememekten çok daha pahalıdır.

🔴 İLK ATAMA KALIR. Bir konuşmaya ürün bir kez yazılır; sonraki mesajlar
onu EZMEZ. Müşteri ikinci bir üründen söz ederse konuşma zaten karışmıştır
ve orası insanın işidir.
"""
from __future__ import annotations

from .satis_dialog import _sade

EN_KISA_ANAHTAR = 4


def anahtarlar(urun_adlari) -> dict[str, str]:
    """Ayırt edici ad → tam ürün adı.

    Katalog adları "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi" ya da
    "BABYSOFT (Bebek Vücut Losyonu)" biçiminde. Ayırt edici kısım ilk
    parçadır; tarif kısmı ("yüz kremi") birden çok üründe geçer ve
    anahtar olarak kullanılırsa yanlış ürüne bağlar.
    """
    cikti: dict[str, str] = {}
    for ad in urun_adlari:
        ad = (ad or "").strip()
        if not ad:
            continue
        ilk = _sade(ad.split("|")[0].split("(")[0]).strip()
        if len(ilk) >= EN_KISA_ANAHTAR:
            cikti[ilk] = ad
    return cikti


def metinde_urun(metin: str, anahtar_sozlugu: dict[str, str]) -> str | None:
    """Metinde geçen TEK ürün. Birden çok geçiyorsa None.

    🔴 BİRDEN ÇOK EŞLEŞME = BELİRSİZLİK. "HYDRAVIE mi DERMANOVA mı daha
    iyi?" sorusunda birini seçmek, seçilmeyenin fiyatını yanlış söylemeye
    açık kapı bırakır. Belirsizi insana bırakmak doğrudur.
    """
    sade = _sade(metin or "")
    if not sade:
        return None
    bulunan = {ad for anahtar, ad in anahtar_sozlugu.items() if anahtar in sade}
    if len(bulunan) == 1:
        return bulunan.pop()
    return None


def konusmada_urun(mesajlar, anahtar_sozlugu: dict[str, str]) -> str | None:
    """Konuşmanın MÜŞTERİ mesajlarında geçen ürün.

    Yalnız gelen mesajlara bakar: kendi cevabımızda ürün adı geçmesi
    müşterinin o ürünü sorduğu anlamına gelmez -- Jarvis "hangi ürün?"
    diye sorarken örnek vermiş olabilir.
    """
    for mesaj in mesajlar:
        if (mesaj.get("yon") or "") != "gelen":
            continue
        bulundu = metinde_urun(mesaj.get("metin") or "", anahtar_sozlugu)
        if bulundu:
            return bulundu
    return None
