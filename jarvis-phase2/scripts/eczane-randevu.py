#!/usr/bin/env python3
"""Eczane ziyaret randevusu: herkese açık küçük servis (n8n.lcarlie.shop/randevu).

Sahip 13.11.2026: *"randevu talebi olursa randevuları üst üste bindirmeyecek
şekilde oluşturacağız"*, *"ciddi olanları alalım"*, *"geri dönüşleri sisteme
entegre et"*.

Neden Jarvis panelinin içinde değil: panelin her yolu oturum + yetki kapısından
geçer; eczacının açacağı sayfa için o kapıya istisna açmak yerine ayrı, dar bir
servis. Yalnız 4 yol var, veritabanına yalnız eczane_* tablolarına yazar.

  GET  /randevu?t=ANAHTAR          sayfa (kişiye özel bağlantı)
  GET  /randevu/api/bos?t=ANAHTAR  eczane adı + boş saatler
  POST /randevu/api/al             randevu talebi
  GET  /randevu/cikis?t=ANAHTAR    listeden çıkma

Kurallar:
  · Çakışma kontrolü VERİTABANINDA (EXCLUDE gist). Burada yalnız gösterim.
  · "Ciddi": geçerli kişisel anahtar + yetkili adı + telefon zorunlu, bal
    küpü alanı dolu gelen istek sessizce yutulur, eczane başına tek açık randevu.
  · Anahtar sıra numarası değil, 24 haneli rastgele; bağlantı tahmin edilemez.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

TR = timezone(timedelta(hours=3))
# Sahip 13.11.2026: "bir iş bloke yapıldığında 1 saatlik alanı kapatalım; anlattı,
# gitti, geldi, yolu uzun sürer". Bir randevu takvimde 60 dk kapatır (DB'deki
# bitiş = başlangıç + BLOK_DK, çakışma kapısı bu aralıkla çalışır).
ZIYARET_DK = 30       # eczanede geçen süre (15 dk tanışma + pay)
BLOK_DK = 60          # ziyaret + yol: takvimde kapanan alan
GUN_SAYISI = 10       # kaç iş günü ileriye
ILK_GUN = 1           # en erken yarın
SAATLER = [(10, 0), (11, 0), (12, 0), (14, 0), (15, 0), (16, 0), (17, 0)]
# Yol süresi: kuş uçuşu mesafe / Ankara içi ortalama hız + park/yürüme payı.
# Kuş uçuşu gerçek yoldan kısadır; hız düşük tutularak telafi edilir. Konumu
# bilinmeyen eczanede yol, bloğun içindeki 30 dk sayılır.
YOL_HIZ_KMS = 22.0
YOL_PAY_DK = 10
YAKIN_KM = 3.0        # "yakınınızda ziyaretimiz var" önerisi
ANAHTAR_RE = re.compile(r"^[0-9a-f]{24}$")
SAYFA = (Path(__file__).resolve().parent / "eczane-randevu.html")
_hiz: dict[str, list[float]] = {}
_kilit = threading.Lock()


def psql(sql: str, **degisken: str) -> list[dict]:
    """Değerler psql değişkeniyle (:'ad') geçer -- SQL'e metin olarak gömülmez."""
    arg = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At",
           "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1"]
    for k, v in degisken.items():
        arg += ["-v", "%s=%s" % (k, v)]
    p = subprocess.run(arg, input=sql, capture_output=True, text=True, timeout=20)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:300])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip().startswith("{")]


def hedef(anahtar: str) -> dict | None:
    if not ANAHTAR_RE.match(anahtar or ""):
        return None
    r = psql("SELECT row_to_json(x) FROM (SELECT id, eczane, il, durum, enlem, boylam"
             " FROM core.eczane_hedef WHERE anahtar = :'a') x;", a=anahtar)
    return r[0] if r else None


def etkilesim(hedef_id: int, tur: str, ayrinti: dict | None = None) -> None:
    psql("INSERT INTO core.eczane_etkilesim (hedef_id, tur, ayrinti) VALUES (:'h', :'t', :'d');",
         h=str(hedef_id), t=tur, d=json.dumps(ayrinti or {}, ensure_ascii=False))


def mesafe_km(a: tuple | None, b: tuple | None) -> float | None:
    if not a or not b or None in a or None in b:
        return None
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def yol_dk(a: tuple | None, b: tuple | None) -> float:
    km = mesafe_km(a, b)
    return BLOK_DK - ZIYARET_DK if km is None else YOL_PAY_DK + km / YOL_HIZ_KMS * 60


