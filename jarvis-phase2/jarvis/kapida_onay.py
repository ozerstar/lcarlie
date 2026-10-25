"""Kapıda ödemeli sipariş teyidi için güvenli aday ve metin doğrulaması."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


class TeyitHatasi(ValueError):
    pass


KAPIDA_ODEME_YONTEMLERI = frozenset({"Çevrim Dışı Ödemeler", "Офлайн-оплата"})


def kapida_odeme_mi(siparis: dict) -> bool:
    return str(siparis.get("odeme_yontemi") or "").strip() in KAPIDA_ODEME_YONTEMLERI


def telefon_duzelt(deger: object) -> str:
    rakamlar = "".join(karakter for karakter in str(deger or "") if karakter.isdigit())
    if len(rakamlar) == 10 and rakamlar.startswith("5"):
        rakamlar = "90" + rakamlar
    elif len(rakamlar) == 11 and rakamlar.startswith("05"):
        rakamlar = "90" + rakamlar[1:]
    if len(rakamlar) != 12 or not rakamlar.startswith("905"):
        raise TeyitHatasi("geçerli bir Türkiye cep telefonu yok")
    return rakamlar


def _metin(deger: object, alan: str, sinir: int) -> str:
    metin = " ".join(str(deger or "").split())
    if not metin or len(metin) > sinir:
        raise TeyitHatasi(f"{alan} eksik veya çok uzun")
    return metin


def taslak(siparis: dict, *, whatsapp_izni: bool) -> dict:
    """Yalnız kayıtlı kapıda ödeme yöntemi ve izinli siparişi hazırlar."""
    if not kapida_odeme_mi(siparis):
        raise TeyitHatasi("kapıda ödeme yöntemi eşleşmedi")
    if whatsapp_izni is not True:
        raise TeyitHatasi("WhatsApp iletişim izni doğrulanmadı")
    if siparis.get("odeme_durumu") != "NOT_PAID":
        raise TeyitHatasi("sipariş ödenmemiş durumda değil")
    if siparis.get("teslimat_durumu") in {"CANCELED", "CANCELLED", "FULFILLED"}:
        raise TeyitHatasi("sipariş iptal edilmiş veya tamamlanmış")
    if siparis.get("arsivlendi") or siparis.get("ic_siparis"):
        raise TeyitHatasi("arşiv veya iç sipariş")
    ham = siparis.get("ham") or {}
    alici = ((ham.get("shippingInfo") or {}).get("shipmentDetails") or {}).get("address") or {}
    musteri = ham.get("buyerInfo") or {}
    telefon = telefon_duzelt(alici.get("phone"))
    if telefon != telefon_duzelt(musteri.get("phone")):
        raise TeyitHatasi("alıcı ve sipariş telefonu farklı")
    numara = _metin(siparis.get("siparis_no"), "sipariş numarası", 30)
    if not numara.isdecimal():
        raise TeyitHatasi("sipariş numarası geçersiz")
    alici_ad = _metin(alici.get("fullName"), "alıcı adı", 100)
    adres = ", ".join(_metin(alici.get(alan), alan, limit)
                      for alan, limit in (("addressLine1", 180), ("city", 80)))
    kalemler = ham.get("lineItems") or []
    if not isinstance(kalemler, list) or not 1 <= len(kalemler) <= 8:
        raise TeyitHatasi("sipariş kalemleri doğrulanamadı")
    urunler = []
    for kalem in kalemler:
        if not isinstance(kalem, dict):
            raise TeyitHatasi("sipariş kalemi geçersiz")
        ad = _metin(kalem.get("name"), "ürün adı", 100)
        try:
            adet = int(kalem.get("quantity"))
        except (TypeError, ValueError) as hata:
            raise TeyitHatasi("ürün adedi geçersiz") from hata
        if not 1 <= adet <= 100:
            raise TeyitHatasi("ürün adedi geçersiz")
        urunler.append(f"{ad} ×{adet}")
    if siparis.get("para_birimi") != "TRY":
        raise TeyitHatasi("para birimi doğrulanamadı")
    try:
        tutar = Decimal(str(siparis.get("toplam")))
    except (InvalidOperation, TypeError) as hata:
        raise TeyitHatasi("kapıda ödenecek tutar doğrulanamadı") from hata
    if not tutar.is_finite() or tutar <= 0:
        raise TeyitHatasi("kapıda ödenecek tutar doğrulanamadı")
    return {"siparis_no": numara, "telefon": telefon, "adres": adres,
            "alici_ad": alici_ad,
            "urunler": ", ".join(urunler), "tutar": f"{tutar:.2f}"}


def ayrinti_metni(hazir: dict) -> str:
    """Kapıda ödeme tercihi ve açık teyit isteyen sipariş özeti."""
    return (f"Merhaba, L’CARLIÉ’den sipariş verdiğiniz için teşekkür ederiz. "
            f"Kapıda ödemeli {hazir['siparis_no']} numaralı siparişiniz oluşturuldu.\n"
            f"Ürünler: {hazir['urunler']}\n"
            f"Kapıda ödenecek toplam: {hazir['tutar']} TL\n"
            f"Alıcı: {hazir['alici_ad']}\n"
            f"Teslimat adresi: {hazir['adres']}\n"
            f"Telefon: +{hazir['telefon']}\n\n"
            "Kapıda nakit mi, kredi kartıyla mı ödemek istersiniz? Bilgiler doğruysa "
            "ONAYLIYORUM NAKİT veya ONAYLIYORUM KART yazın. "
            "Yanlışlık, düzeltme, iptal veya sorunuz "
            "varsa bu mesaja yazın; ekibimiz yardımcı olacak.")


def sablon_parametreleri(hazir: dict) -> tuple[str, ...]:
    return (hazir["siparis_no"], hazir["urunler"], hazir["tutar"],
            hazir["alici_ad"], hazir["adres"], "+" + hazir["telefon"])


def yaniti_tani(metin: str, siparis_no: str, *, tek_bekleyen: bool = False) -> str:
    ceviri = str.maketrans({"İ": "I", "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C"})
    temiz = " ".join((metin or "").strip().upper().translate(ceviri).split())
    for tercih in ("NAKIT", "KART", "KREDI KARTI"):
        if temiz == f"ONAYLIYORUM {tercih} {siparis_no}" or (
                temiz == f"ONAYLIYORUM {tercih}" and tek_bekleyen):
            return "ONAY_NAKIT" if tercih == "NAKIT" else "ONAY_KART"
    if temiz in {"ONAYLIYORUM", f"ONAYLIYORUM {siparis_no}"}:
        return "ODEME_YONTEMI_SOR"
    if tek_bekleyen and temiz in {"NAKIT ONAYLIYORUM", "KARTLA ONAYLIYORUM"}:
        return "ONAY_NAKIT" if temiz.startswith("NAKIT") else "ONAY_KART"
    if temiz == "BANA AIT DEGIL":
        return "ITIRAZ"
    return "SORU_VEYA_DUZELTME"
