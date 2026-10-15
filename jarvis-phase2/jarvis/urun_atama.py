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

import re

from .satis_dialog import _sade

EN_KISA_ANAHTAR = 4


def anahtarlar(urun_adlari) -> dict[str, str]:
    """Ayırt edici ad → tam ürün adı.

    Katalog adları "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi" ya da
    "BABYSOFT (Bebek Vücut Losyonu)" biçiminde. Ayırt edici kısım ilk
    parçadır; tarif kısmı ("yüz kremi") birden çok üründe geçer ve
    anahtar olarak kullanılırsa yanlış ürüne bağlar.
    """
    # 🔴 AYRAÇ "|" ve "(" YETMİYORDU. "VIREON FOR MEN · Erkek Bakım Kremi"
    # anahtarı tüm cümle oluyordu; "KINESIS + (...)" ise "kinesis +" --
    # sondaki " +" yüzünden "kimesis" yazım hatası 3 harf uzakta kalıyor ve
    # yakalanmıyordu. Ayıraç listesine "·" eklendi, anahtar harf dizisine
    # indirildi.
    adaylar: list[tuple[list[str], str]] = []
    for ad in urun_adlari:
        ad = (ad or "").strip()
        if not ad:
            continue
        bas = re.split(r"[|(·]", ad)[0]
        kelimeler = [k for k in re.findall(r"[a-z]+", _sade(bas))
                     if len(k) >= EN_KISA_ANAHTAR]
        if kelimeler:
            adaylar.append((kelimeler, ad))

    # 🔴 ÖN EK OLAN ANAHTAR AYIRT EDİCİ DEĞİLDİR — ÖLÇÜLDÜ 15.10.2026.
    # "BABY RESCUE" ilk kelimesi "baby"; bu BABYDENT/BABYSHOWER/BABYSOFT/
    # BABYSOL'un hepsinin ön eki. Sonuç: "babysoft fiyatı" mesajı HEM
    # "baby" HEM "babysoft" ile eşleşiyor, iki aday çıkıyor ve belirsizlik
    # kuralı gereği HİÇBİRİ atanmıyordu -- yani çakışma, çakışmayan ürünü
    # de sessizce kaybettiriyordu.
    # Çözüm: başka bir anahtarın ön eki olan aday, ayırt edici olana kadar
    # bir sonraki kelimeyle UZATILIR.
    ilkler = [k[0] for k, _ in adaylar]
    cikti: dict[str, str] = {}
    for kelimeler, ad in adaylar:
        anahtar = kelimeler[0]
        onek_sayisi = sum(1 for d in ilkler if d != anahtar and d.startswith(anahtar))
        n = 1
        while onek_sayisi and n < len(kelimeler):
            n += 1
            anahtar = " ".join(kelimeler[:n])
            onek_sayisi = 0
        cikti.setdefault(anahtar, ad)
    return cikti


# 🔴 YAZIM HATASI TOLERANSI — ÖLÇÜLDÜ 15.10.2026.
# Sahip "kinesis" yerine "kimesis" yazdı ve ürün atanmadı. Müşteriler de
# düzgün yazmaz. Ama bulanık eşleşme yanlış ürünü seçerse Jarvis BAŞKA
# bir ürünün fiyatını güvenle söyler -- en pahalı hata sınıfı.
#
# Katalogdaki 36 anahtarın birbirine uzaklığı ölçüldü:
#   eşik 1 -> ÇARPIŞMA YOK
#   eşik 2 -> babysoft/babysol ve calmaros/calmoris karışıyor
# Bu yüzden eşik 1'de sabit. Ayrıca yalnız 6+ harfli kelimelerde açılır:
# kısa anahtarlarda bir harf fark çok şeye benzer.
#
# Ölçülen sonuç (eşik 1): kimesis, kinezis, hidravie, dermanove, dermavask
# hepsi doğru ürüne gidiyor; babysoft ile babysol karışmıyor.
EN_KISA_BULANIK = 6
AZAMI_UZAKLIK = 1


def _uzaklik(a: str, b: str) -> int:
    """Levenshtein. Kısa dizeler için yeterince hızlı."""
    if len(a) < len(b):
        a, b = b, a
    onceki = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        simdi = [i + 1]
        for j, cb in enumerate(b):
            simdi.append(min(onceki[j + 1] + 1, simdi[j] + 1,
                             onceki[j] + (ca != cb)))
        onceki = simdi
    return onceki[-1]


def _bulanik_eslesme(sade: str, anahtar_sozlugu: dict[str, str]) -> set[str]:
    """Yazım hatasıyla yazılmış ürün adlarını bulur.

    🔴 İKİNCİ EN YAKIN DAHA UZAK OLMALI. İki anahtar aynı uzaklıktaysa
    hangisinin kastedildiği BİLİNMİYOR demektir; hiçbiri seçilmez.
    """
    bulunan: set[str] = set()
    adaylar = [k for k in anahtar_sozlugu if len(k) >= EN_KISA_BULANIK]
    for kelime in re.findall(r"[a-z]+", sade):
        if len(kelime) < EN_KISA_BULANIK:
            continue
        olculen = sorted((_uzaklik(kelime, k), k) for k in adaylar)
        if not olculen:
            continue
        en_yakin, kok = olculen[0]
        ikinci = olculen[1][0] if len(olculen) > 1 else 99
        if 0 < en_yakin <= AZAMI_UZAKLIK and ikinci > en_yakin:
            bulunan.add(anahtar_sozlugu[kok])
    return bulunan


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
    if not bulunan:
        # Tam eşleşme yoksa yazım hatası olabilir; aynı belirsizlik kuralı
        # burada da geçerli -- tek aday varsa kabul edilir.
        bulunan = _bulanik_eslesme(sade, anahtar_sozlugu)
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
