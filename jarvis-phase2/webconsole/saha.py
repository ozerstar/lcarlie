"""SAHA sekmesi: ziyaret hedefleri, rota, ziyaret kaydı, fotoğraf.

Panelin veri katmanı. Sorgular `mart.saha_hedef` üzerinden gider; o görünüm
OSM aynasını, elle eklenen noktaları ve insan beyanını tek listede birleştirir.

## Tırnak kaçışı

Yazma işlemlerinde değerler `psql -v` ile geçilir ve SQL içinde `:'ad'`
biçiminde kullanılır: kaçışı psql yapar. Elle tırnak yazmak bu projede daha
önce bozulmuş bir yöntem -- bir işletme adındaki tek tırnak bütün sorguyu
düşürürdü.

## Fotoğraf

Dosya diske yazılır, veritabanında yalnız yol durur. Binlerce fotoğrafı
tabloya gömmek yedek boyutunu ve sorgu hızını bozar. Boyut tavanı var:
tavanı olmayan bir yükleme ucu, diski dolduran en kolay yoldur.
"""
from __future__ import annotations

import base64
import binascii
import json
import subprocess
import time
from pathlib import Path

KAP = "lcarlie-postgres"
FOTO_DIZIN = Path("/opt/lcarlie/saha-foto")
EN_COK_FOTO_BAYT = 4 * 1024 * 1024        # 4 MB
EN_COK_SONUC = 500                         # tek sorguda dönecek hedef tavanı

TURLER = ("ECZANE", "KLINIK", "DIS", "DOKTOR", "HASTANE", "SPOR")
ZIYARET_SONUCLARI = ("GORUSULDU", "KAPALI", "YETKILI_YOK", "ILGILENMEDI",
                     "NUMUNE_BIRAKILDI", "SIPARIS_SOZU", "TEKRAR_GEL")
KONUM_KAYNAKLARI = ("GPS", "HARITA", "ELLE")


class SahaHatasi(ValueError):
    """İstek kabul edilmedi. Sessizce yutulmaz."""


def _oku(sql: str, zaman: int = 30) -> list[dict]:
    tam = "\\set ON_ERROR_STOP on\n" + sql + "\n"
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=tam, capture_output=True, text=True, timeout=zaman, check=False)
    if p.returncode:
        raise SahaHatasi((p.stderr or p.stdout).strip()[:300])
    cikti = []
    for satir in (p.stdout or "").splitlines():
        satir = satir.strip()
        if not satir:
            continue
        try:
            cikti.append(json.loads(satir))
        except ValueError:
            continue
    return cikti


