"""PRODUCT TRUTH -- kaynak hiyerarsili, provenance tutan gercek bilgi.

V2'nin kusuru: kutu-gercegi TEK kaynak sayildi. "KINESIS+ icin tanim,
uyari ve INCI YOK" dedim -- kutu-gercegi icin dogruydu ama SISTEM icin
yanlisti. Urun dosyasinda (knowledge/30-urun-kinesis.md) tam INCI,
tanim ve mevzuat denetcisinden gecmis 7 satis cumlesi duruyordu.

V2.1'de her alan su dortluyu tasir:
    value · source · source_authority · status · last_verified

Dusuk otoriteli kaynak yuksek otoriteliyi EZEMEZ. Iki kaynak celisirse
status=CONFLICT ve deger final artwork'a BASILMAZ. Bulunamazsa UNKNOWN.
"""
from __future__ import annotations

import json
import pathlib
import re

KUTU = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/kutu-gercegi")
DOSYA = pathlib.Path("/opt/lcarlie/jarvis-phase2/knowledge")
MADDE = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/madde-haritasi.json")

BILINMIYOR = "UNKNOWN"
CELISKI = "CONFLICT"

# --- kaynak otorite merdiveni (kucuk sayi = yuksek otorite) -------------
OTORITE = {
    "human_verified_override": 1,
    "approved_packaging_label": 2,   # kutu-gercegi (onayli_kutu_metni)
    "inci_formulation_file": 3,
    "product_dossier": 4,            # knowledge/30-urun-*.md
    "wix_product_record": 5,         # mart.urun_karti / raw.wix_urun
    "ingredient_map": 6,             # madde-haritasi.json
    "packshot_label_read": 7,        # fotograftan okunan etiket
    "legacy_catalog": 8,
}

ANAHTAR_DOSYA = {
    "hydravie": "30-urun-hydravie.md",
    "kinesis+": "30-urun-kinesis.md",
    "femisia": "30-urun-femisia.md",
    "vireon": "30-urun-vireon.md",
    "babysol": "30-urun-babysol.md",
}

# --- 1 · INSAN DOGRULAMALI OVERRIDE ------------------------------------
# En yuksek otorite. Yalnizca gozle/olcumle teyit edilmis degerler.
OVERRIDE = {
    ("babysol", "net_miktar"): {
        "value": BILINMIYOR,
        "status": CELISKI,
        "note": "Kutu etiketinde 150 ml, sise etiketinde 100 ml okunuyor "
                "(ham--DSC04498 ve babysol packshot). Ayri SKU olabilir. "
                "Cozulene kadar final artwork'a BASILMAZ.",
    },
}


def _alan(value, kaynak, durum="OK", tarih="2026-09-26", not_=""):
    return {"value": value, "source": kaynak,
            "source_authority": OTORITE.get(kaynak, 99),
            "status": durum, "last_verified": tarih, "note": not_}


