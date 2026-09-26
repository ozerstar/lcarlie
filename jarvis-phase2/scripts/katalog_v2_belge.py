#!/usr/bin/env python3
"""V2 teslimat belgelerini GERCEK kayitlardan uretir. Elle yazilmaz."""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_aset_v2 as av2          # noqa: E402
from jarvis import katalog_dna as dna              # noqa: E402
from jarvis import katalog_ekip_v2 as ek2          # noqa: E402
from jarvis import katalog_referans as ref         # noqa: E402

CAL = pathlib.Path("/opt/lcarlie/output/creative-asset-library")
C = pathlib.Path("/opt/lcarlie/output/catalog-v2")
B = C / "belgeler"
SAYFA = 216.0


def _yaz(ad, satirlar):
    B.mkdir(parents=True, exist_ok=True)
    (B / ad).write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    print("  %s" % ad)


def creative_department():
    m = ek2.matris()
    k = ek2.kapsama()
    s = ["# Creative Department V2", "",
         "Mevcut 18 rol **korunmuş ve yükseltilmiştir**; yeni rol "
         "uydurulmadı. Kaynak: `jarvis/katalog_yetenek.py` KUTUK (18 kayıt).",
         "", "## Durum", "",
         "| ölçüt | değer |", "|---|---|",
         "| rol | %d |" % len(m),
         "| pipeline aşaması | %d |" % k["asama"],
         "| sahipli aşama | %d / %d |" % (k["sahipli"], k["asama"]),
         "| sahipsiz aşama | %s |" % (k["sahipsiz"] or "YOK"),
         "| gerçek koda bağlı rol | %d / %d |"
         % (sum(1 for x in m if x["bound"]), len(m)),
         "| UNBOUND rol | %s |" % ", ".join(k["unbound_rol"]),
         "",
         "> UNBOUND olan tek rol HUMAN'dır ve bu kasıtlıdır: fiziksel "
         "matbaa provası alınmadı, dolayısıyla final baskı onayı "
         "verilemez. Persona promptu implementasyon sayılmaz.", ""]
    for x in m:
        s += ["## %s — %s" % (x["id"], x["name"]), "",
              "**Tip:** `%s` · **Duruş:** `%s` · **Yetki:** %s · "
              "**Bağlı:** %s" % (x["type"], x["maker_or_judge"],
                                 ", ".join(x["authority"]) or "—",
                                 "EVET" if x["bound"] else "HAYIR"), "",
              "- **PURPOSE:** %s" % x["purpose"],
              "- **UNIQUE CAPABILITY:** %s" % (x["unique_capability"] or "—"),
              "- **DOMAIN KNOWLEDGE:** %s" % (", ".join(x["domain_knowledge"]) or "—"),
              "- **TOOLS:** %s" % (", ".join(x["tools"]) or "—"),
              "- **INPUT CONTRACT:** %s" % (", ".join(x["input_contract"]) or "—"),
              "- **OUTPUT CONTRACT:** %s" % (", ".join(x["output_contract"]) or "—"),
              "- **EVIDENCE:** %s" % (", ".join(x["evidence"]) or "—"),
              "- **AUTHORITY:** %s" % (", ".join(x["authority"]) or "—"),
              "- **REJECTION RIGHTS:** %s" % (", ".join(x["rejection_rights"]) or "—"),
              "- **UPSTREAM:** %s" % (", ".join(x["upstream"]) or "—"),
              "- **DOWNSTREAM:** %s" % (", ".join(x["downstream"]) or "—"),
              "- **WHEN TO INVOKE:** %s" % (x["when_to_invoke"] or "—"),
              "- **WHEN NOT TO INVOKE:** %s" % (x["when_not_to_invoke"] or "—"),
              "- **FAILURE MODES:** %s" % ("; ".join(x["failure_modes"]) or "—"),
              "- **TESTS:** %s" % (", ".join(x["tests"]) or "—"),
              "- **STAGES:** %s" % (", ".join(x["stages"]) or "—"),
              "- **BINDING:** `%s`" % (x["binding"] or "YOK — UNBOUND"), ""]
    _yaz("Creative_Department_V2.md", s)


