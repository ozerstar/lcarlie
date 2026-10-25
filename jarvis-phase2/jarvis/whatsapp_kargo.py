"""WhatsApp müşterisine yalnız telefonuyla doğrulanan kargo durumunu verir."""
from __future__ import annotations

from .basitkargo import Kargo

_DURUMLAR = {
    "NEW": "Gönderi hazırlığında",
    "READY_TO_SHIP": "Kargoya verilmek üzere hazır",
    "SHIPPED": "Kargoya verildi",
    "IN_TRANSIT": "Taşımada",
    "DELIVERED": "Teslim edildi",
    "DELAYED": "Gecikme kaydı var",
    "NEEDS_SUPPORT": "İnceleme gerekiyor",
    "RETURNING": "İade sürecinde",
    "CANCELLED": "İptal edildi",
}


def _telefon(ham: str) -> str:
    rakam = "".join(karakter for karakter in str(ham or "") if karakter.isdigit())
    if len(rakam) == 11 and rakam.startswith("0"):
        return "90" + rakam[1:]
    if len(rakam) == 10 and rakam.startswith("5"):
        return "90" + rakam
    return rakam


def _kimlikler(gonderi: dict) -> set[str]:
    return {str(gonderi.get(alan) or "").strip().casefold()
            for alan in ("id", "orderNumber", "foreignCode", "barcode")}


def durum_sor(telefon: str, siparis_no: str = "", *, api: Kargo | None = None) -> tuple[str, bool]:
    """(yanıt, insana devret). Alıcı telefonu eşleşmezse durum açıklanmaz."""
    telefon = _telefon(telefon)
    if len(telefon) != 12 or not telefon.startswith("90"):
        return "Kargo kaydınızı doğrulayamadım; konuyu yetkili kişiye iletiyorum.", True
    api = api or Kargo(zaman_asimi=12)
    arama = siparis_no.strip() or telefon
    veri = api.cagir("search_shipments", {"keyword": arama, "size": 25}).get("veri") or {}
    gonderiler = [kayit for kayit in veri.get("items") or []
                  if isinstance(kayit, dict) and kayit.get("type") == "OUTGOING"
                  and _telefon((kayit.get("recipient") or {}).get("phone")) == telefon]
    if siparis_no:
        anahtar = siparis_no.strip().casefold()
        gonderiler = [kayit for kayit in gonderiler if anahtar in _kimlikler(kayit)]
    if not gonderiler:
        return "Bu numarayla eşleşen kargo kaydını doğrulayamadım; konuyu yetkili kişiye iletiyorum.", True
    if len(gonderiler) != 1 or veri.get("hasMore"):
        return "Birden fazla gönderi görünüyor. Sipariş numaranızı paylaşır mısınız?", False
    gonderi = gonderiler[0]
    durum = _DURUMLAR.get(str(gonderi.get("status") or "").upper())
    if not durum:
        return "Kargonuzun güncel durumunu doğrulayamadım; konuyu yetkili kişiye iletiyorum.", True
    tasiyici = (gonderi.get("shipmentInfo") or {}).get("handler") or {}
    ad = str(tasiyici.get("name") or "").strip()
    if ad and len(ad) <= 40 and "\n" not in ad:
        durum += f" ({ad})"
    cevap = f"Kargo kaydınızın güncel durumu: {durum}."
    kod = str((gonderi.get("shipmentInfo") or {}).get("handlerShipmentCode") or "").strip()
    if kod and len(kod) <= 50 and kod.isalnum():
        cevap += f" Takip numaranız: {kod}."
    return cevap, False