def _temiz(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\(EN\).*$", "", s, flags=re.S)
    s = re.sub(r"\(TR\)|\(Uyar[ıi]lar\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _inci_kes(s: str) -> str:
    s = _temiz(s)
    for a in ("Bileşen", "Bilesen", "Oran (%)"):
        i = s.find(a)
        if i > 0:
            s = s[:i]
    s = s.strip().rstrip(".")
    return (s + ".") if s else ""


# --- 2 · ONAYLI KUTU METNI ---------------------------------------------

def _kutudan(anahtar: str) -> dict:
    p = KUTU / ("%s.json" % anahtar)
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    b = d.get("bolumler", {})
    out = {}
    for alan, ham in (("tanim", b.get("tanim")), ("kullanim", b.get("kullanim")),
                      ("uyari", b.get("uyarilar"))):
        v = _temiz(ham or "")
        for kes in ("Nioli", "Bileşen", "Oran (%)"):
            i = v.find(kes)
            if i > 60:
                v = v[:i].strip()
        if v:
            out[alan] = _alan(v, "approved_packaging_label")
    inci = _inci_kes(b.get("inci", ""))
    if inci:
        out["inci"] = _alan(inci, "approved_packaging_label")
    raf = _temiz(b.get("raf_omru", ""))
    if raf and "INCI" not in raf:
        out["raf_omru"] = _alan(raf, "approved_packaging_label")
    return out


# --- 3 · URUN DOSYASI ---------------------------------------------------

def _bolum(metin: str, baslik: str) -> str:
    m = re.search(r"^##+\s*%s\s*$(.*?)(?=^##\s|\Z)" % re.escape(baslik),
                  metin, flags=re.M | re.S)
    return m.group(1).strip() if m else ""


def _dosyadan(anahtar: str) -> dict:
    ad = ANAHTAR_DOSYA.get(anahtar)
    if not ad:
        return {}
    p = DOSYA / ad
    if not p.exists():
        return {}
    t = p.read_text(encoding="utf-8")
    out = {}

    tek = _bolum(t, "Tek cümlede")
    if tek:
        out["tanim"] = _alan(_temiz(tek), "product_dossier")

    kul = _bolum(t, "Kullanım")
    if kul:
        out["kullanim"] = _alan(_temiz(kul), "product_dossier")

    ic = _bolum(t, "İçindekiler")
    if ic:
        v = _temiz(ic)
        v = re.sub(r"^(Listesi|/\s*INCI)\s*", "", v).strip()
        for kes in ("(EN)",):
            i = v.find(kes)
            if i > 40:
                v = v[:i].strip()
        if v:
            out["inci"] = _alan(v.rstrip(".") + ".", "product_dossier")

    sat = _bolum(t, "Satışta söylenebilir")
    if sat:
        cumleler = [re.sub(r"^-\s*", "", x).strip()
                    for x in sat.splitlines() if x.strip().startswith("-")]
        if cumleler:
            out["satis_cumleleri"] = _alan(cumleler, "product_dossier")

    zor = _bolum(t, "Zorunlu uyarılar (silinmez)")
    if not zor:
        m = re.search(r"###\s*Zorunlu uyarılar.*?\n(.*?)(?=^##\s|\Z)",
                      t, flags=re.M | re.S)
        zor = m.group(1).strip() if m else ""
    if zor:
        u = [re.sub(r"^-\s*", "", x).strip()
             for x in zor.splitlines() if x.strip().startswith("-")]
        if u:
            out["zorunlu_uyari"] = _alan(u, "product_dossier")

    # mevzuat denetiminde BLOCKED bulgusu
    blok = re.findall(r"\*\*BLOCKED\*\*\s*·\s*([^·\n]+)·\s*\*([^*]+)\*", t)
    if blok:
        out["mevzuat_bulgusu"] = _alan(
            [{"neden": a.strip(), "cumle": b.strip()} for a, b in blok],
            "product_dossier", durum="BLOCKED")

    m = re.search(r"^`[^`]+`\s*·\s*\*\*([\d.]+)\s*TL\*\*", t, flags=re.M)
    if m:
        out["wix_fiyat"] = _alan(m.group(1) + " TL", "wix_product_record")
    return out


# --- 4 · PACKSHOT ETIKETINDEN OKUNAN ------------------------------------
ETIKET_OKUMA = {
    "hydravie": ("50 ml", "ham--DSC04301 etiketi + Wix metni"),
    "kinesis+": ("150 ml", "ham--DSC04520 etiketi"),
    "femisia": ("50 ml", "ham--DSC04316 etiketi"),
    "vireon": ("50 ml", "ham--DSC04316 etiketi"),
}


# --- birlestirme --------------------------------------------------------

def _birlestir(katmanlar: list[dict]) -> dict:
    """Yuksek otorite kazanir; esit otoritede farkli deger CONFLICT."""
    out: dict[str, dict] = {}
    for kat in katmanlar:
        for alan, kayit in kat.items():
            mevcut = out.get(alan)
            if mevcut is None:
                out[alan] = dict(kayit)
                continue
            if kayit["source_authority"] < mevcut["source_authority"]:
                kayit = dict(kayit)
                kayit["note"] = ((kayit.get("note") or "") +
                                 " (daha dusuk otoriteli '%s' degeri ezildi)"
                                 % mevcut["source"]).strip()
                out[alan] = kayit
            elif kayit["source_authority"] == mevcut["source_authority"]:
                if str(kayit["value"]) != str(mevcut["value"]):
                    mevcut["status"] = CELISKI
                    mevcut["note"] = ("ayni otoritede iki farkli deger: "
                                      "%s vs %s" % (mevcut["source"],
                                                    kayit["source"]))
            else:
                mevcut.setdefault("alternatives", []).append(
                    {"value": kayit["value"], "source": kayit["source"],
                     "source_authority": kayit["source_authority"]})
    return out


def yukle(anahtar: str) -> dict:
    kat = [_dosyadan(anahtar), _kutudan(anahtar)]

    net = ETIKET_OKUMA.get(anahtar)
    if net:
        kat.append({"net_miktar": _alan(net[0], "packshot_label_read",
                                        not_=net[1])})

    if MADDE.exists():
        mh = json.loads(MADDE.read_text(encoding="utf-8")).get("urun_madde", {})
        hit = [k for k in mh if anahtar.replace("+", "") in k.lower()]
        if hit:
            kat.append({"madde_listesi": _alan(mh[hit[0]], "ingredient_map")})

    birlesik = _birlestir(kat)

    for (a, alan), ov in OVERRIDE.items():
        if a != anahtar:
            continue
        birlesik[alan] = _alan(ov["value"], "human_verified_override",
                               durum=ov["status"], not_=ov["note"])
    return {"anahtar": anahtar, "alanlar": birlesik}


def deger(g: dict, alan: str, default=BILINMIYOR):
    """Basilabilir deger dondurur. CONFLICT ve UNKNOWN BASILMAZ."""
    k = g["alanlar"].get(alan)
    if not k:
        return default
    if k["status"] in (CELISKI, "BLOCKED") or k["value"] == BILINMIYOR:
        return default
    return k["value"]


def kisalt(m: str, azami: int) -> str:
    if not isinstance(m, str) or m == BILINMIYOR or len(m) <= azami:
        return m
    k = m[:azami]
    for n in (". ", "; "):
        i = k.rfind(n)
        if i > azami * 0.5:
            return k[:i + 1].strip()
    i = k.rfind(" ")
    return (k[:i] if i > 0 else k).strip() + "…"


def catisma_raporu(anahtarlar: list[str]) -> dict:
    out = {"urun": {}, "conflict": [], "unknown": [], "blocked": []}
    for a in anahtarlar:
        g = yukle(a)
        out["urun"][a] = {}
        for alan, k in g["alanlar"].items():
            out["urun"][a][alan] = {
                "source": k["source"], "authority": k["source_authority"],
                "status": k["status"],
                "alternatives": len(k.get("alternatives", [])),
            }
            if k["status"] == CELISKI:
                out["conflict"].append({"urun": a, "alan": alan,
                                        "note": k.get("note", "")})
            if k["status"] == "BLOCKED":
                out["blocked"].append({"urun": a, "alan": alan,
                                       "deger": k["value"]})
        for zorunlu in ("tanim", "kullanim", "uyari", "inci", "net_miktar"):
            if zorunlu not in g["alanlar"]:
                out["unknown"].append({"urun": a, "alan": zorunlu})
    return out


if __name__ == "__main__":
    A = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    r = catisma_raporu(A)
    print("%-10s %-14s %-26s %3s %s"
          % ("urun", "alan", "kaynak", "ot", "durum"))
    print("-" * 78)
    for a in A:
        for alan, k in sorted(r["urun"][a].items(),
                              key=lambda x: x[1]["authority"]):
            print("%-10s %-14s %-26s %3d %s"
                  % (a, alan, k["source"], k["authority"], k["status"]))
        print()
    print("CONFLICT: %d" % len(r["conflict"]))
    for c in r["conflict"]:
        print("  %s.%s -- %s" % (c["urun"], c["alan"], c["note"][:70]))
    print("BLOCKED : %d" % len(r["blocked"]))
    for b in r["blocked"]:
        print("  %s.%s" % (b["urun"], b["alan"]))
    print("UNKNOWN : %d" % len(r["unknown"]))
    for u in r["unknown"]:
        print("  %s.%s" % (u["urun"], u["alan"]))
