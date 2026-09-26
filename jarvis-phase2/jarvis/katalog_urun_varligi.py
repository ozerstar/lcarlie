"""PRODUCT PROMINENCE -- on ayri olcum. TEK SAHTE SKOR URETILMEZ.

V2'nin hatasi: "ortalama fotograf alani %22,2" tek basina urun
varligi sanildi. PHOTO AREA != PRODUCT PRESENCE. Bir sayfada fotograf
kucuk ama urun net, izole ve kontrastli olabilir; ya da fotograf tam
tasma ama urun kadrajin icinde kaybolabilir.

Olcumler creative EVIDENCE'tir; karar ECD + Independent Critic'indir.
"""
from __future__ import annotations

SAYFA = 216.0
TRIM = 210.0


def _kesisim(a: tuple, b: tuple) -> tuple | None:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    x0, y0 = max(ax0, bx0), max(ay0, by0)
    x1, y1 = min(ax1, bx1), min(ay1, by1)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def urun_kutusu_sayfada(yerlesim: dict, analiz: dict) -> dict | None:
    """Asetin urun bbox'ini sayfa mm koordinatina tasir.

    Asetin urun_kutusu normalize aset koordinatinda; kadraj asetin bir
    alt dikdortgeni; yerlesim o kadraji sayfaya oturtuyor. Uc adimda
    tasinir ve kadraj disinda kalan kisim KIRPILIR.
    """
    uk = analiz.get("urun_kutusu") or {}
    if not uk:
        return None
    ux0, uy0 = float(uk.get("x", 0)), float(uk.get("y", 0))
    ux1 = ux0 + float(uk.get("en", 0))
    uy1 = uy0 + float(uk.get("boy", 0))

    k = yerlesim["crop"]
    kx0, ky0 = float(k["x"]), float(k["y"])
    kx1, ky1 = kx0 + float(k["en"]), ky0 + float(k["boy"])

    kes = _kesisim((ux0, uy0, ux1, uy1), (kx0, ky0, kx1, ky1))
    if not kes:
        return None
    x0, y0, x1, y1 = kes

    # kadraj icindeki goreli konum
    rx0 = (x0 - kx0) / max(1e-9, kx1 - kx0)
    rx1 = (x1 - kx0) / max(1e-9, kx1 - kx0)
    ry0 = (y0 - ky0) / max(1e-9, ky1 - ky0)
    ry1 = (y1 - ky0) / max(1e-9, ky1 - ky0)

    px, py = yerlesim["placement_xy_mm"]
    pw, ph = yerlesim["placement_size_mm"]
    return {"x": px + rx0 * pw, "y": py + ry0 * ph,
            "en": (rx1 - rx0) * pw, "boy": (ry1 - ry0) * ph,
            "kadrajda_kirpildi": (ux0 < kx0 - 1e-6 or ux1 > kx1 + 1e-6
                                  or uy0 < ky0 - 1e-6 or uy1 > ky1 + 1e-6)}


