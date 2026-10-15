"""TASARIM DEPARTMANI — "katalog istiyorum" dendiginde ne olacagi.

Sahip 22.09.2026: *"jarvise canva ile ilgili ayri bir sekme, ayri mudurluk
ve teknik personeller verelim... ama gene bizim calisanlarla entegre olsun.
Ben jarvise katalog istiyorum dedigimde markanin cizgisinde, markanin
gorselleri urun gorselleri ile birlikte yapilabilsin."*

ZINCIR
    istek  ->  sablon secimi  ->  veri haritalama  ->  MEVZUAT KAPISI
           ->  Canva autofill  ->  disa aktarim  ->  ONAY KUYRUGU

🔴 MEVZUAT KAPISI TASARIMDAN ONCE. Metin bir kere tasarima girdikten sonra
"bu iddia yazilamaz" demek gec kalmis olur: gorsel uretilmis, sahibin
onune gitmis, belki begenilmis olur. O yuzden `compliance.review()` autofill
CAGRISINDAN ONCE kosuyor ve BLOCKED bulgusu varsa tasarim HIC uretilmiyor.
Bu, para da harcamamak demek.

🔴 SABLON KODDA DEGIL KUTUKTE. `core.tasarim_sablon` tablosundan okunur.
Yeni bir cikti turu (raf etiketi, roll-up) eklemek yeni surum degil, yeni
satir demek.

🔴 ONAY MAKINENIN ELINDE DEGIL. Uretilen her is `onay IS NULL` olarak
defterlenir; onay sutununu yalniz human_approver yazabilir (030'daki
tetikleyici zorluyor). Makine kendi ciktisini onaylayamaz.

🔴 URUN GORSELI AI'YA CIZDIRILMEZ. Sahibin 14.09.2026 kurali: *"ambalaj
AI'ya yeniden tasarlattirilmaz."* Bu modul yalniz VAR OLAN varlik
kimliklerini sablona yerlestirir; gorsel uretmez, urettirmez.

🔴 GORSEL ALANI ORAN TUZAGI (olculdu 22.09.2026): sablonun gorsel cercevesi
1080x752 iken 263x854'luk dikey urun kesimi gonderilince Canva ortadan
zoomladi ve etiket kadraj disinda kaldi. Bu yuzden `uret()` gorsel alanina
giden varligin oranini KONTROL EDER ve sapma buyukse uyari defterler.
"""
from __future__ import annotations

import json
from jarvis.db_transport import run as db_run
from typing import Any

from jarvis import canva, compliance

# Sahibin cumlesinde gecen kelime -> is turu. Panelden secim beklemek
# yerine niyeti metinden cikariyoruz; bulamazsa SORUYORUZ, uydurmuyoruz.
NIYET = {
    "katalog": "katalog_sayfa",
    "kataloğ": "katalog_sayfa",
    "instagram": "instagram_post",
    "gönderi": "instagram_post",
    "post": "instagram_post",
    "story": "story",
    "hikaye": "story",
    "reels": "story",
    "afiş": "afis",
    "afis": "afis",
    "poster": "afis",
    "broşür": "brosur",
    "brosur": "brosur",
    "raf": "raf_etiketi",
    "etiket": "raf_etiketi",
    "roll-up": "rollup",
    "rollup": "rollup",
    "sunum": "sunum",
}


class TasarimHatasi(Exception):
    """Sahibin okuyabilecegi, Turkce ve sebepli hata."""


# ─────────────────────────────────────────────────────── veritabani
def _yaz(sql: str) -> str:
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=sql, capture_output=True, text=True, timeout=25, check=False)
    return (r.stderr or "").strip() if r.returncode else ""


def _oku(sql: str) -> list[dict]:
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=25, check=False)
    if r.returncode:
        # 🔴 SESSİZ BOŞ LİSTE YOK. Eskiden burada [] dönüyordu; sorgu
        # bozuksa çağıran taraf bunu "kayıt yok" diye okuyor ve sahibe
        # inandırıcı bir yanlış söylüyordu.
        raise TasarimHatasi(
            "psql başarısız: " + (r.stderr or "").strip()[:300])
    out = []
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                continue
    return out


