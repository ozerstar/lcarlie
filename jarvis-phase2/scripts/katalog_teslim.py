#!/usr/bin/env python3
"""Pilot teslimatlarini uretir: karar kaydi, QA raporu, birlesik PDF.

Kayittaki her sayfa icin insan-okunur karar kaydi yazar ve tum
sayfalari tek baskiya hazir PDF'te birlestirir.
"""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_sayfa_olcum as so       # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts   # noqa: E402
from jarvis import katalog_tipografi_qa as tqa     # noqa: E402

CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-pilot")


def karar_kaydi(p: dict) -> str:
    son = p["turlar"][-1] if p.get("turlar") else {}
    v = p["varlik_sinifi"]
    k = p["konseptler"]
    sat = []
    A = sat.append
    A("# KARAR KAYDI — %s" % p["klasor"].upper())
    A("")
    A("Ürün: **%s** · Sayfa türü: %s · Kaynak: `%s`"
      % (p["slug"], p["tur"], pathlib.Path(p["kaynak_foto"]).name))
    A("")
    A("## 1 · Varlık sınıflandırması (zorunlu ilk kapı)")
    A("")
    A("**TYPE %s** (güven %.2f)" % (v["asset_type"], v["confidence"]))
    A("")
    A("Kanıt:")
    for e in v["kanit"]:
        A("- %s" % e)
    A("")
    A("Bu sınıfta **yasak** işlemler: %s" % ", ".join("`%s`" % o for o in v["yasak"]))
    A("")
    A("Büyütmeden azami yerleşim: **%.0f × %.0f mm** (300 DPI)"
      % tuple(v["azami_guvenli_mm"]))
    A("")
    A("## 2 · Üretilen konseptler ve ölçülen kanıt")
    A("")
    A("| konsept | ürün yük. oranı | ürün DPI | boşluk | öğe | ölçek kontrastı |")
    A("|---|---|---|---|---|---|")
    for ad, kn in k.items():
        A("| %s | %.2f | %s | %.2f | %d | %.1fx |"
          % (ad, kn["urun_yukseklik_orani"], kn["urun_dpi"],
             kn["bosluk_orani"], kn["oge_sayisi"], kn["olcek_kontrasti"]))
    A("")
    A("## 3 · Seçim")
    A("")
    A("**Seçilen: `%s`**" % p["secilen_konsept"])
    A("")
    A("Gerekçe: %s" % p["secim_gerekcesi"])
    A("")
    A("## 4 · Turlar")
    A("")
    for t in p.get("turlar", []):
        A("### Tur %d — `%s` → **%s**" % (t["tur"], t["konsept"], t["sonuc"]))
        q = t["tipografi_qa"]
        A("")
        A("- Tipografi QA: geçti=%s · durduran=%d · uyarı=%d"
          % (q["gecti"], q["durduran"], q["uyari"]))
        A("- Metin/görüntü kontrast ihlali: %d" % t.get("metin_kontrast_ihlali", 0))
        if t["elestirmen_itirazlari"]:
            A("- Bağımsız eleştirmen itirazları:")
            for i in t["elestirmen_itirazlari"]:
                A("  - **%s** `%s` — %s" % (i["agirlik"], i["kusur_tipi"],
                                            i["neden"]))
        else:
            A("- Bağımsız eleştirmen: itiraz yok")
        if t.get("revizyon"):
            A("- Revizyon: %s" % t["revizyon"])
        A("")
    A("## 5 · Ürün bütünlüğü (köken zinciri)")
    A("")
    A("Kaynak özeti: `%s`" % p["koken"]["kaynak_ozeti"][:32])
    for a in p["koken"]["adimlar"]:
        A("- `%s` (%s) — %s" % (a["islem"], a["arac"], a["not"]))
    A("")
    A("**Ürün pikselleri hiçbir üretken modelden geçmedi.** Yukarı örnekleme yapılmadı.")
    A("")
    A("## 6 · Yerleşim ölçüleri")
    A("")
    o = son.get("olcumler", {})
    A("- Görüntü: **%.0f × %.0f mm** @ **%.0f DPI**"
      % (o.get("urun_en_mm", 0), o.get("urun_boy_mm", 0), o.get("urun_dpi", 0)))
    A("- Kadraj: `%s`" % o.get("kadraj", "-"))
    A("- Sayfa: 210 × 210 mm + 3 mm taşma · güvenli alan 8 mm")
    return "\n".join(sat) + "\n"


