"""Canva kitapligina KLASOR YAPISI kurar ve varliklari yerlestirir.

Sahip 22.09.2026: *"içerde klasörler oluştur ve düzenli olsun."*

Hakli: kitapliga 35 filigranli + ~100 gercek kesim + model kareleri +
uretilen tasarimlar yigildi. Duz bir listede hangisinin ne oldugu
anlasilmaz -- ozellikle iki kaynak (filigranli/temiz) yan yana
durdugu icin YANLIS OLANI secme riski var.

YAPI:
  L'CARLIE
    01 URUN GORSELLERI      -> kesilmis, tanimli urun kareleri (KULLAN)
    02 MODEL CEKIMLERI      -> gercek insan kareleri
    03 SABLONLAR            -> alanlari isaretli Canva sablonlari
    04 URETILEN TASARIMLAR  -> autofill ciktilari
    09 KULLANMA - FILIGRANLI -> Wix kaynakli eski kesimler

🔴 SON KLASOR SILME DEGIL, KARANTINA. Filigranli varliklari silmek
geri alinamaz ve baska bir tasarimda kullanilmis olabilirler. Adinda
"KULLANMA" yazan bir klasore tasimak, hem gorunur kiliyor hem de
yanlislikla secilmelerini zorlastiriyor. Silme karari sahibin.

🔴 KLASOR ADLARI NUMARALI. Canva klasorleri alfabetik siraliyor;
numarasiz adlar her acilista farkli sirada gorunur ve "hangisi neydi"
sorusu tekrar eder.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import canva  # noqa: E402

KOK = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun")
YAPI = [
    ("01 URUN GORSELLERI", "Kesilmiş, ürün adıyla eşleşmiş kareler — "
                           "şablonların urun_gorseli alanı bunları kullanır"),
    ("02 MODEL CEKIMLERI", "Gerçek insan çekimi, arka planı kesilmiş"),
    ("03 SABLONLAR", "Alanları işaretli Canva şablonları"),
    ("04 URETILEN TASARIMLAR", "Autofill çıktıları — onay bekleyenler"),
    ("09 KULLANMA - FILIGRANLI", "Wix kaynaklı eski kesimler; "
                                 "arka planlarında filigran kalıntısı var"),
]


def klasor_kur(ad: str) -> str | None:
    """Klasörü oluşturur; zaten varsa var olanı bulur."""
    try:
        d = canva._cagir("/folders", metot="POST",
                         govde={"name": ad[:255], "parent_folder_id": "root"})
        return ((d.get("folder") or {}).get("id"))
    except canva.CanvaHatasi as h:
        # Aynı adla varsa Canva hata vermiyor, yeni klasör açıyor.
        # Yine de hata gelirse sebebini göster.
        print(f"  ⛔ {ad}: {str(h)[:90]}")
        return None


# 🔴 429 KALICI HATA DEĞİL, "YAVAŞLA" DEMEK. 101 taşımadan sonra Canva
# hız sınırına takıldı ve eski kod pes edip geçti. Geçici hata (429, 5xx)
# ile kalıcı hata (403, 404) aynı muameleyi göremez.
GERI_CEKILME = (2, 4, 8)


def tasi(oge_id: str, klasor_id: str) -> bool:
    for deneme, bekle in enumerate((0,) + GERI_CEKILME):
        if bekle:
            time.sleep(bekle)
        try:
            canva._cagir("/folders/move", metot="POST",
                         govde={"to_folder_id": klasor_id,
                                "item_id": oge_id})
            return True
        except canva.CanvaHatasi as h:
            m = str(h)
            if "429" in m or "too_many_requests" in m:
                if deneme < len(GERI_CEKILME):
                    continue        # yavaşla ve tekrar dene
                print(f"     hız sınırı aşılamadı {oge_id}")
                return False
            print(f"     taşınamadı {oge_id}: {m[:70]}")
            return False
    return False


def main():
    kayit_yolu = KOK / "canva-klasor.json"
    klasorler = {}
    if kayit_yolu.exists():
        klasorler = json.loads(kayit_yolu.read_text(encoding="utf-8"))

    print("=== KLASÖRLER")
    for ad, _aciklama in YAPI:
        if klasorler.get(ad):
            print(f"  · {ad:<28} {klasorler[ad]}  (zaten var)")
            continue
        kid = klasor_kur(ad)
        if kid:
            klasorler[ad] = kid
            print(f"  ✅ {ad:<28} {kid}")
    kayit_yolu.write_text(json.dumps(klasorler, ensure_ascii=False, indent=1),
                          encoding="utf-8")

    # ── varlıkları yerleştir
    tasima = []
    ck = KOK / "cekim-canva.json"
    if ck.exists():
        for v in json.loads(ck.read_text(encoding="utf-8")):
            if not v.get("varlik_id"):
                continue
            hedef = ("02 MODEL CEKIMLERI" if v.get("tur") == "MODEL"
                     else "01 URUN GORSELLERI")
            tasima.append((v["varlik_id"], hedef))

    eski = KOK / "canva-varlik.json"
    if eski.exists():
        for v in json.loads(eski.read_text(encoding="utf-8")):
            if v.get("varlik_id"):
                tasima.append((v["varlik_id"], "09 KULLANMA - FILIGRANLI"))

    print(f"\n=== {len(tasima)} varlık yerleştiriliyor")
    sayim = {}
    for vid, hedef in tasima:
        kid = klasorler.get(hedef)
        if not kid:
            continue
        time.sleep(0.4)   # 🔴 nefes: beklemesiz çağrı 429 üretiyor
        if tasi(vid, kid):
            sayim[hedef] = sayim.get(hedef, 0) + 1
    for k, n in sorted(sayim.items()):
        print(f"  {k:<28} {n} varlık")


if __name__ == "__main__":
    main()
