"""GERCEK CEKIM kesimlerini Canva'ya URUN ADIYLA yukler.

Onceki yukleme Wix gorsellerindendi ve onlar FILIGRANLIYDI (OPTYWAVE'de
arka planda "ARLI" hayaleti kaldi). Gercek cekimler kesildi, tanindi,
ama yuklenmedi -- yani sablonlarin kullanabilecegi iyi varlik Canva'da
YOK. Bu betik onu kapatiyor.

🔴 HEPSINI YUKLEMIYORUZ, UCE AYIRIYORUZ:
  URUN     -> tanimlanmis urun kesimi. Sablonun `urun_gorseli` alani
              bunlari kullanacak. Ad: "URUN <ADI> <n>"
  MODEL    -> ham-kaynak klasoru: bu bir INSAN cekimi, urun degil.
              Sahip "gerçek insan görselleri kullanman daha güzel olur"
              demisti; modelli kreatif icin ayri isimle duruyor.
  BELIRSIZ -> tanınamayan urun kareleri (cogu detay/yakin plan).
              YUKLENMIYOR: adi olmayan varlik kitaplikta cop olur,
              kimse hangisi oldugunu bilemez.

🔴 AYNI URUNUN COK KARESI VAR. En buyuk uc kare yukleniyor; hepsini
yuklemek kitapligi sisirir ve secim yapmayi zorlastirir. Buyukluk
olcut olarak secildi cunku kesim sonrasi buyuk kare = urun kadraja
daha cok oturmus demek.
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import canva  # noqa: E402

KOK = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun")
KESIM = KOK / "cekim-kesim"
CIKTI = KOK / "cekim-canva.json"
URUN_BASINA = 3

tanima = {t["dosya"]: t for t in
          json.loads((KESIM / "tanima.json").read_text(encoding="utf-8"))}

urun_kareleri = defaultdict(list)
model_kareleri = []
for p in sorted(KESIM.glob("*.png")):
    kayit = tanima.get(p.name, {})
    urun = kayit.get("urun")
    if p.name.startswith("ham-kaynak--"):
        model_kareleri.append(p)
    elif urun and urun != "BELIRSIZ":
        urun_kareleri[urun].append(p)

# Her üründen en büyük N kare
for u in urun_kareleri:
    urun_kareleri[u] = sorted(urun_kareleri[u],
                              key=lambda x: x.stat().st_size,
                              reverse=True)[:URUN_BASINA]
model_kareleri = sorted(model_kareleri, key=lambda x: x.stat().st_size,
                        reverse=True)[:20]

mevcut = {}
if CIKTI.exists():
    mevcut = {v["dosya"]: v for v in
              json.loads(CIKTI.read_text(encoding="utf-8"))}

sonuc = []
is_listesi = ([("URUN", u, p) for u, ps in sorted(urun_kareleri.items())
               for p in ps]
              + [("MODEL", "MODEL", p) for p in model_kareleri])
print(f"{len(urun_kareleri)} ürün · {sum(len(v) for v in urun_kareleri.values())} "
      f"ürün karesi · {len(model_kareleri)} model karesi = "
      f"{len(is_listesi)} yükleme\n")

sayac = defaultdict(int)
for i, (tur, ad, p) in enumerate(is_listesi, 1):
    if p.name in mevcut and mevcut[p.name].get("varlik_id"):
        sonuc.append(mevcut[p.name]); continue
    sayac[ad] += 1
    etiket = (f"URUN {ad} {sayac[ad]}" if tur == "URUN"
              else f"MODEL cekim {sayac[ad]}")
    try:
        v = canva.varlik_yukle(p, ad=etiket)
        vid = ((v.get("asset") or v).get("id")) or v.get("id")
        sonuc.append({"dosya": p.name, "tur": tur, "urun": ad,
                      "etiket": etiket, "varlik_id": vid})
        if i % 15 == 0 or tur == "MODEL":
            print(f"  [{i}/{len(is_listesi)}] {etiket:<28} {vid}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"  [{i}] ⛔ {p.name}: {str(e)[:70]}", flush=True)
        sonuc.append({"dosya": p.name, "tur": tur, "urun": ad,
                      "hata": str(e)[:120]})
    time.sleep(0.35)
    if i % 20 == 0:
        CIKTI.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                         encoding="utf-8")

CIKTI.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                 encoding="utf-8")
ok = sum(1 for s in sonuc if s.get("varlik_id"))
print(f"\nyüklendi {ok}/{len(is_listesi)}   künye: {CIKTI}")
