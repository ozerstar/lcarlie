"""Kademe telemetrisi: her model denemesi tek satir JSONL olarak yazilir.

NEDEN VAR. Model zinciri gpu -> local -> external calisiyordu ama HANGI
kademenin cevap verdigi hicbir yere yazilmiyordu. 24.09.2026'da olculdu:
sunucu yeniden baslayinca GPU ucunun ters tuneli dustu ve sistem dokuz kat
yavas kademede (7,45 jeton/sn) kosmaya devam etti -- panel de, alarm da bunu
goremedi, cunku kimse kaydetmiyordu. LiteLLM belgelerindeki ilke aynen
gecerli: yedek devreye girdiginde KAYDET, yoksa gercek ariza sessiz kalir.

KAPSAM. Bu modul yalniz yazar. Hicbir karar vermez, hicbir istegi engellemez,
hicbir seyi yeniden dener. Yazma hatasi cagirani ASLA etkilemez -- telemetri
kaybi, cevabin kaybindan iyidir.

BAGIMLILIK YOK. Uretim makinesinde psycopg kurulu degil (bkz.
scripts/psql_session.py basligi), o yuzden Postgres'e dogrudan yazilmaz.
Satirlar state/kademe.jsonl'e eklenir ve alan adlari core.ai_provider_attempt
sutunlariyla birebir eslesecek sekilde secilmistir, boylece sonradan yazilacak
bir aktarici satiri doneme donmeden INSERT edebilir.

DURUM AYRIMI. "sonuc" alani uc hali ayirir ve bunlar birbirinin yerine
gecmez:
    BASARILI  cevabi bu kademe uretti
    HATA      kademe denendi ve dustu (gerekce = istisna sinifi)
    ATLANDI   kademe hic denenmedi, cunku hazir degildi (gerekce = durum)
"ATLANDI" ile "HATA" ayni sey degildir: birincisi makine kapali, ikincisi
makine acik ama cevap veremedi. Karistirmak, yanlis teshise goturur.
"""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import os
import time
from pathlib import Path

VARSAYILAN_DURUM_DIZINI = "/opt/lcarlie/jarvis-phase2/state"
VARSAYILAN_YOL = VARSAYILAN_DURUM_DIZINI + "/kademe.jsonl"

SONUC_BASARILI = "BASARILI"
SONUC_HATA = "HATA"
SONUC_ATLANDI = "ATLANDI"
SONUC_ZINCIR_TUKENDI = "ZINCIR_TUKENDI"


# 🔴 Zaman damgasi SANIYE cozunurlugunde. Ayni saniyede dort cagri
# olabiliyor ve alanlari ayni oldugunda satirlar birbirinden AYIRT
# EDILEMIYORDU. Olculdu 24.09.2026: 350 kaydin 86'si (%25) aktarimda tek
# satira indi -- "kac kez yedege dustuk" sorusunun cevabi eksik cikardi.
#
# Sira, surec kimligi + artan sayac. Zaman damgasini milisaniyeye cevirmek
# yerine bu secildi: bicim degisikligi paneli ve mevcut kayitlari etkilerdi,
# ayrica iki cagri ayni milisaniyeye de dusebilir. Sira dosyaya YAZILDIGI
# icin ayni dosyayi iki kez aktarmak hala guvenli -- kimlik degismez.
_SIRA = itertools.count(1)


def _yol() -> Path:
    """Gunluk dosyasinin yolu. Her cagride yeniden okunur.

    🔴 VARSAYILAN, JARVIS_STATE_DIR'DAN TURETILIR. Onceki surum mutlak bir
    yol kullaniyordu ve bu projede daha once yasanmis bir hatayi aynen
    tekrar etti: testler URETIM dosyasina yazdi. Olculdu 24.09.2026 --
    tek bir test kosusu uretim gunlugune 19-20 satir ekledi ve o satirlar
    "zincir tukendi" gibi gorunup gercek olcumu kirletti. Ayni sinif hata
    20.09.2026'da sohbet dokumunde yasanmisti (369 satir test fixture'i
    uretim dokumune karisti).

    Proje zaten bir izolasyon kurali kurmus: test modulleri ice aktarmadan
    once JARVIS_STATE_DIR'i gecici klasore alir. Bu modul ayri bir
    degisken kullandigi icin o korumanin DISINDA kaliyordu. Yeni bir
    mekanizma eklemek yerine mevcut kurala baglanmasi dogrusu.

    JARVIS_KADEME_LOG yine de acik bir gecersiz kilma olarak kalir:
    dogrudan bu dosyayi sinayan testler onu kullanir.
    """
    acik = os.environ.get("JARVIS_KADEME_LOG")
    if acik:
        return Path(acik)
    durum = os.environ.get("JARVIS_STATE_DIR", VARSAYILAN_DURUM_DIZINI)
    return Path(durum) / "kademe.jsonl"


