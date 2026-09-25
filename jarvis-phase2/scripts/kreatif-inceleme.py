#!/usr/bin/env python3
"""KREATİF İNCELEME — üretilen görselleri Jarvis'in ekibi inceler.

Akıştaki yeri (sahip kararı, 21.09.2026):
    Jarvis tetikler -> Gemini/GPT üretir -> Jarvis'e döner ->
    *** JARVİS'İN EKİBİ VE DİREKTÖRLERİ İNCELER ***  -> sahibin onayına düşer

Bu betik ortadaki adımdır. İki ayrı şey yapar ve ikisini BİRBİRİNE KARIŞTIRMAZ:

  A) ÖLÇÜM   — aritmetik. Tartışılmaz, modele sorulmaz.
  B) GÖRÜŞ   — departman gözüyle değerlendirme. Model çıkarımıdır, ölçüm değildir.

🔴 AYRIM NEDEN ŞART. Görme modelinin bu işte nerede yalan söylediği ölçüldü:
gözle "HYORAVIE" yazdığı ve şişesi kreme kaydığı doğrulanmış bir kareye
"HYDRAVIE, beyaz" dedi; harf harf heceletince de aynı cevabı verdi. Yani
modelin "ambalaj düzgün" demesi kanıt DEĞİLDİR. Buna karşılık aynı karenin
gövde pikselleri ölçüldüğünde R-B farkı orijinalden +58 sapmış çıktı.

Bu yüzden: ambalajın RENGİ ve BOYU ölçülür, ambalajın YAZISI ölçülemez ve
öyle olduğu açıkça raporlanır -- "insan gözü gerekir" diye.

Çıkış: 0=incelendi · 1=hata · 2=teslim dosyası yok
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from jarvis import providers  # noqa: E402

GORME_MODEL = os.environ.get("KREATIF_GORME_MODELI", "gemini-3.5-flash")

# Gövde renginin orijinalden kabul edilebilir sapması (R-B birimi).
# 🔴 ÖLÇÜLEREK SEÇİLDİ, tahminle değil:
#     orijinal çekim          -13,4
#     kreme kaymış kare       +44,6   -> sapma +58,0   (gözle de belli)
#     nötr ışık kareleri      -12,1 / -12,0 -> sapma +1,3 / +1,4
#     sınırdaki kare          +16,6   -> sapma +30,0   (gözle zor fark ediliyor)
# 20 eşiği, gözün kaçırdığı son vakayı yakalar, temiz kareleri yakalamaz.
BEYAZ_SAPMA_ESIGI = 20.0

# Ürün karenin en az bu kadarını kaplamalı. Küçük çekimde etiket harfleri
# dağılıyor (ölçüldü).
URUN_ASGARI_ORAN = 0.35


def _cagir(parcalar: list[dict], azami: int = 3000) -> str:
    anahtar = providers.load_env().get("GEMINI_API_KEY")
    if not anahtar:
        raise RuntimeError("GEMINI_API_KEY yok")
    govde = {"generationConfig": {"maxOutputTokens": azami},
             "contents": [{"parts": parcalar}]}
    istek = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GORME_MODEL}"
        f":generateContent?key={anahtar}",
        data=json.dumps(govde).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=240) as cevap:
        d = json.loads(cevap.read().decode("utf-8"))
    aday = (d.get("candidates") or [{}])[0]
    return "".join(p.get("text") or ""
                   for p in ((aday.get("content") or {}).get("parts") or []))


def _resim(im: Image.Image, en: int = 900) -> dict:
    k = im.copy()
    k.thumbnail((en, en))
    t = io.BytesIO()
    k.save(t, "JPEG", quality=90)
    return {"inline_data": {"mime_type": "image/jpeg",
                            "data": base64.b64encode(t.getvalue()).decode()}}


def _json_cek(metin: str) -> dict | None:
    metin = metin.strip()
    if metin.startswith("```"):
        parcalar = metin.split("```")
        if len(parcalar) > 1:
            metin = parcalar[1].removeprefix("json").strip()
    bas, son = metin.find("{"), metin.rfind("}")
    if bas < 0 or son <= bas:
        return None
    try:
        return json.loads(metin[bas:son + 1])
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# A) ÖLÇÜM — aritmetik
# --------------------------------------------------------------------------

def urun_kutusu(im: Image.Image) -> tuple[int, int, int, int] | None:
    """Ürünün karedeki yeri (0-1000). Modelden GEOMETRİ istenir, METİN değil.

    🔴 Bu ayrım önemli: model harf okumada güvenilmez ama nesne yerini
    bulmada güvenilir çıktı (aynı çekimde üç koşuda ±2 birim).
    """
    soru = ('Return ONLY the bounding box of the cosmetic bottle/jar in this '
            'image as JSON: {"box_2d":[y0,x0,y1,x1]} normalised 0-1000. '
            'Nothing else.')
    try:
        metin = _cagir([_resim(im, 768), {"text": soru}])
    except (urllib.error.URLError, OSError, RuntimeError, ValueError):
        return None
    es = re.search(r'"box(?:_2d)?"\s*:\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',
                   metin)
    return tuple(int(v) for v in es.groups()) if es else None  # type: ignore[return-value]


def govde_sicakligi(im: Image.Image, kutu: tuple[int, int, int, int]) -> float | None:
    """Ürün gövdesinin R-B farkı. Beyaz negatife yakın, kreme kayınca artar.

    Gövdenin ORTA ŞERİDİ ölçülür: kenar pikselleri arka planla karışıyor,
    üst kısım kapak, alt kısım etiket. İlk denemede sabit kırpma kutusu
    kullanıldı ve sahneden sıcak piksel kapıp YANLIŞ ALARM verdi -- kutu
    ürünün gerçek yerinden alınmak zorunda.
    """
    G, Y = im.size
    y0, x0, y1, x1 = kutu
    px0, px1 = int(x0 / 1000 * G), int(x1 / 1000 * G)
    py0, py1 = int(y0 / 1000 * Y), int(y1 / 1000 * Y)
    gen, yuk = px1 - px0, py1 - py0
    if gen < 12 or yuk < 12:
        return None
    serit = im.crop((px0 + int(gen * 0.25), py0 + int(yuk * 0.55),
                     px1 - int(gen * 0.25), py0 + int(yuk * 0.75)))
    a = np.asarray(serit.convert("RGB")).astype(np.float32)
    parlak = a[a.mean(axis=2) > 150]
    if len(parlak) < 200:
        return None
    return float(parlak[:, 0].mean() - parlak[:, 2].mean())


def olcumler(im: Image.Image, referans_sicaklik: float | None) -> dict:
    kutu = urun_kutusu(im)
    o: dict = {"kutu": list(kutu) if kutu else None}
    if not kutu:
        o["not"] = "ürün kutusu bulunamadı — ölçüm yapılamadı (SORAMADIM)"
        return o
    y0, _x0, y1, _x1 = kutu
    o["urun_oran"] = round((y1 - y0) / 1000, 3)
    o["urun_oran_gecti"] = o["urun_oran"] >= URUN_ASGARI_ORAN
    sicaklik = govde_sicakligi(im, kutu)
    o["govde_rb"] = None if sicaklik is None else round(sicaklik, 1)
    if sicaklik is not None and referans_sicaklik is not None:
        sapma = sicaklik - referans_sicaklik
        o["beyaz_sapma"] = round(sapma, 1)
        o["beyaz_gecti"] = sapma <= BEYAZ_SAPMA_ESIGI
    return o


# --------------------------------------------------------------------------
# B) GÖRÜŞ — departman gözü
# --------------------------------------------------------------------------

ORTAK = """Sen L'CARLIÉ'nin reklam ekibindesin. Sana yayına ADAY bir reklam
görseli veriliyor. İşin övmek değil, yayına girmeden önce kusur bulmak.

