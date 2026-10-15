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
import subprocess
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
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


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
    """Son GELEN mesaja göre devir kapısının kararı. Hiçbir şey YAZMAZ.

    Ürün ataması bugün yapılamıyor: müşteri mesajından ürün çıkarılamaz
    (ölçüldü) ve reklam referansı `mesaj.ek` içinde her zaman yok. Bu
    yüzden `urun_bilindi=False` ile çalışılır -- yani fiyat/içerik soruları
    bugün sahibe düşer. Ürün ataması bağlandığında burası gevşer.
    """
    kid = int(konusma_id)
    satir = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.sinif, m.mevzuat, m.metin
      FROM lcarlie.mesaj m
      WHERE m.konusma_id = {kid} AND m.yon = 'gelen'
      ORDER BY m.zaman DESC LIMIT 1
    ) x;
    """)
    if not satir:
        return {"devir": True, "sebep": devir.SINIF_YOK,
                "sebep_metni": devir.sebep_aciklamasi(devir.SINIF_YOK),
                "not": "konusmada gelen mesaj yok"}
    son = satir[0]
    gerek, sebep = devir.devir_gerekir(
        son.get("sinif"), urun_bilindi=False, mevzuat=son.get("mevzuat"))
    return {
        "devir": gerek,
        "sebep": sebep,
        "sebep_metni": devir.sebep_aciklamasi(sebep),
        "sinif": son.get("sinif"),
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
  SELECT urun_id, urun_adi, aciklama_duz, wix_satis, wix_liste,
         wix_stok, wix_yayinda
  FROM mart.urun_karti
) x;
"""


def urun_kayitlari() -> list[dict]:
    """mart.urun_karti satırları. Fiyatın TEK kaynağı burasıdır."""
    return _calistir(_URUN_SQL)


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
    sinif = son.get("sinif") or mesaj_sinifi.siniflandir(mesaj)
    urun_adi = son.get("urun")

    gerek, sebep = devir.devir_gerekir(
        sinif, urun_bilindi=bool(urun_adi), mevzuat=son.get("mevzuat"))
    if gerek:
        # Model cagrilmaz: uygunsuz taslak da uretilmez, jeton da yanmaz.
        return {"uretildi": False, "devredilmeli": True, "sinif": sinif,
                "sebep": sebep, "sebep_metni": devir.sebep_aciklamasi(sebep),
                "metin": "", "bulgular": []}

    kart = None
    if urun_adi:
        kart = satis_dialog.urun_bul(urun_kayitlari(), urun_adi)

    cevap = satis_dialog.cevap_uret(mesaj, kart, ModelRouter())
    sonuc = cevap.to_dict()
    sonuc.update({
        "uretildi": bool(cevap.metin),
        "devredilmeli": False,
        "sinif": sinif,
        "urun_soruluyor": devir.urun_sorulmali(sinif, urun_bilindi=bool(urun_adi)),
    })
    return sonuc
