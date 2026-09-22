"""Kesilmiş ürün görsellerini CANVA KİTAPLIĞINA yükler.

Sahip: *"Bu dosyalar elimizde hazır olsun, uğraşmayalım arka plan
silmekle."* Sunucuda durması yetmez -- şablonlar Canva varlık kimliği
istiyor. Yüklenmezse her üretimde yeniden yüklemek gerekir.

🔴 "İNCELE" İŞARETLİ OLANLAR DA YÜKLENİYOR AMA AYRI İŞARETLENİYOR.
Yüklememek, sahibin bakıp karar vermesini engellerdi; sessizce "tamam"
saymak ise yayına bozuk görsel gönderebilirdi. İkisi de değil: yükle,
künyeye durumunu yaz.

🔴 KÜNYE ÜRÜN KİMLİĞİYLE BAĞLANIYOR. Dosya adı barkod (SKU); künye
Wix ürün kimliğini, adını ve Canva varlık kimliğini bir arada tutuyor.
Şablon "urun_gorseli" alanını buradan çözecek.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import canva  # noqa: E402

KOK = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun")
KESIM = KOK / "kesim"

kunye = json.loads((KOK / "kunye.json").read_text(encoding="utf-8"))
rapor = {r["dosya"]: r for r in
         json.loads((KESIM / "rapor.json").read_text(encoding="utf-8"))}

# barkod -> ürün bilgisi
urun = {}
for u in kunye:
    urun.setdefault(Path(u["dosya"]).stem, []).append(u)

cikti_yol = KOK / "canva-varlik.json"
mevcut = {}
if cikti_yol.exists():
    mevcut = {v["dosya"]: v for v in
              json.loads(cikti_yol.read_text(encoding="utf-8"))}

sonuc = []
dosyalar = sorted(KESIM.glob("*.png"))
print(f"{len(dosyalar)} kesim yüklenecek\n")

for i, d in enumerate(dosyalar, 1):
    if d.name in mevcut and mevcut[d.name].get("varlik_id"):
        print(f"  [{i:>2}/{len(dosyalar)}] {d.stem:<18} zaten yüklü")
        sonuc.append(mevcut[d.name])
        continue
    bilgi = urun.get(d.stem, [{}])[0]
    adlar = [u.get("ad", "") for u in urun.get(d.stem, [])]
    durum = rapor.get(d.name, {}).get("durum", "?")
    ad = (adlar[0] or d.stem)[:40]
    try:
        v = canva.varlik_yukle(d, ad=f"URUN {ad}")
        vid = ((v.get("asset") or v).get("id")) or v.get("id")
        sonuc.append({"dosya": d.name, "barkod": d.stem, "urun_adlari": adlar,
                      "wix_id": bilgi.get("id"), "varlik_id": vid,
                      "kesim_durumu": durum})
        isaret = "✅" if durum == "TAMAM" else "⚠"
        print(f"  [{i:>2}/{len(dosyalar)}] {isaret} {d.stem:<18} {vid}  {ad}")
    except Exception as e:  # noqa: BLE001
        print(f"  [{i:>2}/{len(dosyalar)}] ⛔ {d.stem:<18} {str(e)[:70]}")
        sonuc.append({"dosya": d.name, "barkod": d.stem,
                      "hata": str(e)[:150]})
    time.sleep(0.4)

cikti_yol.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                     encoding="utf-8")
yuklenen = sum(1 for s in sonuc if s.get("varlik_id"))
print(f"\nyüklendi={yuklenen}/{len(dosyalar)}   künye: {cikti_yol}")
