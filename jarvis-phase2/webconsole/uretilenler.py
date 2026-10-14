# -*- coding: utf-8 -*-
"""ÜRETİLENLER — üretilen her şeyin tek toplandığı yer.

Sahip 26.09.2026: "ben o dosyaları sistemde toplu bir yerde görebilmeyi
istiyorum. sistem arayüzü çok karışık ne nerde anlamıyorum."

🔴 ÖLÇÜLDÜ, HAKLI. Panelde 22 sekme var ve üretilen şeyler dağılmıştı:
katalog PDF'i KATALOG'da, gönderi görselleri INSTAGRAM'da, çekim föyü
gönderi kartının içinde, kreatif konseptler HİÇBİR YERDE, baskı
görselleri yalnız diskte. "Şu dosya nerede" sorusunun tek bir cevabı
yoktu; her biri ayrı bir sekmenin içinde saklıydı.

Burada her üretilen şey aynı biçimde durur: NE olduğu, NE ZAMAN
üretildiği, NE KADAR yer tuttuğu ve NEREDEN inileceği. Sayfa bir şey
üretmez, yalnız gösterir -- gösterilen her satırın arkasında gerçek bir
dosya ya da kayıt vardır.

🔴 YOKLUK DA GÖSTERİLİR. Bir tür hiç üretilmemişse satır gizlenmez,
"henüz üretilmedi" diye yazılır ve neyin çalıştırılacağı söylenir.
Boş bölümü gizlemek, eksik olanı görünmez yapar.
"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

KAP = "lcarlie-postgres"

GONDERI_DIZIN = Path("/opt/lcarlie/gonderi-gorsel")
BASKI_DIZIN = Path("/opt/lcarlie/katalog-baski")
KATALOG_GORSEL = Path("/opt/lcarlie/katalog-gorsel")


class UretimHatasi(RuntimeError):
    pass


def _oku(sql: str) -> list:
    try:
        p = subprocess.run(
            ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.SubprocessError) as hata:
        raise UretimHatasi("veritabani okunamadi: %s" % hata) from None
    if p.returncode:
        raise UretimHatasi((p.stderr or p.stdout)[:200])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def _tarih(zaman: float) -> str:
    return datetime.datetime.fromtimestamp(zaman).strftime("%d.%m.%Y %H:%M")


def _mb(bayt: int) -> float:
    return round(bayt / 1048576.0, 2)


def _dosya_satiri(yol: Path, baslik: str, indir: str, aciklama: str = "",
                  onizleme: str = "") -> dict:
    d = yol.stat()
    return {"baslik": baslik, "aciklama": aciklama, "indir": indir,
            "onizleme": onizleme, "mb": _mb(d.st_size),
            "uretim": _tarih(d.st_mtime)}


def _konseptler() -> dict:
    """Kreatif konseptler. Panelde hiç görünmüyorlardı."""
    try:
        satirlar = _oku("""SELECT row_to_json(t) FROM (
          SELECT k.konsept_id, k.plan_id, p.urun_slug, p.amac, p.bicim,
                 k.ad, k.ana_fikir, k.gorsel_metafor, k.kompozisyon,
                 k.neden_durdurur, k.ay_kamera, k.ay_isik,
                 k.ay_negatif_alan, k.ay_tipografi_alani,
                 k.istem, k.negatif_istem,
                 k.p_marka_uyumu + k.p_ozgunluk + k.p_mesaj_netligi
                  + k.p_durdurma_gucu + k.p_uretilebilirlik
                  + k.p_gorsel_olgunluk AS puan,
                 to_char(k.uretim_at, 'DD.MM.YYYY HH24:MI') AS uretim
            FROM core.kreatif_konsept k
            JOIN core.ig_gonderi_plani p USING (plan_id)
           WHERE k.secildi ORDER BY k.plan_id) t;""")
        elenen = _oku("""SELECT row_to_json(t) FROM (
          SELECT count(*) AS n FROM core.kreatif_konsept
           WHERE ozelestiri_sonuc = 'TERK') t;""")[0]["n"]
    except UretimHatasi as hata:
        return {"durum": "SORAMADIM", "sebep": str(hata), "kayitlar": []}
    return {"durum": "VAR" if satirlar else "YOK", "kayitlar": satirlar,
            "elenen": elenen,
            "bos_notu": "Hiç konsept üretilmedi — "
                        "scripts/kreatif-konsept-uret.py <plan_id> --yaz"}


def _gonderi_gorselleri() -> dict:
    """Instagram paketlerinin görselleri + çekim föyleri."""
    try:
        paketler = _oku("""SELECT row_to_json(t) FROM (
          SELECT plan_id, urun_slug, amac, bicim, durum, gorsel_dosya,
                 gorsel_taslak_mi, konsept_id,
                 to_char(uretim_at, 'DD.MM.YYYY HH24:MI') AS uretim
            FROM core.ig_gonderi_plani
           ORDER BY plan_id DESC) t;""")
    except UretimHatasi as hata:
        return {"durum": "SORAMADIM", "sebep": str(hata), "kayitlar": []}

    kayitlar = []
    for p in paketler:
        dosya = p.get("gorsel_dosya")
        boyut = None
        if dosya:
            yol = GONDERI_DIZIN / dosya
            if yol.is_file():
                boyut = _mb(yol.stat().st_size)
            else:
                dosya = None      # kayitta var, diskte yok: yalan soyleme
        kayitlar.append({
            "plan_id": p["plan_id"], "urun": p["urun_slug"],
            "amac": p["amac"], "bicim": p["bicim"], "durum": p["durum"],
            "gorsel": dosya, "mb": boyut, "uretim": p["uretim"],
            "taslak": p.get("gorsel_taslak_mi"),
            "konsept_id": p.get("konsept_id"),
            # Reels'te bu kare VIDEO DEGIL; etiket bunu soylemezse
            # hazir video sanilir.
            "kapak_karesi": p["bicim"] == "REELS",
            "foy": "/ig-foy/%s" % p["plan_id"],
        })
    return {"durum": "VAR" if kayitlar else "YOK", "kayitlar": kayitlar,
            "bos_notu": "Hiç gönderi paketi yok — "
                        "scripts/ig-gonderi-uret.py"}


def _katalog_pdf() -> dict:
    kayitlar = []
    for tur, ad, aciklama in (
            ("baski", "lcarlie-katalog.pdf",
             "A4 + 3 mm taşma · fontlar gömülü · 300 DPI · basımevine giden"),
            ("gozden", "lcarlie-katalog-gozden.pdf",
             "110 DPI · ekranda bakmak ve paylaşmak için")):
        yol = BASKI_DIZIN / ad
        if yol.is_file():
            kayitlar.append(_dosya_satiri(
                yol, ad, "/katalog-pdf/%s" % tur, aciklama))
    return {"durum": "VAR" if kayitlar else "YOK", "kayitlar": kayitlar,
            "bos_notu": "Katalog PDF'i üretilmedi — "
                        "scripts/katalog-tasarim.py"}


def _urun_gorselleri() -> dict:
    """Katalog ürün görselleri: sayı ve toplam yer."""
    if not KATALOG_GORSEL.is_dir():
        return {"durum": "YOK", "kayitlar": [],
                "bos_notu": "Ürün görselleri indirilmedi — "
                            "scripts/katalog-gorsel-indir.py"}
    dosyalar = [y for y in KATALOG_GORSEL.iterdir() if y.is_file()]
    if not dosyalar:
        return {"durum": "YOK", "kayitlar": [],
                "bos_notu": "Klasör boş — scripts/katalog-gorsel-indir.py"}
    toplam = sum(y.stat().st_size for y in dosyalar)
    en_yeni = max(y.stat().st_mtime for y in dosyalar)
    return {"durum": "VAR", "kayitlar": [{
        "baslik": "%d ürün görseli" % len(dosyalar),
        "aciklama": "katalog kartlarında ve baskıda kullanılıyor",
        "mb": _mb(toplam), "uretim": _tarih(en_yeni), "indir": "",
        "onizleme": ""}]}


def _tasarim_isleri() -> dict:
    try:
        satirlar = _oku("""SELECT row_to_json(t) FROM (
          SELECT is_id, is_turu, isteyen, istek, durum, disa_aktarim,
                 to_char(uretildi, 'DD.MM.YYYY HH24:MI') AS uretim
            FROM core.tasarim_isi ORDER BY is_id DESC LIMIT 40) t;""")
    except UretimHatasi as hata:
        return {"durum": "SORAMADIM", "sebep": str(hata), "kayitlar": []}
    return {"durum": "VAR" if satirlar else "YOK", "kayitlar": satirlar,
            "bos_notu": "Tasarım işi yapılmadı — scripts/tasarim-gorevi.py"}


def uretilenler() -> dict:
    """Üretilen her şey, tek yerde."""
    bolumler = [
        {"anahtar": "konsept", "baslik": "Kreatif konseptler",
         "aciklama": "Her paket için üç fikir üretilir, altı eksende "
                     "puanlanır, klişe kapısından geçer; biri seçilir.",
         **_konseptler()},
        {"anahtar": "gonderi", "baslik": "Gönderi görselleri ve föyler",
         "aciklama": "Instagram paketlerinin kareleri. Reels'te bu kare "
                     "kapak karesidir, video değildir.",
         **_gonderi_gorselleri()},
        {"anahtar": "katalog", "baslik": "Basılı katalog",
         "aciklama": "İki dosya, iki ayrı iş. Karıştırmak, gözden geçirme "
                     "kopyasını basımevine göndermek demek olur.",
         **_katalog_pdf()},
        {"anahtar": "urun_gorsel", "baslik": "Ürün görselleri",
         "aciklama": "Katalog ve baskı için indirilmiş ürün fotoğrafları.",
         **_urun_gorselleri()},
        {"anahtar": "tasarim", "baslik": "Tasarım işleri",
         "aciklama": "Şablondan üretilen tasarımlar ve mevzuat denetimi "
                     "sonuçları.",
         **_tasarim_isleri()},
    ]
    sayi = sum(len(b.get("kayitlar") or []) for b in bolumler)
    soramadim = [b["baslik"] for b in bolumler if b.get("durum") == "SORAMADIM"]
    return {"bolumler": bolumler, "toplam": sayi,
            # 🔴 VERI_YOK ile SORAMADIM ayri seylerdir: birincisi uretim
            #    yapilmadigini, ikincisi bakamadigimizi soyler.
            "soramadim": soramadim}
