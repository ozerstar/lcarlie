#!/usr/bin/env python3
"""GÜNCEL OLAYLAR DEPARTMANI — her gün dış dünyadan önemli haberler.

NEDEN VAR
Sahip Türkiye genel haber analizi istemişti ve hiç üretilmemişti. Sebep
ölçüldü: araştırma katmanı sessizce ölüydü (tek arama arka ucu bu IP'den
engelliydi, 0 sonuç dönüyordu). Gemini grounding'e geçilince gerçek
kaynaklar gelmeye başladı; bu betik o yeteneği günlük bir işe çeviriyor.

NE YAPAR
Dört açıdan arar, indirdiği sayfaları modele KAYNAK OLARAK verir, model
yalnız o kaynaklardan madde çıkarır ve her maddeye "bize neden önemli"
yorumu ekler. Çıktı `core.guncel_olay`'a yazılır.

🔴 KAYNAKSIZ MADDE YAZILMAZ
Model bir madde üretip kaynak URL'sini getirilen listede eşleştiremezse o
madde DÜŞÜRÜLÜR. Bülten "dolu görünsün" diye uydurulmuş haber, hiç bülten
olmamasından kötüdür. Bugün aynı sistemde model iki kez olgu uydurdu
(INTIMBLANC içindekileri, VIREON INCI listesi) -- güçlü model bunu
bitirmiyor, sadece seyrekleştiriyor. O yüzden kapı kodda.

🔴 "HABER YOK" AYRI BİR DURUM
Araştırma boş dönerse `durum='KAYNAK_YOK'` yazılır. Satırın hiç olmaması
"o gün çalışmadı" demektir; ikisi karıştırılırsa ölü bir cron fark edilmez.

Çalıştırma:
    JARVIS_MEMORY_TRANSPORT=local-docker RESEARCH_SEARXNG_URL=... \\
      venv/bin/python scripts/guncel-olaylar.py [--kuru] [--gun YYYY-MM-DD]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jarvis.research_sources as rs
from jarvis.model_layer import ModelRouter

PSQL = ["docker", "exec", "-i", "lcarlie-postgres",
        "psql", "-U", "n8n", "-d", "n8n", "-tA", "-v", "ON_ERROR_STOP=1"]

# Dört açı. "Genel Türkiye haberi" tek sorguyla aranmaz: tek sorgu tek tür
# kaynak getirir. Açılar birbirinden farklı sayfalara iner ve birleşince
# resim çıkar -- research_team.py'nin aynı gerekçesi.
ACILAR: tuple[tuple[str, str], ...] = (
    ("ekonomi",
     "Turkiye ekonomi enflasyon faiz tuketici harcamasi son gelismeler"),
    # 🔴 SOMUT YAZ, "haberleri" DEME.
    # İlk hâli "Turkiye kozmetik kisisel bakim sektoru pazar haberleri" idi
    # ve iki koşuda da 0 kaynak verdi: 15 sayfa iniyor, 15'i birden alakasız
    # diye eleniyordu. Sebep, "haberleri/sektörü/pazar" gibi genel
    # kelimelerin alaka eşleşmesini sulandırması. Somut hâli (pazar
    # büyüklüğü, büyüme, ihracat) 4 kaynağı SIFIR elemeyle getiriyor.
    ("sektor",
     "kozmetik sektoru Turkiye pazar buyuklugu buyume"),
    ("sektor_ticaret",
     "Turkiye kozmetik ihracat uretim sektor raporu"),
    ("duzenleme",
     "Turkiye e-ticaret duzenlemesi reklam mevzuati son degisiklikler"),
    ("gundem",
     "Turkiye gundem onemli gelismeler bu hafta"),
)

MAX_MADDE = 8

# 🔴 ALINTILANAMAZ KAYNAKLAR
# İlk koşuda (20.09.2026) model enflasyon rakamını bir YOUTUBE videosuna,
# perakende satış verisini bir FACEBOOK videosuna dayandırdı. İçerik doğru
# olabilir ama bir iş bülteninde TÜİK verisi için sosyal medya videosu
# kaynak gösterilemez: okuyan doğrulayamaz, arşivi kaybolur, bağlamı
# kesilir. Bu alan adları aramadan DEĞİL, KAYNAK LİSTESİNDEN düşer --
# arama onları bulabilir, bülten onlara dayanamaz.
ALINTILANAMAZ = (
    "youtube.com", "youtu.be", "facebook.com", "fb.watch",
    "instagram.com", "tiktok.com", "twitter.com", "x.com",
    "pinterest.com", "reddit.com", "linkedin.com",
)


def alintilanabilir(url: str) -> bool:
    adres = url.lower()
    return not any(alan in adres for alan in ALINTILANAMAZ)


def _psql(sql: str) -> list[str]:
    sonuc = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, check=False)
    if sonuc.returncode != 0:
        raise SystemExit(f"psql hatası: {sonuc.stderr[:400]}")
    return [s for s in sonuc.stdout.split("\n") if s.strip()]


def _tirnak(deger) -> str:
    if deger is None or deger == "":
        return "NULL"
    return "'" + str(deger).replace("'", "''") + "'"


AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def son_gorulenler(gun: str, url_gun: int = 21, baslik_gun: int = 7) -> tuple[set[str], list[str]]:
    """🔴 GÜNLER ARASI TEKRAR KAPISI (04.11). Sorgular tarihsizdi ve tekrar
    elemesi yoktu: arama her gün aynı kalıcı sayfaları getirdi, panel 6 gün
    aynı "pazar 3,3 milyar dolar" haberini gösterdi. Son günlerde yazılmış
    kaynak adresi bir daha alınmaz; son başlıklar modele "tekrar etme" diye verilir."""
    try:
        urller = set(_psql("SELECT DISTINCT kaynak_url FROM core.guncel_olay "
                           f"WHERE gun < {_tirnak(gun)}::date AND gun >= {_tirnak(gun)}::date - {int(url_gun)};"))
        basliklar = _psql("SELECT baslik FROM core.guncel_olay "
                          f"WHERE gun < {_tirnak(gun)}::date AND gun >= {_tirnak(gun)}::date - {int(baslik_gun)} "
                          "ORDER BY gun DESC, id DESC LIMIT 60;")
    except SystemExit:
        return set(), []
    return urller, basliklar


def kaynaklari_topla(gun: str | None = None, eski_url: set[str] | None = None) -> list[dict]:
    """Her açıdan ayrı arama. Bir açı boş dönerse diğerleri düşmez."""
    adaptor = rs.WebSearchCrawlAdapter()
    toplam: list[dict] = []
    gorulen: set[str] = set(eski_url or ())
    g = date.fromisoformat(gun) if gun else date.today()  # noqa: DTZ011
    # Sorguya ay+yıl: tarihsiz sorgu her gün aynı "kalıcı" sayfaları döndürüyordu.
    zaman = f"{AYLAR[g.month - 1]} {g.year} son dakika"
    for aci, sorgu_ in ACILAR:
        sorgu = f"{sorgu_} {zaman}"
        basladi = time.time()
        try:
            cikti = adaptor.execute({"capability": rs.RESEARCH_CAPABILITY,
                                     "query": sorgu, "max_bytes": 64_000})
        except Exception as exc:  # noqa: BLE001
            print(f"  [{aci}] araştırma hatası: {str(exc)[:100]}")
            continue
        kaynaklar = cikti.get("sources") or []
        yeni, elenen = 0, 0
        for kaynak in kaynaklar:
            url = (kaynak.get("url") or "").strip()
            if not url or url in gorulen:
                if url in (eski_url or ()):
                    elenen += 1   # dün/önceki günlerde zaten yazıldı
                continue
            if not alintilanabilir(url):
                elenen += 1
                continue
            gorulen.add(url)
            toplam.append({
                "aci": aci,
                "baslik": (kaynak.get("title") or "").strip(),
                "url": url,
                "tarih": kaynak.get("published_date") or "",
                "metin": (kaynak.get("text") or "")[:2500],
            })
            yeni += 1
        print(f"  [{aci:10}] {time.time() - basladi:5.1f} sn · "
              f"{len(kaynaklar)} kaynak, {yeni} yeni"
              + (f", {elenen} alıntılanamaz elendi" if elenen else ""))
    return toplam


ISTEM = """Aşağıda Türkiye'den güncel haber kaynakları var. L'CARLIÉ adlı
kozmetik/kişisel bakım e-ticaret şirketi için {gun} tarihli günlük bülten hazırla.
L'CARLIÉ: kendi markalı cilt/vücut/bebek/mahrem bakım ürünleri; Wix sitesi,
Trendyol/Hepsiburada/Idefix/n11 pazaryerleri, Meta reklamları, ihracat hedefi.

