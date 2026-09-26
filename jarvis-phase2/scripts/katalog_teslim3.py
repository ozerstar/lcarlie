#!/usr/bin/env python3
"""TUR 3 teslimatlari: karar kaydi (Creative Board formati) + birlesik PDF."""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

K = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v3")

KURUL = {
    "cover": dict(
        fikir="ÜÇ ÜRÜN BANDI",
        gozlem="Tur 2'nin kapagi uc 'malzeme seridi' kullaniyordu; "
               "ucunun de baskin rengi ayni krem bandindaydi ve uzaktan "
               "tek serit gibi okunuyordu.",
        kanit="Tur 2 kapak zemin olcumu: rgb(214,202,189) %30 ve "
              "rgb(238,230,222) %25 -- iki serit ayni renk ailesinde. "
              "Tur 3'te uc pano uc ayri urun renginden geliyor ve sayfa "
              "ortalama parlakligi 205.4.",
        muhakeme="Marka tezi 'tek kategoride en iyi' degil, '36 urunle "
                 "bir ailenin tum cilt ihtiyaci'. Kapak bunu ancak farkli "
                 "kategorilerin GERCEK renklerini yan yana koyarak "
                 "soyleyebilir. Pano orani (70x83 mm) soyut degil fiziksel "
                 "bir karardir: daha ince bir pano urun kutusunu "
                 "logotype'in ortasindan keserdi.",
        karar="PASS",
        revizyon="Yok. Bir sonraki turda kapak alt ucte biri bos kaliyor; "
                 "oraya kategori indeksi denenebilir."),
    "hydravie": dict(
        fikir="NUMUNE FÖYÜ",
        gozlem="Tur 2'de calisan tek sayfaydi. Fikir korundu, aset ve "
               "yapisi degisti.",
        kanit="Metin alan orani 0.051 -- bes sayfanin en yuksegi ve "
              "tur 2'deki 0.065'e yakin. Fotograf 88x88 mm kare blok, "
              "300 DPI. Ilk denemede 73x200 mm dar kolon kutunun "
              "yazisini ortasindan kesiyordu.",
        muhakeme="Kaynak 1800x1200 ve kutu YATAY duruyor; 73:200 "
                 "oranindaki bir kadraj kaynagin %36.5'ini alabiliyor, "
                 "kutu ise %46 genisliginde -- matematiksel olarak "
                 "sigmaz. Fotograf kare bloga alinip tablo tam genislige "
                 "acilinca hem kutu tamamlandi hem tablo daha baskin oldu.",
        karar="PASS",
        revizyon="Yok."),
    "kinesis": dict(
        fikir="SALON",
        gozlem="Dizinin omurgasi: tek KOYU sayfa ve tek insan karesi.",
        kanit="Sayfa ortalama parlakligi 92.5 -- besin en dusugu "
              "(en yuksek 221.1). Ters tipografi karenin sol-alt "
              "cegreginde; o bolgenin olculen parlakligi L=7..54. "
              "Metin/goruntu kontrast ihlali: 0.",
        muhakeme="Tur 2 tasarisi metni sol-USTE koyuyordu; orasi pencere "
                 "(L=212+) ve ters tipografi okunmazdi. Bolge secimi "
                 "estetik degil olcum kararidir. Sayfa 212x212 mm "
                 "yerlesimle 150.2 DPI'da duruyor -- tam tasma (216 mm) "
                 "147 DPI verip tabani delerdi.",
        karar="PASS",
        revizyon="Yok. rights_status UNKNOWN -- baski oncesi cozulmeli."),
    "private-care": dict(
        fikir="ÇİFT",
        gozlem="FEMISIA ve VIREON ayni fotografta. Katalogda baska "
               "hicbir sayfanin yapamadigi sey: ikili anlati tek karede.",
        kanit="Tam genislik bandi 216x144 mm, 174 DPI. Ilk denemede "
              "govde metni guvenli alani 5 pt asiyordu (4 durduran "
              "ihlal) ve INCI 5.4 pt ile 5.5 tabaninin altindaydi.",
        muhakeme="Bu sayfanin fikri kompozisyonda degil ASETTE: iki urun "
                 "zaten ayni karede cekilmis. Aset kutuphanesine "
                 "bakmadan bu sayfa yazilamazdi -- tur 2'de e-ticaret "
                 "havuzunda boyle bir kare yoktu. Bant kadraji %82'ye "
                 "daraltilarak sagdaki olu mavi alan disarida birakildi.",
        karar="PASS",
        revizyon="Yok."),
    "daily-care": dict(
        fikir="ALT BANT",
        gozlem="Tur 2'de zorunlu gunes uyarisi sayfaya sonradan "
               "yapistirilmis yari saydam bir kutudaydi; form alani "
               "gibi duruyordu.",
        kanit="Uyari artik 72 mm'lik koyu kapanis alaninin icinde, "
               "ters dizilmis, 6.4 pt. Sayfa ortalama parlakligi 116.8 "
               "-- dizinin ikinci koyu sayfasi. Kontrast ihlali 0.",
        muhakeme="Mevzuat metni bir yuk degil, sayfanin kapanisidir. "
                 "Koyu bant hem uyariyi tasiyor hem diziyi kapatiyor "
                 "hem de bir onceki sayfanin acik zeminine karsilik "
                 "veriyor. Kadraj %80'e daraltilarak kutu bandi doldurdu.",
        karar="PASS",
        revizyon="Yok."),
}


