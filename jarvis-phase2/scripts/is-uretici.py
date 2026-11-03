#!/usr/bin/env python3
"""Departmanlara iş ürettirir: günlük görev, haftalık rapor+fikir, aylık hedef ağacı, yürütme.

Kullanım:
  venv/bin/python scripts/is-uretici.py --mod gunluk   [--sinir 50] [--kuru]
  venv/bin/python scripts/is-uretici.py --mod haftalik [--sinir 50]
  venv/bin/python scripts/is-uretici.py --mod aylik
  venv/bin/python scripts/is-uretici.py --mod yurut    [--sinir 8]

Ayrıntı ve sınırlar: jarvis/is_uretici.py başlığı.
Kill-switch: IS_URETICI_ENABLED=false (env dosyası) -> çıkış 78, hiçbir şey yapmaz.
Çıkış: 0=çalıştı · 1=hata · 78=kapalı
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

DURUM = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state")))


def _ofis_yazici():
    try:
        from jarvis import office_events
        return office_events.emit
    except Exception:  # noqa: BLE001
        return None


def _kilit():
    """Aynı anda iki iş üretici koşusu görev ağacını birbirinin üstüne yazmasın."""
    import fcntl
    yol = DURUM / "is-uretici" / ".kilit"
    yol.parent.mkdir(parents=True, exist_ok=True)
    f = open(yol, "w")  # noqa: SIM115 - kilit süreç boyunca açık kalmalı
    fcntl.flock(f, fcntl.LOCK_EX)   # bekler; systemd TimeoutStartSec üst sınırdır
    return f


def _oneri_ac(anahtar: str, metin: str, sebep: str) -> int | None:
    """Kurulun YAP dediği onay işini ana sayfadaki onay kuyruğuna koyar (REQUEST_HUMAN_REVIEW).
    Değerler psql değişkeni olarak geçer (:'x' tırnaklar); SQL'e metin eklenmez."""
    import subprocess
    sql = ("SELECT core.ai_sistem_onerisi('kurul', 'REQUEST_HUMAN_REVIEW', :'a', "
           "jsonb_build_object('reason', :'m'), :'s');")
    r = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
                        "-v", "ON_ERROR_STOP=1", "-tA", "-v", f"a={anahtar}", "-v", f"m={metin}", "-v", f"s={sebep}"],
                       input=sql, capture_output=True, text=True, timeout=60, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"onay önerisi yazılamadı: {r.stderr.strip()[:200]}")
    deger = r.stdout.strip()
    return int(deger) if deger.isdigit() else None


def _rutin_katalog() -> list:
    """config/rutin-isler.json: departmanların sabit tekrarlayan işleri."""
    yol = Path(os.environ.get("IS_URETICI_RUTIN", str(KOK / "config" / "rutin-isler.json")))
    if not yol.exists():
        return []
    return list(json.loads(yol.read_text(encoding="utf-8")).get("isler") or [])