Türkçe yaz. SADECE geçerli JSON döndür:
{"karar": "GECER | DUZELT | RED",
 "gerekce": "tek paragraf, somut",
 "kusurlar": ["gördüğün somut kusurlar; yoksa boş dizi"]}

DUZELT = fikir doğru ama bu kare düzeltilmeli. RED = bu kare kullanılamaz.

🔴 AMBALAJIN ÜZERİNDEKİ YAZININ DOĞRU OLUP OLMADIĞINI SÖYLEME. Ölçüldü:
görme modelleri o yazıyı tanıdıkları marka adına göre kafalarında düzeltiyor,
bu yüzden senin oradaki hükmün güvenilmez. O kontrol insana bırakıldı."""

GOZLER = (
    ("GRAFIK_TASARIM", "Grafik Tasarım", """Tasarım gözüyle bak:
- Yazı okunuyor mu? Telefonda küçük görünecek, satırlar fazla ince mi?
- Yazı arka planla çakışıyor mu, kenardan taşıyor mu, kesiliyor mu?
- Logo bir kez mi var, doğru yerde mi, ürünün üstündeki logoyla karışıyor mu?
- Boşluklar dengeli mi? Ürün karenin neresinde duruyor?
- Karenin kenarlarında kırpılma riski var mı (Instagram/Meta kırpması)?"""),
    ("KREATIF_DIREKTOR", "Kreatif Direktör", """Kreatif gözüyle bak:
