# -*- coding: utf-8 -*-
"""KATALOG: eczane/profesyonel sunum kataloğu ve sunum notları.

KATALOG METNİ BURADA ÜRETİLMEZ, OKUNUR. `scripts/katalog-uret.py` her
satırı ölçülmüş kaynaktan türetip `state/katalog.json`a yazar; bu modül
yalnız onu servis eder. Neden ayrı: 36 ürünün ~700 cümlesini mevzuat
denetçisinden geçirmek saniyeler sürer ve panel her açılışta bunu yapamaz.

🔴 KATALOG MÜŞTERİYE ÇIKAR. `knowledge/30-urun-*.md` dosyalarının beşinde
"🔒 İÇ BİLGİ — ESKİ KATALOG (MÜŞTERİYE ÇIKAMAZ)" bölümü var (eski
katalogun bloklu tıbbi iddiaları). Bu modül o dosyalara HİÇ bakmaz.
Kaynak, yayındaki Wix metninin denetimden temiz geçen cümleleridir.

BAYİ FİYATI: `core.urun_bayi_fiyat` boşsa katalogda "—" görünür ve
sahibin girmesi gerektiği YAZAR. Uydurulmuş bir toptan fiyat, sahada
verilmiş yanlış bir sözdür; boş bırakmak dürüst, doldurmak tehlikeli.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

KAP = "lcarlie-postgres"
GORSEL_DIZIN = Path("/opt/lcarlie/katalog-gorsel")
GONDERI_DIZIN = Path("/opt/lcarlie/gonderi-gorsel")

ILGI_DEGERLERI = ("YOK", "SORDU", "ILGILENDI", "NUMUNE", "SIPARIS_SOZU")
ILGI_ETIKET = {
    "YOK": "ilgilenmedi",
    "SORDU": "soru sordu",
    "ILGILENDI": "ilgilendi",
    "NUMUNE": "numune aldı",
    "SIPARIS_SOZU": "sipariş sözü",
}
EN_COK_NOT = 200


class KatalogHatasi(ValueError):
    """İstek kabul edilmedi. Sessizce yutulmaz."""


def _durum_dizini() -> Path:
    return Path(os.environ.get(
        "JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))


def _yol() -> Path:
    return _durum_dizini() / "katalog.json"


def _oku(sql: str, zaman: int = 30) -> list[dict]:
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input="\\set ON_ERROR_STOP on\n" + sql + "\n",
        capture_output=True, text=True, timeout=zaman, check=False)
    if p.returncode:
        raise KatalogHatasi((p.stderr or p.stdout).strip()[:300])
    cikti = []
    for satir in (p.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                cikti.append(json.loads(satir))
            except ValueError:
                continue
    return cikti


def _yaz(sql: str, degiskenler: dict, zaman: int = 30) -> list[dict]:
    """Değerler psql değişkeni olarak geçer; kaçışı psql yapar."""
    komut = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n"]
    for ad, deger in degiskenler.items():
        komut += ["-v", "%s=%s" % (ad, "" if deger is None else str(deger))]
    komut += ["-f", "-"]
    p = subprocess.run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
                       capture_output=True, text=True, timeout=zaman, check=False)
    if p.returncode:
        raise KatalogHatasi((p.stderr or p.stdout).strip()[:300])
    cikti = []
    for satir in (p.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                cikti.append(json.loads(satir))
            except ValueError:
                continue
    return cikti


# --- katalog ---------------------------------------------------------------
def katalog() -> dict:
    """Ürün kartları + bayi fiyatı + ilgi sayıları.

    Katalog dosyası yoksa HATA verilir, boş liste dönmez: "ürün yok" ile
    "katalog henüz üretilmedi" ayrı şeylerdir ve ikincisi düzeltilebilir
    bir durumdur.
    """
    yol = _yol()
    if not yol.exists():
        raise KatalogHatasi(
            "katalog henuz uretilmedi -- scripts/katalog-uret.py cagrilmali")
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except ValueError as hata:
        raise KatalogHatasi("katalog dosyasi okunamadi: %s" % hata) from None

    bayi = {r["urun_slug"]: r for r in _oku(
        "SELECT row_to_json(t) FROM (SELECT urun_slug, bayi_fiyat, para,"
        " en_az_adet FROM core.urun_bayi_fiyat) t;")}
    ilgi = {r["urun_slug"]: r for r in _oku(
        "SELECT row_to_json(t) FROM (SELECT * FROM mart.katalog_ilgi) t;")}

    for u in veri.get("urunler", []):
        b = bayi.get(u["slug"])
        u["bayi_fiyat"] = b["bayi_fiyat"] if b else None
        u["bayi_en_az_adet"] = b.get("en_az_adet") if b else None
        u["ilgi"] = ilgi.get(u["slug"])

    veri["bayi_fiyati_girilen"] = len(bayi)
    veri["ilgi_degerleri"] = [{"deger": d, "etiket": ILGI_ETIKET[d]}
                              for d in ILGI_DEGERLERI]
    return veri


def gorsel_yolu(dosya: str) -> Path:
    """Güvenli görsel yolu. Yol kaçışı reddedilir."""
    ad = str(dosya or "")
    if not ad or "/" in ad or "\\" in ad or ".." in ad:
        raise KatalogHatasi("gecersiz gorsel adi")
    hedef = (GORSEL_DIZIN / ad).resolve()
    if hedef.parent != GORSEL_DIZIN.resolve() or not hedef.is_file():
        raise KatalogHatasi("gorsel bulunamadi")
    return hedef


# --- sunum notlari ---------------------------------------------------------
def _slug_dogrula(urun_slug: str) -> str:
    slug = str(urun_slug or "").strip()
    if not slug or len(slug) > 120:
        raise KatalogHatasi("urun_slug gerekli")
    veri = katalog()
    if slug not in {u["slug"] for u in veri.get("urunler", [])}:
        raise KatalogHatasi("katalogda boyle bir urun yok: %s" % slug[:40])
    return slug


def not_yaz(urun_slug: str, giren: str, ilgi=None, not_metni: str = "",
            hedef_anahtari: str = "", ziyaret_id=None) -> dict:
    """Sunum notu ve/veya ilgi işareti."""
    slug = _slug_dogrula(urun_slug)
    if ilgi in ("", None):
        ilgi = None
    elif ilgi not in ILGI_DEGERLERI:
        raise KatalogHatasi("gecersiz ilgi: %s" % str(ilgi)[:30])
    metin = (not_metni or "").strip()[:4000]
    if ilgi is None and not metin:
        raise KatalogHatasi("not ya da ilgi isareti gerekli")

    hedef = (hedef_anahtari or "").strip()[:120]
    if hedef and not hedef.startswith(("osm:", "ovt:", "elle:")):
        raise KatalogHatasi("gecersiz hedef anahtari")

    zid = "NULL"
    if ziyaret_id not in (None, "", 0):
        try:
            zid = str(int(ziyaret_id))
        except (TypeError, ValueError):
            raise KatalogHatasi("gecersiz ziyaret_id") from None

    sql = """WITH s AS (
      INSERT INTO core.katalog_not
        (urun_slug, hedef_anahtari, ziyaret_id, ilgi, not_metni, giren)
      VALUES (:'slug', NULLIF(:'hedef', ''), %s, NULLIF(:'ilgi', ''),
              NULLIF(:'not', ''), :'giren')
      RETURNING not_id, urun_slug, ilgi, girildi)
      SELECT row_to_json(t) FROM s t;""" % zid

    satir = _yaz(sql, {"slug": slug, "hedef": hedef, "ilgi": ilgi or "",
                       "not": metin, "giren": (giren or "")[:80]})
    if not satir:
        raise KatalogHatasi("not yazilamadi")
    return satir[0]


def notlar(urun_slug: str = "", hedef_anahtari: str = "",
           limit: int = 50) -> dict:
    """Ürüne ya da hedefe ait notlar. İkisi de boşsa en yeni notlar."""
    try:
        limit = max(1, min(EN_COK_NOT, int(limit)))
    except (TypeError, ValueError):
        raise KatalogHatasi("limit sayi olmali") from None

    kosul = []
    degiskenler = {}
    if urun_slug:
        kosul.append("urun_slug = :'slug'")
        degiskenler["slug"] = str(urun_slug)[:120]
    if hedef_anahtari:
        kosul.append("hedef_anahtari = :'hedef'")
        degiskenler["hedef"] = str(hedef_anahtari)[:120]
    nerede = (" WHERE " + " AND ".join(kosul)) if kosul else ""

    sql = """SELECT row_to_json(t) FROM (
      SELECT not_id, urun_slug, hedef_anahtari, ziyaret_id, ilgi,
             not_metni, giren, girildi
        FROM core.katalog_not %s
       ORDER BY girildi DESC LIMIT %d) t;""" % (nerede, limit)
    kayitlar = _yaz(sql, degiskenler) if degiskenler else _oku(sql)
    for k in kayitlar:
        k["ilgi_etiket"] = ILGI_ETIKET.get(k.get("ilgi") or "", "")
    return {"sayi": len(kayitlar), "notlar": kayitlar}


def bayi_fiyat_yaz(urun_slug: str, bayi_fiyat, giren: str,
                   en_az_adet=None) -> dict:
    """Toptan/bayi fiyatı. Sahip kararı; katalog bunu olduğu gibi gösterir."""
    slug = _slug_dogrula(urun_slug)
    try:
        fiyat = float(bayi_fiyat)
    except (TypeError, ValueError):
        raise KatalogHatasi("bayi_fiyat sayi olmali") from None
    if not 0 < fiyat < 1000000:
        raise KatalogHatasi("bayi_fiyat araligin disinda")
    adet = "NULL"
    if en_az_adet not in (None, "", 0):
        try:
            adet = str(max(1, int(en_az_adet)))
        except (TypeError, ValueError):
            raise KatalogHatasi("en_az_adet sayi olmali") from None

    sql = """WITH s AS (
      INSERT INTO core.urun_bayi_fiyat
        (urun_slug, bayi_fiyat, en_az_adet, giren)
      VALUES (:'slug', %.2f, %s, :'giren')
      ON CONFLICT (urun_slug) DO UPDATE SET
        bayi_fiyat = EXCLUDED.bayi_fiyat,
        en_az_adet = EXCLUDED.en_az_adet,
        giren = EXCLUDED.giren, girildi = now()
      RETURNING urun_slug, bayi_fiyat, en_az_adet, girildi)
      SELECT row_to_json(t) FROM s t;""" % (fiyat, adet)
    satir = _yaz(sql, {"slug": slug, "giren": (giren or "")[:80]})
    if not satir:
        raise KatalogHatasi("bayi fiyati yazilamadi")
    return satir[0]


# --- INSTAGRAM GONDERI PLANI ----------------------------------------------
#
# Paketler `scripts/ig-gonderi-uret.py` tarafindan olculmus veriden
# uretilir; bu modul yalniz okur ve SAHIBIN kararini yazar.
#
# 🔴 ONAY KAPISI SEMADA, BURADA DEGIL. core.ig_gonderi_plani'nda iki kisit
# var: denetimden BULGULU gecen paket onaylanamaz, ve itirazi yanitlanmamis
# paket onaylanamaz. Kurali burada tekrar yazsaydim iki yer ayri karar
# verir ve biri digerini sessizce kabul ederdi.

IG_DURUMLAR = ("ONERI", "ONAYLANDI", "REDDEDILDI", "YAYINLANDI")
IG_AMAC_ETIKET = {
    "SATIS": "satış", "TANITIM": "tanıtım", "B2B": "eczane / profesyonel",
}


def ig_plan(durum: str = "", limit: int = 50) -> dict:
    """Gönderi paketleri. Varsayılan: karar bekleyenler önce."""
    try:
        limit = max(1, min(200, int(limit)))
    except (TypeError, ValueError):
        raise KatalogHatasi("limit sayi olmali") from None

    kosul = ""
    degiskenler = {}
    if durum:
        if durum not in IG_DURUMLAR:
            raise KatalogHatasi("gecersiz durum: %s" % str(durum)[:30])
        kosul = " WHERE durum = :'durum'"
        degiskenler["durum"] = durum

    sql = """SELECT row_to_json(t) FROM (
      SELECT plan_id, urun_slug, amac, bicim, kanca, caption, hashtagler,
             gorsel_brief, cta, cta_gerekce, dayanak, itiraz, itiraza_yanit,
             denetim, denetim_notu, durum, uretim_at, karar_at, karar_veren
        FROM core.ig_gonderi_plani %s
       ORDER BY CASE durum WHEN 'ONERI' THEN 0 WHEN 'ONAYLANDI' THEN 1
                           WHEN 'YAYINLANDI' THEN 2 ELSE 3 END,
                uretim_at DESC
       LIMIT %d) t;""" % (kosul, limit)
    paketler = _yaz(sql, degiskenler) if degiskenler else _oku(sql)
    for p in paketler:
        p["amac_etiket"] = IG_AMAC_ETIKET.get(p.get("amac") or "", p.get("amac"))

    ozet = _oku("""SELECT row_to_json(t) FROM (
      SELECT count(*) AS toplam,
             count(*) FILTER (WHERE durum = 'ONERI') AS karar_bekleyen,
             count(*) FILTER (WHERE durum = 'ONAYLANDI') AS onayli,
             count(*) FILTER (WHERE durum = 'YAYINLANDI') AS yayinda,
             count(*) FILTER (WHERE denetim <> 'TEMIZ') AS bulgulu
        FROM core.ig_gonderi_plani) t;""")
    return {"sayi": len(paketler), "paketler": paketler,
            "ozet": ozet[0] if ozet else {},
            "durumlar": list(IG_DURUMLAR)}


def ig_karar(plan_id, durum: str, karar_veren: str) -> dict:
    """Sahip kararı: onayla / reddet / yayınlandı işaretle.

    Şema kısıtı bulgulu ya da tartışılmamış paketi reddeder; hata mesajı
    AYNEN döner, "kaydedildi" görünmez.
    """
    try:
        pid = int(plan_id)
    except (TypeError, ValueError):
        raise KatalogHatasi("gecersiz plan_id") from None
    if durum not in IG_DURUMLAR:
        raise KatalogHatasi("gecersiz durum: %s" % str(durum)[:30])

    sql = """WITH s AS (
      UPDATE core.ig_gonderi_plani
         SET durum = :'durum', karar_at = now(), karar_veren = :'kim'
       WHERE plan_id = %d
      RETURNING plan_id, urun_slug, durum, karar_at)
      SELECT row_to_json(t) FROM s t;""" % pid
    satir = _yaz(sql, {"durum": durum, "kim": (karar_veren or "")[:80]})
    if not satir:
        raise KatalogHatasi("plan bulunamadi: %d" % pid)
    return satir[0]


def gonderi_gorsel_yolu(dosya: str) -> Path:
    """Uretilen gonderi gorseli. Yol kacisi reddedilir."""
    ad = str(dosya or "")
    if not ad or "/" in ad or "\\" in ad or ".." in ad:
        raise KatalogHatasi("gecersiz gorsel adi")
    hedef = (GONDERI_DIZIN / ad).resolve()
    if hedef.parent != GONDERI_DIZIN.resolve() or not hedef.is_file():
        raise KatalogHatasi("gorsel bulunamadi")
    return hedef