def capability_matrix():
    m = ek2.matris()
    s = ["# Agent Capability Matrix", "",
         "| id | rol | tip | duruş | aşamalar | binding | yetki |",
         "|---|---|---|---|---|---|---|"]
    for x in m:
        s.append("| %s | %s | %s | %s | %s | %s | %s |"
                 % (x["id"], x["name"], x["type"], x["maker_or_judge"],
                    ", ".join(x["stages"]) or "—",
                    "`%s`" % x["binding"] if x["binding"] else "**UNBOUND**",
                    ", ".join(x["authority"]) or "—"))
    k = ek2.kapsama()
    s += ["", "## Aşama sahipliği", "",
          "| aşama | sahip rol(ler) |", "|---|---|"]
    for a in ek2.ASAMALAR:
        s.append("| %s | %s |" % (a, ", ".join(k["sahipler"].get(a, [])) or "**SAHİPSİZ**"))
    _yaz("Agent_Capability_Matrix.md", s)


def handoff_graph(fin):
    t = fin["theater"]
    s = ["# Agent Handoff Graph", "",
         "Roller arasında **tek geçerli iletişim birimi** structured "
         "handoff'tur. Boş onay mesajı (`katılıyorum`, `premium görünüyor`) "
         "AGENT_THEATER olarak yakalanır.", "",
         "## Sözleşme", "",
         "`%s`" % " · ".join(ek2.HANDOFF_ALANLARI), "",
         "## Bu turun taraması", "",
         "| ölçüt | değer |", "|---|---|",
         "| handoff | %d |" % t["handoff"],
         "| görev alan rol | %d |" % t["gorev_alan_rol"],
         "| IDLE rol | %d |" % t["idle_rol"],
         "| YÜKSEK bulgu | %d |" % len(t["yuksek"]),
         "| maker/judge ihlali | %d |" % len(fin["maker_judge_ihlali"]),
         "", "## Bulgular", ""]
    if t["bulgular"]:
        s += ["| tip | rol | neden |", "|---|---|---|"]
        for b in t["bulgular"]:
            s.append("| %s | %s | %s |" % (b["tip"], b["rol"], b["neden"]))
    else:
        s.append("Bulgu yok.")
    s += ["", "> IDLE meşru bir durumdur. Bu turda IDLE olan iki rol: "
          "**C11** (üretken model kullanılmadı) ve **HUMAN** (fiziksel "
          "prova alınmadı). Her görevde 18 rolü zorla çalıştırmak "
          "agent theater üretir.", ""]
    _yaz("Agent_Handoff_Graph.md", s)


