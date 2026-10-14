# -*- coding: utf-8 -*-
"""MÜŞTERİ MESAJI SINIFLANDIRMA — devir kapısının girdisi.

NEDEN VAR
`lcarlie.mesaj.sinif` 540 satırda dolu, 783 satırda boş. Dolu olanların
hepsi 20.08–20.09.2026 arası: tek seferlik elle doldurma. Betik yoktu,
zamanlayıcı yoktu, yeni mesaj hiç sınıflanmıyordu. Sınıf olmadan devir
kapısı her şeyi sahibe veriyor ve Jarvis tek mesaj bile cevaplayamıyor.

🔴 MEVCUT 540 ETİKET ÖLÇÜT DEĞİLDİR. 15.10.2026'da örneklendi ve gürültülü
çıktı: "Neye faydası var" SAGLIK, "Etkisi ne kadar sürede ortaya çıkar"
TESEKKUR, "Krem formunda mı" ANLASILMADI etiketlenmiş. Bu modül onlara
uymaya çalışmaz; uymak gürültüye uymak olurdu.

🔴 İDDİA SORUSU AYRI BİR SINIFTIR — eski etiketlemede yoktu.
"Ne işe yarar", "faydası ne", "etkisi var mı" soruları ürünün ETKİSİNİ
sorar. Kozmetikte bu mevzuat alanıdır ve cevabı bir iddia üretir. Jarvis'e
bırakılamaz; sahibe gider. Eski etiketleme bunları SAGLIK ve TESEKKUR'a
dağıtmıştı, yani bir kısmı gözden kaçıyordu.

🔴 TEREDDÜTTE DEVRET. Sınıflandırıcının işi Jarvis'in güvenle
cevaplayabileceği DAR kümeyi seçmektir. Geri kalan her şey ANLASILMADI
olur ve devir kapısı onu sahibe verir. Yanlış sınıf, cevapsız mesajdan
pahalıdır.

Türkçe eşleştirme `satis_dialog._sade` / `_gecer` üzerinden yapılır: İ/I
casefold tuzağı ve ünsüz yumuşaması orada zaten çözülmüş, ikinci bir kopya
çıkarmak o tuzakları geri getirirdi.
"""
from __future__ import annotations

from .satis_dialog import _gecer, _sade

# 🔴 KELIME ORTASINDA ESLESME TUZAGI -- OLCULDU 15.10.2026.
# "ne ise yarar" mesaji SAGLIK cikiyordu, cunku "yarar" icinde "yara" koku
# geciyor. Guvenli yone gidiyordu ama sebep yanlisti ve ayni tuzak
# "yararli", "yaralanma", "kazanc" gibi kelimelerde de patlar. Bu projede
# ayni sinif hata daha once "hi " kalibinin kelime ortasinda eslesmesiyle
# yasandi.
#
# Cozum iki kademeli:
#   - Cok kelimeli kaliplar ("ne ise yarar") duz arama ile aranir; zaten
#     kendi baslarina ayirt edici.
#   - Tek kelimelik kokler KELIME BASINDAN aranir. Boylece "fiyat" ->
#     "fiyati" yakalanir ama "yara" -> "yarar" YAKALANMAZ... yakalanir,
#     cunku "yarar" da "yara" ile baslar. Bu yuzden boyle koklerin
#     TAM_KELIME kumesine konmasi gerekir.
# "yara" burada DEGIL: "yaram", "yarasi", "yaraya" yakalanmali. Fayda
# anlamindaki "yarar/yararli" ile cakismasi IDDIA listesinin SAGLIK'tan
# once denetlenmesiyle cozulur -- olculdu, iki yon de dogru ayrilir.
TAM_KELIME = frozenset({
    "zarar", "hasta", "agri", "ilac", "tamam", "peki", "kaca",
})


def _kelime_gecer(sade: str, kok: str) -> bool:
    """Kok mesajda KELIME olarak geciyor mu.

    Cok kelimeli kalip: duz arama (`_gecer`, unsuz yumusamasi dahil).
    TAM_KELIME kokleri: birebir kelime esitligi.
    Digerleri: bir kelimenin BASI olmali (Turkce eklemeli dil).
    """
    if " " in kok:
        return _gecer(sade, kok)
    kelimeler = sade.replace("?", " ").replace("!", " ").replace(".", " ") \
                    .replace(",", " ").split()
    if kok in TAM_KELIME:
        return kok in kelimeler
    yumusak = {"k": "g", "t": "d", "p": "b"}
    alternatif = kok
    if kok[-1:] in yumusak:
        alternatif = kok[:-1] + yumusak[kok[-1]]
    return any(k.startswith(kok) or k.startswith(alternatif) for k in kelimeler)

# Jarvis cevaplayabilir
FIYAT = "FIYAT"
ICERIK = "ICERIK"
KULLANIM = "KULLANIM"
KARGO = "KARGO"
SELAMLAMA = "SELAMLAMA"
TESEKKUR = "TESEKKUR"
# Sahibe gider
SAGLIK = "SAGLIK"
IDDIA_SORUSU = "IDDIA_SORUSU"
SIPARIS = "SIPARIS"
ANLASILMADI = "ANLASILMADI"

