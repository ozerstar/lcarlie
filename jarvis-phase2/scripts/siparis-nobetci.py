#!/usr/bin/env python3
"""SIPARIS NOBETCISI — her kanali tarar, YENI siparisi uc yoldan haber verir.

Tasarim kurallari:
  1. Kanal LISTE dondurduyse bilgi KESINDIR; YUKSELDIYSE bilmiyoruz demektir.
     Ikisi core.kanal_nabiz'da ayri tutulur. Bu ayrim olmazsa, kirik bir
     kanal "siparis yok" gibi gorunur ve siparis sessizce kacar.
  2. Yenilik, veritabaninin TEKIL dizini ile belirlenir; bellekte "gordum mu"
     listesi tutulmaz. INSERT ... RETURNING bos donduyse siparis zaten vardi.
  3. BASLANGIC tarihinden onceki siparisler kaydedilir ama HABER VERILMEZ.
     Gecmise toplu bildirim kazasi bu satirla engellenir.
  4. Sessiz bozukluk = kacirilmis siparis. Bir kanal uzun suredir basarili
     cevap vermiyorsa, siparis olmasa bile ALARM uretilir.

Kullanim:
  siparis-nobetci.py                 (tara + haber ver)
  siparis-nobetci.py --kuru          (tara, hicbir sey yazma/gonderme)
  siparis-nobetci.py --ilk-kurulum   (hepsini kaydet, HIC haber verme)
  siparis-nobetci.py --kanal trendyol
  siparis-nobetci.py --durum         (nabiz tablosunu yaz)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import haberci, pazaryeri  # noqa: E402

ENV = Path("/etc/lcarlie/siparis-nobetci.env")
ALARM = "/opt/lcarlie/alarm.sh"
# Bir kanal bu suredir basarili cevap vermiyorsa, siparis olmasa bile alarm.
SESSIZLIK_SINIRI = timedelta(minutes=int(os.environ.get("NOBETCI_SESSIZLIK", "45")))


def ayar(anahtar: str, varsayilan: str = "") -> str:
    dogrudan = os.environ.get(anahtar)
    if dogrudan:
        return dogrudan.strip()
    if ENV.exists():
        for satir in ENV.read_text(encoding="utf-8").splitlines():
            if satir.startswith(anahtar + "="):
                return satir.split("=", 1)[1].strip()
    return varsayilan


def _m(deger) -> str:
    if deger is None or deger == "":
        return "NULL"
    return "'" + str(deger).replace("'", "''") + "'"


def _sayi(deger) -> str:
    try:
        return "%.2f" % float(deger)
    except (TypeError, ValueError):
        return "NULL"


def _alarm(anahtar: str, baslik: str, detay: str, seviye: str = "FAILED") -> None:
    """🔴 alarm.sh imzasi: <SEVIYE> <ANAHTAR> <BASLIK> [DETAY].
    Seviyeyi atlayip kaynak adiyla cagirmak, olayi gecersiz seviyeyle
    kaydeder ve dedup anahtarini kaydirir."""
    try:
        subprocess.run([ALARM, seviye, anahtar, baslik, detay],
                       capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


# ------------------------------------------------------------------- yazimlar
def nabiz_yaz(kanal: str, *, basarili: bool, adet: int | None = None,
              hata: str = "", kapali: bool = False) -> None:
    if basarili:
        haberci.psql(
            "INSERT INTO core.kanal_nabiz (kanal, son_basarili, son_deneme, "
            "  ardisik_hata, son_hata, son_siparis_sayisi, etkin, alarm_verildi) "
            "VALUES (%s, now(), now(), 0, NULL, %d, true, NULL) "
            "ON CONFLICT (kanal) DO UPDATE SET son_basarili = now(), "
            "  son_deneme = now(), ardisik_hata = 0, son_hata = NULL, "
            "  son_siparis_sayisi = %d, etkin = true, alarm_verildi = NULL;"
            % (_m(kanal), adet or 0, adet or 0))
    else:
        haberci.psql(
            "INSERT INTO core.kanal_nabiz (kanal, son_deneme, ardisik_hata, "
            "  son_hata, etkin) VALUES (%s, now(), 1, %s, %s) "
            "ON CONFLICT (kanal) DO UPDATE SET son_deneme = now(), "
            "  ardisik_hata = core.kanal_nabiz.ardisik_hata + 1, "
            "  son_hata = %s, etkin = %s;"
            % (_m(kanal), _m(hata[:300]), "false" if kapali else "true",
               _m(hata[:300]), "false" if kapali else "true"))


def siparis_yaz(s: pazaryeri.Siparis) -> int | None:
    """Yeni ise satir kimligini, zaten varsa None doner.
    🔴 Yenilik karari BURADA ve YALNIZ burada verilir."""
    kalemler = json.dumps(s.kalemler, ensure_ascii=False).replace("'", "''")
    ham = json.dumps(s.ham, ensure_ascii=False, default=str).replace("'", "''")
    zaman = _m(s.zaman.isoformat()) if s.zaman else "NULL"
    sonuc = haberci.psql(
        "INSERT INTO core.pazaryeri_siparis (kanal, siparis_no, paket_no, durum, "
        "  siparis_zamani, tutar, musteri_ad, sehir, kalem_sayisi, kalemler, ham) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %d, '%s'::jsonb, '%s'::jsonb) "
        "ON CONFLICT DO NOTHING RETURNING id;"
        % (_m(s.kanal), _m(s.siparis_no), _m(s.paket_no), _m(s.durum), zaman,
           _sayi(s.tutar), _m(s.musteri_ad), _m(s.sehir), len(s.kalemler),
           kalemler, ham))
    if not sonuc:
        # Zaten vardi: yalniz durum tazelenir, haber VERILMEZ.
        haberci.psql(
            "UPDATE core.pazaryeri_siparis SET durum = %s, son_guncelleme = now() "
            "WHERE kanal = %s AND siparis_no = %s AND durum IS DISTINCT FROM %s;"
            % (_m(s.durum), _m(s.kanal), _m(s.siparis_no), _m(s.durum)))
        return None
    return int(sonuc.splitlines()[0])


def haber_kapat(siparis_id: int, sebep: str) -> None:
    """Haber verilmeyecek siparisin uc yolunu da kapatir; bir daha acilmaz."""
    for yol in haberci.YOLLAR:
        haberci.psql(
            "INSERT INTO core.siparis_bildirim (siparis_id, yol, durum, hata) "
            "VALUES (%d, %s, 'ATLANDI', %s) ON CONFLICT DO NOTHING;"
            % (siparis_id, _m(yol), _m(sebep)))


# --------------------------------------------------------------------- tarama
def kanal_tara(kanal: str, islev, *, baslangic: datetime, kuru: bool,
               haber_ver: bool) -> dict:
    ozet = {"kanal": kanal, "durum": "", "siparis": 0, "yeni": 0, "haber": []}
    try:
        siparisler = islev()
    except pazaryeri.KanalKapali as sebep:
        ozet["durum"] = "KAPALI: %s" % sebep
        if not kuru:
            nabiz_yaz(kanal, basarili=False, hata=str(sebep), kapali=True)
        return ozet
    except Exception as hata:                           # noqa: BLE001
        ozet["durum"] = "HATA: %s: %s" % (type(hata).__name__, str(hata)[:120])
        if not kuru:
            nabiz_yaz(kanal, basarili=False,
                      hata="%s: %s" % (type(hata).__name__, hata))
        return ozet

    ozet["durum"] = "OK"
    ozet["siparis"] = len(siparisler)
    if kuru:
        return ozet
    nabiz_yaz(kanal, basarili=True, adet=len(siparisler))

    for s in siparisler:
        if not s.siparis_no:
            continue
        kimlik = siparis_yaz(s)
        if kimlik is None:
            continue
        ozet["yeni"] += 1
        if not haber_ver:
            haber_kapat(kimlik, "ilk kurulum: gecmis siparis")
            continue
        if s.zaman and s.zaman < baslangic:
            haber_kapat(kimlik, "baslangic tarihinden onceki siparis")
            continue
        sonuc = haberci.bildir(
            kimlik, kanal=s.kanal, siparis_no=s.siparis_no,
            tutar=("%.2f" % s.tutar) if s.tutar else "-",
            musteri=(" / ".join(x for x in (s.musteri_ad, s.sehir) if x)) or "-",
            urunler=s.ozet)
        ozet["haber"].append({s.siparis_no: sonuc})
        if not any(d == "GONDERILDI" for d in sonuc.values()):
            _alarm("siparis.habersiz", "HICBIR YOLDAN HABER VERILEMEDI",
                   "%s %s -> %s" % (s.kanal, s.siparis_no, sonuc))
    return ozet


def sessizlik_denetle() -> list[str]:
    """Bir kanal uzun suredir basarili cevap vermiyorsa ALARM.
    Siparisin olmamasi sessizlik degildir; SORAMAMAK sessizliktir."""
    satirlar = haberci.psql(
        "SELECT kanal, son_basarili, ardisik_hata, coalesce(son_hata,'') "
        "FROM core.kanal_nabiz WHERE etkin "
        "  AND (son_basarili IS NULL OR son_basarili < now() - interval '%d minutes') "
        "  AND alarm_verildi IS NULL;" % int(SESSIZLIK_SINIRI.total_seconds() // 60))
    uyarilar = []
    for satir in satirlar.splitlines():
        if not satir.strip():
            continue
        kanal, son, hata_sayi, son_hata = (satir.split("|") + ["", "", "", ""])[:4]
        mesaj = ("%s kanali %s dakikadir dogrulanamadi (son basarili: %s, "
                 "ardisik hata: %s) — %s"
                 % (kanal, int(SESSIZLIK_SINIRI.total_seconds() // 60),
                    son or "hic", hata_sayi, son_hata[:160]))
        uyarilar.append(mesaj)
        _alarm("siparis.kanal.%s" % kanal, "KANAL SESSIZ: %s" % kanal, mesaj)
        haberci.psql("UPDATE core.kanal_nabiz SET alarm_verildi = now() "
                     "WHERE kanal = %s;" % _m(kanal))
    return uyarilar


def durum_yaz() -> None:
    print(haberci.psql(
        "SELECT rpad(kanal,13) || rpad(coalesce(etkin::text,'?'),7) || "
        "rpad(coalesce(to_char(son_basarili,'DD.MM HH24:MI'),'-'),14) || "
        "rpad(coalesce(son_siparis_sayisi::text,'-'),6) || coalesce(son_hata,'') "
        "FROM core.kanal_nabiz ORDER BY kanal;") or "(nabiz tablosu bos)")
    print()
    print(haberci.psql(
        "SELECT rpad(kanal,13) || rpad(siparis_no,16) || rpad(durum,22) || "
        "to_char(ilk_gorulme,'DD.MM HH24:MI') FROM core.pazaryeri_siparis "
        "ORDER BY ilk_gorulme DESC LIMIT 15;") or "(henuz siparis kaydi yok)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true")
    ap.add_argument("--ilk-kurulum", action="store_true")
    ap.add_argument("--kanal")
    ap.add_argument("--durum", action="store_true")
    a = ap.parse_args()

    if a.durum:
        durum_yaz()
        return 0

    ham_baslangic = ayar("NOBETCI_BASLANGIC")
    try:
        baslangic = datetime.fromisoformat(ham_baslangic)
    except ValueError:
        print("🔴 NOBETCI_BASLANGIC okunamadi (%r) — haber verilmez."
              % ham_baslangic)
        return 2
    if baslangic.tzinfo is None:
        baslangic = baslangic.replace(tzinfo=timezone.utc)

    kanallar = ({a.kanal: pazaryeri.KANALLAR[a.kanal]} if a.kanal
                else pazaryeri.KANALLAR)
    haber_ver = not a.ilk_kurulum

    for kanal, islev in kanallar.items():
        ozet = kanal_tara(kanal, islev, baslangic=baslangic, kuru=a.kuru,
                          haber_ver=haber_ver)
        print("%-13s %-28s siparis=%-4d yeni=%d %s"
              % (ozet["kanal"], ozet["durum"][:28], ozet["siparis"],
                 ozet["yeni"], ozet["haber"] or ""))

    if not a.kuru:
        for uyari in sessizlik_denetle():
            print("🔴 " + uyari)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
