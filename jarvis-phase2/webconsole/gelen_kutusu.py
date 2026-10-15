# -*- coding: utf-8 -*-
"""GELEN KUTUSU — müşteri konuşmaları, devir durumu ve taslak cevap.

Sahip 15.10.2026: *"burdan jarvis mesajlara cevap versin, gerektiğinde bana
devretsin ben konuşayım."*

🔴 BU MODÜL MESAJ GÖNDERMEZ. `satis_dialog` gibi: okur, taslak ürettirir,
devir durumunu yazar. Gönderme ayrı bir modülün (`jarvis.whatsapp`) ve ayrı
bir sahip eyleminin işidir. Panelde "gönder" demeden hiçbir şey çıkmaz.

🔴 CEVAPSIZ TANIMI ÖLÇÜME DAYANIR. Bir konuşma, SON mesajı müşteriden
geldiyse cevapsızdır. "Okunmamış" değil -- okunmuşluk bilgisi bizde yok ve
olmayan bir alanı varmış gibi göstermek panelin yalan söylemesidir.
(Meta panelindeki okunmamış filtresi de cevapsız mesajı gizliyordu;
aynı tuzağa düşmüyoruz.)
"""
from __future__ import annotations

import json
import re
import subprocess
from urllib.parse import quote
from jarvis.db_transport import run as db_run

from jarvis import devir

KAP = "lcarlie-postgres"
VARSAYILAN_LIMIT = 60


class KutuHatasi(RuntimeError):
    pass


def _tirnak(deger) -> str:
    """SQL icin guvenli tirnak. Parametreli surucu yok; psql -f - kullaniyoruz."""
    if deger is None:
        return "NULL"
    return "'" + str(deger).replace("'", "''") + "'"


def _calistir(sql: str) -> list:
    try:
        p = db_run(
            ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.SubprocessError) as hata:
        raise KutuHatasi("veritabani calistirilamadi: %s" % hata) from None
    if p.returncode:
        raise KutuHatasi((p.stderr or p.stdout)[:300])
    return [json.loads(s) for s in p.stdout.split("\n") if s.strip()]


def konusmalar(durum: str | None = None, limit: int = VARSAYILAN_LIMIT) -> list[dict]:
    """Konuşma listesi. `durum` verilirse yalnız o devir durumundakiler."""
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = VARSAYILAN_LIMIT
    kosul = ""
    if durum:
        if durum not in {"JARVIS", "INSANDA", "KAPALI"}:
            raise KutuHatasi("gecersiz devir durumu: %s" % durum)
        kosul = "WHERE k.devir_durumu = %s" % _tirnak(durum)
    sql = f"""
    SELECT row_to_json(x) FROM (
      SELECT k.id, k.kanal, k.harici_id,
             COALESCE(NULLIF(k.musteri_ad,''), k.musteri_ref, k.harici_id) AS musteri,
             k.mesaj_sayisi, k.son_mesaj, k.devir_durumu, k.devir_sebep,
             s.metin AS son_metin, s.yon AS son_yon, s.sinif AS son_sinif,
             (s.yon = 'gelen') AS cevapsiz
      FROM lcarlie.konusma k
      LEFT JOIN LATERAL (
        SELECT m.metin, m.yon, m.sinif FROM lcarlie.mesaj m
        WHERE m.konusma_id = k.id ORDER BY m.zaman DESC LIMIT 1
      ) s ON TRUE
      {kosul}
      ORDER BY k.son_mesaj DESC NULLS LAST
      LIMIT {limit}
    ) x;
    """
    return _calistir(sql)


def konusma(konusma_id: int, limit: int = 60) -> dict:
    """Tek konuşma: başlık bilgisi + mesajlar (eskiden yeniye)."""
    kid = int(konusma_id)
    try:
        limit = max(1, min(int(limit), 300))
    except (TypeError, ValueError):
        limit = 60
    bas = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT k.id, k.kanal, k.harici_id,
             COALESCE(NULLIF(k.musteri_ad,''), k.musteri_ref, k.harici_id) AS musteri,
             k.musteri_ref, k.mesaj_sayisi, k.son_mesaj,
             k.devir_durumu, k.devir_sebep, k.devir_zaman
      FROM lcarlie.konusma k WHERE k.id = {kid}
    ) x;
    """)
    if not bas:
        raise KutuHatasi("konusma bulunamadi: %s" % kid)
    mesajlar = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.id, m.zaman, m.yon, m.gonderen, m.metin, m.sinif, m.mevzuat
      FROM lcarlie.mesaj m WHERE m.konusma_id = {kid}
      ORDER BY m.zaman DESC LIMIT {limit}
    ) x;
    """)
    kayit = bas[0]
    kayit["mesajlar"] = list(reversed(mesajlar))
    kayit["devir_sebep_metni"] = devir.sebep_aciklamasi(kayit.get("devir_sebep"))
    return kayit


