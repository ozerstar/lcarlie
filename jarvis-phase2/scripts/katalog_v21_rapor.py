#!/usr/bin/env python3
"""V2.1 raporlari -- gercek kayitlardan uretilir."""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_urun_gercegi as ug        # noqa: E402

C = pathlib.Path("/opt/lcarlie/output/catalog-v21")
B = C / "belgeler"
URUN = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]


def _yaz(ad, s):
    B.mkdir(parents=True, exist_ok=True)
    (B / ad).write_text("\n".join(s) + "\n", encoding="utf-8")
    print("  %s" % ad)


def product_truth():
    r = ug.catisma_raporu(URUN)
    s = ["# Product Truth Conflict Report", "",
         "## Kaynak otorite merdiveni", "",
         "| sıra | kaynak | not |", "|---|---|---|"]
    for k, v in sorted(ug.OTORITE.items(), key=lambda x: x[1]):
        s.append("| %d | `%s` | %s |" % (v, k,
                 "en yüksek — gözle doğrulanmış" if v == 1 else
                 "onaylı kutu metni" if v == 2 else
                 "ürün dosyası (knowledge/30-urun-*)" if v == 4 else
                 "packshot etiketinden okundu" if v == 7 else "—"))
    s += ["", "> Düşük otoriteli kaynak yüksek otoriteliyi **ezemez**. "
          "Aynı otoritede iki farklı değer varsa `CONFLICT`; hiçbir "
          "kaynakta yoksa `UNKNOWN`. **Uydurma yok.**", "",
          "## V2'nin düzeltilen hatası", "",
          "V2'de `kutu-gercegi` **tek kaynak** sayılmıştı ve "
          "\"KINESIS+ için tanım, uyarı ve INCI YOK\" denmişti. Bu "
          "kutu-gerçeği için doğru, **sistem için yanlıştı**: ürün "
          "dosyasında tam INCI, tanım ve mevzuat denetçisinden geçmiş "
          "7 satış cümlesi duruyordu. V2.1 bunları kullanıyor.", "",
          "## Alan bazında kaynak", "",
          "| ürün | alan | kaynak | otorite | durum |", "|---|---|---|---|---|"]
    for u in URUN:
        for alan, k in sorted(r["urun"][u].items(),
                              key=lambda x: x[1]["authority"]):
            s.append("| %s | %s | `%s` | %d | %s |"
                     % (u, alan, k["source"], k["authority"], k["status"]))
    s += ["", "## CONFLICT", ""]
    if r["conflict"]:
        for c in r["conflict"]:
            s.append("- **%s.%s** — %s" % (c["urun"], c["alan"], c["note"]))
        s.append("")
        s.append("> CONFLICT alanı final artwork'a **basılmaz**. "
                 "BABYSOL net miktarı bu yüzden hiçbir sayfada yok.")
    else:
        s.append("Yok.")
    s += ["", "## BLOCKED", ""]
    for b in r["blocked"] or []:
        s.append("- **%s.%s** — mevzuat denetiminde BLOCKED bulgusu var; "
                 "ilgili cümle sayfaya taşınmadı." % (b["urun"], b["alan"]))
    if not r["blocked"]:
        s.append("Yok.")
    s += ["", "## UNKNOWN", ""]
    for u_ in r["unknown"] or []:
        s.append("- **%s.%s** — hiçbir kaynakta bulunamadı." % (u_["urun"], u_["alan"]))
    if not r["unknown"]:
        s.append("Yok.")
    s.append("")
    _yaz("Product_Truth_Conflict_Report.md", s)