KURALLAR
- YALNIZCA aşağıdaki kaynaklardan madde çıkar. Kaynaklarda olmayan hiçbir
  olay, sayı veya tarih yazma.
- YALNIZ YENİ OLAYLAR: {gun} tarihinden önceki ~10 gün içinde olan olayları al.
  Genel rapor, "2024/2025 değerlendirmesi", eski yıl verisi, tarihi belli
  olmayan kalıcı sayfa (ör. "pazar X milyar dolar") ALINMAZ.
- Aşağıdaki SON GÜNLERDE VERİLMİŞ başlıkların aynısını ya da aynı olayı tekrar verme.
- Her madde için kaynağın numarasını ver.
- "ozet": haberin ANA OLAYI — kim, ne yaptı / ne oldu, ne zaman, varsa sayı.
  1-2 cümle, düz Türkçe.
- "neden_onemli": L'CARLIÉ İÇİN ANLAMI — tek cümle, somut alanı adlandır
  (fiyat/maliyet, reklam ve iddia mevzuatı, pazaryeri, ihracat, müşteri talebi).
  YORUM olarak yaz; kesin sonuç bildirme.
- onem: KRITIK (doğrudan ve acil etki), DIKKAT (izlenmeli), BILGI (bağlam).
- En fazla {mad} madde. Aynı olayı tekrarlama.

