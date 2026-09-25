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
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from PIL import Image  # noqa: E402

from jarvis import providers  # noqa: E402

VARLIK = KOK / "varliklar"
GORSEL_MODEL = os.environ.get("KREATIF_GORSEL_MODELI", "gemini-3-pro-image")
ORANLAR = ("1:1", "4:5", "9:16", "16:9")


def _resim_parcasi(yol: Path, en: int = 1400) -> dict:
    """Dosyayı modele gönderilecek parçaya çevirir.

    Küçültme şart: ham PNG 1,8 MB ve base64'e çevrilince istek zaman aşımına
    uğruyor (ölçüldü). 1400 px ürün etiketinin okunabilir kalmasına yetiyor.
    """
    im = Image.open(yol).convert("RGB")
    im.thumbnail((en, en))
    tampon = io.BytesIO()
    im.save(tampon, "JPEG", quality=95)
    return {"inline_data": {"mime_type": "image/jpeg",
                            "data": base64.b64encode(tampon.getvalue()).decode()}}


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

DESIGN: place the logo from IMAGE 2 once, at the top. Leave clean, uncluttered
space for the headline. Elegant, minimal, modern premium cosmetics advertising
layout. Calm and quiet — not busy, not salesy, no badges, no starbursts, no
price tags, no arrows.

TEXT to typeset on the image. Copy these characters EXACTLY, including Turkish
letters (ı İ ğ ş ç ö ü). Do not translate, do not rephrase, do not add words:
   headline: {ust}
   subline:  {alt}
Use a clean geometric sans-serif. Apart from the logo and these two lines,
there must be NO other text anywhere in the image.
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


# Uretim cozunurlugu. "1K" ile AYNI PARA oldugu icin varsayilan 2K.
GORSEL_BOYUT = os.environ.get("GORSEL_BOYUT", "2K")

# Hangi urunun itirazlari okunacak; main() parti adindan doldurur.
_URUN_ONEKI = ""


def montaj_uret(sahne: str, ust: str, alt: str, oran: str,
                urun_yolu: Path, logo_yolu: Path, etiket: str) -> Image.Image:
    anahtar = providers.load_env().get("GEMINI_API_KEY")
    if not anahtar:
        raise RuntimeError("GEMINI_API_KEY yok")
    # 🔴 Sahibin ACIK itirazlari uretimin ONUNE gecer. Okunamazsa uretim
    # durmaz -- itiraz kaydi erisilemez diye gorsel uretmemek, calisan
    # bir hatti calismayan bir hatta cevirirdi.
    itiraz_blok = ""
    try:
        from jarvis.kreatif_itiraz import acik_itirazlar_metni
        ham = acik_itirazlar_metni(_URUN_ONEKI or "")
        if ham:
            itiraz_blok = ("\n\nOWNER'S OPEN OBJECTIONS on earlier images of "
                           "this product. You MUST NOT repeat these mistakes:\n"
                           + ham)
    except Exception:  # noqa: BLE001 - itiraz okunamazsa uretim durmaz
        itiraz_blok = ""

    istem = ISTEM.format(
        oran=oran, sahne=sahne.strip(), ust=ust or "(başlık yok)",
        alt=alt or "(alt satır yok)",
        itirazlar=itiraz_blok,
        muhur=URUN_MUHRU.format(etiket=etiket))
    govde = {"generationConfig": {"imageConfig": {"aspectRatio": oran,
                                                 "imageSize": GORSEL_BOYUT}},
             "contents": [{"parts": [_resim_parcasi(urun_yolu),
                                     _resim_parcasi(logo_yolu, 512),
                                     {"text": istem}]}]}
    istek = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GORSEL_MODEL}"
        f":generateContent?key={anahtar}",
        data=json.dumps(govde).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=420) as cevap:
        d = json.loads(cevap.read().decode("utf-8"))
    # 🔴 DEFTERE YAZ. Bu cagri `providers.generate()` yolundan gecmiyor,
    # yani defteri besleyen kanca burada YOK. Yazilmazsa gorsel maliyeti
    # panelde hic gorunmez -- nitekim gorunmuyordu.
    try:
        from jarvis import usage as _usage
        _u = d.get("usageMetadata") or {}
        _usage.record(
            "gemini", GORSEL_MODEL, True,
            is_anahtari="kreatif_gorsel", kademe="gorsel",
            prompt_tokens=_u.get("promptTokenCount"),
            completion_tokens=(_u.get("candidatesTokenCount")
                               or _u.get("totalTokenCount")),
            elapsed_s=None, ok=True)
    except Exception:  # noqa: BLE001 - defter uretimi durduramaz
        pass

    aday = (d.get("candidates") or [{}])[0]
    for p in ((aday.get("content") or {}).get("parts") or []):
        veri = p.get("inlineData") or p.get("inline_data")
        if veri and veri.get("data"):
            return Image.open(io.BytesIO(base64.b64decode(veri["data"]))).convert("RGB")
    raise RuntimeError(f"model görsel döndürmedi ({aday.get('finishReason')})")


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
        print("🔴 UYARI: etiket metni dosyası yok "
              f"({urun_yolu.with_suffix('.etiket.txt').name}). Model ambalaj "
              "yazısını UYDURABİLİR — ilk ölçümde 'HYORAVIE' yazdı.",
              file=sys.stderr)

    cikti = Path(a.cikti) if a.cikti else bp.parent / (bp.stem + "-gorseller")
    (cikti / "etiket-kontrol").mkdir(parents=True, exist_ok=True)

    teslim, hata = [], 0
    for n, g in enumerate(gorseller, 1):
        oran = g.get("oran") if g.get("oran") in ORANLAR else "1:1"
        yer = g.get("yerlesim") or {}
        tip = yer.get("katman_4_tipografi") or {}
        ust = tip.get("ust_yazi") or g.get("ust_yazi") or ""
        alt = tip.get("alt_yazi") or g.get("alt_yazi") or ""
        # Sahne tarifi zaten "ürünsüz arka plan" diye yazılmıştı; artık ürün
        # de karede olacağı için mühürdeki yasak cümlesi kullanılmaz --
        # sahnenin yalnız ortam kısmı alınır.
        sahne = str(g.get("sahne_istemi") or "").split("NEGATIVE")[0].strip()
        try:
            kare = montaj_uret(sahne, ust, alt, oran, urun_yolu, logo_yolu, etiket)
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as e:
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
                       "hangi_aci": g.get("hangi_aci")})
        time.sleep(2)

    (cikti / "teslim.json").write_text(
        json.dumps({"urun": (brief.get("urun") or {}).get("urun_adi"),
                    "brief": bp.name, "gorseller": teslim,
                    "yontem": "ürün fotoğrafı + logo görsel modeline verildi; "
                              "kesim, montaj ve tasarım orada yapıldı",
                    "kontrol": "🔴 YAYINDAN ÖNCE İNSAN GÖZÜYLE BAKILMALI: "
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
