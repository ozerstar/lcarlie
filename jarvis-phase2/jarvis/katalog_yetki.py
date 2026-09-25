"""Yetki grafigi ve karar cozumlemesi.

SORUN: 18 capability karar uretiyor. Hangi karar kazanir?

ILKE: siddet kazanir, oy cokluğu DEGIL.
    Bu sistemde OYLAMA YOKTUR. Sahte konsensus uretmemek icin her ret
    tek basina baglayicidir. Uc rol "guzel" deyip biri HARD_REJECT
    verirse sonuc HARD_REJECT'tir.

ASILMA KURALI:
    HARD_REJECT       asilmaz (C12 urun butunlugu, C06 mevzuat)
    REJECT            yalniz INSAN asabilir
    REVIZE            akisi durdurmaz, tur sayaci isletir
    ADVISE            hicbir seyi degistirmez

TUR SINIRI:
    Sonsuz ret dongusu gercek bir risk. Ucuncu turda karar insana tasinir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from jarvis import katalog_yetenek as yetenek

# Artan siddet. Cozumlemede en yuksek indis kazanir.
SIDDET = ("ADVISE", "APPROVE", "REVISE", "REJECT", "ESCALATE_TO_HUMAN",
          "HARD_REJECT")

ASILAMAZ = ("HARD_REJECT",)
YALNIZ_INSAN_ASAR = ("REJECT",)

AZAMI_TUR = 3


@dataclass(frozen=True)
class Karar:
    capability: str
    yetki: str
    gerekce: str
    kanit: dict

    def sozluk(self) -> dict:
        return asdict(self)


class YetkiIhlali(Exception):
    """Capability sahip olmadigi yetkiyi kullandi."""


def yetki_dogrula(karar: Karar) -> None:
    """Capability o yetkiye sahip mi. Degilse istisna.

    Bu, 'her ajan her seyi reddedebilir' kaymasini engeller."""
    y = yetenek.getir(karar.capability)
    if y is None:
        raise YetkiIhlali("bilinmeyen capability: %s" % karar.capability)
    if karar.yetki not in y.authority:
        raise YetkiIhlali(
            "%s (%s) %s yetkisine sahip degil -- sahip oldugu: %s"
            % (karar.capability, y.name, karar.yetki,
               ", ".join(y.authority) or "(hicbiri)"))


def cozumle(kararlar: list[Karar], tur: int = 1) -> dict:
    """Kararlari cozumler. Oylama yok -- en siddetli karar kazanir."""
    for k in kararlar:
        yetki_dogrula(k)

    if not kararlar:
        return {"sonuc": "KANIT_YOK", "gerekce": "hicbir capability karar vermedi",
                "asilabilir": False, "tur": tur, "kararlar": []}

    en_siddetli = max(kararlar, key=lambda k: SIDDET.index(k.yetki))
    sonuc = en_siddetli.yetki

    if tur >= AZAMI_TUR and sonuc in ("REVIZE", "REJECT"):
        return {
            "sonuc": "ESCALATE_TO_HUMAN",
            "gerekce": "tur %d: %s tarafindan %s -- tur siniri asildi, "
                       "karar sahibe tasindi"
                       % (tur, en_siddetli.capability, sonuc),
            "asilabilir": False,
            "tur": tur,
            "kararlar": [k.sozluk() for k in kararlar],
            "tur_siniri_asildi": True,
        }

    return {
        "sonuc": sonuc,
        "belirleyen": en_siddetli.capability,
        "gerekce": en_siddetli.gerekce,
        "asilabilir": sonuc not in ASILAMAZ,
        "yalniz_insan_asar": sonuc in YALNIZ_INSAN_ASAR,
        "tur": tur,
        "kararlar": [k.sozluk() for k in kararlar],
    }


# --- grafik --------------------------------------------------------------

def grafik() -> dict:
    """Yetki grafigini makine-okunur bicimde uretir."""
    dugumler = []
    for y in yetenek.kayitlar():
        dugumler.append({
            "id": y.id,
            "ad": y.name,
            "tip": y.type,
            "yetki": list(y.authority),
            "en_yuksek_yetki": max(y.authority, key=SIDDET.index)
            if y.authority else None,
            "upstream": list(y.upstream),
            "downstream": list(y.downstream),
        })
    return {
        "dugumler": dugumler,
        "durdurabilen": [y.id for y in yetenek.durdurabilenler()],
        "yalniz_tavsiye_eden": [y.id for y in yetenek.kayitlar()
                                if y.authority and
                                set(y.authority) <= {"ADVISE"}],
        "yetkisiz": [y.id for y in yetenek.kayitlar() if not y.authority],
        "dogrulama": yetenek.dogrula(),
    }


# --- agent theater korumasi (calisma zamani) ----------------------------

def yeni_capability_denetle(aday: yetenek.Yetenek) -> dict:
    """Yeni bir capability eklenmeden once uc soruyu sorar.

    Benzersiz yetenek / benzersiz kanit / benzersiz yetki -- ucunden
    hicbiri yoksa POTENTIAL_AGENT_THEATER uyarisi uretir.

    UYARI URETIR, ENGELLEMEZ. Karar sahibindir."""
    mevcut = yetenek.kayitlar()

    olculer: dict[str, list[str]] = {}
    girdiler: dict[str, list[str]] = {}
    for y in mevcut:
        for m in y.measurements_required:
            olculer.setdefault(m, []).append(y.id)
        for g in y.inputs:
            girdiler.setdefault(g, []).append(y.id)

    benzersiz_olcum = [m for m in aday.measurements_required if m not in olculer]
    benzersiz_girdi = [g for g in aday.inputs if g not in girdiler]
    gercek_yetki = sorted(set(aday.authority)
                          & {"REJECT", "HARD_REJECT", "APPROVE"})

    cakisan = [y.id for y in mevcut
               if y.id != aday.id
               and set(y.inputs) == set(aday.inputs)
               and set(y.measurements_required) == set(aday.measurements_required)]

    tiyatro = not (benzersiz_olcum or benzersiz_girdi or gercek_yetki)
    return {
        "id": aday.id,
        "uyari": "POTENTIAL_AGENT_THEATER" if tiyatro else None,
        "benzersiz_olcum": benzersiz_olcum,
        "benzersiz_girdi": benzersiz_girdi,
        "gercek_yetki": gercek_yetki,
        "ayni_veriyi_okuyan": cakisan,
        "karar": "EKLEME" if tiyatro else "EKLENEBILIR",
    }


def ozet() -> dict:
    g = grafik()
    return {
        "capability_sayisi": len(g["dugumler"]),
        "uretimi_durdurabilen": g["durdurabilen"],
        "yetkisiz_capability": g["yetkisiz"],
        "dongu_var_mi": any("dongu" in s for s in g["dogrulama"]),
        "dogrulama_sorunlari": g["dogrulama"],
        "azami_tur": AZAMI_TUR,
    }
