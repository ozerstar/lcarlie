# -*- coding: utf-8 -*-
"""Instagram içerik ustalığı: kanca formülleri, kanca puanı, caption denetimi.

KAYNAK: Jakeschincariol/instagram-agent-skill (MIT, 13.09.2026) -- `hooks.json`,
`hookscore.py`, `caption.py`, `slop.json`. Oradaki yöntem İNGİLİZCE metin için
yazılmıştı; Türkçeye ve L'CARLIÉ mevzuatına UYARLANDI, birebir çevrilmedi.

🔴 MEVZUAT YÜZÜNDEN ALINMAYAN FORMÜLLER. Kaynakta 26 formül var; altısı
kozmetikte doğrudan yasak bir iddia kalıbı kurar ve buraya hiç alınmadı:
  "Before/After"         önce/sonra = etkinlik iddiası
  "Someone Else's Result" bir kişinin sonucu = tanıklık iddiası
  "The Statistic"         "%87'sinde..." = belgesiz klinik iddia
  "The Superlative"       "en iyi / tek" = üstünlük iddiası (§ üstünlük)
  "The Receipt"           "30 gün kullandım, işte sonuçlar" = sonuç iddiası
  "Cost Confession"       korku/kayıp üzerinden satış
Formülü listede tutup "dikkatli kullan" demek, modelin onu bir gün
kullanması demektir. Yasak olan kalıp burada YOKTUR.

🔴 PUAN BİR TAHMİN DEĞİLDİR. Kaynağın kendi ölçümü: kötü kancayı iyiden
ayırmada AUC 0,83, iki iyi kancadan hangisinin tutacağını bilmede 0,56
(yazı tura 0,50). Bu yüzden puan yalnız ELEME için kullanılır -- selam,
önsöz, somut hiçbir şey taşımayan ve 4 saniyede söylenen kancayı yakalar.
Hangi kancanın izleneceğini videonun kendisi ve izlenme grafiği söyler.
"""
from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------
# KANCA FORMÜLLERİ
# --------------------------------------------------------------------------
# Her formül: şablon, örnek, ekran sürümü (<= 6 kelime) ve TUZAK -- formülün
# genelde nasıl bozulduğu. Tuzak satırı modele de gider: bir formülün nasıl
# bozulduğunu bilmeyen onu bozar.
FORMULLER: dict[str, dict[str, str]] = {
    "YANLIS_DOGRU": {
        "ad": "Yanlış yol, doğru yol",
        "sablon": "{Adımı} yanlış yapıyorsun ve suç sende değil. {Doğrusu}.",
        "ornek": "Kremi yanlış sürüyorsun ve suç sende değil. Nemli cilde, bezelye kadar.",
        "ekran": "Bunu yanlış yapıyorsun",
        "tuzak": "Doğrusunu yarıya kadar söylememek. Söz verilen düzeltme ilk 5 saniyede gelir.",
    },
    "KIMSE_SOYLEMEZ": {
        "ad": "Kimse söylemiyor",
        "sablon": "Kimse sana şunu söylemiyor: {kullanımla ilgili rahatsız edici gerçek}.",
        "ornek": "Kimse sana şunu söylemiyor: bakım ürünü miktarla değil düzenle çalışır.",
        "ekran": "Kimse bunu söylemiyor",
        "tuzak": "Gerçek dediğin şey bir ürün iddiası olursa mevzuata takılır. Gerçek KULLANIMLA ilgili olmalı.",
    },
    "BIRAK_YERINE": {
        "ad": "Bırak, yerine bunu yap",
        "sablon": "{Yaygın alışkanlığı} bırak. Yerine {alternatif adım}.",
        "ornek": "Banyodan çıkıp beş dakika bekleme. Cilt nemliyken uygula.",
        "ekran": "Bunu bırak",
        "tuzak": "Başka bir markayı ya da ürün türünü kötülemek. Bırakılan şey bir ALIŞKANLIK olmalı, rakip değil.",
    },
    "SAYILI_ADIM": {
        "ad": "Sayılı adım, gizli favori",
        "sablon": "{N} adımda {rutin}. {k}. adım çoğu kişinin atladığı.",
        "ornek": "Üç adımda akşam rutini. İkinci adım herkesin atladığı.",
        "ekran": "3 adım, 1'i atlanıyor",
        "tuzak": "Sayıyı söyleyip atlanan adımı hiç göstermemek.",
    },
    "DOGRUDAN_SORU": {
        "ad": "Gelen soru, aynen",
        "sablon": "“{Müşterinin sorusu aynen}” Bunu her hafta soruyorsunuz.",
        "ornek": "“Sabah mı akşam mı sürülür?” Bunu her hafta soruyorsunuz.",
        "ekran": "Her hafta bunu soruyorsunuz",
        "tuzak": "Soruyu cilalamak. Gerçek soru bozuk dilbilgisiyle daha inandırıcıdır.",
    },
    "SOGUK_ACILIS": {
        "ad": "Ortadan başla",
        "sablon": "{Uygulamanın ortasından başla, ürün zaten elde.} Şimdi şuna bak.",
        "ornek": "(kapak açılıyor, doku parmakta) Şimdi şu dokuya bak.",
        "ekran": "Şu dokuya bak",
        "tuzak": "İlk karede hareketsiz bir yüz. İlk kare de bir kancadır.",
    },
    "ITIRAZ": {
        "ad": "İtirazı kabul et",
        "sablon": "“{Gerçekten duyulan itiraz}.” Haklısın. O yüzden şöyle kullan.",
        "ornek": "“Benim rutinime bir ürün daha sığmaz.” Haklısın. O yüzden tek adımda bitiyor.",
        "ekran": "Rutinine sığmaz mı?",
        "tuzak": "İtirazı kimsenin söylemediği bir cümleyle kurmak.",
    },
    "HITAP": {
        "ad": "Belirli kişiye seslen",
        "sablon": "{Belirli bir kitle}, bu tam olarak senin için.",
        "ornek": "Gün boyu maske takanlar, bu tam olarak sizin için.",
        "ekran": "Gün boyu maske takanlar",
        "tuzak": "Kitleyi hastalık ya da durum adıyla tanımlamak (egzama, akne). Kitle bir YAŞAM DURUMU olmalı.",
    },
    "IZIN": {
        "ad": "Gerek yok",
        "sablon": "{Herkesin şart dediği şeye} ihtiyacın yok.",
        "ornek": "On adımlı bir rutine ihtiyacın yok.",
        "ekran": "Buna ihtiyacın yok",
        "tuzak": "İzni verip yerine ne konduğunu söylememek.",
    },
    "SURE_SAYACI": {
        "ad": "Saniye sayacı",
        "sablon": "{N} saniyede {rutin adımı}.",
        "ornek": "Yirmi saniyede sabah adımı.",
        "ekran": "20 saniye",
        "tuzak": "Süreyi söyleyip videoyu üç katı uzun tutmak.",
    },
    "TERS_ATASOZU": {
        "ad": "Bilineni ters çevir",
        "sablon": "{Yaygın bir bakım sözünü ters çevir}.",
        "ornek": "Az sürmek, çok sürmekten daha çok iş görür.",
        "ekran": "Az, çoktan iyidir",
        "tuzak": "Ters çevrilen söz bir sağlık iddiasına dönüşürse yayınlanmaz.",
    },
    "ORTA_CUMLE": {
        "ad": "Cümlenin ortasından",
        "sablon": "…ve tam o sırada {dönüm noktası}.",
        "ornek": "…ve tam o sırada kapağın neden pompalı olduğunu anladım.",
        "ekran": "Tam o sırada",
        "tuzak": "Dönüm noktasını hiç vermemek; merak sömürüsü güveni bitirir.",
    },
}

