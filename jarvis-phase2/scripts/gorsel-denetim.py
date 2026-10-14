#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ÜRETİLEN GÖRSELİ DENETLER — sahibin gözü yerine.

Sahip 26.09.2026: "gözle onaylayacak kadar vaktim yok, buna uygun repolar
bul o onaylasın."

🔴 SEBEBİ ÖLÇÜLDÜ. Seedream 4.5'e dört sahne ürettirdim; isteme açıkça
"no products, no bottles, no jars, no text, no letters, no logo" yazdım.
İkisi dinledi, İKİSİ DİNLEMEDİ:
  · INTIMBLANC sahnesine davetsiz makyaj ürünleri koydu ve üstlerine
    "DINC LUXXE" diye bir marka uydurup bastı.
  · DERMARNICA sahnesine "The samgliac-intogoraation and buihding"
    diye hiçbir dile ait olmayan harfler bastı.
İlk koşuda 4'te 2 ret. Aynı kusuru 24.09'da SDXL de yapmıştı (negatif
istemde `bottle` yazmasına rağmen mermer şişe üretti). Model değişti,
kusur değişmedi: **modele "yapma" demek yetmiyor, çıktıya bakmak
gerekiyor.**

Kapı OWLv2 ile bakar (google/owlv2-base-patch16-ensemble, 155M): açık
sözlüklü tespit, yani sorguyu metinle veriyorsun, eğitim sınıfına bağlı
değil. "cosmetic bottle" diye sorabiliyoruz.

🔴 EŞİK VARSAYIM DEĞİL, ÖLÇÜM. Aşağıdaki eşikler gerçek dört kare
üzerinde kalibre edildi: iki kusurlu kare kırmızı, iki temiz kare yeşil
yanana kadar. Eşiği değiştiren, o dört kareyle yeniden ölçsün.

🔴 BU KAPI AYRI VENV'DE KOŞAR (venv-gorsel). Ana venv'e torch kurmak
paneli riske atardı -- MCP'de aynı dersi almıştık.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", "/opt/lcarlie/hf-cache")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_ADI = "google/owlv2-base-patch16-ensemble"

# Her kapi: (anahtar, etiket, sorgular, esik, ret_mi)
# Sorgular INGILIZCE -- OWLv2'nin metin kodlayicisi Ingilizce egitildi.
KAPILAR = [
    ("urun", "ürün sızıntısı",
     ["a cosmetic bottle", "a glass bottle", "a cosmetic jar",
      "a cream jar", "a tube of cream", "a pump dispenser",
      "product packaging", "a perfume bottle"], 0.16, True),
    ("yazi", "yazı / logo sızıntısı",
     ["text", "written words", "a logo", "a watermark",
      "a printed label"], 0.16, True),
    ("insan", "insan",
     ["a person", "a human face", "a human hand"], 0.16, True),
    ("klise", "reddedilen klişe",
     ["a flower", "a leaf", "a pebble", "a stone",
      "a water splash", "a crystal"], 0.20, True),
    # 🔴 Set ekipmani kadrajda gorunmemeli. Bu kapi, kapinin kendi
    # korlugunden dogdu: uretilen bir karede ayakli studyo lambasi
    # vardi ve dort kapinin dordunden de GECTI aldi -- lamba urun
    # degil, yazi degil, insan degil, klise listesinde de yok.
    # Kapi yalniz aradigini bulur; aramadigini goremez.
    ("ekipman", "set ekipmanı",
     ["a studio light", "a lamp", "a light fixture", "a tripod",
      "a softbox", "a light stand", "a camera"], 0.18, True),
]

_MODEL = None
_ISLEMCI = None


def _yukle():
    global _MODEL, _ISLEMCI
    if _MODEL is None:
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
        _ISLEMCI = Owlv2Processor.from_pretrained(MODEL_ADI)
        _MODEL = Owlv2ForObjectDetection.from_pretrained(MODEL_ADI)
        _MODEL.eval()
    return _MODEL, _ISLEMCI


def tespit(gorsel, sorgular: list, esik: float) -> list:
    """OWLv2 ile açık sözlüklü tespit. Eşiği geçen kutular döner."""
    import torch

    model, islemci = _yukle()
    girdi = islemci(text=[sorgular], images=gorsel, return_tensors="pt")
    with torch.no_grad():
        cikti = model(**girdi)
    hedef = torch.tensor([[gorsel.height, gorsel.width]])
    sonuc = islemci.post_process_grounded_object_detection(
        outputs=cikti, target_sizes=hedef, threshold=esik)[0]
    bulunan = []
    for puan, etiket in zip(sonuc["scores"].tolist(),
                            sonuc["labels"].tolist(), strict=False):
        bulunan.append({"ne": sorgular[etiket], "puan": round(puan, 3)})
    bulunan.sort(key=lambda b: -b["puan"])
    return bulunan