def durum_yaz(konusma_id: int, yeni_durum: str, sebep: str | None = None) -> dict:
    """Devir durumunu değiştirir. Geçersiz durum CHECK ile reddedilir."""
    if yeni_durum not in {"JARVIS", "INSANDA", "KAPALI"}:
        raise KutuHatasi("gecersiz devir durumu: %s" % yeni_durum)
    kid = int(konusma_id)
    # 🔴 UPDATE BIR ALT SORGUDA DURAMAZ. Ilk hali
    # `SELECT row_to_json(x) FROM (UPDATE ... RETURNING) x` yaziyordu ve
    # PostgreSQL bunu sozdizimi hatasiyla reddediyor: veri degistiren
    # ifadeler yalniz CTE icinde yazilabilir. Okuma yollari calistigi icin
    # kusur ancak YAZMA denendiginde gorundu -- panelin devir dugmesi
    # sessizce degil, gurultuyle kirilirdi ama hic denenmeseydi
    # "calisiyor" diye bildirilecekti.
    sonuc = _calistir(f"""
    WITH g AS (
      UPDATE lcarlie.konusma
         SET devir_durumu = {_tirnak(yeni_durum)},
             devir_sebep  = {_tirnak(sebep)},
             devir_zaman  = now(),
             guncelleme   = now()
       WHERE id = {kid}
      RETURNING id, devir_durumu, devir_sebep, devir_zaman
    )
    SELECT row_to_json(g) FROM g;
    """)
    if not sonuc:
        raise KutuHatasi("konusma bulunamadi: %s" % kid)
    kayit = sonuc[0]
    kayit["devir_sebep_metni"] = devir.sebep_aciklamasi(kayit.get("devir_sebep"))
    return kayit


def devir_onerisi(konusma_id: int) -> dict:
    """Son gelen mesaja göre devir önerisi. Hiçbir şey yazmaz."""
    kid = int(konusma_id)
    satir = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.sinif, m.mevzuat, m.metin, (k.notlar->>'urun') AS urun
      FROM lcarlie.mesaj m JOIN lcarlie.konusma k ON k.id = m.konusma_id
      WHERE m.konusma_id = {kid} AND m.yon = 'gelen'
      ORDER BY m.zaman DESC LIMIT 1
    ) x;
    """)
    if not satir:
        return {"devir": True, "sebep": devir.SINIF_YOK,
                "sebep_metni": devir.sebep_aciklamasi(devir.SINIF_YOK),
                "not": "konusmada gelen mesaj yok"}
    son = satir[0]
    from jarvis import mesaj_sinifi, satis_dialog

    sinif = _etkin_sinif(son.get("sinif"), son.get("metin") or "")
    urun_bilindi = bool(son.get("urun"))
    kart = None
    if sinif == mesaj_sinifi.ODEME_YONLENDIR:
        kayitlar = urun_kayitlari()
        kart = (satis_dialog.urun_bul(kayitlar, son["urun"]) if urun_bilindi
                else _mesajdaki_urun(kayitlar, son.get("metin") or ""))
        urun_bilindi = bool(kart and _urun_sayfasi(kayitlar, kart.urun_id))
    gerek, sebep = devir.devir_gerekir(
        sinif, urun_bilindi=urun_bilindi, mevzuat=son.get("mevzuat"))
    if sinif == mesaj_sinifi.ODEME_YONLENDIR and kart and not urun_bilindi and not gerek:
        gerek, sebep = True, devir.URUN_BELIRSIZ
    return {
        "devir": gerek,
        "sebep": sebep,
        "sebep_metni": devir.sebep_aciklamasi(sebep),
        "sinif": sinif,
        "son_gelen": (son.get("metin") or "")[:200],
    }


def ozet() -> dict:
    """Panel başlığı için sayaçlar."""
    satir = _calistir("""
    SELECT row_to_json(x) FROM (
      SELECT
        count(*) FILTER (WHERE k.devir_durumu = 'INSANDA') AS insanda,
        count(*) FILTER (WHERE k.devir_durumu = 'JARVIS')  AS jarviste,
        count(*) FILTER (WHERE k.devir_durumu = 'KAPALI')  AS kapali,
        count(*) FILTER (WHERE s.yon = 'gelen')            AS cevapsiz,
        count(*) AS toplam
      FROM lcarlie.konusma k
      LEFT JOIN LATERAL (
        SELECT m.yon FROM lcarlie.mesaj m
        WHERE m.konusma_id = k.id ORDER BY m.zaman DESC LIMIT 1
      ) s ON TRUE
    ) x;
    """)
    return satir[0] if satir else {}


def telefon_bul(konusma_id: int) -> str:
    """Konuşmanın WhatsApp numarası. Bulunamazsa boş döner -- UYDURULMAZ."""
    kayit = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT k.kanal, COALESCE(k.musteri_ref, k.harici_id) AS numara
      FROM lcarlie.konusma k WHERE k.id = {int(konusma_id)}
    ) x;
    """)
    if not kayit:
        raise KutuHatasi("konusma bulunamadi: %s" % konusma_id)
    if (kayit[0].get("kanal") or "") != "whatsapp":
        raise KutuHatasi("bu konusma WhatsApp degil: %s" % kayit[0].get("kanal"))
    return str(kayit[0].get("numara") or "")


