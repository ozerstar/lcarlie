#!/usr/bin/env python3
"""GELEN KUTUSU NOBETI — siparis haberinin IKINCI, bagimsiz yolu.

NEDEN VAR
API nobetcisi yalniz bagladigimiz kanallari gorur. Hepsiburada'da 35 urun
SATISTA oldugu halde API kimligimiz yok; Idefix'in siparis ucu ise henuz
bilinmiyor. Bu kanallarda siparisi gorecegimiz tek yer, pazaryerinin
info@lcarlie.com.tr'ye attigi bildirim e-postasidir.

🔴 API ile AYNI tabloya yazar. Ayni siparisi ikisi de gorurse, veritabanindaki
   tekil dizin ikinci kaydi reddeder ve ikinci bildirim GITMEZ. Yani iki yol
   birbirini yedekler ama cift mesaj uretmez.

Kimlik: /root/.msmtprc icindeki Yandex kullanicisi -- alarm e-postasinin
kullandigi ayni hesap. Ayri bir sifre istenmez.

Kullanim:
  eposta-nobet.py --ogren        (son postalarin gonderen/konu desenini yaz)
  eposta-nobet.py --kuru         (esles ama yazma/gonderme)
  eposta-nobet.py                (esles, kaydet, haber ver)
"""
from __future__ import annotations

import argparse
import email
import imaplib
import re
import sys
from email.header import decode_header
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import haberci  # noqa: E402

MSMTPRC = Path("/root/.msmtprc")
SUNUCU = "imap.yandex.com"
SON_UID = Path("/opt/lcarlie/jarvis-phase2/state/eposta-nobet-son-uid.txt")
BAKILAN = 80          # her turda en fazla bu kadar son mesaja bakilir

# Gonderen alan adi -> kanal. Konu/govdeden siparis numarasi cikarilir.
# 🔴 Desenler OLCULEREK doldurulur; tahminle desen yazilmaz. --ogren kipi
#    gercek postalarin gonderen ve konularini basar, desen ondan tureticilir.
KANAL_DESENI: list[tuple[str, str, str]] = [
    # (kanal, gonderen icinde gecen, siparis numarasi regex'i)
    ("hepsiburada", "hepsiburada.com", r"\b(\d{10,14})\b"),
    ("trendyol", "trendyol.com", r"\b(\d{9,13})\b"),
    ("n11", "n11.com", r"\b(\d{9,13})\b"),
    ("idefix", "idefix.com", r"\b(\d{6,14})\b"),
    ("ciceksepeti", "ciceksepeti.com", r"\b(\d{6,14})\b"),
    ("pazarama", "pazarama.com", r"\b(\d{6,14})\b"),
    # Wix magaza postasi OLCULDU: "Yeni sipariş alındı (#10039)"
    ("wix", "stores-emails.com", r"#(\d{4,12})"),
]
# Konu bu kelimelerden birini icermiyorsa siparis bildirimi SAYILMAZ.
# (Kampanya/bulten postalari bildirim uretmesin.)
# 🔴 "satis" BILEREK YOK: n11'in "Magaza Gunluk Satis Durumu" bulteni her gun
#    gelir ve siparis bildirimi degildir. Olculerek cikarildi.
SIPARIS_KELIMELERI = ("sipariş", "siparis", "order")


def kimlik() -> tuple[str, str]:
    if not MSMTPRC.exists():
        raise RuntimeError("/root/.msmtprc yok — IMAP kimligi okunamiyor")
    alan: dict[str, str] = {}
    for satir in MSMTPRC.read_text(encoding="utf-8").splitlines():
        parca = satir.split(None, 1)
        if len(parca) == 2:
            alan.setdefault(parca[0].strip(), parca[1].strip())
    kul, sif = alan.get("user", ""), alan.get("password", "")
    if not (kul and sif):
        raise RuntimeError("msmtprc icinde user/password yok")
    return kul, sif


def coz(baslik: str | None) -> str:
    if not baslik:
        return ""
    parcalar = []
    for metin, kodlama in decode_header(baslik):
        if isinstance(metin, bytes):
            parcalar.append(metin.decode(kodlama or "utf-8", "replace"))
        else:
            parcalar.append(metin)
    return "".join(parcalar)


def baglan() -> imaplib.IMAP4_SSL:
    kul, sif = kimlik()
    m = imaplib.IMAP4_SSL(SUNUCU, 993, timeout=45)
    m.login(kul, sif)
    m.select("INBOX")
    return m


def basliklar(m: imaplib.IMAP4_SSL, kimlikler: list[bytes]):
    for i in kimlikler:
        tip, veri = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if tip != "OK" or not veri or not isinstance(veri[0], tuple):
            continue
        msg = email.message_from_bytes(veri[0][1])
        yield i, coz(msg.get("From")), coz(msg.get("Subject")), coz(msg.get("Date"))


def esle(gonderen: str, konu: str) -> tuple[str, str] | None:
    k = konu.casefold()
    if not any(x in k for x in SIPARIS_KELIMELERI):
        return None
    g = gonderen.casefold()
    for kanal, alan, desen in KANAL_DESENI:
        if alan in g:
            bulgu = re.search(desen, konu)
            return kanal, (bulgu.group(1) if bulgu else "")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ogren", action="store_true")
    ap.add_argument("--kuru", action="store_true")
    a = ap.parse_args()

    m = baglan()
    tip, veri = m.search(None, "ALL")
    kimlikler = veri[0].split()[-BAKILAN:]

    if a.ogren:
        print("%-44s | %s" % ("GONDEREN", "KONU"))
        for _, gonderen, konu, _tarih in basliklar(m, kimlikler):
            print("%-44s | %s" % (gonderen[:44], konu[:72]))
        m.logout()
        return 0

    gorulen = int(SON_UID.read_text().strip()) if SON_UID.exists() else 0
    en_buyuk = gorulen
    bulunan = 0
    for i, gonderen, konu, _tarih in basliklar(m, kimlikler):
        no = int(i)
        en_buyuk = max(en_buyuk, no)
        if no <= gorulen:
            continue
        sonuc = esle(gonderen, konu)
        if not sonuc:
            continue
        kanal, siparis_no = sonuc
        bulunan += 1
        print("%-12s %-16s %s" % (kanal, siparis_no or "(no yok)", konu[:60]))
        if a.kuru:
            continue
        if not siparis_no:
            # Numara cikarilamadi: siparisi KACIRMAKTANSA numarasiz haber ver.
            siparis_no = "eposta-%d" % no
        kimlik_satiri = haberci.psql(
            "INSERT INTO core.pazaryeri_siparis (kanal, siparis_no, durum, "
            "  musteri_ad, kaynak, ham) VALUES "
            "('%s', '%s', 'EPOSTA BILDIRIMI', '', 'eposta', "
            "  jsonb_build_object('konu', '%s')) "
            "ON CONFLICT DO NOTHING RETURNING id;"
            % (kanal, siparis_no.replace("'", "''"), konu.replace("'", "''")[:300]))
        if not kimlik_satiri:
            print("    (API zaten gormus, ikinci haber gitmez)")
            continue
        haber = haberci.bildir(int(kimlik_satiri), kanal=kanal + " (e-posta)",
                               siparis_no=siparis_no, tutar="-",
                               musteri="e-posta bildirimi", urunler=konu[:120])
        print("    ->", haber)

    if not a.kuru:
        SON_UID.parent.mkdir(parents=True, exist_ok=True)
        SON_UID.write_text(str(en_buyuk))
    print("bakilan: %d  eslesen: %d  son uid: %d" % (len(kimlikler), bulunan, en_buyuk))
    m.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
