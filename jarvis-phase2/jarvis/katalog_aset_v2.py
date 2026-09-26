"""Asset Intelligence V2 -- manifest URETIMIN ERISTIGI HER ASETI kapsar.

V1'in butunluk kusuru: indeks yalnizca `cekim-ham` klasorunu tariyordu.
KINESIS sayfasi ise `pilot-assets/` icinden bir kare kullaniyordu --
yani uretimde kullanilan bir aset manifestte HIC YOKTU. Bu yuzden
"human_subject = 0" (indekslenen arsiv icin dogru) ile "KINESIS tek
insan karesi" (uretim sayfasi icin dogru) ayni raporda cakisti.

V2'de iki yapisal degisiklik:

1) KOKLER coklu. Uretimin okuyabildigi her klasor taranir.
2) human_subject ve rights_status AYRI alanlardir ve celisemezler;
   `dogrula()` celiskiyi hata olarak yukseltir.
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

# --- taranacak kokler: uretimin erisebildigi HER yer --------------------
KOKLER = (
    ("studio", pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-ham")),
    ("pilot", pathlib.Path("/opt/lcarlie/pilot-assets")),
    ("wix", pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/ham")),
)
TUREV_KOK = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-kesim")
KUNYE = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/kunye.json")
TANIMA = TUREV_KOK / "tanima.json"

CIKTI = pathlib.Path("/opt/lcarlie/output/creative-asset-library")

# --- baski kalite kademeleri (C) ----------------------------------------
PROTOTIP_TABANI = 150.0      # DESIGN / PROTOTYPE FLOOR
BASKI_HEDEFI = 250.0         # PRINT QUALITY TARGET
YUKSEK_KALITE = 300.0        # PREFERRED HIGH QUALITY

CEKIM_TIPI = {
    "ham": "studio_product",
    "detay": "macro_detail",
    "ham-kaynak": "lifestyle_human",
    "editli": "hand_edited",
}

FOTO_ROLLERI = (
    "HERO", "PRODUCT_EDITORIAL", "PACKSHOT", "DETAIL", "MACRO",
    "MATERIAL", "ATMOSPHERE", "TECHNICAL", "BOTANICAL",
    "HUMAN_LIFESTYLE", "SUPPORTING",
)

AILE = {
    "BABYSOL": "baby", "BABYSOFT": "baby", "BABYSHOWER": "baby",
    "BABYDENT": "baby", "MINISOOTH": "baby", "EASYCOMB": "baby",
    "NOMORE": "baby", "BRIGHTSMILE": "oral", "ORAGARDE": "oral",
    "CALMJAW": "oral", "KINESIS+": "sport", "DORSIVIA": "sport",
    "MENTHALIS": "sport", "CALMORIS": "sport", "DERMAMOVERA": "sport",
    "FEMISIA": "intimate", "INTIMBLANC": "intimate", "VIREON": "intimate",
    "HYDRAVIE": "face", "LUCIDERM": "face", "SERALIMBO": "face",
    "OPTYWAVE": "face", "SUNACNEA": "face", "DERMANOVA": "face",
    "LIFTELLA": "body", "DERMASTRA": "body", "DERMAVASC": "body",
    "DERMABED": "body", "DERMARNICA": "body", "DERMACORN": "foot",
    "DERMAGUARD": "foot", "CALMAROS": "tonic", "SOFTGUARD": "home",
    "BUGUARD": "home", "AUROLIS": "ear", "EARCLIA": "ear",
    "HAIRNOURIISHER": "hair", "LIPVORA": "lip",
}


# --- olcum yardimcilari --------------------------------------------------

def md5(p: pathlib.Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def dhash(p: pathlib.Path, n: int = 8) -> int:
    from PIL import Image
    with Image.open(p) as im:
        g = im.convert("L").resize((n + 1, n), Image.LANCZOS)
        px = list(g.getdata())
    b = []
    for r in range(n):
        for c in range(n):
            b.append(px[r * (n + 1) + c] > px[r * (n + 1) + c + 1])
    return sum(1 << i for i, x in enumerate(b) if x)


def mesafe(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def ten_payi(p: pathlib.Path) -> float:
    from PIL import Image
    with Image.open(p) as im:
        s = im.convert("YCbCr").resize((96, 96))
        px = list(s.getdata())
    n = sum(1 for y, cb, cr in px
            if 80 <= y <= 245 and 77 <= cb <= 127 and 133 <= cr <= 177)
    return round(n / len(px), 4)


def insan_ozne(p: pathlib.Path, tip: str, ten: float) -> tuple[str, list[str]]:
    """human_subject -- rights_status'tan AYRI alan.

    Tek basina ten esigi yetmiyor: sicak sari ambalaj (BABYSOL) YCbCr
    ten araligina dusuyor. Cekim tipi ve ten payi BIRLIKTE degerlendirilir.
    Emin olunamayan durum UNKNOWN'dir -- EVET ya da HAYIR'a zorlanmaz.
    """
    k = ["ten payi %.3f" % ten, "cekim tipi %s" % tip]
    if tip == "lifestyle_human":
        k.append("cekim tipi insan cekimi")
        return "EVET", k
    if tip in ("studio_product", "macro_detail", "hand_edited"):
        if ten >= 0.30:
            k.append("studyo karesinde beklenmedik yuksek ten payi")
            return "UNKNOWN", k
        k.append("studyo urun cekimi, sahnede insan beklenmiyor")
        return "HAYIR", k
    if ten >= 0.12:
        return "EVET", k
    if ten >= 0.05:
        return "UNKNOWN", k
    return "HAYIR", k


# --- INSAN DOGRULAMA: gozle teyit edilmis gecersiz kilma ----------------
# OLCULDU: ten-rengi sezgiseli sicak amber/sari urun fotografinda asiri
# isaretliyor. 16 isaretli karenin 12'sinde insan YOK; yalnizca ambalaj
# sicak tonlu. Asagidaki tablo GOZLE dogrulanmistir ve olcumu ezer.
# Olcum onerir, gozlem karar verir; kayit hangisinin konustugunu soyler.
INSAN_DOGRULAMA = {
    "babysol-2f9dd85d46": "HAYIR",   # duz zemin, sari sise
    "babysol-396011a519": "HAYIR",   # su/jel yuzey, sari sise
    "babysol-5892a1a733": "EVET",    # kadin omzuna krem suruyor
    "babysol-de9823b849": "HAYIR",   # duz beyaz, sari sise
    "femisia-for-women-8a31ed3fdc": "EVET",   # kadin govde/bacak
    "femisia-for-women-c35cd72cf2": "HAYIR",  # botanik naturmort
    "femisia-for-women-c6125cec97": "HAYIR",  # tas + isik, amber sise
    "hydravie-b5bb15d490": "EVET",   # kadin yuzune krem suruyor
    "kinesis-4f9e28543c": "EVET",    # erkek sinav cekiyor, spor salonu
    "kinesis-6b01303f27": "HAYIR",   # lime kutu + amber sise
    "kinesis-b56d0560c0": "HAYIR",   # flat-lay jel
    "kinesis-cf130a8ac5": "HAYIR",   # duz beyaz packshot
    "8684869609158": "HAYIR",        # HAIR NOURISHER amber sise
    "8684869609530": "HAYIR",        # BABYSOL sari sise
    "8684869609547": "HAYIR",        # KINESIS lime kutu
    "8684869609578": "HAYIR",        # CALMORIS amber roll-on
}


def dogrulanmis_insan(stem: str) -> str | None:
    return INSAN_DOGRULAMA.get(stem)


def haklar(kok: str, insan: str) -> tuple[str, str]:
    """rights_status -- insan_ozne ile CELISEMEZ."""
    if insan == "EVET":
        return ("UNKNOWN_HUMAN_SUBJECT",
                "Karede taninabilir kisi var; model sozlesmesi/mecra "
                "kapsami kayitta yok.")
    if insan == "UNKNOWN":
        return ("UNKNOWN_NEEDS_REVIEW",
                "Insan ozne olup olmadigi olcumle netlesmedi; gozle "
                "dogrulanmali.")
    if kok == "pilot":
        return ("UNKNOWN",
                "Wix urun sayfasi gorseli; uretim kaydi (fotograf/render/AI) "
                "belgelenmemis.")
    return ("UNKNOWN",
            "Kamera dosya adi gercek cekimi dusundurur ancak uretim kaydi yok.")


def foto_rolu(tip: str, a: dict, insan: str,
              en: int, boy: int) -> tuple[str, list[str]]:
    """photo_role -- yerel kaliteden AYRI bir siniflandirma."""
    k = []
    urun_alan = a.get("urun_alan_orani", 0.0)
    derinlik = a.get("derinlik_vekili", 1.0)
    kontrast = a.get("ton_hiyerarsisi", {}).get("kontrast_farki", 0.0)
    kenar = a.get("kenar_gerilimi", {})
    degiyor = bool(kenar.get("degiyor"))
    neg = 1.0 - urun_alan

    if insan == "EVET":
        k.append("karede insan ozne")
        return "HUMAN_LIFESTYLE", k
    if tip == "macro_detail":
        k.append("makro cekim oneki")
        if degiyor:
            k.append("konu kare kenarina degiyor -- asiri yakin")
            return "MACRO", k
        return "DETAIL", k
    if urun_alan < 0.06:
        k.append("urun alani %.3f -- nesne tanimlanamiyor" % urun_alan)
        return "MATERIAL", k
    if degiyor and urun_alan >= 0.30:
        k.append("urun kadraji dolduruyor ve kenara degiyor")
        return "HERO", k
    if derinlik <= 0.55 and kontrast >= 0.30:
        k.append("derinlik %.2f, kontrast %.2f -- mekan ve ayrisma var"
                 % (derinlik, kontrast))
        return "PRODUCT_EDITORIAL", k
    if neg >= 0.85 and derinlik >= 0.80:
        k.append("negatif alan %.2f, derinlik %.2f -- duz izole zemin"
                 % (neg, derinlik))
        return "PACKSHOT", k
    if urun_alan >= 0.22:
        k.append("urun alani %.3f -- editoryal urun karesi" % urun_alan)
        return "PRODUCT_EDITORIAL", k
    k.append("hicbir esik baskin degil")
    return "SUPPORTING", k


def kalite(a: dict, en: int, boy: int) -> dict:
    uzun = max(en, boy)
    kisa = min(en, boy)
    keskin = a.get("keskinlik") or 0.0
    return {
        "class": ("HIGH" if uzun >= 1800 and keskin >= 0.6
                  else "USABLE" if uzun >= 1200 and keskin >= 0.4
                  else "LOW"),
        "sharpness": keskin,
        "max_mm_at_150ppi": round(kisa * 25.4 / PROTOTIP_TABANI, 1),
        "max_mm_at_250ppi": round(kisa * 25.4 / BASKI_HEDEFI, 1),
        "max_mm_at_300ppi": round(kisa * 25.4 / YUKSEK_KALITE, 1),
        "evidence": ["uzun kenar %d px" % uzun, "kisa kenar %d px" % kisa,
                     "keskinlik %.2f" % keskin],
    }


def editoryal_guc(a: dict, tip: str, insan: str) -> dict:
    k = []
    p = 0
    kon = a.get("ton_hiyerarsisi", {}).get("kontrast_farki", 0)
    if kon >= 0.35:
        p += 1
        k.append("ton kontrasti %.2f" % kon)
    der = a.get("derinlik_vekili", 1)
    if der <= 0.6:
        p += 1
        k.append("derinlik %.2f -- mekan hissi" % der)
    neg = 1 - a.get("urun_alan_orani", 0)
    if 0.70 <= neg <= 0.92:
        p += 1
        k.append("negatif alan %.2f -- tipografi icin yer" % neg)
    if insan == "EVET":
        p += 1
        k.append("insan figuru")
    if tip == "macro_detail":
        p += 1
        k.append("makro malzeme karesi")
    if len(a.get("metin_guvenli_bolgeler", [])) >= 2:
        p += 1
        k.append("%d metin-guvenli bolge" % len(a["metin_guvenli_bolgeler"]))
    return {"class": "STRONG" if p >= 4 else "MEDIUM" if p >= 2 else "WEAK",
            "evidence": k}


def uygunluk(rol: str, kal: str) -> list[str]:
    if kal == "LOW":
        return ["index_thumbnail"]
    return {
        "HERO": ["product_page", "category_opener", "cover"],
        "PRODUCT_EDITORIAL": ["product_page", "category_opener"],
        "PACKSHOT": ["product_index", "sku_layer"],
        "DETAIL": ["material_page", "product_page", "cover"],
        "MACRO": ["material_page", "texture_band", "cover"],
        "MATERIAL": ["material_page", "texture_band", "cover"],
        "HUMAN_LIFESTYLE": ["category_opener", "cover", "interruption"],
        "SUPPORTING": ["product_page"],
    }.get(rol, ["product_page"])


# --- dogrulama -----------------------------------------------------------

class ManifestCelismesi(RuntimeError):
    pass


def dogrula(kayitlar: list[dict]) -> list[str]:
    """human_subject ve rights_status CELISEMEZ."""
    hata = []
    for r in kayitlar:
        i, h = r["human_subject"], r["rights_status"]
        if i == "EVET" and h != "UNKNOWN_HUMAN_SUBJECT":
            hata.append("%s: human_subject=EVET ama rights=%s" % (r["asset_id"], h))
        if i == "HAYIR" and h == "UNKNOWN_HUMAN_SUBJECT":
            hata.append("%s: human_subject=HAYIR ama rights insan diyor"
                        % r["asset_id"])
        if r["photo_role"] == "HUMAN_LIFESTYLE" and i != "EVET":
            hata.append("%s: photo_role HUMAN_LIFESTYLE ama human_subject=%s"
                        % (r["asset_id"], i))
        if r["photo_role"] not in FOTO_ROLLERI:
            hata.append("%s: bilinmeyen photo_role %s"
                        % (r["asset_id"], r["photo_role"]))
    return hata


def kapsama_denetimi(kayitlar: list[dict], kullanilan: list[str]) -> list[str]:
    """Uretimde kullanilan her aset manifestte OLMAK ZORUNDA."""
    var = {r["source_path"] for r in kayitlar}
    return [y for y in kullanilan if y not in var]


# --- indeksleme ----------------------------------------------------------

def indeksle(loglayici=print) -> list[dict]:
    import sys
    sys.path.insert(0, "/opt/lcarlie/source/worktrees/katalog-zeka/jarvis-phase2")
    from PIL import Image

    from jarvis import katalog_foto_analiz as fa
    from jarvis import katalog_varlik as vr

    tanima = {}
    if TANIMA.exists():
        for e in json.loads(TANIMA.read_text(encoding="utf-8")):
            tanima[pathlib.Path(e["dosya"]).stem] = e.get("urun", "BELIRSIZ")

    kunye = {}
    if KUNYE.exists():
        for e in json.loads(KUNYE.read_text(encoding="utf-8")):
            kunye[pathlib.Path(e["dosya"]).stem] = e.get("ad", "")

    turev = collections.defaultdict(list)
    if TUREV_KOK.is_dir():
        for p in TUREV_KOK.iterdir():
            if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                turev[p.stem].append(str(p))

    dosyalar = []
    for kok_ad, kok in KOKLER:
        if not kok.is_dir():
            loglayici("KOK YOK: %s" % kok)
            continue
        n = 0
        for p in sorted(kok.iterdir()):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                dosyalar.append((kok_ad, p))
                n += 1
        loglayici("kok %-8s %-58s %4d dosya" % (kok_ad, str(kok), n))
    loglayici("toplam taranacak: %d" % len(dosyalar))

    ham = []
    for kok_ad, p in dosyalar:
        try:
            with Image.open(p) as im:
                en, boy = im.size
        except (OSError, ValueError) as ex:
            loglayici("ATLANDI %s: %s" % (p.name, ex))
            continue
        ham.append(dict(kok=kok_ad, yol=p, en=en, boy=boy,
                        md5=md5(p), dh=dhash(p)))

    # algisal kumeleme -- KOK ICINDE (farkli kaynaklar karistirilmaz)
    ESIK = 5
    kume = [-1] * len(ham)
    g = 0
    for i in range(len(ham)):
        if kume[i] != -1:
            continue
        kume[i] = g
        for j in range(i + 1, len(ham)):
            if (kume[j] == -1 and ham[j]["kok"] == ham[i]["kok"]
                    and mesafe(ham[i]["dh"], ham[j]["dh"]) <= ESIK):
                kume[j] = g
        g += 1
    loglayici("algisal kume: %d" % g)

    kayitlar = []
    for i, h in enumerate(ham):
        p = h["yol"]
        onek = p.stem.split("--")[0] if "--" in p.stem else ""
        tip = CEKIM_TIPI.get(onek, "ecommerce" if h["kok"] == "pilot"
                             else "wix_product" if h["kok"] == "wix"
                             else "unknown")
        try:
            a = fa.analiz(p).sozluk()
        except (OSError, ValueError, ArithmeticError, KeyError,
                IndexError) as ex:
            # Toplu indeksleyici tek bozuk dosyada olmemeli; hangi
            # dosyada ne olustugu loglanir ve kayit atlanir.
            loglayici("ANALIZ HATASI %s: %s" % (p.name, ex))
            continue
        try:
            sinif = vr.siniflandir(p).asset_type
        except (OSError, ValueError, KeyError, IndexError):
            sinif = "UNKNOWN"

        ten = ten_payi(p)
        insan, insan_k = insan_ozne(p, tip, ten)
        teyit = dogrulanmis_insan(p.stem)
        if teyit is not None and teyit != insan:
            insan_k.append("OLCUM '%s' dedi; GOZLE DOGRULAMA '%s' -- "
                           "gozlem gecerli" % (insan, teyit))
            insan = teyit
        elif teyit is not None:
            insan_k.append("gozle dogrulandi: %s" % teyit)
        rol, rol_k = foto_rolu(tip, a, insan, h["en"], h["boy"])
        hak, hak_not = haklar(h["kok"], insan)
        kal = kalite(a, h["en"], h["boy"])
        ed = editoryal_guc(a, tip, insan)

        urun = tanima.get(p.stem) or kunye.get(p.stem, "")
        if not urun and h["kok"] == "pilot":
            urun = p.stem.split("-")[0].upper()
        urun = (urun or "UNKNOWN").upper().split(" (")[0].strip()

        kayitlar.append({
            "asset_id": "cal-%s" % h["md5"][:12],
            "source_root": h["kok"],
            "source_path": str(p),
            "derivatives": turev.get(p.stem, []),
            "product": urun,
            "product_family": AILE.get(urun, "UNKNOWN"),
            "shoot_type": tip,
            "photo_role": rol,
            "photo_role_evidence": rol_k,
            "asset_type": sinif,
            "resolution": [h["en"], h["boy"]],
            "aspect_ratio": round(h["en"] / h["boy"], 3),
            "quality": kal,
            "composition": {
                "product_box": a.get("urun_kutusu"),
                "weight_center": a.get("agirlik_merkezi"),
                "visual_motion": a.get("gorsel_hareket"),
                "edge_tension": a.get("kenar_gerilimi"),
                "depth_proxy": a.get("derinlik_vekili")},
            "lighting": {"angle_deg": a.get("isik_yonu_derece"),
                         "strength": a.get("isik_gucu"),
                         "tone_hierarchy": a.get("ton_hiyerarsisi")},
            "palette": [{"rgb": b["rgb"], "lab": b["lab"], "share": b["oran"]}
                        for b in a.get("baskin_renkler", [])[:3]],
            "negative_space": {
                "ratio": round(1 - a.get("urun_alan_orani", 0), 3),
                "regions": a.get("negatif_bolgeler", [])[:3]},
            "text_safe_regions": a.get("metin_guvenli_bolgeler", [])[:3],
            "crop_potential": a.get("kadraj_firsatlari", []),
            "product_prominence": {
                "area_ratio": a.get("urun_alan_orani"),
                "saliency_share": a.get("saliency_urun_payi")},
            "editorial_strength": ed,
            "catalog_suitability": uygunluk(rol, kal["class"]),
            "human_subject": insan,
            "human_subject_evidence": insan_k,
            "provenance": {
                "status": "UNKNOWN",
                "note": hak_not,
                "capture_hint": ("DSC" if "DSC" in p.stem else
                                 "IMG" if "IMG" in p.stem else
                                 "WIX" if h["kok"] in ("wix", "pilot")
                                 else "UNKNOWN")},
            "rights_status": hak,
            "notes": [],
            "_cluster": kume[i],
            "_md5": h["md5"],
        })
        if (i + 1) % 60 == 0:
            loglayici("  analiz %d/%d" % (i + 1, len(ham)))

    # kume ici siralama
    kg = collections.defaultdict(list)
    for r in kayitlar:
        kg[r["_cluster"]].append(r)
    KS = {"HIGH": 0, "USABLE": 1, "LOW": 2}
    ES = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2}
    for c, uy in kg.items():
        uy.sort(key=lambda r: (KS.get(r["quality"]["class"], 9),
                               ES.get(r["editorial_strength"]["class"], 9),
                               -(r["quality"]["sharpness"] or 0)))
        for k, r in enumerate(uy):
            r["cluster_id"] = "cl-%04d" % c
            r["cluster_size"] = len(uy)
            r["cluster_rank"] = k + 1
            r["is_cluster_representative"] = (k == 0)
    for r in kayitlar:
        r.pop("_cluster", None)
    return kayitlar


def urun_tekil(kayitlar: list[dict], urun: str,
               kok: str | None = None) -> list[dict]:
    """Urun icinde tekillestir -- kuresel kume temsilcisi KULLANILAMAZ.

    dHash ayni mavi sonsuz fonda farkli urunleri tek kumede birlestiriyor.
    """
    KS = {"HIGH": 0, "USABLE": 1, "LOW": 2}
    ES = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2}

    def sira(r):
        return (KS.get(r["quality"]["class"], 9),
                ES.get(r["editorial_strength"]["class"], 9),
                -(r["quality"]["sharpness"] or 0))

    r = [x for x in kayitlar if x["product"] == urun
         and (kok is None or x["source_root"] == kok)]
    en_iyi: dict[str, dict] = {}
    for x in sorted(r, key=sira):
        en_iyi.setdefault(x["cluster_id"], x)
    return sorted(en_iyi.values(), key=sira)


def ozet(kayitlar: list[dict]) -> dict:
    return {
        "kayit": len(kayitlar),
        "tekil_fotograf": len({r["cluster_id"] for r in kayitlar}),
        "kok_dagilimi": dict(collections.Counter(
            r["source_root"] for r in kayitlar)),
        "photo_role": dict(collections.Counter(
            r["photo_role"] for r in kayitlar)),
        "human_subject": dict(collections.Counter(
            r["human_subject"] for r in kayitlar)),
        "rights_status": dict(collections.Counter(
            r["rights_status"] for r in kayitlar)),
        "quality": dict(collections.Counter(
            r["quality"]["class"] for r in kayitlar)),
    }


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    kay = indeksle()
    hata = dogrula(kay)
    (CIKTI / "index-v2.json").write_text(
        json.dumps(kay, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    o = ozet(kay)
    print("\n=== ASSET INTELLIGENCE V2 ===")
    for k, v in o.items():
        print("%-18s %s" % (k, v))
    print("\ndogrulama hatasi: %d" % len(hata))
    for h in hata[:10]:
        print("  ", h)
    (CIKTI / "index-v2-ozet.json").write_text(
        json.dumps({"ozet": o, "dogrulama_hatalari": hata},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if hata else 0


if __name__ == "__main__":
    raise SystemExit(main())
