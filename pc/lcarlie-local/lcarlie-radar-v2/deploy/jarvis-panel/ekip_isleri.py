# -*- coding: utf-8 -*-
"""ÜRETİLENLER sayfası için ekip işleri bölümleri (iş üretici + programlar).

Sahip 26.10.2026: "panelde göreyim". İş üretici çıktıları yalnız diskteydi
(state/is-uretici, state/programlar). Bu modül onları ÜRETİLENLER'in genel
kart biçimine (baslik/aciklama/mb/uretim) çevirir; önyüz değişmez.
Yalnız okur. Kişi verili B2B listesi (state/b2b) burada GÖSTERİLMEZ.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

DURUM = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
IU = DURUM / "is-uretici"
PR = DURUM / "programlar"


def _agac() -> dict:
    try:
        return json.loads((IU / "agac.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _satir(baslik: str, aciklama: str, yol: str | None = None, zaman: str = "") -> dict:
    uretim = zaman or ""
    if yol and not uretim:
        try:
            uretim = datetime.datetime.fromtimestamp(Path(yol).stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        except OSError:
            pass
    return {"baslik": str(baslik or ""), "aciklama": str(aciklama or "")[:900], "indir": "", "onizleme": "",
            "mb": None, "uretim": str(uretim)}


def _tr(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).astimezone(
            datetime.timezone(datetime.timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return str(iso or "")[:16]


def teslimler() -> dict:
    a = _agac()
    kay = []
    for kod, d in (a.get("departmanlar") or {}).items():
        for g in d.get("gorevler", []):
            t = g.get("teslim") or {}
            if t.get("kalite") == "GECTI":
                kay.append((t.get("tarih", ""), _satir(f"{d.get('ad', kod)} · {g.get('baslik')}",
                                                       f"{t.get('ozet', '')} — hazırlayan: {g.get('sorumlu')}", t.get("yol"), _tr(t.get("tarih")))))
    kay.sort(key=lambda x: x[0], reverse=True)
    return {"durum": "VAR" if kay else "YOK", "kayitlar": [k for _, k in kay[:60]],
            "bos_notu": "Henüz kalite kapısından geçen teslim yok — lcarlie-is-uretici@yurut gün içinde 6 kez çalışır."}


def onay_bekleyen() -> dict:
    a = _agac()
    kay = [_satir(f"{d.get('ad', kod)} · {g.get('baslik')}",
                  f"Neden: {g.get('neden') or '-'} · Teslim: {g.get('cikti')} · Kabul: {g.get('kabul_olcutu')}",
                  None, _tr(g.get("olusturma")))
           for kod, d in (a.get("departmanlar") or {}).items() for g in d.get("gorevler", [])
           if g.get("durum") in ("ONAY_BEKLIYOR", "INSAN_INCELEMESI")]
    return {"durum": "VAR" if kay else "YOK", "kayitlar": kay[-80:][::-1],
            "bos_notu": "Onayını bekleyen iş yok."}


def acik_isler() -> dict:
    a = _agac()
    sayac, kay = {}, []
    for kod, d in (a.get("departmanlar") or {}).items():
        gs = d.get("gorevler", [])
        acik = [g for g in gs if g.get("durum") == "ACIK"]
        if not gs:
            continue
        for g in gs:
            sayac[g.get("durum", "?")] = sayac.get(g.get("durum", "?"), 0) + 1
        retro = (d.get("retro") or {}).get("odak")
        kay.append(_satir(f"{d.get('ad', kod)} — {len(acik)} açık / {len(gs)} görev",
                          ("Sıradaki: " + "; ".join(g.get("baslik", "") for g in acik[:3]) if acik else "Açık iş yok.")
                          + (f" · Haftanın odağı: {retro}" if retro else "")))
    return {"durum": "VAR" if kay else "YOK", "kayitlar": kay,
            "bos_notu": "İş üretici henüz görev üretmedi.", "ozet": sayac}


def _jsonl(yol: Path, n: int) -> list[dict]:
    if not yol.exists():
        return []
    satir = yol.read_text(encoding="utf-8").splitlines()[-n:]
    out = []
    for s in satir:
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out[::-1]


def rakip() -> dict:
    kay = [_satir(f"[{k.get('bolge')}] {k.get('marka')}",
                  f"{k.get('ne_yapiyor')} · Öne çıkışı: {k.get('nasil_one_cikiyor')} · Kaynak: {'; '.join(k.get('kaynaklar') or [])[:300]}",
                  None, k.get("tarih", "")) for k in _jsonl(PR / "rakip" / "kartlar.jsonl", 40)]
    kay += [_satir(f"Bizde eksik [{e.get('bolge')}]: {e.get('baslik')}", f"{e.get('neden')} (önem {e.get('onem')})"
                   + ("" if e.get("dogrulandi") else " · DOĞRULANMADI"), None, e.get("tarih", ""))
            for e in _jsonl(PR / "rakip" / "eksikler.jsonl", 20)]
    return {"durum": "VAR" if kay else "YOK", "kayitlar": kay,
            "bos_notu": "Rakip istihbaratı henüz çalışmadı — lcarlie-is-uretici@rakip günde 2 kez."}


def kreatif() -> dict:
    kay = []
    for k in _jsonl(PR / "kreatif" / "tum-kartlar.jsonl", 60):
        h = k.get("hakem") or {}
        if h.get("karar") != "GECTI":
            continue
        kay.append(_satir(f"{k.get('urun')} · {k.get('baslik')}",
                          f"{k.get('kanca')} — {k.get('bilgi', '')[:400]} · hakem {h.get('bilgi_degeri')}/5 · {k.get('format')}",
                          k.get("yol"), k.get("tarih", "")))
    return {"durum": "VAR" if kay else "YOK", "kayitlar": kay,
            "bos_notu": "Hakemden geçen bilgi kartı yok — lcarlie-is-uretici@kreatif günde 2 kez."}


def raporlar() -> dict:
    kay = []
    for alt in ("is-uretici/raporlar", "programlar/rakip", "programlar/b2b", "programlar/retro"):
        kok = DURUM / alt
        if kok.exists():
            for y in kok.rglob("*.md"):
                kay.append((y.stat().st_mtime, y))
    kay.sort(reverse=True)
    out = []
    for _, y in kay[:40]:
        ilk = ""
        try:
            satirlar = [s for s in y.read_text(encoding="utf-8").splitlines() if s.strip()]
            ilk = " ".join(satirlar[1:4])
            baslik = satirlar[0].lstrip("# ") if satirlar else y.name
        except OSError:
            baslik = y.name
        out.append(_satir(baslik, ilk, str(y)))
    return {"durum": "VAR" if out else "YOK", "kayitlar": out, "bos_notu": "Rapor yok."}


RADAR_PANEL = Path(os.environ.get("RADAR_PANEL", "/opt/lcarlie/radar/data/panel.json"))


def radar() -> dict:
    """L'CARLİÉ Radar (29.10.2026): sabah özeti, aday markalar, teyitli değişiklikler, mevzuat.

    Radar'ın kendi yazdığı data/panel.json okunur; kişi verisi o dosyaya yazılmaz.
    """
    try:
        d = json.loads(RADAR_PANEL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"durum": "YOK", "kayitlar": [], "bos_notu": "Radar henüz çalışmadı (lcarlie-radar@ozet her sabah 07:00)."}
    kay = []
    oz = d.get("sabah_ozeti") or {}
    if oz.get("body"):
        kay.append(_satir("Sabah özeti", oz["body"], None, _tr(oz.get("created_at"))))
    for a in d.get("adaylar") or []:
        kay.append(_satir(f"Aday marka #{a.get('id')} · {a.get('ad')} (puan {a.get('puan')})",
                          f"{a.get('satir', '')} · Onay: python3 -m radar onayla-marka {a.get('id')}"))
    for u in d.get("uyarilar") or []:
        kay.append(_satir("Teyitli değişiklik", f"{u.get('metin')} · {' | '.join(u.get('kaynak') or [])}", None,
                          _tr(u.get("zaman"))))
    for m in d.get("mevzuat") or []:
        kay.append(_satir("TİTCK duyurusu", " · ".join(m.get("satirlar") or []) + f" · {m.get('url')}", None,
                          _tr(m.get("zaman"))))
    kotu = [k for k in d.get("kaynak_sagligi") or [] if (k.get("basarili") or 0) < (k.get("toplam") or 0)]
    if kotu:
        kay.append(_satir("Taranamayan kaynaklar (7 gün)",
                          ", ".join(f"{k['kaynak']} {k['basarili']}/{k['toplam']}" for k in kotu[:15])))
    return {"durum": "VAR" if kay else "YOK", "kayitlar": kay,
            "bos_notu": "Radar çalıştı, yeni bulgu yok.",
            "ozet": {"izlenen_marka": d.get("izlenen_marka"), "onay_bekleyen_mesaj": d.get("onay_bekleyen_mesaj")}}


def bolumler() -> list[dict]:
    return [
        {"anahtar": "ekip_teslim", "baslik": "Ekip teslimleri (tebrik edilecekler)",
         "aciklama": "Kalite kapısından geçen işler: en az 3 madde/tablo, kanıta dayalı, kabul ölçütü karşılandı.", **teslimler()},
        {"anahtar": "ekip_onay", "baslik": "Onayını bekleyen işler",
         "aciklama": "Dışarıya temas, yayın, harcama gerektiren ya da iki denemede kaliteyi tutturamayan işler. Hiçbiri kendiliğinden uygulanmaz.", **onay_bekleyen()},
        {"anahtar": "ekip_acik", "baslik": "Departmanlar ne üzerinde çalışıyor",
         "aciklama": "Her ekibin açık işleri ve retrodan gelen haftalık odağı.", **acik_isler()},
        {"anahtar": "ekip_radar", "baslik": "Radar: sabah özeti ve rakip radarı",
         "aciklama": "Her gün 05:00 tarama, 06:00 teyit, 07:00 özet. Sayfada birebir görülmeyen fiyat/ürün tutulmaz; yeni marka siz onaylamadan izlenmez.", **radar()},
        {"anahtar": "ekip_rakip", "baslik": "Rakip istihbaratı",
         "aciklama": "TR / AB / ABD / Asya / Körfez sırayla taranır. Kaynaksız kart tutulmaz.", **rakip()},
        {"anahtar": "ekip_kreatif", "baslik": "Kreatif bilgi kartları",
         "aciklama": "PubMed ve kaynaklı aramaya dayanan, hakemden geçmiş şaşırtıcı-ama-doğru içerikler ve görsel brifleri.", **kreatif()},
        {"anahtar": "ekip_rapor", "baslik": "Ekip raporları",
         "aciklama": "Günlük planlar, haftalık raporlar, rakip/B2B raporları ve retrolar.", **raporlar()},
    ]