Yanıtı SADECE şu JSON biçiminde ver:
{{"maddeler":[{{"kaynak_no":1,"baslik":"...","ozet":"...","neden_onemli":"...","onem":"DIKKAT"}}]}}

SON GÜNLERDE VERİLMİŞ BAŞLIKLAR (tekrar etme)
{eski}

KAYNAKLAR
{kaynaklar}
"""


def madde_uret(kaynaklar: list[dict], layer, gun: str | None = None,
               eski_baslik: list[str] | None = None) -> tuple[list[dict], str | None]:
    bloklar = []
    for sira, kaynak in enumerate(kaynaklar, start=1):
        tarih = f" (yayın: {kaynak['tarih']})" if kaynak.get("tarih") else ""
        bloklar.append(f"[{sira}] {kaynak['baslik']}{tarih}\n{kaynak['metin'][:1200]}")
    istem = ISTEM.format(mad=MAX_MADDE, gun=gun or str(date.today()),  # noqa: DTZ011
                         eski="\n".join(f"- {b}" for b in (eski_baslik or [])[:60]) or "- (yok)",
                         kaynaklar="\n\n".join(bloklar))
    sonuc, _, _ = layer.generate([{"role": "user", "content": istem}],
                                 max_tokens=1800, escalate=True,
                                 is_anahtari="guncel_olaylar")
    ham = (sonuc or {}).get("text") or ""
    model = (sonuc or {}).get("model")
    basla, bit = ham.find("{"), ham.rfind("}")
    if basla < 0 or bit <= basla:
        return [], model
    try:
        veri = json.loads(ham[basla:bit + 1])
    except json.JSONDecodeError:
        return [], model

    maddeler: list[dict] = []
    for madde in (veri.get("maddeler") or []):
        try:
            no = int(madde.get("kaynak_no"))
        except (TypeError, ValueError):
            continue
        # 🔴 KAYNAK KAPISI: numara listede yoksa madde DÜŞER.
        if not (1 <= no <= len(kaynaklar)):
            continue
        kaynak = kaynaklar[no - 1]
        baslik = " ".join(str(madde.get("baslik") or "").split())
        ozet = " ".join(str(madde.get("ozet") or "").split())
        if not baslik or not ozet:
            continue
        onem = str(madde.get("onem") or "BILGI").upper()
        if onem not in ("KRITIK", "DIKKAT", "BILGI"):
            onem = "BILGI"
        maddeler.append({
            "aci": kaynak["aci"], "baslik": baslik[:300], "ozet": ozet[:1200],
            "neden_onemli": " ".join(str(madde.get("neden_onemli") or "").split())[:800],
            "kaynak_url": kaynak["url"],
            "kaynak_adi": (kaynak["baslik"] or "")[:200],
            "yayin_tarihi": kaynak["tarih"][:40],
            "onem": onem,
        })
    return maddeler[:MAX_MADDE], model


def yaz(gun: str, maddeler: list[dict], kaynak_sayisi: int,
        model: str | None, sure: float, durum: str, not_metni: str) -> None:
    _psql(
        "INSERT INTO core.guncel_olay_kosu (gun,durum,aci_sayisi,kaynak_sayisi,"
        "madde_sayisi,model,sure_sn,not_metni) VALUES "
        f"({_tirnak(gun)},{_tirnak(durum)},{len(ACILAR)},{kaynak_sayisi},"
        f"{len(maddeler)},{_tirnak(model)},{sure:.1f},{_tirnak(not_metni)}) "
        "ON CONFLICT (gun) DO UPDATE SET durum=EXCLUDED.durum,"
        "kaynak_sayisi=EXCLUDED.kaynak_sayisi,madde_sayisi=EXCLUDED.madde_sayisi,"
        "model=EXCLUDED.model,sure_sn=EXCLUDED.sure_sn,"
        "not_metni=EXCLUDED.not_metni,olusturma=now();")
    for madde in maddeler:
        _psql(
            "INSERT INTO core.guncel_olay (gun,aci,baslik,ozet,neden_onemli,"
            "kaynak_url,kaynak_adi,yayin_tarihi,onem) VALUES ("
            f"{_tirnak(gun)},{_tirnak(madde['aci'])},{_tirnak(madde['baslik'])},"
            f"{_tirnak(madde['ozet'])},{_tirnak(madde['neden_onemli'])},"
            f"{_tirnak(madde['kaynak_url'])},{_tirnak(madde['kaynak_adi'])},"
            f"{_tirnak(madde['yayin_tarihi'])},{_tirnak(madde['onem'])}) "
            "ON CONFLICT (gun,kaynak_url) DO NOTHING;")


def main() -> None:
    kuru = "--kuru" in sys.argv
    gun = str(date.today())  # noqa: DTZ011
    if "--gun" in sys.argv:
        gun = sys.argv[sys.argv.index("--gun") + 1]

    basladi = time.time()
    print(f"GÜNCEL OLAYLAR · {gun} · {len(ACILAR)} açı")
    eski_url, eski_baslik = son_gorulenler(gun)
    print(f"son günlerde yazılmış: {len(eski_url)} adres, {len(eski_baslik)} başlık (tekrar edilmez)")
    kaynaklar = kaynaklari_topla(gun, eski_url)
    print(f"toplam benzersiz kaynak: {len(kaynaklar)}")

    if not kaynaklar:
        print("KAYNAK YOK — bülten üretilmiyor (uydurma madde yazılmaz)")
        if not kuru:
            yaz(gun, [], 0, None, time.time() - basladi, "KAYNAK_YOK",
                "araştırma hiçbir açıdan kaynak döndürmedi")
        return

    maddeler, model = madde_uret(kaynaklar, ModelRouter(), gun, eski_baslik)
    # Son kapı: dünkü başlığın aynısı yazılmaz (model kuralı kaçırırsa).
    eski_kucuk = {" ".join(b.lower().split()) for b in eski_baslik}
    maddeler = [m for m in maddeler if " ".join(m["baslik"].lower().split()) not in eski_kucuk]
    sure = time.time() - basladi
    print(f"madde: {len(maddeler)} · model: {model} · {sure:.1f} sn")
    for madde in maddeler:
        print(f"  [{madde['onem']:6}] ({madde['aci']}) {madde['baslik'][:70]}")

    if kuru:
        print("--kuru: veritabanına yazılmadı")
        return
    durum = "URETILDI" if maddeler else "KAYNAK_YOK"
    yaz(gun, maddeler, len(kaynaklar), model, sure, durum,
        "" if maddeler else "kaynak bulundu ama kaynağa bağlanabilen madde çıkmadı")
    print(f"yazıldı → core.guncel_olay ({durum})")


if __name__ == "__main__":
    main()