def _yaz(sql: str, degiskenler: dict, zaman: int = 30) -> list[dict]:
    """Yazma. Değerler psql değişkeni olarak geçer; kaçışı psql yapar."""
    komut = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n"]
    for ad, deger in degiskenler.items():
        komut += ["-v", "%s=%s" % (ad, "" if deger is None else str(deger))]
    komut += ["-f", "-"]
    p = subprocess.run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
                       capture_output=True, text=True, timeout=zaman, check=False)
    if p.returncode:
        raise SahaHatasi((p.stderr or p.stdout).strip()[:300])
    cikti = []
    for satir in (p.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                cikti.append(json.loads(satir))
            except ValueError:
                continue
    return cikti


def _sayi(deger, ad: str, en_az=None, en_cok=None):
    try:
        s = float(deger)
    except (TypeError, ValueError):
        raise SahaHatasi("%s sayi olmali" % ad) from None
    if en_az is not None and s < en_az:
        raise SahaHatasi("%s en az %s olmali" % (ad, en_az))
    if en_cok is not None and s > en_cok:
        raise SahaHatasi("%s en fazla %s olabilir" % (ad, en_cok))
    return s


def _liste_kosulu(alan: str, degerler, izinli=None) -> str:
    """IN listesi. Değerler beyaz listeden geçer -- serbest metin SQL'e girmez."""
    if not degerler:
        return ""
    temiz = []
    for d in degerler:
        d = str(d).strip().upper()
        if not d or not d.replace("_", "").isalnum():
            continue
        if izinli and d not in izinli:
            continue
        temiz.append("'" + d + "'")
    if not temiz:
        return ""
    return " AND %s IN (%s)" % (alan, ", ".join(temiz))


def filtre_secenekleri() -> dict:
    """Panelde gösterilecek filtre değerleri -- uydurma değil, VERİDEN."""
    satirlar = _oku("""
      SELECT row_to_json(t) FROM (
        SELECT
          (SELECT json_agg(x ORDER BY x) FROM
             (SELECT DISTINCT tur x FROM mart.saha_hedef WHERE tur IS NOT NULL) a) AS turler,
          (SELECT json_agg(x ORDER BY x) FROM
             (SELECT DISTINCT brans x FROM mart.saha_hedef WHERE brans IS NOT NULL) b) AS branslar,
          (SELECT json_agg(x ORDER BY x) FROM
             (SELECT DISTINCT ilce x FROM mart.saha_hedef WHERE ilce IS NOT NULL) c) AS ilceler,
          (SELECT count(*) FROM mart.saha_hedef) AS toplam
      ) t;""")
    d = satirlar[0] if satirlar else {}
    d["ziyaret_sonuclari"] = list(ZIYARET_SONUCLARI)
    return d


def hedefler(tur=None, brans=None, ilce=None, enlem=None, boylam=None,
             yaricap_m=None, ziyaret_durumu=None, arama=None,
             limit: int = 200) -> dict:
    """Filtreli hedef listesi.

    `ziyaret_durumu`: GIDILMEDI | GIDILDI | hepsi(None).
    Konum verilirse yarıçap içindekiler, mesafeye göre sıralı gelir.
    """
    limit = int(_sayi(limit, "limit", 1, EN_COK_SONUC))
    kosul = " WHERE NOT hedef_disi AND kayip_at IS NULL"
    kosul += _liste_kosulu("tur", tur, set(TURLER))
    kosul += _liste_kosulu("brans", brans)
    if ilce:
        temiz = [str(i).replace("'", "") for i in ilce if str(i).strip()]
        if temiz:
            kosul += " AND ilce IN (%s)" % ", ".join("'" + t + "'" for t in temiz)
    if arama:
        # Tek tırnak temizlenir; LIKE kalıbı yine de veriden değil kullanıcıdan
        # geliyor, o yüzden uzunluk da sınırlanır.
        a = str(arama).replace("'", "")[:60]
        if a:
            kosul += " AND ad ILIKE '%%" + a + "%%'"
    if ziyaret_durumu == "GIDILMEDI":
        kosul += " AND COALESCE(ziyaret_sayisi, 0) = 0"
    elif ziyaret_durumu == "GIDILDI":
        kosul += " AND COALESCE(ziyaret_sayisi, 0) > 0"

    mesafe_sec, sirala = "NULL::numeric AS mesafe_m", "ad"
    if enlem is not None and boylam is not None:
        en = _sayi(enlem, "enlem", -90, 90)
        bo = _sayi(boylam, "boylam", -180, 180)
        ya = _sayi(yaricap_m or 1500, "yaricap_m", 50, 50000)
        hesap = ("6371000*2*asin(sqrt(power(sin(radians(enlem-%f)/2),2)"
                 "+cos(radians(%f))*cos(radians(enlem))"
                 "*power(sin(radians(boylam-%f)/2),2)))" % (en, en, bo))
        mesafe_sec = "round(%s::numeric, 1) AS mesafe_m" % hesap
        kosul += " AND %s < %f" % (hesap, ya)
        sirala = "mesafe_m"

    sql = """SELECT row_to_json(t) FROM (
      SELECT hedef_anahtari, kaynak, ad, tur, brans, brans_kaynagi, telefon,
             eposta, website, adres, ilce, enlem, boylam, ilgili_kisi, notlar,
             ziyaret_sayisi, son_ziyaret, son_sonuc, %s
        FROM mart.saha_hedef %s
       ORDER BY %s LIMIT %d) t;""" % (mesafe_sec, kosul, sirala, limit)
    kayitlar = _oku(sql)
    return {"sayi": len(kayitlar), "limit": limit, "hedefler": kayitlar}


def rota(baslangic_enlem, baslangic_boylam, en_fazla_durak=20, **filtre) -> dict:
    """Bulunduğun noktadan rota. Filtreler `hedefler()` ile aynı."""
    from jarvis import saha_rota
    en = _sayi(baslangic_enlem, "baslangic_enlem", -90, 90)
    bo = _sayi(baslangic_boylam, "baslangic_boylam", -180, 180)
    en_fazla = int(_sayi(en_fazla_durak, "en_fazla_durak", 1, 60))
    filtre.setdefault("yaricap_m", 2000)
    liste = hedefler(enlem=en, boylam=bo, limit=EN_COK_SONUC, **filtre)["hedefler"]
    sonuc = saha_rota.rota_kur((en, bo), liste, en_fazla_durak=en_fazla)
    sonuc["baslangic"] = {"enlem": en, "boylam": bo}
    return sonuc


def ziyaret_kaydet(hedef_anahtari: str, sonuc: str, giden: str,
                   not_metni: str = "", enlem=None, boylam=None,
                   konum_dogruluk_m=None, siparis_ref: str = "",
                   foto_b64: str = "") -> dict:
    """Ziyaret kaydı + isteğe bağlı fotoğraf."""
    if sonuc not in ZIYARET_SONUCLARI:
        raise SahaHatasi("gecersiz sonuc: %s" % sonuc)
    anahtar = str(hedef_anahtari or "")
    if anahtar.startswith("osm:"):
        _, tur, kimlik = anahtar.split(":", 2)
        if tur not in ("node", "way", "relation") or not kimlik.isdigit():
            raise SahaHatasi("gecersiz hedef anahtari")
        hedef = {"osm_tur": "'%s'" % tur, "osm_id": kimlik, "nokta_id": "NULL"}
    elif anahtar.startswith("elle:"):
        kimlik = anahtar.split(":", 1)[1]
        if not kimlik.isdigit():
            raise SahaHatasi("gecersiz hedef anahtari")
        hedef = {"osm_tur": "NULL", "osm_id": "NULL", "nokta_id": kimlik}
    else:
        raise SahaHatasi("hedef anahtari 'osm:' ya da 'elle:' ile baslamali")

    kon = "NULL, NULL, NULL"
    if enlem is not None and boylam is not None:
        kon = "%f, %f, %s" % (
            _sayi(enlem, "enlem", -90, 90), _sayi(boylam, "boylam", -180, 180),
            ("%f" % _sayi(konum_dogruluk_m, "konum_dogruluk_m", 0, 100000))
            if konum_dogruluk_m is not None else "NULL")

    sql = """SELECT row_to_json(t) FROM (
      INSERT INTO core.saha_ziyaret
        (osm_tur, osm_id, nokta_id, giden, sonuc, not_metni, siparis_ref,
         enlem, boylam, konum_dogruluk_m)
      VALUES (%s, %s, %s, :'giden', :'sonuc', NULLIF(:'not', ''),
              NULLIF(:'siparis', ''), %s)
      RETURNING ziyaret_id, ziyaret_at) t;""" % (
        hedef["osm_tur"], hedef["osm_id"], hedef["nokta_id"], kon)

    satir = _yaz(sql, {"giden": giden, "sonuc": sonuc,
                       "not": (not_metni or "")[:4000],
                       "siparis": (siparis_ref or "")[:80]})
    if not satir:
        raise SahaHatasi("ziyaret yazilamadi")
    kayit = satir[0]

    if foto_b64:
        kayit["foto"] = foto_kaydet(kayit["ziyaret_id"], foto_b64, enlem, boylam)
    return kayit


def foto_kaydet(ziyaret_id: int, veri_b64: str, enlem=None, boylam=None) -> dict:
    """Fotoğrafı diske yazar, kaydını veritabanına düşer."""
    ham = veri_b64.split(",", 1)[-1]           # data: URL önekini at
    try:
        ikili = base64.b64decode(ham, validate=True)
    except (binascii.Error, ValueError):
        raise SahaHatasi("fotograf cozulemedi (gecersiz base64)") from None
    if not ikili:
        raise SahaHatasi("fotograf bos")
    if len(ikili) > EN_COK_FOTO_BAYT:
        raise SahaHatasi("fotograf en fazla %d MB olabilir"
                         % (EN_COK_FOTO_BAYT // (1024 * 1024)))
    # JPEG/PNG imzası: uzantıya değil İÇERİĞE bakılır.
    if ikili[:3] == b"\xff\xd8\xff":
        uzanti = "jpg"
    elif ikili[:8] == b"\x89PNG\r\n\x1a\n":
        uzanti = "png"
    else:
        raise SahaHatasi("yalniz JPEG ve PNG kabul edilir")

    FOTO_DIZIN.mkdir(parents=True, exist_ok=True)
    ad = "z%d-%s.%s" % (ziyaret_id, time.strftime("%Y%m%dT%H%M%S"), uzanti)
    yol = FOTO_DIZIN / ad
    yol.write_bytes(ikili)

    kon = "NULL, NULL"
    if enlem is not None and boylam is not None:
        kon = "%f, %f" % (_sayi(enlem, "enlem", -90, 90),
                          _sayi(boylam, "boylam", -180, 180))
    _yaz("""INSERT INTO core.saha_ziyaret_foto
              (ziyaret_id, dosya_yolu, bayt, enlem, boylam)
            VALUES (%d, :'yol', %d, %s);"""
         % (int(ziyaret_id), len(ikili), kon), {"yol": str(yol)})
    return {"dosya": ad, "bayt": len(ikili)}


def nokta_ekle(ad: str, tur: str, enlem, boylam, ekleyen: str,
               brans: str = "", telefon: str = "", eposta: str = "",
               adres: str = "", notlar: str = "",
               konum_kaynagi: str = "ELLE", konum_dogruluk_m=None) -> dict:
    """Haritada olmayan bir yeri elle ekler.

    🔴 `core.saha_elle_nokta`'ya yazılır, OSM aynasına DEĞİL: aylık tarama
    OSM'de bulamadığı kaydı kayıp işaretler, elle eklenen nokta ilk taramada
    kaybolmuş görünürdü.
    """
    ad = (ad or "").strip()
    if len(ad) < 2:
        raise SahaHatasi("ad en az 2 karakter olmali")
    if tur not in TURLER:
        raise SahaHatasi("gecersiz tur: %s" % tur)
    if konum_kaynagi not in KONUM_KAYNAKLARI:
        raise SahaHatasi("gecersiz konum kaynagi")
    en = _sayi(enlem, "enlem", -90, 90)
    bo = _sayi(boylam, "boylam", -180, 180)
    dogruluk = ("%f" % _sayi(konum_dogruluk_m, "konum_dogruluk_m", 0, 100000)
                ) if konum_dogruluk_m is not None else "NULL"

    sql = """SELECT row_to_json(t) FROM (
      INSERT INTO core.saha_elle_nokta
        (ad, tur, brans, enlem, boylam, telefon, eposta, adres, notlar,
         konum_kaynagi, konum_dogruluk_m, ekleyen)
      VALUES (:'ad', :'tur', NULLIF(:'brans',''), %f, %f,
              NULLIF(:'tel',''), NULLIF(:'eposta',''), NULLIF(:'adres',''),
              NULLIF(:'notlar',''), :'kaynak', %s, :'ekleyen')
      RETURNING nokta_id, ad, tur) t;""" % (en, bo, dogruluk)

    satir = _yaz(sql, {"ad": ad[:200], "tur": tur, "brans": (brans or "")[:60],
                       "tel": (telefon or "")[:60], "eposta": (eposta or "")[:120],
                       "adres": (adres or "")[:300], "notlar": (notlar or "")[:2000],
                       "kaynak": konum_kaynagi, "ekleyen": ekleyen})
    if not satir:
        raise SahaHatasi("nokta eklenemedi")
    kayit = satir[0]
    kayit["hedef_anahtari"] = "elle:%s" % kayit["nokta_id"]
    return kayit
