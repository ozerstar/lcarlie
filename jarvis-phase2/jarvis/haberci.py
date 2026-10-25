"""Sahibe bildirim yayini: Web Push + WhatsApp + e-posta.

AMAC: bir siparis UC AYRI yoldan haber verilir. Bir yol sessizce olurse
oteki ikisi ulasir. "Haber verildi" demek icin en az BIR yolun GONDERILDI
olmasi gerekir; hicbiri olmadiysa nobetci alarm uretir.

🔴 Kilit: her (siparis, yol) icin core.siparis_bildirim'de TEK satir vardir
ve satir INSERT edilmeden aga cikilmaz. 23.10.2026'da ayni musteriye uc
mesaj gitmesinin kok nedeni buydu -- psql cikti kontrolu yanlisti,
`-tAq` kullanilmadigi icin "UPDATE 0" etiketi "kilit acildi" sanildi.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

SAHIP_TELEFON = os.environ.get("NOBETCI_TELEFON", "905421886937")
SAHIP_EPOSTA = [e.strip() for e in os.environ.get(
    "NOBETCI_EPOSTA", "moy.ozeryildiz@gmail.com,info@lcarlie.com.tr").split(",")
    if e.strip()]
SABLON = os.environ.get("NOBETCI_SABLON", "lcarlie_yeni_siparis_v1")
EN_FAZLA_DENEME = 20
YOLLAR = ("push", "whatsapp", "eposta")


class BildirimHatasi(RuntimeError):
    pass


def psql(sorgu: str) -> str:
    """🔴 -tAq SART: -q olmadan psql, satir donmeyen INSERT icin bile
    "INSERT 0 1" komut etiketi basar ve bos olmayan cikti kilit acilmis
    sanilir."""
    s = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n",
         "-d", "n8n", "-v", "ON_ERROR_STOP=1", "-tAq"],
        input=sorgu, capture_output=True, text=True)
    if s.returncode != 0:
        raise BildirimHatasi("psql: " + s.stderr.strip()[:200])
    return s.stdout.strip()


def _m(deger: Any) -> str:
    return "'" + str(deger if deger is not None else "").replace("'", "''") + "'"


# ------------------------------------------------------------------- kilitler
def kilit_al(siparis_id: int, yol: str) -> bool:
    """Bu yol icin satiri BIZ actiysak True. Baskasi actiysa/acilmissa False.
    HATA durumundaki satir, deneme hakki varsa yeniden alinabilir."""
    acildi = psql(
        "INSERT INTO core.siparis_bildirim (siparis_id, yol, durum, deneme) "
        "VALUES (%d, %s, 'GONDERILIYOR', 1) "
        "ON CONFLICT (siparis_id, yol) DO UPDATE "
        "  SET durum = 'GONDERILIYOR', deneme = core.siparis_bildirim.deneme + 1, "
        "      guncelleme = now() "
        "WHERE core.siparis_bildirim.durum = 'HATA' "
        "  AND core.siparis_bildirim.deneme < %d "
        "RETURNING id;" % (siparis_id, _m(yol), EN_FAZLA_DENEME))
    return bool(acildi)


def kilit_kapat(siparis_id: int, yol: str, durum: str, *,
                dis_kimlik: str = "", hata: str = "") -> None:
    psql("UPDATE core.siparis_bildirim SET durum = %s, dis_kimlik = %s, "
         "hata = %s, guncelleme = now() "
         "WHERE siparis_id = %d AND yol = %s;"
         % (_m(durum), _m(dis_kimlik), _m(hata[:400]), siparis_id, _m(yol)))


# ---------------------------------------------------------------------- push
def push_gonder(baslik: str, metin: str, etiket: str) -> str:
    import push_store
    from pywebpush import WebPushException, webpush

    aboneler = push_store.all_subscriptions()
    if not aboneler:
        raise BildirimHatasi("push abonesi yok")
    ulasan = 0
    son_hata = ""
    for abone in aboneler.values():
        try:
            webpush(
                subscription_info={"endpoint": abone["endpoint"], "keys": abone["keys"]},
                data=json.dumps({"title": baslik, "body": metin[:150],
                                 "tag": etiket}, ensure_ascii=False),
                vapid_private_key=str(push_store.PRIVATE_KEY_FILE),
                vapid_claims={"sub": "https://jarvis.lcarlie.shop"},
                ttl=86400, timeout=10)
            ulasan += 1
        except WebPushException as hata:
            kod = getattr(getattr(hata, "response", None), "status_code", None)
            if kod in (404, 410):
                push_store.remove(abone["endpoint"])
            son_hata = "push %s" % kod
    if not ulasan:
        raise BildirimHatasi(son_hata or "hicbir aboneye ulasilamadi")
    return "%d abone" % ulasan


# ------------------------------------------------------------------ whatsapp
def whatsapp_gonder(degerler: list[str]) -> str:
    from jarvis import whatsapp
    sonuc = whatsapp.sablon_gonder(SAHIP_TELEFON, SABLON, degerler,
                                   onay_kaynagi="jarvis-otomatik")
    return str(sonuc.get("wamid") or "")


# -------------------------------------------------------------------- eposta
# 🔴 IKI AYRI YOL, SIRAYLA. Gmail'in jetonu 25.10.2026'da yenilenemez
#    durumdaydi (refresh 400) -- tek yola guvenen tasarim o gun sessizce
#    e-postasiz kalirdi. msmtp birincil, Gmail yedektir.
MSMTP = "/usr/bin/msmtp"
GONDEREN = os.environ.get("NOBETCI_GONDEREN", "info@lcarlie.com.tr")


def _msmtp_gonder(konu: str, govde: str) -> str:
    from email.message import EmailMessage

    mesaj = EmailMessage()
    mesaj["From"] = GONDEREN
    mesaj["To"] = ", ".join(SAHIP_EPOSTA)
    mesaj["Subject"] = konu
    mesaj.set_content(govde)
    s = subprocess.run([MSMTP, "--from=" + GONDEREN, "-t"],
                       input=mesaj.as_bytes(), capture_output=True, timeout=60)
    if s.returncode != 0:
        raise BildirimHatasi("msmtp %d: %s"
                             % (s.returncode, s.stderr.decode("utf-8", "replace")[:160]))
    return "msmtp"


def _gmail_gonder(konu: str, govde: str) -> str:
    """Sahibin KENDI hesabindan KENDI adreslerine gider; disariya mesaj
    degildir, bu yuzden onay kuyruguna girmez."""
    import base64
    from email.message import EmailMessage

    import google_workspace

    jeton = google_workspace._access_token("operator")
    mesaj = EmailMessage()
    mesaj["To"] = ", ".join(SAHIP_EPOSTA)
    mesaj["Subject"] = konu
    mesaj.set_content(govde)
    ham = base64.urlsafe_b64encode(mesaj.as_bytes()).decode()
    istek = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": ham}).encode(),
        headers={"Authorization": "Bearer " + jeton,
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(istek, timeout=40) as y:
        return "gmail:" + str(json.loads(y.read().decode()).get("id") or "")


def eposta_gonder(konu: str, govde: str) -> str:
    try:
        return _msmtp_gonder(konu, govde)
    except Exception as ilk:                            # noqa: BLE001
        try:
            return _gmail_gonder(konu, govde)
        except Exception as ikinci:                     # noqa: BLE001
            raise BildirimHatasi(
                "iki yol da basarisiz — msmtp: %s | gmail: %s"
                % (str(ilk)[:80], str(ikinci)[:80])) from None


# --------------------------------------------------------------------- yayin
def bildir(siparis_id: int, *, kanal: str, siparis_no: str, tutar: str,
           musteri: str, urunler: str, yollar: tuple[str, ...] = YOLLAR,
           kuru: bool = False) -> dict[str, str]:
    """Her yolu AYRI dener. Birinin dusmesi otekini engellemez."""
    baslik = "🛎️ %s · yeni sipariş" % kanal.upper()
    ozet = "%s · %s TL · %s · %s" % (siparis_no, tutar, musteri, urunler)
    uzun = ("Kanal     : %s\nSipariş no: %s\nTutar     : %s TL\n"
            "Müşteri   : %s\nÜrünler   : %s\n\nPanel: https://jarvis.lcarlie.shop"
            % (kanal, siparis_no, tutar, musteri, urunler))
    sonuc: dict[str, str] = {}
    for yol in yollar:
        if kuru:
            sonuc[yol] = "KURU"
            continue
        if not kilit_al(siparis_id, yol):
            sonuc[yol] = "ATLANDI (kilit)"
            continue
        try:
            if yol == "push":
                kimlik = push_gonder(baslik, ozet, "siparis-%d" % siparis_id)
            elif yol == "whatsapp":
                kimlik = whatsapp_gonder([kanal, siparis_no, tutar, musteri, urunler])
            elif yol == "eposta":
                kimlik = eposta_gonder(baslik + " " + siparis_no, uzun)
            else:
                raise BildirimHatasi("bilinmeyen yol: %s" % yol)
            kilit_kapat(siparis_id, yol, "GONDERILDI", dis_kimlik=kimlik)
            sonuc[yol] = "GONDERILDI"
        except Exception as hata:                      # noqa: BLE001
            kilit_kapat(siparis_id, yol, "HATA",
                        hata="%s: %s" % (type(hata).__name__, hata))
            sonuc[yol] = "HATA: %s" % str(hata)[:80]
    return sonuc
