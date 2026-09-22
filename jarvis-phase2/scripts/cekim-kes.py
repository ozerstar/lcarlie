"""385 GERCEK CEKIMI keser. Arka planda kosar.

Wix gorselleri filigranliydi ve OPTYWAVE'de hayalet birakti. Bu klasor
sahibin kendi cekim arsivi: duz zemin, yumusak golge, tek urun -- kesim
icin kolay vaka. Uc ornekte olculdu, sonuc temiz cikti.

🔴 URUN TANIMA BU ADIMDA YAPILMIYOR. Dosya adlari DSC04301 gibi; hangi
urun oldugunu etiketten okumak ayri bir is ve para harciyor (gorsel
modeli cagrisi). Once kesim (bedava, yerel), sonra tanima. Boylece
tanima adimi calismasa bile elimizde kesilmis 385 gorsel kalir.

🔴 SONUC DENETLENIYOR. doluluk < %2 urunu yemis, > %98 hicbir sey
silmemis demek. Supheliler "INCELE" ile ayriliyor.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import new_session, remove

KAYNAK = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-ham")
HEDEF = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-kesim")
HEDEF.mkdir(parents=True, exist_ok=True)

ALFA_ESIK = 40
PARCA_ORANI = 0.02


def bilesen_temizle(alfa):
    try:
        from scipy import ndimage
    except ImportError:
        return alfa, -1
    kucuk = alfa[::4, ::4] > 0
    etiket, adet = ndimage.label(kucuk)
    if adet <= 1:
        return alfa, 0
    boyut = np.array(ndimage.sum(kucuk, etiket, range(1, adet + 1)))
    tut = {i + 1 for i, b in enumerate(boyut) if b >= boyut.max() * PARCA_ORANI}
    m = np.isin(etiket, list(tut))
    maske = np.array(Image.fromarray((m * 255).astype(np.uint8))
                     .resize((alfa.shape[1], alfa.shape[0]),
                             Image.NEAREST)) > 127
    return np.where(maske, alfa, 0).astype(np.uint8), adet - len(tut)


def main():
    dosyalar = sorted(KAYNAK.glob("*.jpg"))
    oturum = new_session("isnet-general-use")
    rapor = []
    print(f"{len(dosyalar)} çekim kesilecek", flush=True)

    for i, d in enumerate(dosyalar, 1):
        cikti = HEDEF / (d.stem + ".png")
        if cikti.exists() and cikti.stat().st_size > 20_000:
            continue
        try:
            im = Image.open(d).convert("RGB")
            k = remove(im, session=oturum).convert("RGBA")
            a = np.array(k)
            alfa = np.where(a[:, :, 3] < ALFA_ESIK, 0, a[:, :, 3])
            alfa, atilan = bilesen_temizle(alfa.astype(np.uint8))
            a[:, :, 3] = alfa
            k = Image.fromarray(a)
            doluluk = float((alfa > 0).mean())
            kutu = k.getbbox()
            if kutu:
                k = k.crop(kutu)
            durum = "TAMAM"
            if doluluk < 0.02:
                durum = "İNCELE: ürün yenmiş olabilir"
            elif doluluk > 0.98:
                durum = "İNCELE: arka plan silinmemiş olabilir"
            k.save(cikti, "PNG", optimize=True)
            rapor.append({"dosya": cikti.name, "olcu": list(k.size),
                          "doluluk": round(doluluk, 3), "atilan": atilan,
                          "durum": durum})
            if i % 25 == 0 or durum != "TAMAM":
                print(f"  [{i}/{len(dosyalar)}] {d.stem:<34} {k.size} "
                      f"{durum}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}] ⛔ {d.stem}: {str(e)[:70]}", flush=True)
            rapor.append({"dosya": d.name, "durum": f"HATA: {str(e)[:90]}"})

    (HEDEF / "rapor.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    tamam = sum(1 for r in rapor if r.get("durum") == "TAMAM")
    print(f"\nBİTTİ  TAMAM={tamam}  İNCELE/HATA={len(rapor) - tamam}",
          flush=True)


if __name__ == "__main__":
    main()
