"""Metin tekrar motoru (C05 kaniti).

DORT KATMAN -- ucu deterministik, biri gommeye bagli:
    1. birebir tekrar      -- ayni cumle
    2. n-gram tekrar       -- ayni kelime dizisi
    3. kalip tekrar        -- ayni sozdizimi iskeleti
    4. anlamsal tekrar     -- farkli kelimeler, ayni vaat  (GOMME GEREKIR)

NEDEN DORDUNCU KATMAN GEREKLI:
    OLCULDU: "yardimcı ol" 224 cumlenin 54'unde (%24). Yazar kelimeleri
    degistirerek n-gram olcumunden kacabilir; "cildi nemlendirir" ile
    "nem dengesini destekler" farkli n-gram, ayni vaattir. 36 urunun
    birbirinden ayristigi bu olcum olmadan DOGRULANAMAZ.

ZORUNLU TEKRAR OTOMATIK HATA DEGILDIR:
    Mevzuat geregi her urunde tekrarlanmasi gereken uyarilar vardir.
    Bunlar ayri tutulur ve tekrar sayimina GIRMEZ. Bu ayrim yapilmazsa
    motor dogru davranisi kusur sayar.

BAGIMLILIK: yalnizca stdlib. Anlamsal katman ISTEGE BAGLI ve
    cagiran tarafindan saglanan bir gomme islevine baglidir; yoksa
    durum SORAMADIM doner -- "tekrar yok" DEGIL.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass

# Mevzuat geregi tekrarlanan ifadeler -- tekrar sayimina GIRMEZ.
# Bu liste knowledge/catalog/16-regulatory/ altindan genisletilir.
ZORUNLU_KALIPLAR = (
    "cocuklarin ulasamayacagi",
    "goz ile temasindan kacininiz",
    "dis kullanim icindir",
    "hassasiyet durumunda kullanimi birakiniz",
    "alerjik reaksiyon durumunda doktora danisin",
    "yeni doganlarda doktor onerisi",
    "kullanmadan once test ediniz",
    "gunes koruyucu",
    "serin ve kuru yerde saklayiniz",
    "son kullanma tarihi",
)

CUMLE_AYIRICI = re.compile(r"(?<=[.!?…])\s+")
KELIME = re.compile(r"[0-9A-Za-zÀ-ÿĞğİıŞşÇçÖöÜü]+", re.UNICODE)


@dataclass(frozen=True)
class TekrarBulgusu:
    katman: str
    kalip: str
    gecen_urun: tuple[str, ...]
    gecis_sayisi: int
    oran: float

    def sozluk(self) -> dict:
        d = asdict(self)
        d["gecen_urun"] = list(self.gecen_urun)
        return d


# --- normalizasyon -------------------------------------------------------

def _sadelestir(metin: str) -> str:
    """Kucuk harf + diakritik sadelestirme. Turkce 'I/i' tuzagi icin
    once ozel eslemeler yapilir."""
    metin = (metin.replace("İ", "i").replace("I", "ı")
             .replace("Ş", "ş").replace("Ğ", "ğ").replace("Ç", "ç")
             .replace("Ö", "ö").replace("Ü", "ü"))
    metin = metin.lower()
    ayrik = unicodedata.normalize("NFD", metin)
    return "".join(k for k in ayrik if unicodedata.category(k) != "Mn")


def kelimeler(metin: str) -> list[str]:
    return KELIME.findall(_sadelestir(metin))


def cumleler(metin: str) -> list[str]:
    return [c.strip() for c in CUMLE_AYIRICI.split(metin or "") if c.strip()]


def zorunlu_mu(cumle: str, kaliplar=ZORUNLU_KALIPLAR) -> bool:
    s = _sadelestir(cumle)
    return any(k in s for k in kaliplar)


# --- katmanlar -----------------------------------------------------------

def birebir_tekrar(metinler: dict[str, str]) -> list[TekrarBulgusu]:
    """Ayni cumlenin birden fazla urunde gecmesi."""
    sahipler: dict[str, set[str]] = {}
    for urun, metin in metinler.items():
        for c in cumleler(metin):
            if zorunlu_mu(c):
                continue
            anahtar = " ".join(kelimeler(c))
            if len(anahtar.split()) < 4:
                continue
            sahipler.setdefault(anahtar, set()).add(urun)
    toplam = max(len(metinler), 1)
    return sorted(
        (TekrarBulgusu("birebir", a, tuple(sorted(u)), len(u), round(len(u) / toplam, 4))
         for a, u in sahipler.items() if len(u) > 1),
        key=lambda b: -b.gecis_sayisi)


def ngram_tekrar(metinler: dict[str, str], n: int = 3,
                 asgari_urun: int = 3) -> list[TekrarBulgusu]:
    """n kelimelik dizilerin kac urunde gectigi."""
    sahipler: dict[str, set[str]] = {}
    for urun, metin in metinler.items():
        k = kelimeler(metin)
        for i in range(len(k) - n + 1):
            sahipler.setdefault(" ".join(k[i:i + n]), set()).add(urun)
    toplam = max(len(metinler), 1)
    return sorted(
        (TekrarBulgusu("ngram%d" % n, a, tuple(sorted(u)), len(u), round(len(u) / toplam, 4))
         for a, u in sahipler.items() if len(u) >= asgari_urun),
        key=lambda b: -b.gecis_sayisi)


def kalip_tekrar(metinler: dict[str, str], asgari_urun: int = 3) -> list[TekrarBulgusu]:
    """Cumle iskeleti tekrari: sayilar ve ozel adlar yerine yer tutucu."""
    sahipler: dict[str, set[str]] = {}
    for urun, metin in metinler.items():
        for c in cumleler(metin):
            if zorunlu_mu(c):
                continue
            k = kelimeler(c)
            if len(k) < 5:
                continue
            # ilk ve son ucer kelimeyi koru, ortayi uzunluga indirge
            iskelet = " ".join(k[:3]) + " <%d> " % (len(k) - 6) + " ".join(k[-3:])
            sahipler.setdefault(iskelet, set()).add(urun)
    toplam = max(len(metinler), 1)
    return sorted(
        (TekrarBulgusu("kalip", a, tuple(sorted(u)), len(u), round(len(u) / toplam, 4))
         for a, u in sahipler.items() if len(u) >= asgari_urun),
        key=lambda b: -b.gecis_sayisi)


def anlamsal_tekrar(metinler: dict[str, str], gomme_islevi=None,
                    esik: float = 0.86) -> dict:
    """Farkli kelimelerle ayni vaadi arar.

    DURUM AYRIMI: gomme islevi verilmediyse SORAMADIM doner.
    'Tekrar yok' ile 'bakamadim' ayni sey DEGILDIR."""
    if gomme_islevi is None:
        return {"durum": "SORAMADIM",
                "sebep": "gomme islevi saglanmadi -- anlamsal katman calismadi",
                "ciftler": []}
    anahtarlar = sorted(metinler)
    try:
        vektorler = [gomme_islevi(metinler[a]) for a in anahtarlar]
    except Exception as hata:                        # noqa: BLE001
        return {"durum": "OKUNAMADI",
                "sebep": "%s: %s" % (hata.__class__.__name__, hata),
                "ciftler": []}

    def kosinus(a, b):
        nokta = sum(x * y for x, y in zip(a, b, strict=False))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return nokta / (na * nb) if na and nb else 0.0

    ciftler = []
    for i in range(len(anahtarlar)):
        for j in range(i + 1, len(anahtarlar)):
            b = kosinus(vektorler[i], vektorler[j])
            if b >= esik:
                ciftler.append({"urunler": [anahtarlar[i], anahtarlar[j]],
                                "benzerlik": round(b, 4)})
    ciftler.sort(key=lambda c: -c["benzerlik"])
    return {"durum": "OK", "esik": esik, "cift_sayisi": len(ciftler),
            "ciftler": ciftler[:60]}


# --- birlesik kanit ------------------------------------------------------

def kanit(metinler: dict[str, str], gomme_islevi=None) -> dict:
    """Dort katmanli tekrar kaniti. YARGI ICERMEZ, esik dayatmaz."""
    birebir = birebir_tekrar(metinler)
    ngram = ngram_tekrar(metinler)
    kalip = kalip_tekrar(metinler)
    anlamsal = anlamsal_tekrar(metinler, gomme_islevi)

    tum_kelime = Counter()
    zorunlu_cumle = 0
    toplam_cumle = 0
    for metin in metinler.values():
        for c in cumleler(metin):
            toplam_cumle += 1
            if zorunlu_mu(c):
                zorunlu_cumle += 1
        tum_kelime.update(kelimeler(metin))

    return {
        "urun_sayisi": len(metinler),
        "toplam_cumle": toplam_cumle,
        "zorunlu_cumle": zorunlu_cumle,
        "birebir_tekrar": [b.sozluk() for b in birebir[:30]],
        "birebir_tekrar_sayisi": len(birebir),
        "ngram_tekrar": [b.sozluk() for b in ngram[:30]],
        "ngram_tekrar_sayisi": len(ngram),
        "kalip_tekrar": [b.sozluk() for b in kalip[:30]],
        "kalip_tekrar_sayisi": len(kalip),
        "anlamsal": anlamsal,
        "en_sik_kelimeler": tum_kelime.most_common(20),
    }

# --- kaynak ayiklama -----------------------------------------------------

BASLIK_SATIS = re.compile(r"^##+\s*Satı[sş]ta s[oö]ylenebilir", re.I | re.M)
BASLIK_HERHANGI = re.compile(r"^##+\s", re.M)
MADDE = re.compile(r"^[-*]\s+(.+)$", re.M)


def satis_cumleleri(md_metni: str) -> list[str]:
    """Urun bilgi dosyasindan YALNIZ satis cumlelerini ayiklar.

    OLCULDU: tum dosyayi olcmek yaniltiyor -- on bilgi bloklari
    ('urun bilgisi anahtar', 'gizlilik ic bilgi', 'marj buna dayaniyor')
    36 dosyanin hepsinde ayni oldugu icin tekrar motoru bunlari
    buluyor, satis dilini degil. Tekrar olcumu satis cumleleri
    uzerinde yapilir."""
    m = BASLIK_SATIS.search(md_metni or "")
    if not m:
        return []
    kalan = md_metni[m.end():]
    sonraki = BASLIK_HERHANGI.search(kalan)
    bolum = kalan[:sonraki.start()] if sonraki else kalan
    return [x.strip() for x in MADDE.findall(bolum) if x.strip()]


def urun_metinleri(klasor, desen: str = "30-urun-*.md") -> dict[str, str]:
    """Klasordeki urun dosyalarindan satis metni sozlugu uretir."""
    import pathlib
    sonuc: dict[str, str] = {}
    for p in sorted(pathlib.Path(klasor).glob(desen)):
        cumleler_ = satis_cumleleri(p.read_text(encoding="utf-8"))
        if cumleler_:
            sonuc[p.stem.replace("30-urun-", "")] = " ".join(cumleler_)
    return sonuc
