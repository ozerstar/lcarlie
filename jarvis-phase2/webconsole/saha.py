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
from jarvis.db_transport import run as db_run
import time
from pathlib import Path

KAP = "lcarlie-postgres"
FOTO_DIZIN = Path("/opt/lcarlie/saha-foto")
EN_COK_FOTO_BAYT = 4 * 1024 * 1024        # 4 MB
EN_COK_SONUC = 500                         # tek sorguda dönecek hedef tavanı

# 🔴 BU LISTE VERIYLE AYNI OLMAK ZORUNDA. Onceden alti tur yaziyordu ama
# veride on alti var. Eksik turler filtrede SESSIZCE dusuyordu: HUZUREVI
# secen kisi 18.845 kaydin tamamini geri aliyor ve secimin islediğini
# saniyordu. Yeni tur eklendiginde scripts/saha-tara.py ile birlikte burasi
# da guncellenir; sinama ikisini karsilastirir.
TURLER = ("ECZANE", "KLINIK", "DIS", "DOKTOR", "HASTANE", "SPOR",
          "GUZELLIK", "KUAFOR", "OTEL", "KRES", "PSIKOLOG", "OPTIK",
          "DIYETISYEN", "HUZUREVI", "BEBEK", "AYAK")

# Ekranda gorunen ad. Anahtar ASCII kalir (SQL ve filtre icin), etiket
# Turkce yazilir -- "PSIKOLOG" degil "Psikolog", "HUZUREVI" degil
# "Huzurevi / bakim evi".
TUR_ETIKET = {
    "ECZANE": "Eczane", "KLINIK": "Klinik / tıp merkezi",
    "DIS": "Diş kliniği", "DOKTOR": "Muayenehane",
    "HASTANE": "Hastane", "SPOR": "Spor salonu",
    "GUZELLIK": "Güzellik merkezi", "KUAFOR": "Kuaför / berber",
    "OTEL": "Otel", "KRES": "Kreş / anaokulu", "PSIKOLOG": "Psikolog",
    "OPTIK": "Optik", "DIYETISYEN": "Diyetisyen",
    "HUZUREVI": "Huzurevi / bakım evi", "BEBEK": "Bebek ürünleri",
    "AYAK": "Ayak sağlığı (podoloji)",
}

BRANS_ETIKET = {
    "AILE_SAGLIGI": "Aile sağlığı merkezi", "KADIN_DOGUM": "Kadın doğum",
    "DERMATOLOJI": "Dermatoloji", "ORTOPEDI": "Ortopedi",
    "UROLOJI": "Üroloji", "KARDIYOLOJI": "Kardiyoloji",
    "NOROLOJI": "Nöroloji", "FIZIK_TEDAVI": "Fizik tedavi",
    "COCUK": "Çocuk", "DIYALIZ": "Diyaliz",
    "LABORATUVAR": "Laboratuvar", "GORUNTULEME": "Görüntüleme",
    "GENEL": "Genel", "ESTETIK": "Estetik", "ORTODONTI": "Ortodonti",
    "AGIZ_CENE": "Ağız ve çene cerrahisi", "ENDODONTI": "Endodonti",
    "PERIODONTOLOJI": "Periodontoloji", "GOZ": "Göz", "KBB": "KBB",
    "GASTROENTEROLOJI": "Gastroenteroloji",
    "ENDOKRINOLOJI": "Endokrinoloji", "ONKOLOJI": "Onkoloji",
    "PSIKIYATRI": "Psikiyatri", "PSIKOLOJI": "Psikoloji",
    "ALTERNATIF": "Tamamlayıcı tıp", "VETERINER": "Veteriner",
    "AYAK": "Podoloji", "DIS": "Diş",
}

