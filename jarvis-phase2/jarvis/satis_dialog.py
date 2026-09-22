"""Müşteriye giden cevabı ÜRETİR — hazır şablon seçmez.

NEDEN VAR
Mevcut satış ajanı sabit şablonlardan seçiyordu. Ölçüldü (20.09.2026,
`lcarlie.mesaj` üzerinde): aynı soruya 33 farklı cevap gitmiş, VIREON fiyatı
kimi mesajda 1.200 kimi mesajda 2.400 denmiş. Sahibin talebi net: şablon
değil, müşteriye ve ürüne göre yazılan, geri dönüşe bakarak kendini
düzelten bir cevap.

ÜÇ KATMAN, ÜÇÜ DE AYRI SORUMLU
  1. OLGU   -- fiyat, stok, içindekiler, kargo. `mart.urun_karti`'ndan gelir.
               Model bu sayıları ÜRETMEZ, yalnız cümle içine yerleştirir.
               Fiyatı modele sorduğumuz an 33 farklı cevap sorunu geri gelir.
  2. ÜSLUP  -- `yaklasim` metni. Kodda gömülü DEĞİL, sürümlü veri.
               Öğrenme döngüsü yeni sürüm önerir, insan onaylar.
  3. DENETİM-- jarvis.compliance (kademe 1 mevzuat taraması). BLOCKED çıkan
               metin gönderilmez; bu modül "uygun" damgası basmaz.

🔴 NE YAPMAZ
Mesaj GÖNDERMEZ. Bu modülün dışarıya hiçbir yolu yok: üretir, denetler,
döndürür. Gönderme kararı ve yolu çağıranındır (ve bugün insan onayındadır).

🔴 ÜRÜN ATAMASI TAHMİN EDİLMEZ
Ölçüldü: 540 müşteri mesajının hiçbirinde "VIREON" geçmiyor, ama 183'ü fiyat
soruyor. Yani "fiyatı nedir?" mesajından ürün ÇIKARILAMAZ. Ürün dışarıdan
(reklam referansından) verilmezse `urun=None` ile çalışılır ve cevap ürün
adı uydurmak yerine doğal biçimde hangi ürün olduğunu sorar. Yanlış ürünün
fiyatını söylemek, fiyat söylememekten çok daha pahalıdır.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import compliance

# --- soru tipleri --------------------------------------------------------
FIYAT = "FIYAT"
ICERIK = "ICERIK"
SIPARIS = "SIPARIS"
KULLANIM = "KULLANIM"
KARGO = "KARGO"
GENEL = "GENEL"

# Kök halinde tutulur; Türkçe ekler ve ünsüz yumuşaması `_gecer()` içinde
# ele alınıyor. Sıra ÖNEMLİ: bir mesaj hem "fiyat" hem "içindekiler"
# içerebilir ve o durumda ilki kazanır.
_TIP_KOKLERI: tuple[tuple[str, tuple[str, ...]], ...] = (
    (SIPARIS, ("siparis", "nasil alabilir", "nasil alinir", "satin al",
               "sepet", "odeme", "kapida")),
    (KARGO, ("kargo", "teslim", "ne zaman gelir", "gonderim")),
    (ICERIK, ("icindekiler", "icerik", "icinde ne", "bilesen", "formul",
              "ingredient", "muhtevi")),
    (FIYAT, ("fiyat", "kac para", "ne kadar", "ucret", "kac tl", "kac lira")),
    (KULLANIM, ("nasil kullan", "kullanim", "gunde kac", "surulur")),
)


def _sade(text: str) -> str:
    """Türkçe duyarlı sadeleştirme: küçült, aksanı kaldır, boşluğu tekle.

    🔴 `.lower()` DEĞİL `casefold()` + açık I/İ eşlemesi: Türkçe yerelde
    `"I".lower()` noktasız `ı` üretir ve hiçbir şeyle eşleşmez. Bu tuzak bu
    projede daha önce 30 üründen 12'sini sessizce denetim dışı bıraktı.
    """
    text = (text or "").replace("İ", "i").replace("I", "i").replace("ı", "i")
    text = text.casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _gecer(sade_mesaj: str, kok: str) -> bool:
    """Kök mesajda geçiyor mu — ünsüz yumuşaması dahil.

    Türkçede k→ğ, t→d, p→b: "icerik" ≠ "icerigi". Sondaki ünsüzün yumuşamış
    hâli de aranır, yoksa en sık sorulan soru kaçar.
    """
    if kok in sade_mesaj:
        return True
    yumusak = {"k": "g", "t": "d", "p": "b", "c": "c"}
    son = kok[-1:]
    if son in yumusak:
        return (kok[:-1] + yumusak[son]) in sade_mesaj
    return False


def soru_tipi(mesaj: str) -> str:
    """Müşterinin ne sorduğu. Bilinmiyorsa GENEL — uydurulmaz."""
    sade = _sade(mesaj)
    if not sade:
        return GENEL
    for tip, kokler in _TIP_KOKLERI:
        if any(_gecer(sade, kok) for kok in kokler):
            return tip
    return GENEL


# --- ürün kartı ----------------------------------------------------------
# 🔴 İKİ NOKTA ZORUNLU, opsiyonel değil.
# İlk hâli `kullan[ıi]m\s*:?` yazıyordu ve ölçümde "Düzenli kullanımDA yorgun,
# mat ve gergin..." cümlesinin ORTASINDAN yakaladı; müşteriye kullanım
# talimatı diye ürün övgüsü gidecekti. Başlık, başlık gibi aranmalı.
_ICINDEKILER = re.compile(r"i[çc]indekiler\s*:\s*(.+?)(?:\s*ingredients\s*:|$)",
                          re.IGNORECASE | re.DOTALL)
_KULLANIM = re.compile(r"(?:^|[.\s])kullan[ıi]m\s*:\s*(.+?)(?:\s{2,}|uyar[ıi]lar|raf [öo]mr|$)",
                       re.IGNORECASE | re.DOTALL)
_KARGO = re.compile(r"kargo\s*(?:&|ve)?\s*teslimat\s*:\s*(.+?)(?:\s{2,}|$)",
                    re.IGNORECASE | re.DOTALL)


def _bosluk_koru(ham: str) -> str:
    """HTML varlıklarını çözer ama BOŞLUK YAPISINI KORUR.

    Wix metninde bölümler ardışık boşlukla ayrılıyor; `" ".join(split())`
    o sınırı siliyordu ve kargo alanı ürün açıklamasının içine taşıyordu.
    Kırpma, alan ayıklandıktan SONRA yapılır.
    """
    return html.unescape(ham or "").replace("\xa0", " ").replace("\r", " ")


def _temizle(ham: str) -> str:
    return " ".join(_bosluk_koru(ham).split())


@dataclass
class UrunKarti:
    urun_id: str
    ad: str
    satis_fiyat: float | None
    liste_fiyat: float | None
    stokta: bool
    aciklama: str
    icindekiler: str = ""
    kullanim: str = ""
    kargo: str = ""

    @property
    def kampanyali(self) -> bool:
        return bool(self.liste_fiyat and self.satis_fiyat
                    and self.liste_fiyat > self.satis_fiyat)

    def _fiyat_satiri(self) -> str | None:
        if not self.satis_fiyat:
            return None
        if self.kampanyali:
            return (f"Güncel fiyat: {self.satis_fiyat:,.0f} TL "
                    f"(liste fiyatı {self.liste_fiyat:,.0f} TL)").replace(",", ".")
        return f"Fiyat: {self.satis_fiyat:,.0f} TL".replace(",", ".")

    def olgular(self, tip: str = GENEL) -> list[str]:
        """Bu SORU için gereken doğrulanmış olgular — hepsi değil.

        🔴 NEDEN DARALTILDI (sahip talebi, 20.09.2026):
        *"her mesaj için tüm konuyu anlatma, gerekli cevabı iste"*.
        Önceki hâli ürün kartının tamamını (içindekiler dahil, ~1.500
        karakter) her soruda gönderiyordu. İki zararı vardı: dış modele
        gereksiz jeton parası ödeniyordu ve model, sorulmayan bilgiyi
        cevaba sokuyordu ("fiyat?" sorusuna kullanım talimatı ekliyordu).

        Fiyat sorana fiyat, içerik sorana içerik gider.
        """
        satir = [f"Ürün: {self.ad}"]
        fiyat = self._fiyat_satiri()

        if tip == ICERIK:
            # Liste modele VERİLMEZ: onu kod, beyan biçiminde kendisi ekler.
            # Modele verilirse düz yazıya gömüyor ve mevzuat kuralı haklı
            # olarak blokluyor (ölçüldü: 'epimedium' bileşen tuzağı).
            return satir
        if tip == KULLANIM:
            if self.kullanim:
                satir.append("Kullanım: " + self.kullanim)
            return satir
        if tip == KARGO:
            if self.kargo:
                satir.append("Kargo: " + self.kargo)
            return satir
        # FIYAT, SIPARIS ve GENEL: fiyat + stok yeter.
        if fiyat:
            satir.append(fiyat)
        satir.append("Stok: " + ("var" if self.stokta else "yok"))
        return satir


def _alan(desen: re.Pattern[str], kaynak: str, sinir: int) -> str:
    eslesme = desen.search(kaynak)
    if not eslesme:
        return ""
    return " ".join(eslesme.group(1).split())[:sinir]


def kart_olustur(kayit: dict[str, Any]) -> UrunKarti:
    ham = _bosluk_koru(kayit.get("aciklama_duz") or "")
    aciklama = _temizle(kayit.get("aciklama_duz") or "")
    # Ayıklama boşluk yapısı KORUNMUŞ metin üzerinde yapılır; bölüm sınırı
    # ardışık boşluktur ve kırpılmış metinde o sınır yoktur.
    icindekiler = _alan(_ICINDEKILER, ham, 1200)
    kullanim = _alan(_KULLANIM, ham, 400)
    kargo = _alan(_KARGO, ham, 200)
    satis = kayit.get("wix_satis")
    liste = kayit.get("wix_liste")
    return UrunKarti(
        urun_id=str(kayit.get("urun_id") or ""),
        ad=str(kayit.get("urun_adi") or "").strip(),
        satis_fiyat=float(satis) if satis is not None else None,
        liste_fiyat=float(liste) if liste is not None else None,
        stokta=bool((kayit.get("wix_stok") or 0) > 0 and kayit.get("wix_yayinda")),
        aciklama=aciklama,
        icindekiler=icindekiler,
        kullanim=kullanim,
        kargo=kargo,
    )


def urun_bul(kayitlar: Iterable[dict[str, Any]], ad: str) -> UrunKarti | None:
    """Ürünü ADIYLA bulur. Bulamazsa None döner — en yakınına DÜŞMEZ.

    "En yakın ürün" tahmini burada bilerek yok: yanlış ürünün fiyatını
    söylemek, fiyat söylememekten pahalıdır.
    """
    aranan = _sade(ad)
    if not aranan:
        return None
    for kayit in kayitlar:
        if _sade(str(kayit.get("urun_adi") or "")).startswith(aranan):
            return kart_olustur(kayit)
    for kayit in kayitlar:
        if aranan in _sade(str(kayit.get("urun_adi") or "")):
            return kart_olustur(kayit)
    return None


# --- yaklaşım (üslup) ----------------------------------------------------
# Kodda duran tek şey BAŞLANGIÇ sürümü. Öğrenme döngüsü bunun üzerine yeni
# sürüm önerir; onaylanan sürüm veriden gelir ve buradaki metni ezer.
VARSAYILAN_YAKLASIM = (
    "Sıcak ve doğal yaz, sohbet gibi. Soruyu cevapla, sonra tek bir adım öner."
)

# Yaklaşım sürümü değişse de bunlar değişmez. Üçü de ilk canlı denemede
# (20.09.2026) gerçekten yaşandı ve hiçbirini denetim katmanı yakalayamaz --
# çünkü üçü de yasak iddia değil, ÜSLUP sorunu.
DEGISMEZ_USLUP = (
    "SİZ diye hitap et. Soruyu tekrar etme. "
    "Müşterinin durumu hakkında varsayım yapma."
)

# 🔴 İSTEM NEDEN BU KADAR KISA
# Sahip talebi (20.09.2026): *"ona basit prompt söyle… her mesaj için tüm
# konuyu anlatma"*. Kısaltmak güvenliği ZAYIFLATMIYOR, çünkü güvenlik zaten
# istemde değil KODDA duruyor: olgu kapısı, sayı kapısı, kesik-cevap kapısı
# ve `compliance.review`. Uzun bir kural listesi modelin uymasına güvenmek
# demekti; ölçtük, 4B model uymadı. Kod uyuyor.
#
# Kalan üç satırın her biri denetimle yakalanamayan bir ÜSLUP sorununu
# kapatıyor (iddia değil, ton): siz dili, soruyu tekrar etmemek, müşterinin
# durumu hakkında varsayım yapmamak.
SISTEM_YONERGESI = """L'CARLIÉ müşteri mesajını yanıtla. Türkçe, 2-3 cümle.
Yalnızca aşağıdaki bilgiyi kullan; burada olmayan hiçbir şey yazma.
{yaklasim}

