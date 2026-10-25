#!/usr/bin/env python3
"""Müşteri adresini onaylayınca HepsiJET barkodunu üretir.

Sahip kararı 23.10.2026: *"o onaylayınca jarvis kargo kodunu hepsijet ile
oluştursun."* `kargo_islem` modülünün "otomatik çağrılamaz" kuralı bu tek
yol için kaldırıldı. Kuralın koruduğu şeyler KALDI:

  · fiyat çağrıdan hemen önce uçtan yeniden sorulur (`barkod_uret` yapar),
  · `core.kargo_karar` kısmî tekil dizini aynı siparişe ikinci barkodu
    veritabanı seviyesinde durdurur,
  · karar satırı çağrıdan ÖNCE yazılır.

Buraya eklenen üç ek kapı:
  1. `KARGO_OTOMATIK=1` yoksa hiçbir şey yapılmaz (varsayılan KAPALI).
  2. Günlük tavan: bir günde en fazla `GUNLUK_TAVAN` otomatik barkod.
     Kaçak bir döngü bakiyeyi boşaltamasın diye.
  3. Yalnız BİZİM teyit mesajımızı alan ve ona ONAY yazan sipariş işlenir.
     Onay metni `core.siparis_teyit.onay_metni`ye aynen yazılır.

🔴 "Adresimi düzelteceğim" diyen sipariş kargoya VERİLMEZ; insana düşer.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import kapida_onay, kargo_islem, whatsapp  # noqa: E402
from jarvis.basitkargo import Kargo, KargoHatasi  # noqa: E402

ENV_DOSYASI = os.environ.get("META_ENV_FILE", "/opt/lcarlie/n8n/.env")
WIX_URL = "https://www.wixapis.com/stores/v2/orders/query"
ALARM = "/opt/lcarlie/alarm.sh"
TASIYICI = "HEPSIJET"
GUNLUK_TAVAN = int(os.environ.get("KARGO_OTOMATIK_TAVAN", "20"))
EN_FAZLA_DENEME = 5

# Onay sayılan metinler. Buton metni birebir gelir; elle yazan müşteri için
# birkaç güvenli karşılık eklendi. Sorular ve düzeltmeler ONAY DEĞİLDİR.
ONAY_METINLERI = {"ADRESIM DOGRU", "ADRES DOGRU", "ONAYLIYORUM",
                  "DOGRU", "EVET DOGRU", "ADRESIM DOGRUDUR"}
DUZELTME_METINLERI = {"ADRESIMI DUZELTECEGIM", "ADRESIMI DUZELTMEK ISTIYORUM",
                      "ADRES YANLIS", "DUZELTME"}
CEVIRI = str.maketrans({"İ": "I", "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O",
                        "Ç": "C", "ı": "I", "ş": "S", "ğ": "G", "ü": "U",
                        "ö": "O", "ç": "C"})


def sadelestir(metin: str) -> str:
    return " ".join((metin or "").strip().upper().translate(CEVIRI).split())


def _env(anahtar: str) -> str:
    deger = os.environ.get(anahtar)
    if deger:
        return deger.strip()
    for satir in Path(ENV_DOSYASI).read_text(encoding="utf-8").splitlines():
        if satir.startswith(anahtar + "="):
            return satir.split("=", 1)[1].strip()
    return ""


def _psql(sorgu: str) -> str:
    sonuc = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1", "-tAq"],
        input=sorgu, capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise RuntimeError("psql: " + sonuc.stderr.strip()[:200])
    return sonuc.stdout.strip()


def _metin(deger) -> str:
    return "'" + str(deger or "").replace("'", "''") + "'"


def _alarm(baslik: str, detay: str) -> None:
    try:
        subprocess.run([ALARM, "kargo-onay", baslik, detay],
                       capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def bekleyenler() -> list[dict]:
    """Teyidi gitmiş, kargosu henüz çıkmamış siparişler."""
    ham = _psql(
        "select coalesce(json_agg(row_to_json(x)), '[]') from ("
        "  select siparis_no, yol, kargo_durum, kargo_deneme,"
        "         greatest(son_deneme, coalesce(onay_zaman, son_deneme)) as bakilacak"
        "  from core.siparis_teyit"
        "  where durum = 'GONDERILDI'"
        "    and (kargo_durum is null or kargo_durum = 'BEKLIYOR'"
        "         or (kargo_durum = 'HATA' and kargo_deneme < %d))"
        "    and son_deneme >= now() - interval '30 days'"
        "  order by siparis_no) x;" % EN_FAZLA_DENEME)
    return json.loads(ham or "[]")


def gunluk_sayac() -> int:
    return int(_psql("select count(*) from core.siparis_teyit "
                     "where kargo_durum = 'OLUSTU' "
                     "and onay_zaman >= date_trunc('day', now());") or "0")


def wix_siparis(no: int) -> dict | None:
    govde = json.dumps({"query": {
        "paging": {"limit": 1, "offset": 0},
        "filter": json.dumps({"number": no})}}).encode()
    istek = urllib.request.Request(WIX_URL, data=govde, method="POST", headers={
        "Authorization": _env("WIX_API_KEY"), "wix-site-id": _env("WIX_SITE_ID"),
        "Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=45) as yanit:
        kayitlar = json.loads(yanit.read().decode("utf-8")).get("orders") or []
    return kayitlar[0] if kayitlar else None


def _rakam(deger) -> str:
    return "".join(k for k in str(deger or "") if k.isdigit())


def musteri_yaniti(telefon: str, sonra: str) -> tuple[str, str]:
    """(ham metin, zaman). Teyit gönderildikten SONRAKİ ilk gelen mesaj."""
    rakam = _rakam(telefon)
    if len(rakam) < 10:
        return "", ""
    ham = _psql(
        "select coalesce(json_agg(row_to_json(x)), '[]') from ("
        "  select coalesce(nullif(m.ek->>'button_payload',''), m.metin) as metin,"
        "         m.zaman"
        "    from lcarlie.mesaj m"
        "    join lcarlie.konusma k on k.id = m.konusma_id"
        "   where k.kanal = 'whatsapp'"
        "     and m.yon = 'gelen'"
        "     and regexp_replace(k.harici_id, '[^0-9]', '', 'g') like %s"
        "     and m.zaman > %s::timestamptz"
        "   order by m.zaman limit 5) x;" % (
            _metin("%" + rakam[-10:]), _metin(sonra)))
    kayitlar = json.loads(ham or "[]")
    for kayit in kayitlar:
        if sadelestir(kayit["metin"]):
            return kayit["metin"], kayit["zaman"]
    return "", ""


def il_ilce(siparis: dict, k: Kargo) -> tuple[str, str]:
    """Wix `subdivision` TR-06 = il plakası, `city` ise İLÇE adıdır.
    Bu ikisi karıştırılırsa gönderi yanlış şubeye düşer."""
    adres = (((siparis.get("shippingInfo") or {}).get("shipmentDetails") or {})
             .get("address") or {})
    plaka = str(adres.get("subdivision") or "").replace("TR-", "").strip()
    ilce_ham = str(adres.get("city") or "").strip()
    if not plaka or not ilce_ham:
        raise ValueError("il plakasi veya ilce adi yok")
    iller = k.cagir("list_cities", {}).get("veri") or []
    il = next((i["name"] for i in iller if str(i.get("iso2")) == plaka), "")
    if not il:
        raise ValueError("plaka taninmadi: " + plaka)
    ilceler = [d["name"] for d in (k.cagir("get_districts",
                                           {"cityId": plaka}).get("veri") or [])]
    eslesen = next((d for d in ilceler if sadelestir(d) == sadelestir(ilce_ham)), "")
    if not eslesen:
        raise ValueError("ilce %s, %s listesinde yok" % (ilce_ham, il))
    return il, eslesen


def kargo_kapat(no, durum, sebep="", kargo_id="", barkod="") -> None:
    _psql("update core.siparis_teyit set kargo_durum=%s, kargo_sebep=%s, "
          "kargo_siparis_id=%s, barkod=%s, kargo_deneme=kargo_deneme+1 "
          "where siparis_no=%d;" % (_metin(durum), _metin(sebep[:300]),
                                    _metin(kargo_id), _metin(barkod), int(no)))


def bekliyor(no, sebep: str) -> None:
    """Deneme sayacını ARTIRMADAN beklemeye alır: bu bir hata değil,
    henüz onay gelmemiş olmasıdır."""
    _psql("update core.siparis_teyit set kargo_durum='BEKLIYOR', kargo_sebep=%s "
          "where siparis_no=%d;" % (_metin(sebep[:300]), int(no)))


def onay_yaz(no, metin, zaman) -> None:
    _psql("update core.siparis_teyit set onay_metni=%s, onay_zaman=%s::timestamptz "
          "where siparis_no=%d;" % (_metin(metin[:200]), _metin(zaman), int(no)))


def isle(satir: dict, *, gercek: bool, k: Kargo) -> str:
    no = satir["siparis_no"]
    siparis = wix_siparis(int(no))
    if siparis is None:
        kargo_kapat(no, "HATA", "siparis Wix'te bulunamadi")
        return "%s: siparis bulunamadi" % no
    adres = (((siparis.get("shippingInfo") or {}).get("shipmentDetails") or {})
             .get("address") or {})
    telefon = str(adres.get("phone")
                  or (siparis.get("buyerInfo") or {}).get("phone") or "")
    yanit, zaman = musteri_yaniti(telefon, satir["bakilacak"])
    if not yanit:
        return "%s: musteri yaniti yok" % no
    # Bakılan mesajın zamanı kaydedilir: bir sonraki tur ONDAN SONRASINA
    # bakar. Yoksa müşterinin ilk sorusu, sonradan bastığı onay düğmesini
    # sonsuza kadar gölgelerdi.
    onay_yaz(no, yanit, zaman)
    sade = sadelestir(yanit)

    kapida = satir["yol"] == "KAPIDA"
    if kapida:
        karar = kapida_onay.yaniti_tani(yanit, str(no), tek_bekleyen=True)
        if karar == "ITIRAZ":
            kargo_kapat(no, "INSANA", "musteri siparisi reddetti")
            return "%s: ITIRAZ, kargo yok" % no
        if karar not in {"ONAY_NAKIT", "ONAY_KART"}:
            bekliyor(no, "kapida yaniti onay degil: %s" % karar)
            return "%s: kapida onayi degil (%s), bekliyor" % (no, karar)
        kapida_tur = "CASH" if karar == "ONAY_NAKIT" else "CREDIT_CARD"
    else:
        if sade in DUZELTME_METINLERI:
            kargo_kapat(no, "INSANA", "musteri adres duzeltmek istiyor")
            return "%s: DUZELTME istendi, kargo yok" % no
        if sade not in ONAY_METINLERI:
            # Soru sormak onay DEĞİLDİR ama reddetmek de değildir: satır
            # beklemede kalır, müşteri sonra onaylayabilir.
            bekliyor(no, "yanit onay sayilmadi: %s" % sade[:60])
            return "%s: yanit onay degil, bekliyor" % no
        kapida_tur = "CASH"

    try:
        il, ilce = il_ilce(siparis, k)
    except ValueError as hata:
        kargo_kapat(no, "HATA", "adres cozulemedi: %s" % hata)
        _alarm("adres cozulemedi", "siparis %s: %s" % (no, hata))
        return "%s: adres cozulemedi (%s)" % (no, hata)

    ad_alani = adres.get("fullName") or {}
    alici = " ".join(p for p in (ad_alani.get("firstName"),
                                 ad_alani.get("lastName")) if p).strip()
    kalemler = siparis.get("lineItems") or []
    icerik = ", ".join("%s x%s" % (str(x.get("name") or "").split("(")[0].strip(),
                                   x.get("quantity") or 1) for x in kalemler)
    tutar = (siparis.get("totals") or {}).get("total")

    if not gercek:
        return ("%s: KURU -- %s / %s / %s | %s | %s%s" % (
            no, alici, il, ilce, icerik, TASIYICI,
            " (karsi odemeli %s)" % tutar if kapida else ""))

    kargo_kapat(no, "ISTENDI", "musteri onayi: %s" % sade[:60])
    try:
        taslak = kargo_islem.taslak_olustur(
            alici=alici, telefon=telefon, il=il, ilce=ilce,
            adres=str(adres.get("addressLine1") or ""), icerik=icerik,
            karsi_odemeli=kapida, kapida_tutar=tutar if kapida else None,
            kapida_tur=kapida_tur, referans="WIX-%s" % no)
    except kargo_islem.IslemHatasi as hata:
        kargo_kapat(no, "HATA", "taslak: %s" % hata)
        _alarm("kargo taslagi acilamadi", "siparis %s: %s" % (no, hata))
        return "%s: taslak acilamadi (%s)" % (no, hata)

    kargo_id = taslak["siparis_id"]
    try:
        fiyatlar = kargo_islem.ucret_sor(kargo_id)
    except kargo_islem.IslemHatasi as hata:
        kargo_kapat(no, "HATA", "fiyat: %s" % hata, kargo_id)
        return "%s: fiyat alinamadi (%s)" % (no, hata)
    satirlar = fiyatlar.get("fiyatlar") or []
    hepsijet = next((s for s in satirlar
                     if str(s.get("tasiyici")).upper() == TASIYICI), None)
    if not hepsijet or hepsijet.get("kapali") or hepsijet.get("ucret") is None:
        kargo_kapat(no, "HATA", "HepsiJET fiyat vermedi", kargo_id)
        _alarm("HepsiJET fiyat yok", "siparis %s, kargo taslagi %s" % (no, kargo_id))
        return "%s: HepsiJET fiyati yok, barkod uretilmedi" % no

    try:
        sonuc = kargo_islem.barkod_uret(
            siparis_id=kargo_id, tasiyici=TASIYICI,
            gosterilen_ucret=hepsijet["ucret"], veren="jarvis-musteri-onayi",
            karsi_odemeli=kapida, kapida_tutar=tutar if kapida else None)
    except kargo_islem.IslemHatasi as hata:
        kargo_kapat(no, "HATA", "barkod: %s" % hata, kargo_id)
        _alarm("barkod uretilemedi", "siparis %s: %s" % (no, hata))
        return "%s: barkod uretilemedi (%s)" % (no, hata)

    kargo_kapat(no, "OLUSTU", "%s %.2f TL" % (TASIYICI, hepsijet["ucret"]),
                kargo_id, str(sonuc.get("barkod") or ""))
    # Musteri onayladi ve kargo cikti: sessiz kalmak, onayin ise yarayip
    # yaramadigini bilinmez birakir. Kisa bir kapanis yazilir -- musteri az
    # once yazdigi icin 24 saat penceresi aciktir, sablon gerekmez.
    try:
        whatsapp.gonder(
            telefon,
            "Teşekkür ederiz, adresiniz onaylandı. Siparişiniz kargoya "
            "hazırlanıyor; gönderiye verildiğinde takip numaranızı "
            "buradan ileteceğiz.",
            onay_kaynagi=whatsapp.ONAY_OTOMATIK)
    except whatsapp.GondermeReddedildi as hata:
        _alarm("onay kapanisi gonderilemedi", "siparis %s: %s" % (no, hata))
    return "%s: HEPSIJET BARKOD %s (%.2f TL)" % (
        no, sonuc.get("barkod"), hepsijet["ucret"])


def main() -> None:
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--gercek", action="store_true",
                             help="🔴 PARA HARCAR -- barkod uretir")
    arg = ayristirici.parse_args()
    gercek = arg.gercek and os.environ.get("KARGO_OTOMATIK") == "1"
    if arg.gercek and not gercek:
        print("KARGO_OTOMATIK=1 degil -- kuru kosu")

    bekleyen = bekleyenler()
    if not bekleyen:
        return
    if gercek:
        sayac = gunluk_sayac()
        if sayac >= GUNLUK_TAVAN:
            _alarm("gunluk kargo tavani", "%d barkod uretildi, durduruldu" % sayac)
            print("gunluk tavan (%d) doldu, barkod uretilmiyor" % GUNLUK_TAVAN)
            gercek = False

    k = Kargo(zaman_asimi=30)
    for satir in bekleyen:
        try:
            print(isle(satir, gercek=gercek, k=k))
        except (KargoHatasi, RuntimeError, OSError) as hata:
            print("%s: HATA %s" % (satir["siparis_no"], str(hata)[:160]))


if __name__ == "__main__":
    main()