def karar_kaydi(p: dict, ritim: dict, sira: int) -> str:
    kl = p["klasor"]
    k = KURUL[kl]
    o, s, q = p["olcumler"], p["sayfa_olcumu"], p["tipografi_qa"]
    d = o.get("dizi", {})
    sat = [
        "# CREATIVE BOARD KARARI — %s (TUR 3)" % kl.upper(), "",
        "**Fikir:** %s" % k["fikir"], "",
        "| dizideki yeri | %d / 5 |" % sira, "|---|---|",
        "| rol | `%s` |" % d.get("rol", "-"),
        "| isik | %s (ortalama L = %.1f) |" % (d.get("isik", "-"),
                                               p["ortalama_L"]),
        "| zemin ailesi | %s |" % ritim["zemin_aileleri"][sira - 1],
        "| insan karesi | %s |" % ("EVET" if d.get("insan") else "hayir"),
        "| kaynak aset | `%s` |" % pathlib.Path(p["kaynak_aset"]).name,
        "", "## OBSERVATION", "", k["gozlem"], "",
        "## EVIDENCE", "", k["kanit"], "",
        "| ölçüt | değer |", "|---|---|",
        "| görüntü | %.0f × %.0f mm @ %.0f DPI |"
        % (o.get("urun_en_mm", 0), o.get("urun_boy_mm", 0),
           o.get("urun_dpi", 0)),
        "| kadraj | `%s` |" % o.get("kadraj", "-"),
        "| varlık sınıfı | TYPE %s |" % p["varlik_sinifi"],
        "| metin alan oranı | %.4f |" % s["metin"],
        "| en büyük punto | %.1f pt |" % s["en_buyuk_punto"],
        "| öğe sayısı | %d |" % s["oge"],
        "| tipografi QA | geçti=%s · durduran=%d · uyarı=%d |"
        % (q["gecti"], q["durduran"], q["uyari"]),
        "| metin/görüntü kontrast ihlali | %d |" % p["kontrast_ihlali"],
        "| bağımsız eleştirmen itirazı | %d |" % len(p["elestirmen"]),
        "", "## DESIGN REASONING", "", k["muhakeme"], "",
        "## DECISION", "",
        "**Teknik QA:** %s · **Creative Board:** %s"
        % ("GEÇTİ" if q["gecti"] else "GEÇMEDİ", k["karar"]), "",
        "> Teknik PASS ≠ Creative PASS. İki hüküm ayrı verilir ve",
        "> biri diğerini geçersiz kılamaz.", "",
        "## REVISION DIRECTION", "", k["revizyon"], "",
        "## Ürün bütünlüğü", "",
        "Ürün pikselleri hiçbir üretken modelden geçmedi; yukarı "
        "örnekleme yapılmadı. Köken zinciri `koken.json` içindedir.",
    ]
    return "\n".join(sat) + "\n"


def main() -> int:
    import pymupdf
    veri = json.loads((K / "pilot3-kayit.json").read_text(encoding="utf-8"))
    sayfalar, ritim = veri["sayfalar"], veri["dizi_ritmi"]

    birlesik = pymupdf.open()
    for i, p in enumerate(sayfalar, 1):
        h = K / p["klasor"]
        (h / "creative-board-karari.md").write_text(
            karar_kaydi(p, ritim, i), encoding="utf-8")
        d = pymupdf.open(str(h / ("%s.pdf" % p["klasor"])))
        birlesik.insert_pdf(d)
        d.close()
        print("teslim: %s" % p["klasor"])

    d = pymupdf.open(str(K / "sku-index" / "sku-index.pdf"))
    birlesik.insert_pdf(d)
    d.close()
    yol = K / "LCARLIE-katalog-pilot-TUR3-6-sayfa.pdf"
    birlesik.save(str(yol))
    birlesik.close()
    print("birlesik: %s (%d sayfa)" % (yol, len(sayfalar) + 1))

    # dizi raporu
    sat = ["# KATALOG DİZİSİ — TUR 3", "",
           "Sayfalar tek tek değil, bir koreografi olarak tasarlandı.",
           "", "| # | sayfa | rol | zemin ailesi | ort. L | metin oranı "
           "| en büyük punto | insan |", "|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(sayfalar, 1):
        d = p["olcumler"].get("dizi", {})
        sat.append("| %d | %s | `%s` | %s | %.1f | %.4f | %.1f pt | %s |"
                   % (i, p["klasor"], d.get("rol", "-"),
                      ritim["zemin_aileleri"][i - 1], p["ortalama_L"],
                      p["sayfa_olcumu"]["metin"],
                      p["sayfa_olcumu"]["en_buyuk_punto"],
                      "EVET" if d.get("insan") else "—"))
    sat += ["", "## Ritim denetimi", "",
            "- zemin aileleri: **%s**" % " → ".join(ritim["zemin_aileleri"]),
            "- dağılım: `%s`" % ritim["aile_dagilimi"],
            "- koyu sayfa: %d / %d" % (ritim["koyu_sayfa"], len(sayfalar)),
            "- insan sayfası: %d / %d" % (ritim["insan_sayfa"], len(sayfalar)),
            "- punto aralığı: %s pt" % ritim["punto_araligi"],
            "- metin yoğunluğu aralığı: %s" % ritim["yogunluk_araligi"],
            "", "**Dizi itirazı: %s**"
            % ("YOK" if not ritim["bulgular"] else
               "; ".join(b["neden"] for b in ritim["bulgular"])), "",
            "## Neden bu denetim gerekiyordu", "",
            "Tur 2'de beş sayfanın dördü aynı sıcak krem zemin ailesine",
            "düştü. Sayfa kapıları bunu yakalayamadı çünkü her sayfa tek",
            "başına kusursuzdu. Kusur sayfada değil **dizide**ydi.",
            "`dizi_ritmi()` beş sayfayı birlikte ölçer.", ""]
    (K / "KATALOG-DIZISI.md").write_text("\n".join(sat), encoding="utf-8")
    print("dizi raporu: %s" % (K / "KATALOG-DIZISI.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
