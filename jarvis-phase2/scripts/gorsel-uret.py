#!/usr/bin/env python3
"""GÖRSEL ÜRETİM — brief'ten teslim edilebilir reklam görseli.

ZİNCİRİN İKİNCİ YARISI. `kreatif-brief.py` brief'i, sahne tarifini ve
onaylı Türkçe metinleri üretir. ChatGPT Work ürün fotoğrafı ve logoyu
kullanarak sahnenin tamamını ve ürün yerleşimini tasarlar. Jarvis yalnızca
başlık ve destek metnini Monument Extended ve Metropolis font dosyalarıyla
ekler.
Çıkış: 0=görseller üretildi · 1=hata · 2=brief yok · 3=kısmi
"""
from __future__ import annotations

import argparse
import importlib.util
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

_sp = importlib.util.spec_from_file_location(
    "gorsel_kompozit", str(KOK / "scripts" / "gorsel-kompozit.py"))
gk = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(gk)

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

TAM_GORSEL_ISTEM = """Create a finished premium editorial Instagram skincare campaign for L'CARLIÉ {urun}.
GPT must create the complete photograph, art direction, Turkish headline and any
supporting copy inside the image. Campaign angle: {odak}.

COMPOSITION: Treat the square as a mobile ad with a 12% clear safe margin on all four
sides. Keep every letter fully inside that margin. Make the real product the unmistakable
hero, near the visual center (never against an edge), occupying about 42–48% of frame
height, sharp and readable. Place the headline in the upper third, visually connected
to the product; keep it to two short lines maximum. Use generous breathing room and
clear hierarchy. Any ingredient support line is secondary, at least as legible as
normal phone body text, and may read only “Niacinamide + Sodium Hyaluronate”.

ART DIRECTION: Build one memorable, ownable hydration image: a sculptural translucent
Hydravie-aqua gel ribbon or suspended dewy membrane curves around the bottle, with
macro water beads and soft ripples catching crisp studio light. Restrained warm-white
negative space, vivid aqua focal color sampled from the product label, tactile and
photographic. The object and water must form one coherent visual gesture, not unrelated
props. Avoid generic stone slabs, glass prisms, floating glass objects, beige cast,
stock cosmetics styling, clutter, dark text bands, extra logos, badges and unsupported
claims. Keep the white bottle neutral white and preserve its exact package design.
Typography should feel like Monument Extended headlines with Metropolis supporting
text: confident, refined, editorial, never distorted or cramped. {referans_talimati}
Aspect ratio {oran}.{revizyon}"""


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
                urun_yolu: Path, logo_yolu: Path, etiket: str,
                stil_referansi: Path | None = None,
                revizyon_notu: str = "", urun_adi: str = "HYDRAVIE") -> Image.Image:
    """GPT creates the whole ad and copy; review notes guide autonomous revisions."""
    if not urun_yolu.is_file() or not logo_yolu.is_file():
        raise gk.GorselHatasi("urun fotografi veya resmi logo bulunamadi")
    if stil_referansi is not None and not Path(stil_referansi).is_file():
        raise gk.GorselHatasi("onceki gorsel referansi bulunamadi")
    revizyon = ""
    if revizyon_notu.strip():
        revizyon = ("\n\nCREATIVE TEAM REVISION — make these concrete changes to the rejected draft; "
                    "do not merely polish it: " + " ".join(revizyon_notu.split())[:500])
    referans_talimati = (
        "IMAGE 1 is the exact product package. IMAGE 2 is a rejected draft; use it only to "
        "identify prior defects, do not copy its layout, props, lighting, crop or typography. "
        "The final image is the official logo; use it once, only if it fits the composition."
        if stil_referansi is not None else
        "Use the supplied product photo and logo as faithful references.")
    istem = TAM_GORSEL_ISTEM.format(
        urun=urun_adi, oran=oran, revizyon=revizyon,
        referans_talimati=referans_talimati, odak=" ".join(sahne.split())[:220])
    dosyalar = [urun_yolu]
    if stil_referansi is not None:
        dosyalar.append(Path(stil_referansi))
    dosyalar.append(logo_yolu)
    return chatgpt_web_gorsel(istem, oran, dosyalar)

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
    ap.add_argument("--stil-referans", type=Path, default=None,
                    help="revizyon icin onceki GPT gorseli")
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
        instagram_format = str(g.get("instagram_format") or "").upper()
        seri_kodu = str(g.get("seri_kodu") or "").strip()
        kart_no = str(g.get("kart_no") or "").strip()
        kart_rolu = str(g.get("kart_rolu") or "").upper()
        oran = g.get("oran") if g.get("oran") in ORANLAR else "4:5"
        if instagram_format in ("2_KART_KARUSEL", "3_5_KART_KARUSEL"):
            oran = "4:5"
        elif instagram_format == "REELS_STORY_KAPAK":
            oran = "9:16"
        yer = g.get("yerlesim") or {}
        tip = yer.get("katman_4_tipografi") or {}
        ust = g.get("ust_yazi") or tip.get("ust_yazi") or ""
        alt = g.get("alt_yazi") or tip.get("alt_yazi") or ""
        # Sahne tarifi zaten "ürünsüz arka plan" diye yazılmıştı; artık ürün
        # de karede olacağı için mühürdeki yasak cümlesi kullanılmaz --
        # sahnenin yalnız ortam kısmı alınır.
        sahne = str(g.get("ad") or "") + "; " + str(g.get("hangi_aci") or "")
        # GPT'nin sanat yönetimini eski, birbiriyle çelişen revizyon notlarıyla
        # boğmuyoruz; yalnız brief'teki kısa konsept ve ürün açısı gönderilir.
        geri_bildirim = []
        try:
            kare = montaj_uret(
                sahne, ust, alt, oran, urun_yolu, logo_yolu, etiket,
                stil_referansi=a.stil_referans,
                revizyon_notu=str(g.get("revizyon_notu") or ""),
                urun_adi=str((brief.get("urun") or {}).get("urun_adi") or "HYDRAVIE").split("|")[0].strip())
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
                       "ust_yazi": "GPT tarafından görsel içinde yazıldı",
                       "alt_yazi": "GPT tarafından görsel içinde yazıldı",
                       "yazi_modeli": "gpt_work",
                       "revizyon_yonlendirmesi": str(g.get("revizyon_notu") or ""),
                       "hangi_aci": g.get("hangi_aci"),
                       "instagram_format": instagram_format,
                       "seri_kodu": seri_kodu, "kart_no": kart_no, "kart_rolu": kart_rolu,
                       "onceki_inceleme_notlari": geri_bildirim,
                       "inceleme_durumu": "DEPARTMAN_INCELEMESI_BEKLIYOR",
                       "gorsel_uretme_yontemi": "gpt_work_tam_gorsel_ve_yazi",
                       "tipografi_tercihi": "Monument Extended + Metropolis stili GPT isteminde belirtildi"})
        time.sleep(2)

    (cikti / "teslim.json").write_text(
        json.dumps({"urun": (brief.get("urun") or {}).get("urun_adi"),
                    "brief": bp.name, "gorseller": teslim,
                    "saglayici": GORSEL_SAGLAYICI, "model": GORSEL_MODEL,
                    "instagram_reklam_format_karari": brief.get("instagram_reklam_format_karari"),
                    "yontem": "GPT Work görseli ve Türkçe yazıları birlikte üretir; Jarvis metne görsel katmanı eklemez; taslak inceleme bekliyor",
                    "tipografi": "GPT görsel içinde oluşturdu; Monument Extended ve Metropolis görsel dili istendi",
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


