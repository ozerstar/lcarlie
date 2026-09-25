"""Urun Butunlugu Muhafizi (C12) -- ASILAMAZ VETO.

BU MODUL YARGI ICERMEZ VE HICBIR MODELE SORMAZ.
    Tek soru: sayfadaki urun, gercek urunden farkli mi?
    Estetik degerlendirme rol 10'un isidir ve buraya AIT DEGILDIR.

KOKEN ZINCIRI:
    Her varlik uzerinde yapilan islem kaydedilir. Bir urun pikseli
    uretken modelden GECTIYSE bu zincirde iz birakir ve veto HARD_FAIL
    verir. Kayit yoksa durum BILINMIYOR'dur -- 'temiz' DEGIL.

    "Kanit yoksa gecer" bu kapida GECERSIZDIR: kanit yoksa gecmez.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import asdict, dataclass, field

from jarvis import katalog_renk as renk

# Urun pikseline dokunmasi YASAK islemler. Zincirde gorunurse HARD_FAIL.
URETKEN_ISLEMLER = (
    "diffusion",
    "inpaint",
    "outpaint_over_product",
    "product_regeneration",
    "label_regeneration",
    "generative_fill",
    "generative_upscale",
    "relight_product",
)

# Geometriyi bozan islemler.
GEOMETRI_ISLEMLERI = (
    "non_uniform_scale",
    "perspective_warp",
    "skew",
    "liquify",
)

ESIK = {
    "en_boy_sapmasi": 0.005,      # %0,5
    "govde_delta_e": 3.0,         # algisal olarak fark edilir sinir
    "etiket_delta_e": 2.0,        # etiket bolgesi daha siki
}


@dataclass
class KokenAdimi:
    islem: str
    arac: str
    zaman: str
    girdi_ozeti: str
    cikti_ozeti: str
    not_: str = ""

    def sozluk(self) -> dict:
        d = asdict(self)
        d["not"] = d.pop("not_")
        return d


@dataclass
class Koken:
    varlik: str
    kaynak_ozeti: str
    adimlar: list[KokenAdimi] = field(default_factory=list)

    def ekle(self, islem: str, arac: str, zaman: str,
             girdi_ozeti: str, cikti_ozeti: str, not_: str = "") -> None:
        self.adimlar.append(KokenAdimi(islem, arac, zaman, girdi_ozeti,
                                       cikti_ozeti, not_))

    def sozluk(self) -> dict:
        return {"varlik": self.varlik, "kaynak_ozeti": self.kaynak_ozeti,
                "adimlar": [a.sozluk() for a in self.adimlar]}

    @classmethod
    def sozlukten(cls, veri: dict) -> "Koken":
        k = cls(veri["varlik"], veri["kaynak_ozeti"])
        for a in veri.get("adimlar", []):
            k.ekle(a["islem"], a.get("arac", ""), a.get("zaman", ""),
                   a.get("girdi_ozeti", ""), a.get("cikti_ozeti", ""),
                   a.get("not", ""))
        return k


def dosya_ozeti(yol: str | pathlib.Path, blok: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        while True:
            parca = f.read(blok)
            if not parca:
                break
            h.update(parca)
    return h.hexdigest()


def koken_yaz(koken: Koken, yol: str | pathlib.Path) -> None:
    pathlib.Path(yol).write_text(
        json.dumps(koken.sozluk(), ensure_ascii=False, indent=1), encoding="utf-8")


def koken_oku(yol: str | pathlib.Path) -> Koken | None:
    p = pathlib.Path(yol)
    if not p.is_file():
        return None
    try:
        return Koken.sozlukten(json.loads(p.read_text(encoding="utf-8")))
    except Exception:                                # noqa: BLE001
        return None


# --- olcumler ------------------------------------------------------------

def _boyut(yol):
    from PIL import Image
    with Image.open(yol) as im:
        return im.size


def en_boy_sapmasi(kaynak_yolu, yerlesmis_yolu) -> float:
    ke, kb = _boyut(kaynak_yolu)
    ye, yb = _boyut(yerlesmis_yolu)
    if kb == 0 or yb == 0:
        return float("inf")
    a, b = ke / kb, ye / yb
    return abs(a - b) / max(a, 1e-9)


def govde_rengi(yol, ortalama_bolge: float = 0.5) -> tuple[int, int, int] | None:
    """Merkezi bolgenin medyan rengi -- urun govdesinin vekili."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:                              # pragma: no cover
        return None
    with Image.open(yol) as im:
        im = im.convert("RGB")
        en, boy = im.size
        de, db = int(en * ortalama_bolge), int(boy * ortalama_bolge)
        kutu = ((en - de) // 2, (boy - db) // 2, (en + de) // 2, (boy + db) // 2)
        k = np.asarray(im.crop(kutu), dtype="float32").reshape(-1, 3)
    return tuple(int(v) for v in np.median(k, axis=0))


# --- veto ----------------------------------------------------------------

@dataclass(frozen=True)
class ButunlukKarari:
    karar: str                      # GECER | DURDUR | BILINMIYOR
    ihlaller: tuple[str, ...]
    olcumler: dict
    asilabilir: bool = False        # HER ZAMAN False -- sozlesme geregi

    def sozluk(self) -> dict:
        d = asdict(self)
        d["ihlaller"] = list(self.ihlaller)
        return d


def dogrula(kaynak_yolu: str | pathlib.Path,
            yerlesmis_yolu: str | pathlib.Path,
            koken: Koken | None = None,
            etiket_bolgesi_rengi: tuple[int, int, int] | None = None,
            esikler: dict | None = None) -> ButunlukKarari:
    """Urun butunlugu vetosu.

    KOKEN YOKSA 'BILINMIYOR' DONER, 'GECER' DEGIL. Kanitsiz gecis yok."""
    e = dict(ESIK)
    if esikler:
        e.update(esikler)

    ihlaller: list[str] = []
    olcumler: dict = {}

    # --- 1. koken zinciri
    if koken is None:
        return ButunlukKarari(
            "BILINMIYOR",
            ("koken kaydi yok -- urun pikselinin uretken modelden gecip "
             "gecmedigi DOGRULANAMIYOR; kanitsiz gecis verilmez",),
            {"koken": None})

    yasak = [a.islem for a in koken.adimlar if a.islem in URETKEN_ISLEMLER]
    if yasak:
        ihlaller.append("uretken islem urun pikseline uygulanmis: %s"
                        % ", ".join(sorted(set(yasak))))
    geometri = [a.islem for a in koken.adimlar if a.islem in GEOMETRI_ISLEMLERI]
    if geometri:
        ihlaller.append("geometri bozan islem: %s" % ", ".join(sorted(set(geometri))))
    olcumler["koken_adim_sayisi"] = len(koken.adimlar)
    olcumler["koken_islemleri"] = [a.islem for a in koken.adimlar]

    # --- 2. kaynak ozeti degismis mi
    try:
        guncel = dosya_ozeti(kaynak_yolu)
    except OSError as hata:
        return ButunlukKarari("BILINMIYOR",
                              ("kaynak okunamadi: %s" % hata.__class__.__name__,),
                              olcumler)
    olcumler["kaynak_ozeti_esit"] = (guncel == koken.kaynak_ozeti)
    if koken.kaynak_ozeti and guncel != koken.kaynak_ozeti:
        ihlaller.append("kaynak dosya kokende kayitli ozetle eslesmiyor")

    # --- 3. en/boy orani
    try:
        sapma = en_boy_sapmasi(kaynak_yolu, yerlesmis_yolu)
    except Exception as hata:                        # noqa: BLE001
        return ButunlukKarari("BILINMIYOR",
                              ("olcu okunamadi: %s" % hata.__class__.__name__,),
                              olcumler)
    olcumler["en_boy_sapmasi"] = round(sapma, 5)
    if sapma > e["en_boy_sapmasi"]:
        ihlaller.append("en/boy orani sapmasi %.4f > %.4f"
                        % (sapma, e["en_boy_sapmasi"]))

    # --- 4. govde rengi
    k_renk = govde_rengi(kaynak_yolu)
    y_renk = govde_rengi(yerlesmis_yolu)
    if k_renk and y_renk:
        dE = renk.rgb_delta_e(k_renk, y_renk)
        olcumler["govde_delta_e"] = round(dE, 3)
        olcumler["govde_rgb"] = {"kaynak": list(k_renk), "yerlesmis": list(y_renk)}
        if dE > e["govde_delta_e"]:
            ihlaller.append("govde rengi dE %.2f > %.2f" % (dE, e["govde_delta_e"]))
    else:
        olcumler["govde_delta_e"] = None

    # --- 5. etiket bolgesi (verilmisse)
    if etiket_bolgesi_rengi and y_renk:
        dEe = renk.rgb_delta_e(etiket_bolgesi_rengi, y_renk)
        olcumler["etiket_delta_e"] = round(dEe, 3)
        if dEe > e["etiket_delta_e"]:
            ihlaller.append("etiket bolgesi dE %.2f > %.2f" % (dEe, e["etiket_delta_e"]))

    return ButunlukKarari("DURDUR" if ihlaller else "GECER",
                          tuple(ihlaller), olcumler)


class ButunlukIhlali(Exception):
    """Asilamaz veto. Uretim burada durur."""


def kapi(*args, **kw) -> ButunlukKarari:
    """Veto kapisi: GECER disinda her sonuc istisna firlatir.

    BILINMIYOR da gecmez -- kanitsiz urun baskiya gitmez."""
    karar = dogrula(*args, **kw)
    if karar.karar != "GECER":
        raise ButunlukIhlali("%s -- %s" % (karar.karar, " | ".join(karar.ihlaller)))
    return karar