def olc(plan, yerlesimler: list[dict], analizler: dict) -> dict:
    """On metrik. Hicbiri digeriyle toplanmaz."""
    sayfa_alan = SAYFA * SAYFA

    # A · PHOTO AREA / PAGE
    foto_alan = sum(y["placement_size_mm"][0] * y["placement_size_mm"][1]
                    for y in yerlesimler)
    A = foto_alan / sayfa_alan

    # B · PRODUCT BBOX / PAGE  (birden cok yerlesimde en buyuk urun)
    kutular = []
    for y in yerlesimler:
        a = analizler.get(y["source"])
        if not a:
            continue
        kb = urun_kutusu_sayfada(y, a)
        if kb:
            kutular.append((kb, y, a))
    B = 0.0
    en_buyuk = None
    for kb, y, a in kutular:
        alan = kb["en"] * kb["boy"] / sayfa_alan
        if alan > B:
            B, en_buyuk = alan, (kb, y, a)

    # C · PRODUCT / PHOTO AREA
    C = (B / A) if A > 0 else 0.0

    if en_buyuk is None:
        return {"A_photo_area_page": round(A, 4),
                "B_product_bbox_page": 0.0, "C_product_per_photo": 0.0,
                "D_product_contrast": None, "E_product_isolation": None,
                "F_saliency_proxy": None, "G_background_competition": None,
                "H_product_sharpness": None, "I_product_position": None,
                "J_edge_interaction": None,
                "kanit": ["sayfada olculebilir urun kutusu YOK"]}

    kb, y, a = en_buyuk

    # D · PRODUCT CONTRAST -- ASET DUZEYINDE olculur, SAYFA duzeyinde
    # degil. Iki tur ayni aseti kullaniyorsa D zorunlu olarak ESITTIR;
    # bu gercek esitlik degil OLCUM SINIRIDIR. Sayfa uzerindeki gercek
    # yerel kontrast icin render pikselinden olcum gerekir -- yapilmadi.
    D = (a.get("ton_hiyerarsisi") or {}).get("kontrast_farki")

    # E · PRODUCT ISOLATION -- urun cevresindeki bos pay (kadraj icinde)
    ke = a.get("kenar_gerilimi") or {}
    E = ke.get("en_dar")

    # F · SALIENCY_PROXY -- gercek saliency modeli DEGIL. katalog_foto_
    # analiz icindeki CV vekili. Kesin hukum icin kullanilamaz; ayni
    # asette iki tur arasinda zorunlu olarak esittir.
    F = a.get("saliency_urun_payi")

    # G · BACKGROUND COMPETITION -- urun kutusuyla CAKISAN metin/alan ogesi
    cakisan = 0
    kutu = (kb["x"], kb["y"], kb["x"] + kb["en"], kb["y"] + kb["boy"])
    for oge in plan.ogeler:
        if oge.tur not in ("metin", "cizgi", "not_alani"):
            continue
        v = oge.veri
        ow = float(v.get("en", 0)) or 30.0
        oh = 8.0 if oge.tur == "metin" else 4.0
        if _kesisim(kutu, (v["x"], v["y"] - oh, v["x"] + ow, v["y"] + oh)):
            cakisan += 1
    G = cakisan

    # H · PRODUCT SHARPNESS
    H = a.get("keskinlik")

    # I · PRODUCT POSITION -- urun merkezinin sayfadaki konumu
    cx = (kb["x"] + kb["en"] / 2) / SAYFA
    cy = (kb["y"] + kb["boy"] / 2) / SAYFA
    yatay = "sol" if cx < 0.38 else "sag" if cx > 0.62 else "orta"
    dikey = "ust" if cy < 0.38 else "alt" if cy > 0.62 else "orta"
    I = {"cx": round(cx, 3), "cy": round(cy, 3), "bolge": "%s-%s" % (dikey, yatay)}

    # J · EDGE INTERACTION -- urun sayfa kenarina degiyor / tasiyor mu
    tasma = (SAYFA - TRIM) / 2.0
    dokunan = []
    if kb["x"] <= tasma + 0.5:
        dokunan.append("sol")
    if kb["y"] <= tasma + 0.5:
        dokunan.append("ust")
    if kb["x"] + kb["en"] >= SAYFA - tasma - 0.5:
        dokunan.append("sag")
    if kb["y"] + kb["boy"] >= SAYFA - tasma - 0.5:
        dokunan.append("alt")
    J = {"kenarlar": dokunan, "kirpildi": kb["kadrajda_kirpildi"]}

    return {
        "A_photo_area_page": round(A, 4),
        "B_product_bbox_page": round(B, 4),
        "C_product_per_photo": round(C, 4),
        "D_product_contrast": round(D, 4) if D is not None else None,
        "E_product_isolation": round(E, 4) if E is not None else None,
        "F_saliency_proxy": round(F, 4) if F is not None else None,
        "G_background_competition": G,
        "H_product_sharpness": round(H, 4) if H is not None else None,
        "I_product_position": I,
        "J_edge_interaction": J,
        "bbox_width_mm": round(kb["en"], 1),
        "bbox_height_mm": round(kb["boy"], 1),
        "bbox_long_edge_mm": round(max(kb["en"], kb["boy"]), 1),
        "bbox_area_over_page": round(B, 4),
        "measurement_method": {
            "A_B_C": "plan yerlesim geometrisi + aset urun_kutusu (mm)",
            "D": "ASET duzeyi ton kontrasti -- sayfa duzeyi DEGIL",
            "E": "aset kenar gerilimi -- kadraj icindeki en dar pay",
            "F": "CV SALIENCY_PROXY -- gercek saliency modeli degil",
            "G": "plan ogeleriyle urun kutusunun geometrik cakismasi",
        },
        "confidence": {
            "A_B_C": "HIGH -- dogrudan geometri",
            "D": "LOW -- aset duzeyi, sayfa zeminini gormuyor",
            "E": "MEDIUM -- aset duzeyi",
            "F": "LOW -- proxy",
            "G": "MEDIUM -- kaba dikdortgen yaklasimi",
        },
        "urun_kutusu_mm": {k: round(v, 1) for k, v in kb.items()
                           if isinstance(v, (int, float))},
        "kanit": [
            "fotograf sayfanin %%%.1f'i" % (A * 100),
            "urun kutusu sayfanin %%%.1f'i" % (B * 100),
            "urun fotografin %%%.1f'i" % (C * 100),
            "urun/zemin ton farki %s" % (round(D, 3) if D is not None else "-"),
            "urun konumu %s" % I["bolge"],
            "urun kutusuyla cakisan tipografi ogesi %d" % G,
        ],
    }


def karsilastir(kayitlar: list[dict]) -> dict:
    """Turlar arasi karsilastirma -- tek skor URETMEZ."""
    out = {}
    for t, liste in kayitlar:
        A = [k["A_photo_area_page"] for k in liste]
        B = [k["B_product_bbox_page"] for k in liste]
        C = [k["C_product_per_photo"] for k in liste]
        out[t] = {
            "A_ortalama": round(sum(A) / len(A), 4),
            "B_ortalama": round(sum(B) / len(B), 4),
            "B_en_dusuk": round(min(B), 4),
            "B_en_yuksek": round(max(B), 4),
            "C_ortalama": round(sum(C) / len(C), 4),
        }
    return out


if __name__ == "__main__":
    print(__doc__)
    print("Metrikler: A..J -- hicbiri toplanmaz, hicbiri tek basina karar "
          "vermez.")