def asset_index():
    kay = json.loads((CAL / "index-v2.json").read_text(encoding="utf-8"))
    o = av2.ozet(kay)
    hata = av2.dogrula(kay)
    s = ["# Asset Library Index", "",
         "## V1'in bütünlük kusuru ve düzeltmesi", "",
         "V1 indeksi **yalnızca `cekim-ham`** klasörünü tarıyordu. KINESIS "
         "sayfası ise `pilot-assets/` içinden bir kare kullanıyordu — yani "
         "üretimde kullanılan bir aset manifestte **hiç yoktu**. Bu yüzden "
         "`human_subject = 0` (indekslenen arşiv için doğru) ile "
         "`KINESIS = tek insan karesi` (üretim sayfası için doğru) aynı "
         "raporda çakıştı.", "",
         "V2'de manifest üretimin eriştiği **her kökü** tarar ve "
         "`human_subject` ile `rights_status` ayrı alanlardır; "
         "`dogrula()` çelişkiyi hata olarak yükseltir.", "",
         "## Durum", "", "| ölçüt | değer |", "|---|---|",
         "| kayıt | %d |" % o["kayit"],
         "| tekil fotoğraf | %d |" % o["tekil_fotograf"],
         "| kök dağılımı | %s |" % o["kok_dagilimi"],
         "| photo_role | %s |" % o["photo_role"],
         "| human_subject | %s |" % o["human_subject"],
         "| rights_status | %s |" % o["rights_status"],
         "| quality | %s |" % o["quality"],
         "| doğrulama hatası | %d |" % len(hata),
         "", "## İnsan öznesi", "",
         "Ten rengi sezgiseli sıcak amber/sarı ambalajda **aşırı "
         "işaretliyordu**: 16 işaretli karenin 12'sinde insan yoktu. "
         "Gözle doğrulama tablosu (`INSAN_DOGRULAMA`) ölçümü ezer ve "
         "kayıt hangisinin konuştuğunu söyler.", "",
         "| dosya | human_subject | rights_status |", "|---|---|---|"]
    for r in kay:
        if r["human_subject"] != "HAYIR":
            s.append("| `%s` | %s | %s |" % (pathlib.Path(r["source_path"]).name,
                                             r["human_subject"],
                                             r["rights_status"]))
    s += ["", "## Alanlar", "",
          "`%s`" % "` · `".join(sorted(kay[0].keys())), "",
          "## Karantina", "",
          "Katalog aset klasörüne yanlışlıkla düşmüş 165 kişisel kare "
          "(+165 türev) `/opt/lcarlie/karantina/ozel-fotograf-20260926/` "
          "altındadır. **Kataloğa geri alınmadı, silinmedi, "
          "indekslenmedi.**", ""]
    _yaz("Asset_Library_Index.md", s)


def failure_library():
    s = ["# Failure Library", "",
         "Anti-luxury hata kütüğü. Sadece yasak değil: **neden "
         "başarısız olduğu** kayıtlı.", "",
         "| kod | neden başarısız | bu projede görüldü |", "|---|---|---|"]
    for h in ref.HATA_KUTUGU:
        s.append("| `%s` | %s | %s |" % (h["kod"], h["neden_basarisiz"],
                                         h["bu_projede_goruldu"]))
    g = ref.gorulen_hatalar()
    s += ["", "**Bu projede gerçekten görülen: %d / %d**"
          % (len(g), len(ref.HATA_KUTUGU)), ""]
    _yaz("Failure_Library.md", s)


def reference_principles():
    d = ref.DIS_REFERANS_DURUMU
    s = ["# Reference Principles", "",
         "## Dürüstlük notu", "",
         "| ölçüt | değer |", "|---|---|",
         "| dış referans kütüphanesi | **%s** |" % d["durum"],
         "| neden | %s |" % d["neden"],
         "| gereken | %s |" % d["gereken"],
         "| uydurma yapıldı mı | **%s** |" % d["uydurma_yapildi_mi"],
         "",
         "Aşağıdaki prensipler bu projede **ölçülen** kanıttan "
         "çıkarılmıştır; doğrulanmamış bir dış kaynağa atıf "
         "uydurulmamıştır.", ""]
    for p in ref.PRENSIPLER:
        s += ["## %s" % p["eksen"], "",
              "**Prensip:** %s" % p["prensip"], "",
              "**Kanıt:** %s" % p["kanit"], "",
              "**Uygulama:** %s" % p["uygulama"], ""]
    _yaz("Reference_Principles.md", s)


