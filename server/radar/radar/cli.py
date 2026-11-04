"""Komut satırı: python -m radar <komut>"""
import argparse
import json
import os
import sys

from . import claims, config, content, ingest, kaynaklar, leads, outbox, regulation, reports, satis, trendyol
from .db import connect, jload
from .pricing import PriceBook
from .util import iso, norm, now


def main(argv=None):
    ap = argparse.ArgumentParser(prog="radar", description="L'CARLİÉ Radar")
    ap.add_argument("--config", default=None)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init", help="Veritabanını oluştur")
    p = sp.add_parser("ingest", help="Jarvis tarama sonucunu al (JSON dosya veya -)")
    p.add_argument("file")
    sp.add_parser("teyit-listesi", help="İkinci tarama gereken linkler (JSON)")
    sp.add_parser("adaylar", help="Onay bekleyen aday markalar")
    sp.add_parser("izlenenler", help="İzlenen markalar (Jarvis ajanı için JSON)")
    p = sp.add_parser("marka", help="Marka detayı ve puan dökümü")
    p.add_argument("id", type=int)
    p = sp.add_parser("onayla-marka"); p.add_argument("id", type=int, nargs="+")
    p = sp.add_parser("reddet-marka"); p.add_argument("id", type=int); p.add_argument("--neden", required=True)
    p.add_argument("--kelime", action="append", default=[], help="Bundan sonra hariç tutulacak kelime")
    p = sp.add_parser("haric-kelime"); p.add_argument("kelime", nargs="+")
    sp.add_parser("ozet", help="Sabah özetini üret ve Özer'e kuyrukla")
    p = sp.add_parser("ozet-onizle", help="Sabah özetini gönderilmiş saymadan göster")
    sp.add_parser("aylik", help="Aylık değişim raporu")
    sp.add_parser("saglik", help="Haftalık sağlık kontrolü")
    sp.add_parser("yedek")
    sp.add_parser("musteri-bul", help="Google Maps ile lead bul + mesaj taslağı")
    sp.add_parser("mevzuat", help="TİTCK sayfalarını kontrol et")
    sp.add_parser("icerik", help="Haftalık içerik taslakları")
    sp.add_parser("bekleyenleri-temizle", help="Süresi dolan teyitleri kapat")
    sp.add_parser("mesajlar", help="Onay bekleyen mesajlar")
    p = sp.add_parser("onayla-mesaj"); p.add_argument("id", type=int, nargs="+")
    p = sp.add_parser("reddet-mesaj"); p.add_argument("id", type=int, nargs="+")
    sp.add_parser("gonder", help="Onaylı mesajları gönder")
    sp.add_parser("panel", help="Jarvis paneli için data/panel.json yaz")
    p = sp.add_parser("trendyol-ekle", help="Chrome'da okunan Trendyol kartlarını (TSV) ekle")
    p.add_argument("dosya")
    sp.add_parser("telegram-kimlik", help="Bota mesaj yazdıktan sonra sohbet kimliğinizi gösterir")
    sp.add_parser("satis", help="Wix + Trendyol sipariş toplamlarını data/satis_ozet.json'a yaz")
    p = sp.add_parser("kaynak-tara", help="Online eczane + Gratis: marka listesi ve JSON-LD fiyatları (modelsiz)")
    p.add_argument("--gunluk", type=int, default=25)
    p = sp.add_parser("iddia-kontrol", help="Metni TİTCK ön taramasından geçir"); p.add_argument("metin")
    a = ap.parse_args(argv)

    cfg = config.load(a.config)
    conn = connect(cfg["db_path"])
    book = PriceBook(cfg["price_list"])
    out = lambda o: print(o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, indent=1))

    if a.cmd == "init":
        out(f"Hazır: {cfg['db_path']}")
    elif a.cmd == "ingest":
        payload = json.load(sys.stdin if a.file == "-" else open(a.file, encoding="utf-8"))
        out(ingest.ingest(conn, payload, cfg, book))
    elif a.cmd == "teyit-listesi":
        out(ingest.recheck_list(conn))
    elif a.cmd == "adaylar":
        rows = conn.execute("SELECT * FROM brands WHERE status='candidate' ORDER BY score DESC").fetchall()
        out("\n".join(reports.brand_line(conn, b) for b in rows) or "Onay bekleyen aday yok.")
    elif a.cmd == "izlenenler":
        rows = conn.execute("SELECT id,name,status,website,instagram,trendyol_url FROM brands "
                            "WHERE status IN ('active','passive') ORDER BY name").fetchall()
        out([{k: r[k] for k in r.keys()} for r in rows])
    elif a.cmd == "marka":
        b = conn.execute("SELECT * FROM brands WHERE id=?", (a.id,)).fetchone()
        out({k: (jload(b[k]) if k in ("detail", "texts") else b[k]) for k in b.keys()} if b else "Bulunamadı")
    elif a.cmd == "onayla-marka":
        for i in a.id:
            conn.execute("UPDATE brands SET status='active', approved_at=? WHERE id=? AND status IN "
                         "('candidate','unqualified','passive')", (iso(now()), i))
        conn.commit(); out("İzlemeye alındı: " + ", ".join(map(str, a.id)))
    elif a.cmd == "reddet-marka":
        conn.execute("UPDATE brands SET status='rejected', status_reason=? WHERE id=?", (a.neden, a.id))
        for k in a.kelime:
            conn.execute("INSERT OR IGNORE INTO keywords(kw,kind,added_at) VALUES(?,?,?)", (norm(k), "exclude", iso(now())))
        conn.commit(); out("Reddedildi; bir daha önerilmeyecek.")
    elif a.cmd == "haric-kelime":
        for k in a.kelime:
            conn.execute("INSERT OR IGNORE INTO keywords(kw,kind,added_at) VALUES(?,?,?)", (norm(k), "exclude", iso(now())))
        conn.commit(); out("Eklendi.")
    elif a.cmd in ("ozet", "ozet-onizle"):
        text = reports.morning_brief(conn, cfg, mark=(a.cmd == "ozet"))
        if a.cmd == "ozet":
            outbox.to_owner(conn, cfg, text, "Sabah özeti", ref="ozet:" + now().strftime("%Y-%m-%d"))
        out(text)
    elif a.cmd == "aylik":
        path, _ = reports.monthly(conn, cfg); out(f"Rapor: {path}")
    elif a.cmd == "saglik":
        text = reports.health(conn, cfg)
        outbox.to_owner(conn, cfg, "🩺 Radar sağlık kontrolü\n" + text, "Radar sağlık", ref="saglik")
        out(text)
    elif a.cmd == "yedek":
        out(reports.backup(conn, cfg))
    elif a.cmd == "musteri-bul":
        out(leads.find(conn, cfg, book))
    elif a.cmd == "mevzuat":
        out(regulation.check(conn, cfg))
    elif a.cmd == "icerik":
        out(content.weekly(conn, cfg, book))
    elif a.cmd == "bekleyenleri-temizle":
        out(f"Kapatılan: {ingest.expire_pending(conn, cfg)}")
    elif a.cmd == "mesajlar":
        rows = outbox.pending(conn)
        out("\n\n".join(f"#{m['id']} → {m['recipient']} ({m['channel']})\n{m['body']}" for m in rows) or "Onay bekleyen mesaj yok.")
    elif a.cmd in ("onayla-mesaj", "reddet-mesaj"):
        ok = [i for i in a.id if outbox.decide(conn, i, a.cmd == "onayla-mesaj")]
        out(f"İşlendi: {ok}")
    elif a.cmd == "gonder":
        sent, errs = outbox.send_approved(conn, cfg)
        out({"gonderilen": sent, "hatalar": errs})
    elif a.cmd == "kaynak-tara":
        izlenen = [r["name"] for r in conn.execute("SELECT name FROM brands WHERE status IN ('active','passive')")]
        getir = kaynaklar.NazikGetir()
        sonuc = {}
        for ad, fn in (("eczane", kaynaklar.eczane_tara), ("gratis", kaynaklar.gratis_tara)):
            yol = os.path.join(os.path.dirname(cfg["db_path"]), f"{ad}_markalari.json")
            payload = fn(yol, getir, izlenen, a.gunluk)
            rep = ingest.ingest(conn, payload, cfg, book)
            sonuc[ad] = {"ilk_tur": payload.get("ilk_tur"), "yeni_giren": payload.get("yeni_giren"),
                         "taranan_marka": len(payload["brands"]), "kabul": rep["kabul"], "red": rep["red"][:3],
                         "aday": rep["yeni_marka"],
                         "kaynak_hata": [d for d in payload["source_status"] if not d["ok"]][:5]}
        out(sonuc)
    elif a.cmd == "trendyol-ekle":
        with open(a.dosya, encoding="utf-8") as f:
            payload = trendyol.satirlardan_payload(f.read().splitlines())
        rep = ingest.ingest(conn, payload, cfg, book)
        out({"marka": len(payload["brands"]), "kabul": rep["kabul"], "red": rep["red"][:5],
             "fiyatsiz_kart": len(payload["atlanan"]), "aday": rep["yeni_marka"], "elenen": rep["atlanan"]})
    elif a.cmd == "telegram-kimlik":
        import urllib.request
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            out("Önce .env'e TELEGRAM_BOT_TOKEN yazın.")
            return 1
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        kimlik = {}
        for u in d.get("result", []):
            c = (u.get("message") or {}).get("chat") or {}
            if c.get("id"):
                kimlik[c["id"]] = c.get("first_name") or c.get("title") or ""
        out({"sohbetler": kimlik} if kimlik else "Bota henüz mesaj gelmemiş: Telegram'da botunuza 'merhaba' yazıp tekrar deneyin.")
    elif a.cmd == "satis":
        out(satis.yaz(cfg))
    elif a.cmd == "panel":
        out(reports.panel(conn, cfg))
    elif a.cmd == "iddia-kontrol":
        out(claims.check(a.metin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