def bos_saatler(h: dict) -> list[dict]:
    """Bu eczane için boş saatler.

    1) Takvimde 60 dk'lık bloklar çakışamaz (DB kapısının aynısı).
    2) Rota: aynı gün önceki ziyaretin bitişinden buraya, buradan sonraki
       ziyarete yol yetişmeli. Uzak iki eczane art arda saate düşmez.
    3) Aynı gün YAKIN_KM içinde ziyaret varsa komşu saat "yakın" işaretlenir.
    """
    dolu = psql("SELECT row_to_json(x) FROM (SELECT r.baslangic, r.bitis, e.enlem, e.boylam"
                " FROM core.eczane_randevu r JOIN core.eczane_hedef e ON e.id = r.hedef_id"
                " WHERE r.durum <> 'IPTAL' AND r.bitis > now() AND r.hedef_id <> :'h') x;",
                h=str(h["id"]))
    ziyaretler = [(datetime.fromisoformat(d["baslangic"]), datetime.fromisoformat(d["bitis"]),
                   (d.get("enlem"), d.get("boylam"))) for d in dolu]
    ben = (h.get("enlem"), h.get("boylam"))
    gunler, gun, eklenen = [], datetime.now(TR).date() + timedelta(days=ILK_GUN), 0
    while eklenen < GUN_SAYISI:
        if gun.weekday() < 5:
            saatler, yakin = [], []
            o_gun = [z for z in ziyaretler if z[0].astimezone(TR).date() == gun]
            for s, d in SAATLER:
                b = datetime(gun.year, gun.month, gun.day, s, d, tzinfo=TR)
                e = b + timedelta(minutes=BLOK_DK)
                if any(b < y and e > x for x, y, _ in ziyaretler):
                    continue
                uygun, komsu_yakin = True, False
                for x, _y, konum in o_gun:
                    if x < b:      # önceki ziyaret: oradaki işin bitişinden buraya yol
                        bosluk = (b - (x + timedelta(minutes=ZIYARET_DK))).total_seconds() / 60
                        if bosluk < yol_dk(konum, ben):
                            uygun = False
                    else:          # sonraki ziyaret: buradaki işin bitişinden oraya yol
                        bosluk = (x - (b + timedelta(minutes=ZIYARET_DK))).total_seconds() / 60
                        if bosluk < yol_dk(ben, konum):
                            uygun = False
                    km = mesafe_km(konum, ben)
                    if km is not None and km <= YAKIN_KM and abs((x - b).total_seconds()) <= 2 * 3600:
                        komsu_yakin = True
                if uygun:
                    saatler.append(b.isoformat())
                    if komsu_yakin:
                        yakin.append(b.isoformat())
            if saatler:
                gunler.append({"gun": gun.isoformat(), "saatler": saatler, "yakin": yakin})
            eklenen += 1
        gun += timedelta(days=1)
    return gunler


def bildir(h: dict, r: dict) -> None:
    """Sahibe push + e-posta (haberci). Başarısızlık randevuyu bozmaz."""
    try:
        from jarvis import haberci
        zaman = datetime.fromisoformat(r["baslangic"]).astimezone(TR).strftime("%d.%m %H:%M")
        metin = "%s · %s · %s (%s) · %s" % (zaman, h["eczane"], r["yetkili"], r["unvan"] or "-",
                                            r["telefon"])
        haberci.push_gonder("🗓️ Eczane randevu talebi", metin, "eczane-randevu")
        haberci.eposta_gonder("Eczane randevu talebi: %s %s" % (h["eczane"], zaman),
                              metin + "\nİlgi: %s\nNot: %s\n" % (r["ilgi"] or "-", r["notu"] or "-"))
    except Exception as hata:  # noqa: BLE001
        sys.stderr.write("[randevu] bildirim gitmedi: %s\n" % hata)


def hiz_asimi(ip: str, tavan: int = 30, pencere: int = 600) -> bool:
    simdi = time.time()
    with _kilit:
        l = [t for t in _hiz.get(ip, []) if simdi - t < pencere]
        l.append(simdi)
        _hiz[ip] = l
        return len(l) > tavan


