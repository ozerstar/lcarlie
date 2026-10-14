"""385 kesimin HANGI URUN oldugunu etiketten okur.

Dosya adlari DSC04301 / IMG_0050 gibi; hangi urun oldugu yalniz
gorseldeki etiketten anlasilir. Bu oturumda olculdu: model ambalaj
metnini GUVENILIR OKUYOR (720p videoda "HYDRAVIE" birebir okundu); yazma
tarafi guvenilmez ama burada yazma yok, okuma var.

🔴 SECENEKLI SORU, ACIK UCLU DEGIL. Modele "bu hangi urun?" diye acik
sormak uydurmaya davet olur. Bunun yerine 39 urunun adi veriliyor ve
"bu listeden HANGISI, yoksa BELIRSIZ" deniyor. Liste disi bir cevap
gelirse BELIRSIZ sayiliyor.

🔴 EMIN DEGILSE BELIRSIZ. Ayirt edilemeyen kareler (yalniz kapak,
bulanik, cok uzak) zorla bir urune atanmaz -- yanlis etiketlenmis bir
gorsel, etiketsiz gorselden daha zararlidir: sablona yanlis urun girer
ve kimse fark etmez.

🔴 KUCUK GONDERILIYOR. Etiket okumak icin 512 px yeter; 385 cagriyi tam
cozunurlukte gondermek bos para.
"""
import base64
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from PIL import Image  # noqa: E402

from jarvis import providers  # noqa: E402

KESIM = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-kesim")
KUTU = Path("/opt/lcarlie/jarvis-phase2/varliklar/kutu-gercegi")
CIKTI = KESIM / "tanima.json"

MODEL = "gemini-3.6-flash"   # 2.5-flash yeni kullanicilara KAPALI (404), Gemini bunu onerdi
ANAHTAR = providers.load_env().get("GEMINI_API_KEY")
UC = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
      f":generateContent?key={ANAHTAR}")

urunler = sorted(p.stem.upper() for p in KUTU.glob("*.json")
                 if not p.stem.startswith("_"))

ISTEM = (
    "Bu bir L'CARLIÉ kozmetik ürününün fotoğrafı. Ambalajın üzerindeki "
    "ürün adını OKU ve aşağıdaki listeden hangisi olduğunu söyle.\n\n"
    f"LİSTE: {', '.join(urunler)}\n\n"
    "KURALLAR:\n"
    "- Yalnızca listeden bir ad yaz, başka hiçbir şey yazma.\n"
    "- Etiket okunmuyorsa, emin değilsen ya da liste dışıysa: BELIRSIZ\n"
    "- Tahmin etme. Emin değilsen BELIRSIZ yaz.\n"
    "- Karede birden fazla ürün varsa en büyük/öndeki ürünü söyle."
)


def sor(yol: Path) -> tuple[str, dict]:
    im = Image.open(yol).convert("RGB")
    o = 512 / max(im.size)
    if o < 1:
        im = im.resize((max(1, int(im.width * o)), max(1, int(im.height * o))),
                       Image.LANCZOS)
    tampon = io.BytesIO()
    im.save(tampon, "JPEG", quality=85)
    b64 = base64.b64encode(tampon.getvalue()).decode()

    govde = {"contents": [{"parts": [
        {"text": ISTEM},
        {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 800}}
    istek = urllib.request.Request(
        UC, data=json.dumps(govde).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=90) as c:
        d = json.loads(c.read().decode())
    aday = (d.get("candidates") or [{}])[0]
    parcalar = ((aday.get("content") or {}).get("parts") or [])
    metin = " ".join(p.get("text", "") for p in parcalar).strip().upper()
    return metin, (d.get("usageMetadata") or {})


def main():
    dosyalar = sorted(KESIM.glob("*.png"))
    onceki = {}
    if CIKTI.exists():
        onceki = {k["dosya"]: k for k in
                  json.loads(CIKTI.read_text(encoding="utf-8"))}
    sonuc = []
    girdi_jeton = 0
    cikti_jeton = 0
    print(f"{len(dosyalar)} kesim tanınacak ({len(urunler)} ürün adayı)",
          flush=True)

    for i, d in enumerate(dosyalar, 1):
        if d.name in onceki and onceki[d.name].get("urun"):
            sonuc.append(onceki[d.name]); continue
        try:
            metin, kul = sor(d)
            girdi_jeton += (kul.get("promptTokenCount") or 0)
            cikti_jeton += (kul.get("candidatesTokenCount") or 0)
            eslesen = next((u for u in urunler
                            if re.sub(r"[^A-Z]", "", u) in
                            re.sub(r"[^A-Z]", "", metin)), None)
            urun = eslesen or "BELIRSIZ"
            sonuc.append({"dosya": d.name, "urun": urun, "ham_cevap": metin[:40]})
            if i % 20 == 0 or urun == "BELIRSIZ":
                print(f"  [{i}/{len(dosyalar)}] {d.stem:<34} {urun}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}] ⛔ {d.stem}: {str(e)[:70]}", flush=True)
            sonuc.append({"dosya": d.name, "urun": None, "hata": str(e)[:90]})
        time.sleep(0.25)
        if i % 25 == 0:
            CIKTI.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    CIKTI.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    sayim = {}
    for s in sonuc:
        sayim[s.get("urun") or "HATA"] = sayim.get(s.get("urun") or "HATA", 0) + 1
    print("\n=== SONUÇ")
    for u, n in sorted(sayim.items(), key=lambda x: -x[1]):
        print(f"  {u:<24} {n}")
    print(f"\njeton — girdi: {girdi_jeton}  çıktı: {cikti_jeton}")
    try:
        from jarvis import usage
        # 🔴 GİRDİ/ÇIKTI AYRI SAYILIR. Önce toplam jetonun tamamını
        # girdi yazıyordum; fiyat tablosunda girdi ve çıktı birim fiyatı
        # FARKLI (0.75 / 3.75) olduğu için bu maliyeti eksik gösterir.
        usage.record("gemini", MODEL, True, is_anahtari="urun_tanima",
                     kademe="hizli", prompt_tokens=girdi_jeton,
                     completion_tokens=cikti_jeton, ok=True)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