def cevap_gonder(konusma_id: int, metin: str, *, kuru: bool = False) -> dict:
    """Sahibin yazdığı cevabı gönderir.

    🔴 ONAY KAYNAĞI HER ZAMAN `sahip-panel`. Bu uç otomatik çağrılamaz:
    paneldeki bir insan eylemidir. Jarvis'in kendi cevabı gönderecekse
    AYRI bir yol ve ayrı bir onay kaynağı gerekir -- ikisini aynı uca
    bağlamak, otomatik gönderimi insan onayı gibi göstermek olurdu.
    """
    from jarvis import whatsapp
    numara = telefon_bul(konusma_id)
    if not numara:
        raise KutuHatasi("konusmada telefon numarasi yok")
    try:
        return whatsapp.gonder(numara, metin,
                               onay_kaynagi=whatsapp.ONAY_INSAN,
                               konusma_id=int(konusma_id), kuru=kuru)
    except whatsapp.GondermeReddedildi as hata:
        raise KutuHatasi(str(hata)) from None


# ══════════════════════════════════════════════════════════════════════
# JARVİS TASLAĞI
#
# 🔴 TASLAK GÖNDERİLMEZ. Üretilir, denetlenir, panele konur. Sahip okur,
# isterse değiştirir, GÖNDER'e basar. "Üret" ile "gönder" aynı düğme
# olsaydı, modelin her çıktısı bir yayın kararı olurdu.
#
# 🔴 DEVİR KAPISI MODELDEN ÖNCE İŞLER. Sağlık/şikâyet, sipariş, iddia
# sorusu ya da tanınmayan sınıf ise model HİÇ ÇAĞRILMAZ -- para da
# harcanmaz, uygunsuz bir taslak da üretilmez.

_URUN_SQL = """
SELECT row_to_json(x) FROM (
  SELECT u.urun_id, u.urun_adi, u.aciklama_duz, u.wix_satis, u.wix_liste,
         u.wix_stok, u.wix_yayinda, w.slug, w.gorunur
  FROM mart.urun_karti u
  LEFT JOIN raw.wix_urun w ON w.urun_id = u.urun_id
) x;
"""


def urun_kayitlari() -> list[dict]:
    """mart.urun_karti satırları. Fiyatın TEK kaynağı burasıdır."""
    return _calistir(_URUN_SQL)


def _urun_sayfasi(kayitlar: list[dict], urun_id: str) -> str:
    for kayit in kayitlar:
        if (str(kayit.get("urun_id")) == urun_id and kayit.get("wix_yayinda")
                and kayit.get("gorunur") and kayit.get("slug")):
            return "https://www.lcarlie.shop/product-page/" + quote(str(kayit["slug"]), safe="")
    return ""


def _mesajdaki_urun(kayitlar: list[dict], mesaj: str):
    from jarvis.satis_dialog import _sade, kart_olustur

    metin = _sade(mesaj)
    eslesen = []
    for kayit in kayitlar:
        ad = _sade(str(kayit.get("urun_adi") or "")).split(" ")[0]
        if len(ad) >= 5 and re.search(r"(?<!\w)" + re.escape(ad) + r"(?!\w)", metin):
            eslesen.append(kayit)
    return kart_olustur(eslesen[0]) if len(eslesen) == 1 else None


def _etkin_sinif(saklanan: str | None, mesaj: str) -> str:
    from jarvis import mesaj_sinifi

    guncel = mesaj_sinifi.siniflandir(mesaj)
    if guncel in {mesaj_sinifi.SAGLIK, mesaj_sinifi.SIKAYET, mesaj_sinifi.DURDURMA,
                 mesaj_sinifi.ODEME_YONLENDIR}:
        return guncel
    return saklanan or guncel