def _tirnak(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


# ─────────────────────────────────────────────────────── sablon kutugu
def sablonlar(is_turu: str | None = None) -> list[dict]:
    """ÜRETİLEBİLİR şablonlar: Canva tasarımı bağlı ve durumu HAZIR.

    🔴 Kütüğün tamamı değil. Kütükte şartnamesi yazılı ama tasarımı
    olmayan satırlar var; üretim onları seçerse anlaşılmaz bir hatayla
    düşer. Tamamı için kutuk().
    """
    kosul = f"AND is_turu = {_tirnak(is_turu)}" if is_turu else ""
    return _oku(
        "SELECT row_to_json(t) FROM (SELECT sablon_id, sablon_kodu, is_turu, "
        "ad, canva_id, alan_haritasi, en, boy, gerekce, motor "
        f"FROM mart.tasarim_sablon_kutuk WHERE aktif AND uretilebilir {kosul} "
        "ORDER BY is_turu, sablon_id) t;")


def kutuk(faz: int | None = None) -> list[dict]:
    """Şablon kütüğünün TAMAMI: şartnameler + üretilebilirlik.

    Üretilemeyen satır bir eksiklik değil, bir SIRADAKİ İŞTİR: ölçüsü,
    alanları ve kuralları belli; yalnız Canva tasarımı bekliyor.
    """
    kosul = f"WHERE faz = {int(faz)}" if faz else ""
    return _oku(
        "SELECT row_to_json(t) FROM (SELECT sablon_kodu, is_turu, ad, "
        "kategori, platform, bicim, en, boy, en_mm, boy_mm, dpi, "
        "beklenen_alanlar, marka_kurallari, mevzuat_kurallari, surum, "
        "durum, motor, onay_zorunlu, faz, canva_id, uretilebilir, oran "
        f"FROM mart.tasarim_sablon_kutuk {kosul}) t;")


def kutuk_ozet() -> dict:
    """Panel ve Şablon Sorumlusu için: hangi faz ne durumda."""
    satirlar = _oku(
        "SELECT row_to_json(t) FROM (SELECT faz, kategori, count(*) AS adet, "
        "count(*) FILTER (WHERE uretilebilir) AS hazir "
        "FROM mart.tasarim_sablon_kutuk GROUP BY faz, kategori "
        "ORDER BY faz, kategori) t;")
    toplam = sum(r["adet"] for r in satirlar)
    hazir = sum(r["hazir"] for r in satirlar)
    return {"toplam": toplam, "hazir": hazir, "gruplar": satirlar}


def sablon_ekle(*, is_turu: str, ad: str, canva_id: str, gerekce: str,
                ekleyen: str, alan_haritasi: dict | None = None) -> dict:
    """Canva tasarımını şablon olarak kütükler.

    🔴 ALANLARI CANVA'YA SORAR, VARSAYMAZ. Tasarımın gerçekten hangi
    doldurulabilir alanları olduğunu `/designs/{id}/dataset` söyler.
    Alansız bir tasarım şablon olamaz -- autofill onu dolduramaz ve
    kütüğe girerse sessizce bozuk bir şablon üretiriz.
    """
    if len((gerekce or "").strip()) < 12:
        raise TasarimHatasi("gerekçe en az 12 karakter olmalı — şablonun "
                            "neden seçildiği kayıtta dursun")
    try:
        d = canva._cagir(f"/designs/{canva_id}/dataset")
    except canva.CanvaHatasi as h:
        raise TasarimHatasi(f"Canva tasarımı okunamadı: {h}") from None
    alanlar = d.get("dataset") or {}
    if not alanlar:
        raise TasarimHatasi(
            f"{canva_id} tasarımının doldurulabilir alanı yok. Önce "
            "alanları işaretleyin (update_autofill_field), sonra kütükleyin.")

    harita = alan_haritasi or {ad_: ad_ for ad_ in alanlar}
    eksik = set(harita) - set(alanlar)
    if eksik:
        raise TasarimHatasi(
            f"haritada olup tasarımda olmayan alan: {sorted(eksik)}. "
            f"Tasarımdaki alanlar: {sorted(alanlar)}")

    hata = _yaz(
        "INSERT INTO core.tasarim_sablon "
        "(is_turu, ad, canva_id, alan_haritasi, gerekce, ekleyen) VALUES ("
        f"{_tirnak(is_turu)}, {_tirnak(ad)}, {_tirnak(canva_id)}, "
        f"{_tirnak(json.dumps(harita, ensure_ascii=False))}::jsonb, "
        f"{_tirnak(gerekce)}, {_tirnak(ekleyen)}) "
        "ON CONFLICT (is_turu, canva_id) DO UPDATE SET "
        "alan_haritasi = EXCLUDED.alan_haritasi, aktif = true;")
    if hata:
        raise TasarimHatasi(f"kütüğe yazılamadı: {hata[:200]}")
    return {"is_turu": is_turu, "canva_id": canva_id,
            "alanlar": sorted(alanlar), "harita": harita}


# ─────────────────────────────────────────────────────── niyet
def is_turu_cikar(istek: str) -> str | None:
    """Sahibin cümlesinden iş türünü çıkarır; emin değilse None döner.

    🔴 TAHMİN ETMEZ. "Bir şeyler yap" gibi bir cümleden katalog üretmek,
    yanlış işi para harcayarak yapmak olur. Bulamazsa çağıran taraf
    sorar.
    """
    import re

    duz = compliance.fold(istek or "")
    # 🔴 KELİME ORTASINDA EŞLEŞME YOK. "kartpostal" içinde "post" geçiyor;
    # düz alt dize araması bunu Instagram gönderisi sanıyordu. Türkçe'de
    # bu tuzak daha önce de yaşandı, bkz. jarvis/turkish.py dersi.
    # Sonuna ek gelebilir ("afişi", "kataloğa") — bu yüzden sağ tarafta
    # sınır aranmıyor, yalnız SOL tarafta kelime başı şartı var.
    en_iyi = None
    for kelime, tur in NIYET.items():
        k = compliance.fold(kelime)
        if re.search(r"(?<![\w])" + re.escape(k), duz):
            if en_iyi is None or len(k) > len(en_iyi[0]):
                en_iyi = (k, tur)
    return en_iyi[1] if en_iyi else None


# ─────────────────────────────────────────────────────── uretim
def _metin_denetimi(veri: dict) -> dict:
    """Şablona gidecek TÜM metinleri mevzuat kapısından geçirir."""
    metinler = [str(v) for v in veri.values() if isinstance(v, str)]
    birlesik = "\n".join(metinler)
    if not birlesik.strip():
        return {"bulgu": [], "engel": False}
    inceleme = compliance.review(birlesik)
    bulgular = [f.to_dict() for f in getattr(inceleme, "findings", [])]
    engel = any(b.get("label") == compliance.BLOCKED for b in bulgular)
    return {"bulgu": bulgular, "engel": engel,
            "kaynak": compliance.RULES_SOURCE}


def _oran_uyarisi(sablon: dict, gorsel_varlik: str | None) -> str | None:
    """Görsel alanına giden varlığın oranı çerçeveye uyuyor mu?

    22.09.2026'da ölçüldü: 263x854 dikey kesim, 1080x752 yatay çerçeveye
    konunca Canva ortadan zoomladı ve ürün etiketi kadraj dışında kaldı.
    Boyutu Canva'dan sorup kıyaslıyoruz.
    """
    if not gorsel_varlik or not (sablon.get("en") and sablon.get("boy")):
        return None
    try:
        v = canva._cagir(f"/assets/{gorsel_varlik}")
    except canva.CanvaHatasi:
        return None
    b = ((v.get("asset") or {}).get("thumbnail") or {})
    ven, vboy = b.get("width"), b.get("height")
    if not (ven and vboy):
        return None
    cerceve = sablon["en"] / sablon["boy"]
    varlik = ven / vboy
    if cerceve <= 0 or varlik <= 0:
        return None
    sapma = max(cerceve, varlik) / min(cerceve, varlik)
    if sapma >= 1.4:
        return (f"görsel oranı çerçeveye uymuyor (çerçeve {cerceve:.2f}, "
                f"görsel {varlik:.2f}) — Canva kırpacak, ürün kadraj "
                "dışında kalabilir")
    return None


def uret(*, is_turu: str, veri: dict, isteyen: str, istek: str,
         sablon_id: int | None = None) -> dict:
    """Şablonu veriyle doldurup tasarım üretir ve onay kuyruğuna koyar."""
    adaylar = sablonlar(is_turu)
    if sablon_id:
        adaylar = [s for s in adaylar if s["sablon_id"] == sablon_id]
    if not adaylar:
        # 🔴 "YOK" ile "HENÜZ YAPILMADI" AYNI ŞEY DEĞİL. Kütükte
        # şartnamesi varsa sahibe eksik olanı tam olarak söyleriz.
        tanimli = [k for k in kutuk() if k["is_turu"] == is_turu]
        if tanimli:
            t0 = tanimli[0]
            olcu = (f"{t0['en_mm']}x{t0['boy_mm']} mm @{t0['dpi']} dpi"
                    if t0.get("en_mm") else f"{t0['en']}x{t0['boy']} px")
            raise TasarimHatasi(
                f"'{is_turu}' kütükte TANIMLI ({t0['sablon_kodu']}, {olcu}, "
                f"alanlar: {t0['beklenen_alanlar']}) ama Canva tasarımı "
                "henüz bağlanmadı — üretilemez. Eksik olan tek şey: bu "
                "ölçüde bir tasarım açıp alanlarını işaretlemek.")
        raise TasarimHatasi(
            f"'{is_turu}' kütükte hiç tanımlı değil. Önce şartnamesini "
            "yazın (ölçü, alanlar, kurallar), sonra tasarımını bağlayın.")
    sablon = adaylar[0]

    # 1 ── MEVZUAT KAPISI (tasarımdan ÖNCE, para harcamadan)
    denetim = _metin_denetimi(veri)
    if denetim["engel"]:
        engeller = [b["matched"] for b in denetim["bulgu"]
                    if b.get("label") == compliance.BLOCKED]
        _defterle(is_turu, sablon, isteyen, istek, veri, None, None,
                  "BASARISIZ", denetim, 0)
        raise TasarimHatasi(
            "mevzuat kapısı geçilmedi, tasarım ÜRETİLMEDİ. Engelleyen "
            f"ifadeler: {engeller}. Metni düzeltip tekrar isteyin.")

    # 2 ── veriyi Canva alan adlarına çevir
    harita = sablon.get("alan_haritasi") or {}
    try:
        sema = canva._cagir(f"/designs/{sablon['canva_id']}/dataset")
    except canva.CanvaHatasi as h:
        raise TasarimHatasi(f"şablon okunamadı: {h}") from None
    alanlar = sema.get("dataset") or {}

    govde: dict[str, Any] = {}
    gorsel_varlik = None
    for canva_alan, tanim in alanlar.items():
        bizim_ad = harita.get(canva_alan, canva_alan)
        deger = veri.get(bizim_ad)
        if deger is None:
            continue
        if tanim.get("type") == "text":
            govde[canva_alan] = {"type": "text", "text": str(deger)}
        elif tanim.get("type") == "image":
            gorsel_varlik = str(deger)
            govde[canva_alan] = {"type": "image", "asset_id": gorsel_varlik}

    eksik = [a for a in alanlar if a not in govde]
    if eksik:
        raise TasarimHatasi(
            f"şablonun şu alanları için veri yok: {eksik}. Eksik alan "
            "gönderilirse Canva yer tutucu metni olduğu gibi bırakır "
            "(ör. 'reallygreatsite.com') ve yayına o gider.")

    uyari = _oran_uyarisi(sablon, gorsel_varlik)
    if uyari:
        denetim["oran_uyarisi"] = uyari

    # 3 ── Canva'da üret
    is_ = canva._cagir("/autofills", metot="POST", govde={
        "type": "create_from_design",
        "design_id": sablon["canva_id"],
        "title": f"{sablon['ad']} — {istek[:60]}",
        "data": govde,
    })
    sonuc = canva._is_bekle(f"/autofills/{is_['job']['id']}", "design")
    tasarim_id = (sonuc or {}).get("id")
    if not tasarim_id:
        raise TasarimHatasi(f"tasarım üretilmedi: {sonuc}")

    # 4 ── dışa aktar
    try:
        baglar = canva.disa_aktar(tasarim_id, "png")
        cikti = baglar[0] if baglar else None
    except canva.CanvaHatasi as h:
        cikti = None
        denetim["disa_aktarim_hatasi"] = str(h)[:200]

    is_id = _defterle(is_turu, sablon, isteyen, istek, veri, tasarim_id,
                      cikti, "URETILDI", denetim, 0)
    return {"is_id": is_id, "tasarim": tasarim_id, "cikti": cikti,
            "sablon": sablon["ad"], "denetim": denetim,
            "onay": "bekliyor — yalnız sahip onaylayabilir"}


def _defterle(is_turu, sablon, isteyen, istek, veri, tasarim, cikti,
              durum, denetim, maliyet) -> int | None:
    hata = _yaz(
        "INSERT INTO core.tasarim_isi (is_turu, sablon_id, isteyen, istek, "
        "veri, canva_tasarim, disa_aktarim, durum, denetim, maliyet_tl) "
        f"VALUES ({_tirnak(is_turu)}, "
        f"{sablon['sablon_id'] if sablon else 'NULL'}, {_tirnak(isteyen)}, "
        f"{_tirnak(istek)}, "
        f"{_tirnak(json.dumps(veri, ensure_ascii=False))}::jsonb, "
        f"{_tirnak(tasarim) if tasarim else 'NULL'}, "
        f"{_tirnak(cikti) if cikti else 'NULL'}, {_tirnak(durum)}, "
        f"{_tirnak(json.dumps(denetim, ensure_ascii=False))}::jsonb, "
        f"{maliyet});")
    if hata:
        return None
    satir = _oku("SELECT row_to_json(t) FROM (SELECT max(is_id) AS id "
                 "FROM core.tasarim_isi) t;")
    return (satir[0] or {}).get("id") if satir else None


def isler(yalniz_onaysiz: bool = False, adet: int = 30) -> list[dict]:
    """Panel için: ne üretildi, onay bekliyor mu."""
    kosul = "WHERE onay_bekliyor" if yalniz_onaysiz else ""
    return _oku("SELECT row_to_json(t) FROM (SELECT * FROM "
                f"mart.tasarim_guncel {kosul} LIMIT {int(adet)}) t;")
