"""Creative Department V2 -- MEVCUT 18 rolu UPGRADE eder, yenisini uydurmaz.

Kaynak roller: jarvis.katalog_yetenek.KUTUK (18 kayit, degistirilmedi).
Bu modul her role V1'de EKSIK olan alanlari ekler ve rolu gercek
pipeline asamasina BAGLAR:

    unique_capability  -- yalnizca bu rolun yapabildigi sey
    when_to_invoke     -- hangi kosulda cagrilir
    when_not_to_invoke -- hangi kosulda CAGRILMAZ (IDLE mesru durumdur)
    failure_modes      -- bu rol bozulursa nasil gorunur
    tests              -- bunu dogrulayan gercek test adlari
    stages             -- sahiplendigi pipeline asamalari
    binding            -- asamayi yuruten gercek cagrilabilir/modul

Persona promptu IMPLEMENTATION degildir: binding bos ise rol
UNBOUND sayilir ve rapora oyle gecer.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass

from jarvis import katalog_yetenek as ky

# --- H: gercek pipeline asamalari ---------------------------------------
ASAMALAR = (
    "PRODUCT_TRUTH", "BRAND_DNA", "CATEGORY_DNA", "PRODUCT_VISUAL_DNA",
    "CONCEPT_KERNEL", "ASSET_INTELLIGENCE", "ASSET_BOARD",
    "PHOTOGRAPHY_SELECTION", "COLOR_MATERIAL_LIGHT",
    "INFORMATION_CHOREOGRAPHY", "COMPOSITION", "TYPOGRAPHY_AD",
    "INGREDIENT_AD", "TECHNICAL_INCI", "MICROTYPOGRAPHY", "RENDER",
    "TECHNICAL_QA", "PRODUCT_INTEGRITY", "REGULATORY", "CRAFT_CRITIQUE",
    "CONCEPT_CRITIQUE", "SEQUENCE_REVIEW", "REMOVE_TEST", "ECD_APPROVAL",
    "PREPRESS",
)

# --- F: handoff sozlesmesi ----------------------------------------------
HANDOFF_ALANLARI = ("TASK", "INPUT", "EVIDENCE", "CONSTRAINTS",
                    "DECISION", "OUTPUT", "OPEN_RISK", "NEXT_OWNER")

BOS_MESAJ_KALIPLARI = (
    "katiliyorum", "katılıyorum", "guzel olmus", "güzel olmuş",
    "premium gorunuyor", "premium görünüyor", "bence de", "onaylarim",
    "onaylarım", "diger uzmana soralim", "diğer uzmana soralım",
    "harika", "mukemmel", "mükemmel", "cok iyi", "çok iyi",
)


@dataclass(frozen=True)
class Handoff:
    """Roller arasi TEK gecerli iletisim birimi."""
    task: str
    input: str
    evidence: list[str]
    constraints: list[str]
    decision: str
    output: str
    open_risk: list[str]
    next_owner: str
    owner: str = ""
    stage: str = ""
    consumes: tuple[str, ...] = ()

    def dogrula(self) -> list[str]:
        h = []
        if not self.task.strip():
            h.append("TASK bos")
        if not self.evidence:
            h.append("EVIDENCE bos -- kanitsiz handoff gecersiz")
        if not self.decision.strip():
            h.append("DECISION bos")
        if not self.next_owner.strip():
            h.append("NEXT_OWNER bos")
        metin = " ".join([self.task, self.decision, self.output]).lower()
        for kalip in BOS_MESAJ_KALIPLARI:
            if kalip in metin and len(metin) < 160:
                h.append("AGENT_THEATER suphesi: bos onay kalibi '%s'" % kalip)
                break
        return h


@dataclass(frozen=True)
class RolEk:
    id: str
    unique_capability: str
    when_to_invoke: str
    when_not_to_invoke: str
    failure_modes: tuple[str, ...]
    tests: tuple[str, ...]
    stages: tuple[str, ...]
    binding: str = ""
    maker_or_judge: str = "MAKER"     # G: uretici / degerlendirici ayrimi
    notes: str = ""


# --- 18 rolun upgrade kaydi ---------------------------------------------
EK = {
    "C01": RolEk(
        "C01",
        "Turun tezini koyar ve DIZI butunlugune karar verir; tek sayfayi "
        "degil katalogun tamamini kabul/red eder.",
        "Tur basinda (kernel onayi) ve tur sonunda (dizi onayi).",
        "Tek sayfalik teknik duzeltmede cagrilmaz -- o AD'nin isidir.",
        ("Sayfa sayfa onaylayip diziyi hic gormemek (tur 2 kusuru).",
         "Kendi urettigi fikri kendi onaylamak."),
        ("test_dizide_koyu_sayfa_var", "test_roller_benzersiz"),
        ("BRAND_DNA", "CONCEPT_KERNEL", "SEQUENCE_REVIEW", "ECD_APPROVAL"),
        "jarvis.katalog_dna.MARKA_DNA + katalog_v2.dizi_ritmi",
        "JUDGE",
        "X maddesi: Reference/Taste capability bu role eklendi, ayri "
        "agent acilmadi."),
    "C02": RolEk(
        "C02",
        "Kategori DNA'sini olculen urun gercekligiyle baglar; markanin "
        "genislik tezini savunur.",
        "Kategori acilisi ve kapak kararlarinda.",
        "Tek urunun ic sayfasinda cagrilmaz.",
        ("Kategoriyi renk paletine indirgemek.",
         "Rakip konumunu sayfaya tasimamak."),
        ("test_kategori_dna_tam",),
        ("CATEGORY_DNA", "PRODUCT_VISUAL_DNA"),
        "jarvis.katalog_dna.KATEGORI_DNA",
        "MAKER"),
    "C03": RolEk(
        "C03",
        "Referanstan PRENSIP cikarir; referansi kopyalamaz.",
        "Yeni gorsel dil aranirken.",
        "Uretim asamasinda cagrilmaz -- prensip zaten kararlasmistir.",
        ("Referansi taklit etmek.",
         "Prensibi gerekcesiz 'iyi gorunuyor' diye almak."),
        ("test_referans_prensibe_cevrilmis",),
        ("BRAND_DNA", "COLOR_MATERIAL_LIGHT"),
        "jarvis.katalog_referans.PRENSIPLER",
        "MAKER"),
    "C04": RolEk(
        "C04",
        "Her urun icin FARKLI bilgi koreografisi kurar (FIRST/SECOND/"
        "THIRD/TECHNICAL/UTILITY READ).",
        "Her urun sayfasinda.",
        "Kapakta cagrilmaz -- kapakta urun bilgisi yoktur.",
        ("Butun urunlerde ayni okuma sirasini tekrarlamak (tur 1 kusuru).",
         "Metni azaltip yerine bir sey koymamak (tur 2 kusuru)."),
        ("test_koreografi_benzersiz",),
        ("INFORMATION_CHOREOGRAPHY", "TECHNICAL_INCI"),
        "jarvis.katalog_konsept_v2.KOREOGRAFI",
        "MAKER"),
    "C05": RolEk(
        "C05",
        "Onayli kutu metninden editoryal cumle AYIKLAR; yeni iddia yazmaz.",
        "Sayfa metni gerekli oldugunda.",
        "Kutu metni eksikse cagrilmaz -- UNKNOWN doner, uydurmaz.",
        ("Kutuda olmayan fayda iddiasi yazmak.",
         "Etiket cumlesini editoryal cumle sanmak (tur 2 KINESIS kusuru)."),
        ("test_icerik_kutu_gercegi_kaynakli",),
        ("PRODUCT_TRUTH", "INFORMATION_CHOREOGRAPHY"),
        "jarvis.katalog_icerik_v2.yukle",
        "MAKER"),
    "C06": RolEk(
        "C06",
        "Zorunlu ibare ve yasak iddia denetimi; HARD_REJECT yetkisi.",
        "Metin iceren HER sayfada.",
        "Hicbir kosulda atlanmaz.",
        ("Zorunlu uyariyi sayfada unutmak.",
         "Kendi ihlalini affetmek."),
        ("test_zorunlu_uyari_basili", "test_yasak_iddia_yok"),
        ("REGULATORY",),
        "jarvis.katalog_icerik_v2 + katalog_v2.mevzuat_kapisi",
        "JUDGE"),
    "C07": RolEk(
        "C07",
        "Kompozisyonu ve fotograf secimini kurar; bosluğu ACTIVE/DEAD "
        "olarak SINIFLANDIRIR (doldurmaz).",
        "Her sayfada.",
        "Mevzuat/prepress karariyla cakisirsa geri ceker.",
        ("Boslugu gorunce doldurmak (T maddesi ihlali).",
         "En guzel kareyi dizi katkisina bakmadan secmek."),
        ("test_bosluk_siniflandirildi",),
        ("PHOTOGRAPHY_SELECTION", "COLOR_MATERIAL_LIGHT", "COMPOSITION"),
        "jarvis.katalog_konsept_v2 + katalog_aset_v2.urun_tekil",
        "MAKER",
        "X maddesi: Reference/Taste capability bu role de eklendi."),
    "C07A": RolEk(
        "C07A",
        "Aseti TYPE A/B/C/D siniflandirir ve izinsiz islemi HARD_REJECT eder.",
        "Her aset kullanimindan ONCE.",
        "Hicbir kosulda atlanmaz.",
        ("TYPE A karede arka plan silmek.",
         "Insan ozneyi zemin duzlugune bakarak siniflandirmak."),
        ("test_varlik_izin_matrisi",),
        ("ASSET_INTELLIGENCE",),
        "jarvis.katalog_varlik.siniflandir",
        "JUDGE"),
    "C08": RolEk(
        "C08",
        "Sayfa planini gercek olculere cevirir; akisi satir sayisindan "
        "hesaplar.",
        "Render oncesi her sayfada.",
        "Konsept asamasinda cagrilmaz.",
        ("Blok yuksekligini tahmin etmek.",
         "Guvenli alani asan metin birakmak."),
        ("test_kadraj_orani_yerlesim_oranina_esit",),
        ("COMPOSITION", "RENDER"),
        "jarvis.katalog_render.blok_yuksekligi_mm + pdf_uret",
        "MAKER"),
    "C09A": RolEk(
        "C09A",
        "Tipografik REPERTUAR secer: her sayfa ayni display refleksine "
        "dusmez.",
        "Her sayfada.",
        "Salt teknik QA duzeltmesinde cagrilmaz.",
        ("Her sayfada dev bold manset (tur 1 kusuru).",
         "Olcek araliginin daralmasi (tur 2 kusuru: 14-19 pt)."),
        ("test_tipografik_repertuar_cesitli",),
        ("TYPOGRAPHY_AD", "MICROTYPOGRAPHY"),
        "jarvis.katalog_tasarim_sistemi.TIP + katalog_konsept_v2",
        "MAKER"),
    "C09B": RolEk(
        "C09B",
        "Punto tabani, guvenli alan, cakisma ve font gomulmesini OLCER; "
        "HARD_REJECT yetkisi.",
        "Uretilen HER PDF'te.",
        "Hicbir kosulda atlanmaz.",
        ("PDF glif kontrolu yapmaya calismak (subset cmap Unicode degil).",
         "Uyariyi durduran ihlal sanmak."),
        ("test_katalog_tipografi_qa",),
        ("TECHNICAL_QA",),
        "jarvis.katalog_tipografi_qa.kapi",
        "JUDGE"),
    "C10": RolEk(
        "C10",
        "Fotografin kendi cercevesine saygiyi denetler; kadraj kazasini "
        "yakalar.",
        "Fotograf yerlesimi degistiginde.",
        "Metin-only sayfada cagrilmaz (orn. SKU katmani).",
        ("Urunun logotype'ini kelime ortasindan kesmek.",
         "Yatay kutuyu dar dikey kolona sikistirmak."),
        ("test_kadraj_kutusu_goruntu_icinde",),
        ("PHOTOGRAPHY_SELECTION", "COMPOSITION"),
        "jarvis.katalog_konsept3.kadraj + katalog_foto_analiz",
        "MAKER"),
    "C11": RolEk(
        "C11",
        "Uretken model ciktisinin katalogda kullanilmasini denetler.",
        "Bir aset uretken bir modelden gectiyse.",
        "Gercek cekim asetlerinde IDLE -- mesru durumdur.",
        ("Uretilmis gorseli gercek cekim sanmak.",),
        ("test_koken_uretken_islem_yok",),
        ("PRODUCT_INTEGRITY",),
        "jarvis.katalog_butunluk.URETKEN_ISLEMLER",
        "JUDGE"),
    "C12": RolEk(
        "C12",
        "Urun pikselinin kokenini zincirle dogrular; kendi ihlalini "
        "AFFEDEMEZ.",
        "Her sayfada.",
        "Hicbir kosulda atlanmaz.",
        ("Kokeni olmayan aseti 'muhtemelen fotograf' diye gecirmek.",),
        ("test_katalog_butunluk",),
        ("PRODUCT_INTEGRITY",),
        "jarvis.katalog_butunluk.kapi",
        "JUDGE"),
    "C13": RolEk(
        "C13",
        "CRAFT ve CONCEPT icin AYRI hukum verir; tasarim cozumu URETMEZ.",
        "Her konsept ve her final oncesi.",
        "Cozum onerisi istendiginde cagrilmaz -- o AD'nin isidir.",
        ("Elestiri yerine cozum yazmak (maker/judge sinirini gecmek).",
         "Craft PASS gorunce Concept'i de PASS vermek."),
        ("test_craft_concept_ayri",),
        ("CRAFT_CRITIQUE", "CONCEPT_CRITIQUE", "REMOVE_TEST"),
        "katalog_v2.elestirmen",
        "JUDGE"),
    "C14": RolEk(
        "C14",
        "Sayfayi eczane tezgahindaki 90 saniyeye gore denetler.",
        "Urun sayfalarinda.",
        "Kapakta cagrilmaz.",
        ("Not alaninin dekoratif ciziye donusmesi (R maddesi).",
         "Uzaktan okunmayan urun adi."),
        ("test_not_alani_gercek_yazilabilir",),
        ("INFORMATION_CHOREOGRAPHY", "REMOVE_TEST"),
        "katalog_v2.saha_denetimi",
        "JUDGE"),
    "C15": RolEk(
        "C15",
        "Baski kalite kademesini uygular ve PRINT_QUALITY_EXCEPTION kaydi "
        "tutar; print-blocking sorunu GECIREMEZ.",
        "Her yerlesimde.",
        "Hicbir kosulda atlanmaz.",
        ("150 PPI'i premium baski standardi saymak (V1 kusuru).",
         "'Interpolasyon yok' ile 'yuksek baski kalitesi'ni esitlemek."),
        ("test_ppi_kademeleri", "test_print_exception_kaydi"),
        ("PREPRESS", "RENDER"),
        "katalog_v2.baski_kademesi",
        "JUDGE"),
    "HUMAN": RolEk(
        "HUMAN",
        "Fiziksel prova uzerinden FINAL BASKI onayi; tek gercek otorite.",
        "Matbaa provasi geldiginde.",
        "Dijital asamada cagrilmaz -- prova yoksa onay da yoktur.",
        ("Ekran onayini baski onayi saymak.",),
        (),
        ("PREPRESS",),
        "",
        "JUDGE",
        "binding BOS: fiziksel prova hentiz alinmadi -- UNBOUND."),
}

# --- INGREDIENT / MICROTYPOGRAPHY / SEQUENCE sahipligi -------------------
EK_ASAMA_SAHIBI = {
    "INGREDIENT_AD": "C07",      # ingredient art direction AD'ye ait
    "ASSET_BOARD": "C07",
    "PRODUCT_TRUTH": "C05",
    "SEQUENCE_REVIEW": "C01",
    "REMOVE_TEST": "C13",
}


# --- F: agent theater denetimi ------------------------------------------

def theater_taramasi(handoffs: list[Handoff],
                     roller: dict[str, RolEk] | None = None) -> dict:
    """DEAD_OUTPUT / ORPHAN_ROLE / DUPLICATE_CAPABILITY / AGENT_THEATER."""
    roller = roller or EK
    bulgular = []

    gorev_alan = collections.Counter(h.owner for h in handoffs)
    tuketilen = collections.Counter(h.next_owner for h in handoffs)

    for rid in roller:
        if gorev_alan.get(rid, 0) == 0:
            bulgular.append({"tip": "IDLE", "rol": rid,
                             "neden": "bu turda gorev almadi",
                             "agirlik": "BILGI"})

    for h in handoffs:
        if h.next_owner not in roller and h.next_owner not in ("SON", "HUMAN"):
            bulgular.append({"tip": "ORPHAN_ROLE", "rol": h.next_owner,
                             "neden": "handoff bilinmeyen role gidiyor",
                             "agirlik": "YUKSEK"})
        if h.owner not in tuketilen and h.next_owner == "SON":
            pass
        hatalar = h.dogrula()
        for e in hatalar:
            bulgular.append({"tip": "AGENT_THEATER" if "THEATER" in e
                             else "GECERSIZ_HANDOFF",
                             "rol": h.owner, "neden": e, "agirlik": "YUKSEK"})

    # DEAD_OUTPUT: uretilen cikti hicbir downstream tarafindan
    # tuketilmiyor. Tuketim iki yoldan kanitlanabilir: downstream
    # `input` metninde adi gecer, ya da downstream `consumes` listesinde
    # ACIKCA bildirilir. Yalniz metin eslesmesine bakmak 4 yanlis
    # DEAD_OUTPUT uretmisti.
    girdiler = " || ".join(h.input for h in handoffs)
    tuketilen_ciktilar = set()
    for h in handoffs:
        tuketilen_ciktilar.update(h.consumes)
    for h in handoffs:
        cikti = h.output
        if not cikti or h.next_owner == "SON":
            continue
        if cikti in girdiler or cikti in tuketilen_ciktilar:
            continue
        bulgular.append({"tip": "DEAD_OUTPUT", "rol": h.owner,
                         "neden": "cikti '%s' hicbir downstream tarafindan "
                                  "tuketilmiyor" % cikti[:48],
                         "agirlik": "ORTA"})

    # DUPLICATE_CAPABILITY: ayni asamayi AYNI DURUSTAKI iki rol
    # yuruttuyse. Bir MAKER ile bir JUDGE ayni asamada bulunabilir --
    # biri tasarlar, digeri yargilar; bu G maddesinin geregidir, kusur
    # degildir. Dedektor once bunu duplicate saniyordu.
    asama_sahibi = collections.defaultdict(set)
    for h in handoffs:
        if h.stage:
            asama_sahibi[h.stage].add(h.owner)
    for asama, sahipler in asama_sahibi.items():
        if len(sahipler) < 2:
            continue
        durus = collections.defaultdict(list)
        for r in sahipler:
            e = roller.get(r)
            durus[e.maker_or_judge if e else "?"].append(r)
        for d, rs in durus.items():
            if len(rs) > 1:
                bulgular.append({"tip": "DUPLICATE_CAPABILITY",
                                 "rol": "/".join(sorted(rs)),
                                 "neden": "ayni asama (%s) ayni durusta (%s) "
                                          "iki rol tarafindan yurutuldu"
                                          % (asama, d),
                                 "agirlik": "ORTA"})

    return {
        "handoff": len(handoffs),
        "gorev_alan_rol": len([r for r in roller if gorev_alan.get(r, 0)]),
        "idle_rol": len([r for r in roller if not gorev_alan.get(r, 0)]),
        "bulgular": bulgular,
        "yuksek": [b for b in bulgular if b["agirlik"] == "YUKSEK"],
    }


# --- G: maker / judge ayrimi --------------------------------------------

def maker_judge_denetimi(handoffs: list[Handoff]) -> list[dict]:
    """Ureten ekip ile degerlendiren ekip ayrilmali."""
    hata = []
    for h in handoffs:
        e = EK.get(h.owner)
        if not e:
            continue
        if e.maker_or_judge == "JUDGE" and h.stage in (
                "COMPOSITION", "TYPOGRAPHY_AD", "INGREDIENT_AD",
                "COLOR_MATERIAL_LIGHT"):
            hata.append({"rol": h.owner, "asama": h.stage,
                         "neden": "JUDGE rolu tasarim cozumu uretiyor"})
        if e.maker_or_judge == "MAKER" and h.stage in (
                "TECHNICAL_QA", "REGULATORY", "PRODUCT_INTEGRITY",
                "CRAFT_CRITIQUE", "CONCEPT_CRITIQUE"):
            hata.append({"rol": h.owner, "asama": h.stage,
                         "neden": "MAKER rolu kendi isini yargiliyor"})
    return hata


# --- rapor ---------------------------------------------------------------

def matris() -> list[dict]:
    """18 rolun V1 kaydi + V2 eki -- Agent_Capability_Matrix kaynagi."""
    out = []
    for y in ky.KUTUK:
        e = EK.get(y.id)
        out.append({
            "id": y.id, "name": y.name, "type": y.type,
            "purpose": y.purpose,
            "domain_knowledge": list(y.knowledge_required),
            "tools": list(y.tools_required),
            "input_contract": list(y.inputs),
            "output_contract": list(y.outputs),
            "evidence": list(y.evidence),
            "authority": list(y.authority),
            "rejection_rights": list(y.rejection_conditions),
            "upstream": list(y.upstream),
            "downstream": list(y.downstream),
            "v1_status": y.implementation_status,
            "unique_capability": e.unique_capability if e else "",
            "when_to_invoke": e.when_to_invoke if e else "",
            "when_not_to_invoke": e.when_not_to_invoke if e else "",
            "failure_modes": list(e.failure_modes) if e else [],
            "tests": list(e.tests) if e else [],
            "stages": list(e.stages) if e else [],
            "binding": e.binding if e else "",
            "maker_or_judge": e.maker_or_judge if e else "",
            "bound": bool(e and e.binding),
        })
    return out


def kapsama() -> dict:
    """Her pipeline asamasinin sahibi var mi."""
    sahip = collections.defaultdict(list)
    for rid, e in EK.items():
        for s in e.stages:
            sahip[s].append(rid)
    for s, r in EK_ASAMA_SAHIBI.items():
        if r not in sahip[s]:
            sahip[s].append(r)
    return {
        "asama": len(ASAMALAR),
        "sahipli": sum(1 for s in ASAMALAR if sahip.get(s)),
        "sahipsiz": [s for s in ASAMALAR if not sahip.get(s)],
        "sahipler": {s: sahip.get(s, []) for s in ASAMALAR},
        "unbound_rol": [r for r, e in EK.items() if not e.binding],
    }


if __name__ == "__main__":
    m = matris()
    k = kapsama()
    print("rol: %d  bagli: %d  unbound: %s"
          % (len(m), sum(1 for x in m if x["bound"]), k["unbound_rol"]))
    print("asama: %d  sahipli: %d  sahipsiz: %s"
          % (k["asama"], k["sahipli"], k["sahipsiz"]))
    print()
    print("%-6s %-34s %-10s %-26s %s"
          % ("id", "name", "m/j", "stages", "bound"))
    for x in m:
        print("%-6s %-34s %-10s %-26s %s"
              % (x["id"], x["name"][:34], x["maker_or_judge"],
                 ",".join(x["stages"])[:26], "EVET" if x["bound"] else "HAYIR"))