def _ortam(canli_arastirma: bool):
    from jarvis import improvement, providers, roster
    from jarvis.is_uretici import Departman, Kanit, Ortam, Uye
    from jarvis.memory import CompanyMemory
    from jarvis.transport import memory_host

    memory = CompanyMemory(host=memory_host())
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import program_baglantilari as pb
    uye_haritasi = roster.departman_uyeleri()

    def departmanlar():
        kayitlar = list(memory._fetch("departments").records)
        out = []
        for d in kayitlar:
            kod = str(d.get("kod") or "")
            if not kod:
                continue
            uyeler = [Uye(m.key, m.name, m.job, tuple(m.reads)) for m in uye_haritasi.get(kod, ())]
            # Sorumlu üye başa alınır: görev sahibi belirsizse ona düşer.
            sorumlu = roster.departman_sorumlusu(kod)
            if sorumlu:
                uyeler.sort(key=lambda u: u.key != sorumlu.key)
            out.append(Departman(kod=kod, ad=str(d.get("ad") or kod), misyon=str(d.get("misyon") or ""),
                                 aile=str(d.get("aile") or ""), uyeler=uyeler))
        return out

    def uye_gorusleri(dep):
        keys = tuple(u.key for u in dep.uyeler)
        if not keys:
            return []
        out = []
        for g in roster.opinions(memory, only=keys):
            s = str(g.get("statement") or "").strip()
            if s:
                out.append(Kanit("", f"üye:{g.get('key')} ({g.get('status', '')})", s[:700]))
        return out

    onbellek: dict = {}

    def ham_veri(uye):
        """Üyenin okuduğu tablolardan örnek satırlar: analiz rakamları buradan gelir."""
        out = []
        for q in list(uye.okur)[:3]:
            if q not in onbellek:
                try:
                    ev = memory._fetch(q)
                    onbellek[q] = (str(getattr(ev, "source", q)), list(ev.records))
                except Exception as e:  # noqa: BLE001
                    onbellek[q] = (q, None)
                    print(f"UYARI: {q} okunamadı: {str(e)[:120]}", file=sys.stderr)
            kaynak, kayitlar = onbellek[q]
            if not kayitlar:
                continue
            ornek = json.dumps(kayitlar[:40], ensure_ascii=False, default=str)[:3500]
            out.append(Kanit("", f"tablo:{q} ({len(kayitlar)} satır; ilk 40) {kaynak}", ornek))
        return out

    atif = DURUM / "departman_arastirma.jsonl"

    def arastirma_notlari(kod, gun):
        if not atif.exists():
            return []
        esik = (datetime.now(timezone.utc) - timedelta(days=gun)).isoformat()
        satirlar = []
        with atif.open(encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("departman") != kod or r.get("enjeksiyon") or str(r.get("zaman", "")) < esik:
                    continue
                satirlar.append(r)
        satirlar = satirlar[-12:]
        return [Kanit("", f"araştırma:{r.get('yayinci') or 'web'} · {str(r.get('zaman', ''))[:10]} · {r.get('url', '')}",
                      f"{r.get('baslik', '')} — {r.get('ozet', '')}"[:600]) for r in satirlar]

    arastir = None
    if canli_arastirma:
        try:
            from jarvis import knowledge
            from jarvis.adapter_factory import default_factory
            from jarvis.research_controller import ResearchController
            from jarvis.research_sources import WebSearchCrawlAdapter
            factory = default_factory()
            factory.register(WebSearchCrawlAdapter(
                searxng_url=os.environ.get("RESEARCH_SEARXNG_URL", "http://127.0.0.1:8888")))
            controller = ResearchController(factory)

            def arastir(konu):
                run = knowledge.research_topic(controller, konu, set())
                items = [i for i in getattr(run, "new_items", ()) or () if not getattr(i, "injection_detected", False)][:6]
                return [Kanit("", f"canlı-araştırma:{i.publisher or 'web'} · {i.url}",
                              f"{i.title} — {(i.snippet or '')[:500]}") for i in items]
        except Exception as e:  # noqa: BLE001
            print(f"UYARI: canlı araştırma kapalı: {e}", file=sys.stderr)
            arastir = None


    return Ortam(departmanlar=departmanlar, uye_gorusleri=uye_gorusleri,
                 arastirma_notlari=arastirma_notlari,
                 # Varsayılan ÜCRETSİZ: sahibin PC GPU'su -> sunucu CPU modeli (scripts/yerel_model.py).
                 uret=(providers.generate if os.environ.get("IS_URETICI_MODEL", "ucretsiz") == "ucretli"
                       else __import__("yerel_model").yonlendirici(providers)),
                 defter=improvement.Store(), durum_dizini=DURUM, arastir=arastir, ham_veri=ham_veri,
                 grounded=pb.grounded_arama(providers), adlib=pb.adlib_kancalari,
                 urunler=pb.urun_listesi(memory), bilgi_dosyasi=pb.bilgi_dosyasi(KOK),
                 pubmed=pb.pubmed_ara(Kanit), b2b_ozet=pb.b2b_ozet(DURUM), b2b_liste=pb.b2b_liste(DURUM),
                 plan_ekle=pb.plan_ekle, ofis=_ofis_yazici(), rutin=_rutin_katalog,
                 oneri_ac=_oneri_ac, gunluk_arastirma=True,
                 odak_bilgi=tuple(x for x in os.environ.get("IS_URETICI_ODAK", "kasim-2026-plani").split(",") if x))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mod", required=True,
                   choices=("gunluk", "haftalik", "aylik", "yurut", "rakip", "kreatif", "b2b", "retro", "kurul"))
    p.add_argument("--sinir", type=int, default=None)
    p.add_argument("--kuru", action="store_true", help="deftere/ağaca yazmadan dene")
    p.add_argument("--sure", type=int, default=None, help="yurut: bu kadar saniye sonra yeni işe başlama")
    a = p.parse_args()
    if os.environ.get("IS_URETICI_ENABLED", "true").lower() in ("0", "false", "no", "hayir"):
        print("İş üretici kapalı (IS_URETICI_ENABLED=false).")
        return 78
    from jarvis.is_uretici import IsUretici
    kilit = _kilit() if not a.kuru else None  # noqa: F841 - süreç boyunca tutulur
    try:
        iu = IsUretici(_ortam(canli_arastirma=(a.mod == "yurut")), kuru=a.kuru)
        if a.mod == "gunluk":
            sonuc = iu.gunluk(a.sinir or 50)
        elif a.mod == "haftalik":
            sonuc = iu.haftalik(a.sinir or 50)
        elif a.mod == "aylik":
            sonuc = iu.aylik()
        elif a.mod == "kurul":
            from jarvis.kurul import Kurul
            sonuc = Kurul(iu, radar_panel=Path(os.environ.get("RADAR_PANEL", "/opt/lcarlie/radar/data/panel.json"))).calistir()
        elif a.mod in ("rakip", "kreatif", "b2b", "retro"):
            from jarvis.programlar import Programlar
            pr = Programlar(iu)
            sonuc = pr.calistir(a.mod, a.sinir)
        else:
            sonuc = iu.yurut(a.sinir or 12, sure_sn=a.sure)
        sonuc["ozet"] = iu.ozet_yaz(sonuc)
    except Exception as e:  # noqa: BLE001
        print(f"HATA: {type(e).__name__}: {e}"[:800], file=sys.stderr)
        return 1
    print(json.dumps(sonuc, ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