# Video saniye sınırları -- kaynak kuralı: kanca ~2 sn, ekran yazısı ~1 sn.
KURALLAR: tuple[str, ...] = (
    "Söylenen kanca ile ekran yazısı AYRI yazılır. Ekran yazısı 6 kelimeyi geçmez.",
    "Giriş yok. Video, normalde 6. saniyede söyleyeceğin cümleyle başlar.",
    "Sayıyı söyle. 'Çok' bir sayı değildir.",
    "İlk kare de kancadır: hareketsiz, yazısız bir açılış üç kancayı harcar.",
    "Rakibin de söyleyebileceği kanca senin kancan değildir; ürüne özgü olanı koy.",
    "Kanca bir söz verir; söz videonun yarısından önce yerine getirilir.",
)

# --------------------------------------------------------------------------
# KANCA PUANI (Türkçe uyarlama)
# --------------------------------------------------------------------------
_KELIME = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû%'’-]+")
_SAYI = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|ml|gr|g|sn|saniye|dakika|dk|gün|hafta|adım)?",
                   re.IGNORECASE)
_HASHTAG = re.compile(r"(?:^|\s)#\w+")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")

SOZLU_SAYI = {
    "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on",
    "yirmi", "otuz", "kırk", "elli", "yüz", "bin", "yarım", "çeyrek",
    "saniye", "saniyede", "dakika", "dakikada", "adım", "adımda", "damla",
}
# Bir şeyin kaybedilebileceğini söyleyen kelimeler. Hiçbiri yoksa cümle bir
# bildirimdir; biri varsa izlemeye devam etmek için sebeptir.
GERILIM = {
    "yanlış", "hata", "hatası", "bırak", "asla", "kimse", "kimsenin", "değil",
    "yerine", "sakın", "aslında", "ama", "sadece", "yalnız", "olmadan",
    "önce", "atla", "atlıyor", "atladığı", "unut", "neden", "gerek", "yok",
    "ihtiyacın", "herkes", "çoğu", "söylemiyor", "bilmiyor", "fark",
    "haklısın", "tam", "dur", "bekleme",
}
ZAYIF_ACILIS = (
    "merhaba", "selam", "arkadaşlar", "bugün", "bu videoda", "bu video",
    "hepinize", "evet", "şimdi size", "hani", "biliyor musunuz",
    "size göstereceğim", "sizlere", "herkese", "iyi günler", "günaydın",
    "bu ürün", "bu ürünümüz", "l'carlié",
)
HITAP_KELIME = {
    "sen", "sana", "seni", "senin", "siz", "size", "sizin", "cildin",
    "cildini", "cildine", "rutinin", "rutinine", "rutinini",
}
OLDURUCU = (
    (re.compile(r"(?i)^\s*(kaydırmayı bırak|geçme|dur ve izle)"),
     "“Kaydırmayı bırak” ile açılıyor; dikkat istemek, onu kazanmadığını gösterir."),
    (re.compile(r"(?i)\b(bu videoda|size göstereceğim|sizlere anlatacağım)\b"),
     "Önsöz. Sil, doğrudan sonuçla aç."),
    (re.compile(r"(?i)^\s*(merhaba|selam|herkese|iyi günler|günaydın)\b"),
     "Selamlama. Kimse akışa selamlanmak için gelmedi."),
    (_HASHTAG, "Kancada hashtag. Hashtag caption'ın sonunda olur."),
    (_EMOJI, "Kancada emoji. Kanca boyutundaki ekran yazısında ya kelimeye ya emojiye yer var."),
)