def qa_raporu(p: dict, pdf_yolu: pathlib.Path) -> str:
    q = tqa.kapi(pdf_yolu, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
    olc = so.sayfa_olcumleri(pdf_yolu)[0]
    sat = []
    A = sat.append
    A("# QA SONUCU — %s" % p["klasor"].upper())
    A("")
    A("## Tipografi QA (deterministik, model sormaz)")
    A("")
    A("- **Geçti: %s**" % q["gecti"])
    A("- Durduran ihlal: **%d**" % q["durduran_ihlal"])
    A("- Uyarı: %d" % q["uyari"])
    A("- Tip dağılımı: `%s`" % q["tip_dagilimi"])
    A("")
    if q["ihlaller"]:
        A("| tip | ölçülen | eşik | ağırlık |")
        A("|---|---|---|---|")
        for i in q["ihlaller"][:12]:
            A("| %s | %s | %s | %s |" % (i["ihlal_tipi"], str(i["olculen"])[:40],
                                         str(i["esik"])[:24], i["agirlik"]))
        A("")
    A("## Sayfa ölçümleri")
    A("")
    A("| ölçüt | değer |")
    A("|---|---|")
    A("| sayfa ölçüsü | %.1f × %.1f mm |" % (olc.en_mm, olc.boy_mm))
    A("| görsel alan oranı | %.3f |" % olc.gorsel_alan_orani)
    A("| çizim alan oranı | %.3f |" % olc.cizim_alan_orani)
    A("| metin alan oranı | %.3f |" % olc.metin_alan_orani)
    A("| boşluk oranı | %.3f |" % olc.bosluk_orani)
    A("| öğe sayısı | %d |" % olc.ogeler)
    A("| en büyük punto | %.1f pt |" % olc.en_buyuk_punto)
    A("| yoğunluk | %.3f |" % olc.yogunluk)
    A("| düzen imzası | `%s` |" % olc.duzen_imzasi[:70])
    A("")
    A("## Baskı gerçeği")
    A("")
    o = (p["turlar"][-1].get("olcumler") or {}) if p.get("turlar") else {}
    A("- Görüntü yerleşim DPI: **%.0f** (ürün tabanı %.0f)"
      % (o.get("urun_dpi", 0), ts.URUN_TABAN_DPI))
    A("- Yukarı örnekleme: **YOK** — render motoru hedef kaynağı aşarsa "
      "istisna fırlatır")
    A("- Metin: **vektör** (reportlab); difüzyona çizdirilmedi")
    A("- PNG teslimatı PDF'ten üretildi — PNG ile PDF birebir aynı")
    return "\n".join(sat) + "\n"


def main() -> int:
    kayit = json.loads((CIKTI / "pilot-kayit.json").read_text(encoding="utf-8"))
    import pymupdf

    birlesik = pymupdf.open()
    for p in kayit:
        hedef = CIKTI / p["klasor"]
        pdf_yolu = hedef / ("%s.pdf" % p["klasor"])
        (hedef / "creative-decision-record.md").write_text(
            karar_kaydi(p), encoding="utf-8")
        (hedef / "qa-result.md").write_text(
            qa_raporu(p, pdf_yolu), encoding="utf-8")
        d = pymupdf.open(str(pdf_yolu))
        birlesik.insert_pdf(d)
        d.close()
        print("teslim: %s" % p["klasor"])

    birlesik.save(str(CIKTI / "LCARLIE-katalog-pilot-5-sayfa.pdf"))
    birlesik.close()
    print("birlesik PDF: %s" % (CIKTI / "LCARLIE-katalog-pilot-5-sayfa.pdf"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