def kaydet(**alanlar) -> None:
    """Tek satir ekle. Hicbir kosulda istisna firlatmaz."""
    try:
        satir = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "sira": "%d-%d" % (os.getpid(), next(_SIRA)), **alanlar}
        yol = _yol()
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(satir, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 - telemetri cagirani asla dusuremez
        pass


def son_kayitlar(limit: int = 50) -> list[dict]:
    """Son N satiri yeniden eskiye dogru dondur. Dosya yoksa bos liste."""
    try:
        yol = _yol()
        if not yol.exists():
            return []
        with yol.open("r", encoding="utf-8") as dosya:
            satirlar = dosya.readlines()[-limit:]
    except OSError:
        return []
    kayitlar = []
    for satir in reversed(satirlar):
        satir = satir.strip()
        if not satir:
            continue
        try:
            kayitlar.append(json.loads(satir))
        except json.JSONDecodeError:
            continue
    return kayitlar


def ozet(kayitlar: list[dict]) -> dict:
    """Kademe dagilimi. Sayi uretir, yorum uretmez.

    "bilinmiyor" ayri bir kovadir: kaydi olmayan bir kademeyi "calismadi"
    diye raporlamak, olculmemis olani olculmus gibi gostermek olurdu.
    """
    dagilim: dict[str, dict[str, int]] = {}
    gecikmeler: dict[str, list[float]] = {}
    for kayit in kayitlar:
        uc = str(kayit.get("uc") or "bilinmiyor")
        sonuc = str(kayit.get("sonuc") or "bilinmiyor")
        dagilim.setdefault(uc, {})
        dagilim[uc][sonuc] = dagilim[uc].get(sonuc, 0) + 1
        gecikme = kayit.get("gecikme_ms")
        if sonuc == SONUC_BASARILI and isinstance(gecikme, (int, float)):
            gecikmeler.setdefault(uc, []).append(float(gecikme))
    ortalama = {uc: round(sum(v) / len(v), 1) for uc, v in gecikmeler.items() if v}
    return {"toplam": len(kayitlar), "dagilim": dagilim,
            "ortalama_gecikme_ms": ortalama}


# ---------------------------------------------------------------------------
# POSTGRES AKTARIMI
#
# 🔴 Hedef tablo core.ai_provider_attempt DEGIL, core.kademe_denemesi.
# Sebep olculdu: o tabloyu mart.ai_provider_score okuyor ve "deneme" sayisi
# ile basari oranini ondan cikariyor. Bizim ATLANDI satirlarimiz HIC
# DENENMEMIS kademeleri anlatir; oraya yazmak, kapali duran bir makineyi
# "basarisiz saglayici" gibi gosterip mevcut yonlendirme skorlarini bozardi.
#
# Aktarim ESIRGEYICI degil FIKIRSIZ olmali: burasi satiri donusturur, ne
# gonderilecegine karar vermez. Ayiklama yapsaydi, aktarilmayan satirin
# sebebini kimse goremezdi.
# ---------------------------------------------------------------------------

AKTARIM_SUTUNLARI = ("ts", "uc", "kademe", "model", "sonuc", "gecikme_ms",
                     "gerekce", "deneme", "escalate", "is_anahtari", "kayit_hash")


def satir_hash(kayit: dict) -> str:
    """Satirin kimligi. Ayni satir iki kez aktarilmasin diye.

    Filigran/ofset tutmak yerine icerik hash'i secildi: dosya donduruldugunde
    ya da aktarim yarida kaldiginda ofset yaniltir, hash yaniltmaz. Tekrar
    calistirmak her kosulda guvenlidir.
    """
    ham = json.dumps(kayit, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:40]


def aktarim_csv(kayitlar: list[dict]) -> str:
    """Kayitlari COPY ... FROM STDIN (FORMAT csv) icin metne cevirir.

    csv modulu kullanilir: model adinda tirnak, gerekcede virgul olabilir ve
    elle kacis yazmak bu projede daha once bozulmus bir yontemdir.
    """
    tampon = io.StringIO()
    yazici = csv.writer(tampon, lineterminator="\n")
    for kayit in kayitlar:
        if not isinstance(kayit, dict) or not kayit.get("ts") or not kayit.get("sonuc"):
            # ts ve sonuc olmadan satirin anlami yok; NOT NULL'a carpip
            # butun aktarimi dusururdu.
            continue
        yazici.writerow([
            kayit.get("ts"),
            kayit.get("uc") or "-",
            kayit.get("kademe") if kayit.get("kademe") is not None else "",
            kayit.get("model") if kayit.get("model") is not None else "",
            kayit.get("sonuc"),
            kayit.get("gecikme_ms") if kayit.get("gecikme_ms") is not None else "",
            kayit.get("gerekce") if kayit.get("gerekce") is not None else "",
            kayit.get("deneme") if kayit.get("deneme") is not None else "",
            "true" if kayit.get("escalate") else "false",
            kayit.get("is_anahtari") if kayit.get("is_anahtari") is not None else "",
            satir_hash(kayit),
        ])
    return tampon.getvalue()


def tum_kayitlar(yol: "Path | None" = None) -> list[dict]:
    """Gunlugun TAMAMI, eskiden yeniye. Bozuk satir atlanir ama sayilir."""
    hedef = Path(yol) if yol else _yol()
    if not hedef.exists():
        return []
    kayitlar = []
    try:
        with hedef.open("r", encoding="utf-8") as dosya:
            for satir in dosya:
                satir = satir.strip()
                if not satir:
                    continue
                try:
                    kayitlar.append(json.loads(satir))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return kayitlar