def negatif_alan_olc(gorsel, kutu=None) -> dict:
    """Yazı için ayrılan alan gerçekten boş mu?

    Kenar yoğunluğu ölçülür: alan ne kadar 'meşgul'se yazı o kadar
    okunmaz. Kutu verilmezse görselin en sakin üçte biri aranır.
    """
    from PIL import ImageFilter, ImageStat

    gri = gorsel.convert("L")
    if kutu:
        gri = gri.crop(kutu)
    kenar = gri.filter(ImageFilter.FIND_EDGES)
    ist = ImageStat.Stat(kenar)
    return {"kenar_ortalama": round(ist.mean[0], 2),
            "kenar_sapma": round(ist.stddev[0], 2)}


def en_sakin_bolge(gorsel, bol: int = 3) -> dict:
    """Görselin en sakin (yazıya en uygun) üçte biri hangisi?"""
    g, y = gorsel.size
    adaylar = {}
    for ad, kutu in (("ust", (0, 0, g, y // bol)),
                     ("orta", (0, y // bol, g, 2 * y // bol)),
                     ("alt", (0, 2 * y // bol, g, y))):
        adaylar[ad] = negatif_alan_olc(gorsel, kutu)["kenar_ortalama"]
    en_sakin = min(adaylar, key=adaylar.get)
    return {"bolgeler": adaylar, "en_sakin": en_sakin,
            "en_sakin_kenar": adaylar[en_sakin]}


def denetle(yol: Path, insan_serbest: bool = False,
            klise_serbest: bool = False) -> dict:
    """Bir görseli tüm kapılardan geçirir.

    🔴 "GEÇTİ" ile "BAKILMADI" ayrı şeylerdir. Bir kapı kapalıysa
    (insan_serbest gibi) sonuçta ATLANDI yazar, GECTI yazmaz.
    """
    from PIL import Image

    gorsel = Image.open(yol).convert("RGB")
    rapor = {"dosya": yol.name, "boyut": list(gorsel.size), "kapilar": []}
    red_sebepleri = []

    for anahtar, etiket, sorgular, esik, ret_mi in KAPILAR:
        if anahtar == "insan" and insan_serbest:
            rapor["kapilar"].append({"kapi": anahtar, "etiket": etiket,
                                     "sonuc": "ATLANDI",
                                     "gerekce": "konsept insan istiyor"})
            continue
        if anahtar == "klise" and klise_serbest:
            rapor["kapilar"].append({"kapi": anahtar, "etiket": etiket,
                                     "sonuc": "ATLANDI",
                                     "gerekce": "konsept bu nesneyi istiyor"})
            continue
        bulunan = tespit(gorsel, sorgular, esik)
        gecti = not bulunan
        rapor["kapilar"].append({
            "kapi": anahtar, "etiket": etiket, "esik": esik,
            "sonuc": "GECTI" if gecti else "KALDI",
            "bulunan": bulunan[:4]})
        if not gecti and ret_mi:
            red_sebepleri.append("%s: %s" % (
                etiket, ", ".join("%s (%.2f)" % (b["ne"], b["puan"])
                                  for b in bulunan[:3])))

    rapor["negatif_alan"] = en_sakin_bolge(gorsel)
    rapor["sonuc"] = "RET" if red_sebepleri else "GECTI"
    rapor["red_sebepleri"] = red_sebepleri
    return rapor


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gorseller", nargs="+")
    ap.add_argument("--insan-serbest", action="store_true")
    ap.add_argument("--klise-serbest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    raporlar = []
    for ad in a.gorseller:
        yol = Path(ad)
        if not yol.is_file():
            print("DOSYA YOK: %s" % ad)
            continue
        r = denetle(yol, a.insan_serbest, a.klise_serbest)
        raporlar.append(r)
        if a.json:
            continue
        print("\n%s  %s" % (r["sonuc"].ljust(6), r["dosya"]))
        for k in r["kapilar"]:
            iz = k.get("bulunan") or []
            print("   %-22s %-8s %s"
                  % (k["etiket"], k["sonuc"],
                     ", ".join("%s %.2f" % (b["ne"], b["puan"])
                               for b in iz) or k.get("gerekce", "")))
        n = r["negatif_alan"]
        print("   %-22s %-8s en sakin: %s (kenar %.1f)"
              % ("yazı alanı", "-", n["en_sakin"], n["en_sakin_kenar"]))
        for s in r["red_sebepleri"]:
            print("   🔴 " + s)

    if a.json:
        print(json.dumps(raporlar, ensure_ascii=False, indent=1))
    kalan = sum(1 for r in raporlar if r["sonuc"] == "RET")
    if not a.json:
        print("\n%d gorsel · %d RET · %d GECTI"
              % (len(raporlar), kalan, len(raporlar) - kalan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
