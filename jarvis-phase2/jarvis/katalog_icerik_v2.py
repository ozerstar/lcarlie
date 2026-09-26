"""Gercek urun icerigi -- ONAYLI KUTU METNI kaynakli. Uydurma YOK.

Kaynak: varliklar/kutu-gercegi/*.json  (kaynak_tur = onayli_kutu_metni)

Kural: bir alan kaynakta yoksa UNKNOWN doner ve sayfa o alani BASMAZ.
Ozellikle net miktar kutu metninde HIC gecmiyor; etiketten okunan
degerler kaynagi ile birlikte kaydedilir, celisen urunde CELISKI
isaretlenir ve sayfaya basilmaz.
"""
from __future__ import annotations

import json
import pathlib
import re

KUTU = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/kutu-gercegi")

BILINMIYOR = "UNKNOWN"

# Net miktar kutu metninde YOK. Asagidaki degerler PACKSHOT ETIKETINDEN
# okundu; her biri hangi karede okundugu ile birlikte kayitli.
NET_MIKTAR = {
    "hydravie": {"deger": "50 ml", "kaynak": "packshot etiketi (ham--DSC04301)",
                 "durum": "OKUNDU"},
    "kinesis+": {"deger": "150 ml", "kaynak": "packshot etiketi (ham--DSC04520)",
                 "durum": "OKUNDU"},
    "femisia": {"deger": "50 ml", "kaynak": "packshot etiketi (ham--DSC04316)",
                "durum": "OKUNDU"},
    "vireon": {"deger": "50 ml", "kaynak": "packshot etiketi (ham--DSC04316)",
               "durum": "OKUNDU"},
    # Kutuda 150 ml, siseninkinde 100 ml okunuyor -- ayri SKU olabilir.
    "babysol": {"deger": BILINMIYOR,
                "kaynak": "kutu 150 ml / sise 100 ml -- CELISKI",
                "durum": "CELISKI"},
}

KATEGORI = {
    "hydravie": "YÜZ VE EL BAKIMI",
    "kinesis+": "SPOR VE MASAJ",
    "femisia": "HASSAS BÖLGE · KADIN",
    "vireon": "HASSAS BÖLGE · ERKEK",
    "babysol": "BEBEK · GÜNEŞ KORUMA",
}

# Kutu metninin bilesen tablosundan CIKARILMIS one cikan icerikler.
# TR adi ve INCI adi kaynaktan; oran kaynaktan. Uydurma yok.
ONE_CIKAN = {
    "femisia": [
        ("Epimedium", "Epimedium Grandiflorum Leaf Extract", None),
        ("Maca Kökü", "Lepidium Meyenii Root Extract", None),
        ("L-Arginin", "L-Arginine", None),
        ("Hindistan Cevizi Yağı", "Cocos Nucifera Oil", None),
        ("Aloe Vera Yaprak Suyu", "Aloe Barbadensis Leaf Juice", None),
    ],
    "vireon": [
        ("Epimedium Ekstresi", "Epimedium Grandiflorum Leaf Extract", "5.0"),
        ("L-Arginin", "L-Arginine", "5.0"),
        ("Nioli Yağı", "Melaleuca Quinquenervia Leaf Oil", "3.5"),
        ("Karabiber Yağı", "Piper Nigrum Fruit Oil", "3.0"),
        ("Havuç Tohumu Yağı", "Daucus Carota Sativa Seed Oil", "2.0"),
    ],
    "babysol": [
        ("Çinko Oksit (non-nano)", "Zinc Oxide", "30.0"),
        ("Tamanu Yağı", "Calophyllum Inophyllum Seed Oil", "10.0"),
        ("Aloe Vera Jeli", "Aloe Barbadensis Gel", "7.0"),
        ("Shea Yağı", "Butyrospermum Parkii Butter", "6.0"),
        ("Jojoba Yağı", "Simmondsia Chinensis Seed Oil", "4.0"),
    ],
    "hydravie": [
        ("Sodyum Hyalüronat", "Sodium Hyaluronate", None),
        ("Niasinamid", "Niacinamide", None),
        ("Skualan", "Squalane", None),
        ("Provitamin B5", "Panthenol", None),
        ("Shea Yağı", "Butyrospermum Parkii Butter", None),
    ],
    "kinesis+": [],     # onayli kutu metninde bilesen tablosu YOK
}


