#!/usr/bin/env python3
"""TUR 2 teslimatlari: karar kaydi + birlesik baski PDF'i."""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

K = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v2")

FIKIR = {
    "cover": ("MALZEME İNDEKSİ",
              "Marka, yapıldığı şeydir. Ürün yok, manşet yok: üç malzeme "
              "dünyası (jel / botanik / su) dikey şerit olarak yan yana; "
              "koyu sırt markayı taşır."),
    "hydravie": ("NUMUNE FÖYÜ",
                 "Kanıt, düzenin kendisi. Manşet yok; sayfanın baskın öğesi "
                 "içerik/işlev tablosu. Fotoğraf dar dikey kolon."),
    "kinesis": ("FOTOĞRAF GRİDDİR",
                "Grid'i fotoğraf kuruyor. Tipografi yalnız fotoğrafın "
                "ölçülen sakin jel alanlarına yerleşir; sayfa grid'ine değil."),
    "private-care": ("SÜREKLİ YÜZEY",
                     "Ürün malzemenin içinden çıkar. Sayfa tek krem yüzey; "
                     "fotoğrafın görünür kenarı yok. Manşet yok, tek kısa "
                     "cümle metin ölçeğinde."),
    "daily-care": ("IŞIK ALANI",
                   "Güneş ışığı sayfanın kendisi. Ad + SPF tek büyük öğe, "
                   "fotoğrafın en parlak sakin bölgesinde."),
}


def karar_kaydi(p: dict) -> str:
    kl = p["klasor"]
    ad, fikir = FIKIR[kl]
    o, s, q = p["olcumler"], p["sayfa_olcumu"], p["tipografi_qa"]
    sat = ["# KARAR KAYDI — %s (TUR 2)" % kl.upper(), "",
           "## Fikir", "", "**%s**" % ad, "", fikir, "",
           "## Bilgi koreografisi", "",
           "- Manşet: **%s**" % ("YOK" if not o.get("mansert") else "var"),
           "- Baskın öğe: **%s**" % o.get("baskin_oge", o.get("tip", "-")),
           "- En büyük punto: %.1f pt — ölçek kontrastı %.1fx"
           % (s["en_buyuk_punto"], s["en_buyuk_punto"] / 9.5),
           "", "## Ölçümler", "", "| ölçüt | değer |", "|---|---|",
           "| görüntü | %.0f x %.0f mm @ %.0f DPI |"
           % (o.get("urun_en_mm", 0), o.get("urun_boy_mm", 0),
              o.get("urun_dpi", 0)),
           "| kadraj | %s |" % o.get("kadraj", "-"),
           "| varlık sınıfı | TYPE %s |" % p["varlik_sinifi"],
           "| görsel alan oranı | %.3f |" % s["gorsel"],
           "| metin alan oranı | %.3f |" % s["metin"],
           "| boşluk oranı | %.3f |" % s["bosluk"],
           "| öğe sayısı | %d |" % s["oge"],
           "", "## Kapılar", "",
           "- Tipografi QA: geçti=%s · durduran=%d · uyarı=%d"
           % (q["gecti"], q["durduran"], q["uyari"]),
           "- Metin/görüntü kontrast ihlali: %d" % p["kontrast_ihlali"],
           "- Bağımsız eleştirmen itirazı: %d" % len(p["elestirmen"]),
           "- **Sonuç: %s**" % p["sonuc"], "",
           "## Ürün bütünlüğü", "",
           "Ürün pikselleri hiçbir üretken modelden geçmedi; yukarı "
           "örnekleme yapılmadı. Köken zinciri sayfa klasöründedir."]
    return "\n".join(sat) + "\n"


def main() -> int:
    import pymupdf
    kayit = json.loads((K / "pilot2-kayit.json").read_text(encoding="utf-8"))
    birlesik = pymupdf.open()
    for p in kayit:
        kl = p["klasor"]
        h = K / kl
        (h / "creative-decision-record.md").write_text(
            karar_kaydi(p), encoding="utf-8")
        d = pymupdf.open(str(h / ("%s.pdf" % kl)))
        birlesik.insert_pdf(d)
        d.close()
        print("teslim: %s" % kl)
    yol = K / "LCARLIE-katalog-pilot-TUR2-5-sayfa.pdf"
    birlesik.save(str(yol))
    birlesik.close()
    print("birlesik: %s" % yol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