def _katla(metin: str) -> str:
    return unicodedata.normalize("NFC", metin).replace("İ", "i").replace("I", "ı").lower()


def kelimeler(metin: str) -> list[str]:
    return _KELIME.findall(metin or "")


def kanca_puani(metin: str, urun_adi: str = "") -> dict:
    """0-100 puan + beş ölçütün gerekçesi + öldürücü kusurlar.

    Türkçe sondan eklemeli: İngilizcede 5-12 kelimelik kanca Türkçede
    4-10 kelimeye denk düşüyor ("saniyede", "atladığı" tek kelime).
    """
    metin = (metin or "").strip()
    k = kelimeler(metin)
    kucuk = [_katla(x).strip("'’") for x in k]
    n = len(k)

    # 1) uzunluk -- ~2,5 kelime/sn konuşma hızı
    if 4 <= n <= 10:
        uzunluk = 100.0
    elif n < 4:
        uzunluk = max(0.0, 100 - (4 - n) * 25)
    else:
        uzunluk = max(0.0, 100 - (n - 10) * 12)
    if len(metin) > 60:
        uzunluk -= 12

    # 2) somutluk -- sayı, özel ad, sözlü sayı
    sayilar = [s for s in _SAYI.findall(metin) if s.strip()]
    ozel = [w for i, w in enumerate(k) if i and w[:1].isupper()]
    sozlu = [w for w in kucuk if w in SOZLU_SAYI]
    isabet = len(sayilar) + len(ozel) + len(sozlu)
    somutluk = 15.0 if isabet == 0 else min(100.0, 45 + isabet * 30)

    # 3) gerilim
    gerilim_k = sorted({w for w in kucuk if w in GERILIM})
    gerilim = {0: 20.0, 1: 70.0}.get(len(gerilim_k), 100.0)

    # 4) öne yükleme -- ilginç kelime 4. kelimeden önce
    ceza = 20 if any(_katla(metin).startswith(z) for z in ZAYIF_ACILIS) else 0
    yuk = None
    for i, w in enumerate(kucuk):
        if w in GERILIM or w in SOZLU_SAYI or _SAYI.match(k[i]) or (i and k[i][:1].isupper()):
            yuk = i
            break
    if yuk is None:
        one = 30.0
    elif yuk <= 3:
        one = 100.0
    elif yuk <= 6:
        one = 70.0
    else:
        one = 40.0
    one = max(0.0, one - ceza)

    # 5) hitap -- kime söylendiği belli mi
    hitap = 100.0 if any(w in HITAP_KELIME for w in kucuk) or re.search(
        r"(?i)\b\w+(?:ıyorsun|iyorsun|uyorsun|üyorsun|sın|sin|sun|sün)\b", metin) else 40.0

    kusurlar = [neden for desen, neden in OLDURUCU if desen.search(metin)]
    if urun_adi and _katla(metin).startswith(_katla(urun_adi.split("(")[0].strip())[:6]):
        kusurlar.append("Ürün adıyla açılıyor; ad kancayı değil reklamı başlatır.")

    toplam = round(uzunluk * 0.2 + somutluk * 0.2 + gerilim * 0.25 + one * 0.2 + hitap * 0.15)
    if kusurlar:
        toplam = min(toplam, 35)
    return {
        "puan": int(max(0, min(100, toplam))),
        "uzunluk": f"{n} kelime, {len(metin)} karakter (hedef 4-10 kelime)",
        "somutluk": f"{isabet} somut işaret",
        "gerilim": ", ".join(gerilim_k) or "yok",
        "kusurlar": kusurlar,
    }