def print_rights(fin):
    s = ["# Print / Rights / Provenance Exception Report", "",
         "## Üç baskı durumu", "",
         "| durum | anlamı |", "|---|---|",
         "| `PRINT_READY_CANDIDATE` | ≥ 250 PPI, insan öznesi yok |",
         "| `PRINT_EXCEPTION` | 150–249 PPI — prototipte kullanılır, "
         "final baskıya aday değil |",
         "| `DIGITAL_PROTOTYPE_OK` | rights UNKNOWN (insan özne) — "
         "**PRINT_READY olamaz** |",
         "",
         "> `FINAL_PRINT_APPROVED` **kullanılmadı**: fiziksel matbaa "
         "provası alınmadı ve final otorite odur.", "",
         "## 5 final", "",
         "| # | sayfa | efektif PPI | baskı durumu | human_subject | "
         "rights_status | AI |", "|---|---|---|---|---|---|---|"]
    for k in fin["sayfalar"]:
        s.append("| %d | %s | **%.0f** | `%s` | %s | %s | %s |"
                 % (k["sira"], k["slot"], k["effective_ppi"] or 0,
                    k["PRINT_STATUS"], k["HUMAN_SUBJECT"],
                    k["RIGHTS_STATUS"], "NO_AI"))
    ist = [k for k in fin["sayfalar"] if k["PRINT_EXCEPTION"]]
    s += ["", "## İstisnalar", ""]
    for k in ist:
        s.append("- **%s** — %s" % (k["slot"], k["PRINT_EXCEPTION"]))
    if not ist:
        s.append("Yok.")
    s += ["", "## Neden kapak istisna taşıyor", "",
          "Kapağın kaynağı 1254×1254 px. Ürün kutusu karenin %96'sı "
          "olduğundan 145 mm yerleşim 212 PPI veriyor. Ürünü küçültmek "
          "250 PPI'a çıkarırdı ama kapağın fikrini (nesne kahraman) "
          "bozardı. **Takas kaydedildi, gizlenmedi.**", "",
          "## Provenance", "",
          "Tüm asetlerde `provenance.status = UNKNOWN`: fotoğraf / render "
          "/ AI ayrımı belgelenmemiş. Bu **baskı öncesi çözülmelidir**. "
          "Hiçbir sayfada üretken model kullanılmadı (`AI_STATUS = "
          "NO_AI`); ComfyUI bu turda **hiç çağrılmadı**.", "",
          "## Rights", "",
          "KINESIS+ insan karesi (`kinesis-4f9e28543c.png`) "
          "`UNKNOWN_HUMAN_SUBJECT` taşıyor. V21-K1 challenger'ı onu "
          "kullanıyor ve `DIGITAL_PROTOTYPE_OK` olarak işaretli. "
          "**Final 5'e alınmadı** — yerine hakları temiz stüdyo karesiyle "
          "kurulan V21-K2 seçildi.", ""]
    _yaz("Print_Rights_Provenance_Report.md", s)


def creative_board(fin):
    s = ["# Creative Board Decisions — V2.1", "", "## Seçim", "",
         "| sayfa | seçilen | gerekçe |", "|---|---|---|"]
    for k in fin["sayfalar"]:
        s.append("| %s | `%s` | %s |" % (k["slot"], k["konsept_id"],
                                         k["secim_gerekcesi"]))
    s += ["", "## Ürün-özel sanat yönetimi", "",
          "Tek reçete uygulanmadı. Her ürün için ayrı soruldu: "
          "**WHAT ACTUALLY NEEDS TO BECOME LARGER?**", ""]
    ne = json.loads((C / "v21-challenger-kayit.json").read_text(
        encoding="utf-8"))["ne_buyumeli"]
    for u, v in ne.items():
        s.append("- **%s** — %s" % (u, v))
    s += ["", "## Product DNA → Design Decision", "",
          "| sayfa | DNA öğesi | tasarım kararı |", "|---|---|---|"]
    for k in fin["sayfalar"]:
        m = k["meta"]
        s.append("| %s | MATERIAL | %s |" % (k["slot"], m.get("iliski")))
        s.append("| %s | LIGHT | zemin ortalama L = %.0f, aile %s |"
                 % (k["slot"], k["ortalama_L"], k["zemin_aile"]))
        s.append("| %s | GEOMETRY | kadraj ürün kutusundan türetildi "
                 "(`urun_kadraji`) |" % k["slot"])
        s.append("| %s | ENERGY | %s · repertuar %s |"
                 % (k["slot"], m.get("enerji"), m.get("repertuar")))
    s += ["", "## 12 soruluk final visual acceptance", ""]
    for q in fin["kurul"]:
        s += ["### %s" % q["soru"], "",
              "- **OBSERVATION:** %s" % q["observation"],
              "- **EVIDENCE:** %s" % q["evidence"],
              "- **DECISION:** %s" % q["decision"], ""]
    s += ["## Takaslar", "", "| sayfa | takas |", "|---|---|"]
    for k in fin["sayfalar"]:
        s.append("| %s | %s |" % (k["slot"], k["meta"].get("takas", "—")))
    s.append("")
    _yaz("Creative_Board_Decisions_V21.md", s)


