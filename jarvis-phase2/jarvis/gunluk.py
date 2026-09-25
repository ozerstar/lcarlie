"""Yutulan hatalarin gunlugu: gorunmez arizayi gorunur kilar.

NEDEN VAR. 25.09.2026'da olculdu: kod tabaninda 158 adet `except Exception`
blogu var ve `import logging` gecen dosya sayisi 1. Bloklarin hepsi
gerekceli -- "telemetri cagirani asla dusuremez", "bellek bir yardimcidir,
bagimlilik degil" gibi. Yani yutmak bilincli bir karar. Sorun yutmak degil,
YUTARKEN HICBIR YERE YAZMAMAK.

Sonucu su: bir saglayici sessizce dusse, bir arastirma kaynagi 403 dondurse
ya da bir ayristirma bozulsa, bunu ancak sonucun YOKLUGUNDAN anlarsiniz. Bu
projede daha once olculmus bir kok hata var ve tam olarak budur: yoklugu
sebebini bilmeden cumleye cevirmek. "Veri yok" ile "bakamadim" ayni sey
degildir; ikincisi bir arizadir ve bugun hicbir yerde yazmiyor.

KAPSAM. Bu modul yalniz YAZAR. Hicbir karar vermez, hicbir istegi engellemez,
hicbir seyi yeniden dener. Yazma hatasi cagirani ASLA etkilemez -- gunluk
kaybi, cevabin kaybindan iyidir. Bu, kademe_kaydi.py ile ayni sozlesmedir.

BAGIMLILIK YOK. Cekirdek hicbir dis pakete bagli degildir; bu modul de yalniz
standart kutuphane kullanir.

DURUM AYRIMI. `agirlik` alani iki hali ayirir ve bunlar birbirinin yerine
gecmez:
    YUTULDU   beklenen bir bosluk; cagiran eski davranisina dustu
    ARIZA     beklenmeyen; sonuc eksik ve bunun bir bedeli var
Ayrimi cagiran yapar, cunku yalniz o hangi yolun yedegi oldugunu bilir.
Hepsini "ARIZA" yazmak, gunlugu yine okunmaz hale getirirdi.
"""
from __future__ import annotations

import itertools
import json
import os
import time
import traceback
from pathlib import Path

VARSAYILAN_DURUM_DIZINI = "/opt/lcarlie/jarvis-phase2/state"

AGIRLIK_YUTULDU = "YUTULDU"
AGIRLIK_ARIZA = "ARIZA"

# Ayni saniyede birden cok yutma olabilir ve alanlari ayni oldugunda satirlar
# ayirt edilemez hale gelir -- kademe.jsonl'de bu olculmustu (350 kaydin 86'si
# aktarimda tek satira indi). Ayni cozum burada bastan uygulaniyor.
_SIRA = itertools.count(1)

# 🔴 UST SINIR GEREKLI. Bu gunluk, kademe.jsonl'den farkli olarak bir HATA
# akisiyla beslenir. Bir saglayici her iki dakikada bir dusmeye baslarsa
# (action-worker 2 dk'da bir kosuyor) dosya sinirsiz buyur ve diski doldurur
# -- yani gorunurluk icin eklenen sey, bir kesintiye donusur. Devir tek
# yedekle sinirli: gecmisi sonsuza saklamak bu dosyanin isi degil, son
# durumu gostermek isi.
AZAMI_BAYT = 5 * 1024 * 1024


def _yol() -> Path:
    """Gunluk dosyasinin yolu. Her cagride yeniden okunur.

    🔴 JARVIS_STATE_DIR'DAN TURETILIR, mutlak yol YAZILMAZ. Bu projede ayni
    sinif hata iki kez yasandi: testler uretim dosyasina yazdi (kademe
    gunlugune tek kosuda 19-20 satir, sohbet dokumune 369 satir fixture).
    Test modulleri ice aktarmadan once JARVIS_STATE_DIR'i gecici klasore
    aliyor; bu modul o korumanin ICINDE kalmali.
    """
    acik = os.environ.get("JARVIS_GUNLUK_LOG")
    if acik:
        return Path(acik)
    durum = os.environ.get("JARVIS_STATE_DIR", VARSAYILAN_DURUM_DIZINI)
    return Path(durum) / "gunluk.jsonl"


def _devret(yol: Path) -> None:
    """Dosya siniri astiysa tek yedege devret. Hata firlatmaz."""
    try:
        if yol.exists() and yol.stat().st_size >= AZAMI_BAYT:
            yol.replace(yol.with_suffix(yol.suffix + ".1"))
    except OSError:
        # Devredemedik; yazmaya devam etmek, hic yazmamaktan iyidir.
        pass


