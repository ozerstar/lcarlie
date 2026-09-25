"""Urun Varlik Siniflandiricisi (C07A) -- TYPE A korumasinin bulundugu yer.

NEDEN VAR:
    OLCULDU 25.09.2026 -- scripts/gorsel-kompozit.py:124-128 her gorseli
    kosulsuz rembg'e gonderiyor. Sinif kontrolu yok. Sonuc olculdu:
      varliklar/urun/ham   medyan genislik 1254 px
      varliklar/urun/kesim medyan genislik  299 px   (%76 kayip)

    Zaten sanat yonetimi gormus bir fotografi kesip jenerik sahneye
    koymak deger URETMEZ, deger YOK EDER. Bu modul once "kesmeli miyim"
    sorusunu sorar.

SINIFLAR:
    A  FINISHED EDITORIAL  -- urun + profesyonel arka plan + isik +
                             kompozisyon zaten tasarlanmis. VARSAYILAN: DOKUNMA.
    B  STUDIO              -- profesyonel cekim, sahne notr. Genisletilebilir.
    C  ISOLATED PACKSHOT   -- izole urun. Kompozit uygulanabilir.
    D  INSUFFICIENT        -- hedef yerlesim icin yetersiz. URETIM KAPISI FAIL.

YONTEM SIRASI (sartname geregi):
    1. Deterministik olcum (piksel, DPI, en/boy)
    2. CV kaniti (kenar yogunlugu, maske, gradyan, golge, parlama)
    3. Vision -- YALNIZ ikinci katman, ve yalniz kararsiz kalinirsa.
       Bu surumde vision BAGLI DEGIL; `vision_gerekli` bayragi uretir.

BAGIMLILIK: Pillow + numpy (ikisi de kurulu). Yeni bagimlilik YOK.
"""

from __future__ import annotations

import pathlib
from dataclasses import asdict, dataclass

from jarvis import katalog_gorsel_olcum as olcum

# --- izin matrisi --------------------------------------------------------
# TYPE A icin yasaklar sartnameden birebir gelir.

IZIN: dict[str, dict[str, tuple[str, ...]]] = {
    "A": {
        "izinli": (
            "non_destructive_page_placement",
            "careful_whole_image_crop_where_justified",
            "color_managed_placement",
            "layout_derived_from_photograph",
        ),
        "yasak": (
            "background_removal",
            "automatic_crop_to_product",
            "product_regeneration",
            "label_regeneration",
            "background_replacement",
            "geometry_modification",
        ),
    },
    "B": {
        "izinli": (
            "controlled_canvas_extension",
            "controlled_background_extension",
            "controlled_compositing",
            "shadow_reinforcement",
            "color_managed_placement",
            "non_destructive_page_placement",
        ),
        "yasak": (
            "product_regeneration",
            "label_regeneration",
            "geometry_modification",
            "relighting_of_product",
        ),
    },
    "C": {
        "izinli": (
            "background_removal",
            "compositing_into_new_scene",
            "contact_shadow_generation",
            "color_managed_placement",
            "non_destructive_page_placement",
        ),
        "yasak": (
            "product_regeneration",
            "label_regeneration",
            "geometry_modification",
        ),
    },
    "D": {
        "izinli": (),
        "yasak": (
            "any_placement",
            "upscaling_to_pass_gate",
            "silent_downscale_and_use",
        ),
    },
}

# Karar esikleri. Hepsi adlandirilmis ve tek yerde.
ESIK = {
    "alfa_seffaf_orani": 0.15,      # bunun ustu = zaten kesilmis
    "arka_plan_karmasikligi": 0.055,  # kenar bandi doku/kenar enerjisi
    "konu_orani_ust": 0.62,          # urun kareyi doldurmuyorsa editoryal olabilir
    "merkez_sapmasi": 0.08,          # normalize merkez kaymasi
    "negatif_alan": 0.28,            # sakin alan orani
    "golge_gradyani": 0.035,         # taban bolgesi koyulasma
    "parlama_orani": 0.0015,         # kucuk, parlak, doygunlugu dusuk bolgeler
    # Kusursuz duz fon (dikissiz studyo kagidi) da "sakin alan" uretir.
    # Kasitli negatif alan sayilmasi icin zeminin bir yapisi olmali.
    "zemin_tabani": 0.012,
    "editoryal_sinyal_sayisi": 3,    # 5 sinyalden kaci gerekli
}