{olgular}

Müşteri: {soru}
"""

# Meta, otomatik yanıt deneyimlerinin kullanıcıya bildirilmesini şart koşuyor.
# Sahip kararı (20.09.2026): görünmez düzeyde — yalnız konuşmanın İLK
# cevabında, tek satır, sonraki mesajlarda hiç yok.
IFSA_SATIRI = "— L'CARLIÉ dijital asistanı"


@dataclass
class Cevap:
    metin: str
    soru_tipi: str
    urun: str | None
    yaklasim: str
    olgular: list[str] = field(default_factory=list)
    mevzuat: str = "BILINMIYOR"
    bulgular: list[dict[str, str]] = field(default_factory=list)
    gonderilebilir: bool = False
    model: str | None = None
    model_calls: int = 0
    gerekce: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metin": self.metin, "soru_tipi": self.soru_tipi, "urun": self.urun,
            "yaklasim": self.yaklasim, "olgular": self.olgular,
            "mevzuat": self.mevzuat, "bulgular": self.bulgular,
            "gonderilebilir": self.gonderilebilir, "model": self.model,
            "model_calls": self.model_calls, "gerekce": self.gerekce,
        }


# --- uydurma kapısı ------------------------------------------------------
# 🔴 BU BÖLÜM BİR ÖLÇÜMDEN DOĞDU (20.09.2026, ilk canlı deneme)
# INTIMBLANC'ın içindekiler alanı kartta BOŞ. Modele "içindekiler nelerdir"
# diye sorulunca listeyi SIFIRDAN UYDURDU: "niasinamid, arbutin, traneksamik
# asit, kojik asit dipalmitat". Mevzuat taraması bunu TEMİZ geçirdi -- ve
# doğru davrandı: o katman yasak İDDİA arar, uydurma OLGU aramaz.
#
# Kozmetikte uydurma bileşen listesi müşteriye gidemez. Çözüm istem yazmak
# değil -- 4B model kuralı tutmadı, tutacağına da güvenilemez. Çözüm yapısal:
# cevap için gereken olgu kartta YOKSA model hiç çağrılmaz.

_GEREKLI_OLGU: dict[str, str] = {
    FIYAT: "satis_fiyat",
    ICERIK: "icindekiler",
    KULLANIM: "kullanim",
}

# Cevapta geçmesine izin verilen, olgudan bağımsız küçük sayılar
# (gün/kez gibi). Bunun dışındaki her sayı olgularda geçmek zorunda.
_SERBEST_SAYILAR = {"1", "2", "3", "24"}


def eksik_olgu(tip: str, urun: UrunKarti) -> str | None:
    """Bu soru tipini cevaplamak için gereken olgu kartta var mı."""
    alan = _GEREKLI_OLGU.get(tip)
    if not alan:
        return None
    return alan if not getattr(urun, alan, None) else None


_SAYI = re.compile(r"\d[\d.,]*")
_YER_TUTUCU = re.compile(r"\[[^\]]{3,}\]|\{\{|buraya\s+\w+\s+(eklen|yaz)",
                         re.IGNORECASE)


def uydurma_sayi(metin: str, olgular: list[str]) -> list[str]:
    """Cevapta geçip olgularda geçmeyen sayılar.

    Uydurulmuş fiyat, oran, süre ve adet bu kapıdan geçemez. Karşılaştırma
    ayraçsız yapılır: "1.200" ile "1200" aynı sayıdır.
    """
    havuz = _SAYI.sub(lambda m: m.group(0).replace(".", "").replace(",", ""),
                      " ".join(olgular))
    kacak: list[str] = []
    for ham in _SAYI.findall(metin):
        sade = ham.replace(".", "").replace(",", "").rstrip("0") or ham
        tam = ham.replace(".", "").replace(",", "")
        if tam in _SERBEST_SAYILAR or sade in _SERBEST_SAYILAR:
            continue
        if tam not in havuz:
            kacak.append(ham)
    return kacak


def _urun_sor(tip: str) -> str:
    """Ürün bilinmiyorken kurulacak doğal soru.

    Şablon gibi durmasın diye soru tipine göre değişir, ama UYDURMA bilgi
    içermez: hangi ürün olduğunu bilmeden fiyat ya da içerik söylenemez.
    """
    if tip == FIYAT:
        return ("Tabii, hemen söyleyeyim — hangi ürünümüz için soruyorsunuz? "
                "Adını yazarsanız güncel fiyatını ileteyim.")
    if tip == ICERIK:
        return ("Elbette, içeriğini paylaşayım. Hangi ürünümüzü "
                "soruyorsunuz acaba?")
    if tip == KULLANIM:
        return ("Memnuniyetle anlatayım. Hangi ürün için sormuştunuz?")
    return ("Merhaba, size yardımcı olayım. Hangi ürünümüzle ilgili "
            "bilgi istiyorsunuz?")


def cevap_uret(mesaj: str, urun: UrunKarti | None, layer: Any,
               yaklasim: str = VARSAYILAN_YAKLASIM,
               ilk_cevap: bool = True, max_tokens: int = 220) -> Cevap:
    """Bir müşteri mesajına cevap üretir ve mevzuat taramasından geçirir.

    `layer` jarvis.model_layer.ModelLayer örneği (yerel önce, gerekirse dış).
    Model çağrılamazsa cevap üretilmez — uydurma yedek metin DÖNMEZ, çünkü
    bu hattın tamamı "şablon değil" diye var.
    """
    tip = soru_tipi(mesaj)

    if urun is None:
        # Ürün bilinmiyor: fiyat/içerik söylenemez. Doğal biçimde sorulur.
        metin = _urun_sor(tip)
        inceleme = compliance.review(metin)
        return Cevap(metin=_ifsala(metin, ilk_cevap), soru_tipi=tip, urun=None,
                     yaklasim=yaklasim, olgular=[],
                     mevzuat="TEMIZ" if inceleme.clean else "INCELE",
                     bulgular=_bulgulari_cikar(inceleme),
                     gonderilebilir=inceleme.clean,
                     gerekce="urun bilinmiyor -> dogal soru")

    # Cevap için gereken olgu kartta yoksa model HİÇ çağrılmaz: modele
    # sorulan her boşluk uydurma riskidir ve bir kez gerçekten uyduruldu.
    eksik = eksik_olgu(tip, urun)
    if eksik:
        metin = (f"{urun.ad} için bu bilgiyi elimdeki kayıttan doğrulayamadım. "
                 "Yanlış bilgi vermemek için ilgili arkadaşıma aktarıyorum, "
                 "en kısa sürede size dönüş yapılacak.")
        return Cevap(metin=_ifsala(metin, ilk_cevap), soru_tipi=tip, urun=urun.ad,
                     yaklasim=yaklasim, olgular=urun.olgular(tip),
                     mevzuat="OLGU_EKSIK", gonderilebilir=False,
                     gerekce=f"kartta '{eksik}' bos -> insana aktarilir")

    olgular = urun.olgular(tip)
    # İÇERİK sorusunda modelden yalnız BİR çerçeve cümlesi istenir; bileşen
    # listesini kod, resmî beyan biçiminde ("İçindekiler: …") birebir ekler.
    #
    # NEDEN: Ölçüldü (20.09.2026) -- model listeyi düz yazıya gömünce
    # `compliance` "VIREON/FEMISIA bileşen tuzağı" kuralıyla BLOKLADI ve
    # doğru yaptı; aynı liste "İçindekiler:" başlığıyla temiz geçiyor
    # (`_is_ingredient_declaration`). Ayrıca bileşen beyanı zaten birebir
    # olmak zorunda -- modelin yeniden yazmasına hiçbir sebep yok.
    ek_beyan = ""
    liste_kirpildi = False
    if tip == ICERIK:
        ek_beyan = "İçindekiler: " + urun.icindekiler
        # 🔴 "liste ayrıca eklenecek" DEME: ölçüldü, model o cümleyi duyunca
        # yer tutucu bırakıyor -> "* [Buraya bileşen listesi eklenecektir]".
        # Listeden hiç söz ettirme; girişin kendi başına tam olması gerekir.
        yaklasim = (yaklasim + " Sadece tek cümlelik kısa bir giriş yaz. "
                    "Bileşen sayma, liste yazma, 'şunlardır' gibi listeye "
                    "giriş yapan ifade kullanma.")

    istem = SISTEM_YONERGESI.format(
        yaklasim=yaklasim.strip() + " " + DEGISMEZ_USLUP,
        olgular="\n".join("- " + o for o in olgular),
        soru=mesaj.strip(),
    )
    try:
        # escalate=True -> zincir DIŞ sağlayıcıyla başlar (ölçülmüş sıra:
        # gemini 1,0 s). Müşteriye giden metin için bilinçli tercih: yerel
        # 4B model ölçümde sen/siz karıştırdı ve soruyu tekrar etti; kusur
        # müşteriye görünür. Dış sağlayıcı düşerse zincir yerele iner.
        #
        # generate() -> (saglayici_cikti, katman, deneme_sayisi)
        sonuc, katman, _ = layer.generate(
            [{"role": "user", "content": istem}],
            max_tokens=max_tokens,
            escalate=True,
            # Kademe kaydi: musteriye giden metin -> muhakeme.
            is_anahtari="satis_dialog",
        )
    except Exception as exc:  # noqa: BLE001
        return Cevap(metin="", soru_tipi=tip, urun=urun.ad, yaklasim=yaklasim,
                     olgular=olgular, mevzuat="URETILEMEDI", gonderilebilir=False,
                     gerekce=f"model cagrilamadi: {str(exc)[:120]}")

    ham = (sonuc or {}).get("text") or ""
    metin = " ".join(str(ham).split())
    # Yarida kesilen cevap musteriye GITMEZ: cumlenin ortasinda biten bir
    # mesaj, yanlis mesajdan daha kotu gorunur.
    if (sonuc or {}).get("truncated"):
        return Cevap(metin=metin, soru_tipi=tip, urun=urun.ad, yaklasim=yaklasim,
                     olgular=olgular, mevzuat="KESIK", gonderilebilir=False,
                     model=(sonuc or {}).get("model"), model_calls=1,
                     gerekce="cevap token sinirinda yarida kesildi")
    if not metin:
        return Cevap(metin="", soru_tipi=tip, urun=urun.ad, yaklasim=yaklasim,
                     olgular=olgular, mevzuat="URETILEMEDI", gonderilebilir=False,
                     gerekce="model bos cevap dondu")

    # 🔴 LİSTE KAPISI — İÇERİK sorusunun en tehlikeli hatası
    # Ölçüldü (20.09.2026): "bileşen sayma" DENMESİNE RAĞMEN Gemini VIREON
    # için tamamen alakasız, genel bir kozmetik INCI listesi uydurdu
    # (Niacinamide, Panthenol, Ceteareth-25, Carbomer…). O sefer sayı kapısı
    # yakaladı, ama yalnızca "Ceteareth-25" içindeki 25 sayesinde --
    # yani ŞANS ESERİ. Sayısız bir uydurma liste sızabilirdi.
    #
    # Bu yüzden içerik sorusunda modelin metni bir LİSTE İÇEREMEZ: beyanı
    # kod ekliyor, modelin işi tek cümlelik giriş. İki virgülden fazlası
    # liste demektir.
    # Reddetmek yerine KIRPILIR: yoksa her içerik sorusu cevapsız kalırdı.
    # Modelin ilk cümlesi doğal bir giriştir; listesi varsa o cümlede değil,
    # sonrasındadır. İlk cümle de liste taşıyorsa nötr bir girişe düşülür --
    # burada şablona düşmek güvenli, çünkü cevabın ÖZÜ (beyan) zaten birebir.
    if tip == ICERIK:
        metin = _ilk_cumle(metin)
        if metin.count(",") > 2 or not metin:
            metin = f"{urun.ad} ürünümüzün içeriğini paylaşıyorum."
            liste_kirpildi = True

    # Yer tutucu kapısı: model "[buraya … eklenecek]" gibi bir boşluk
    # bırakırsa müşteriye yarım mesaj gider. Ölçüldü ve yaşandı.
    if _YER_TUTUCU.search(metin):
        return Cevap(metin=metin, soru_tipi=tip, urun=urun.ad, yaklasim=yaklasim,
                     olgular=olgular, mevzuat="YER_TUTUCU", gonderilebilir=False,
                     model=(sonuc or {}).get("model"), model_calls=1,
                     gerekce="model cevapta yer tutucu birakti")

    if ek_beyan:
        metin = f"{metin}\n\n{ek_beyan}"

    # Olgularda geçmeyen sayı = uydurma fiyat/oran/süre. Mevzuat taraması
    # bunu yakalamaz (o yasak iddia arar), bu yüzden ayrı kapı.
    kacak = uydurma_sayi(metin, olgular + ([ek_beyan] if ek_beyan else []))
    if kacak:
        return Cevap(metin=metin, soru_tipi=tip, urun=urun.ad, yaklasim=yaklasim,
                     olgular=olgular, mevzuat="UYDURMA_SAYI",
                     gonderilebilir=False, model=(sonuc or {}).get("model"),
                     model_calls=1,
                     gerekce="olgularda olmayan sayi: " + ", ".join(kacak[:4]))

    inceleme = compliance.review(metin)
    bloklu = any(f.label == "BLOCKED" for f in inceleme.findings)
    return Cevap(
        metin=_ifsala(metin, ilk_cevap),
        soru_tipi=tip, urun=urun.ad, yaklasim=yaklasim, olgular=olgular,
        mevzuat="TEMIZ" if inceleme.clean else ("BLOKLU" if bloklu else "INCELE"),
        bulgular=_bulgulari_cikar(inceleme),
        gonderilebilir=inceleme.clean,
        model=(sonuc or {}).get("model"),
        model_calls=1,
        gerekce=f"uretildi ({katman})"
                + (" | model liste yazdi, girise dusuldu" if liste_kirpildi else ""),
    )


_CUMLE_SONU = re.compile(r"(?<=[.!?])\s")


def _ilk_cumle(metin: str) -> str:
    parcalar = _CUMLE_SONU.split(metin.strip(), 1)
    return parcalar[0].strip() if parcalar else ""


def _ifsala(metin: str, ilk_cevap: bool) -> str:
    if not metin or not ilk_cevap:
        return metin
    return f"{metin}\n\n{IFSA_SATIRI}"


def _bulgulari_cikar(inceleme: Any) -> list[dict[str, str]]:
    cikti: list[dict[str, str]] = []
    for bulgu in getattr(inceleme, "findings", ())[:8]:
        cikti.append({
            "etiket": getattr(bulgu, "label", ""),
            "kural": getattr(bulgu, "rule", ""),
            "yakalanan": getattr(bulgu, "matched", ""),
        })
    return cikti
