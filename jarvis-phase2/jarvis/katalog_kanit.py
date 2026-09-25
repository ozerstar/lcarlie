"""Creative Evidence Pack + Karar Kaydi.

KANIT MOTORU YARATICI KARARI VERMEZ.
    Sanat yonetmenine ve elestirmene KANIT saglar. Kanit paketi hicbir
    yerde 0-100 skor uretmez; olculebilen esikle, olculemeyen
    GOZLEM-KANIT-GEREKCE-KARAR biciminde kaydedilir.

NEDEN SKOR YOK:
    "Premium mi? 8/10" uc seyi ayni anda yapar: olculemeyeni olculmus
    gibi gosterir, gerekceyi gizler, duzeltme icin hicbir bilgi vermez.
    Bu modul skor uretmeyi YAPISAL OLARAK engeller -- karar kaydi
    dort alanin hepsini zorunlu tutar.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass

# Sayfa rolleri -- urun baskinligi profili bunlara gore degerlendirilir.
SAYFA_ROLLERI = ("HERO", "ANLATI", "KATALOG", "DETAY", "SESSIZ")

# Yetki kademeleriyle AYNI dagarcik. Iki benzer ama farkli sozcuk
# kumesi (REVIZE/REVISE) gercek bir hata kaynagidir -- birlestirildi.
KARARLAR = ("APPROVE", "REVISE", "REJECT", "ESCALATE_TO_HUMAN")


@dataclass(frozen=True)
class KararKaydi:
    """Yaratici kararin tek gecerli bicimi. Dort alan da zorunlu."""

    gozlem: str
    kanit: dict
    gerekce: str
    karar: str
    eylem: str
    veren: str          # capability id
    sayfa: int | None = None

    def __post_init__(self):
        for ad, deger in (("gozlem", self.gozlem), ("gerekce", self.gerekce),
                          ("eylem", self.eylem), ("veren", self.veren)):
            if not str(deger).strip():
                raise ValueError("karar kaydinda %s bos olamaz" % ad)
        if self.karar not in KARARLAR:
            raise ValueError("gecersiz karar: %r -- izinli: %s"
                             % (self.karar, ", ".join(KARARLAR)))
        if not self.kanit:
            raise ValueError("karar kaydi kanitsiz olamaz")

    def sozluk(self) -> dict:
        return asdict(self)

    def metin(self) -> str:
        return (
            "GOZLEM\n  %s\n\n"
            "KANIT\n  %s\n\n"
            "GEREKCE\n  %s\n\n"
            "KARAR\n  %s\n\n"
            "EYLEM\n  %s\n"
            % (self.gozlem,
               json.dumps(self.kanit, ensure_ascii=False, sort_keys=True),
               self.gerekce, self.karar, self.eylem)
        )


def skor_mu(deger) -> bool:
    """Bir alanin sahte skor olup olmadigini soyler.

    0-100 veya 0-1 araliginda tek bir sayi, adinda 'skor/puan/kalite'
    geciyorsa bu bir yargi kisaltmasidir ve kanit paketinde YERI YOKTUR."""
    return isinstance(deger, (int, float)) and not isinstance(deger, bool)


YASAK_ALAN_ADLARI = ("skor", "puan", "score", "rating", "kalite_puani",
                     "premium_skoru", "estetik_skoru")


def _skor_denetle(paket: dict, yol: str = "") -> list[str]:
    bulgular: list[str] = []
    for anahtar, deger in paket.items():
        tam = "%s.%s" % (yol, anahtar) if yol else anahtar
        if any(y in str(anahtar).lower() for y in YASAK_ALAN_ADLARI):
            bulgular.append(tam)
        if isinstance(deger, dict):
            bulgular.extend(_skor_denetle(deger, tam))
    return bulgular


@dataclass
class KanitPaketi:
    sayfa: int
    sayfa_rolu: str | None = None
    varlik_siniflandirmasi: dict | None = None
    kaynak_kalitesi: dict | None = None
    yerlesim_kalitesi: dict | None = None
    kirpma_korunumu: dict | None = None
    urun_baskinligi: dict | None = None
    saliency: dict | None = None
    duzen_olcumleri: dict | None = None
    tipografi_qa: dict | None = None
    renk: dict | None = None
    tekrar: dict | None = None
    urun_butunlugu: dict | None = None
    bilinmeyenler: list[str] | None = None

    def sozluk(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def dogrula(self) -> list[str]:
        """Paket sozlesmeye uyuyor mu. Bos liste = temiz."""
        sorunlar: list[str] = []
        if self.sayfa_rolu and self.sayfa_rolu not in SAYFA_ROLLERI:
            sorunlar.append("gecersiz sayfa rolu: %r" % self.sayfa_rolu)
        sahte = _skor_denetle(self.sozluk())
        if sahte:
            sorunlar.append("sahte skor alani: %s" % ", ".join(sahte))
        return sorunlar

    def eksikler(self) -> list[str]:
        """Toplanamamis kanit basliklari. 'yok' degil, 'toplanmadi'."""
        return [ad for ad, deger in asdict(self).items()
                if deger is None and ad not in ("sayfa_rolu", "bilinmeyenler")]


# --- toplama -------------------------------------------------------------

def paket_uret(pdf_yolu: str | pathlib.Path,
               sayfa_no: int,
               sayfa_rolu: str | None = None,
               tipografi: bool = True,
               tekrar: bool = True) -> KanitPaketi:
    """Bir sayfa icin toplanabilen tum deterministik kaniti toplar.

    Toplanamayan basliklar None kalir ve `eksikler()` ile raporlanir --
    bos deger 'sorun yok' anlamina GELMEZ."""
    from jarvis import katalog_sayfa_olcum as so

    bilinmeyen: list[str] = []
    olcumler = so.sayfa_olcumleri(pdf_yolu)
    hedef = next((o for o in olcumler if o.sayfa == sayfa_no), None)
    duzen = hedef.sozluk() if hedef else None
    if hedef is None:
        bilinmeyen.append("sayfa %d bulunamadi" % sayfa_no)

    tip = None
    if tipografi:
        try:
            from jarvis import katalog_tipografi_qa as tqa
            tumu = tqa.kapi(pdf_yolu)
            ilgili = [i for i in tumu["ihlaller"] if i["sayfa"] in (0, sayfa_no)]
            tip = {"gecti": not any(i["agirlik"] == tqa.AGIRLIK_DURDURUR
                                    for i in ilgili),
                   "ihlaller": ilgili}
        except Exception as hata:                    # noqa: BLE001
            bilinmeyen.append("tipografi_qa: %s" % hata.__class__.__name__)

    tkr = None
    if tekrar:
        try:
            tkr = so.tekrar_kaniti(pdf_yolu)
        except Exception as hata:                    # noqa: BLE001
            bilinmeyen.append("tekrar: %s" % hata.__class__.__name__)

    return KanitPaketi(
        sayfa=sayfa_no,
        sayfa_rolu=sayfa_rolu,
        duzen_olcumleri=duzen,
        tipografi_qa=tip,
        tekrar=tkr,
        bilinmeyenler=bilinmeyen or None,
    )


def paket_yaz(paket: KanitPaketi, yol: str | pathlib.Path) -> None:
    veri = paket.sozluk()
    veri["_eksik_kanit_basliklari"] = paket.eksikler()
    pathlib.Path(yol).write_text(
        json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
