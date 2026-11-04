"""is-uretici programlarının (rakip/kreatif/b2b/retro) sunucu bağlantıları.

Her fonksiyon tek bir dış kaynağı okur; yazma yapan tek bağlantı plan_ekle'dir
(core.arastirma_plani, ai_writer rolüyle, psql değişkenleriyle -- model metni
SQL'e asla birleştirilmez).
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def grounded_arama(providers):
    model = os.environ.get("IS_URETICI_ARAMA_MODELI", "gemini-3.5-flash-lite")
    gemini = next((p for p in providers.PROVIDERS if p.name == "gemini"), None)

    def ara(soru: str) -> tuple[str, list[str]]:
        key = providers.load_env().get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY yok")
        govde = {"contents": [{"parts": [{"text": soru}]}], "tools": [{"google_search": {}}]}
        istek = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            data=json.dumps(govde).encode("utf-8"), headers={"Content-Type": "application/json"})
        basla = time.perf_counter()
        with urllib.request.urlopen(istek, timeout=90) as c:
            d = json.loads(c.read().decode("utf-8"))
        aday = (d.get("candidates") or [{}])[0]
        metin = "".join(p.get("text") or "" for p in ((aday.get("content") or {}).get("parts") or []))
        urller = []
        for ch in ((aday.get("groundingMetadata") or {}).get("groundingChunks") or []):
            u = (ch.get("web") or {}).get("uri") or ""
            baslik = (ch.get("web") or {}).get("title") or ""
            if u:
                urller.append(f"{baslik} {u}".strip())
        if gemini:
            um = d.get("usageMetadata") or {}
            providers._record_usage(gemini, model, basla, is_anahtari="is-uretici-arama", kademe="hizli",
                                    prompt_tokens=um.get("promptTokenCount"), completion_tokens=um.get("candidatesTokenCount"))
        return metin, urller
    return ara


def adlib_kancalari(anahtar: str, ulke: str) -> list[dict]:
    url = os.environ.get("KANCA_ADLIB_URL", "http://127.0.0.1:3010")
    govde = json.dumps({"keyword": anahtar, "country": ulke, "status": "ALL", "limit": 20}).encode("utf-8")
    istek = urllib.request.Request(f"{url}/api/scrape", data=govde, headers={"Content-Type": "application/json"})
    out = []
    with urllib.request.urlopen(istek, timeout=240) as cevap:
        for ham in cevap:
            satir = ham.decode("utf-8", "replace").strip()
            if not satir.startswith("data:"):
                continue
            try:
                olay = json.loads(satir[5:].strip())
            except json.JSONDecodeError:
                continue
            if olay.get("type") != "ad":
                continue
            r = olay.get("data") or {}
            govdeler = r.get("body_variants") or []
            if not govdeler:
                continue
            ilk = re.split(r"(?<=[.!?])\s+|\n", str(govdeler[0]).strip())[0].strip()
            if 12 <= len(ilk) <= 220:
                out.append({"metin": ilk, "marka": str(r.get("advertiser_name") or "")[:80],
                            "gun_sayisi": r.get("days_running"), "video_var": bool(r.get("video_urls")),
                            "ad_id": str(r.get("id") or "")})
    return out


def urun_listesi(memory):
    onbellek: list = []

    def urunler() -> list[tuple[str, str]]:
        if not onbellek:
            for r in memory._fetch("urun_bilgi").records:
                ad = str(r.get("urun_adi") or "").strip()
                metin = str(r.get("aciklama_duz") or "")
                # Aksesuar/merch ürünlerinde formül yok; kreatif bilgi hattı formüllü ürünlerle çalışır.
                if ad and len(metin) > 250 and re.search(r"(?i)içindekiler|ingredients|inci|aqua|extract|oil", metin):
                    onbellek.append((ad, metin[:6000]))
        return onbellek
    return urunler


def bilgi_dosyasi(kok: Path):
    def oku(ad: str) -> str:
        ad = re.sub(r"[^a-z0-9\-]", "", ad.lower().replace("ı", "i").replace("ö", "o").replace("ü", "u")
                    .replace("ş", "s").replace("ç", "c").replace("ğ", "g"))
        yol = kok / "knowledge" / f"{ad}.md"
        return yol.read_text(encoding="utf-8")[:6000] if yol.exists() else ""
    return oku


def pubmed_ara(Kanit):
    temel = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    def al(url: str) -> bytes:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lcarlie-jarvis/1.0"}), timeout=30) as c:
            return c.read()

    def ara(sorgu: str) -> list:
        q = urllib.parse.urlencode({"db": "pubmed", "term": sorgu, "retmax": 4, "sort": "relevance", "retmode": "json"})
        ids = json.loads(al(temel + "esearch.fcgi?" + q))["esearchresult"].get("idlist", [])
        if not ids:
            return []
        time.sleep(0.4)  # anahtarsız sınır saniyede 3 istek
        ozet = json.loads(al(temel + "esummary.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})))["result"]
        time.sleep(0.4)
        metin = al(temel + "efetch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "text"})).decode("utf-8", "replace")
        parcalar = re.split(r"\n\n\d+\. ", "\n\n" + metin)
        out = []
        for i, pid in enumerate(ids):
            s = ozet.get(pid) or {}
            abstract = re.sub(r"\s+", " ", parcalar[i + 1] if i + 1 < len(parcalar) else "")[:900]
            out.append(Kanit("", f"pubmed:{pid} https://pubmed.ncbi.nlm.nih.gov/{pid}/ · {s.get('source', '')} {str(s.get('pubdate', ''))[:4]}",
                             f"{s.get('title', '')} — {abstract}"))
        return out
    return ara


# ------------------------------------------------------------------ B2B eczane verisi
SUTUNLAR = ("tts", "bolge", "eczane", "eczaci", "frekans", "telefon", "adres", "il")


def _eczaneler(yol: Path) -> list[dict]:
    if not yol.exists():
        return []
    with yol.open(encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        next(r, None)
        return [dict(zip(SUTUNLAR, satir)) for satir in r if len(satir) >= 8]  # noqa: B905


def b2b_ozet(durum: Path):
    yol = durum / "b2b" / "eczaneler.csv"

    def ozet() -> dict:
        kayit = _eczaneler(yol)
        if not kayit:
            return {}
        il = Counter(k["il"].strip() for k in kayit)
        sicak = defaultdict(int)
        for k in kayit:
            if k["frekans"].strip() not in ("", "0"):
                sicak[k["il"].strip()] += 1
        frek = Counter(k["frekans"].strip() or "0" for k in kayit)
        zincir = Counter(re.sub(r"\s+", " ", k["eczane"].upper()).strip() for k in kayit)
        return {
            "kaynak": "Drive: eczaneler-20240815 (üçüncü kişiden paylaşılmış liste; 2024-08; e-posta yok)",
            "toplam_eczane": len(kayit), "il_sayisi": len(il),
            "telefon_dolu": sum(1 for k in kayit if k["telefon"].strip()),
            "adres_dolu": sum(1 for k in kayit if k["adres"].strip()),
            "eczaci_adi_dolu": sum(1 for k in kayit if k["eczaci"].strip()),
            "frekans_dagilimi": dict(frek),
            "frekans_aciklamasi": "Listeyi hazırlayan firmanın temsilci ziyaret sıklığı olduğu tahmin ediliyor; >0 = o firmanın aktif ziyaret ettiği eczane.",
            "il_ilk25": [{"il": k, "eczane": v, "ziyaretli": sicak.get(k, 0), "ziyaret_orani": round(sicak.get(k, 0) / v, 2)} for k, v in il.most_common(25)],
            "temsilci_bolge_sayisi": len(Counter(k["tts"] for k in kayit)),
            "ayni_adli_eczane_tekrari_ilk5": [c for _, c in zincir.most_common(5)],
        }
    return ozet


def b2b_liste(durum: Path):
    yol = durum / "b2b" / "eczaneler.csv"

    def liste() -> str:
        kayit = _eczaneler(yol)
        il = Counter(k["il"].strip() for k in kayit)
        buyuk = {k for k, _ in il.most_common(12)}
        secim = sorted((k for k in kayit if k["il"].strip() in buyuk and k["telefon"].strip()),
                       key=lambda k: (-(int(k["frekans"]) if k["frekans"].strip().isdigit() else 0), k["il"]))[:1500]
        tarih = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
        hedef = durum / "b2b" / f"oncelik-{tarih}.csv"
        with hedef.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["il", "eczane", "eczaci", "telefon", "adres", "frekans", "not"])
            for k in secim:
                w.writerow([k["il"], k["eczane"], k["eczaci"], k["telefon"], k["adres"], k["frekans"],
                            "İç kullanım. Temas öncesi KVKK aydınlatma + İYS kontrolü; toplu gönderim sahip onayıyla."])
        os.chmod(hedef, 0o600)
        return str(hedef)
    return liste


def plan_ekle(hedef: str, konu: str, gerekce: str) -> bool:
    sql = ("BEGIN; SET SESSION AUTHORIZATION ai_writer; "
           "INSERT INTO core.arastirma_plani(kapsam,hedef,konu,siklik_gun,oncelik,gerekce,planlayan) "
           "VALUES ('DEPARTMAN', :'hedef', :'konu', 7, 4, :'gerekce', 'is_uretici') "
           "ON CONFLICT ON CONSTRAINT arastirma_plani_tekil DO NOTHING; COMMIT;\n")
    r = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
                        "-U", "n8n", "-d", "n8n", "-v", f"hedef={hedef[:60]}", "-v", f"konu={konu[:180]}",
                        "-v", f"gerekce={gerekce[:300]}", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr or "plan yazılamadı")[:300])
    return True
