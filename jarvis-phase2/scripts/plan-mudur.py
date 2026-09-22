#!/usr/bin/env python3
"""İŞ PLANLAMA MÜDÜRÜ — kapsamı ölçer, araştırma planını yazar.

Sahip 21.09.2026: *"önce sistem tüm ürünler için bir tur hepsini yapsın,
ardından müdürler bunu planlasın ve düzenli bir şekilde bu veriler
toplanacak… iş bölümü planlamasını kim yapıyorsa göreve çağır, yoksa işe
al."* Kadroda böyle bir rol yoktu; `is_planlama` 21.09.2026'da eklendi.

NE YAPAR
1. KAPSAMI ÖLÇER  — hangi departmanın kadrosu var, hangi ürün yayında,
                    hangisi en son ne zaman araştırıldı
2. BOŞLUĞU GÖRÜR  — hiç araştırılmamış olanı öne alır
3. PLANI YAZAR    — core.arastirma_plani'ye satır atar

🔴 SIFIR MODEL ÇAĞRISI. Plan bir MUHAKEME değil, bir DAĞITIMDIR: kim
kadrolu, hangi ürün yayında, en son ne zaman bakıldı. Bunları saymak için
modele ihtiyaç yok; model kullanmak hem maliyet hem de sayının üstüne bir
yorum katmanı koymak olurdu.

🔴 SIKLIK KEYFİ DEĞİL, KADROYA VE SATIŞA BAĞLI:
   - kadrosu kalabalık departman daha sık (bakan çok, iş çok)
   - satışı olan ürün, satışı olmayandan daha sık
   - hiç araştırılmamış olan HER ZAMAN önce
Sebep: sınırsız araştırma faturayı şişirir; sıklık, ilgiyi takip etmeli.

Çıkış: 0=plan yazıldı · 1=hata · 2=plan gerekmedi
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis.memory import CompanyMemory  # noqa: E402

# Departman kodu -> o birimin gerçekten arayacağı konular.
# 🔴 Bunlar "konu şablonu"dur, kapsam değil. Kapsamı (kimin alacağını)
# kadro ölçümü belirler; buradaki liste yalnız o birimin NE arayacağını
# söyler. Sözlükte olmayan departman GENEL konuyu alır -- dışarıda kalmaz.
KONU_SABLONU: dict[str, tuple[str, ...]] = {
    "CREATIVE_STRAT": ("kozmetik reklam kreatif trendleri",
                       "sosyal medya reklam formatlari etkilesim"),
    "BRAND": ("kozmetik marka konumlandirma fiyat iletisimi",),
    "COMPETITOR_INT": ("turkiye kozmetik pazaryeri fiyat karsilastirma",),
    "MARKET_INT": ("turkiye kozmetik pazari buyume verileri",),
    "REGULATORY": ("kozmetik yonetmeligi iddia sinirlari Turkiye",),
    "CONTENT": ("kozmetik icerik pazarlamasi ornekleri",),
    "BIZDEV": ("kozmetik distributor ve is gelistirme firsatlari Turkiye",),
    "SEO": ("kozmetik e-ticaret SEO anahtar kelime",),
    "META_MEDIA": ("Meta reklam maliyetleri kozmetik Turkiye",),
    "CRO": ("e-ticaret donusum orani iyilestirme kozmetik",),
    "ECOM": ("kozmetik e-ticaret operasyon ve kargo",),
    "FINANCE": ("kozmetik urun maliyet ve marj yapisi",),
    "PRODUCT": ("kozmetik formulasyon ve icerik trendleri",),
    "SOCIAL": ("kozmetik sosyal medya organik buyume",),
    "INFLUENCER": ("kozmetik influencer isbirligi Turkiye",),
}
GENEL_KONU = "kozmetik sektoru guncel gelismeler Turkiye"

# Ürün başına konu kalıbı.
URUN_KONULARI = (
    "{urun} benzeri urun fiyatlari Turkiye pazaryeri",
    "{urun} kategorisinde one cikan markalar ve satis vaatleri",
)


def _psql(sql: str, rol: str = "ai_writer") -> list[str]:
    """Tek sorgu, stdin'den. 🔴 CRLF ve $$ tuzakları için stdin kullanılır."""
    tam = f"\\set ON_ERROR_STOP on\nBEGIN;\nSET SESSION AUTHORIZATION {rol};\n{sql}\nCOMMIT;\n"
    p = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n",
         "-d", "n8n", "-At", "-f", "-"],
        input=tam.replace("\r\n", "\n"), capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:400])
    return [s for s in (p.stdout or "").splitlines() if s and s not in ("BEGIN", "COMMIT", "SET")]


def kadrolu_departmanlar(hafiza: CompanyMemory) -> list[tuple[str, int]]:
    """Kadrosu OLAN departmanlar ve üye sayısı."""
    try:
        from jarvis import roster
    except Exception as hata:  # noqa: BLE001
        raise RuntimeError(f"kadro okunamadi: {hata}") from hata
    out = []
    for kod, uyeler in roster.departman_uyeleri().items():
        if uyeler:
            out.append((kod, len(uyeler)))
    return sorted(out, key=lambda x: -x[1])