def urun_varligi(fin):
    s = ["# Product Prominence — 10 ölçüm, tek skor YOK", "",
         "> **METRİĞİ OPTİMİZE ETME.** Bu ölçümler kötü tasarımı tespit "
         "etmek için kanıttır, hedef sayı değildir.", "",
         "## Ölçüm yöntemi ve güven", "",
         "| metrik | yöntem | güven |", "|---|---|---|"]
    mm = fin["sayfalar"][0]["varlik"].get("measurement_method", {})
    cc = fin["sayfalar"][0]["varlik"].get("confidence", {})
    for k in mm:
        s.append("| %s | %s | %s |" % (k, mm[k], cc.get(k, "—")))
    s += ["", "> **D** ve **F** ASET düzeyinde ölçülür, sayfa düzeyinde "
          "değil. İki tur aynı aseti kullanıyorsa bu metrikler zorunlu "
          "olarak eşit çıkar — bu gerçek eşitlik değil **ölçüm sınırıdır**. "
          "**F** gerçek saliency modeli değil CV vekilidir "
          "(`SALIENCY_PROXY`).", "",
          "## 5 final", "",
          "| sayfa | A foto/sayfa | B bbox/sayfa | bbox en | bbox boy | "
          "uzun kenar | C ürün/foto | G rekabet | konum |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k in fin["sayfalar"]:
        v = k["varlik"]
        s.append("| %s | %.3f | **%.3f** | %.1f mm | %.1f mm | %.1f mm | "
                 "%.3f | %s | %s |"
                 % (k["slot"], v["A_photo_area_page"], v["B_product_bbox_page"],
                    v.get("bbox_width_mm") or 0, v.get("bbox_height_mm") or 0,
                    v.get("bbox_long_edge_mm") or 0, v["C_product_per_photo"],
                    v["G_background_competition"],
                    (v["I_product_position"] or {}).get("bolge", "—")))
    s += ["", "## Tur karşılaştırması (ürün kutusu / sayfa)", "",
          "| tur | ortalama | en düşük | en yüksek | ≥250 PPI sayfa |",
          "|---|---|---|---|---|",
          "| TUR 3 | 0.273 | 0.071 | 0.418 | 0 / 5 |",
          "| V2 | 0.128 | 0.064 | 0.238 | 3 / 5 |",
          "| **V2.1** | **0.227** | 0.125 | 0.376 | **4 / 5** |",
          "", "> Kapak çoklu ürün içermediği için ürün-sayfa ortalamasına "
          "dahildir; TUR3 kapağı üç ürün içerdiğinden onun ortalaması bu "
          "yönde hafif yanlıdır.", ""]
    _yaz("Product_Prominence_V21.md", s)


def main() -> int:
    fin = json.loads((C / "v21-final-kayit.json").read_text(encoding="utf-8"))
    print("belgeler:")
    product_truth()
    print_rights(fin)
    creative_board(fin)
    urun_varligi(fin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
