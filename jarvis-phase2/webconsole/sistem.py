"""SISTEM sekmesi: uc makinenin kaynak kullanimi + kaynak politikasi.

Neden ayri dosya: app.py 2600 satir ve buradaki isin iki yani var --
(1) OLCUM okumak, (2) POLITIKA yazmak. Ikisi de app.py'nin rota
dagitimindan bagimsiz test edilebilmeli.

## Olcum nereden geliyor

| makine | yol | kim yaziyor |
|---|---|---|
| sunucu | app.py `_host_metrics()` (/proc/stat, /proc/meminfo, statvfs) | istegin kendisi, anlik |
| PC-1   | `state/hosts/pc1.json` | PC-1'deki `jarvis-metrik.ps1`, dakikada bir SSH ile iter |
| PC-2   | `state/hosts/pc2.json` | PC-2'deki ayni betik |

PC'ler NAT arkasinda; sunucu onlara baglanamaz. Bu yuzden yon TERS:
PC iter, sunucu okur. Iki PC'nin sunucuya zaten kalici SSH tuneli var,
yeni port veya guvenlik duvari kurali ACILMADI.

## Yoklugun sebebi ayrilir

Bir PC'nin verisi olmamasinin iki ayri sebebi vardir ve bunlari ayni
cumleye cevirmek bu projede tekrar eden bir kok hatadir:

  RAPOR_YOK  dosya hic yok        -> toplayici hic kurulmamis/hic kosmamis
  BAYAT      dosya var ama eski   -> PC kapali ya da itme basarisiz
  TAZE       dosya var ve yeni    -> sayilar gercek

"BAYAT" bir makinenin KAPALI oldugunu KANITLAMAZ; yalnizca son raporun
eskidigini soyler. Panel de tam olarak bunu yazar, fazlasini degil.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

# Bir rapor bu sureden eskiyse BAYAT sayilir. Toplayici 60 sn'de bir
# ittigi icin 180 sn uc kacirilmis tura tolerans demektir -- aglar
# takilir, tek gecikme alarm uretmemeli.
BAYAT_ESIGI_S = 180

MAKINE_ADLARI = {
    "pc1": "PC-1",
    "pc2": "PC-2",
}


# ---------------------------------------------------------------- olcum

def _hosts_dir(state_dir: Path) -> Path:
    return Path(state_dir) / "hosts"


def _rapor_oku(state_dir: Path, anahtar: str) -> dict:
    """Bir PC'nin son raporunu, tazelik hukmuyle birlikte dondurur."""
    yol = _hosts_dir(state_dir) / (anahtar + ".json")
    ad = MAKINE_ADLARI.get(anahtar, anahtar)
    if not yol.exists():
        return {"makine": ad, "durum": "RAPOR_YOK",
                "sebep": yol.name + " yok -- toplayici hic kosmamis",
                "veri": None, "yas_s": None}
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as hata:
        return {"makine": ad, "durum": "OKUNAMADI",
                "sebep": yol.name + " okunamadi: " + str(hata),
                "veri": None, "yas_s": None}
    if not isinstance(ham, dict):
        return {"makine": ad, "durum": "OKUNAMADI",
                "sebep": yol.name + " bir nesne degil",
                "veri": None, "yas_s": None}

    # Yasi dosyanin kendi zaman damgasindan degil, DOSYA mtime'indan
    # olcuyoruz: PC'nin saati kaymis olabilir, sunucununki referans.
    try:
        yas = max(0, int(time.time() - yol.stat().st_mtime))
    except OSError:
        yas = None

    if yas is not None and yas > BAYAT_ESIGI_S:
        return {"makine": ad, "durum": "BAYAT",
                "sebep": ("son rapor " + str(yas) + " sn once geldi (esik "
                          + str(BAYAT_ESIGI_S) + " sn). PC kapali olabilir ya da "
                          "itme basarisiz -- bu veri KAPALI oldugunu kanitlamaz."),
                "veri": ham, "yas_s": yas}
    return {"makine": ad, "durum": "TAZE", "sebep": None,
            "veri": ham, "yas_s": yas}


# ------------------------------------------------- sunucunun GERCEK RAM'i