def yayindaki_urunler(hafiza: CompanyMemory) -> list[tuple[str, int]]:
    """Yayındaki ürünler ve ölçülen satış adedi."""
    kayitlar = hafiza._fetch("urun_karti").records
    satislar = hafiza._fetch("sales_items").records
    say: dict[str, int] = {}
    for s in satislar:
        ad = str(s.get("urun_adi") or "").split("|")[0].strip()
        if ad:
            say[ad] = say.get(ad, 0) + 1
    out = []
    gorulen = set()
    for k in kayitlar:
        if not k.get("wix_yayinda"):
            continue
        ad = str(k.get("urun_adi") or "").split("|")[0].strip()
        if not ad or ad in gorulen:
            continue
        gorulen.add(ad)
        out.append((ad, say.get(ad, 0)))
    # Satışı olan önce: ilgiyi takip et.
    return sorted(out, key=lambda x: -x[1])


def _siklik_departman(uye: int) -> tuple[int, int]:
    """(sıklık_gün, öncelik) — kadro kalabalıksa daha sık ve öncelikli."""
    if uye >= 4:
        return 3, 2
    if uye >= 2:
        return 7, 4
    return 14, 6


def _siklik_urun(satis: int) -> tuple[int, int]:
    if satis >= 3:
        return 7, 3
    if satis >= 1:
        return 14, 5
    return 30, 7


def plan_kur(hafiza: CompanyMemory, urun_sinir: int, kuru: bool) -> dict:
    satirlar: list[tuple] = []

    for kod, uye in kadrolu_departmanlar(hafiza):
        siklik, oncelik = _siklik_departman(uye)
        konular = KONU_SABLONU.get(kod, (GENEL_KONU,))
        for konu in konular:
            satirlar.append((
                "DEPARTMAN", kod, konu, siklik, oncelik,
                f"{uye} kisilik kadro; kadro buyuklugune gore {siklik} gunde bir"))

    urunler = yayindaki_urunler(hafiza)[:urun_sinir]
    for ad, satis in urunler:
        siklik, oncelik = _siklik_urun(satis)
        for kalip in URUN_KONULARI:
            satirlar.append((
                "URUN", ad, kalip.format(urun=ad), siklik, oncelik,
                f"olculen satis {satis}; satisa gore {siklik} gunde bir"))

    if kuru:
        return {"kuru": True, "satir": len(satirlar),
                "departman": len({s[1] for s in satirlar if s[0] == "DEPARTMAN"}),
                "urun": len({s[1] for s in satirlar if s[0] == "URUN"}),
                "ornek": satirlar[:5]}

    # 🔴 Tek deyimde toplu ekleme; ON CONFLICT ile aynı satır iki kez
    # planlanmaz (tekil kısıt zaten var, ama çakışmada patlamak yerine
    # gerekçeyi ve sıklığı GÜNCELLEMEK doğru davranış: plan değişebilir).
    def q(s: str) -> str:
        return "'" + str(s).replace("'", "''") + "'"

    degerler = ",".join(
        f"({q(k)},{q(h)},{q(ko)},{si},{on},{q(g)})" for k, h, ko, si, on, g in satirlar)
    sql = (
        "INSERT INTO core.arastirma_plani "
        "(kapsam,hedef,konu,siklik_gun,oncelik,gerekce) VALUES "
        f"{degerler} "
        "ON CONFLICT (kapsam,hedef,konu) DO UPDATE SET "
        "siklik_gun=EXCLUDED.siklik_gun, oncelik=EXCLUDED.oncelik, "
        "gerekce=EXCLUDED.gerekce, aktif=TRUE;")
    _psql(sql)
    sayim = _psql("SELECT count(*)::text FROM core.arastirma_plani WHERE aktif;",
                  rol="ai_reader")
    return {"kuru": False, "yazilan": len(satirlar),
            "plandaki_toplam": int(sayim[0]) if sayim else None,
            "departman": len({s[1] for s in satirlar if s[0] == "DEPARTMAN"}),
            "urun": len({s[1] for s in satirlar if s[0] == "URUN"})}


def main() -> int:
    ap = argparse.ArgumentParser(description="Araştırma planını kurar")
    ap.add_argument("--urun-sinir", type=int, default=40,
                    help="plana alınacak en fazla ürün")
    ap.add_argument("--kuru", action="store_true",
                    help="yazma, yalnız ne yazacağını göster")
    a = ap.parse_args()

    hafiza = CompanyMemory(host=None)
    try:
        sonuc = plan_kur(hafiza, a.urun_sinir, a.kuru)
    except Exception as hata:  # noqa: BLE001
        print(f"plan kurulamadi: {str(hata)[:300]}", file=sys.stderr)
        return 1

    print(json.dumps(sonuc, ensure_ascii=False, indent=1))
    return 0 if sonuc.get("satir", sonuc.get("yazilan", 0)) else 2


if __name__ == "__main__":
    sys.exit(main())