def yut(modul: str, islev: str, istisna: BaseException, *,
        neden: str, agirlik: str = AGIRLIK_YUTULDU, **ek) -> None:
    """Yutulan bir istisnayi kaydet. Hicbir kosulda istisna firlatmaz.

    modul/islev  hatanin GERCEKTEN olustugu yer -- cagiranin degil.
    neden        bu hatanin neden yutuldugu, insan cumlesiyle. Zorunlu:
                 gerekcesi yazilamayan bir yutma, gozden gecirilmeli.
    agirlik      AGIRLIK_YUTULDU / AGIRLIK_ARIZA (yukaridaki ayrima bak).
    """
    try:
        satir = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "sira": "%d-%d" % (os.getpid(), next(_SIRA)),
            "modul": modul,
            "islev": islev,
            "agirlik": agirlik,
            "tip": type(istisna).__name__,
            # Mesaj kirpilir: bazi saglayicilar tum HTML govdesini istisna
            # metnine koyuyor ve tek satir gunlugu okunmaz hale getiriyor.
            "mesaj": str(istisna)[:500],
            "neden": neden,
            **ek,
        }
        yol = _yol()
        yol.parent.mkdir(parents=True, exist_ok=True)
        _devret(yol)
        with yol.open("a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(satir, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 - gunluk cagirani asla dusuremez
        pass


def son_kayitlar(limit: int = 50) -> list[dict]:
    """Son N satiri yeniden eskiye dogru dondur. Dosya yoksa bos liste.

    Dosya yokluguyla okuma hatasi AYNI SEY DEGILDIR ama bu islev ikisini de
    bos liste ile karsilar; ayrimi gereken yerde `ozet()` kullanilir.
    """
    try:
        yol = _yol()
        if not yol.exists():
            return []
        satirlar = yol.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    cikti: list[dict] = []
    for ham in reversed(satirlar):
        if len(cikti) >= limit:
            break
        ham = ham.strip()
        if not ham:
            continue
        try:
            cikti.append(json.loads(ham))
        except json.JSONDecodeError:
            # Yarim yazilmis son satir olabilir (surec kesildiyse). Atla.
            continue
    return cikti


def ozet(limit: int = 500) -> dict:
    """Modul basina yutma sayisi -- panelin 'en cok nerede susuyoruz' sorusu.

    `durum` alani, bu projenin her yerinde oldugu gibi yoklugu sebebinden
    ayirir: VERI_YOK gercekten sifir satir, OKUNAMADI ise dosya var ama
    okunamadi. Ikisini karistirmak yanlis teshise goturur.
    """
    yol = _yol()
    if not yol.exists():
        return {"durum": "VERI_YOK", "toplam": 0, "moduller": {}, "arizalar": 0}
    try:
        kayitlar = son_kayitlar(limit)
    except OSError:
        return {"durum": "OKUNAMADI", "toplam": 0, "moduller": {}, "arizalar": 0}
    moduller: dict[str, int] = {}
    arizalar = 0
    for k in kayitlar:
        anahtar = "%s.%s" % (k.get("modul", "?"), k.get("islev", "?"))
        moduller[anahtar] = moduller.get(anahtar, 0) + 1
        if k.get("agirlik") == AGIRLIK_ARIZA:
            arizalar += 1
    return {
        "durum": "OK",
        "toplam": len(kayitlar),
        "arizalar": arizalar,
        "moduller": dict(sorted(moduller.items(), key=lambda p: -p[1])),
    }


def izle(modul: str, islev: str, *, neden: str,
         agirlik: str = AGIRLIK_YUTULDU):
    """`with` blogu olarak yutma: istisnayi kaydeder ve YUTAR.

    Kullanim:
        with gunluk.izle("research_sources", "_tarih_cikar",
                         neden="tarih ayristirma arastirmayi bozamaz"):
            ...

    🔴 Bu, `except Exception: pass`in yerine gecer -- yanina degil. Ikisini
    ust uste koymak, ayni hatayi iki kez yutup bir kez kaydetmek olurdu.
    """
    return _Izleyici(modul, islev, neden, agirlik)


class _Izleyici:
    __slots__ = ("_modul", "_islev", "_neden", "_agirlik")

    def __init__(self, modul: str, islev: str, neden: str, agirlik: str) -> None:
        self._modul = modul
        self._islev = islev
        self._neden = neden
        self._agirlik = agirlik

    def __enter__(self) -> _Izleyici:
        return self

    def __exit__(self, tip, deger, iz) -> bool:
        if deger is None:
            return False
        # KeyboardInterrupt / SystemExit yutulmaz: bunlar bir ariza degil,
        # birinin durdurma emridir. Yutmak, durdurulamayan surec demektir.
        if isinstance(deger, (KeyboardInterrupt, SystemExit)):
            return False
        yut(self._modul, self._islev, deger,
            neden=self._neden, agirlik=self._agirlik,
            iz=traceback.format_exc(limit=3)[:800])
        return True