# 🔴 24.09.2026 olculdu: sunucu VMware uzerinde ve `vmw_balloon` surucusu
# bellegi ana makineye IADE ETMIS. `free` "23,5 GB'in 21,7'si kullanimda"
# diyor ama o kullanimin 15,25 GB'i balon sayfalari -- bizim stack'te
# degil. Uygulamalarin gercek kullanimi 7,2 GB.
#
# Panelde ham `free` yuzdesini gostermek, sahibi "sunucunun RAM'i bitti"
# diye yanlis bir karara goturur. Ust politika "once sunucu RAM'i"
# dedigi icin bu sayinin dogru olmasi ayrica onemli: sunucunun gercek
# bosluu ~0,8 GB, 2,3 GB degil.
#
# Balon okunamazsa None doner ve panel ham degeri "duzeltilmemis" notuyla
# gosterir. Tahmin uretilmez.

def _balon_gib() -> "float | None":
    """VMware balonunun ana makineye iade ettigi bellek (GiB)."""
    sisir = indir = None
    try:
        with open("/proc/vmstat", "r", encoding="utf-8") as handle:
            for satir in handle:
                if satir.startswith("balloon_inflate"):
                    sisir = float(satir.split()[1])
                elif satir.startswith("balloon_deflate"):
                    indir = float(satir.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    if sisir is None or indir is None:
        return None
    try:
        sayfa = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        sayfa = 4096
    net = (sisir - indir) * sayfa
    if net <= 0:
        return 0.0
    return round(net / (1024.0 ** 3), 2)


def _surec_rss_gib() -> "float | None":
    """Butun sureclerin RSS toplami -- uygulamalarin GERCEK kullanimi.

    Paylasilan sayfalar birden fazla surecte sayilir, yani bu deger bir
    UST sinirdir. Balon sayfalarini ise hic saymaz; asil isi o.
    """
    try:
        sayfa = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        sayfa = 4096
    toplam = 0
    bulundu = False
    try:
        for ad in os.listdir("/proc"):
            if not ad.isdigit():
                continue
            try:
                with open("/proc/" + ad + "/statm", "r", encoding="utf-8") as handle:
                    alanlar = handle.readline().split()
                toplam += int(alanlar[1])      # resident sayfa sayisi
                bulundu = True
            except (OSError, ValueError, IndexError):
                continue      # surec aradan kayboldu; normal
    except OSError:
        return None
    if not bulundu:
        return None
    return round(toplam * sayfa / (1024.0 ** 3), 2)


def sunucu_bellek_gercegi(ram: dict) -> dict:
    """Ham `free` okumasini balon duzeltmesiyle birlikte sunar."""
    balon = _balon_gib()
    rss = _surec_rss_gib()
    toplam = ram.get("total_gib")
    sonuc = {
        "ham_yuzde": ram.get("percent"),
        "ham_kullanim_gib": ram.get("used_gib"),
        "tanimli_gib": toplam,
        "balon_gib": balon,
        "surec_rss_gib": rss,
    }
    if balon is None:
        sonuc["durum"] = "DUZELTILEMEDI"
        sonuc["not"] = ("/proc/vmstat balon sayaclari okunamadi -- yukaridaki "
                        "yuzde HAM degerdir, sanal makine duzeltmesi yapilmadi.")
        return sonuc
    if toplam is None:
        sonuc["durum"] = "DUZELTILEMEDI"
        sonuc["not"] = "MemTotal okunamadi, balon dusulemedi."
        return sonuc

    gercek_toplam = round(max(0.0, toplam - balon), 2)
    sonuc["gercek_toplam_gib"] = gercek_toplam
    if rss is not None and gercek_toplam > 0:
        sonuc["gercek_bos_gib"] = round(max(0.0, gercek_toplam - rss), 2)
        sonuc["gercek_yuzde"] = round(min(100.0, rss / gercek_toplam * 100.0), 1)
    sonuc["durum"] = "BALON_VAR" if balon > 0.1 else "BALON_YOK"
    sonuc["not"] = (
        "Sanal makine balonu " + str(balon) + " GB'i ana makineye iade etmis. "
        "`free` bunu da 'kullanimda' sayar; asagidaki GERCEK satirlar "
        "balon dusulmus halidir. RSS toplami paylasilan sayfalari birden "
        "fazla saydigi icin UST sinirdir."
        if balon > 0.1 else
        "Balon sifir; ham degerler zaten gercegi gosteriyor."
    )
    return sonuc


def makineler(state_dir: Path, sunucu_metrikleri: dict) -> dict:
    """Uc makinenin tek sozlukte birlesik gorunumu."""
    sunucu = dict(sunucu_metrikleri)
    ram = sunucu.get("ram")
    if isinstance(ram, dict):
        sunucu["bellek_gercegi"] = sunucu_bellek_gercegi(ram)
    return {
        "sunucu": {"makine": "SUNUCU", "durum": "TAZE", "sebep": None,
                   "yas_s": 0, "veri": sunucu},
        "pc1": _rapor_oku(state_dir, "pc1"),
        "pc2": _rapor_oku(state_dir, "pc2"),
    }


# ------------------------------------------------------------- politika

# Sahibin 24.09.2026'da verdigi kaynak sirasi. Kod bu sozlugu
# DEGISTIRMEZ; yalnizca dosya yoksa ilk hali olarak okunur.
#
#   1. sunucu      -- her is once burada
#   2. PC-1        -- yetmezse ek kapasite (RAM + CPU + RX 6600)
#   3. PC-2        -- YALNIZ ekran karti
#
# PC-2'nin CPU/RAM'i kilit "ozel_izin" ile kapali gelir: panelden
# acilabilir ama acan kisi ne actigini gorur.
VARSAYILAN_POLITIKA = {
    "siralama": ["sunucu", "pc1", "pc2_gpu"],
    "anahtarlar": {
        "sunucu_cpu_ram": {
            "acik": True, "kilit": "yok", "sira": 1,
            "baslik": "SUNUCU - CPU + RAM",
            "aciklama": "Birincil kaynak. Her is once burada denenir.",
        },
        "pc1_cpu_ram": {
            "acik": True, "kilit": "yok", "sira": 2,
            "baslik": "PC-1 - CPU + RAM",
            "aciklama": "Ek kapasite. Sunucunun RAM'i yetmezse devreye girer.",
        },
        "pc1_gpu": {
            "acik": True, "kilit": "yok", "sira": 3,
            "baslik": "PC-1 - ekran karti (RX 6600)",
            "aciklama": "Gomme (BGE-M3) burada calisir.",
        },
        "pc2_gpu": {
            "acik": True, "kilit": "yok", "sira": 4,
            "baslik": "PC-2 - ekran karti (RTX 5060)",
            "aciklama": "Dil modeli burada calisir. PC-2'de izinli TEK kaynak.",
        },
        "pc2_cpu_ram": {
            "acik": False, "kilit": "ozel_izin", "sira": 5,
            "baslik": "PC-2 - CPU + RAM",
            "aciklama": ("Sahip karari: kapali. PC-2'den yalniz ekran karti "
                         "kullanilir. Acmak ozel izin ister."),
        },
    },
}


def _politika_yolu(state_dir: Path) -> Path:
    return Path(state_dir) / "kaynak_politikasi.json"


def politika_oku(state_dir: Path) -> dict:
    """Kayitli politika; dosya yoksa varsayilan (yazmadan)."""
    yol = _politika_yolu(state_dir)
    try:
        kayit = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        kayit = {}
    if not isinstance(kayit, dict):
        kayit = {}

    # Varsayilanin uzerine kayitli degerler bindirilir. Boylece sonradan
    # eklenen bir anahtar eski dosyada yok diye KAYBOLMAZ -- kapali
    # gorunup sessizce devre disi kalmasi en kotu sonuc olurdu.
    anahtarlar = {}
    kayitli = kayit.get("anahtarlar")
    if not isinstance(kayitli, dict):
        kayitli = {}
    for ad, tanim in VARSAYILAN_POLITIKA["anahtarlar"].items():
        birlesik = dict(tanim)
        k = kayitli.get(ad)
        if isinstance(k, dict) and isinstance(k.get("acik"), bool):
            birlesik["acik"] = k["acik"]
            birlesik["degistiren"] = k.get("degistiren")
            birlesik["degistirildi"] = k.get("degistirildi")
        anahtarlar[ad] = birlesik

    return {
        "siralama": list(VARSAYILAN_POLITIKA["siralama"]),
        "anahtarlar": anahtarlar,
        "kaynak": "dosya" if kayit else "varsayilan",
        "dosya": str(yol),
    }


def politika_yaz(state_dir: Path, anahtar: str, acik: bool, kim: str) -> dict:
    """Tek bir anahtari cevirir ve yeni politikayi dondurur.

    Bilinmeyen anahtar sessizce yok sayilmaz, ValueError atar: panelde
    yanlis isimle gonderilen bir istegin "basarili" gorunmesi, bu
    projede daha once yasanmis bir hata sinifi.
    """
    if anahtar not in VARSAYILAN_POLITIKA["anahtarlar"]:
        raise ValueError("bilinmeyen anahtar: " + str(anahtar))

    mevcut = politika_oku(state_dir)
    tanim = mevcut["anahtarlar"][anahtar]
    tanim["acik"] = bool(acik)
    tanim["degistiren"] = kim
    tanim["degistirildi"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    yol = _politika_yolu(state_dir)
    yol.parent.mkdir(parents=True, exist_ok=True)
    govde = {
        "guncellendi": tanim["degistirildi"],
        "guncelleyen": kim,
        "anahtarlar": {ad: {"acik": t["acik"],
                            "degistiren": t.get("degistiren"),
                            "degistirildi": t.get("degistirildi")}
                       for ad, t in mevcut["anahtarlar"].items()},
    }
    # Atomik yazim: yarim dosya okunursa politika "varsayilan"a duser ve
    # kapatilmis bir kaynak sessizce geri acilirdi.
    gecici = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(yol.parent), delete=False, suffix=".tmp")
    try:
        json.dump(govde, gecici, ensure_ascii=False, indent=2)
        gecici.flush()
        os.fsync(gecici.fileno())
        gecici.close()
        os.replace(gecici.name, yol)
    except BaseException:
        try:
            os.unlink(gecici.name)
        except OSError:
            pass
        raise
    return politika_oku(state_dir)


def izinli_mi(state_dir: Path, anahtar: str) -> bool:
    """Bir kaynak su anda kullanilabilir mi. Cagiran taraf icin tek kapi."""
    p = politika_oku(state_dir)
    tanim = p["anahtarlar"].get(anahtar)
    return bool(tanim and tanim.get("acik"))


def gorunum(state_dir: Path, sunucu_metrikleri: dict) -> dict:
    return {
        "olculdu": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "makineler": makineler(state_dir, sunucu_metrikleri),
        "politika": politika_oku(state_dir),
        "bayat_esigi_s": BAYAT_ESIGI_S,
    }


def makine_durumu(state_dir: Path, anahtar: str) -> str:
    """Tek makinenin rapor tazeligi: TAZE | BAYAT | RAPOR_YOK | BILINMIYOR.

    Ayri bir yardimci cunku cagiranlarin cogu sunucu metriklerine ihtiyac
    duymuyor; `makineler()` cagirmak icin bos bir olcum sozlugu uydurmak
    gerekirdi ve o sozluk zamanla gercek saniliyordu.
    """
    if anahtar == "sunucu":
        return "TAZE"
    try:
        return str(_rapor_oku(state_dir, anahtar).get("durum") or "BILINMIYOR")
    except Exception:  # noqa: BLE001 - okunamamak da bir durumdur
        return "BILINMIYOR"


# Uzaktan ACMA (Wake-on-LAN) icin donanim on kosullari. 24.09.2026'da
# PC-2 uzerinde OLCULDU ve saglanmiyor:
#   Wi-Fi  TP-Link USB adaptor -> WakeOnMagicPacket: Unsupported
#   Ethernet Realtek PCIe GbE  -> MAC 60-CF-84-A8-2E-F9, KABLO TAKILI DEGIL
#   HiberbootEnabled = 1 (Hizli Baslatma WoL'u ayrica bozar)
# Bu yuzden panelde "ac" dugmesi CALISIYORMUS gibi gosterilmez: istek
# kaydedilir ama uc, eksik on kosulu adiyla bildirir. Calismayan bir
# dugme, olmayan bir dugmeden kotudur.
UYANDIRMA_ON_KOSULLARI = (
    "PC-2'ye ethernet kablosu takilmali (Realtek PCIe GbE)",
    "Kartta WakeOnMagicPacket etkinlestirilmeli",
    "Hizli Baslatma kapatilmali (HiberbootEnabled = 0)",
)


def uyandirma_iste(state_dir: Path, hedef: str, kim: str) -> dict:
    """Uyandirma istegini kaydeder ve ON KOSUL durumunu dondurur.

    Istek dosyasi LAN'daki diger PC'nin ajani icindir: sunucu ev agina
    sihirli paket gonderemez, paket LAN icinden cikmali.
    """
    if hedef not in ("pc1", "pc2"):
        raise ValueError("bilinmeyen hedef: " + str(hedef))
    yol = Path(state_dir) / "uyandirma-istegi.json"
    kayit = {
        "hedef": hedef,
        "istendi": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "isteyen": str(kim)[:60],
    }
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(kayit, ensure_ascii=False), encoding="utf-8")
    os.replace(str(gecici), str(yol))
    return {
        "kaydedildi": True,
        "istek": kayit,
        "hazir": False,
        "sebep": "DONANIM_ON_KOSULU_EKSIK",
        "eksikler": list(UYANDIRMA_ON_KOSULLARI),
    }
