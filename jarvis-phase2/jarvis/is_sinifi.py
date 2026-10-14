"""İş sınıfı kapısı: bu metin neye dönüşüyor, hangi kademeyi hak ediyor.

ÖLÇÜLEN SORUN
`model_layer.needs_escalation()` bir KELİME LİSTESİNE bakıyordu: "strateji",
"karar ver", "kıyasla"... Liste iyi seçilmişti ama tek savunmaydı ve şu soru
listeye takılmıyor:

    "Bu krem hangi ürünle birlikte kullanılır?"

Kelime yok, 280 karakterin altında -> küçük modele düşer. Sahibin karar
vereceği bilgi, kalitesi ölçülmemiş modelden gelir. Sonucu zaten ölçülmüş:
aynı soruya 33 farklı cevap, VIREON fiyatı kimi cevapta 1.200 kimi 2.400.

ÇÖZÜM: SORUNUN ZORLUĞUNU DEĞİL, CEVABIN SONUCUNU SINIFLANDIR
"Bu soru zor mu" bir tahmindir ve yanlış tarafa düşebilir. "Bu cevap neye
dönüşüyor" bir olgudur ve çağıran taraf bunu bilir. Tahmin yerine politika:

    MUSTERIYE     müşteriye doğrudan gider    -> en güçlü model + mevzuat
    YAYIN_ADAYI   onay kuyruğuna/yayına aday  -> güçlü model + mevzuat
    KARAR_GIRDISI sahibin kararına girdi      -> güçlü model
    OLGU          kesin cevabı veritabanında  -> MODEL YOK
    MEKANIK       sınıflandırma/özet/biçim    -> küçük model yeter

MUSTERIYE bugün BOŞ bir sınıftır: 24.09.2026 itibarıyla EXTERNAL_ACTIONS=false,
JARVIS_MODE=SHADOW, n8n kanalları canlı trafiğe bağlı değil ve müşteri
mesajlarını Meta gelen kutusunda insan cevaplıyor. Jarvis'in ürettiği tek bir
cümle müşteriye ulaşmıyor. Sınıf, o gün geldiğinde hazır olsun diye tanımlı.

BEYAN TAHMİNDEN ÜSTÜNDÜR
Çağıran taraf ne ürettiğini bilir: kreatif hattı reklam metni ürettiğini
bilir, araştırma denetleyicisi analiz ürettiğini bilir. Beyan (`amac`) varsa
metin hiç taranmaz. Tarama, yalnız beyan yokken devreye giren yedek yoldur.

SIFIR MODEL ÇAĞRISI. Hangi modelin kullanılacağına model karar vermez.
"""
from __future__ import annotations

MUSTERIYE = "MUSTERIYE"
YAYIN_ADAYI = "YAYIN_ADAYI"
KARAR_GIRDISI = "KARAR_GIRDISI"
OLGU = "OLGU"
MEKANIK = "MEKANIK"

SINIFLAR = (MUSTERIYE, YAYIN_ADAYI, KARAR_GIRDISI, OLGU, MEKANIK)

# Güçlü modele gidenler. OLGU listede yok çünkü ona model hiç sorulmaz.
GUCLU_MODEL = frozenset({MUSTERIYE, YAYIN_ADAYI, KARAR_GIRDISI})

# Mevzuat denetçisinden geçmesi zorunlu olanlar: dışarı çıkabilecek metin.
MEVZUAT_ZORUNLU = frozenset({MUSTERIYE, YAYIN_ADAYI})


def fold(text: str) -> str:
    """Türkçe için güvenli küçük harfe indirme. TEK kaynak: model_layer da bunu
    kullanır, çünkü aynı hatayı iki yerde tutmak onu iki kez yapmak demek.

    🔴 ÖLÇÜLEN TUZAK -- kendi testim yakaladı (24.09.2026):
        "RAKİP".casefold() == "raki̇p"      ("i" + U+0307 BİRLEŞEN NOKTA)
        "raki̇p" != "rakip"                 -> eşleşme SESSİZCE boş döner
    Python'un casefold'u Türkçe bilmez: büyük "İ" (U+0130) küçültülürken
    noktayı ayrı bir birleşen karakter olarak bırakır. Önceki hâl yalnız
    "ı"->"i" yapıyordu, bu vakayı kaçırıyordu; "RAKİP ANALİZİ" MEKANIK
    sayılıp küçük modele düşüyordu.

    Sıra önemli: noktalı/noktasız büyük harfler casefold'dan ÖNCE düzleştirilir,
    kalan birleşen nokta sonra düşürülür (metin zaten ayrışık gelmiş olabilir).
    Diğer diakritikler (ö ü ç ş ğ) KORUNUR -- terim listeleri her iki yazımı da
    içeriyor, harfleri silmek gereksiz bilgi kaybı olurdu.
    """
    t = (text or "").replace("İ", "i").replace("I", "i").replace("ı", "i")
    t = t.casefold().replace("̇", "")
    return " ".join(t.split())


# Eski ad, iç kullanım için korunur.
_fold = fold