def print_exception(fin, trace):
    s = ["# Print Exception Report", "",
         "## Üç kademeli baskı kalitesi", "",
         "| kademe | eşik | anlamı |", "|---|---|---|",
         "| `DESIGN_PROTOTYPE_FLOOR` | ≥ 150 PPI | tasarım prototipinde "
         "kullanılabilir; **final print ready DEĞİL** |",
         "| `PRINT_QUALITY_TARGET` | ≥ 250 PPI | baskı kalitesi hedefi |",
         "| `PREFERRED_HIGH_QUALITY` | ≈ 300 PPI | kaynak izin verdiğinde |",
         "",
         "> **150 PPI premium baskı standardı değildir.** "
         "\"İnterpolasyon yok\" ile \"yüksek baskı kalitesi\" aynı şey "
         "değildir. Fiziksel prova final otoritedir ve **alınmadı**.", "",
         "## Yükseltme (upscaling)", "",
         "Hiçbir yerleşimde yukarı örnekleme yapılmadı; render motoru "
         "bunu `ValueError` ile reddediyor. `upscaled` alanı tüm "
         "yerleşimlerde `false`.", "",
         "## 5 finalin yerleşimleri", "",
         "| sayfa | yerleşim mm | efektif PPI | kademe | final print ready |",
         "|---|---|---|---|---|"]
    istisna = 0
    for k in fin["sayfalar"]:
        for p in k["yerlesim"]:
            if p["print_exception"]:
                istisna += 1
            s.append("| %s | %.0f × %.0f | **%.0f** | `%s` | %s |"
                     % (k["slot"], p["placement_size_mm"][0],
                        p["placement_size_mm"][1], p["effective_ppi"],
                        p["print_tier"],
                        "EVET" if p["final_print_ready"] else "**HAYIR**"))
    s += ["", "**5 finalde PRINT_QUALITY_EXCEPTION: %d yerleşim**" % istisna,
          "", "## 25 konseptin tamamı", "",
          "| ölçüt | değer |", "|---|---|",
          "| raster yerleşim | %d |" % trace["raster_placements"],
          "| PRINT_QUALITY_EXCEPTION | %d |"
          % sum(1 for p in trace["placements"] if p["print_exception"]),
          "", "## Açık risk", "",
          "- HERO/PRODUCT fotoğrafı 250 PPI altındaysa **FINAL PRINT READY "
          "otomatik PASS alamaz**.",
          "- Kâğıt, ICC profili ve TAC tavanı seçilmedi.",
          "- Matbaa provası alınmadı — **final otorite odur**.", ""]
    _yaz("Print_Exception_Report.md", s)


