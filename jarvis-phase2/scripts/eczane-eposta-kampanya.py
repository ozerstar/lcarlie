#!/usr/bin/env python3
"""Eczane e-posta kampanyası: info@lcarlie.com.tr'den, çalışma başına EN FAZLA bir e-posta.

Sahip 13.11.2026: "e-postası olan eczanelere de e-posta paylaşımlarını yap,
bir yandan kurumsal info'lu mailden". WhatsApp kampanyasıyla paralel yürür.

Her çalışmada:
  1. Gelen kutusu (IMAP, aynı info@ hesabı): kampanya gönderdiğimiz adresten
     gelen cevap -> eczane_etkilesim YANIT + push; geri dönen (bounce) posta
     -> adres GECERSIZ, bir daha denenmez.
  2. Frenler: hafta içi 10-18, DURDUR dosyası, günlük tavan, geri dönme oranı.
  3. Sıradaki eczaneye tek e-posta (kişiye özel randevu ve çıkış bağlantısı).

Yalnız doğrulaması GECERLI ya da BELIRSIZ (hotmail/yahoo yoklamaya cevap
vermez) adresler. GECERSIZ ve denetlenmemiş adrese gönderilmez: info@ şirketin
ana adresi, geri dönen posta onun itibarını düşürür.
"""
from __future__ import annotations

import email
import imaplib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

TR = timezone(timedelta(hours=3))
# "Ankara" ya da "*" (tüm iller, il önceliğiyle: Ankara -> büyükşehirler -> diğer).
# Diğer iller sahip onayıyla açılır: /etc/lcarlie/eczane-eposta.env -> ECZANE_EPOSTA_IL=*
IL = os.environ.get("ECZANE_EPOSTA_IL", "Ankara")
SABLON = Path(os.environ.get("ECZANE_EPOSTA_SABLON", str(Path(__file__).with_name("eczane-mail-ankara.html"))))
SABLON_GENEL = Path(__file__).with_name("eczane-mail-genel.html")
KONU = "Doğal ve bitkisel içerikli dermokozmetik: L’CARLIÉ ile 15 dakikalık bir tanışma"
KONU_GENEL = "Sizi ziyaret etmemizi ister misiniz? L’CARLIÉ doğal ve bitkisel dermokozmetik"
GONDEREN = "info@lcarlie.com.tr"
PENCERE = (10, 18)
GUNLUK_TAVAN = int(os.environ.get("ECZANE_EPOSTA_GUNLUK", "150"))
GERI_DONME_ORANI = 0.08              # gönderilenin %8'i geri dönerse dur
DURUM = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "eczane-eposta"
DURDUR = DURUM / "DURDUR"
MSMTPRC = Path("/root/.msmtprc")
KATALOG = "https://www.lcarlie.shop/_files/ugd/92cdbf_9a439a7872ad438ca0e0c7f6f908fe87.pdf"


def psql(sql: str, **v: str) -> list[dict]:
    arg = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At",
           "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1"]
    for k, d in v.items():
        arg += ["-v", "%s=%s" % (k, d)]
    p = subprocess.run(arg, input=sql, capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:400])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip().startswith("{")]


def push(baslik: str, metin: str) -> None:
    try:
        from jarvis import haberci
        haberci.push_gonder(baslik, metin, "eczane-eposta")
    except Exception as e:  # noqa: BLE001 - bildirim gitmese de kayıt durur
        print("push gitmedi:", e)


def durdur(sebep: str) -> None:
    if not DURDUR.exists():
        DURUM.mkdir(parents=True, exist_ok=True)
        DURDUR.write_text(datetime.now(TR).isoformat() + " " + sebep + "\n")
        push("⛔ Eczane e-posta kampanyası DURDU", sebep)
    print("DURDU:", sebep)


def kimlik() -> tuple[str, str]:
    alan: dict[str, str] = {}
    for satir in MSMTPRC.read_text(encoding="utf-8").splitlines():
        parca = satir.split(None, 1)
        if len(parca) == 2:
            alan.setdefault(parca[0].strip(), parca[1].strip())
    return alan.get("user", ""), alan.get("password", "")


