#!/usr/bin/env python3
"""GÖRSEL ÜRETİM — brief'ten teslim edilebilir reklam görseli.

ZİNCİRİN İKİNCİ YARISI. `kreatif-brief.py` brief'i, sahne tarifini ve
denetimden geçmiş Türkçe yazıları üretir. Bu betik ÜRÜN FOTOĞRAFINI + LOGOYU
görsel modeline gönderir; KESİM, MONTAJ ve TASARIM orada yapılır.

🔴 MİMARİ KARARI (sahip, 21.09.2026) — verbatim:
   "kesme işini sen yapmıcan sen sadece resmi göndereceksin; kesim, montaj,
    görsel işlerini gönderdiğin yer yapacak, tasarımla birlikte."

Önceki sürüm ürünü Pillow ile kendisi kesip diziyordu. O yol ölçüldü ve
zayıftı: şişe beyaz, çekim zemini açık gri, gövde-zemin farkı 11 birim,
zeminin kendi gradyanı 24 birim -> güvenilir kesit çıkmıyor, tüylendirilmiş
geçiş kullanmak zorunda kalınıyor ve koyu sahnede hale bırakıyordu.
Görsel modeli aynı işi temiz kesim ve gerçek gölgeyle yapıyor.

🔴 AMBALAJ HÂLÂ KORUNUR — ama artık İSTEMLE korunur, kodla değil.
Ürün metinden yeniden çizdirilmez: gerçek fotoğraf GİRDİ olarak verilir ve
"yeniden çizme, harflerine dokunma" şartı konur. Buna rağmen ölçülen şudur:

   ETİKET METNİ İSTEMDE YAZILMAZSA MODEL UYDURUR.
   İlk deneme: etikette "HYORAVIE" yazdı (doğrusu HYDRAVIE).
   Etiket satırları isteme eklenince: HYDRAVIE ve L'CARLIÉ doğru çıktı.

Bu yüzden `varliklar/urun/<urun>.etiket.txt` dosyası VARSA isteme aynen
eklenir. Yoksa uyarı basılır -- sessizce geçilmez.

🔴 KALAN KUSUR, ÖLÇÜLDÜ VE KAPANMADI: şişenin ince puntolu satırları
("Herbal Moisturizing Cream", "1.69 fl oz") yakın planda bozuluyor;
bir koşuda "1.69" -> "1.89" oldu. Teslim boyutunda (1080 px karede şişe
~%30) bu satırlar ~8 piksel yüksekliğinde ve okunmuyor. Ambalajın YAKIN PLAN
kullanılacağı bir işte bu yol kullanılmamalıdır.

Çıkış: 0=görseller üretildi · 1=hata · 2=brief yok · 3=kısmi
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from PIL import Image, ImageOps  # noqa: E402


VARLIK = KOK / "varliklar"
GORSEL_SAGLAYICI = "chatgpt_web_work"
GORSEL_MODEL = "Kullanıcının Chrome oturumundaki GPT"
ORANLAR = ("1:1", "4:5", "9:16", "16:9")


# 🔴 Bu şart KOD tarafından her isteme eklenir, modelden istenmez.
# Ürünü koruyan tek şey bu metin olduğu için istemin gövdesine karışmaz.
URUN_MUHRU = """
THE PRODUCT IS SACRED. Cut the product out of IMAGE 1 and place it into the new
scene WITHOUT redrawing it. Keep its exact shape, proportions, colour, finish
and cap. Every letter and number printed on the packaging must stay EXACTLY as
it appears in IMAGE 1 — do not restyle, re-letter, translate or re-typeset any
of it.

Two things are measured and cause rejection:
  1. RENDER THE PRODUCT LARGE — it must occupy at least 40% of the frame
     height — and sharp, so its label stays crisp. Small renders come out with
     scrambled lettering.
  2. KEEP THE PRODUCT'S OWN COLOUR. The bottle body is WHITE. Neutral white
     balance on the product; the scene's light must NOT tint it cream, beige,
     gold or any warm shade, even if the surrounding scene is warm.
{etiket}
If any text on the packaging differs from IMAGE 1, the image is rejected.
"""

ETIKET_BASLIK = """
For your verification, the packaging is printed with exactly these lines:
{satirlar}
"""

ISTEM = """IMAGE 1 = the real product photograph. IMAGE 2 = the brand logo.

Create a FINISHED {oran} advertising image for this cosmetic product.
You do the cut-out, the montage and the full design.
{muhur}
SCENE: {sahne}

