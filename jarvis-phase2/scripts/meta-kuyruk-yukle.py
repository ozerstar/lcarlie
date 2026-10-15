#!/usr/bin/env python3
"""Webhook kuyruğunu `lcarlie` şemasına aktarır ve reklam→ürün'ü bağlar.

ZİNCİRDEKİ YERİ
    Meta → /webhook/meta → gelen.jsonl  →  ** BU BETİK **  →  lcarlie.mesaj
                                                           →  konusma.notlar.ad_id

Webhook bilerek veritabanına yazmıyor (Meta gecikmede olayı tekrarlıyor ve
`jarvis-web` DB'ye yalnız okuma kimliğiyle bakıyor). Aradaki boşluğu bu
betik kapatıyor.

🔴 TEKRAR ÇALIŞTIRMAK GÜVENLİ
`UNIQUE (kanal,harici_id)` ve `UNIQUE (konusma_id,harici_id)` kısıtları var;
aynı Meta mesaj kimliği ikinci kez eklenmez. Kuyruk dosyası işlendikten
sonra ARŞİVLENİR, silinmez -- bir yükleme hatası olayı kaybettirmesin.

🔴 KENDİ MESAJIMIZIN YANKISI MÜŞTERİ SAYILMAZ
`is_echo` olayları `gonderen='isletme'` olarak yazılır. Sayılmazsa kendi
cevabımıza cevap üretiriz.

🔴 ÜRÜN TAHMİN EDİLMEZ
`ad_id` yoksa ya da `mart.reklam_urun`'de karşılığı yoksa ürün alanı BOŞ
kalır. Boş bırakmak, yanlış ürünün fiyatını göndermekten iyidir.

Çalıştırma:
    venv/bin/python scripts/meta-kuyruk-yukle.py [--kuru]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR",
                                "/opt/lcarlie/jarvis-phase2/state"))
KUYRUK = STATE_DIR / "meta_webhook" / "gelen.jsonl"
ARSIV = STATE_DIR / "meta_webhook" / "arsiv"

PSQL = ["docker", "exec", "-i", "lcarlie-postgres",
        "psql", "-U", "n8n", "-d", "n8n", "-tA", "-v", "ON_ERROR_STOP=1"]


def _psql(sql: str) -> list[str]:
    sonuc = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise SystemExit(f"psql hatası: {sonuc.stderr[:500]}")
    return [s for s in sonuc.stdout.split("\n") if s.strip()]


def _tirnak(deger) -> str:
    if deger is None or deger == "":
        return "NULL"
    return "'" + str(deger).replace("'", "''") + "'"


def olaylari_oku(kuyruk: Path) -> list[dict]:
    if not kuyruk.is_file():
        return []
    olaylar = []
    for satir in kuyruk.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir:
            continue
        try:
            olaylar.append(json.loads(satir))
        except json.JSONDecodeError:
            # Yarıda kalmış son satır: atlanır, dosya arşivde kalır.
            sys.stderr.write("bozuk satır atlandı\n")
    return olaylar


def _zaman(olay: dict) -> str:
    ms = olay.get("zaman_ms")
    if isinstance(ms, (int, float)) and ms > 0:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    return datetime.now(tz=timezone.utc).isoformat()


def yukle(olaylar: list[dict], kuru: bool) -> dict[str, int]:
    sayac = {"konusma": 0, "mesaj": 0, "urunlu": 0, "yanki": 0, "atlanan": 0,
             "zaten_vardi": 0}
    for olay in olaylar:
        kanal = olay.get("kanal") or "messenger"
        if kanal not in {"messenger", "whatsapp"}:
            sayac["atlanan"] += 1
            continue
        psid = (olay.get("gonderen_id") or "").strip()
        mesaj_id = (olay.get("mesaj_id") or "").strip()
        metin = olay.get("metin") or ""
        yanki = bool(olay.get("yanki"))
        if not psid or not mesaj_id:
            # harici_id NOT NULL: kimliksiz olay yazılamaz, sessizce de
            # atlanmaz -- sayılır ve raporlanır.
            sayac["atlanan"] += 1
            continue

        # Yankıda konuşmanın karşı tarafı ALICIdır; gönderen biziz.
        konusma_ref = (olay.get("alici_id") if yanki else psid) or psid
        ad_id = olay.get("ad_id")
        gonderen = "isletme" if yanki else "musteri"
        # 🔴 YON SOZLESMESI: "gelen"/"giden". Bu betik "in"/"out" yaziyordu
        # ve veritabaninda iki ayri sozlesme olusmustu: Meta konusma ice
        # aktaricisi 3.300 satiri "gelen"/"giden", bu betik ise yeni
        # gelenleri "in"/"out" yaziyordu. Sonuc sessizdi ve kotuydu --
        # siniflandirici `yon='gelen'` ariyor, panel cevapsizi `yon='gelen'`
        # sayiyor; webhook'tan gelen her WhatsApp mesaji IKISINE DE
        # gorunmuyordu. 15.10.2026'da ilk gercek WhatsApp mesaji geldiginde
        # uctan uca testle yakalandi.
        yon = "giden" if yanki else "gelen"
        if yanki:
            sayac["yanki"] += 1

        if kuru:
            sayac["mesaj"] += 1
            if ad_id:
                sayac["urunlu"] += 1
            continue

        # 🔴 REKLAM REFERANSI AYNI INSERT'İN İÇİNDE YAZILIR.
        # İlk hâli ayrı bir CTE'de UPDATE ediyordu ve SESSİZCE HİÇBİR ŞEY
        # YAPMIYORDU: PostgreSQL'de aynı ifadedeki veri değiştiren CTE'ler
        # tek anlık görüntüyle çalışır, biri diğerinin yazdığı satırı
        # GÖREMEZ. Mesajlar yazılıyor, ad_id düşüyordu -- yani ürün
        # atamasının tamamı sessizce ölüydü. Ölçülerek yakalandı.
        #
        # Referans yalnız BİR KEZ yazılır (ilk temas): sonraki mesajlar
        # ilk geldiği reklamı ezmemeli.
        ad_json = (
            f"jsonb_build_object('ad_id', {_tirnak(ad_id)}, 'urun', "
            f"(SELECT urun_adi FROM mart.reklam_urun WHERE ad_id = {_tirnak(ad_id)}))"
            if ad_id else "'{}'::jsonb"
        )
        sql = f"""
        WITH k AS (
          INSERT INTO lcarlie.konusma (kanal, harici_id, musteri_ref, notlar)
          VALUES ({_tirnak(kanal)}, {_tirnak(konusma_ref)}, {_tirnak(konusma_ref)},
                  jsonb_build_object('kaynak','webhook') || {ad_json})
          ON CONFLICT (kanal, harici_id) DO UPDATE
            SET notlar = CASE WHEN lcarlie.konusma.notlar ? 'ad_id'
                              THEN lcarlie.konusma.notlar
                              ELSE lcarlie.konusma.notlar || excluded.notlar END,
                guncelleme = now()
          RETURNING id
        )
        INSERT INTO lcarlie.mesaj (konusma_id, harici_id, zaman, yon, gonderen,
                                   metin, ek)
        SELECT (SELECT id FROM k), {_tirnak(mesaj_id)}, {_tirnak(_zaman(olay))},
               {_tirnak(yon)}, {_tirnak(gonderen)}, {_tirnak(metin)},
               jsonb_build_object('ad_id', {_tirnak(ad_id)})
        ON CONFLICT (konusma_id, harici_id) DO NOTHING
        RETURNING 'yazildi';
        """
        cikti = _psql(sql)
        # 🔴 "ÇIKTI VAR" = "YAZILDI" DEĞİL.
        # psql `-tA` ile bile komut etiketini basıyor: çakışan bir INSERT
        # `INSERT 0 0` döndürüyor ve bu BOŞ OLMAYAN bir satır. İlk hâli
        # buna bakıp her tekrar çalıştırmada "4 mesaj yazıldı" diyordu --
        # oysa sıfır satır yazılmıştı. Kopya oluşmuyordu (kısıtlar tuttu)
        # ama RAPOR YALAN SÖYLÜYORDU; bu projede aynı sınıf hata daha önce
        # bir cron'un iki gün ölü kalmasını gizledi.
        if any(s.strip() == "yazildi" for s in cikti):
            sayac["mesaj"] += 1
            if ad_id:
                sayac["urunlu"] += 1
        else:
            sayac["zaten_vardi"] += 1
    return sayac


def bekleyen_kuyrugu_al() -> list[Path]:
    ARSIV.mkdir(parents=True, exist_ok=True)
    with (KUYRUK.parent / ".queue.lock").open("a") as kilit:
        fcntl.flock(kilit, fcntl.LOCK_EX)
        if KUYRUK.is_file():
            hedef = ARSIV / f"gelen-{time.time_ns()}.pending"
            KUYRUK.replace(hedef)
    return sorted(ARSIV.glob("gelen-*.pending"))


def main() -> None:
    kuru = "--kuru" in sys.argv
    if kuru:
        dosyalar = [KUYRUK, *sorted(ARSIV.glob("gelen-*.pending"))]
    else:
        dosyalar = bekleyen_kuyrugu_al()
    for dosya in dosyalar:
        olaylar = olaylari_oku(dosya)
        if not olaylar:
            continue
        print(f"kuyrukta {len(olaylar)} olay")
        sayac = yukle(olaylar, kuru)
        print(f"yazılan mesaj: {sayac['mesaj']} · zaten vardı: {sayac['zaten_vardi']} "
              f"· reklam referanslı: {sayac['urunlu']} · kendi yankımız: {sayac['yanki']} "
              f"· kimliksiz atlanan: {sayac['atlanan']}")
        if not kuru:
            hedef = dosya.with_suffix(".jsonl")
            dosya.replace(hedef)
            os.chmod(hedef, 0o640)
            print(f"kuyruk arşivlendi → {hedef}")
    if kuru:
        print("--kuru: veritabanına yazılmadı, kuyruk arşivlenmedi")


if __name__ == "__main__":
    main()