class IMAP4v4(imaplib.IMAP4_SSL):
    """Yalnız IPv4. Sunucunun IPv6 yolu yok; create_connection bazen önce
    IPv6 adresini deneyip [Errno 101] ile düşüyordu (13.11 ölçüldü)."""

    def _create_socket(self, timeout):
        import socket
        adres = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)[0][4]
        ham = socket.create_connection(adres, timeout)
        return self.ssl_context.wrap_socket(ham, server_hostname=self.host)


def coz(b: str | None) -> str:
    try:
        return str(make_header(decode_header(b or "")))
    except (UnicodeDecodeError, LookupError):
        return b or ""


# ------------------------------------------------------- 1. cevap ve geri dönme
def gelenleri_isle() -> None:
    gonderilen = {r["eposta"]: r for r in psql("""
      SELECT row_to_json(x) FROM (
        SELECT DISTINCT ON (lower(e.ayrinti->>'eposta')) lower(e.ayrinti->>'eposta') AS eposta,
               e.hedef_id, h.eczane, h.ilce
        FROM core.eczane_etkilesim e JOIN core.eczane_hedef h ON h.id = e.hedef_id
        WHERE e.tur = 'GONDERILDI' AND e.ayrinti->>'kanal' = 'eposta'
          AND coalesce(e.ayrinti->>'test','false') <> 'true'
      ) x;""")}
    if not gonderilen:
        return
    gorulen_dosya = DURUM / "gorulen.json"
    try:
        gorulen = set(json.loads(gorulen_dosya.read_text()))
    except (OSError, ValueError):
        gorulen = set()
    # 🔴 Yandex IMAP komut ortasında bağlantıyı kesiyor ("FETCH/UID => problems
    # with connection", 13.11, defalarca). Kural: (1) yalnız YENİ UID'ler,
    # (2) başlıklar 20'lik gruplar halinde tek komutla, (3) gövde yalnız bizim
    # adresimizden gelen cevapta ya da geri dönen postada, (4) kopunca yeniden
    # bağlanıp KALDIĞI YERDEN sürer (en çok 4 kez). Görülen UID her adımda
    # kaydedilir; kopma bir sonraki çalışmada işi baştan yaptırmaz.
    kul, sif = kimlik()
    tarih = (datetime.now(TR) - timedelta(days=7)).strftime("%d-%b-%Y")
    m = None
    try:
        bekleyen: list[bytes] | None = None
        for deneme in range(5):
            try:
                if m is None:
                    m = IMAP4v4("imap.yandex.com", 993, timeout=45)
                    m.login(kul, sif)
                    m.select("INBOX", readonly=True)       # okundu işareti DEĞİŞMEZ
                if bekleyen is None:
                    _, veri = m.uid("search", None, "SINCE", tarih)
                    bekleyen = [u for u in (veri[0] or b"").split()[-400:]
                                if "uid:" + u.decode() not in gorulen]
                while bekleyen:
                    grup, kalan = bekleyen[:20], bekleyen[20:]
                    _, parcalar = m.uid("fetch", b",".join(grup),
                                        "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)])")
                    for parca in parcalar or []:
                        if not isinstance(parca, tuple):
                            continue
                        u = re.search(rb"UID (\d+)", parca[0])
                        if not u:
                            continue
                        _mesaj_isle(m, u.group(1), email.message_from_bytes(parca[1]), gonderilen)
                    gorulen.update("uid:" + x.decode() for x in grup)
                    bekleyen = kalan
                break
            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as hata:
                print("gelen kutusu bağlantısı koptu (%d. deneme, %d mesaj kaldı): %s"
                      % (deneme + 1, len(bekleyen or []), str(hata)[:80]))
                try:
                    if m is not None:
                        m.shutdown()
                except (OSError, imaplib.IMAP4.error):
                    pass
                m = None
    finally:
        try:
            if m is not None:
                m.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
        DURUM.mkdir(parents=True, exist_ok=True)
        gorulen_dosya.write_text(json.dumps(sorted(gorulen)[-5000:]))