SCENE LIGHTING — STRICT: soft, cool, neutral overcast daylight. No golden hour,
no warm tungsten, no sunset, no amber glow, no strong colour cast of any kind.
🔴 Measured: warm scene light tinted the white bottle cream AND scrambled the
lettering on its label. Neutral light keeps both intact.

DESIGN: place the logo from IMAGE 2 once, at the top. Build a distinctive,
high-end editorial beauty campaign with a clear visual idea tied to the
ingredient/story in the scene. Use tactile materials, considered depth,
intentional light and a composed focal point. Avoid generic stock-ad layouts,
plain gradients, floating-product clichés and familiar water-splash tropes.
Keep the frame calm and art-directed, with purposeful negative space; no
badges, starbursts, price tags, arrows or decorative clutter.

TEXT to typeset on the image. Copy these characters EXACTLY, including Turkish
letters (ı İ ğ ş ç ö ü). Do not translate, do not rephrase, do not add words:
   headline: {ust}
   subline:  {alt}
TYPOGRAPHY IS A HARD REQUIREMENT: give the headline a refined, characterful
editorial display face and pair it with a clean, premium grotesk for the
supporting line. Do not use a default heavy geometric bold or template-style
type. Set deliberate line breaks, precise kerning, optical alignment and a
clear hierarchy; keep the support line comfortably readable on a phone with
a confident medium weight and strong contrast. Make the typography feel
custom art-directed for a premium skincare campaign, not pasted on. Keep every
text line and the logo at least 8% inside every crop edge.
Apart from the supplied logo and these two exact lines, there must be NO other
text anywhere in the image.
{itirazlar}"""


def etiket_satirlari(urun_yolu: Path) -> str:
    """Ambalajın üzerinde ne yazdığı — varsa isteme aynen eklenir.

    🔴 Bu dosya yoksa model etiketi UYDURUR ("HYORAVIE"). Sessiz geçilmez;
    çağıran uyarılır.
    """
    yan = urun_yolu.with_suffix(".etiket.txt")
    if not yan.exists():
        return ""
    satirlar = [s.strip() for s in yan.read_text(encoding="utf-8").splitlines()
                if s.strip()]
    if not satirlar:
        return ""
    return ETIKET_BASLIK.format(
        satirlar="\n".join(f"   {s}" for s in satirlar))


# Hangi urunun itirazlari okunacak; main() parti adindan doldurur.
_URUN_ONEKI = ""


def chatgpt_web_gorsel(istem: str, oran: str, girdi_dosyalari: list[Path],
                        zaman_asimi_s: int = 1800) -> Image.Image:
    from jarvis import tarayici as browser_queue
    is_ = browser_queue.enqueue_browser_task(
        istem, "chatgpt_image", input_files=[str(p.resolve()) for p in girdi_dosyalari],
        requested_by="tasarim-departmani",
        idempotency_key="gptwork:" + uuid.uuid4().hex)
    print(f"GPT Work Chrome kuyruğuna eklendi: iş {is_['is_id']}", flush=True)
    bitis = time.monotonic() + zaman_asimi_s
    while time.monotonic() < bitis:
        sonuc = browser_queue.isi_sonucu(is_["is_id"])
        if sonuc:
            durum = sonuc.get("durum")
            if durum in ("BITTI", "SUNULDU"):
                dosyalar = sonuc.get("sonuc_dosyalari") or []
                if not dosyalar:
                    raise RuntimeError(f"ChatGPT web işi {is_['is_id']} bitti ama görsel dönmedi")
                kok = browser_queue.CIKTI_KOK.resolve()
                yol = (kok / str(dosyalar[0])).resolve()
                if kok not in yol.parents or not yol.is_file():
                    raise RuntimeError(f"ChatGPT web işi {is_['is_id']} sonucu sunucuda bulunamadı")
                im = Image.open(yol).convert("RGB")
                hedef = {"1:1": (1024, 1024), "4:5": (1024, 1280),
                         "9:16": (1024, 1820), "16:9": (1820, 1024)}[oran]
                return ImageOps.fit(im, hedef, method=Image.Resampling.LANCZOS)
            if durum in ("HATA", "INSAN_GEREKLI"):
                raise RuntimeError(f"ChatGPT web işi {is_['is_id']} {durum}: {sonuc.get('hata') or 'insan müdahalesi gerekli'}")
        time.sleep(10)
    raise RuntimeError(f"ChatGPT web işi {is_['is_id']} {zaman_asimi_s} sn içinde tamamlanmadı; Jarvis tarayıcı kuyruğunu kontrol edin")

def montaj_uret(sahne: str, ust: str, alt: str, oran: str,
                urun_yolu: Path, logo_yolu: Path, etiket: str) -> Image.Image:
    itiraz_blok = ""
    try:
        from jarvis.kreatif_itiraz import acik_itirazlar_metni
        ham = acik_itirazlar_metni(_URUN_ONEKI or "")
        if ham:
            itiraz_blok = "\n\nOWNER'S OPEN OBJECTIONS: \n" + ham
    except Exception:  # noqa: BLE001 - feedback store failure must not block generation
        pass
    istem = ISTEM.format(oran=oran, sahne=sahne.strip(), ust=ust or "(başlık yok)",
        alt=alt or "(alt satır yok)", itirazlar=itiraz_blok,
        muhur=URUN_MUHRU.format(etiket=etiket))
    return chatgpt_web_gorsel(istem, oran, [urun_yolu, logo_yolu])

# ══════════════════════════════════════════════════════════════════════════
# 🔴 OTOMATİK AMBALAJ DENETİMİ DENENDİ VE ÇALIŞMIYOR — KALDIRILDI
#
# Fikir şuydu: kare üretildikten sonra görme modeline geri gösterilip
# etiketi okuması istenecek, yanlışsa kare yeniden üretilecekti.
#
# ÖLÇÜM: gözle "HYORAVIE" yazdığı ve şişesi kreme kaydığı doğrulanmış bir
# kare doğrulayıcıya verildi. Cevap:  urun='HYDRAVIE'  renk='beyaz'.
# "Harfi harfine yaz, düzeltme, yanlış yazılmış olabilir" denildi; harf harf
# hecelemesi istendi. Cevap yine "H-Y-D-R-A-V-I-E", emin_miyim='yuksek'.
# Aynı soru bilinen DOĞRU kareye de aynı cevabı verdi -- yani doğrulayıcı
# iki kareyi AYIRT EDEMİYOR.
#
# Sebep: görme modeli gördüğünü değil, BEKLEDİĞİNİ okuyor. Marka adını
# tanıyor ve bozuk harfi kafasında düzeltiyor.
#
# Bu yüzden kod bu denetimi YAPMIYOR. Çalışmayan bir kapı, olmayan bir
# kapıdan kötüdür: "ambalaj denetlendi" diye rapor eder ve bozuk etiket
# yayına gider. Yerine `etiket-kontrol/` klasörüne yakın plan kırpıntılar
# yazılır ve İNSAN GÖZÜYLE bakılması istenir.
# ══════════════════════════════════════════════════════════════════════════

_KULLANILMIYOR_DOGRULAMA = """Read the text printed on the product packaging in this
advertising image. Ignore the headline and the logo at the top of the image —
only read what is printed ON the bottle/jar itself.