# Sıra ÖNEMLİ: önce sahibe gidenler. Bir mesaj hem "fiyatı ne" hem
# "yarasına iyi gelir mi" olabilir; o zaman sağlık kazanmalı.
_SIRA: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 1. İDDİA SORUSU -- urunun ETKISINI soruyor. Cevabi mevzuat uretir.
    (IDDIA_SORUSU, (
        "ne ise yarar", "yarar", "nasil etki", "etkisi", "etkili mi", "etki eder",
        "faydasi", "faydali mi", "fayda eder", "iyi gelir mi", "iyi gelirmi",
        "gecirir mi", "gecer mi", "tedavi", "cozer mi", "yok eder",
        "sonuc verir", "sonuc alir", "ise yarar mi", "ise yararmi",
        "kac gunde", "ne kadar surede", "nekadar surede", "kalici mi",
    )),
    # 2. SAĞLIK / ŞİKÂYET -- en geniş ağ. Yanlış yakalamak ucuz, kaçırmak pahalı.
    (SAGLIK, (
        "alerji", "alerjik", "kasinti", "kasindi", "yanma", "yandi", "tahris",
        "kizarik", "kizardi", "dokuntu", "sislik", "sisti", "yan etki",
        "doktor", "hastane", "ameliyat", "ilac", "recete", "hamile", "emzir",
        "bebek", "hasta", "agri", "aciyor", "yara", "yarasi", "egzama",
        "sedef", "mantar", "diyabet", "seker hastas", "tansiyon", "kanser",
        "kanama", "felc", "kaza gecir", "zarar", "kotu oldu", "iyi gelmedi",
        "yaramadi", "tepki verdi", "sikayet",
    )),
    # 3. SİPARİŞ / İŞLEM -- sahibe gider (sahip kararı).
    (SIPARIS, (
        "siparis", "sipariw", "satin al", "nasil alabilir", "nereden alabilir",
        "iade", "degisim", "iptal", "odeme", "havale", "kapida",
        "fatura", "takip no", "kargom", "gelmedi", "ulasmadi",
    )),
    # 4. KARGO -- bilgi sorusu, Jarvis cevaplayabilir.
    (KARGO, ("kargo", "teslimat", "gonderim", "ne zaman gelir", "kac gunde gelir")),
    # 5. FİYAT
    (FIYAT, ("fiyat", "ucret", "kac para", "kac tl", "kaca", "ne kadar tutuyor",
             "indirim", "kampanya", "tl mi")),
    # 6. İÇİNDEKİLER
    (ICERIK, ("icindekiler", "icerik", "ingredient", "inci", "formul",
              "paraben", "koku", "parfum", "dogal mi", "organik mi",
              "krem formunda", "jel mi", "sprey mi", "ml mi", "gram")),
    # 7. KULLANIM
    (KULLANIM, ("nasil kullan", "nereye sur", "ne kadar sur", "gunde kac",
                "sabah mi", "aksam mi", "kullanim", "uygulan")),
    # 8. TEŞEKKÜR
    (TESEKKUR, ("tesekkur", "sagolun", "sag olun", "eyvallah", "tamamdir",
                "tamam", "anladim", "peki")),
    # 9. SELAMLAMA
    (SELAMLAMA, ("merhaba", "selam", "iyi gunler", "gunaydin", "iyi aksamlar",
                 "kolay gelsin", "slm")),
)


# 🔴 ONCELIK: sirali listelerden de once bakilan, tartismasiz kaliplar.
# "Yan etkisi var mi" bir GUVENLIK sorusudur; ama IDDIA listesindeki
# "etkisi" koku onu once yakaliyordu. Olculdu ve duzeltildi: tek kelimelik
# kokler, cok kelimeli ve daha spesifik bir kalibi ezmemeli.
ONCELIK: tuple[tuple[str, tuple[str, ...]], ...] = (
    (SAGLIK, ("yan etki", "yan etkisi", "ters etki")),
)


def siniflandir(metin: str) -> str:
    """Mesajın sınıfı. Emin değilse ANLASILMADI -- tahmin etmez."""
    sade = _sade(metin)
    if not sade:
        return ANLASILMADI
    for sinif, kokler in ONCELIK:
        if any(_kelime_gecer(sade, kok) for kok in kokler):
            return sinif
    for sinif, kokler in _SIRA:
        if any(_kelime_gecer(sade, kok) for kok in kokler):
            return sinif
    return ANLASILMADI


def jarvis_cevaplayabilir(sinif: str) -> bool:
    """Bu sınıf devir kapısının beyaz listesinde mi?

    `jarvis.devir` ile AYNI kümeyi kullanır; iki yerde iki liste tutmak
    ikisinin sessizce ayrışması demektir.
    """
    from . import devir
    return sinif in devir.JARVIS_SINIFLARI
