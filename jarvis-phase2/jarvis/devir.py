# -*- coding: utf-8 -*-
"""DEVİR KAPISI — hangi müşteri mesajı Jarvis'te kalır, hangisi sahibe gider.

Sahip 15.10.2026: *"burdan jarvis mesajlara cevap versin, gerektiğinde bana
devretsin ben konuşayım."*

🔴 KURAL SAHİBİN, KOD DEĞİL. Dört devir sebebini sahip tek tek seçti:
şikâyet/yan etki/sağlık, sipariş/ödeme/iade, ürün belirsizse, mevzuat
takılırsa. Buradaki eşleştirme o dört maddenin koddaki karşılığıdır;
genişletmek yeni bir sahip kararı ister.

🔴 SINIF DEĞERLERİ UYDURULMADI. `lcarlie.mesaj.sinif` sütunundaki gerçek
dağılımdan alındı (15.10.2026): FIYAT 184 · ICERIK 167 · ANLASILMADI 123 ·
SIPARIS 31 · TESEKKUR 11 · SELAMLAMA 9 · KULLANIM 6 · SAGLIK 6 ·
DURDURMA 1 · BELIRTI_ANLATIMI 1 · KATEGORI 1 · (boş) 783.

🔴 BİLİNMEYEN SINIF DEVREDİLİR, CEVAPLANMAZ. 783 mesajın sınıfı boş. Boş
sınıfı "herhalde fiyat sorusudur" diye yorumlamak, yanlış ürünün fiyatını
söylemenin yoludur. Bilmiyorsak insana gider -- sessizce tahmin etmeyiz.
"""
from __future__ import annotations

# Sahibin seçtiği dört devir sebebi
SAGLIK_SIKAYET = "SAGLIK_SIKAYET"
ISLEM = "ISLEM"
URUN_BELIRSIZ = "URUN_BELIRSIZ"
MEVZUAT = "MEVZUAT"
IDDIA = "IDDIA"
SINIF_YOK = "SINIF_YOK"

# 1. madde -- şikâyet, yan etki, sağlık
SAGLIK_SINIFLARI = frozenset({"SAGLIK", "BELIRTI_ANLATIMI", "SIKAYET", "DURDURMA"})
# 2. madde -- işlem gerektiren konular
ISLEM_SINIFLARI = frozenset({"SIPARIS", "IADE", "ODEME", "KARGO_SORUN"})
# Ürünün ETKİSİNİ soran mesajlar. Cevabı bir iddia üretir ve kozmetikte bu
# mevzuat alanıdır -- Jarvis'e bırakılmaz. Eski 540 etiketlemede bu sınıf
# yoktu; sorular SAGLIK ve TESEKKUR arasına dağılmıştı.
IDDIA_SINIFLARI = frozenset({"IDDIA_SORUSU"})
# Jarvis'in cevaplayabileceği sınıflar. Beyaz liste: listede olmayan DEVREDİLİR.
JARVIS_SINIFLARI = frozenset({
    "FIYAT", "ICERIK", "KULLANIM", "KARGO", "SELAMLAMA", "TESEKKUR", "KATEGORI",
})
# Ürün adı bilinmeden cevaplanamayacak sınıflar. "Fiyatı nedir?" mesajından
# ürün ÇIKARILAMAZ -- 540 müşteri mesajının hiçbirinde ürün adı geçmiyor ama
# 183'ü fiyat soruyor (satis_dialog.py'deki ölçüm).
URUN_GEREKTIREN = frozenset({"FIYAT", "ICERIK", "KULLANIM"})

SEBEP_METNI = {
    SAGLIK_SIKAYET: "Sağlık, yan etki veya şikâyet konusu",
    ISLEM: "Sipariş, ödeme veya iade işlemi",
    URUN_BELIRSIZ: "Hangi üründen bahsedildiği belli değil",
    MEVZUAT: "Üretilen cevap mevzuat kapısından geçmedi",
    IDDIA: "Ürünün etkisi soruluyor; cevabı mevzuat iddiası üretir",
    SINIF_YOK: "Mesajın sınıfı belirlenemedi",
}


def devir_gerekir(sinif: str | None, *, urun_bilindi: bool,
                  mevzuat: str | None = None) -> tuple[bool, str | None]:
    """(devredilsin mi, sebep kodu).

    Sıra önemli: mevzuat ve sağlık her şeyin önündedir. Bir mesaj hem
    sağlık hem fiyat sorusu olabilir; o zaman sağlık kazanır.
    """
    if (mevzuat or "").upper() in {"BLOCKED", "BLOKE", "RED"}:
        return True, MEVZUAT

    temiz = (sinif or "").strip().upper()
    if not temiz:
        return True, SINIF_YOK
    if temiz in SAGLIK_SINIFLARI:
        return True, SAGLIK_SIKAYET
    if temiz in IDDIA_SINIFLARI:
        return True, IDDIA
    if temiz in ISLEM_SINIFLARI:
        return True, ISLEM
    if temiz not in JARVIS_SINIFLARI:
        # ANLASILMADI dahil: tanımadığımız her sınıf insana gider.
        return True, SINIF_YOK
    if temiz in URUN_GEREKTIREN and not urun_bilindi:
        return True, URUN_BELIRSIZ
    return False, None


def sebep_aciklamasi(sebep: str | None) -> str:
    """Panelde gösterilecek insan okunur sebep."""
    if not sebep:
        return ""
    return SEBEP_METNI.get(sebep, sebep)