# Çağıran tarafın `amac` olarak verebileceği değerler. Beyan her zaman kazanır.
AMAC_SINIFI: dict[str, str] = {
    "musteri_yaniti": MUSTERIYE,
    "dm_yaniti": MUSTERIYE,
    "whatsapp_yaniti": MUSTERIYE,
    "reklam_metni": YAYIN_ADAYI,
    "caption": YAYIN_ADAYI,
    "urun_aciklamasi": YAYIN_ADAYI,
    "blog": YAYIN_ADAYI,
    "kreatif": YAYIN_ADAYI,
    "influencer_brief": YAYIN_ADAYI,
    "eposta_metni": YAYIN_ADAYI,
    "arastirma": KARAR_GIRDISI,
    "analiz": KARAR_GIRDISI,
    "strateji": KARAR_GIRDISI,
    "brief": KARAR_GIRDISI,
    "oneri": KARAR_GIRDISI,
    "rakip": KARAR_GIRDISI,
    "olgu": OLGU,
    "siniflandirma": MEKANIK,
    "ozet": MEKANIK,
    "bicim": MEKANIK,
    "niyet": MEKANIK,
}

# Sıra ÖNEMLİ: yayın > karar > olgu. "fiyat" hem "VIREON fiyatı kaç" (olgu)
# hem "fiyat stratejisi ne olmalı" (karar) içinde geçer; strateji terimi
# daha spesifik olduğu için önce bakılır.
_YAYIN_TERIMLERI = (
    "reklam metni", "reklam yaz", "caption", "gonderi metni", "gönderi metni",
    "post yaz", "slogan", "urun aciklamasi", "ürün açıklaması", "blog yaz",
    "blog yazisi", "blog yazısı", "baslik yaz", "başlık yaz", "metin yaz",
    "ilan metni", "eposta metni", "e-posta metni", "brief yaz", "kopya yaz",
    "tanitim yaz", "tanıtım yaz", "paylasim yaz", "paylaşım yaz",
)

_KARAR_TERIMLERI = (
    "detayli", "detaylı", "derin", "kapsamli", "kapsamlı", "daha iyi dusun",
    "daha iyi düşün", "uzun uzun", "buyuk model", "büyük model",
    "strateji", "karar ver", "kiyasla", "kıyasla", "karsilastir", "karşılaştır",
    "karsi cik", "karşı çık", "itiraz", "risk analizi", "senaryo",
    "avantaj ve dezavantaj", "arti ve eksi", "artı ve eksi",
    # araştırma/değerlendirme -- eski listede YOKTU, ölçülen boşluk buydu
    "arastir", "araştır", "analiz", "rakip", "degerlendir", "değerlendir",
    "yorumla", "ne yapmali", "ne yapmalı", "ne yapalim", "ne yapalım",
    "oneri", "öneri", "tavsiye", "sence", "planla", "yol haritasi",
    "yol haritası", "hangi urunle", "hangi ürünle", "birlikte kullan",
    "neden dusuyor", "neden düşüyor", "neden artiyor", "neden artıyor",
)

_OLGU_TERIMLERI = (
    "kac tane", "kaç tane", "kac adet", "kaç adet", "kac urun", "kaç ürün",
    "listele", "hangi tarihte", "ne zaman eklendi", "stok", "barkod", "sku",
    "kac konusma", "kaç konuşma", "kac mesaj", "kaç mesaj", "toplam sayi",
    "toplam sayı",
)

# Çok cümleli uzun istek aynı anda birden fazla iş yapıyor demektir.
_KARAR_KARAKTER = 280


def siniflandir(mesaj: str, *, amac: str | None = None) -> str:
    """Bu iş hangi sınıfa girer. Beyan varsa metin hiç taranmaz."""
    if amac:
        sinif = AMAC_SINIFI.get(_fold(amac).replace(" ", "_"))
        if sinif:
            return sinif
        # Tanınmayan beyan sessizce MEKANIK sayılamaz: bilinmeyen iş,
        # ucuz kademeye değil güvenli tarafa gider.
        return KARAR_GIRDISI

    metin = _fold(mesaj)
    if not metin:
        return MEKANIK
    if any(_fold(t) in metin for t in _YAYIN_TERIMLERI):
        return YAYIN_ADAYI
    if len(metin) >= _KARAR_KARAKTER:
        return KARAR_GIRDISI
    if any(_fold(t) in metin for t in _KARAR_TERIMLERI):
        return KARAR_GIRDISI
    if any(_fold(t) in metin for t in _OLGU_TERIMLERI):
        return OLGU
    return MEKANIK


def guclu_model_gerekir(sinif: str) -> bool:
    """Bu sınıf güçlü (dış) modelle mi cevaplanmalı."""
    return sinif in GUCLU_MODEL


def mevzuat_zorunlu(sinif: str) -> bool:
    """Bu sınıfın çıktısı mevzuat denetçisinden geçmek zorunda mı."""
    return sinif in MEVZUAT_ZORUNLU


def model_gerekir(sinif: str) -> bool:
    """OLGU sınıfına model sormak gerilemedir: Company Memory kesin biliyor."""
    return sinif != OLGU