def _mesaj_isle(m, uid: bytes, baslik, gonderilen: dict) -> None:
    """Tek mesaj: bizim gönderdiğimiz adresten cevap ya da geri dönen posta mı?

    Aynı cevap iki kez işlenmez: message_id etkileşim kaydında aranır (UID
    kaydı kopmadan önce yazılamamış olsa bile).
    """
    mid = (baslik.get("Message-ID") or "uid:" + uid.decode()).strip()
    kimden = parseaddr(baslik.get("From") or "")[1].lower()
    konu = coz(baslik.get("Subject"))
    geri = bool("mailer-daemon" in kimden or "postmaster" in kimden
                or re.search(r"undeliver|delivery status|teslim edilemedi|returned mail|failure", konu, re.I))
    if kimden not in gonderilen and not geri:
        return
    if psql("SELECT row_to_json(x) FROM (SELECT 1 AS var FROM core.eczane_etkilesim"
            " WHERE ayrinti->>'message_id' = :'i' LIMIT 1) x;", i=mid):
        return
    _, parca = m.uid("fetch", uid, "(BODY.PEEK[])")
    ham = parca[0][1] if parca and isinstance(parca[0], tuple) else b""
    msj = email.message_from_bytes(ham)
    govde = ""
    for p in msj.walk():
        if p.get_content_type() == "text/plain":
            try:
                govde = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
            except (AttributeError, LookupError):
                govde = ""
            break
    if geri:
        tum = ham.decode("utf-8", "replace").lower()
        for adres, r in gonderilen.items():
            if adres in govde.lower() or adres in tum:
                psql("UPDATE core.eczane_eposta SET dogrulama = 'GECERSIZ', dogrulandi = now()"
                     " WHERE lower(eposta) = :'e';"
                     " INSERT INTO core.eczane_etkilesim (hedef_id, tur, ayrinti) VALUES (:'h', 'NOT',"
                     " jsonb_build_object('kanal','eposta','olay','geri_dondu','eposta', :'e','message_id', :'i'));",
                     e=adres, h=str(r["hedef_id"]), i=mid)
                print("GERI DONDU", adres)
        return
    r = gonderilen[kimden]
    ozet = re.split(r"\n\s*(>|On .+wrote:|.+ tarihinde .+ yazdı:)", govde.strip(), maxsplit=1)[0].strip()[:1000]
    red = bool(re.search(r"\b(istemiyorum|listeden çıkar|göndermeyin|abonelikten)\b", ozet, re.I))
    psql("INSERT INTO core.eczane_etkilesim (hedef_id, tur, ayrinti) VALUES (:'h', :'t',"
         " jsonb_build_object('kanal','eposta','eposta', :'e','konu', :'k','metin', :'m','message_id', :'i'));"
         + (" UPDATE core.eczane_hedef SET durum='CIKTI', guncellendi=now() WHERE id = :'h';" if red else
            " UPDATE core.eczane_hedef SET durum='ILGILENDI', guncellendi=now()"
            " WHERE id = :'h' AND durum IN ('YENI','GONDERILDI');"),
         h=str(r["hedef_id"]), t="CIKIS" if red else "YANIT", e=kimden, k=konu[:200], m=ozet, i=mid)
    push("📧 Eczane e-postaya cevap verdi" if not red else "Eczane e-posta listesinden çıktı",
         "%s%s: %s" % (r["eczane"], " (" + r["ilce"] + ")" if r.get("ilce") else "", ozet[:180]))
    print("YANIT" if not red else "CIKIS", kimden)


# ------------------------------------------------------------------ 2. frenler
def frenler() -> bool:
    simdi = datetime.now(TR)
    if simdi.weekday() >= 5 or not (PENCERE[0] <= simdi.hour < PENCERE[1]) or DURDUR.exists():
        return False
    o = psql("""SELECT row_to_json(x) FROM (SELECT
        count(*) FILTER (WHERE tur='GONDERILDI' AND zaman > now() - interval '24 hours') AS son24,
        count(*) FILTER (WHERE tur='GONDERILDI') AS toplam,
        count(*) FILTER (WHERE tur='NOT' AND ayrinti->>'olay' = 'geri_dondu') AS geri
      FROM core.eczane_etkilesim WHERE ayrinti->>'kanal' = 'eposta'
        AND coalesce(ayrinti->>'test','false') <> 'true') x;""")[0]
    if o["toplam"] >= 25 and o["geri"] / o["toplam"] > GERI_DONME_ORANI:
        durdur("Geri dönen e-posta oranı yüksek (%d/%d)." % (o["geri"], o["toplam"]))
        return False
    return o["son24"] < GUNLUK_TAVAN


