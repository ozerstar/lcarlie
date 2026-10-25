#!/usr/bin/env python3
"""Yeni Wix siparişlerini tarar ve ÖDEME YOLUNA GÖRE teyit mesajı gönderir.

ÖNCE ÖDEME YOLU BELİRLENİR, SONRA MESAJ SEÇİLİR
  `billingInfo.paymentMethod` alanı:
    "Çevrim Dışı Ödemeler" / "Офлайн-оплата"  -> KAPIDA ÖDEME
        lcarlie_kapida_odeme_butonlu_v1  (nakit/kart tercihi sorar)
    PayTR vb. ve ödeme PAID                   -> NORMAL ÖDEME
        lcarlie_siparis_teyidi_v1        (teşekkür + adres onayı)
  🔴 Alan boşsa HİÇBİR ŞEY gönderilmez. Yanlış mesaj, mesajsızlıktan kötüdür:
     kapıda ödemeliye "ödemeniz alındı" demek müşteriyi yanıltır.

TEK SEFERLİK: `core.siparis_teyit` tablosu sipariş başına kilittir. Satır
INSERT edilmeden ağa çıkılmaz; aynı siparişe ikinci mesaj gidemez.

🔴 GERİ ALINAMAZ İŞ. Varsayılan KURU KOŞU; gerçek gönderim için --gonder
gerekir ve `jarvis.whatsapp`in beş kapısı ayrıca işler.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import kapida_onay, whatsapp  # noqa: E402

ENV_DOSYASI = os.environ.get("META_ENV_FILE", "/opt/lcarlie/n8n/.env")
WIX_URL = "https://www.wixapis.com/stores/v2/orders/query"
GORSEL_KOK = "https://n8n.lcarlie.shop/urun-gorsel/teyit/"
GORSEL_DIZIN = Path("/opt/lcarlie/urun-gorsel/teyit")
GORSEL_URETICI = KOK / "scripts" / "wa-teyit-gorsel.py"
ALARM = "/opt/lcarlie/alarm.sh"

SABLON_NORMAL = "lcarlie_siparis_teyidi_v1"
SABLON_KAPIDA = "lcarlie_kapida_odeme_butonlu_v1"
EN_FAZLA_DENEME = 48   # 15 dk x 48 = 12 saat; sablon onayi beklerken pes etmesin
IPTAL = {"CANCELED", "CANCELLED"}

ONIZLEME_NORMAL = (
    "Sayın {0},\n\nL’CARLIÉ ritüeline hoş geldiniz. Bize gösterdiğiniz güven "
    "için teşekkür ederiz.\n\n{1} numaralı siparişiniz tarafımıza ulaştı ve "
    "özenle hazırlanmak üzere alındı.\n\nÜrünler: {2}\nTutar: {3} TL\n"
    "Teslimat adresi: {4}\nTelefon: {5}\n\nGönderinizin ilk seferde doğru "
    "kapıya ulaşabilmesi için adres bilgilerinizi onaylamanızı rica ederiz. "
    "Bir düzeltme gerekiyorsa bu mesaja yazmanız yeterlidir; ekibimiz en kısa "
    "sürede dönüş yapar."
)


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
        # 🔴 -q SART. Onsuz psql, satir donmeyen INSERT/UPDATE icin bile
        #    "UPDATE 0" komut etiketi basar; bunu "sonuc var" sanan kilit
        #    HER TURDA acilir ve ayni musteriye mesaj tekrar gider.
        #    23.10.2026'da tam bu yuzden bir siparise 3 mesaj cikti.
        input=sorgu, capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise RuntimeError("psql: " + sonuc.stderr.strip()[:200])
    return sonuc.stdout.strip()


def _alarm(baslik: str, detay: str) -> None:
    try:
        subprocess.run([ALARM, "siparis-teyit", baslik, detay],
                       capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def _metin(deger) -> str:
    return "'" + str(deger or "").replace("'", "''") + "'"


def wix_siparisleri(adet: int) -> list[dict]:
    """En yeni siparişler. Sıralama sunucuda yapılır; sayfalama gerekmez."""
    govde = json.dumps({"query": {
        "paging": {"limit": adet, "offset": 0},
        "sort": "[{\"dateCreated\": \"desc\"}]"}}).encode()
    istek = urllib.request.Request(WIX_URL, data=govde, method="POST", headers={
        "Authorization": _env("WIX_API_KEY"), "wix-site-id": _env("WIX_SITE_ID"),
        "Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=45) as yanit:
        return json.loads(yanit.read().decode("utf-8")).get("orders") or []


def _kayit(siparis: dict) -> dict:
    """API nesnesini `raw.wix_order` satırıyla aynı anahtarlara çevirir;
    `kapida_onay` bu şekli bekler."""
    return {
        "odeme_yontemi": (siparis.get("billingInfo") or {}).get("paymentMethod"),
        "odeme_durumu": siparis.get("paymentStatus"),
        "teslimat_durumu": siparis.get("fulfillmentStatus"),
        "arsivlendi": siparis.get("archived"),
        "ic_siparis": siparis.get("isInternalOrderCreate"),
        "siparis_no": str(siparis.get("number") or ""),
        "para_birimi": siparis.get("currency"),
        "toplam": (siparis.get("totals") or {}).get("total"),
        "ham": siparis,
    }


def _tutar(deger) -> str:
    return f"{float(deger):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _slug(ad: str) -> str:
    sade = ad.split("(")[0].strip().lower()
    for eski, yeni in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"),
                       ("ö", "o"), ("ç", "c"), (" ", "-")):
        sade = sade.replace(eski, yeni)
    return "".join(k for k in sade if k.isalnum() or k == "-").strip("-")


def baslik_gorseli(urun_adi: str) -> str:
    """Ürün kartı yoksa üretilir; o da olmazsa markalı genel kart kullanılır.
    Görsel yüzünden mesaj gönderilmemesi, görselsiz mesajdan kötüdür."""
    ad = _slug(urun_adi)
    if ad and (GORSEL_DIZIN / (ad + ".jpg")).exists():
        return GORSEL_KOK + ad + ".jpg"
    if ad:
        try:
            subprocess.run([str(KOK / "venv" / "bin" / "python"),
                            str(GORSEL_URETICI), urun_adi.split("(")[0].strip()],
                           capture_output=True, text=True, timeout=120, check=True)
        except (OSError, subprocess.SubprocessError):
            pass
        if (GORSEL_DIZIN / (ad + ".jpg")).exists():
            return GORSEL_KOK + ad + ".jpg"
    return GORSEL_KOK + "genel.jpg"


def normal_degerler(siparis: dict) -> tuple[list[str], str, str]:
    """(şablon değerleri, telefon, ürün adı). Eksik alanda ValueError."""
    adres = (((siparis.get("shippingInfo") or {}).get("shipmentDetails") or {})
             .get("address") or {})
    alici = siparis.get("buyerInfo") or {}
    ad_alani = adres.get("fullName") or {}
    ad = " ".join(p for p in (ad_alani.get("firstName"), ad_alani.get("lastName")) if p)
    ad = ad.strip() or " ".join(
        p for p in (alici.get("firstName"), alici.get("lastName")) if p).strip()
    telefon = str(adres.get("phone") or alici.get("phone") or "").strip()
    kalemler = siparis.get("lineItems") or []
    if not ad or not telefon or not kalemler:
        raise ValueError("ad, telefon veya ürün yok")
    satir = ", ".join("%s x%s" % (str(k.get("name") or "").split("(")[0].strip(),
                                  k.get("quantity") or 1) for k in kalemler)
    yer = ", ".join(p for p in (adres.get("addressLine1"), adres.get("city")) if p)
    if not yer:
        raise ValueError("teslimat adresi yok")
    degerler = [ad, str(siparis.get("number")), satir,
                _tutar((siparis.get("totals") or {}).get("total")),
                " ".join(yer.split()), telefon]
    return degerler, telefon, str(kalemler[0].get("name") or "")


def kilit_al(kayit: dict, yol: str, sablon: str, telefon: str) -> bool:
    """Satırı açar. False dönerse bu siparişe DOKUNULMAZ."""
    no = int(kayit["siparis_no"])
    sonuc = _psql(
        "with yazim as (insert into core.siparis_teyit "
        "(siparis_no, siparis_id, yol, sablon, durum, telefon_son4, deneme) "
        "values (%d, %s, %s, %s, 'GONDERILIYOR', %s, 1) "
        "on conflict (siparis_no) do update set "
        "  durum='GONDERILIYOR', deneme=core.siparis_teyit.deneme+1, son_deneme=now() "
        "where core.siparis_teyit.durum='HATA' "
        "  and core.siparis_teyit.deneme < %d "
        "returning 1) select count(*) from yazim;" % (
            no, _metin(kayit["ham"].get("id")), _metin(yol), _metin(sablon),
            _metin(whatsapp._telefon_sadele(telefon)[-4:]), EN_FAZLA_DENEME))
    # Sayiyi ACIKCA karsilastir: "bos degil" yetmez, etiket de bos degildir.
    return sonuc.strip() == "1"


def kilit_kapat(no: str, durum: str, sebep: str = "", wamid: str = "") -> None:
    _psql("update core.siparis_teyit set durum=%s, sebep=%s, wamid=%s, son_deneme=now() "
          "where siparis_no=%d;" % (_metin(durum), _metin(sebep[:300]),
                                    _metin(wamid), int(no)))


def atla(no: str, sebep: str) -> None:
    """Mesaj gönderilmeyecek siparişi kalıcı olarak işaretler."""
    _psql("insert into core.siparis_teyit "
          "(siparis_no, siparis_id, yol, sablon, durum, sebep) "
          "values (%d, '', 'ATLANDI', '', 'ATLANDI', %s) "
          "on conflict (siparis_no) do nothing;" % (int(no), _metin(sebep)))


TESLIMAT_DEFTERI = Path(
    "/opt/lcarlie/jarvis-phase2/state/meta_webhook/teslimat.jsonl")


def teslimat_isle() -> list[str]:
    """Meta'nın teslim raporunu deftere işler.

    🔴 "Meta çağrıyı KABUL ETTİ" ile "mesaj ULAŞTI" aynı şey değildir.
    Gönderme çağrısı anında `wamid` döndürür; başarısızlık dakikalar sonra
    ayrı bir webhook'la gelir. 23.10.2026'da gönderilen her mesaj 131042
    (işletme ödeme uygunluğu) ile düştü, defterde ise "GONDERILDI" yazıyordu.
    Bu fonksiyon o yalanı kapatır: ulaşmayan mesaj BASARISIZ olur.

    BASARISIZ satır kendiliğinden yeniden denenmez -- `kilit_al` yalnız
    HATA satırını yeniden dener. Ödeme/uygunluk sorunu çözülmeden tekrar
    göndermek, aynı hatayı müşteri başına çoğaltmaktan başka işe yaramaz.
    """
    try:
        satirlar = TESLIMAT_DEFTERI.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    son: dict[str, dict] = {}
    for satir in satirlar:
        try:
            olay = json.loads(satir)
        except ValueError:
            continue
        wamid = str(olay.get("wamid") or "")
        if wamid:
            son[wamid] = olay

    notlar = []
    for wamid, olay in son.items():
        durum = str(olay.get("durum") or "")
        if durum == "failed":
            kod = str(olay.get("hata_kodu") or "?")
            etkilenen = _psql(
                "with y as (update core.siparis_teyit set durum='BASARISIZ', "
                "sebep=%s where wamid=%s and durum='GONDERILDI' "
                "returning siparis_no) select count(*) from y;" % (
                    _metin("Meta teslim etmedi, hata " + kod), _metin(wamid)))
            if etkilenen.strip() not in ("", "0"):
                notlar.append("ULASMADI (Meta %s)" % kod)
        elif durum in ("delivered", "read"):
            _psql("update core.siparis_teyit set sebep=%s "
                  "where wamid=%s and durum='GONDERILDI' and coalesce(sebep,'')='';"
                  % (_metin("teslim edildi"), _metin(wamid)))
    return notlar


def isle(siparis: dict, *, gonder: bool, baslangic: datetime) -> str:
    kayit = _kayit(siparis)
    no = kayit["siparis_no"]
    if not no.isdecimal():
        return "no yok"
    tarih = datetime.fromisoformat(
        str(siparis.get("dateCreated")).replace("Z", "+00:00"))
    if tarih < baslangic:
        return "%s: baslangic oncesi" % no
    if kayit["arsivlendi"] or kayit["teslimat_durumu"] in IPTAL:
        return "%s: arsiv/iptal" % no

    yontem = str(kayit["odeme_yontemi"] or "").strip()
    if not yontem:
        atla(no, "odeme yontemi bos -- yol belirlenemedi")
        _alarm("odeme yolu belirsiz", "siparis %s: billingInfo.paymentMethod bos" % no)
        return "%s: ODEME YOLU BELIRSIZ, mesaj yok" % no

    if yontem in kapida_onay.KAPIDA_ODEME_YONTEMLERI:
        yol, sablon = "KAPIDA", SABLON_KAPIDA
        try:
            hazir = kapida_onay.taslak(kayit, whatsapp_izni=True)
        except kapida_onay.TeyitHatasi as hata:
            atla(no, "kapida teyit hazirlanamadi: %s" % hata)
            return "%s: kapida ATLANDI (%s)" % (no, hata)
        degerler = list(kapida_onay.sablon_parametreleri(hazir))
        telefon = hazir["telefon"]
        onizleme = kapida_onay.ayrinti_metni(hazir)
        urun_adi = (siparis.get("lineItems") or [{}])[0].get("name") or ""
    else:
        yol, sablon = "NORMAL", SABLON_NORMAL
        if kayit["odeme_durumu"] != "PAID":
            atla(no, "kapida degil ama odeme %s" % kayit["odeme_durumu"])
            return "%s: odenmemis (%s), mesaj yok" % (no, kayit["odeme_durumu"])
        try:
            degerler, telefon, urun_adi = normal_degerler(siparis)
        except ValueError as hata:
            atla(no, "normal teyit hazirlanamadi: %s" % hata)
            return "%s: normal ATLANDI (%s)" % (no, hata)
        onizleme = ONIZLEME_NORMAL.format(*degerler)

    if not kilit_al(kayit, yol, sablon, telefon):
        return "%s: zaten islenmis" % no

    gorsel = baslik_gorseli(urun_adi)
    try:
        sonuc = whatsapp.sablon_gonder(
            telefon, sablon, degerler, onay_kaynagi=whatsapp.ONAY_OTOMATIK,
            baslik_gorsel=gorsel, onizleme=onizleme, kuru=not gonder)
    except whatsapp.GondermeReddedildi as hata:
        kilit_kapat(no, "HATA", str(hata))
        _alarm("teyit gonderilemedi", "siparis %s (%s): %s" % (no, yol, hata))
        return "%s: %s GONDERILEMEDI -- %s" % (no, yol, hata)
    if sonuc.get("kuru"):
        kilit_kapat(no, "HATA", "kuru kosu")
        return "%s: %s KURU KOSU (gonderilmedi)" % (no, yol)
    kilit_kapat(no, "GONDERILDI", "", sonuc.get("wamid", ""))
    return "%s: %s GONDERILDI" % (no, yol)


def main() -> None:
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--gonder", action="store_true")
    ayristirici.add_argument("--adet", type=int, default=25)
    ayristirici.add_argument("--saat", type=int, default=72,
                             help="bu kadar saatten eski siparise bakilmaz")
    arg = ayristirici.parse_args()

    ham_baslangic = os.environ.get("SIPARIS_TEYIT_BASLANGIC", "")
    if ham_baslangic:
        baslangic = datetime.fromisoformat(ham_baslangic)
        if baslangic.tzinfo is None:
            raise SystemExit("SIPARIS_TEYIT_BASLANGIC saat dilimsiz")
    else:
        baslangic = datetime.now(timezone.utc) - timedelta(hours=arg.saat)
    baslangic = max(baslangic, datetime.now(timezone.utc) - timedelta(hours=arg.saat))

    for not_ in teslimat_isle():
        print(not_)

    for siparis in wix_siparisleri(arg.adet):
        print(isle(siparis, gonder=arg.gonder, baslangic=baslangic))


if __name__ == "__main__":
    main()