# --------------------------------------------------------------------------
# YAPAY ZEKÂ KOKUSU (Türkçe) + CAPTION DENETİMİ
# --------------------------------------------------------------------------
# Kaynağın slop.json'u İngilizce kalıp listesiydi; Türkçe reklam metninde
# yapay zekâyı ele veren kalıplar bunlar. Liste değil SİNYAL: biri bile
# metni "şablon" gibi okutur.
KOKU: tuple[str, ...] = (
    "hazır mısınız", "hazır mısın", "keşfetmeye hazır", "büyülü", "eşsiz",
    "vazgeçilmez", "sırrı", "devrim niteliğinde", "bir sonraki seviye",
    "kendinizi şımartın", "kendini şımart", "lüksün tadını", "hayalinizdeki",
    "adeta", "tam anlamıyla", "unutulmaz", "benzersiz", "muhteşem",
    "sonuç olarak", "unutmayın", "unutma ki", "işte tam bu noktada",
    "gelin birlikte", "hadi gelin", "peki ya", "yolculuğ", "deneyimleyin",
    "dönüştürün", "kucaklayın", "ışıldayın", "parıldayın", "harikalar yaratır",
    "fark yaratır", "mükemmel uyum",
)
# Ürün etkisi anlatan fiiller. Serbest metinde (yani {S#} cümle referansı
# DIŞINDA) geçerse modelin İDDİA uydurduğu anlamına gelir: ürün cümlesi
# yalnız yayındaki, denetimden geçmiş havuzdan gelir.
IDDIA_FIILI = re.compile(
    # Kök + ek kalıbı: "sağlam", "giderken", "korku" gibi masum kelimeler
    # yakalanmasın diye kökler EKİYLE yazıldı.
    r"(?i)(?<!\w)(?:kazandır|sağla(?:r|yan|dığı|yıp|maya)|destekle|azalt|"
    r"gider(?:ir|en|mey)|onar(?:ır|an|ıp)|koru(?:r|yan|maya|yup)|besle(?:r|yen|yip)|"
    r"nemlendir|yatıştır|rahatlat|arındır|sıkılaştır|aydınlat|"
    r"yenile(?:r|yen|yip)|canlandır|güçlendir|önle(?:r|yen|meye)|iyileştir|tedavi)\w*")