def sequence_record(fin):
    d = fin["dizi"]
    s = ["# Catalog Sequence Record", "",
         "Sayfalar tek tek değil **dizi** olarak tasarlandı ve birlikte "
         "ölçüldü.", "",
         "| # | sayfa | konsept | zemin ailesi | ort. L | yoğunluk | "
         "punto | repertuar | insan |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k in fin["sayfalar"]:
        s.append("| %d | %s | %s | %s | %.1f | %.4f | %.0f pt | %s | %s |"
                 % (k["sira"], k["slot"], k["konsept_id"], k["zemin_aile"],
                    k["ortalama_L"], k["olcum"]["metin"], k["olcum"]["punto"],
                    k["meta"]["repertuar"], "EVET" if k["insan_karesi"] else "—"))
    s += ["", "## Ritim", "",
          "- **renk:** %s" % " → ".join(d["COLOR"]),
          "- **ışık (ort. L):** %s" % d["LIGHT_DARK"],
          "- **yoğunluk:** %s" % d["DENSITY"],
          "- **ürün ölçeği:** %s" % d["PRODUCT_SCALE"],
          "- **repertuar:** %d ayrı kip" % len(set(d["REPERTOIRE"])),
          "- **koyu sayfa:** %d / %d" % (d["koyu_sayfa"], len(fin["sayfalar"])),
          "", "## Dizi bulguları", ""]
    if d["bulgular"]:
        s += ["| eksen | ağırlık | neden |", "|---|---|---|"]
        for b in d["bulgular"]:
            s.append("| %s | %s | %s |" % (b["eksen"], b["agirlik"], b["neden"]))
    else:
        s.append("Bulgu yok.")
    s += ["", "## Neden dizi denetimi gerekli", "",
          "Tur 2'de beş sayfanın dördü aynı sıcak krem zemin ailesine "
          "düştü ve **sayfa kapıları bunu yakalayamadı** çünkü her sayfa "
          "tek başına kusursuzdu. V2'nin ilk seçimi de aynı tuzağa düştü "
          "(4/5 nötr) ve dizi denetimi YÜKSEK itiraz verdi; seçim ritim "
          "kısıtıyla yenilendi.", ""]
    _yaz("Catalog_Sequence_Record.md", s)


def constitution(fin, trace):
    s = ["# L'CARLIÉ Catalog Design Constitution V2", "",
         "V1 anayasasının üzerine, bu turda **ölçümle** kazanılmış "
         "maddeler eklenmiştir. Her madde bir kanıta dayanır.", "",
         "## I · Bütünlük", "",
         "1. **Manifest üretimin eriştiği her kökü kapsar.** Üretimde "
         "kullanılan bir aset manifestte yoksa üretim durur. "
         "*(Kanıt: V1'de KINESIS aseti indeks dışındaydı ve "
         "`human_subject = 0` yanlış bir kapsam iddiası üretti.)*",
         "2. **`human_subject` ve `rights_status` ayrı alanlardır ve "
         "çelişemez.** UNKNOWN meşru bir değerdir.",
         "3. **Ölçüm önerir, gözlem karar verir.** Gözle doğrulama "
         "ölçümü ezer ve kayıt hangisinin konuştuğunu söyler. "
         "*(Kanıt: ten sezgiseli 16 karenin 12'sinde yanıldı.)*", "",
         "## II · Baskı kalitesi", "",
         "4. **150 PPI prototip tabanıdır, baskı standardı değildir.** "
         "150–249 PPI arası `PRINT_QUALITY_EXCEPTION` olarak kaydedilir.",
         "5. **HERO/PRODUCT fotoğrafı 250 PPI altındaysa final print "
         "ready otomatik PASS alamaz.**",
         "6. **\"İnterpolasyon yok\" ≠ \"yüksek baskı kalitesi\".** "
         "Fiziksel prova final otoritedir.",
         "7. **Yukarı örnekleme yasaktır** ve render motoru bunu "
         "`ValueError` ile reddeder.", "",
         "## III · Fikir", "",
         "8. **Her sayfa bir CONCEPT KERNEL'e bağlıdır.** Renk tarifi "
         "kernel değildir: \"mavi nemlendirme sayfası\" bir tarif, "
         "\"nem tutulan bir şeydir\" bir fikirdir.",
         "9. **Fikirsiz ama temiz sayfa Creative PASS alamaz.**",
         "10. **Gerçek bilgi geldiğinde çöken konsept REJECT alır.** "
         "*(Kanıt: KINESIS+ kutu metninde tanım, uyarı ve INCI yok; "
         "bu ürünün sayfaları bilgiyle değil anlamla taşınmak zorunda.)*", "",
         "## IV · Sayfa–ürün ilişkisi", "",
         "11. **Mekanik renk eşleşmesi yasaktır** (ürün rengi = sayfa "
         "zemini). Yedi meşru ilişkiden biri seçilir ve **kayda geçer**: "
         "`%s`." % "`, `".join(dna.ILISKILER),
         "12. **Bazen doğru karar ürün rengini sayfada hiç "
         "tekrarlamamaktır.**", "",
         "## V · Boşluk", "",
         "13. **Boşluk görünce doldurulmaz; önce ACTIVE/DEAD "
         "sınıflandırılır.** Renkli alan da boş olabilir. "
         "*(Kanıt: tur 2 FEMISIA'da ölçülen boşluk 0.00'dı çünkü alan "
         "renkliydi; gözle üçte biri işlevsizdi.)*",
         "14. **DEAD boşluk rastgele rozet/indeks/çizgiyle doldurulmaz; "
         "kompozisyon düzeltilir.**", "",
         "## VI · Bilgi", "",
         "15. **Fiyat ve barkod editoryal kompozisyona girmez.** Ayrı "
         "ticari SKU katmanı; fiyat değişince premium katalog eskimez.",
         "16. **INCI ne gri dipnot ne hero'dur** — tasarlanmış bir "
         "teknik bilgi bölgesidir.",
         "17. **TÜRKÇE adı / botanik (Latin) adı / INCI adı ayrı "
         "tutulur.** Bilgi yoksa uydurulmaz.",
         "18. **SANA NOT gerçek yazılabilir alandır**, dekoratif üç "
         "çizgi değil; kompozisyonun baştan planlanan utility space'i.",
         "19. **Her üründe aynı okuma sırası tekrarlanmaz.** Farklı "
         "layout değil farklı **bilgi koreografisi**.", "",
         "## VII · Ekip", "",
         "20. **MAKER ≠ JUDGE.** Independent Critic tasarım çözümü "
         "üretmez; Product Integrity kendi ihlalini affedemez.",
         "21. **CRAFT ve CONCEPT ayrı hüküm alır.** Craft PASS + "
         "Concept FAIL mümkündür ve Creative PASS verilmez.",
         "22. **Technical PASS ≠ Creative PASS.**",
         "23. **IDLE meşru bir durumdur.** Her görevde 18 rolü zorla "
         "çalıştırmak agent theater üretir.",
         "24. **Handoff yalnız structured artifact ile olur:** "
         "`%s`." % " · ".join(ek2.HANDOFF_ALANLARI),
         "25. **Persona promptu implementasyon değildir.** Binding yoksa "
         "rol UNBOUND sayılır.", "",
         "## VIII · Dizi", "",
         "26. **Sayfa tek başına mükemmel, katalog içinde yanlış "
         "olabilir.** Karar dizi üzerinden verilir.",
         "27. **Tek zemin ailesi dizinin üçte ikisini geçemez.** "
         "*(Kanıt: tur 2'de 4/5 sıcak krem; V2'nin ilk seçiminde 4/5 "
         "nötr — ikisi de dizi denetiminden YÜKSEK itiraz aldı.)*",
         "28. **Fotoğraf seçimi yerel kalite + dizi katkısı ile "
         "yapılır.** En güzel fotoğraf katalog için en doğru fotoğraf "
         "olmayabilir.", "",
         "## IX · Kaldırma", "",
         "29. **REMOVE TEST:** bir öğe kaldırıldığında bilgi, hiyerarşi, "
         "fikir, marka karakteri veya kompozisyon işlevi kaybedilmiyorsa "
         "**kaldırılır**. Lüks daha çok eleman değildir.", "",
         "## X · Dürüstlük", "",
         "30. **Premium score üretilmez.** Karar gerekçeyle verilir.",
         "31. **Gerçek kusur tespit edilip açıklamasız PASS verilemez.**",
         "32. **Yeni tur eski turdan kötüyse bu gizlenmez.** "
         "*(Bu turda uygulandı: V2 ürün varlığında Tur 3'ün gerisinde "
         "kaldı — %s vs %s ortalama fotoğraf alanı — ve hüküm REVISE.)*"
         % ("%22.2", "%56.7"), ""]
    _yaz("Catalog_Design_Constitution_V2.md", s)


def main() -> int:
    fin = json.loads((C / "v2-final-kayit.json").read_text(encoding="utf-8"))
    trace = json.loads((C / "trace-manifest.json").read_text(encoding="utf-8"))
    print("belgeler uretiliyor:")
    creative_department()
    capability_matrix()
    handoff_graph(fin)
    asset_index()
    failure_library()
    reference_principles()
    print_exception(fin, trace)
    sequence_record(fin)
    constitution(fin, trace)
    print("\ntoplam: %d belge -> %s" % (len(list(B.glob('*.md'))), B))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