@dataclass(frozen=True)
class Sinyaller:
    alfa_seffaf_orani: float | None
    arka_plan_karmasikligi: float | None
    konu_orani: float | None
    merkez_sapmasi: float | None
    negatif_alan_orani: float | None
    golge_gradyani: float | None
    parlama_orani: float | None
    kenara_degiyor: bool | None
    baskin_renk_sayisi: int | None

    def sozluk(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Siniflandirma:
    asset_type: str
    confidence: float
    evidence: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    forbidden_operations: tuple[str, ...]
    signals: dict
    source_quality: dict
    placement_quality: dict | None
    max_safe_placement_mm: tuple[float, float]
    vision_gerekli: bool
    okunamadi: str | None = None

    def sozluk(self) -> dict:
        d = asdict(self)
        d["evidence"] = list(self.evidence)
        d["allowed_operations"] = list(self.allowed_operations)
        d["forbidden_operations"] = list(self.forbidden_operations)
        return d


# --- sinyal cikarimi -----------------------------------------------------

def _yukle(yol):
    from PIL import Image
    im = Image.open(yol)
    im.load()
    return im


def _kucult(im, azami=512):
    from PIL import Image
    if max(im.size) <= azami:
        return im
    oran = azami / max(im.size)
    return im.resize((max(1, int(im.width * oran)), max(1, int(im.height * oran))),
                     Image.BILINEAR)


def sinyaller(yol: str | pathlib.Path) -> Sinyaller:
    """Gorselden CV kanitlarini cikarir. numpy yoksa alanlar None doner."""
    try:
        import numpy as np
    except ImportError:                       # pragma: no cover
        return Sinyaller(None, None, None, None, None, None, None, None, None)

    im = _kucult(_yukle(yol))
    en, boy = im.size

    # --- alfa
    alfa_oran = None
    maske = None
    if "A" in im.mode:
        a = np.asarray(im.convert("RGBA").split()[-1], dtype="float32") / 255.0
        alfa_oran = float((a < 0.5).mean())
        maske = a >= 0.5

    rgb = np.asarray(im.convert("RGB"), dtype="float32") / 255.0
    gri = rgb.mean(axis=2)

    # --- konu maskesi (alfa yoksa kenar rengi farkiyla kestir)
    if maske is None:
        bant = max(2, int(min(en, boy) * 0.04))
        kenar_pikselleri = np.concatenate([
            rgb[:bant].reshape(-1, 3), rgb[-bant:].reshape(-1, 3),
            rgb[:, :bant].reshape(-1, 3), rgb[:, -bant:].reshape(-1, 3),
        ])
        zemin = np.median(kenar_pikselleri, axis=0)
        fark = np.sqrt(((rgb - zemin) ** 2).sum(axis=2))
        maske = fark > 0.18
    konu_oran = float(maske.mean())

    # --- arka plan karmasikligi: kenar bandinda gradyan + doku
    bant = max(2, int(min(en, boy) * 0.10))
    kenar_gri = np.concatenate([
        gri[:bant].ravel(), gri[-bant:].ravel(),
        gri[:, :bant].ravel(), gri[:, -bant:].ravel(),
    ])
    gx = np.abs(np.diff(gri, axis=1)).mean() if gri.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(gri, axis=0)).mean() if gri.shape[0] > 1 else 0.0
    ap_karmasiklik = float(kenar_gri.std() * 0.5 + (gx + gy) * 0.5)

    # --- merkez sapmasi
    if maske.any():
        ys, xs = np.nonzero(maske)
        cx, cy = xs.mean() / max(en - 1, 1), ys.mean() / max(boy - 1, 1)
        merkez_sap = float(((cx - 0.5) ** 2 + (cy - 0.5) ** 2) ** 0.5 * 2.0)
        kenara_degiyor = bool(
            maske[0].any() or maske[-1].any() or maske[:, 0].any() or maske[:, -1].any())
    else:
        merkez_sap, kenara_degiyor = 0.0, False

    # --- negatif alan: dusuk yerel varyansli, konu disi alan
    blok = max(4, min(en, boy) // 24)
    h, w = (boy // blok) * blok, (en // blok) * blok
    if h >= blok and w >= blok:
        parca = gri[:h, :w].reshape(h // blok, blok, w // blok, blok)
        yerel_std = parca.std(axis=(1, 3))
        konu_parca = maske[:h, :w].reshape(h // blok, blok, w // blok, blok).mean(axis=(1, 3))
        sakin = (yerel_std < 0.035) & (konu_parca < 0.10)
        negatif = float(sakin.mean())
    else:
        negatif = 0.0

    # --- golge: konu alt sinirinin hemen altinda koyulasma
    golge = 0.0
    if maske.any():
        ys, _ = np.nonzero(maske)
        alt = int(ys.max())
        pencere = max(3, boy // 20)
        if alt + 1 < boy:
            altbant = gri[alt + 1:min(boy, alt + 1 + pencere)]
            uzak = gri[min(boy - 1, alt + 1 + pencere):]
            if altbant.size and uzak.size:
                golge = float(max(0.0, uzak.mean() - altbant.mean()))

    # --- parlama: YALNIZ KONU ICINDE, ve yalniz KUCUK bolgelerde.
    # OLCULDU: konu disini de sayinca duz beyaz studyo fonu 0.86 veriyor
    # ve her packshot editoryal gorunuyordu. Parlama urunun uzerinde olur.
    enb = rgb.max(axis=2)
    enk = rgb.min(axis=2)
    doygunluk = np.where(enb > 0, (enb - enk) / np.maximum(enb, 1e-6), 0.0)
    parlak = (gri > 0.92) & (doygunluk < 0.20) & maske
    konu_piksel = float(maske.sum())
    parlama = float(parlak.sum() / konu_piksel) if konu_piksel else 0.0
    # Konunun yarisindan fazlasi "parlama" ise bu parlama degil, beyaz govdedir.
    if parlama > 0.50:
        parlama = 0.0

    # --- baskin renk sayisi (kaba palet genisligi)
    kucuk = _kucult(im.convert("RGB"), 96)
    nicel = kucuk.quantize(colors=16, method=2)
    sayimlar = sorted((s for s, _ in nicel.getcolors(4096) or []), reverse=True)
    toplam = sum(sayimlar) or 1
    birikim, baskin = 0, 0
    for s in sayimlar:
        birikim += s
        baskin += 1
        if birikim / toplam >= 0.85:
            break

    return Sinyaller(
        alfa_seffaf_orani=None if alfa_oran is None else round(alfa_oran, 4),
        arka_plan_karmasikligi=round(ap_karmasiklik, 4),
        konu_orani=round(konu_oran, 4),
        merkez_sapmasi=round(merkez_sap, 4),
        negatif_alan_orani=round(negatif, 4),
        golge_gradyani=round(golge, 4),
        parlama_orani=round(parlama, 6),
        kenara_degiyor=kenara_degiyor,
        baskin_renk_sayisi=baskin,
    )


# --- siniflandirma -------------------------------------------------------

def siniflandir(yol: str | pathlib.Path,
                hedef_en_mm: float | None = None,
                hedef_boy_mm: float | None = None) -> Siniflandirma:
    """Bir urun gorselini A/B/C/D olarak siniflandirir.

    Karar sirasi sartnamededir: once D elemesi (uretim kapisi),
    sonra C (zaten kesilmis), sonra A/B ayrimi."""
    kay = olcum.kaynak_kalite(yol)
    guvenli = olcum.azami_guvenli_yerlesim_mm(kay)

    if kay.okunamadi:
        return Siniflandirma(
            asset_type="D", confidence=1.0,
            evidence=("kaynak okunamadi: %s" % kay.okunamadi,),
            allowed_operations=IZIN["D"]["izinli"],
            forbidden_operations=IZIN["D"]["yasak"],
            signals={}, source_quality=kay.sozluk(), placement_quality=None,
            max_safe_placement_mm=guvenli, vision_gerekli=False,
            okunamadi=kay.okunamadi)

    yer = None
    if hedef_en_mm is not None and hedef_boy_mm is not None:
        yer = olcum.yerlesim_kalite(kay, hedef_en_mm, hedef_boy_mm)

    kanit: list[str] = []

    # --- 1. D elemesi: mutlak taban
    if kay.kisa_kenar < olcum.MUTLAK_TABAN_PX:
        kanit.append("kisa kenar %d px < mutlak taban %d px"
                     % (kay.kisa_kenar, olcum.MUTLAK_TABAN_PX))
        return Siniflandirma(
            "D", 1.0, tuple(kanit), IZIN["D"]["izinli"], IZIN["D"]["yasak"],
            {}, kay.sozluk(), yer.sozluk() if yer else None, guvenli, False)

    # --- 1b. D elemesi: hedef yerlesim icin yetersiz
    if yer is not None and not yer.gecti:
        kanit.append(yer.gerekce)
        kanit.append("buyutmeden azami yerlesim: %.1f x %.1f mm" % guvenli)
        return Siniflandirma(
            "D", 0.95, tuple(kanit), IZIN["D"]["izinli"], IZIN["D"]["yasak"],
            {}, kay.sozluk(), yer.sozluk(), guvenli, False)

    s = sinyaller(yol)
    if s.konu_orani is None:
        # numpy yok -- siniflandirma yapilamaz. DURUM AYRIMI: bilinmiyor.
        return Siniflandirma(
            "D", 0.0, ("sinyal cikarilamadi: numpy yok -- BILINMIYOR, kotu degil",),
            (), IZIN["D"]["yasak"], s.sozluk(), kay.sozluk(),
            yer.sozluk() if yer else None, guvenli, True)

    # --- 2. C: zaten kesilmis
    if s.alfa_seffaf_orani is not None and s.alfa_seffaf_orani >= ESIK["alfa_seffaf_orani"]:
        kanit.append("alfa seffaf orani %.2f >= %.2f -- varlik zaten izole"
                     % (s.alfa_seffaf_orani, ESIK["alfa_seffaf_orani"]))
        return Siniflandirma(
            "C", 0.92, tuple(kanit), IZIN["C"]["izinli"], IZIN["C"]["yasak"],
            s.sozluk(), kay.sozluk(), yer.sozluk() if yer else None, guvenli, False)

    # --- 3. A / B ayrimi: bes editoryal sinyal
    sinyal_sonuclari = [
        ("arka plan karmasik (%.3f >= %.3f)" % (s.arka_plan_karmasikligi, ESIK["arka_plan_karmasikligi"]),
         s.arka_plan_karmasikligi >= ESIK["arka_plan_karmasikligi"]),
        ("urun kareyi doldurmuyor (%.2f <= %.2f)" % (s.konu_orani, ESIK["konu_orani_ust"]),
         s.konu_orani <= ESIK["konu_orani_ust"]),
        ("kompozisyon merkez disi (%.3f >= %.3f) veya YAPILI zeminde kasitli "
         "negatif alan (%.2f >= %.2f ve zemin %.3f >= %.3f)"
         % (s.merkez_sapmasi, ESIK["merkez_sapmasi"], s.negatif_alan_orani,
            ESIK["negatif_alan"], s.arka_plan_karmasikligi, ESIK["zemin_tabani"]),
         s.merkez_sapmasi >= ESIK["merkez_sapmasi"]
         or (s.negatif_alan_orani >= ESIK["negatif_alan"]
             and s.arka_plan_karmasikligi >= ESIK["zemin_tabani"])),
        ("golge var (%.3f >= %.3f)" % (s.golge_gradyani, ESIK["golge_gradyani"]),
         s.golge_gradyani >= ESIK["golge_gradyani"]),
        ("parlama/yansima var (%.4f >= %.4f)" % (s.parlama_orani, ESIK["parlama_orani"]),
         s.parlama_orani >= ESIK["parlama_orani"]),
    ]
    saglanan = [ad for ad, tamam in sinyal_sonuclari if tamam]
    saglanmayan = [ad for ad, tamam in sinyal_sonuclari if not tamam]
    n = len(saglanan)

    kanit.extend("OK  " + ad for ad in saglanan)
    kanit.extend("--  " + ad for ad in saglanmayan)

    if n >= ESIK["editoryal_sinyal_sayisi"]:
        # Guven: sinyal fazlaligiyla artar ama 1.0'a asla ulasmaz.
        guven = round(min(0.90, 0.55 + 0.10 * (n - ESIK["editoryal_sinyal_sayisi"] + 1)), 3)
        kanit.append("%d/5 editoryal sinyal -> TYPE A. VARSAYILAN DAVRANIS: DOKUNMA." % n)
        return Siniflandirma(
            "A", guven, tuple(kanit), IZIN["A"]["izinli"], IZIN["A"]["yasak"],
            s.sozluk(), kay.sozluk(), yer.sozluk() if yer else None, guvenli,
            vision_gerekli=(n == ESIK["editoryal_sinyal_sayisi"]))

    guven = round(min(0.85, 0.55 + 0.10 * (ESIK["editoryal_sinyal_sayisi"] - 1 - n)), 3)
    kanit.append("%d/5 editoryal sinyal -> TYPE B (notr sahne)." % n)
    return Siniflandirma(
        "B", guven, tuple(kanit), IZIN["B"]["izinli"], IZIN["B"]["yasak"],
        s.sozluk(), kay.sozluk(), yer.sozluk() if yer else None, guvenli,
        vision_gerekli=(n == ESIK["editoryal_sinyal_sayisi"] - 1))


# --- islem kapisi --------------------------------------------------------

class VarlikIhlali(Exception):
    """Sinifin yasakladigi islem denendi. HARD_REJECT."""


def islem_izinli_mi(sinif: Siniflandirma, islem: str) -> bool:
    return islem in sinif.allowed_operations


def islemi_dogrula(sinif: Siniflandirma, islem: str) -> None:
    """Yasak islemde istisna firlatir -- bu, C07A'nin HARD_REJECT yetkisidir."""
    if islem in sinif.forbidden_operations:
        raise VarlikIhlali(
            "TYPE %s varlikta yasak islem: %s -- gerekce: %s"
            % (sinif.asset_type, islem,
               sinif.evidence[0] if sinif.evidence else "sinif karari"))
    if islem not in sinif.allowed_operations:
        raise VarlikIhlali(
            "TYPE %s varlik icin tanimsiz islem: %s -- izinli olmayan islem "
            "varsayilan olarak reddedilir" % (sinif.asset_type, islem))