# 🔴 YASAK NESNE -- compliance.review'un KAÇIRDIĞI kalıplar (30.10.2026 ilk
# günlük pakette ölçüldü): "Sızlayan bacaklar", "rahat uyku", "bacaklar
# dinlenir", "emilim daha iyi olur", "Sonuç: fark". Kural fiil değil
# NESNE: izinli nesneler görünüm · his · doku · nem hissi · konfor · koku.
# Semptom, fizyolojik işlev ve sonuç vaadi serbest metinde geçemez.
YASAK_NESNE: tuple[tuple[str, re.Pattern], ...] = tuple(
    (ad, re.compile(desen, re.IGNORECASE)) for ad, desen in (
        ("semptom", r"(?<!\w)(?:sızla\w*|ağrı\w*|kramp\w*|şişlik\w*|şişkin\w*|"
                    r"uyuşma\w*|uyuşuk\w*|karıncalan\w*|kaşıntı\w*|iltihap\w*|"
                    r"ödem\w*|varis\w*|selülit\w*|egzama\w*|akne\w*|sivilce\w*|"
                    r"tahriş\w*|kızarıklı\w*|yara(?:lar\w*|ya|yı|da|dan|sı\w*|nın|nız)?(?!\w)|mantar\w*|çatla\w*)"),
        ("fizyolojik işlev", r"(?<!\w)(?:dolaşım\w*|kan akış\w*|damar\w*|emilim\w*|"
                             r"emil(?:ir|en|di)\w*|hücre\w*|kolajen\w*|elastik\w*|"
                             r"metabolizma\w*|hormon\w*|uyku\w*|uyurken|dinlen\w*|"
                             r"yenilen\w*|onarım\w*|detoks\w*|toksin\w*|aktif hale)"),
        ("sonuç vaadi", r"(?:fark\w* gör\w*|sonuç\s*:|sonucu\w* gör\w*|öncesi ve sonrası|"
                        r"önce ve sonra|kanıtlan\w*|garanti\w*|\d+\s*%|%\s*\d+|"
                        r"\d+\s*günde)"),
    ))


def yasak_nesne(metin: str, muaf: tuple[str, ...] = ()) -> list[str]:
    """Serbest metindeki yasak nesneler. `muaf`: zorunlu uyarı cümleleri
    ("Açık yaralara uygulanmamalıdır" gibi) -- bunlar silinmemeli, aranmaz."""
    temiz = re.sub(r"\{S\d+\}", " ", metin or "")
    for m in muaf:
        if m:
            temiz = temiz.replace(m.strip().rstrip("."), " ")
    bulgu = []
    for ad, desen in YASAK_NESNE:
        for m in desen.finditer(temiz):
            bulgu.append("%s: %s" % (ad, m.group(0)))
    return sorted(set(bulgu))


def noktalama_duzelt(metin: str) -> str:
    """Havuz cümlesi yerleşince oluşan '..', '.,', ' .' gibi dikiş izleri."""
    metin = re.sub(r"\.\s*\.(?!\.)", ".", metin or "")
    metin = re.sub(r"\.\s*,", ".", metin)
    metin = re.sub(r"[ \t]+([.,;:!?])", r"\1", metin)
    metin = re.sub(r"[ \t]{2,}", " ", metin)
    return metin.strip()


CAPTION_GORUNUR = 125     # "...devamı"ndan önce görünen karakter
CAPTION_TAVAN = 2200
EMOJI_TAVAN = 3


def koku_bul(metin: str) -> list[str]:
    k = _katla(metin)
    return [x for x in KOKU if x in k]


def insanlastir(metin: str) -> str:
    """Tipografik yapay zekâ izi: uzun tire, akıllı tırnak, görünmez karakter."""
    metin = re.sub(r"\s*—\s*", ", ", metin or "")
    metin = metin.replace("–", "-").replace("​", "").replace(" ", " ")
    return re.sub(r",\s*,", ",", metin)


def serbest_iddia(metin: str) -> list[str]:
    """{S#} referansları çıkarıldıktan sonra kalan iddia fiilleri."""
    temiz = re.sub(r"\{S\d+\}", " ", metin or "")
    return sorted({m.group(0) for m in IDDIA_FIILI.finditer(temiz)})


def caption_denetle(caption: str, hashtagler: list[str], tavan: int) -> list[str]:
    """Yayından önce yakalanması gereken biçim kusurları. Boş liste = temiz."""
    notlar = []
    ilk = (caption or "").split("\n", 1)[0]
    if len(ilk) > CAPTION_GORUNUR:
        notlar.append(f"İlk satır {len(ilk)} karakter; '…devamı'ndan önce {CAPTION_GORUNUR} görünür, kanca kesilir.")
    if len(caption or "") > CAPTION_TAVAN:
        notlar.append(f"Caption {len(caption)} karakter, tavan {CAPTION_TAVAN}.")
    if re.search(r"https?://|www\.", caption or ""):
        notlar.append("Caption'da link var; Instagram caption linki tıklanmaz. 'Profildeki bağlantı' yazılır.")
    if len(hashtagler or []) > tavan:
        notlar.append(f"{len(hashtagler)} hashtag, tavan {tavan}.")
    emoji = len(_EMOJI.findall(caption or ""))
    if emoji > EMOJI_TAVAN:
        notlar.append(f"{emoji} emoji, tavan {EMOJI_TAVAN}.")
    koku = koku_bul(caption or "")
    if koku:
        notlar.append("Yapay zekâ kokusu: " + ", ".join(koku[:5]))
    return notlar