class Y(BaseHTTPRequestHandler):
    server_version = "lcarlie-randevu"

    def log_message(self, fmt, *args):  # erişim günlüğünde anahtar yazmasın
        sys.stderr.write("%s %s\n" % (self.command, urlparse(self.path).path))

    def _ip(self) -> str:
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def _json(self, kod: int, veri: dict) -> None:
        ham = json.dumps(veri, ensure_ascii=False).encode()
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(ham)))
        self.end_headers()
        self.wfile.write(ham)

    def _html(self, kod: int, govde: str) -> None:
        ham = govde.encode()
        self.send_response(kod)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(ham)))
        self.end_headers()
        self.wfile.write(ham)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        t = (parse_qs(u.query).get("t") or [""])[0]
        if hiz_asimi(self._ip(), 120):
            return self._json(429, {"hata": "Çok fazla istek."})
        if u.path in ("/randevu", "/randevu/"):
            h = hedef(t)
            if h:
                etkilesim(h["id"], "SAYFA")
            return self._html(200, SAYFA.read_text(encoding="utf-8"))
        if u.path == "/randevu/api/bos":
            h = hedef(t)
            if not h:
                return self._json(404, {"hata": "Bağlantı geçersiz."})
            acik = psql("SELECT row_to_json(x) FROM (SELECT baslangic, durum FROM core.eczane_randevu"
                        " WHERE hedef_id = :'h' AND durum IN ('TALEP','ONAYLANDI')) x;", h=str(h["id"]))
            return self._json(200, {"eczane": h["eczane"], "il": h["il"], "mevcut": acik[0] if acik else None,
                                    "gunler": bos_saatler(h)})
        if u.path == "/randevu/cikis":
            h = hedef(t)
            if h:
                psql("UPDATE core.eczane_hedef SET durum='CIKTI', guncellendi=now() WHERE id = :'h';",
                     h=str(h["id"]))
                etkilesim(h["id"], "CIKIS")
            return self._html(200, CIKIS_SAYFA)
        return self._json(404, {"hata": "Bulunamadı."})

    def do_POST(self):  # noqa: N802
        self.close_connection = True
        n = int(self.headers.get("Content-Length") or 0)
        govde = self.rfile.read(n) if 0 < n <= 8192 else b""
        if urlparse(self.path).path != "/randevu/api/al":
            return self._json(404, {"hata": "Bulunamadı."})
        if hiz_asimi(self._ip(), 20):
            return self._json(429, {"hata": "Çok fazla deneme. Lütfen biraz sonra tekrar deneyin."})
        try:
            v = json.loads(govde.decode())
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"hata": "Geçersiz istek."})
        if v.get("web_sitesi"):          # bal küpü: insan bu alanı görmez
            return self._json(200, {"tamam": True})
        h = hedef(str(v.get("t") or ""))
        if not h:
            return self._json(404, {"hata": "Bağlantı geçersiz."})
        yetkili = str(v.get("yetkili") or "").strip()[:80]
        telefon = str(v.get("telefon") or "").strip()[:20]
        if len(yetkili) < 3 or len(re.sub(r"\D", "", telefon)) < 10:
            return self._json(400, {"hata": "Lütfen yetkili adını ve telefonu eksiksiz yazın."})
        try:
            bas = datetime.fromisoformat(str(v.get("saat")))
        except ValueError:
            return self._json(400, {"hata": "Saat seçin."})
        gecerli = {s for g in bos_saatler(h) for s in g["saatler"]}
        if bas.isoformat() not in gecerli:
            return self._json(409, {"hata": "Bu saat az önce doldu. Lütfen başka bir saat seçin."})
        r = dict(baslangic=bas.isoformat(), bitis=(bas + timedelta(minutes=BLOK_DK)).isoformat(),
                 yetkili=yetkili, unvan=str(v.get("unvan") or "")[:40], telefon=telefon,
                 ilgi=", ".join(str(x)[:30] for x in (v.get("ilgi") or [])[:8]),
                 notu=str(v.get("not") or "").strip()[:500])
        try:
            psql("INSERT INTO core.eczane_randevu (hedef_id, baslangic, bitis, yetkili, unvan, telefon, ilgi, notu)"
                 " VALUES (:'h', :'b', :'e', :'y', nullif(:'u',''), :'tel', nullif(:'i',''), nullif(:'n',''));"
                 " UPDATE core.eczane_hedef SET durum='RANDEVU', guncellendi=now() WHERE id = :'h';",
                 h=str(h["id"]), b=r["baslangic"], e=r["bitis"], y=r["yetkili"], u=r["unvan"],
                 tel=r["telefon"], i=r["ilgi"], n=r["notu"])
        except RuntimeError as hata:
            m = str(hata)
            if "eczane_randevu_tek_acik" in m:
                return self._json(409, {"hata": "Eczaneniz için zaten bir randevu talebi var. "
                                                 "Değişiklik için 0542 188 69 37 numarasını arayabilirsiniz."})
            if "exclusion" in m or "conflicting key" in m:
                return self._json(409, {"hata": "Bu saat az önce doldu. Lütfen başka bir saat seçin."})
            raise
        etkilesim(h["id"], "RANDEVU", r)
        threading.Thread(target=bildir, args=(h, r), daemon=True).start()
        return self._json(200, {"tamam": True, "saat": r["baslangic"]})


CIKIS_SAYFA = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>L’CARLIÉ</title></head>
<body style="font-family:Arial,sans-serif;background:#f7f4ee;color:#303638;padding:40px 20px;text-align:center">
<h1 style="color:#155761;font-size:22px">Listeden çıkarıldınız</h1>
<p style="font-size:16px">Eczanenize bundan sonra L’CARLIÉ tanıtım e-postası gönderilmeyecek.</p>
</body></html>"""


def main() -> None:
    adres = os.environ.get("RANDEVU_BIND", "172.18.0.1")
    port = int(os.environ.get("RANDEVU_PORT", "8095"))
    ThreadingHTTPServer((adres, port), Y).serve_forever()


if __name__ == "__main__":
    main()