def taslak(konusma_id: int) -> dict:
    """Son gelen mesaja Jarvis taslağı. HİÇBİR ŞEY GÖNDERMEZ."""
    from jarvis import devir, mesaj_sinifi, satis_dialog
    from jarvis.model_layer import ModelRouter

    kid = int(konusma_id)
    satir = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.metin, m.sinif, m.mevzuat, (k.notlar->>'urun') AS urun
      FROM lcarlie.mesaj m JOIN lcarlie.konusma k ON k.id = m.konusma_id
      WHERE m.konusma_id = {kid} AND m.yon = 'gelen'
      ORDER BY m.zaman DESC LIMIT 1
    ) x;
    """)
    if not satir:
        raise KutuHatasi("konusmada gelen mesaj yok")
    son = satir[0]
    mesaj = son.get("metin") or ""
    sinif = _etkin_sinif(son.get("sinif"), mesaj)
    urun_adi = son.get("urun")

    kayitlar = []
    kart = None
    if sinif == mesaj_sinifi.ODEME_YONLENDIR or urun_adi:
        kayitlar = urun_kayitlari()
        kart = satis_dialog.urun_bul(kayitlar, urun_adi) if urun_adi else None
        if kart is None and sinif == mesaj_sinifi.ODEME_YONLENDIR:
            kart = _mesajdaki_urun(kayitlar, mesaj)

    if sinif == mesaj_sinifi.ODEME_YONLENDIR and (son.get("mevzuat") or "").upper() not in {"BLOCKED", "BLOKE", "RED"}:
        adres = _urun_sayfasi(kayitlar, kart.urun_id) if kart else ""
        metin = (f"{kart.ad} ürününü şu sayfadan inceleyip ödeme adımlarını "
                 f"tamamlayabilirsiniz: {adres}" if adres else
                 ("Bu ürünün alışveriş sayfasını şu anda doğrulayamadım; "
                  "konuyu yetkili kişiye iletiyorum." if kart else
                  "Hangi ürünle ilgilendiğinizi paylaşır mısınız? Doğru ürün sayfasını "
                  "göndererek ödeme adımlarına yönlendireyim."))
        devredilmeli = bool(kart and not adres)
        return {"uretildi": True, "devredilmeli": devredilmeli, "sinif": sinif,
                "sebep": devir.URUN_BELIRSIZ if devredilmeli else None,
                "sebep_metni": devir.sebep_aciklamasi(devir.URUN_BELIRSIZ) if devredilmeli else "",
                "metin": metin, "bulgular": [], "gonderilebilir": not devredilmeli,
                "urun_soruluyor": not bool(kart)}

    gerek, sebep = devir.devir_gerekir(
        sinif, urun_bilindi=bool(urun_adi), mevzuat=son.get("mevzuat"))
    if gerek:
        yonlendirme = {
            "SAGLIK": "Sağlığınız bizim için öncelikli. Buradan tıbbi değerlendirme yapamam; "
                      "bir sağlık uzmanına danışmanızı öneririm. Konuyu yetkili kişiye iletiyorum.",
            "BELIRTI_ANLATIMI": "Sağlığınız bizim için öncelikli. Buradan tıbbi değerlendirme "
                                "yapamam; bir sağlık uzmanına danışmanızı öneririm. "
                                "Konuyu yetkili kişiye iletiyorum.",
            "SIKAYET": "Yaşadığınız olumsuz deneyim için üzgünüz, özür dileriz. "
                       "Konuyu bizzat incelemesi için yetkili kişiye iletiyorum.",
            "ANLASILMADI": "Mesajınızı aldım. Doğru yanıt verebilmem için sorunuzu veya "
                           "ilgili ürünü biraz açabilir misiniz? Konuyu ayrıca "
                           "yetkili kişiye iletiyorum.",
        }
        metin = yonlendirme.get(sinif, "") if son.get("mevzuat") not in {"BLOCKED", "BLOKE", "RED"} else ""
        return {"uretildi": bool(metin), "devredilmeli": True, "sinif": sinif,
                "sebep": sebep, "sebep_metni": devir.sebep_aciklamasi(sebep),
                "metin": metin, "bulgular": [], "gonderilebilir": False}

    if urun_adi and kart is None:
        kart = satis_dialog.urun_bul(kayitlar, urun_adi)

    cevap = satis_dialog.cevap_uret(mesaj, kart, ModelRouter())
    sonuc = cevap.to_dict()
    sonuc.update({
        "uretildi": bool(cevap.metin),
        "devredilmeli": False,
        "sinif": sinif,
        "urun_soruluyor": devir.urun_sorulmali(sinif, urun_bilindi=bool(urun_adi)),
    })
    return sonuc