- Bu kare BİR ŞEY söylüyor mu, yoksa herhangi bir kremin reklamı da olabilir mi?
- Akışta kaydırırken durdurur mu?
- Başlık ile görsel aynı şeyi mi anlatıyor, birbirinden kopuk mu?
- Sahne ürünle ilgili mi, yoksa sadece güzel bir oda mı?"""),
    ("MARKA", "Marka Stratejisti", """Marka gözüyle bak:
- Bu kare bir PREMIUM ürünün reklamı gibi duruyor mu? Ürün 1.200 TL ve
  kategorideki rakiplerin çoğundan pahalı; kare bu fiyatı haklı çıkarıyor mu?
- Ucuz, stok fotoğraf, jenerik ya da yapay duruyor mu?
- Marka kimliğiyle çelişen bir şey var mı?"""),
    ("MEVZUAT", "Mevzuat", """Mevzuat gözüyle bak. SADECE KAREDE GÖRÜNEN YAZIYA
bak (ambalajın üstündeki basılı metne değil):
- Karede, başlık ve alt satır DIŞINDA fazladan yazı var mı? (Model kendiliğinden
  kelime, rozet, mühür, yüzde, fiyat eklemiş olabilir — bunlar denetimden
  geçmemiştir ve en tehlikelisidir.)
