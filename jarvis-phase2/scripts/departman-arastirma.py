#!/usr/bin/env python3
"""Departman sorumlularinin gunluk arastirmasi.

NEDEN VAR
Sahip 20.09.2026: "bu mudurler surekli kendi konulari ile ilgili arastirma
yapip kendilerini gelistirsinler." Ekip panosundaki her birim kendi konusunu
disaridan takip eder; boylece gundem sahibin okuduguyla sinirli kalmaz.

🔴 TUM 45 DEPARTMAN DEGIL. Sahip kararı: "oncelikli birkac departman, gunluk."
Sebebi olculmus bir risk: 45 birim x her gun = kimsenin okumadigi bir rapor
yigini. Odakli liste asagida; degistirmek icin KONULAR sozlugunu duzenle.

🔴 SIFIR MODEL CAGRISI. Arama, cekme, cikarma, alaka ve tekillestirme
jarvis/knowledge.py'nin mevcut deterministik hattiyla yapilir. Token
maliyeti yoktur ve saglayici kotasi dolsa bile calisir.

🔴 KNOWLEDGE.PY'NIN SOZLESMESI DEGISTIRILMEDI. KnowledgeItem'a 'departman'
alani EKLENMEDI; onun yerine bu betik kendi atif indeksini tutar. Ortak
bilgi deposu (KNOWLEDGE_LOG) yine ayni formatta yazilir, tekrar-kesif
korumasi ondan gelir.

Cikis: 0=calisti (yeni bulgu olsun olmasin) · 1=hata · 2=hicbir konu kosulamadi
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis import knowledge  # noqa: E402

ATIF = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "departman_arastirma.jsonl"

# --------------------------------------------------------------------------
# ONCELIKLI DEPARTMANLAR VE KONULARI
#
# Konu metni dogrudan arama sorgusudur. Her departmanin konusu KENDI ISINE
# bagli olmali; genel "kozmetik haberleri" gibi bir konu her birim icin ayni
# seyi getirir ve ekip tek sesli olur.
# --------------------------------------------------------------------------
# =========================================================================
# KONULAR -- HER BIRI TEK TEK OLCULDU (20.09.2026), TAHMIN EDILMEDI
#
# 🔴 OLCULMUS KURAL: KURUM/KANAL ADI + SOMUT BELGE TIPI -> sonuc gelir.
#                    SOYUT KAVRAM SORUSU -> SIFIR sonuc.
#   4 bulgu  "TITCK kozmetik urun bildirim duyuru"           (TITCK genelgeleri)
#   4 bulgu  "Hepsiburada kozmetik kategori komisyon orani"  (2026 komisyon tablosu)
#   2 bulgu  "dermokozmetik marka Instagram reklam kampanya Turkiye"
#   0 bulgu  "Meta reklam kreatif frekans yorgunluk esigi kac"
#   0 bulgu  "kozmetik markada fiyat seffafligi tuketici davranisi"
#
# 🔴 URUN/FIYAT DUZEYINDE RAKIP ISTIHBARATI BU HATTAN GELMIYOR. Olculdu:
#   0 bulgu  "Trendyol erkek mahrem bolge bakim kremi satici fiyat"
#   0 bulgu  "erkek bakim kremi marka Trendyol fiyat"
#   0 bulgu  "intim bolge bakim urunu marka Turkiye"
#   Sebep boru hatti degil KAYNAK: web aramasi pazaryeri liste sayfalarini
#   getirmiyor. Rakip FIYATI istiyorsak gereken sey baska bir yetenek --
#   pazaryerini dogrudan okuyan bir cekim. Buraya daha dar konu yazmak
#   bosuna; dar yazdikca sonuc sifirlaniyor.
#
# 🔴 GENIS KONU DA CALISMIYOR, BASKA SEBEPTEN: "kisisel bakim rakip kampanya
#   indirim Turkiye" 4 sonuc getirdi ama hepsi "Kisisel Bakim Nedir?" tipi
#   ansiklopedi yazisiydi. Genis soru genel cevap alir.
# =========================================================================
KONULAR: dict[str, tuple[str, ...]] = {
    "CREATIVE_STRAT": (
        # Olculdu: bu iki konu ilk kosuda 6 bulgu getirdi.
        "kozmetik reklam kreatifi hangi format daha iyi calisiyor",
        "instagram reels kozmetik marka reklam ornekleri",
    ),
    "BRAND": (
        # Olculdu: 5 bulgu.
        "kozmetik marka konumlandirma fiyat iletisimi",
        "dermokozmetik marka mesaji tuketici beklentisi Turkiye",
    ),
    "BIZDEV": (
        # Olculdu: 4 bulgu, iceriginde 2026 komisyon tablosu var.
        "Hepsiburada kozmetik kategori komisyon orani satici",
        "pazaryeri kozmetik kategori buyume Turkiye",
    ),
    "COMPETITOR_INT": (
        # Olculdu: 2 bulgu. Urun/fiyat sorgusu yerine REKLAM/KAMPANYA
        # duzeyi -- bu hattan gelebilen tek rakip sinyali bu.
        "dermokozmetik marka Instagram reklam kampanya Turkiye",
        "dermokozmetik rakip markalar yeni urun lansmani",
    ),
    "REGULATORY": (
        # Olculdu: 4 + 4 bulgu. En verimli iki konu; kurum adi tasiyorlar.
        "TITCK kozmetik urun bildirim duyuru",
        "kozmetik mevzuat yonetmelik degisikligi Turkiye",
    ),
    # ─── 22.09.2026'da eklendi: yeni kurulan departmanlar boş durmasın.
    # Sahip: "boştakiler kendi dallarıyla ilgili internetten araştırma
    # yapıp kendilerini geliştirsinler, daha iyi nasıl yapabilirler diye."
    # Konular "nedir" değil "NASIL YAPILIR" biçiminde: bu dosyanın kendi
    # ölçümü geniş soruların ansiklopedi yazısı getirdiğini söylüyor.
    "TASARIM": (
        "kozmetik urun katalog sayfasi tasarim kurallari nasil hazirlanir",
        "eczane raf materyali tasarim olcu baski standartlari",
    ),
    "PR": (
        "kozmetik marka basin bulteni nasil yazilir ornek",
        "marka itibar yonetimi sikayet yaniti nasil verilir",
    ),
    "YAYIN": (
        "kozmetik e-kitap icerik hazirlama saglik iddiasi sinirlari",
        "urun katalogu icindekiler yapisi nasil kurgulanir",
    ),
    "ECZANE_KANAL": (
        # Kurum/kanal adi tasiyor: bu dosyanin olcumune gore en verimli kalip.
        "eczane kanalinda dermokozmetik urun sunumu eczaci beklentisi",
        "eczane raf duzeni gorunurluk satis etkisi arastirma",
    ),
    "CONTENT": (
        # 🔴 Ilk kosuda 0 bulgu geldi ve ENGELLENMEDI -- gercekten yeni bir
        #    sey bulunamadi. Konu yine de birakildi: sifir sonuc da bir
        #    olcumdur ve konu degistirilirse neyin degistigi izlenebilsin.
        "sosyal medya icerik takvimi kozmetik marka",
        "instagram gonderi sikligi etkilesim arastirma",
    ),
}


def _simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _yaz(kayitlar: list[dict]) -> None:
    if not kayitlar:
        return
    ATIF.parent.mkdir(parents=True, exist_ok=True)
    with ATIF.open("a", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")


def main() -> int:
    try:
        from jarvis.adapter_factory import default_factory
        from jarvis.research_controller import ResearchController
        from jarvis.research_sources import WebSearchCrawlAdapter
    except Exception as hata:  # noqa: BLE001
        print(f"HATA: arastirma denetleyicisi yuklenemedi: {hata}", file=sys.stderr)
        return 1

    # 🔴 SEARXNG ADRESI ACIKCA VERILIR. Verilmezse adapter sessizce
    #    DuckDuckGo'nun anahtarsiz HTML ucuna duser ve bu sunucudan SIFIR
    #    sonuc doner -- arastirma "calisti" gorunur, hicbir sey bulmaz.
    #    Ayni tuzak sohbet tarafinda bir kez yasandi.
    searxng = os.environ.get("RESEARCH_SEARXNG_URL", "http://127.0.0.1:8888")
    try:
        factory = default_factory()
        factory.register(WebSearchCrawlAdapter(searxng_url=searxng))
        controller = ResearchController(factory)
    except Exception as hata:  # noqa: BLE001
        print(f"HATA: denetleyici kurulamadi: {hata}", file=sys.stderr)
        return 1

    bilinen = knowledge._known_hashes()
    simdi = _simdi()
    kosan = 0
    toplam_yeni = 0
    engellenen = 0
    kayitlar: list[dict] = []
    ozet_satirlari: list[str] = []

    # 🔴 "BULAMADI" ILE "BAKAMADI" AYRI SEYLERDIR.
    #    Ilk surumde her iki durum da "yeni bulgu yok" diye yazildi ve ILK
    #    kosuda 6 birimin 5'i oyle gorundu -- oysa ayni konu tek basina
    #    kosuldugunda 4 bulgu getiriyordu. Fark: art arda sorgu, arastirma
    #    denetleyicisinin devre kesicisini/kotasini tetikliyor. Bir arastirma
    #    hatti oldugunde panoyu yesil tutmak, olmamasindan kotudur.
    #    stop_reason bu ayrimi tasir; asagida ENGELLENDI olarak raporlanir.
    ENGELLEYEN = {"CIRCUIT_OPEN", "TIMEOUT", "RATE_LIMITED", "NO_ADAPTER",
                  "BUDGET_EXHAUSTED", "ERROR"}

    for departman, konular in KONULAR.items():
        dep_yeni = 0
        dep_hata = ""
        dep_engel: list[str] = []
        for konu in konular:
            try:
                kosum = knowledge.research_topic(
                    controller, konu, bilinen.get(konu, set()), now=simdi)
            except Exception as hata:  # noqa: BLE001
                dep_hata = str(hata)[:120]
                dep_engel.append("ISTISNA")
                continue
            kosan += 1
            if kosum.error:
                dep_hata = str(kosum.error)[:120]
            sebep = str(kosum.stop_reason or "")
            if sebep.upper() in ENGELLEYEN or kosum.error:
                dep_engel.append(sebep or "HATA")
            yeni = list(kosum.new_items or ())
            if yeni:
                # Ortak bilgi deposuna yaz -- tekrar-kesif korumasi oradan gelir.
                knowledge._append(yeni)
                bilinen.setdefault(konu, set()).update(i.content_hash for i in yeni)
            dep_yeni += len(yeni)
            # 🔴 Konular arasi bekleme: art arda sorgu devre kesiciyi aciyor.
            time.sleep(float(os.environ.get("ARASTIRMA_BEKLEME", "6")))
            for i in yeni:
                kayitlar.append({
                    "zaman": simdi,
                    "departman": departman,
                    "konu": konu,
                    "baslik": i.title,
                    "url": i.url,
                    "yayinci": i.publisher,
                    "kaynak_tipi": i.source_type,
                    "gorulme": i.observed_at,
                    "alaka": i.relevance,
                    # 🔴 Enjeksiyon isareti TASINIR, gizlenmez: disaridan gelen
                    #    metin bir yonerge tasiyorsa bunu okuyan bilmelidir.
                    "enjeksiyon": bool(getattr(i, "injection_detected", False)),
                    "ozet": (i.snippet or "")[:400],
                })
        toplam_yeni += dep_yeni
        if dep_engel:
            engellenen += 1
            durum = "🔴 ENGELLENDİ: " + ", ".join(sorted(set(dep_engel)))
        elif dep_yeni:
            durum = "yeni bulgu"
        else:
            durum = "aradı, yeni bir şey yok"
        ozet_satirlari.append(
            f"  {departman:16s} {len(konular)} konu · {dep_yeni} yeni bulgu · {durum}"
            + (f" · {dep_hata}" if dep_hata else ""))

    _yaz(kayitlar)

    print(f"departman arastirmasi · {len(KONULAR)} birim · {kosan} konu kosuldu "
          f"· {toplam_yeni} yeni bulgu")
    for s in ozet_satirlari:
        print(s)

    if engellenen:
        # 🔴 Bu satir stderr'e gider ki systemd/cron kaydinda ayirt edilsin.
        print(f"UYARI: {engellenen} birimin arastirmasi ENGELLENDI - bu birimler "
              f"icin 'yeni bilgi yok' DEGIL, 'BAKILAMADI' dogru ifadedir.",
              file=sys.stderr)
    if kosan == 0:
        # 🔴 "Hicbir konu kosulamadi" ile "yeni bulgu yok" AYRI SEYLERDIR.
        #    Ilkini basarili saymak, arastirma olu iken panoyu yesil tutardi.
        print("UYARI: hicbir konu kosulamadi - arastirma hatti calismiyor",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
