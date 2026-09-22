"""36 ürünün arka planını keser ve SONUCU DENETLER.

🔴 KESİM KÖRLEMESİNE KABUL EDİLMEZ. rembg bazen ürünün bir kısmını da
siler, bazen hiçbir şey silmez. Üç ölçüt bakılıyor:
    doluluk < %2   -> ürünü yemiş, kullanılamaz
    doluluk > %97  -> hiçbir şey silmemiş, arka plan duruyor
    parça sayısı   -> en büyük bileşen dışında kırpıntı kalmış mı
Şüpheli olanlar "İNCELE" ile ayrılıyor ve sahibin önüne öyle gidiyor.
Hepsini "tamam" saymak, bir gün yayına yarısı silinmiş bir ürün
göndermek demekti.

🔴 AMBALAJ DEĞİŞTİRİLMEZ. Sahibin kuralı (14.09.2026): şişe/kutu görseli
ve üstündeki yazılar değişmeyecek. Bu betik yalnız ARKA PLANI siler;
ürünün kendisine dokunmaz, yeniden çizmez, rötuşlamaz.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import new_session, remove

HAM = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/ham")
KESIM = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/kesim")
KESIM.mkdir(parents=True, exist_ok=True)

AZAMI_KENAR = 2000          # kesimden önce küçült: hız ve bellek
ASGARI_DOLULUK = 0.02
# 🔴 Alfası bu değerin altındaki piksel ARKA PLAN sayılır. rembg arka
# planı tam sıfırlamıyor; 5-30 arası bir sis bırakıyor ve koyu zeminde
# hayalet olarak görünüyor (ölçüldü: HYDRAVIE ve OPTYWAVE).
ALFA_ESIK = 40
AZAMI_DOLULUK = 0.97


# Bir parça, en büyük parçanın bu oranından küçükse KIRPINTI sayılır.
# Tek parça şartı koymuyoruz: bazı ürünler gerçekten iki parçalı
# (şeffaf kapak + gövde) ve onları kesmek ürünü bozardı.
PARCA_ORANI = 0.02


def en_buyuk_bilesen(alfa: np.ndarray) -> tuple[np.ndarray, int]:
    """Kırpıntıları eler, gerçek parçaları korur.

    🔴 MASKE PIL İLE BÜYÜTÜLÜYOR. np.kron ile büyütünce çıkış boyutu
    (h//4)*4 oluyordu; 4'e bölünmeyen yüksekliklerde boyut uyuşmuyor ve
    fonksiyon sessizce orijinali döndürüyordu -- yani filtre yoktu.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return alfa, -1

    kucuk = alfa[::4, ::4] > 0
    etiket, adet = ndimage.label(kucuk)
    if adet <= 1:
        return alfa, adet

    boyutlar = np.array(ndimage.sum(kucuk, etiket, range(1, adet + 1)))
    esik = boyutlar.max() * PARCA_ORANI
    tutulacak = {i + 1 for i, b in enumerate(boyutlar) if b >= esik}
    kucuk_maske = np.isin(etiket, list(tutulacak))

    # 🔴 Boyut HER ZAMAN kaynakla aynı: NEAREST ile tam ölçeğe çıkar.
    maske = np.array(
        Image.fromarray((kucuk_maske * 255).astype(np.uint8))
        .resize((alfa.shape[1], alfa.shape[0]), Image.NEAREST)) > 127

    return np.where(maske, alfa, 0).astype(np.uint8), adet - len(tutulacak)


def main():
    dosyalar = sorted(HAM.glob("*.jpg"))
    if not dosyalar:
        print("ham klasörü boş"); return
    print(f"{len(dosyalar)} görsel kesilecek\n")
    oturum = new_session("isnet-general-use")
    rapor = []

    for i, d in enumerate(dosyalar, 1):
        cikti = KESIM / (d.stem + ".png")
        if cikti.exists() and cikti.stat().st_size > 20_000:
            print(f"  [{i:>2}/{len(dosyalar)}] {d.stem:<20} zaten var")
            continue
        try:
            im = Image.open(d).convert("RGB")
            if max(im.size) > AZAMI_KENAR:
                o = AZAMI_KENAR / max(im.size)
                im = im.resize((int(im.width * o), int(im.height * o)),
                               Image.LANCZOS)
            kesik = remove(im, session=oturum).convert("RGBA")
            a = np.array(kesik)[:, :, 3]
            # 🔴 ÖNCE EŞİKLE. Bileşen analizi ve bbox, sis üstünde
            # çalışırsa ürünü değil sisin sınırlarını bulur.
            a = np.where(a < ALFA_ESIK, 0, a).astype(np.uint8)
            temiz, parca = en_buyuk_bilesen(a)
            arr = np.array(kesik)
            arr[:, :, 3] = temiz
            kesik = Image.fromarray(arr, "RGBA")

            doluluk = float((temiz > 0).mean())
            kutu = kesik.getbbox()
            if kutu:
                kesik = kesik.crop(kutu)

            durum = "TAMAM"
            if doluluk < ASGARI_DOLULUK:
                durum = "İNCELE: ürün yenmiş olabilir"
            elif doluluk > AZAMI_DOLULUK:
                durum = "İNCELE: arka plan silinmemiş olabilir"
            elif parca > 12:
                durum = f"İNCELE: {parca} kırpıntı atıldı"

            kesik.save(cikti, "PNG", optimize=True)
            rapor.append({"dosya": cikti.name, "doluluk": round(doluluk, 3),
                          "parca": parca, "olcu": list(kesik.size),
                          "durum": durum})
            isaret = "✅" if durum == "TAMAM" else "⚠"
            print(f"  [{i:>2}/{len(dosyalar)}] {isaret} {d.stem:<20} "
                  f"{kesik.size[0]}x{kesik.size[1]} doluluk={doluluk:.2f} "
                  f"{'' if durum == 'TAMAM' else durum}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>2}/{len(dosyalar)}] ⛔ {d.stem:<20} {str(e)[:60]}")
            rapor.append({"dosya": d.name, "durum": f"HATA: {str(e)[:80]}"})

    (KESIM / "rapor.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    tamam = sum(1 for r in rapor if r.get("durum") == "TAMAM")
    print(f"\nTAMAM={tamam}  İNCELE/HATA={len(rapor) - tamam}")
    print(f"rapor: {KESIM / 'rapor.json'}")


if __name__ == "__main__":
    main()
