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
        p = subprocess.run(
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
    sonuc = _calistir(f"""
    SELECT row_to_json(x) FROM (
      UPDATE lcarlie.konusma
         SET devir_durumu = {_tirnak(yeni_durum)},
             devir_sebep  = {_tirnak(sebep)},
             devir_zaman  = now(),
             guncelleme   = now()
       WHERE id = {kid}
      RETURNING id, devir_durumu, devir_sebep, devir_zaman
    ) x;
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
