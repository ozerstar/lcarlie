#!/usr/bin/env python3
"""Benchmark kumesi ureteci -- ORIJINAL PDF'LERE DOKUNMAZ.

Eski (kare) ve yeni (A4) katalogtan analiz/test icin aday sayfalar
secer ve olculmus gerekcelerle bir manifest uretir.

TEMEL KURAL -- OVERFIT YASAGI:
    Bu kume sistemin OGRENECEGI bir cevap anahtari degildir. Insan
    notu (`neden_secildi`) yalnizca insanin okumasi icindir; hicbir
    otomatik karar bu nota bakamaz.

    "Guclu" / "zayif" etiketleri OLCUMDEN TURETILIR ve insan onayina
    kadar `insan_onayi: BEKLIYOR` tasir. Sistem kendi olcumunu
    dogrulamak icin kendi etiketini kullanamaz.

KOPYALAMA YOK: manifest yalnizca dosya yolu + sayfa numarasi tutar.
    PDF'ler depoya konmaz (boyut ve degistirmeme kurali).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_sayfa_olcum as so   # noqa: E402


def _olc(pdf: str) -> dict:
    o = so.sayfa_olcumleri(pdf)
    return {"olcumler": o, "tekrar": so.tekrar_kaniti(pdf),
            "ritim": so.ritim_kaniti(o)}


def _aday_urun_sayfasi(olcumler, guclu: bool):
    """Urun sayfasi adayi: gorsel agirlikli, metni olan sayfalar.

    GUCLU = gorsel orani yuksek + metin var + oge sayisi asiri degil
    ZAYIF = gorsel orani dusuk ya da oge sayisi asiri (gurultu)"""
    adaylar = [x for x in olcumler if x.metin_alan_orani > 0.02]
    if not adaylar:
        return None
    if guclu:
        return max(adaylar, key=lambda x: (x.gorsel_alan_orani + x.cizim_alan_orani)
                   / max(x.ogeler, 1))
    return min(adaylar, key=lambda x: (x.gorsel_alan_orani + x.cizim_alan_orani)
               / max(x.ogeler, 1))


def _aday_bolum_acilisi(olcumler, guclu: bool):
    """Bolum acilisi adayi: dusuk metin, yuksek gorsel ya da tam tersi."""
    if not olcumler:
        return None
    if guclu:
        return max(olcumler, key=lambda x: (x.gorsel_alan_orani + x.cizim_alan_orani)
                   - x.metin_alan_orani * 3)
    # zayif: hem gorsel hem metin dusuk -> olu alan suphesi
    return min(olcumler, key=lambda x: x.gorsel_alan_orani + x.cizim_alan_orani
               + x.metin_alan_orani)


def _olu_alan_suphesi(olcumler):
    """Bosluk orani yuksek + oge sayisi dusuk -> olu bosluk adayi."""
    adaylar = [x for x in olcumler if x.bosluk_orani > 0.45 and x.ogeler <= 12]
    return max(adaylar, key=lambda x: x.bosluk_orani) if adaylar else None


def kume(pdf: str, etiket: str) -> dict:
    v = _olc(pdf)
    o = v["olcumler"]
    ogeler: list[dict] = []

    def E(kimlik, sayfa, tur, neden, olcum_gerekcesi):
        if sayfa is None:
            ogeler.append({"id": kimlik, "tur": tur, "durum": "ADAY_YOK",
                           "neden_secildi": neden})
            return
        ogeler.append({
            "id": kimlik,
            "kaynak": pdf,
            "sayfa": sayfa.sayfa,
            "tur": tur,
            "olcum": sayfa.sozluk(),
            "olcum_gerekcesi": olcum_gerekcesi,
            "neden_secildi": neden,
            "insan_onayi": "BEKLIYOR",
        })

    E("%s-urun-guclu" % etiket, _aday_urun_sayfasi(o, True), "URUN_SAYFASI",
      "Gorsel kutlesi yuksek ama oge sayisi dusuk -- sade ve gorsel agirlikli "
      "urun sayfasi adayi. Insan dogrulamasi bekliyor.",
      "max((gorsel+cizim) / oge_sayisi), metin_orani > 0.02")
    E("%s-urun-zayif" % etiket, _aday_urun_sayfasi(o, False), "URUN_SAYFASI",
      "Oge sayisina gore gorsel kutlesi dusuk -- gurultulu ya da urunu zayif "
      "gosteren sayfa adayi.",
      "min((gorsel+cizim) / oge_sayisi), metin_orani > 0.02")
    E("%s-acilis-guclu" % etiket, _aday_bolum_acilisi(o, True), "BOLUM_ACILISI",
      "Gorsel hakimiyeti yuksek, metin asgari -- gucu gorselden alan bolum "
      "acilisi adayi.",
      "max((gorsel+cizim) - 3*metin)")
    E("%s-acilis-zayif" % etiket, _aday_bolum_acilisi(o, False), "BOLUM_ACILISI",
      "Hem gorsel hem metin dusuk -- acilis islevini tasimayan sayfa adayi.",
      "min(gorsel+cizim+metin)")
    E("%s-olu-alan" % etiket, _olu_alan_suphesi(o), "OLU_ALAN_SUPHESI",
      "Bosluk orani yuksek ve oge sayisi dusuk. Bu OLU BOSLUK KANITI DEGILDIR; "
      "kasitlilik isareti insan tarafindan degerlendirilir.",
      "bosluk_orani > 0.45 ve oge_sayisi <= 12")

    t = v["tekrar"]
    if t["gorsel_olarak_ayni_ciftler"]:
        c = t["gorsel_olarak_ayni_ciftler"][0]
        ogeler.append({
            "id": "%s-tekrar-cifti" % etiket,
            "kaynak": pdf, "sayfalar": c["sayfalar"], "tur": "YUKSEK_TEKRAR_CIFTI",
            "olcum": {"algisal_karma_mesafesi": c["mesafe"]},
            "olcum_gerekcesi": "dHash mesafesi <= 6",
            "neden_secildi": "Duzen imzalari farkli olsa bile gorsel olarak ayni "
                             "gorunen sayfa cifti. Tek sinyalin neden yetmediginin ornegi.",
            "insan_onayi": "BEKLIYOR",
        })
    # en uzak cift -- iyi varyasyon ornegi
    try:
        karmalar = so.algisal_karma(pdf)
        en_uzak, mesafe = None, -1
        for i in range(len(karmalar)):
            for j in range(i + 1, len(karmalar)):
                d = so.karma_mesafesi(karmalar[i], karmalar[j])
                if d > mesafe:
                    mesafe, en_uzak = d, [i + 1, j + 1]
        if en_uzak:
            ogeler.append({
                "id": "%s-varyasyon-cifti" % etiket,
                "kaynak": pdf, "sayfalar": en_uzak, "tur": "IYI_VARYASYON_CIFTI",
                "olcum": {"algisal_karma_mesafesi": mesafe},
                "olcum_gerekcesi": "azami dHash mesafesi",
                "neden_secildi": "Katalogun birbirinden en uzak iki sayfasi. "
                                 "Varyasyon araliginin ust sinirini gosterir.",
                "insan_onayi": "BEKLIYOR",
            })
    except Exception as hata:                     # noqa: BLE001
        ogeler.append({"id": "%s-varyasyon-cifti" % etiket, "durum": "OLCULEMEDI",
                       "sebep": "%s" % hata.__class__.__name__})

    ozet = {
        "sayfa_sayisi": len(o),
        "olcu_mm": [o[0].en_mm, o[0].boy_mm] if o else None,
        "gorsel_cizim_orani_medyan": round(statistics.median(
            [x.gorsel_alan_orani + x.cizim_alan_orani for x in o]), 4) if o else None,
        "metin_orani_medyan": round(statistics.median(
            [x.metin_alan_orani for x in o]), 4) if o else None,
        "oge_sayisi_medyan": statistics.median([x.ogeler for x in o]) if o else None,
        "duzen_cesitliligi": t["duzen_cesitliligi"],
        "gorsel_ayni_cift_sayisi": t["gorsel_ayni_cift_sayisi"],
        "ardisik_ayni_duzen": len(t["ardisik_ayni_duzen"]),
        "ritim_ardisik_uc_ayni": len(v["ritim"]["ardisik_uc_ayni_kademe"]),
        "yogunluk_araligi": [v["ritim"]["en_dusuk"], v["ritim"]["en_yuksek"]],
    }
    return {"etiket": etiket, "kaynak": pdf, "ozet": ozet, "ogeler": ogeler}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eski", required=True, help="eski (kare) katalog PDF yolu")
    ap.add_argument("--yeni", required=True, help="yeni (A4) katalog PDF yolu")
    ap.add_argument("--cikti", default="evidence/katalog-benchmark.json")
    a = ap.parse_args()

    manifest = {
        "surum": 1,
        "uretildi": "FAZ -1B",
        "kural": ("Orijinal PDF'ler DEGISTIRILMEDI ve depoya KOPYALANMADI. "
                  "Bu manifest yalnizca yol + sayfa numarasi + olcum tutar. "
                  "OVERFIT YASAGI: neden_secildi alani yalnizca insan icindir; "
                  "hicbir otomatik karar bu alani okuyamaz."),
        "kumeler": [kume(a.eski, "eski-kare"), kume(a.yeni, "yeni-a4")],
    }

    # Karsilastirma -- iki kume arasinda dogrudan
    e, y = manifest["kumeler"][0]["ozet"], manifest["kumeler"][1]["ozet"]
    manifest["karsilastirma"] = {
        "not": ("'Eski daha iyiydi' bir baslangic varsayimi DEGILDIR. "
                "Asagidaki sayilar iki yonde de kanit tasiyor."),
        "eski_lehine": [],
        "yeni_lehine": [],
    }
    if e["metin_orani_medyan"] > y["metin_orani_medyan"]:
        manifest["karsilastirma"]["eski_lehine"].append(
            "metin alani medyani %.3f vs %.3f -- sayfa basina daha cok bilgi"
            % (e["metin_orani_medyan"], y["metin_orani_medyan"]))
    if e["oge_sayisi_medyan"] < y["oge_sayisi_medyan"]:
        manifest["karsilastirma"]["eski_lehine"].append(
            "oge sayisi medyani %s vs %s -- daha sade sayfa"
            % (e["oge_sayisi_medyan"], y["oge_sayisi_medyan"]))
    if y["gorsel_ayni_cift_sayisi"] < e["gorsel_ayni_cift_sayisi"]:
        manifest["karsilastirma"]["yeni_lehine"].append(
            "gorsel olarak ayni sayfa cifti %d vs %d -- daha az gorsel tekrar"
            % (y["gorsel_ayni_cift_sayisi"], e["gorsel_ayni_cift_sayisi"]))
    if y["ritim_ardisik_uc_ayni"] < e["ritim_ardisik_uc_ayni"]:
        manifest["karsilastirma"]["yeni_lehine"].append(
            "ardisik uc ayni yogunluk %d vs %d -- daha degisken ritim"
            % (y["ritim_ardisik_uc_ayni"], e["ritim_ardisik_uc_ayni"]))

    yol = pathlib.Path(a.cikti)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    print("BENCHMARK MANIFESTI: %s" % yol)
    for k in manifest["kumeler"]:
        o = k["ozet"]
        print("\n%s -- %d sayfa, %.0fx%.0f mm"
              % (k["etiket"], o["sayfa_sayisi"], o["olcu_mm"][0], o["olcu_mm"][1]))
        print("  metin orani medyan %.3f | oge medyan %s | duzen cesitliligi %.3f"
              % (o["metin_orani_medyan"], o["oge_sayisi_medyan"], o["duzen_cesitliligi"]))
        print("  gorsel ayni cift %d | ritimde ardisik uc ayni %d"
              % (o["gorsel_ayni_cift_sayisi"], o["ritim_ardisik_uc_ayni"]))
        print("  aday oge: %d" % len(k["ogeler"]))
    print("\nKARSILASTIRMA")
    for yon in ("eski_lehine", "yeni_lehine"):
        print("  %s:" % yon)
        for s in manifest["karsilastirma"][yon] or ["(bulgu yok)"]:
            print("    - %s" % s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