# ------------------------------------------------------------------ 3. gönderim
SIRADAKI = """
SELECT row_to_json(x) FROM (
  -- Eski listede "İ" çoğu yerde düz "I" yazılmış ("DEMIRTEPE" -> "Demırtepe" gitti).
  -- Odanın nöbet kaydı ve Google adı doğru yazımlı: varsa o kullanılır.
  SELECT DISTINCT ON (h.oncelik, h.id) h.id, h.il,
         coalesce((SELECT k.ad FROM raw.eczane_kaynak k
                   WHERE k.hedef_id = h.id AND k.kaynak IN ('AEO_NOBET', 'GMAPS') AND k.ad ILIKE '%eczane%'
                   ORDER BY (k.kaynak = 'AEO_NOBET') DESC LIMIT 1), h.eczane) AS eczane,
         h.eczaci, h.anahtar, lower(e.eposta) AS eposta
  FROM core.eczane_hedef h
  JOIN core.eczane_eposta e ON e.hedef_id = h.id AND e.dogrulama IN ('GECERLI','BELIRSIZ')
  WHERE (:'il' = '*' OR h.il = :'il') AND h.durum NOT IN ('GECERSIZ','CIKTI','ILGISIZ')
    AND NOT ('TEST' = ANY (h.etiketler))
    AND NOT EXISTS (SELECT 1 FROM core.eczane_etkilesim x
                    WHERE x.tur = 'GONDERILDI' AND x.ayrinti->>'kanal' = 'eposta'
                      AND (x.hedef_id = h.id OR lower(x.ayrinti->>'eposta') = lower(e.eposta)))
  ORDER BY h.oncelik, h.id, (e.dogrulama = 'GECERLI') DESC
  LIMIT 1
) x;"""


def baslik_hali(ad: str) -> str:
    s = re.sub(r"\s+", " ", ad or "").strip()
    s = " ".join(k[:1] + k[1:].replace("I", "ı").replace("İ", "i").lower() for k in s.split(" "))
    if s.lower().endswith(" eczane"):
        s += "si"                                   # "1923 Eczane" -> "1923 Eczanesi"
    elif "eczane" not in s.lower():
        s += " Eczanesi"
    return s


def yonelme(il: str) -> str:
    """İl adına yönelme eki: İstanbul’a, İzmir’e, Bursa’ya, Rize’ye."""
    unluler = [h for h in il.lower() if h in "aeıioöuü"]
    son = unluler[-1] if unluler else "e"
    ek = "a" if son in "aıou" else "e"
    return il + "’" + ("y" + ek if il[-1].lower() in "aeıioöuü" else ek)


def buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def mailto(konu: str, govde: str) -> str:
    from urllib.parse import quote
    return "mailto:%s?subject=%s&body=%s" % (GONDEREN, quote(konu), quote(govde))