- Görünen yazıda tedavi/iyileştirme iması var mı?
- Görselde tıbbi çağrışım var mı (önce-sonra, beyaz önlük, klinik, grafik)?"""),
)


def goz_incele(im: Image.Image, kod: str, ad: str, rubrik: str,
               ust: str, alt: str, aci: str) -> dict:
    baglam = (f"Karede OLMASI GEREKEN yazı şu ikisidir, başkası değil:\n"
              f"  başlık: {ust}\n  alt satır: {alt}\n"
              f"Bu karenin anlatması gereken açı: {aci}\n\n{rubrik}")
    try:
        metin = _cagir([_resim(im), {"text": ORTAK + "\n\n" + baglam}])
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as hata:
        return {"uye": ad, "departman": kod, "karar": "SORAMADIM",
                "gerekce": f"inceleme yapılamadı: {str(hata)[:120]}",
                "kusurlar": []}
    veri = _json_cek(metin)
    if not isinstance(veri, dict):
        return {"uye": ad, "departman": kod, "karar": "OKUNAMADI",
                "gerekce": metin[:200], "kusurlar": []}
    return {"uye": ad, "departman": kod,
            "karar": str(veri.get("karar", "?")).upper(),
            "gerekce": veri.get("gerekce", ""),
            "kusurlar": [str(x) for x in (veri.get("kusurlar") or [])][:6]}


# --------------------------------------------------------------------------
# DİREKTÖR KARARI — ölçüm görüşü EZER
# --------------------------------------------------------------------------

def direktor(olcum: dict, gorusler: list[dict]) -> tuple[str, str]:
    """Nihai karar.

    🔴 ÖLÇÜM GÖRÜŞÜ EZER. Bir kare aritmetikten kaldıysa, dört departman da
    "GECER" dese bile geçmez. Tersi geçerli değil: ölçümden geçmek, görüşlerin
    yerine geçmez.
    """
    kusur = []
    if olcum.get("beyaz_gecti") is False:
        kusur.append(f"ürünün beyazı orijinalden {olcum['beyaz_sapma']:+} birim "
                     "kaymış (sahne ışığı ambalajı boyamış)")
    if olcum.get("urun_oran_gecti") is False:
        kusur.append(f"ürün karenin yalnız %{olcum['urun_oran'] * 100:.0f}'ini "
                     "kaplıyor; küçük çekimde etiket harfleri dağılıyor")
    if kusur:
        return "DUZELT", "ÖLÇÜM: " + " · ".join(kusur)

    red = [g for g in gorusler if g["karar"] == "RED"]
    if red:
        return "RED", " · ".join(f"{g['uye']}: {g['gerekce'][:150]}" for g in red)
    duzelt = [g for g in gorusler if g["karar"] == "DUZELT"]
    if duzelt:
        return "DUZELT", " · ".join(f"{g['uye']}: {g['gerekce'][:150]}"
                                    for g in duzelt)
    soru = [g for g in gorusler if g["karar"] in ("SORAMADIM", "OKUNAMADI")]
    if len(soru) == len(gorusler):
        return "DUZELT", "hiçbir departman inceleyemedi (SORAMADIM) — karar yok"
    return "GECER", "ölçümler ve departman görüşleri temiz"


def main() -> int:
    ap = argparse.ArgumentParser(description="Üretilen kreatifleri ekip inceler")
    ap.add_argument("klasor", help="gorsel-uret.py'nin çıktı klasörü")
    ap.add_argument("--urun-gorsel", required=True,
                    help="orijinal çekim (renk referansı)")
    a = ap.parse_args()

    klasor = Path(a.klasor)
    tp = klasor / "teslim.json"
    if not tp.exists():
        print(f"teslim.json yok: {tp}", file=sys.stderr)
        return 2
    teslim = json.loads(tp.read_text(encoding="utf-8"))

    # Renk referansı: ORİJİNAL çekimin kendi gövde sıcaklığı.
    ref_im = Image.open(a.urun_gorsel).convert("RGB")
    ref_kutu = urun_kutusu(ref_im)
    referans = govde_sicakligi(ref_im, ref_kutu) if ref_kutu else None
    print(f"renk referansı (orijinal çekim): "
          f"{'ölçülemedi' if referans is None else round(referans, 1)}")

    sonuc = []
    for g in teslim.get("gorseller") or []:
        yol = klasor / g["dosya"]
        if not yol.exists():
            continue
        im = Image.open(yol).convert("RGB")
        olcum = olcumler(im, referans)
        gorusler = [goz_incele(im, kod, ad, rubrik,
                               g.get("ust_yazi", ""), g.get("alt_yazi", ""),
                               g.get("hangi_aci", ""))
                    for kod, ad, rubrik in GOZLER]
        karar, gerekce = direktor(olcum, gorusler)
        print(f"\n{g['dosya']} -> {karar}")
        print(f"  ölçüm: beyaz_sapma={olcum.get('beyaz_sapma')} "
              f"urun_oran={olcum.get('urun_oran')}")
        for gr in gorusler:
            isaret = {"GECER": "+", "DUZELT": "~", "RED": "!"}.get(gr["karar"], "?")
            print(f"  {isaret} {gr['uye']}: {gr['karar']} — {gr['gerekce'][:110]}")
        print(f"  DİREKTÖR: {gerekce[:200]}")
        sonuc.append({**g, "olcum": olcum, "inceleme": gorusler,
                      "direktor_karari": karar, "direktor_gerekce": gerekce})

    (klasor / "inceleme.json").write_text(
        json.dumps({"parti": klasor.name, "urun": teslim.get("urun"),
                    "renk_referansi": referans, "gorseller": sonuc,
                    "not": "ambalaj YAZISININ doğruluğu makineyle "
                           "doğrulanamaz; etiket-kontrol/ klasörüne insan "
                           "gözüyle bakılmalıdır"},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    gecen = sum(1 for s in sonuc if s["direktor_karari"] == "GECER")
    print(f"\n{gecen}/{len(sonuc)} kare direktörden geçti · "
          f"{klasor / 'inceleme.json'}")
    return 0


# Onay özeti `jarvis/kreatif_ozet.py` içindedir: aynı metni `loop.py` de
# üretiyor ve iki kopya tutmak, ikisinin zamanla ayrışması demekti.


if __name__ == "__main__":
    sys.exit(main())