ZIYARET_ETIKET = {
    "GORUSULDU": "Görüşüldü", "KAPALI": "Kapalı",
    "YETKILI_YOK": "Yetkili yoktu", "ILGILENMEDI": "İlgilenmedi",
    "NUMUNE_BIRAKILDI": "Numune bırakıldı", "SIPARIS_SOZU": "Sipariş sözü",
    "TEKRAR_GEL": "Tekrar gelinecek",
}
ZIYARET_SONUCLARI = ("GORUSULDU", "KAPALI", "YETKILI_YOK", "ILGILENMEDI",
                     "NUMUNE_BIRAKILDI", "SIPARIS_SOZU", "TEKRAR_GEL")
KONUM_KAYNAKLARI = ("GPS", "HARITA", "ELLE")


class SahaHatasi(ValueError):
    """İstek kabul edilmedi. Sessizce yutulmaz."""


def _oku(sql: str, zaman: int = 30) -> list[dict]:
    tam = "\\set ON_ERROR_STOP on\n" + sql + "\n"
    p = db_run(
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
    p = db_run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
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
    """IN listesi. Değerler beyaz listeden geçer -- serbest metin SQL'e girmez.

    🔴 REDDEDİLEN DEĞER HATA VERİR, SESSİZCE DÜŞMEZ. Eskiden geçersiz değer
    atlanıyordu; hepsi atlanınca koşul hiç eklenmiyor ve sorgu FİLTRESİZ
    dönüyordu. Kullanıcı "HUZUREVİ seçtim" diyordu, ekran 18.845 kayıt
    gösteriyordu ve ikisi de doğru görünüyordu. Yokluk ile reddediliş ayrı
    şeylerdir; ayrı söylenir.
    """
    if not degerler:
        return ""
    temiz = []
    for d in degerler:
        d = str(d).strip().upper()
        if not d:
            continue
        if not d.replace("_", "").isalnum():
            raise SahaHatasi("gecersiz %s degeri: %s" % (alan, d[:40]))
        if izinli and d not in izinli:
            raise SahaHatasi("bilinmeyen %s: %s" % (alan, d[:40]))
        temiz.append("'" + d + "'")
    if not temiz:
        return ""
    return " AND %s IN (%s)" % (alan, ", ".join(temiz))


TEMEL_KOSUL = "NOT hedef_disi AND kayip_at IS NULL"

# Eleme, silme değildir. Elenen kayıt listeden çıkar ama İSTENİRSE
# görülebilir ve neden elendiği yazar. Görülemeseydi, yanlış elediğimizi
# bir daha fark edemezdik.
ELEME_GORUNUMU = {
    None:     TEMEL_KOSUL,
    "":       TEMEL_KOSUL,
    "GIZLE":  TEMEL_KOSUL,
    "GOSTER": "kayip_at IS NULL",
    "SADECE": "hedef_disi AND kayip_at IS NULL",
}


def _temel(eleme=None) -> str:
    if eleme not in ELEME_GORUNUMU:
        raise SahaHatasi("gecersiz eleme gorunumu: %s" % str(eleme)[:30])
    return ELEME_GORUNUMU[eleme]


def _kosul_parcalari(tur=None, brans=None, ilce=None, arama=None,
                     ziyaret_durumu=None) -> dict:
    """Her filtreyi AYRI parça olarak üretir.

    Ayrı tutulmasının sebebi facet sayımı: bir filtrenin kendi seçenekleri
    sayılırken KENDİ koşulu uygulanmaz -- yoksa seçili olmayan her seçenek
    sıfır görünür ve kullanıcı seçimini genişletemez. Arama motorlarının
    kenar çubuğu da böyle çalışır.
    """
    p = {}
    k = _liste_kosulu("tur", tur, set(TURLER))
    if k:
        p["tur"] = k
    k = _liste_kosulu("brans", brans)
    if k:
        p["brans"] = k
    if ilce:
        temiz = [str(i).replace("'", "")[:60] for i in ilce if str(i).strip()]
        if temiz:
            p["ilce"] = " AND ilce IN (%s)" % ", ".join("'" + t + "'" for t in temiz)
    if arama:
        a = str(arama).replace("'", "")[:60]
        if a:
            # 🔴 AKSAN DUYARSIZ. ILIKE büyük/küçük harfi Türkçede doğru
            # çeviriyordu (ölçüldü: 'diş' ve 'DİŞ' ikisi de 560 kayıt) ama
            # aksanı çevirmiyordu: Türkçe karakteri olmayan klavyeden
            # 'dis' yazan kişi 'Diş Kliniği'ni HİÇ bulamıyordu. Artık iki
            # taraf da core.tr_anahtar'dan geçiyor.
            p["arama"] = (" AND ad_ara LIKE '%' || core.tr_anahtar('"
                          + a + "') || '%'")
    if ziyaret_durumu == "GIDILMEDI":
        p["ziyaret"] = " AND COALESCE(ziyaret_sayisi, 0) = 0"
    elif ziyaret_durumu == "GIDILDI":
        p["ziyaret"] = " AND COALESCE(ziyaret_sayisi, 0) > 0"
    elif ziyaret_durumu:
        raise SahaHatasi("gecersiz ziyaret durumu: %s" % str(ziyaret_durumu)[:30])
    return p


def _birlestir(parcalar: dict, haric: str = "", eleme=None) -> str:
    return "WHERE " + _temel(eleme) + "".join(
        v for k, v in sorted(parcalar.items()) if k != haric)


def _facet(alan: str, parcalar: dict, eleme=None) -> str:
    """Bir filtrenin seçenekleri + mevcut seçim altındaki kayıt sayısı.

    Sıfır çıkan seçenek LİSTEDEN DÜŞMEZ, sayısı 0 olarak döner; panel onu
    söner gösterir. Düşseydi liste her tıklamada zıplardı ve kullanıcı bir
    seçeneğin hiç var olmadığını mı yoksa seçimiyle elendiğini mi
    bilemezdi.
    """
    return """(SELECT json_agg(json_build_object('deger', u.x, 'adet',
                 COALESCE(c.n, 0)) ORDER BY COALESCE(c.n, 0) DESC, u.x)
        FROM (SELECT DISTINCT {alan} x FROM mart.saha_hedef
               WHERE {temel} AND {alan} IS NOT NULL) u
        LEFT JOIN (SELECT {alan} x, count(*) n FROM mart.saha_hedef
                    {kosul} AND {alan} IS NOT NULL GROUP BY 1) c
               ON c.x = u.x)""".format(
        alan=alan, temel=_temel(eleme),
        kosul=_birlestir(parcalar, haric=alan, eleme=eleme))


def _calistir(sql: str, zaman: int = 180) -> None:
    """Çıktı beklemeyen komut. Her deyim kendi işleminde çalışır."""
    p = db_run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q",
         "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=sql, capture_output=True, text=True, timeout=zaman, check=False)
    if p.returncode:
        raise SahaHatasi((p.stderr or p.stdout).strip()[:300])


def tazele() -> dict:
    """Kaynak görünümlerini yeniden kurar.

    🔴 NE ZAMAN ÇAĞRILIR: aylık tarama sonrası, ve sahada bilgi/nokta
    yazıldığında. Ziyaret kaydı için GEREKMEZ -- ziyaret canlı bağlı.

    CONCURRENTLY kullanılır: tazeleme sürerken panel okumaya devam eder.
    Kilitleseydik, tarama koşarken sahadaki kişi listeyi göremezdi.
    """
    _calistir("REFRESH MATERIALIZED VIEW CONCURRENTLY mart.saha_tum;\n"
              "REFRESH MATERIALIZED VIEW CONCURRENTLY mart.saha_kaynak;\n")
    satir = _oku("SELECT row_to_json(t) FROM (SELECT"
                 " (SELECT count(*) FROM mart.saha_hedef) AS kayit,"
                 " (SELECT count(*) FROM mart.saha_hedef WHERE hedef_disi)"
                 " AS hedef_disi) t;")
    return satir[0] if satir else {}


def filtre_secenekleri(tur=None, brans=None, ilce=None, arama=None,
                       ziyaret_durumu=None, eleme=None) -> dict:
    """Filtre seçenekleri + mevcut seçim altındaki sayılar. VERİDEN."""
    p = _kosul_parcalari(tur, brans, ilce, arama, ziyaret_durumu)
    sql = """SELECT row_to_json(t) FROM (SELECT
        {ftur} AS turler, {fbrans} AS branslar, {filce} AS ilceler,
        (SELECT count(*) FROM mart.saha_hedef {tam}) AS eslesen,
        (SELECT count(*) FROM mart.saha_hedef WHERE {temel}) AS toplam,
        (SELECT count(*) FROM mart.saha_hedef
          WHERE hedef_disi AND kayip_at IS NULL) AS elenen,
        (SELECT count(*) FROM mart.saha_hedef
          WHERE {temel} AND ilce IS NULL) AS ilcesiz
      ) t;""".format(ftur=_facet("tur", p, eleme),
                     fbrans=_facet("brans", p, eleme),
                     filce=_facet("ilce", p, eleme),
                     tam=_birlestir(p, eleme=eleme),
                     temel=_temel(eleme))
    satirlar = _oku(sql)
    d = satirlar[0] if satirlar else {}
    for ad, etiketler in (("turler", TUR_ETIKET), ("branslar", BRANS_ETIKET)):
        for secenek in (d.get(ad) or []):
            secenek["etiket"] = etiketler.get(secenek["deger"], secenek["deger"])
    for secenek in (d.get("ilceler") or []):
        secenek["etiket"] = secenek["deger"]
    d["ziyaret_sonuclari"] = [{"deger": s, "etiket": ZIYARET_ETIKET.get(s, s)}
                              for s in ZIYARET_SONUCLARI]
    d["turler_tanim"] = dict(TUR_ETIKET)
    return d


def hedefler(tur=None, brans=None, ilce=None, enlem=None, boylam=None,
             yaricap_m=None, ziyaret_durumu=None, arama=None, eleme=None,
             limit: int = 200) -> dict:
    """Filtreli hedef listesi.

    `ziyaret_durumu`: GIDILMEDI | GIDILDI | hepsi(None).
    Konum verilirse yarıçap içindekiler, mesafeye göre sıralı gelir.
    """
    limit = int(_sayi(limit, "limit", 1, EN_COK_SONUC))
    kosul = " " + _birlestir(
        _kosul_parcalari(tur, brans, ilce, arama, ziyaret_durumu), eleme=eleme)

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
             eposta, website, adres, ilce, ilce_ham, ilce_kaynagi,
             hedef_disi_neden, enlem, boylam, ilgili_kisi, notlar,
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


def _anahtar_coz(hedef_anahtari: str) -> dict:
    """'osm:node:12' / 'ovt:08f...' / 'elle:7' -> eski sütunlar.

    🔴 ÜÇÜNCÜ KAYNAK BURADA UNUTULMUŞTU. Fonksiyon yalnız 'osm:' ve 'elle:'
    kabul ediyordu; oysa 18.845 hedefin 16.625'i (%88) 'ovt:' önekli.
    Saha elemanı listedeki neredeyse her yere ziyaret kaydedemiyordu ve
    aldığı hata "gecersiz hedef anahtari" idi -- sebebini söylemeyen bir
    cümle. Artık anahtar metin olarak SAKLANIR; kaynağa özel sütunlar
    yalnızca eski kayıtlarla uyum için doldurulur.
    """
    anahtar = str(hedef_anahtari or "").strip()
    if len(anahtar) > 120:
        raise SahaHatasi("hedef anahtari cok uzun")
    alanlar = {"osm_tur": "NULL", "osm_id": "NULL", "nokta_id": "NULL"}
    if anahtar.startswith("osm:"):
        parcalar = anahtar.split(":", 2)
        if len(parcalar) != 3:
            raise SahaHatasi("gecersiz osm anahtari")
        _, tur, kimlik = parcalar
        if tur not in ("node", "way", "relation") or not kimlik.isdigit():
            raise SahaHatasi("gecersiz osm anahtari")
        alanlar.update({"osm_tur": "'%s'" % tur, "osm_id": kimlik})
    elif anahtar.startswith("elle:"):
        kimlik = anahtar.split(":", 1)[1]
        if not kimlik.isdigit():
            raise SahaHatasi("gecersiz elle anahtari")
        alanlar["nokta_id"] = kimlik
    elif anahtar.startswith("ovt:"):
        kimlik = anahtar.split(":", 1)[1]
        # Overture kimliği onaltılık/harf-rakam; sütun yok, anahtar metni
        # kendisi taşır.
        if not kimlik or not kimlik.replace("-", "").replace("_", "").isalnum():
            raise SahaHatasi("gecersiz overture anahtari")
    else:
        raise SahaHatasi(
            "hedef anahtari 'osm:', 'ovt:' ya da 'elle:' ile baslamali")
    alanlar["anahtar"] = anahtar
    return alanlar


def ziyaret_kaydet(hedef_anahtari: str, sonuc: str, giden: str,
                   not_metni: str = "", enlem=None, boylam=None,
                   konum_dogruluk_m=None, siparis_ref: str = "",
                   foto_b64: str = "") -> dict:
    """Ziyaret kaydı + isteğe bağlı fotoğraf."""
    if sonuc not in ZIYARET_SONUCLARI:
        raise SahaHatasi("gecersiz sonuc: %s" % sonuc)
    hedef = _anahtar_coz(hedef_anahtari)

    kon = "NULL, NULL, NULL"
    if enlem is not None and boylam is not None:
        kon = "%f, %f, %s" % (
            _sayi(enlem, "enlem", -90, 90), _sayi(boylam, "boylam", -180, 180),
            ("%f" % _sayi(konum_dogruluk_m, "konum_dogruluk_m", 0, 100000))
            if konum_dogruluk_m is not None else "NULL")

    sql = """WITH s AS (
      INSERT INTO core.saha_ziyaret
        (hedef_anahtari, osm_tur, osm_id, nokta_id, giden, sonuc, not_metni,
         siparis_ref, enlem, boylam, konum_dogruluk_m)
      VALUES (:'anahtar', %s, %s, %s, :'giden', :'sonuc', NULLIF(:'not', ''),
              NULLIF(:'siparis', ''), %s)
      RETURNING ziyaret_id, ziyaret_at)
      SELECT row_to_json(t) FROM s t;""" % (
        hedef["osm_tur"], hedef["osm_id"], hedef["nokta_id"], kon)

    satir = _yaz(sql, {"anahtar": hedef["anahtar"], "giden": giden,
                       "sonuc": sonuc,
                       "not": (not_metni or "")[:4000],
                       "siparis": (siparis_ref or "")[:80]})
    if not satir:
        raise SahaHatasi("ziyaret yazilamadi")
    kayit = satir[0]
    kayit["hedef_anahtari"] = hedef["anahtar"]

    if foto_b64:
        kayit["foto"] = foto_kaydet(kayit["ziyaret_id"], foto_b64, enlem, boylam)
    return kayit


def bilgi_kaydet(hedef_anahtari: str, giren: str, ad: str = "",
                 brans: str = "", telefon: str = "", eposta: str = "",
                 ilgili_kisi: str = "", notlar: str = "",
                 hedef_disi=None) -> dict:
    """Sahada öğrenilen bilgiyi hedefin üzerine yazar.

    🔴 BU KAYIT AYLIK TARAMADA SİLİNMEZ. Tarama raw.* tablolarını tazeler;
    burası core.saha_bilgi'dir ve görünümde tazelenen veriyi YENER. Sahibin
    şartı buydu: "senin girdiğin bilgi tazelemede silinmez."

    Boş bırakılan alan DEĞİŞTİRİLMEZ; "bilmiyorum" ile "boş olsun" aynı şey
    değildir. Bir alanı gerçekten boşaltmak için '-' yazılır.
    """
    hedef = _anahtar_coz(hedef_anahtari)
    degerler = {"anahtar": hedef["anahtar"], "giren": (giren or "")[:80]}
    atamalar, sutunlar, girisler = [], ["hedef_anahtari", "giren"], [":'anahtar'", ":'giren'"]
    for ad_alan, deger, uzunluk in (
            ("ad", ad, 200), ("brans", brans, 40), ("telefon", telefon, 60),
            ("eposta", eposta, 120), ("ilgili_kisi", ilgili_kisi, 120),
            ("notlar", notlar, 4000)):
        if deger is None or str(deger).strip() == "":
            continue
        ham = str(deger).strip()[:uzunluk]
        if ad_alan == "brans":
            ham = ham.upper().replace(" ", "_")
            if not ham.replace("_", "").isalnum():
                raise SahaHatasi("gecersiz brans")
        degerler[ad_alan] = "" if ham == "-" else ham
        sutunlar.append(ad_alan)
        girisler.append("NULLIF(:'%s', '')" % ad_alan)
        atamalar.append("%s = NULLIF(:'%s', '')" % (ad_alan, ad_alan))
    if hedef_disi is not None:
        sutunlar.append("hedef_disi")
        girisler.append("true" if hedef_disi else "false")
        atamalar.append("hedef_disi = %s" % ("true" if hedef_disi else "false"))
    if not atamalar:
        raise SahaHatasi("degistirilecek alan yok")
    atamalar.append("giren = :'giren'")
    atamalar.append("girildi = now()")

    sql = """WITH s AS (
      INSERT INTO core.saha_bilgi (%s, girildi)
      VALUES (%s, now())
      ON CONFLICT (hedef_anahtari) DO UPDATE SET %s
      RETURNING hedef_anahtari, giren, girildi)
      SELECT row_to_json(t) FROM s t;""" % (
        ", ".join(sutunlar), ", ".join(girisler), ", ".join(atamalar))
    satir = _yaz(sql, degerler)
    if not satir:
        raise SahaHatasi("bilgi yazilamadi")
    return satir[0]


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

    sql = """WITH s AS (
      INSERT INTO core.saha_elle_nokta
        (ad, tur, brans, enlem, boylam, telefon, eposta, adres, notlar,
         konum_kaynagi, konum_dogruluk_m, ekleyen)
      VALUES (:'ad', :'tur', NULLIF(:'brans',''), %f, %f,
              NULLIF(:'tel',''), NULLIF(:'eposta',''), NULLIF(:'adres',''),
              NULLIF(:'notlar',''), :'kaynak', %s, :'ekleyen')
      RETURNING nokta_id, ad, tur)
      SELECT row_to_json(t) FROM s t;""" % (en, bo, dogruluk)

    satir = _yaz(sql, {"ad": ad[:200], "tur": tur, "brans": (brans or "")[:60],
                       "tel": (telefon or "")[:60], "eposta": (eposta or "")[:120],
                       "adres": (adres or "")[:300], "notlar": (notlar or "")[:2000],
                       "kaynak": konum_kaynagi, "ekleyen": ekleyen})
    if not satir:
        raise SahaHatasi("nokta eklenemedi")
    kayit = satir[0]
    kayit["hedef_anahtari"] = "elle:%s" % kayit["nokta_id"]
    # 🔴 Elle nokta maddileştirilmiş katmandadır (kopya ayıklaması onu da
    # kapsasın diye). Tazelemeseydik eklenen nokta listede GÖRÜNMEZ ve
    # saha elemanı "kaydedilmedi" sanardı. ~5 sn sürer; ekleme nadir bir
    # iştir, kopya çıkması ise her gün rahatsız ederdi.
    tazele()
    return kayit


# ---------------------------------------------------------------------------
# KONUM TAKİBİ
#
# 🔴 Bu, çalışanın KİŞİSEL VERİSİDİR -- işletme adresi tutmakla aynı kategori
# değil. Üç koruma koda gömülüdür, sonradan eklenen koruma eklenmez:
#
#   SAKLAMA_GUN      kayıtlar bu süre sonunda silinir
#   konum_gecmisi()  kişi kendi verisini görebilir
#   TAZELIK          panel "bayat" ile "hareketsiz"i ayırır
#
# "Bayat" hareketsizlik DEĞİLDİR: tarayıcı tabanlı konum, telefon kilitlenince
# ya da sekme arkaya atılınca durur. Bunu "duruyor" diye okumak, olmayan bir
# olguyu rapor etmek olur.
# ---------------------------------------------------------------------------

# 🔴 SAKLAMA SILME KAPALI -- sahip karari 25.09.2026: "silmelik bir konuya
# gerek yok, data saklayalim". Islev DURUYOR ve zamanlayici olmadan elle
# cagrilabilir; silinmesi gerektigine karar verilirse tek satirla acilir.
# Kaldirilmadi cunku sonradan yazilacak bir silme, yazilmayan silmedir.
SAKLAMA_ETKIN = False
SAKLAMA_GUN = 3650
BAYAT_ESIGI_DK = 10
ROTADA_SAYILAN_MESAFE_M = 150.0


def konum_yaz(kullanici: str, enlem, boylam, dogruluk_m=None, hiz_m_s=None,
              kaynak: str = "TARAYICI", rota_id=None) -> dict:
    """Tek konum noktası kaydeder."""
    if kaynak not in ("TARAYICI", "OWNTRACKS"):
        raise SahaHatasi("gecersiz konum kaynagi")
    en = _sayi(enlem, "enlem", -90, 90)
    bo = _sayi(boylam, "boylam", -180, 180)
    dog = ("%f" % _sayi(dogruluk_m, "dogruluk_m", 0, 100000)
           ) if dogruluk_m is not None else "NULL"
    hiz = ("%f" % _sayi(hiz_m_s, "hiz_m_s", 0, 200)
           ) if hiz_m_s is not None else "NULL"
    rota = str(int(rota_id)) if rota_id not in (None, "", 0) else "NULL"

    satir = _yaz("""WITH s AS (
      INSERT INTO core.saha_konum
        (kullanici, enlem, boylam, dogruluk_m, hiz_m_s, kaynak, rota_id)
      VALUES (:'kullanici', %f, %f, %s, %s, :'kaynak', %s)
      RETURNING konum_id, ts)
      SELECT row_to_json(t) FROM s t;""" % (en, bo, dog, hiz, rota),
                 {"kullanici": kullanici, "kaynak": kaynak})
    if not satir:
        raise SahaHatasi("konum yazilamadi")
    return satir[0]


def son_konumlar() -> dict:
    """Yönetici görünümü: kim nerede, ne kadar önce, taze mi."""
    kayitlar = _oku("""SELECT row_to_json(t) FROM (
      SELECT kullanici, ts, enlem, boylam, dogruluk_m, kaynak, rota_id,
             kac_saniye_once, tazelik
        FROM mart.saha_son_konum ORDER BY ts DESC) t;""")
    return {
        "sayi": len(kayitlar),
        "kisiler": kayitlar,
        "bayat_esigi_dk": BAYAT_ESIGI_DK,
        # Panelde AYNEN gösterilir: yorumu okuyana bırakmak, yanlış okumayı
        # davet etmek olurdu.
        "uyari": ("BAYAT, kisinin durdugu anlamina GELMEZ: tarayici konumu "
                  "telefon kilitlenince gondermeyi durdurur."),
    }


def konum_gecmisi(kullanici: str, saat: int = 12, limit: int = 500) -> dict:
    """Bir kişinin son N saatlik izi. Kişi KENDİ verisini buradan görür."""
    s = int(_sayi(saat, "saat", 1, 24 * 30))
    lim = int(_sayi(limit, "limit", 1, 5000))
    ad = str(kullanici).replace("'", "")[:60]
    kayitlar = _oku("""SELECT row_to_json(t) FROM (
      SELECT ts, enlem, boylam, dogruluk_m, hiz_m_s, kaynak, rota_id
        FROM core.saha_konum
       WHERE kullanici = '%s' AND ts > now() - interval '%d hours'
       ORDER BY ts DESC LIMIT %d) t;""" % (ad, s, lim))
    return {"kullanici": ad, "saat": s, "sayi": len(kayitlar),
            "noktalar": kayitlar, "saklama_gun": SAKLAMA_GUN}


def rota_uzerinde_mi(kullanici: str, rota_id: int) -> dict:
    """Kişinin son konumu, rotanın duraklarına göre nerede.

    Ölçüm verir, HÜKÜM vermez: "en yakın durak şu, şu kadar metre uzakta".
    "Rotadan çıktı" demek, sokağın karşısına geçmiş birini suçlamak olabilir.
    """
    ad = str(kullanici).replace("'", "")[:60]
    rid = int(_sayi(rota_id, "rota_id", 1, 10 ** 12))
    son = _oku("""SELECT row_to_json(t) FROM (
      SELECT enlem, boylam, ts, kac_saniye_once, tazelik
        FROM mart.saha_son_konum WHERE kullanici = '%s') t;""" % ad)
    if not son:
        return {"durum": "KONUM_YOK", "kullanici": ad}
    k = son[0]

    duraklar = _oku("""SELECT row_to_json(t) FROM (
      SELECT d.sira, h.ad, h.enlem, h.boylam
        FROM core.saha_rota_durak d
        JOIN mart.saha_hedef h
          ON (h.osm_tur = d.osm_tur AND h.osm_id = d.osm_id)
       WHERE d.rota_id = %d ORDER BY d.sira) t;""" % rid)
    if not duraklar:
        return {"durum": "DURAK_YOK", "kullanici": ad, "rota_id": rid}

    from jarvis import saha_rota
    konum = (k["enlem"], k["boylam"])
    en_yakin = min(duraklar,
                   key=lambda d: saha_rota.mesafe_m(konum, (d["enlem"], d["boylam"])))
    mesafe = saha_rota.mesafe_m(konum, (en_yakin["enlem"], en_yakin["boylam"]))
    return {
        "durum": "OLCULDU",
        "kullanici": ad,
        "rota_id": rid,
        "tazelik": k["tazelik"],
        "kac_saniye_once": k["kac_saniye_once"],
        "en_yakin_durak": {"sira": en_yakin["sira"], "ad": en_yakin["ad"]},
        "mesafe_m": round(mesafe, 1),
        "rotada": mesafe <= ROTADA_SAYILAN_MESAFE_M,
        "esik_m": ROTADA_SAYILAN_MESAFE_M,
    }


def konum_temizle(gun: int = SAKLAMA_GUN) -> dict:
    """Saklama süresi dolmuş konum kayıtlarını siler.

    Süresiz saklanan konum geçmişi, toplanma amacıyla ilgisi olmayan şeyleri
    de anlatır: ev adresi, mesai dışı alışkanlıklar. Bu yüzden silme bir
    bakım işi değil, verinin tutulma koşuludur.
    """
    g = int(_sayi(gun, "gun", 1, 3650))
    # Veri degistiren CTE EN UST DUZEYDE olmali; alt sorguya gomulemez.
    # Olculdu 25.09.2026: "WITH clause containing a data-modifying statement
    # must be at the top level".
    satir = _yaz("""WITH s AS (
        DELETE FROM core.saha_konum
         WHERE ts < now() - interval '%d days'
      RETURNING 1)
      SELECT row_to_json(t) FROM (SELECT count(*) AS silinen FROM s) t;"""
                 % g, {})
    silinen = satir[0]["silinen"] if satir else 0
    return {"silinen": silinen, "saklama_gun": g}