def _temizle(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\(EN\).*$", "", s, flags=re.S)
    s = re.sub(r"\(TR\)", "", s)
    s = re.sub(r"\(Uyar[ıi]lar\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _inci_kes(s: str) -> str:
    """INCI listesini bilesen tablosundan ayir."""
    s = _temizle(s)
    for ayrac in ("Bileşen", "Bilesen", "Oran (%)"):
        i = s.find(ayrac)
        if i > 0:
            s = s[:i]
    return s.strip().rstrip(".") + "." if s else ""


def yukle(anahtar: str) -> dict:
    p = KUTU / ("%s.json" % anahtar)
    if not p.exists():
        raise FileNotFoundError(str(p))
    d = json.loads(p.read_text(encoding="utf-8"))
    b = d.get("bolumler", {})
    eksik = list(d.get("eksik_bolumler", []))

    tanim = _temizle(b.get("tanim", ""))
    uyari = _temizle(b.get("uyarilar", ""))
    kullanim = _temizle(b.get("kullanim", ""))
    inci = _inci_kes(b.get("inci", ""))

    # uyari alanina sizmis bilesen tablosunu kes
    for ayrac in ("Nioli", "Bileşen", "Oran (%)"):
        i = uyari.find(ayrac)
        if i > 60:
            uyari = uyari[:i].strip()

    net = NET_MIKTAR.get(anahtar, {"deger": BILINMIYOR, "kaynak": "-",
                                   "durum": "YOK"})
    return {
        "anahtar": anahtar,
        "kaynak_tur": d.get("kaynak_tur", BILINMIYOR),
        "kaynak_dosya": d.get("kaynak", BILINMIYOR),
        "kategori": KATEGORI.get(anahtar, BILINMIYOR),
        "net_miktar": net["deger"],
        "net_miktar_kaynak": net["kaynak"],
        "net_miktar_durum": net["durum"],
        "tanim": tanim or BILINMIYOR,
        "kullanim": kullanim or BILINMIYOR,
        "uyari": uyari or BILINMIYOR,
        "inci": inci or BILINMIYOR,
        "one_cikan": ONE_CIKAN.get(anahtar, []),
        "eksik_bolumler": eksik,
        "raf_omru": _temizle(b.get("raf_omru", "")) or BILINMIYOR,
    }


def kisalt(metin: str, azami: int) -> str:
    """Cumle sinirinda kes -- kelime ortasinda kesme."""
    if metin == BILINMIYOR or len(metin) <= azami:
        return metin
    kes = metin[:azami]
    for nokta in (". ", "; "):
        i = kes.rfind(nokta)
        if i > azami * 0.5:
            return kes[:i + 1].strip()
    i = kes.rfind(" ")
    return (kes[:i] if i > 0 else kes).strip() + "…"


def icerik_raporu(anahtarlar: list[str]) -> dict:
    """Hangi urunde hangi alan gercekten var -- REAL CONTENT PROOF girdisi."""
    ALANLAR = ("tanim", "kullanim", "uyari", "inci", "net_miktar")
    rapor = {}
    for a in anahtarlar:
        d = yukle(a)
        rapor[a] = {
            "var": [k for k in ALANLAR if d[k] != BILINMIYOR],
            "yok": [k for k in ALANLAR if d[k] == BILINMIYOR],
            "one_cikan_sayisi": len(d["one_cikan"]),
            "inci_karakter": 0 if d["inci"] == BILINMIYOR else len(d["inci"]),
            "net_miktar_durum": d["net_miktar_durum"],
        }
    return rapor


if __name__ == "__main__":
    ANAHTAR = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    r = icerik_raporu(ANAHTAR)
    print("%-10s %-34s %-22s %8s %s"
          % ("urun", "VAR", "YOK", "inci", "one_cikan"))
    print("-" * 92)
    for a in ANAHTAR:
        v = r[a]
        print("%-10s %-34s %-22s %8d %d"
              % (a, ",".join(v["var"]), ",".join(v["yok"]) or "-",
                 v["inci_karakter"], v["one_cikan_sayisi"]))
    print()
    for a in ANAHTAR:
        d = yukle(a)
        print("=" * 72)
        print("%s | %s | net: %s (%s)"
              % (a.upper(), d["kategori"], d["net_miktar"],
                 d["net_miktar_durum"]))
        print("  tanim   :", kisalt(d["tanim"], 150))
        print("  kullanim:", kisalt(d["kullanim"], 110))
        print("  uyari   :", kisalt(d["uyari"], 110))
        print("  inci    :", kisalt(d["inci"], 110))
