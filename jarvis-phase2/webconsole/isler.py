"""IŞLER sekmesi: görsel üretim kuyruğunu okumak ve ona iş eklemek.

Kuyruk zaten vardı (`/opt/lcarlie/gorsel-kuyruk`) ve PC-2'deki hakem onu
20 saniyede bir yokluyor; eksik olan tek şey sahibin oraya panelden iş
koyabilmesiydi.

## Dizin sözleşmesi (hakem bunu varsayar, değiştirilemez)

    bekleyen/   alınmayı bekleyen işler   -> hakem buraya bakar
    calisan/    o an üretilen iş
    biten/      başarıyla tamamlanan
    hata/       başarısız
    cikti/      üretilen görseller

🔴 **Yazma ATOMİK olmak zorunda.** Hakem `ls bekleyen/*.json` ile tarıyor ve
gördüğü dosyayı hemen okuyor. Doğrudan `bekleyen/` içine yazsaydık, hakem
yarım yazılmış bir JSON'u okuyup işi `hata/`ya atardı. Bu yüzden önce aynı
dosya sisteminde geçici ada yazılır, sonra `os.replace` ile yerine konur --
POSIX'te bu işlem atomiktir.

## Yokluğun sebebi ayrılır

Kuyruğun boş olması ile okunamaması aynı şey değildir:

    KUYRUK_YOK   dizin hiç yok        -> kurulum eksik
    BOS          dizin var, iş yok    -> gerçekten iş yok
    okunabilir   sayılar gerçek

Bir de "iş bekliyor ama PC-2 raporu bayat" hâli var: bu makinenin KAPALI
olduğunu KANITLAMAZ, yalnızca son raporun eskidiğini söyler. Panel de
tam olarak bunu yazar -- `pc2_durum` alanı `sistem.py`'nin sözlüğünü
aynen kullanır, yeni bir kelime uydurmaz.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

VARSAYILAN_KUYRUK = "/opt/lcarlie/gorsel-kuyruk"
ASAMALAR = ("bekleyen", "calisan", "biten", "hata")

# İstem uzunluk sınırları. Üst sınır keyfi değil: ComfyUI'ye giden metin
# CLIP kodlayıcıda ~77 jetonda kesilir, 2000 karakter zaten fazlasıyla üstü.
# Alt sınır, yanlışlıkla gönderilen boş formu reddetmek içindir.
EN_AZ_ISTEM = 8
EN_COK_ISTEM = 2000
EN_COK_ADET = 8

# 🔴 HAKEMIN ZORUNLU ALANLARI. PC-2'deki jarvis-hakem.ps1 is dosyasini
# okuyup dogrudan ComfyUI is akisina yerlestiriyor:
#   EmptyLatentImage <- genislik, yukseklik, adet
#   CLIPTextEncode   <- istem, negatif
#   KSampler         <- adim, cfg
# Eksik bir alan $null olarak gidiyor ve ComfyUI HTTP 400 donuyor.
# 24.09.2026'da olculdu: panelden eklenen ilk is tam bu yuzden hata/
# klasorune dustu. Varsayilanlar, calistigi KANITLANMIS isten alindi.
ZORUNLU_ALANLAR = ("id", "istem", "negatif", "adet",
                   "genislik", "yukseklik", "adim", "cfg")
VARSAYILAN_GENISLIK = 1024
VARSAYILAN_YUKSEKLIK = 1024
VARSAYILAN_ADIM = 28
VARSAYILAN_CFG = 8.5


class IsHatasi(ValueError):
    """Panelden gelen istek kabul edilmedi. Sessizce yutulmaz."""


def _kok(kuyruk_dir: str | Path | None = None) -> Path:
    return Path(kuyruk_dir or os.environ.get("LCARLIE_KUYRUK", VARSAYILAN_KUYRUK))


def _sayim(kok: Path) -> dict:
    sayilar = {}
    for asama in ASAMALAR:
        d = kok / asama
        try:
            sayilar[asama] = len([p for p in d.iterdir() if p.suffix == ".json"])
        except OSError:
            sayilar[asama] = None  # okunamadi: sifir DEGIL
    return sayilar


def _son_isler(kok: Path, limit: int = 12) -> list[dict]:
    """En yeni işler, hangi aşamada olduklarıyla. Bozuk dosya atlanmaz --
    'BOZUK' olarak gösterilir; sessizce kaybolan iş, olmayan işten kötüdür."""
    bulunan: list[tuple[float, dict]] = []
    for asama in ASAMALAR:
        d = kok / asama
        try:
            dosyalar = [p for p in d.iterdir() if p.suffix == ".json"]
        except OSError:
            continue
        for p in dosyalar:
            try:
                zaman = p.stat().st_mtime
            except OSError:
                continue
            try:
                kayit = json.loads(p.read_text(encoding="utf-8"))
                ozet = {
                    "id": kayit.get("id") or p.stem,
                    "istem": (kayit.get("istem") or "")[:160],
                    "olusturuldu": kayit.get("olusturuldu"),
                    "isteyen": kayit.get("isteyen"),
                }
            except (OSError, json.JSONDecodeError):
                ozet = {"id": p.stem, "istem": None, "olusturuldu": None,
                        "isteyen": None, "bozuk": True}
            ozet["asama"] = asama
            bulunan.append((zaman, ozet))
    bulunan.sort(key=lambda t: t[0], reverse=True)
    return [o for _, o in bulunan[:limit]]


def durum(kuyruk_dir: str | Path | None = None,
          pc2_durum: str | None = None) -> dict:
    """Kuyruğun hâli + 'PC-2'yi açman gerekebilir' hatırlatması.

    `pc2_durum` sistem.py'nin ürettiği değerdir (TAZE / BAYAT / RAPOR_YOK).
    Burada yeniden hesaplanmaz; iki yerde iki farklı tanım olması, bu
    projede daha önce yaşanmış bir hata sınıfı.
    """
    kok = _kok(kuyruk_dir)
    if not kok.is_dir():
        return {"durum": "KUYRUK_YOK", "yol": str(kok), "sayilar": {},
                "isler": [], "hatirlatma": None}

    sayilar = _sayim(kok)
    bekleyen = sayilar.get("bekleyen")

    hatirlatma = None
    if bekleyen and pc2_durum in ("BAYAT", "RAPOR_YOK"):
        # 🔴 "KAPALI" demiyoruz. Rapor eskimiş olabilir çünkü makine kapalı,
        # ama ağ da takılmış olabilir. Sahibe karar verdirilir, teşhis
        # uydurulmaz.
        hatirlatma = {
            "kod": "PC2_RAPOR_ESKI",
            "bekleyen": bekleyen,
            # Cumle GOZLEM + SORU. Teshis yok: "makine kapali" demiyoruz,
            # cunku bilmiyoruz -- rapor gecikmesinin sebebi ag da olabilir.
            "metin": ("Kuyrukta %d iş var. PC-2'den son rapor eski, "
                      "işler alınmamış olabilir. PC-2'yi açayım mı?"
                      % bekleyen),
        }

    return {
        "durum": "BOS" if not bekleyen else "IS_VAR",
        "yol": str(kok),
        "sayilar": sayilar,
        "isler": _son_isler(kok),
        "hatirlatma": hatirlatma,
    }


def _kimlik() -> str:
    return "is-%s-%d" % (time.strftime("%Y%m%dT%H%M%S"), os.getpid() % 100000)


def is_ekle(kuyruk_dir: str | Path | None, istem: str,
            negatif: str = "", adet: int = 1, isteyen: str = "panel") -> dict:
    """Kuyruğa tek iş koyar. Doğrulamayı geçemeyen istek KABUL EDİLMEZ."""
    istem = (istem or "").strip()
    if len(istem) < EN_AZ_ISTEM:
        raise IsHatasi("istem en az %d karakter olmali" % EN_AZ_ISTEM)
    if len(istem) > EN_COK_ISTEM:
        raise IsHatasi("istem en fazla %d karakter olabilir" % EN_COK_ISTEM)
    try:
        adet = int(adet)
    except (TypeError, ValueError):
        raise IsHatasi("adet sayi olmali") from None
    if not 1 <= adet <= EN_COK_ADET:
        raise IsHatasi("adet 1 ile %d arasinda olmali" % EN_COK_ADET)

    kok = _kok(kuyruk_dir)
    hedef_dizin = kok / "bekleyen"
    try:
        hedef_dizin.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IsHatasi("kuyruk dizini olusturulamadi: %s" % exc) from None

    kayit = {
        "id": _kimlik(),
        "olusturuldu": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "isteyen": str(isteyen)[:60],
        "istem": istem,
        "negatif": (negatif or "").strip()[:EN_COK_ISTEM],
        "adet": adet,
        "genislik": VARSAYILAN_GENISLIK,
        "yukseklik": VARSAYILAN_YUKSEKLIK,
        "adim": VARSAYILAN_ADIM,
        "cfg": VARSAYILAN_CFG,
    }
    eksik = [a for a in ZORUNLU_ALANLAR if a not in kayit]
    if eksik:
        # Kuyruga eksik is KOYULMAZ. Hakem onu alir, ComfyUI 400 doner ve
        # is hata/ klasorune duser -- sahip de "neden uretilmedi" diye
        # bakmak zorunda kalir. Burada durmak daha ucuz.
        raise IsHatasi("is kaydinda zorunlu alan eksik: " + ", ".join(eksik))
    govde = json.dumps(kayit, ensure_ascii=False, indent=2)

    # ATOMİK YAZMA: hakem bekleyen/ dizinini tarayip gordugu dosyayi hemen
    # okudugu icin yarim dosya = hata klasorune dusen is demektir.
    # noqa gerekcesi: atomik yazim kalibi. Dosya blok bitince DEGIL,
    # fsync sonrasi os.replace ile kapanip yerine tasiniyor; asagidaki
    # try/except onu kapatiyor ve hata halinde siliyor.
    gecici = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="w", encoding="utf-8", dir=str(hedef_dizin),
        prefix=".yaziliyor-", suffix=".tmp", delete=False)
    try:
        with gecici as f:
            f.write(govde)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici.name, str(hedef_dizin / (kayit["id"] + ".json")))
    except OSError as exc:
        try:
            os.unlink(gecici.name)
        except OSError:
            pass
        raise IsHatasi("is yazilamadi: %s" % exc) from None

    return kayit
