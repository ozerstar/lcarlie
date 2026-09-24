# -*- coding: utf-8 -*-
"""SAHA haritası: karo (tile) vekili ve disk önbelleği.

NEDEN VEKİL, NEDEN DOĞRUDAN DEĞİL:

Panelin içerik güvenliği ilkesi `img-src 'self' data:`. Harita karolarını
tarayıcı doğrudan openstreetmap.org'dan çekseydi üç şey olurdu: (1) ilke
gevşetilmek zorunda kalırdı, (2) saha elemanının o an haritada NEREYE
baktığı üçüncü tarafa giderdi, (3) sahibin "veriyi kendi veri merkezimizde
tutalım" şartı delinirdi. Vekil bu üçünü birden kapatır: tarayıcı yalnız
kendi sunucumuzla konuşur.

ÖNBELLEK: İnilen her karo diske yazılır ve bir daha indirilmez. Ankara'nın
gezilen bölgesi birkaç gün içinde yerelde birikir; ondan sonra harita
internetsiz de açılır ve yukarı akışa yük binmez.

🔴 AÇIK KAPI DEĞİL. İki sınır var: z 10-18 arası, ve karo ANKARA
ÇERÇEVESİNİN içinde olmak zorunda. Olmasaydı bu uç, dünyanın her yerinin
karosunu bizim üzerimizden indiren bir açık vekile dönerdi -- hem yukarı
akıştaki servisin kullanım şartlarını çiğnerdi hem de diski doldururdu.

KULLANIM ŞARTI: OpenStreetMap karo sunucusu kendini tanıtan bir
User-Agent ister ve toplu indirmeyi yasaklar. Talep üzerine, tek kullanıcı
ölçeğinde ve önbellekli çekim bu şartların içindedir. Saha ekibi
büyüdüğünde ücretli bir karo sağlayıcısına ya da kendi karo sunucumuza
geçmek gerekir -- bu dosyanın tek değiştirilecek yeri KAYNAK satırıdır.
"""
from __future__ import annotations

import math
import time
import urllib.error
import urllib.request
from pathlib import Path

KAROLAR = Path("/opt/lcarlie/saha-karo")
KAYNAK = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TANITIM = "LCARLIE-Saha/1.0 (+https://jarvis.lcarlie.shop; saha ziyaret paneli)"

EN_KUCUK_Z, EN_BUYUK_Z = 10, 18
# Ankara çerçevesi -- tarama betiğiyle AYNI sınır (scripts/overture-tara.py).
SINIR = {"xmin": 32.3, "xmax": 33.3, "ymin": 39.4, "ymax": 40.3}
ZAMAN_ASIMI = 12
# Karo eskimez sayılmaz ama sonsuza kadar da taze değildir: 90 günden eski
# karo bir daha çekilir. Yol ağı değişir; dondurulmuş harita yanıltır.
TAZELIK_GUN = 90


class HaritaHatasi(ValueError):
    """Karo isteği kabul edilmedi."""


def _karo_araligi(z: int) -> tuple[int, int, int, int]:
    """Ankara çerçevesinin bu yakınlaştırmadaki karo aralığı."""
    n = 2 ** z

    def _x(boylam):
        return int((boylam + 180.0) / 360.0 * n)

    def _y(enlem):
        r = math.radians(enlem)
        return int((1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n)

    # Enlem büyüdükçe y küçülür; bu yüzden ymax/ymin ters bağlanır.
    return _x(SINIR["xmin"]), _x(SINIR["xmax"]), _y(SINIR["ymax"]), _y(SINIR["ymin"])


def dogrula(z: int, x: int, y: int) -> None:
    if not EN_KUCUK_Z <= z <= EN_BUYUK_Z:
        raise HaritaHatasi("yakinlastirma %d-%d arasinda olmali"
                           % (EN_KUCUK_Z, EN_BUYUK_Z))
    n = 2 ** z
    if not (0 <= x < n and 0 <= y < n):
        raise HaritaHatasi("karo araligin disinda")
    x1, x2, y1, y2 = _karo_araligi(z)
    # Bir karoluk pay: ekranın kenarı çerçevenin biraz dışını gösterir.
    if not (x1 - 1 <= x <= x2 + 1 and y1 - 1 <= y <= y2 + 1):
        raise HaritaHatasi("karo Ankara cercevesinin disinda")


def _yol(z: int, x: int, y: int) -> Path:
    return KAROLAR / str(z) / str(x) / ("%d.png" % y)


def karo(z: int, x: int, y: int) -> bytes:
    """Karo baytları. Önce disk, yoksa yukarı akış.

    Yukarı akış hata verirse ve elimizde ESKİ bir kopya varsa o döner:
    eski harita, hiç harita olmamasından iyidir. Elimizde hiçbir şey yoksa
    hata yükselir -- boş bir kare döndürüp "harita çalışıyor" görüntüsü
    vermek, sahada yanlış yöne yürütür.
    """
    dogrula(z, x, y)
    hedef = _yol(z, x, y)
    if hedef.exists():
        yas_gun = (time.time() - hedef.stat().st_mtime) / 86400.0
        if yas_gun < TAZELIK_GUN:
            return hedef.read_bytes()

    istek = urllib.request.Request(
        KAYNAK.format(z=z, x=x, y=y), headers={"User-Agent": TANITIM})
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            veri = yanit.read()
    except (urllib.error.URLError, OSError, ValueError) as hata:
        if hedef.exists():
            return hedef.read_bytes()      # bayat ama var
        raise HaritaHatasi("karo alinamadi: %s" % str(hata)[:120]) from None

    if not veri.startswith(b"\x89PNG"):
        raise HaritaHatasi("karo PNG degil")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_suffix(".png.tmp")
    gecici.write_bytes(veri)
    gecici.replace(hedef)                  # yarim dosya okunmaz
    return veri


def onbellek_durumu() -> dict:
    """Kaç karo birikti, ne kadar yer tutuyor."""
    if not KAROLAR.exists():
        return {"karo": 0, "bayt": 0}
    sayi = bayt = 0
    for p in KAROLAR.rglob("*.png"):
        sayi += 1
        bayt += p.stat().st_size
    return {"karo": sayi, "bayt": bayt}
