"""Trendyol rakip fiyatları: sahibin kendi Chrome'unda açılan arama sayfalarından (30.10.2026).

Neden Chrome: Trendyol sunucudan ve başsız tarayıcıdan gelen isteklere 403 veriyor (29.10.2026 ölçüldü);
bot engeli aşılmaz. Sahip "Chrome olarak çalıştırarak ilerle" dedi: arama sayfası sahibin tarayıcısında
normal bir ziyaret olarak açılır, kartlar deploy/trendyol_chrome.js ile okunur ve bu modüle verilir.
Doğrulama robotu (CAPTCHA) çıkarsa durulur; otomatik, zamanlanmış Trendyol taraması YOKTUR.

Girdi satırı: marka-slug|fiyat|ürün-no|ürün adı (kartta görünen; en çok 70 karakter)
Kaynak linki: https://www.trendyol.com/<marka>/x-p-<ürün-no> (Trendyol asıl ürün sayfasına yönlendirir).
Alıntı: kartta görünen ad + fiyat satırı (ör. "TERA DERMOKOZMETİK ÇATLAK ÖNLEYİCİ KREM 1.150 TL").
"""
import re

from .util import iso, now

_ROZET = re.compile(r"^En Çok (Ziyaret Edilen|Favorilenen|Değerlendirilen|Satan)", re.I)
_FIYAT = re.compile(r"^\d{1,3}(?:\.\d{3})*(?:,\d{1,2})? TL$")


def marka_adi(slug):
    return " ".join(p.capitalize() for p in slug.split("-"))


def satirlardan_payload(satirlar, zaman=None):
    """TSV satırları -> Radar ingest JSON'u. Rozet adlı ('En Çok Favorilenen 2. Ürün') kartlarda ürün adı
    yoktur: yalnız kanal kaydı yapılır, fiyat yazılmaz (hangi ürüne ait olduğu belirsiz)."""
    ts = iso(zaman or now())
    markalar, red = {}, []
    for ham in satirlar:
        parca = [p.strip() for p in ham.split("|", 3)]
        if len(parca) != 4 or not parca[0]:
            continue
        slug, fiyat_metni, no, ad = parca
        url = f"https://www.trendyol.com/{slug}/x-p-{no}"
        b = markalar.setdefault(slug, {"name": marka_adi(slug), "trendyol_url": f"https://www.trendyol.com/{slug}",
                                       "texts": [], "observations": [
                                           {"kind": "channel", "value": "trendyol", "source_url": url, "fetched_at": ts}]})
        if not _FIYAT.match(fiyat_metni) or _ROZET.match(ad) or len(ad) < 6:
            red.append(f"{slug}/{no}: ürün adı yok ({ad[:30]})")
            continue
        deger = float(fiyat_metni.removesuffix(" TL").replace(".", "").replace(",", "."))
        b["texts"].append(ad)
        b["observations"] += [
            {"kind": "product", "product": ad, "source_url": url, "fetched_at": ts},
            {"kind": "price", "product": ad, "value": deger, "source_url": url, "fetched_at": ts,
             "excerpt": f"{ad} {fiyat_metni}"}]
    return {"source": "trendyol-chrome", "source_status": [{"source": "trendyol.com (Chrome)", "ok": True}],
            "brands": list(markalar.values()), "atlanan": red}
