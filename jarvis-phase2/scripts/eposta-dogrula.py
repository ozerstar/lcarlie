#!/usr/bin/env python3
"""Eczane e-postalarını göndermeden doğrular: sözdizimi -> MX -> SMTP RCPT.

Sonuç core.eczane_hedef.eposta_dogrulama'ya yazılır:
  GECERLI   sunucu alıcıyı kabul etti (250)
  GECERSIZ  sözdizimi bozuk, MX yok ya da sunucu 550/551/553 dedi
  BELIRSIZ  hepsini kabul eden sunucu, gri liste, zaman aşımı
"""
import re
import smtplib
import socket
import subprocess
import sys
import time
import uuid

PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n", "-At", "-v", "ON_ERROR_STOP=1"]
HELO = "n8n.lcarlie.shop"
GONDEREN = "dogrulama@lcarlie.com.tr"
DESEN = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
mx_onbellek = {}


def psql(sql, **degisken):
    komut = PSQL[:]
    for ad, deger in degisken.items():
        komut += ["-v", f"{ad}={deger}"]
    return subprocess.run(komut, input=sql, capture_output=True, text=True, check=True).stdout


def mx(alan):
    if alan not in mx_onbellek:
        cikti = subprocess.run(["dig", "+short", "MX", alan], capture_output=True, text=True, timeout=15).stdout
        kayit = sorted((int(p[0]), p[1].rstrip(".")) for p in (s.split() for s in cikti.splitlines()) if len(p) == 2)
        mx_onbellek[alan] = [h for _, h in kayit]
    return mx_onbellek[alan]


def rcpt(sunucu, adres):
    s = smtplib.SMTP(timeout=20)
    try:
        s.connect(sunucu, 25)
        s.helo(HELO)
        s.mail(GONDEREN)
        kod, _ = s.rcpt(adres)
        # Var olamayacak bir adres de kabul ediliyorsa sunucu hepsini kabul ediyor demektir
        sahte, _ = s.rcpt(f"yok-{uuid.uuid4().hex[:12]}@{adres.split('@')[1]}") if kod == 250 else (0, b"")
        return kod, sahte
    finally:
        try:
            s.quit()
        except (OSError, smtplib.SMTPException):
            pass


def dogrula(adres):
    if not DESEN.match(adres):
        return "GECERSIZ", "sözdizimi"
    sunucular = mx(adres.split("@")[1])
    if not sunucular:
        return "GECERSIZ", "MX yok"
    for sunucu in sunucular[:2]:
        try:
            kod, sahte = rcpt(sunucu, adres)
        except (socket.timeout, OSError, smtplib.SMTPException) as e:
            son = f"{sunucu}: {type(e).__name__}"
            continue
        if kod == 250:
            return ("BELIRSIZ", "hepsini kabul ediyor") if sahte == 250 else ("GECERLI", sunucu)
        if kod in (550, 551, 553):
            return "GECERSIZ", f"{kod}"
        return "BELIRSIZ", f"kod {kod}"
    return "BELIRSIZ", son


def main():
    satirlar = psql("SELECT id, lower(trim(eposta)) FROM core.eczane_hedef "
                    "WHERE eposta <> '' AND eposta_dogrulama IS NULL ORDER BY id;").split("\n")
    sayac = {}
    for satir in filter(None, satirlar):
        hedef_id, adres = satir.split("|", 1)
        sonuc, ayrinti = dogrula(adres)
        sayac[sonuc] = sayac.get(sonuc, 0) + 1
        psql("UPDATE core.eczane_hedef SET eposta_dogrulama = :'s', guncellendi = now() WHERE id = :'i';",
             s=sonuc, i=hedef_id)
        print(f"{sonuc:9} {adres} ({ayrinti})", flush=True)
        time.sleep(1.5)
    print("ÖZET", sayac)


if __name__ == "__main__":
    sys.exit(main())