def icerik(a: dict) -> tuple[str, str, str]:
    """(konu, html, düz metin). Ankara: saat seçimli randevu; diğer iller: ortak gün + beni arayın."""
    eczane = baslik_hali(a["eczane"])
    hitap = ("Ecz. " + baslik_hali(a["eczaci"]).replace(" Eczanesi", "")) if a.get("eczaci") else "Eczacımız"
    cikis = "https://n8n.lcarlie.shop/randevu/cikis?t=" + a["anahtar"]
    ortak = ("L’CARLIÉ, doğal ve bitkisel içeriklerle formüle edilmiş bir dermokozmetik markasıdır. "
             "Serimiz sekiz bakım grubunda 36 üründen oluşur: yüz bakımı, bebek ve çocuk bakımı, vücut bakımı, "
             "masaj ve spor, ağız bakımı, ayak bakımı, kadın ve erkek bakımı, saç ve ev bakımı.\n\n")
    alt = ("Katalog: %s\n\nSaygılarımızla,\nL’CARLIÉ Eczane İlişkileri · Tel: 0542 188 69 37 · WhatsApp: 0544 544 21 15\n\n"
           "Bu e-postayı almak istemiyorsanız: %s" % (KATALOG, cikis))
    if a["il"] == "Ankara":
        sablon, konu = SABLON, KONU
        randevu = "https://n8n.lcarlie.shop/randevu?t=" + a["anahtar"]
        duz = ("Sayın %s,\n\n%sSerimizi %s’nde 15 dakikalık bir ziyaretle tanıtmak isteriz. "
               "Size uygun gün ve saati seçin:\n%s\n\n%s" % (hitap, ortak, eczane, randevu, alt))
        degis = {}
    else:
        sablon, konu = SABLON_GENEL, KONU_GENEL
        ziyaret = mailto("Ziyaret talebi – %s (%s)" % (eczane, a["il"]),
                         "Merhaba,\n\n%s olarak L’CARLIÉ ürünlerini tanımak için ziyaretinizi isteriz.\n"
                         "Bizim için uygun gün(ler): \nYetkili ve telefon: \n" % eczane)
        ara = mailto("Beni arayın – %s (%s)" % (eczane, a["il"]),
                     "Merhaba,\n\nL’CARLIÉ hakkında detaylı bilgi almak istiyoruz.\n"
                     "Telefon: \nUygun arama saati: \n")
        degis = {"{{il_buyuk}}": buyuk(a["il"]), "{{il_e}}": yonelme(a["il"]), "{{il}}": a["il"],
                 "{{mailto_ziyaret}}": ziyaret.replace("&", "&amp;"), "{{mailto_ara}}": ara.replace("&", "&amp;")}
        duz = ("Sayın %s,\n\nSizi ziyaret etmemizi ister misiniz?\n\n%s"
               "Serimizi %s’nde tanıtmak için %s gelmek isteriz; sizinle ortak bir gün belirleyelim. "
               "Detaylı bilgi için bu e-postayı yanıtlamanız yeterli: uygun gününüzü ya da telefon numaranızı "
               "yazın, sizi arayalım.\n\n%s" % (hitap, ortak, eczane, yonelme(a["il"]), alt))
    html = re.sub(r"<!--.*?-->", "", sablon.read_text(encoding="utf-8"), flags=re.S)
    for anahtar, deger in {"{{eczaci_hitap}}": hitap, "{{eczane_adi}}": eczane,
                           "{{anahtar}}": a["anahtar"], **degis}.items():
        html = html.replace(anahtar, deger)
    return konu, html, duz


def gonder_bir() -> None:
    adaylar = psql(SIRADAKI, il=IL)
    if not adaylar:
        print("gönderilecek eczane kalmadı")
        return
    a = adaylar[0]
    eczane = baslik_hali(a["eczane"])
    konu, html, duz = icerik(a)
    cikis = "https://n8n.lcarlie.shop/randevu/cikis?t=" + a["anahtar"]
    mid = make_msgid(domain="lcarlie.com.tr")
    m = EmailMessage()
    m["From"] = "L’CARLIÉ Eczane İlişkileri <%s>" % GONDEREN
    m["To"] = a["eposta"]
    m["Reply-To"] = GONDEREN
    m["Subject"] = konu
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = mid
    m["List-Unsubscribe"] = "<%s>, <mailto:%s?subject=Listeden%%20cikar>" % (cikis, GONDEREN)
    m.set_content(duz)
    m.add_alternative(html, subtype="html")
    s = subprocess.run(["/usr/bin/msmtp", "--from=" + GONDEREN, "-t"], input=m.as_bytes(),
                       capture_output=True, timeout=90)
    if s.returncode:
        hata = s.stderr.decode("utf-8", "replace")[:300]
        print("GONDERILEMEDI", a["eposta"], hata)
        # SMTP kotası/engeli: o gün daha deneme
        if re.search(r"quota|limit|spam|blocked|554|550 5\.7|too many", hata, re.I):
            durdur("SMTP gönderimi reddetti: " + hata[:160])
        return
    psql("INSERT INTO core.eczane_etkilesim (hedef_id, tur, ayrinti) VALUES (:'h', 'GONDERILDI',"
         " jsonb_build_object('kanal','eposta','eposta', :'e','message_id', :'i','konu', :'k'));"
         " UPDATE core.eczane_hedef SET durum = 'GONDERILDI', guncellendi = now() WHERE id = :'h' AND durum = 'YENI';",
         h=str(a["id"]), e=a["eposta"], i=mid, k=konu)
    print("GONDERILDI", a["id"], eczane, a["eposta"])


def main() -> None:
    DURUM.mkdir(parents=True, exist_ok=True)
    try:
        gelenleri_isle()
    except (imaplib.IMAP4.error, OSError, RuntimeError) as e:
        print("gelen kutusu okunamadı:", e)
    if "--kuru" in sys.argv:
        print("kuru koşu: fren", frenler(), "sıradaki", psql(SIRADAKI, il=IL))
        return
    if frenler():
        gonder_bir()


if __name__ == "__main__":
    main()
