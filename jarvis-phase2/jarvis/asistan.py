"""KİŞİSEL ASİSTAN: hatırlatıcılar + günün haberleri.

Sahip 22.09.2026: *"kişisel asistanımı farklı bir bölümde, hatırlatıcılar
ve haberleri ana sayfada görebilmek istiyorum, buranın düzeni önemli."*

İKİ AYRI ŞEY, İKİ AYRI YER:
  hatirlaticilar() -> sahibin kendi notu; ASİSTAN sekmesinde
  haberler()       -> güncel olaylar hattının çıktısı; ANA SAYFADA

🔴 HATIRLATICI METNİ ŞİRKET HAFIZASINA AÇILMIYOR. Sahip "Ahmet Bey'i
ara" yazabilir -- bu PII'dir. Bu modül yalnız panele okutur;
CompanyMemory sorgusu olarak kaydedilmedi. Aynı kural müşteri mesajı
metninde de geçerliydi.

🔴 TEKRAR EDEN HATIRLATICI KAPANMAZ, ÖTELENİR. "Her ay fatura" bir kez
yapılınca listeden düşerse bir daha hatırlatmaz. `tamamla()` tekrarlı
satırı bir sonraki tarihe taşır.

🔴 HABER KAYNAKSIZ GÖSTERİLMEZ. `core.guncel_olay` satırlarının
kaynak_url'si var; panelde bağlantısıyla birlikte veriliyor ki sahip
"bunu nereden aldın" diye sorduğunda cevap hazır olsun.
"""
from __future__ import annotations

import json
from jarvis.db_transport import run as db_run
from typing import Any


class AsistanHatasi(Exception):
    """Sahibin okuyabileceği, Türkçe ve sebepli hata."""


def _oku(sql: str) -> list[dict]:
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=25, check=False)
    if r.returncode:
        # 🔴 Sessiz boş liste yok; bugün üç kez bu hatayı düzelttik.
        raise AsistanHatasi("psql başarısız: " + (r.stderr or "").strip()[:300])
    out = []
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                continue
    return out


def _yaz(sql: str) -> None:
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
         "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=sql, capture_output=True, text=True, timeout=25, check=False)
    if r.returncode:
        raise AsistanHatasi((r.stderr or "").strip()[:300])


def _t(v: Any) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


# ───────────────────────────────────────────────── hatırlatıcılar
def hatirlaticilar(adet: int = 40) -> list[dict]:
    return _oku("SELECT row_to_json(t) FROM (SELECT * FROM "
                f"mart.hatirlatici_guncel LIMIT {int(adet)}) t;")


def ekle(*, baslik: str, zaman: str, not_: str | None = None,
         tekrar: str | None = None, onem: str = "NORMAL") -> dict:
    baslik = (baslik or "").strip()
    if len(baslik) < 2:
        raise AsistanHatasi("başlık en az 2 karakter olmalı")
    if tekrar and tekrar not in ("gunluk", "haftalik", "aylik"):
        raise AsistanHatasi("tekrar: gunluk | haftalik | aylik olabilir")
    if onem not in ("DUSUK", "NORMAL", "YUKSEK"):
        raise AsistanHatasi("önem: DUSUK | NORMAL | YUKSEK olabilir")
    _yaz("INSERT INTO core.hatirlatici (baslik, not_, zaman, tekrar, onem) "
         f"VALUES ({_t(baslik)}, {_t(not_)}, {_t(zaman)}::timestamptz, "
         f"{_t(tekrar)}, {_t(onem)});")
    return {"eklendi": baslik, "zaman": zaman}


TEKRAR_ARALIK = {"gunluk": "1 day", "haftalik": "7 days", "aylik": "1 month"}


def tamamla(hid: int) -> dict:
    """Tamamlar; tekrarlıysa KAPATMAZ, bir sonraki tarihe öteler."""
    satir = _oku("SELECT row_to_json(t) FROM (SELECT id, tekrar, baslik "
                 f"FROM core.hatirlatici WHERE id = {int(hid)}) t;")
    if not satir:
        raise AsistanHatasi(f"hatırlatıcı {hid} bulunamadı")
    tekrar = satir[0].get("tekrar")
    if tekrar:
        aralik = TEKRAR_ARALIK[tekrar]
        _yaz(f"UPDATE core.hatirlatici SET zaman = zaman + interval '{aralik}' "
             f"WHERE id = {int(hid)};")
        return {"id": hid, "sonuc": f"ötelendi (+{aralik})"}
    _yaz("UPDATE core.hatirlatici SET durum = 'TAMAM', tamamlandi = now() "
         f"WHERE id = {int(hid)};")
    return {"id": hid, "sonuc": "tamamlandı"}


# ───────────────────────────────────────────────────────── haberler
def haberler(gun_sayisi: int = 3, adet: int = 12) -> list[dict]:
    """Güncel olaylar hattının son çıktısı — ana sayfa için."""
    return _oku(
        "SELECT row_to_json(t) FROM (SELECT id, gun, aci, baslik, ozet, "
        "neden_onemli, kaynak_url, kaynak_adi, onem "
        "FROM core.guncel_olay "
        f"WHERE gun >= current_date - {int(gun_sayisi)} "
        f"ORDER BY gun DESC, onem, id DESC LIMIT {int(adet)}) t;")


def ozet() -> dict:
    """Ana sayfa için tek bakışta: kaç hatırlatıcı, kaç haber."""
    h = hatirlaticilar(200)
    return {
        "hatirlatici_toplam": len(h),
        "zamani_gelen": sum(1 for x in h if x.get("zamani_geldi")),
        "geciken": sum(1 for x in h if x.get("gecikti")),
        "haber_sayisi": len(haberler()),
    }

# ───────────────────────────────────────────────────────── gündem
def gundem(adet: int = 20) -> list[dict]:
    """Şirket gündemi — ASİSTAN'ın ikinci sekmesi."""
    return _oku("SELECT row_to_json(t) FROM (SELECT soru_id, hedef, oncelik, "
                "soru, neden_onemli, kaynak_plani, durum, olusturma "
                "FROM mart.sirket_gundemi ORDER BY olusturma DESC "
                f"LIMIT {int(adet)}) t;")


# ──────────────────────────────────────────────── onaylar & imzalar
def tasarim_onay_bekleyen(adet: int = 30) -> list[dict]:
    """Onay bekleyen tasarımlar.

    🔴 Öneri kuyruğundan AYRI okunuyor. İkisi de "imzamı bekleyen iş"
    ama onay mekanizmaları farklı: biri action gateway, bu ise
    human_approver rolüyle veritabanı tetikleyicisi. Kaynağı gizlemek
    sahibi yanlış yerde onay aramaya iter.
    """
    return _oku("SELECT row_to_json(t) FROM (SELECT is_id, is_turu, "
                "sablon_adi, isteyen, istek, canva_tasarim, disa_aktarim, "
                "uretildi FROM mart.tasarim_guncel WHERE onay_bekliyor "
                f"ORDER BY uretildi DESC LIMIT {int(adet)}) t;")