Answer with STRICT JSON and nothing else. Use SINGLE braces:
{"marka": "the brand wordmark on the packaging, exactly as rendered",
 "urun": "the product name on the coloured label, exactly as rendered",
 "beyaz_mi": "is the bottle body WHITE, or tinted cream/beige/other? answer 'beyaz' or the colour you see"}

Transcribe LITERALLY what is rendered, letter by letter, even if it looks like
a misspelling. Do not correct it. Do not guess what it was meant to say."""


def etiket_yakin_plan(kare: Image.Image) -> Image.Image:
    """Ambalajı büyütülmüş olarak ayrı kaydeder.

    Amacı denetimdir: teslim boyutunda okunmayan etiket, burada okunur ve
    modelin harfleri bozup bozmadığı GÖZLE kontrol edilebilir. Bu dosya
    müşteriye gitmez, kontrol içindir.
    """
    g, y = kare.size
    return kare.crop((int(g * 0.30), int(y * 0.45), int(g * 0.70), int(y * 0.92))) \
               .resize((900, int(900 * (y * 0.47) / (g * 0.40))), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Brief'ten reklam görseli üretir")
    ap.add_argument("brief", help="kreatif-brief.py'nin ürettiği .json")
    ap.add_argument("--urun-gorsel", required=True, help="gerçek ürün çekimi")
    ap.add_argument("--logo", default=str(VARLIK / "logo" / "lcarlie-logo.png"))
    ap.add_argument("--cikti", default=None)
    ap.add_argument("--adet", type=int, default=0, help="0 = brief'teki hepsi")
    a = ap.parse_args()

    bp = Path(a.brief)
    if not bp.exists():
        print(f"brief yok: {bp}", file=sys.stderr)
        return 2
    # Itiraz kayitlari parti adiyla tutuluyor; parti adi brief dosya
    # adiyla ayni onekle basliyor ("hydravie-20260921-1307").
    global _URUN_ONEKI
    _URUN_ONEKI = bp.stem.split("-")[0]

    brief = json.loads(bp.read_text(encoding="utf-8"))
    gorseller = brief.get("gorseller") or []
    if a.adet:
        gorseller = gorseller[:a.adet]
    if not gorseller:
        print("brief'te görsel yok", file=sys.stderr)
        return 2

    urun_yolu, logo_yolu = Path(a.urun_gorsel), Path(a.logo)
    etiket = etiket_satirlari(urun_yolu)
    if etiket:
        print(f"etiket metni verildi: {urun_yolu.with_suffix('.etiket.txt').name}")
    else:
        print("GPT web üretimi kullanılır; ürün etiketi insan incelemesinden geçmelidir.")

    cikti = Path(a.cikti) if a.cikti else bp.parent / (bp.stem + "-gorseller")
    (cikti / "etiket-kontrol").mkdir(parents=True, exist_ok=True)

    teslim, hata = [], 0
    for n, g in enumerate(gorseller, 1):
        oran = g.get("oran") if g.get("oran") in ORANLAR else "1:1"
        yer = g.get("yerlesim") or {}
        tip = yer.get("katman_4_tipografi") or {}
        ust = g.get("ust_yazi") or tip.get("ust_yazi") or ""
        alt = g.get("alt_yazi") or tip.get("alt_yazi") or ""
        # Sahne tarifi zaten "ürünsüz arka plan" diye yazılmıştı; artık ürün
        # de karede olacağı için mühürdeki yasak cümlesi kullanılmaz --
        # sahnenin yalnız ortam kısmı alınır.
        sahne = str(g.get("sahne_istemi") or "").split("NEGATIVE")[0].strip()
        geri_bildirim = [str(x).strip() for x in (g.get("onceki_inceleme_notlari") or [])
                         if str(x).strip()]
        if geri_bildirim:
            sahne += "\n\nMANDATORY REVISION NOTES FROM THE PREVIOUS DESIGN REVIEW:\n" + "\n".join(
                "- " + x for x in geri_bildirim[:8])
            sahne += "\nResolve every listed issue in this new composition."
        try:
            kare = montaj_uret(sahne, ust, alt, oran, urun_yolu, logo_yolu, etiket)
        except (OSError, RuntimeError, ValueError) as e:
            print(f"{n}. HATA: {str(e)[:160]}", file=sys.stderr)
            hata += 1
            continue

        ad = cikti / f"{n:02d}-{oran.replace(':', 'x')}.jpg"
        kare.save(ad, quality=93)
        etiket_yakin_plan(kare).save(cikti / "etiket-kontrol" / f"{n:02d}.jpg",
                                     quality=93)
        print(f"{n}. {g.get('ad','?')} · {oran} -> {ad.name} {kare.size}")
        teslim.append({"dosya": ad.name, "sahne": g.get("ad"), "oran": oran,
                       "ust_yazi": ust, "alt_yazi": alt,
                       "hangi_aci": g.get("hangi_aci"),
                       "onceki_inceleme_notlari": geri_bildirim,
                       "inceleme_durumu": "DEPARTMAN_INCELEMESI_BEKLIYOR",
                       "gorsel_uretme_yontemi": "kullanici_gpt_work_chrome"})
        time.sleep(2)

    (cikti / "teslim.json").write_text(
        json.dumps({"urun": (brief.get("urun") or {}).get("urun_adi"),
                    "brief": bp.name, "gorseller": teslim,
                    "saglayici": GORSEL_SAGLAYICI, "model": GORSEL_MODEL,
                    "yontem": "kullanıcının Chrome GPT Work oturumunda üretilmiş taslak; insan ve departman incelemesi bekliyor",
                    "kontrol": "🔴 YAYINDAN ÖNCE JARVIS TASARIM EKİBİ VE İNSAN GÖZÜYLE BAKILMALI: "
                               "etiket-kontrol/ içindeki yakın planlarda "
                               "ambalaj yazısı doğru mu, şişenin beyazı "
                               "kaymış mı? Otomatik denetim denendi ve "
                               "çalışmıyor (görme modeli bozuk harfi "
                               "kafasında düzeltiyor)."},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(teslim)} görsel · {cikti}")
    print(f"🔎 ambalaj denetimi: {cikti / 'etiket-kontrol'}")
    return 0 if not hata else 3


if __name__ == "__main__":
    sys.exit(main())

