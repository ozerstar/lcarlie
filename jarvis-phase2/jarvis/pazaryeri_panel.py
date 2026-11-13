"""PAZARYERİ SATIŞLARI — panelin E-TİCARET sayfasındaki sipariş görünümü.

Sahip 13.11.2026: *"e-ticaret panellerindeki satışlar neden Jarvis'e
düşmüyor, bununla ilgili bir sayfa neden yok… her pazaryerinin satışları
entegrasyonlarla burada görünsün."*

Siparişler zaten düşüyordu: Sipariş Nöbetçisi her kanalı 2 dakikada bir okuyup
`core.pazaryeri_siparis`e yazıyor. Eksik olan onu gösteren sayfaydı. Bu modül
yalnız OKUR.

🔴 KANAL DURUMU SİPARİŞTEN AYRI DÖNER. "Hepsiburada'da sipariş yok" ile
"Hepsiburada'yı okuyamıyoruz" aynı satırda birleşirse kaçan sipariş sessizce
kaybolur; `kanallar` her kanalın en son ne zaman okunabildiğini taşır.
"""
from __future__ import annotations

import json
from typing import Any

from jarvis.db_transport import run as db_run

KANAL_ADI = {"wix": "Web sitesi", "trendyol": "Trendyol", "idefix": "İdefix",
             "n11": "n11", "hepsiburada": "Hepsiburada",
             "ciceksepeti": "Çiçeksepeti", "pazarama": "Pazarama"}

# Aynı sipariş birden çok paketle ya da iki yoldan (API + e-posta) gelebilir;
# sipariş numarası başına en son güncellenen satır alınır.
_SIPARIS_SQL = (
    "SELECT row_to_json(x) FROM ("
    " SELECT * FROM ("
    "  SELECT DISTINCT ON (kanal, siparis_no) kanal, siparis_no, durum,"
    "   siparis_zamani, tutar, musteri_ad, sehir, kalem_sayisi, kalemler, kaynak"
    "  FROM core.pazaryeri_siparis"
    # Trendyol aynı siparişi bir de adı yıldızlanmış (*** ***) verir; okunur
    # olan satır öne alınır.
    "  ORDER BY kanal, siparis_no, (coalesce(musteri_ad,'') LIKE '*%%'),"
    "   son_guncelleme DESC) t"
    " ORDER BY siparis_zamani DESC NULLS LAST LIMIT %d) x")

_OZET_SQL = (
    "SELECT row_to_json(x) FROM ("
    " SELECT kanal, count(*)::int AS adet, coalesce(sum(tutar),0)::float AS ciro,"
    "  max(siparis_zamani) AS son_siparis FROM ("
    "  SELECT DISTINCT ON (kanal, siparis_no) kanal, siparis_no, tutar,"
    "   siparis_zamani, durum FROM core.pazaryeri_siparis"
    "  ORDER BY kanal, siparis_no, son_guncelleme DESC) t"
    " WHERE siparis_zamani >= now() - interval '30 days'"
    "  AND lower(durum) !~ '(cancel|iptal|return|iade|refund|not_paid)'"
    " GROUP BY kanal) x")

_NABIZ_SQL = (
    "SELECT row_to_json(x) FROM ("
    " SELECT kanal, son_basarili, son_deneme, ardisik_hata, son_hata, etkin"
    " FROM core.kanal_nabiz ORDER BY kanal) x")


def _oku(sql: str) -> list[dict]:
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=25, check=False)
    if r.returncode:
        raise RuntimeError((r.stderr or "sorgu çalışmadı").strip()[:200])
    cikti = []
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                cikti.append(json.loads(satir))
            except json.JSONDecodeError:
                continue
    return cikti


def _kisa_ad(baslik: str) -> str:
    """Pazaryeri başlığından ürün adını ayırır.

    "LuciDerm Temizleme Köpüğü 150 ml - Lavanta-melisa…" → "LuciDerm Temizleme
    Köpüğü". Ayraçta, parantezde ya da ilk rakamda (hacim, SPF değeri) durur;
    en çok dört kelime.
    """
    kelimeler = []
    for k in str(baslik or "").split():
        if k in ("-", "–", "—", "|", "·") or k[0] in "(/" or k[0].isdigit():
            break
        kelimeler.append(k.rstrip(",;:"))
        if len(kelimeler) == 4 or k[-1] in ",;:":
            break
    return " ".join(kelimeler) or "-"


def _urunler(kalemler: Any) -> list[dict]:
    """Kalemleri panelin gösterdiği kısa ad + adet listesine indirir."""
    cikti = []
    for k in kalemler if isinstance(kalemler, list) else []:
        if isinstance(k, dict):
            cikti.append({"ad": _kisa_ad(k.get("ad")), "adet": k.get("adet") or 1})
    return cikti


def _kanal_durumu(n: dict) -> dict:
    """Bir kanalın bağlantısı: BAGLI / KIMLIK_YOK / OKUNAMIYOR."""
    if not n.get("etkin"):
        durum, not_ = "KIMLIK_YOK", "API anahtarı girilmemiş; siparişler buraya düşmez."
    elif n.get("ardisik_hata"):
        durum, not_ = "OKUNAMIYOR", str(n.get("son_hata") or "")[:160]
    else:
        durum, not_ = "BAGLI", ""
    return {"kanal": n.get("kanal"), "ad": KANAL_ADI.get(n.get("kanal"), n.get("kanal")),
            "durum": durum, "not": not_, "son_okuma": n.get("son_basarili"),
            "adet_30g": 0, "ciro_30g": 0.0, "son_siparis": None}


def gorunum(limit: int = 100) -> dict:
    """E-TİCARET › PAZARYERİ SATIŞLARI bölümünün verisi."""
    kanallar = {n["kanal"]: _kanal_durumu(n) for n in _oku(_NABIZ_SQL)}
    for o in _oku(_OZET_SQL):
        k = kanallar.setdefault(o["kanal"], _kanal_durumu(
            {"kanal": o["kanal"], "etkin": True}))
        k["adet_30g"], k["ciro_30g"], k["son_siparis"] = (
            o["adet"], o["ciro"], o["son_siparis"])
    siparisler = []
    for s in _oku(_SIPARIS_SQL % max(1, min(int(limit), 300))):
        siparisler.append({
            "kanal": s["kanal"], "kanal_adi": KANAL_ADI.get(s["kanal"], s["kanal"]),
            "siparis_no": s["siparis_no"], "durum": s["durum"],
            "zaman": s["siparis_zamani"], "tutar": s["tutar"],
            "musteri": s["musteri_ad"], "sehir": s["sehir"],
            "urun_listesi": _urunler(s["kalemler"]), "kaynak": s["kaynak"]})
    return {"kanallar": sorted(kanallar.values(),
                               key=lambda k: (k["durum"] != "BAGLI", -k["adet_30g"])),
            "siparisler": siparisler}
