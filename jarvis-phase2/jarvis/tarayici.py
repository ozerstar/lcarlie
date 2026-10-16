# -*- coding: utf-8 -*-
"""TARAYICI İŞİ — Jarvis'in bilgisayardaki Chrome'a iş vermesi.

Sunucu headless; ChatGPT ve Claude'un web arayüzü bir masaüstü oturumu
ister. Bu yüzden iş SUNUCUDA yapılmaz: Jarvis kuyruğa yazar, PC-1'deki
worker SSH ile alır, kendi Chrome profilinde yapar, sonucu geri yükler.

## Neden bu modül ince

Kuyruğun bütün kuralları `migrations/037_tarayici_isi.sql` içindedir:
atomik kiralama, deneme tavanı, `INSAN_GEREKLI`'nin terminal oluşu,
merkezi anahtar. Burada o kuralların kopyası YOKTUR. Sınırları çağıran
tarafa bırakmak, sınır koymamakla aynı şeydir -- bu dosya silinse de
kuyruk aynı kurallarla çalışır.

Bu modülün tek kendine ait işi **mevzuat kapısı**dır:

    istek  -> compliance.review(istem)  -> BLOCKED ise kuyruğa HİÇ girmez
    sonuç  -> compliance.review(sonuç)  -> BLOCKED ise öneri BLOKLU işaretli

🔴 KAPI İKİ YÖNLÜ ÇALIŞIR ve bu bilinçli. Girişte durdurmak yetmez:
ChatGPT'ye temiz bir istem gidip "cilt lekelerini tedavi eder" diye bir
cümle geri gelebilir. Dönen metin de yayımlanabilir bir metindir.

🔴 BLOKLU SONUÇ SİLİNMEZ, GİZLENMEZ. Sahibin önüne "uyum kapısı
engelledi, metin şu" diye konur. Sessizce atmak, "üretilmedi" ile
"engellendi"yi aynı gösterirdi; bu projede o ayrımın kaybı daha önce
günler süren bir arıza gizledi (bkz. jarvis/whatsapp.py defteri).

## Yetki sınırı

Jarvis `ai_writer`'dır: iş EKLER, sonuç OKUR. İş ALAMAZ (o `tarayici_worker`),
`SUNULDU` yazamaz (o `human_approver` -- öneriyi insan otoritesi açar).
Bu ayrım veritabanındaki GRANT'lerle zorlanır, burada değil.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Any

from . import compliance
from .db_transport import run as db_run
from .transport import memory_host

HEDEFLER = ("chatgpt_image", "chatgpt_chat", "claude_chat")

# İstem sınırları. Üst sınır tablodaki CHECK ile aynı: iki yerde iki farklı
# sayı olması, bu projede yaşanmış bir hata sınıfı.
EN_AZ_ISTEM = 8
EN_COK_ISTEM = 8000

_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_IDEM_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,200}$")

# Sonuç dosyalarının sunucudaki kökü. Worker buraya yükler, panel buradan
# okur. Statik klasörün DIŞINDA: onaylanmamış üretim açık internete düşmesin
# (bkz. webconsole/app.py `_route_kreatif` aynı gerekçe).
CIKTI_KOK = Path(os.environ.get("TARAYICI_CIKTI_DIR", "/opt/lcarlie/tarayici-cikti"))

# Nabız bu süreden eskiyse rapor BAYAT sayılır.
#
# 🔴 BAYAT, WORKER'IN KAPALI OLDUĞUNU KANITLAMAZ. Ağ da takılmış olabilir,
#    SSH anahtarı da reddedilmiş olabilir. Panel bu yüzden teşhis yazmaz,
#    gözlem + soru yazar. (webconsole/sistem.py aynı sözlüğü kullanır.)
NABIZ_BAYAT_ESIGI_S = 300.0


class TarayiciHatasi(RuntimeError):
    """İstek kabul edilmedi. Sessizce yutulmaz."""


class UyumEngelledi(TarayiciHatasi):
    """İstem mevzuat kapısında bloklu bir iddia taşıyor. Kuyruğa girmedi."""

    def __init__(self, bulgular):
        self.bulgular = tuple(bulgular)
        ozet = "; ".join(f"{b.rule} <- {b.matched}" for b in self.bulgular[:4])
        super().__init__("UYUM_ENGELLEDI: " + ozet)


# --------------------------------------------------------------------------
# SQL taşıma
# --------------------------------------------------------------------------
def _psql(sql: str, rol: str, *, degiskenler: dict[str, str] | None = None,
          timeout_s: int = 15) -> list[str]:
    """Tek ifadeyi verilen rolle çalıştırır, satırları döndürür.

    🔴 DEĞER ASLA SQL METNİNE GÖMÜLMEZ. İstem metni kullanıcıdan/modelden
       gelir ve tırnak, satır sonu, ters eğik çizgi içerebilir. Değerler
       psql'in `-v ad=değer` + `:'ad'` mekanizmasıyla geçer: gerçek psql
       kendi güvenli literal alıntılamasını yapar, `db_transport`'un
       doğrudan-psycopg yolu ise aynı yer tutucuyu `psycopg.sql.Literal`
       ile değiştirir. İki yolda da string birleştirme YOK.

    🔴 `-f -` KULLANILIR, `-c` DEĞİL. Ölçüldü: `-c` ile verilen metinde
       psql değişken yerleştirmesi HİÇ yapılmaz; ifade sunucuya `:'ad'`
       diye gidip "syntax error at or near :" ile düşer. Değişkenler
       yalnız psql'in kendi çözümleyicisinden geçen girdide (stdin/dosya)
       açılır.

    🔴 ROL, DOĞRUDAN-PG KİPİNDE VERİLMEZ. `db_transport` yalnız
       `ai_reader` ve `human_approver` için `SET SESSION AUTHORIZATION`
       çevirisi yapar; başka bir rol görürse çağrıyı reddeder. Panel
       süreci (`jarvis_web`) bu kipte koşar ve zaten dar yetkilidir --
       rol ifadesi eklemek, paneli çalışamaz hâle getirirdi.
    """
    degiskenler = degiskenler or {}
    dogrudan = os.environ.get("JARVIS_MEMORY_TRANSPORT") == "direct-pg"
    if dogrudan and rol not in ("ai_reader", "human_approver"):
        tam = f"{sql}"
    else:
        tam = f"BEGIN; SET SESSION AUTHORIZATION {rol}; {sql} COMMIT;"

    temel = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
             "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n"]
    for ad, deger in degiskenler.items():
        temel += ["-v", f"{ad}={deger}"]
    temel += ["-f", "-"]

    host = memory_host()
    if host:
        # Uzaktan çalışırken tek bir kabuk satırı kurulur; her parça
        # shlex ile alıntılanır, çünkü değer satır sonu içerebilir.
        komut = ["ssh", host, " ".join(shlex.quote(p) for p in temel)]
    else:
        komut = temel

    sonuc = db_run(komut, input=tam, capture_output=True, text=True,
                   timeout=timeout_s, check=False)
    if sonuc.returncode:
        raise TarayiciHatasi((sonuc.stderr or "").strip()
                             or "tarayici kuyruk sorgusu basarisiz")
    return [s for s in (sonuc.stdout or "").splitlines() if s.strip()]


# --------------------------------------------------------------------------
# İŞ EKLEME — Jarvis ve ekip üyeleri buradan çağırır
# --------------------------------------------------------------------------
def enqueue_browser_task(prompt: str, target: str,
                         input_files: list[str] | None = None,
                         requested_by: str = "jarvis",
                         idempotency_key: str | None = None) -> dict[str, Any]:
    """Tarayıcı işini kuyruğa koyar. Mevzuat kapısını geçmeyen istem GİRMEZ.

    `input_files`, sunucudaki yolların listesidir (worker onları indirir).
    `idempotency_key` verilmezse istem + hedeften türetilir: aynı istek iki
    kez gelirse ikinci kez iş AÇILMAZ, var olanın kimliği döner.
    """
    istem = (prompt or "").strip()
    if target not in HEDEFLER:
        raise TarayiciHatasi("hedef su degerlerden biri olmali: %s"
                             % ", ".join(HEDEFLER))
    if len(istem) < EN_AZ_ISTEM:
        raise TarayiciHatasi("istem en az %d karakter olmali" % EN_AZ_ISTEM)
    if len(istem) > EN_COK_ISTEM:
        raise TarayiciHatasi("istem en fazla %d karakter olabilir" % EN_COK_ISTEM)

    # 🔴 MEVZUAT KAPISI — GİRİŞ. Bloklu bir iddia taşıyan istem kuyruğa hiç
    #    girmez. Kapıyı worker'a bırakmak, kapıyı PC'ye taşımak olurdu.
    inceleme = compliance.review(istem)
    if inceleme.blocked:
        raise UyumEngelledi(inceleme.blocked)

    dosyalar = _girdi_dogrula(input_files)

    if idempotency_key is None:
        from hashlib import sha256
        ozet = sha256(("%s|%s" % (target, istem)).encode("utf-8")).hexdigest()[:32]
        idempotency_key = "tarayici:%s:%s" % (target, ozet)
    if not _IDEM_RE.match(idempotency_key):
        raise TarayiciHatasi("idempotency_key [A-Za-z0-9_.:-]{8,200} olmali")

    satirlar = _psql(
        "SELECT core.tarayici_isi_ekle(:'isteyen', :'hedef', :'istem', "
        ":'idem', :'girdi'::jsonb);",
        "ai_writer",
        degiskenler={"isteyen": str(requested_by)[:80], "hedef": target,
                     "istem": istem, "idem": idempotency_key,
                     "girdi": json.dumps(dosyalar, ensure_ascii=False)},
    )
    if not satirlar:
        raise TarayiciHatasi("is eklendi ama kimlik donmedi")
    return {"is_id": int(satirlar[0]), "hedef": target,
            "idempotency_key": idempotency_key,
            "uyum": {"clean_tier1": inceleme.clean,
                     "verify": [b.to_dict() for b in inceleme.verify]}}


def _girdi_dogrula(input_files: list[str] | None) -> list[str]:
    """Girdi dosyası yollarını doğrular.

    🔴 Yalnız sunucudaki bilinen köklerin altı kabul edilir. Worker bu
       yolları SSH kapısından indirecek; keyfi bir yol kabul etmek, kapıyı
       "sunucudaki her dosyayı oku" hâline getirirdi.
    """
    if not input_files:
        return []
    if not isinstance(input_files, (list, tuple)):
        raise TarayiciHatasi("input_files bir liste olmali")
    izinli_kokler = [CIKTI_KOK,
                     Path("/opt/lcarlie/urun-ham"),
                     Path("/opt/lcarlie/cekim-arsivi"),
                     Path("/opt/lcarlie/gonderi-gorsel"),
                     Path("/opt/lcarlie/katalog-gorsel")]
    temiz: list[str] = []
    for yol in input_files:
        p = Path(str(yol))
        if not p.is_absolute():
            raise TarayiciHatasi("girdi dosyasi yolu mutlak olmali: %s" % yol)
        cozulen = Path(os.path.normpath(str(p)))
        if not any(kok == cozulen or kok in cozulen.parents for kok in izinli_kokler):
            raise TarayiciHatasi(
                "girdi dosyasi izinli koklerin disinda: %s" % cozulen)
        temiz.append(str(cozulen))
    if len(temiz) > 6:
        raise TarayiciHatasi("en fazla 6 girdi dosyasi")
    return temiz


# --------------------------------------------------------------------------
# OKUMA — döngü ve panel buradan okur
# --------------------------------------------------------------------------
def sayim() -> dict[str, Any]:
    """Her durumun adedi. Okunamazsa sıfır UYDURULMAZ."""
    try:
        satirlar = _psql("SELECT durum || '|' || adet FROM core.tarayici_sayim();",
                         "ai_reader")
    except TarayiciHatasi as hata:
        return {"durum": "OKUNAMADI", "sebep": str(hata)[:200], "sayilar": {}}
    sayilar = {}
    for satir in satirlar:
        ad, _, adet = satir.partition("|")
        sayilar[ad] = int(adet or 0)
    return {"durum": "OKUNDU", "sebep": None, "sayilar": sayilar}


def nabiz() -> dict[str, Any]:
    """Worker'ın son görülme hâli.

    🔴 Sözlük `webconsole/sistem.py` ile AYNI: TAZE | BAYAT | RAPOR_YOK.
       Yeni kelime uydurulmaz ve BAYAT "kapalı" demek DEĞİLDİR.
    """
    try:
        satirlar = _psql(
            "SELECT worker || '|' || yas_s FROM core.tarayici_nabiz_oku();",
            "ai_reader")
    except TarayiciHatasi as hata:
        return {"durum": "OKUNAMADI", "sebep": str(hata)[:200], "worker": None,
                "yas_s": None}
    if not satirlar:
        return {"durum": "RAPOR_YOK", "worker": None, "yas_s": None,
                "sebep": "worker hic nabiz atmamis; hic kurulmamis olabilir"}
    worker, _, yas = satirlar[0].partition("|")
    yas_s = float(yas or 0)
    if yas_s > NABIZ_BAYAT_ESIGI_S:
        return {"durum": "BAYAT", "worker": worker, "yas_s": yas_s,
                "sebep": ("son nabiz %.0f sn once geldi (esik %.0f sn). "
                          "Worker kapali olabilir, ag da takilmis olabilir."
                          % (yas_s, NABIZ_BAYAT_ESIGI_S))}
    return {"durum": "TAZE", "worker": worker, "yas_s": yas_s, "sebep": None}


def durum() -> dict[str, Any]:
    """Panelin İŞLER sekmesi için tek bakışta hâl + hatırlatma.

    `webconsole/isler.py` ile AYNI desen: hatırlatma cümlesi GÖZLEM + SORU
    olur, teşhis içermez.
    """
    s = sayim()
    n = nabiz()
    bekleyen = s["sayilar"].get("BEKLIYOR")
    hatirlatma = None
    if bekleyen and n["durum"] in ("BAYAT", "RAPOR_YOK", "OKUNAMADI"):
        hatirlatma = {
            "kod": "TARAYICI_NABIZ_ESKI",
            "bekleyen": bekleyen,
            "metin": ("Kuyrukta %d tarayıcı işi var. Bilgisayarın worker'ından "
                      "son haber eski, işler alınmamış olabilir. Worker'ı "
                      "açayım mı?" % bekleyen),
        }
    return {"sayilar": s["sayilar"], "sayim_durumu": s["durum"],
            "nabiz": n, "hatirlatma": hatirlatma,
            "cikti_kok": str(CIKTI_KOK)}


def sunulacaklar(limit: int = 20) -> list[dict[str, Any]]:
    """Sonucu gelmiş ama henüz sahibe sunulmamış işler."""
    satirlar = _psql(
        "SELECT json_build_object('is_id', is_id, 'hedef', hedef, "
        "'istem', istem, 'durum', durum, 'isteyen', isteyen, "
        "'sonuc_metin', sonuc_metin, 'sonuc_dosyalari', sonuc_dosyalari, "
        "'ekran_goruntusu', ekran_goruntusu, 'hata', hata, "
        "'deneme', deneme)::text "
        "FROM core.tarayici_sunulacak(:'limit'::integer);",
        "ai_reader", degiskenler={"limit": str(int(limit))})
    return [json.loads(s) for s in satirlar]


# --------------------------------------------------------------------------
# MEVZUAT KAPISI — ÇIKIŞ
# --------------------------------------------------------------------------
def sonuc_uyum(sonuc_metin: str | None) -> dict[str, Any]:
    """Dönen metni mevzuat kapısından geçirir.

    Sonuç `GECTI` ya da `BLOKLU` olur; ikisi de sahibe gösterilir. Metin
    yoksa (yalnız görsel üretildiyse) kapı işletilecek bir şey bulamaz ve
    bunu `METIN_YOK` diye söyler -- "geçti" demek YANLIŞ olurdu, çünkü
    denetlenen bir şey yok.
    """
    metin = (sonuc_metin or "").strip()
    if not metin:
        return {"uyum_durumu": "GECTI", "kapi": "METIN_YOK",
                "bloklu": [], "verify": [],
                "not": ("Denetlenecek metin yok (yalnız dosya üretildi). "
                        "Görsel yargı ve konumlandırma onayı insana aittir.")}
    inceleme = compliance.review(metin)
    return {
        "uyum_durumu": "BLOKLU" if inceleme.blocked else "GECTI",
        "kapi": "ISLETILDI",
        "bloklu": [b.to_dict() for b in inceleme.blocked],
        "verify": [b.to_dict() for b in inceleme.verify],
        "not": ("Kademe 1 mekanik taramadır. Bulgu çıkmaması yayın onayı "
                "değildir; görsel yargı ve konumlandırma onayı insana aittir."),
    }
