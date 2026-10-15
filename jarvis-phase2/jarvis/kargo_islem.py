"""KARGO İŞLEMLERİ — panelin BasitKargo ile konuştuğu tek yer.

Sahip 21.09.2026: *"taşıyıcıyı seçebilmek, karşı ödemeli mi biz mi ödemeli
gibi bilgileri seçebilme gibi panel istiyorum. burası bizim merkez üssümüz."*

AKIŞ (ve hangisi para harcar)
    1. taslak_olustur   create_shipment        ÜCRETSİZ  -> DRAFT
    2. ucret_sor        get_shipment_fee       ÜCRETSİZ  -> taşıyıcı fiyatları
    3. barkod_uret      generate_shipment_code 🔴 PARA HARCAR
    4. etiket_al        get_label              ÜCRETSİZ  -> PNG
    5. scripts/kargo-etiket.py                           -> HB-1006 .docx

🔴 3. ADIM NEDEN BU KADAR UZUN
Ucun kendi açıklaması: *"THIS CHARGES THE FIRM'S BALANCE and calls the
carrier."* Geri alınamaz. Bu yüzden çağrıdan önce üç şey yapılır:

  a) Fiyat UÇTAN YENİDEN sorulur ve operatörün gördüğü rakamla
     karşılaştırılır. Ekranda 74 TL görüp 96 TL ödemek, panelin sahibine
     yalan söylemesidir.
  b) `core.kargo_karar` tablosuna ISTENDI satırı yazılır. Kısmî tekil
     dizin, aynı siparişin ikinci kez istenmesini VERİTABANI seviyesinde
     durdurur -- çift tıklama da, iki sekme de aynı yere çıkar.
  c) Ancak ondan sonra `onayli=True` verilir.

Satır ÇAĞRIDAN ÖNCE yazılır, sonra değil: çağrı patlarsa hiç iz kalmazdı,
oysa para gitmiş olabilir.

🔴 OTOMATİK ÇAĞRILAMAZ. Bu modülü yalnız panelin POST ucu çağırır; o uç
oturum çerezi ve CSRF başlığı ister. Döngünün, ajanların, zamanlayıcının
oturumu yoktur. Para harcayan yol, insanın ekrandaki düğmesinden geçer.
"""
from __future__ import annotations

import json
import secrets
from jarvis.db_transport import run as db_run
from typing import Any

from jarvis.basitkargo import Kargo, KargoHatasi

# Uçtaki taşıyıcı kodları (araç açıklamasından birebir).
TASIYICILAR = ("ARAS", "MNG", "YURTICI", "SURAT", "PTT",
               "HEPSIJET", "KOLAYGELSIN", "SENDEO")
ODEME_TURU = ("CASH", "CREDIT_CARD")

# Gösterilen fiyatla gerçek fiyat arasında kabul edilen fark.
# Sıfır tolerans kuruş yuvarlamasında paneli kilitlerdi; 1 TL, sahibin
# kararını değiştirecek bir fark değil.
UCRET_TOLERANSI = 1.0


class IslemHatasi(Exception):
    """Panelin kullanıcıya gösterebileceği, Türkçe ve sebepli hata."""


# --------------------------------------------------------------- yardımcılar
def _psql(sql: str, zaman: int = 20) -> tuple[int, str]:
    """SQL'i stdin'den geçirir.

    🔴 Değerler argv'ye KONMAZ. Bu projede kabuk tırnaklaması defalarca
    bozdu; uzak bash `$$` dizisini PID'e çeviriyordu. Yol: stdin + rastgele
    etiketli dolar-tırnak.
    """
    try:
        r = db_run(
            ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
             "-U", "n8n", "-d", "n8n", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=zaman, check=False)
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)[:200]
    return r.returncode, (r.stderr or r.stdout or "").strip()[:300]


def _dolar_etiket(yuk: str, onek: str) -> str:
    etiket = onek + secrets.token_hex(8)
    if f"${etiket}$" in yuk:
        raise IslemHatasi("kodlama çakışması, işlem yapılmadı")
    return etiket


def _sayi(x: Any) -> float | None:
    if x in (None, "", "-"):
        return None
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _oku(sql: str) -> list[dict]:
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=25, check=False)
    if r.returncode:
        return []
    out = []
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                continue
    return out


# ------------------------------------------------------------------- 1) liste
def _alt(sozluk: Any, *yol: str) -> Any:
    """İç içe alanı güvenle okur; ara katman yoksa None döner."""
    su = sozluk
    for ad in yol:
        if not isinstance(su, dict):
            return None
        su = su.get(ad)
    return su


def _gonderi_ozet(g: dict) -> dict:
    """Bir gönderiyi panelin tek satırına indirger.

    🔴 ALAN ADLARI TAHMİN EDİLMEDİ, UÇTAN OKUNDU. İlk sürüm `handlerCode`
    ve `recipientName` gibi düz alanlar bekliyordu; gerçek cevap iç içe
    (`shipmentInfo.handler.code`, `recipient.name`) ve taşıyıcı sütunu
    panelde boş çıkıyordu -- hata vermeden, sessizce.

    Sahibin *"sipariş → kargo → teslimat tek ekranda"* isteği de buradan
    karşılanıyor: uç `lastState` alanını zaten Türkçe veriyor
    ("Teslim Edildi"), çevirmeye gerek yok.
    """
    kargo = g.get("shipmentInfo") or {}
    kapida = g.get("codInfo") or {}
    fiyat = g.get("priceInfo") or {}
    kalemler = _alt(g, "content", "items") or []
    return {
        "siparis_id": g.get("id"),
        "durum": g.get("status"),
        "son_durum": kargo.get("lastState"),      # uçtan Türkçe geliyor
        "alici": _alt(g, "recipient", "name"),
        "nere": " / ".join(x for x in (_alt(g, "recipient", "city"),
                                       _alt(g, "recipient", "town")) if x),
        "icerik": ", ".join(
            f"{k.get('name')}×{k.get('quantity')}" for k in kalemler
            if isinstance(k, dict) and k.get("name")),
        "desi": kargo.get("handlerDesi") or _alt(g, "content", "totalDesiKg"),
        "tasiyici": _alt(kargo, "handler", "code"),
        "tasiyici_adi": _alt(kargo, "handler", "name"),
        "barkod": kargo.get("handlerShipmentCode") or g.get("barcode"),
        "takip_linki": kargo.get("handlerShipmentTrackingLink"),
        "karsi_odemeli": bool(kapida.get("collectOnDelivery")),
        "kapida_tutar": kapida.get("amount") or None,
        "kapida_tur": kapida.get("type"),
        "tahsilat_durumu": kapida.get("collectionStatusText"),
        # 🔴 `shipmentFee` + `extraFee` toplamı `totalCost`a EŞİT DEĞİL
        # (ölçüldü: 161.08 + 53.17 ≠ 162.08). Bu yüzden hiçbiri toplanmıyor,
        # üçü de uçtaki adıyla ayrı gösteriliyor. Toplasaydık panel
        # uydurulmuş bir rakam yazardı.
        "ucret": fiyat.get("shipmentFee"),
        "ek_ucret": fiyat.get("extraFee"),
        "toplam_maliyet": fiyat.get("totalCost"),
        "olusturuldu": g.get("createdTime"),
        "kargoya_verildi": kargo.get("shippedTime"),
        "teslim_edildi": kargo.get("deliveredTime"),
    }


def gonderiler(limit: int = 15) -> dict:
    """Panelin açılışta gördüğü tablo: gönderiler + verilmiş kararlar."""
    veri: dict[str, Any] = {"tasiyicilar": list(TASIYICILAR),
                            "odeme_turleri": list(ODEME_TURU)}
    k = Kargo()
    try:
        r = k.cagir("list_shipments", {"size": min(int(limit), 25)})
        ham = ((r.get("veri") or {}).get("items")) or []
    except KargoHatasi as hata:
        # 🔴 "kargo yok" DEMEZ. Sormak başarısız oldu; sormamakla yokluk
        # aynı şey değil.
        veri["gonderi_hatasi"] = f"BasitKargo'ya sorulamadı: {str(hata)[:200]}"
        ham = []
    veri["gonderiler"] = [_gonderi_ozet(g) for g in ham if isinstance(g, dict)]
    veri["kararlar"] = _oku(
        "SELECT row_to_json(x) FROM (SELECT * FROM mart.kargo_karar_ozet"
        " LIMIT 25) x")
    return veri


def kapida_ozet() -> dict:
    """Elle satış (kapıda ödeme) — `mart.gonderi` üzerinden.

    🔴 BU FONKSİYON BİR KEZ YANLIŞ YAZILDI, ÖLÇÜMLE DÜZELTİLDİ.
    İlk sürüm BasitKargo ucunu tek tek gezip kendi sayımını yapıyordu ve
    "kapıda ödenen 15.555 TL ciro tablosunda yok" diyordu. İkisi de hatalı:

    1. Veri ZATEN YEREL. `raw.bk_shipment` 50 gönderiyi tutuyor ve düzenli
       çekiliyor. Uca tekrar sormak hem yavaş hem de aynı gerçeğin ikinci
       bir sayımını üretiyordu.
    2. Sınıflandırma ZATEN VAR. `mart.gonderi.sinif` gönderiyi SATIS /
       ELLE_SATIS / IADE / NUMUNE / UNKNOWN diye ayırıyor; CR-010'da
       kurulmuş. 11 kapıda ödemeli gönderinin 2'si Wix siparişiyle
       EŞLEŞİYOR (4.480 TL) -- yani o para zaten kayıtlı. Kayıt dışı olan
       kısım 9 gönderi / 11.075 TL, ve onun da adı konmuş: ELLE_SATIS,
       sütunu `elle_ciro_tahsil`.

    GERÇEK BOŞLUK ŞUYDU: `mart.gunluk` bu rakamı (`ciro_elle_tahsil`)
    hesaplıyor ama panelde hiçbir yer okumuyordu -- kodda tek bir referans
    bile yok. Veri eksik değildi, GÖSTERİLMİYORDU.

    🔴 BURADAN CİRO YAZILMAZ; yalnız okunur.
    """
    satirlar = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT gonderi_id, gun, sinif, durum, tasiyici, sehir,"
        "        cod_var, cod_tutar, cod_durum, siparis_id,"
        "        elle_ciro_tahsil, elle_ciro_bekleyen,"
        "        array_to_string(urun_adlari, ', ') AS urun"
        "   FROM mart.gonderi"
        "  WHERE cod_var"
        "  ORDER BY gun DESC) x")
    ozet = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT sinif,"
        "        count(*)::int AS adet,"
        "        COALESCE(sum(cod_tutar), 0)::numeric AS cod_toplam,"
        "        COALESCE(sum(elle_ciro_tahsil), 0)::numeric AS tahsil,"
        "        COALESCE(sum(elle_ciro_bekleyen), 0)::numeric AS bekleyen"
        "   FROM mart.gonderi WHERE cod_var"
        "  GROUP BY sinif ORDER BY 2 DESC) x")
    sinifsiz = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT count(*)::int AS adet FROM mart.gonderi"
        "  WHERE sinif IN ('UNKNOWN', 'YON_BILINMIYOR')) x")

    def _top(ad: str) -> float:
        return round(sum(float(s.get(ad) or 0) for s in ozet), 2)

    return {
        "kapida_adet": sum(int(s.get("adet") or 0) for s in ozet),
        "kapida_toplam": _top("cod_toplam"),
        # 🔴 İKİSİ AYRI RAKAM. "Kapıda ödenen" ile "kayıt dışı kalan" aynı
        # şey değil: Wix siparişiyle eşleşen kapıda ödemeli gönderiler
        # zaten ciroda. Tek rakam göstermek sahibi yanıltırdı.
        "elle_tahsil": _top("tahsil"),
        "elle_bekleyen": _top("bekleyen"),
        "siniflar": ozet,
        "sinifsiz_gonderi": (sinifsiz[0].get("adet") if sinifsiz else 0),
        "satirlar": satirlar,
        "not": ("ELLE_SATIS = kapıda ödenmiş ama Wix siparişi olmayan "
                "gönderi (telefon/WhatsApp satışı). SATIS sınıfındakiler "
                "zaten ciroda. Sınıfsız gönderiler SATIŞLAR panelinden "
                "beyan edilmeden ciroya giremez."),
    }


# ------------------------------------------------------------------- 2) taslak
def taslak_olustur(*, alici: str, telefon: str, il: str, ilce: str,
                   adres: str, icerik: str, desi: Any = None,
                   karsi_odemeli: bool = False, kapida_tutar: Any = None,
                   kapida_tur: str = "CASH", referans: str = "") -> dict:
    """DRAFT gönderi. Ücretsizdir, kargo çağrılmaz, barkod üretilmez."""
    eksik = [ad for ad, deger in (
        ("alıcı adı", alici), ("telefon", telefon), ("il", il),
        ("ilçe", ilce), ("adres", adres), ("içerik", icerik))
        if not (deger or "").strip()]
    if eksik:
        raise IslemHatasi("şu alanlar boş bırakılamaz: " + ", ".join(eksik))

    girdi: dict[str, Any] = {
        "recipientName": alici.strip()[:200],
        "recipientPhone": "".join(ch for ch in telefon if ch.isdigit())[:15],
        "recipientCity": il.strip()[:60],
        "recipientTown": ilce.strip()[:60],
        "recipientAddress": adres.strip()[:500],
        "contentName": icerik.strip()[:200],
    }
    if not girdi["recipientPhone"]:
        raise IslemHatasi("telefon rakam içermiyor")
    d = _sayi(desi)
    if d is not None:
        if d <= 0:
            raise IslemHatasi("desi sıfır veya negatif olamaz")
        girdi["desiKg"] = d
    if referans.strip():
        girdi["reference"] = referans.strip()[:120]

    if karsi_odemeli:
        tutar = _sayi(kapida_tutar)
        # 🔴 Tutarsız karşı ödemeli gönderi, kuryenin kapıda YANLIŞ para
        # toplaması demektir. Veritabanı da bunu reddediyor; burada
        # reddetmek, sahibe hatayı SQL diliyle değil Türkçe söyler.
        if tutar is None or tutar <= 0:
            raise IslemHatasi("karşı ödemeli seçildi ama kapıda tahsil "
                              "edilecek tutar girilmedi")
        if kapida_tur not in ODEME_TURU:
            raise IslemHatasi(f"tahsilat türü {' veya '.join(ODEME_TURU)} olmalı")
        girdi["codAmount"] = tutar
        girdi["codType"] = kapida_tur

    k = Kargo()
    try:
        sonuc = k.cagir("create_shipment", girdi)
    except KargoHatasi as hata:
        raise IslemHatasi(f"taslak açılamadı: {str(hata)[:220]}") from hata
    veri = sonuc.get("veri") or {}
    siparis_id = veri.get("id") or veri.get("orderId")
    if not siparis_id:
        raise IslemHatasi("uç taslak kimliği döndürmedi; gönderi açılmadı "
                          "sayılır")
    return {"ok": True, "siparis_id": siparis_id, "durum": veri.get("status"),
            "karsi_odemeli": karsi_odemeli}


# -------------------------------------------------------------------- 3) ücret
def _ucret_listesi(k: Kargo, siparis_id: str) -> list[dict]:
    """Taşıyıcı fiyat listesi.

    🔴 ALANLAR UÇTAN OKUNDU. Taşıyıcı adı `handlerName` değil düz
    `handler`; ilk sürüm `handlerName` arayıp panelde ad yerine kodu
    ("HEPSIJET") gösteriyordu. Uç ayrıca üç şey daha veriyor ve üçü de
    kararı etkiliyor:
      duration  tahmini teslim günü
      codFee    karşı ödemeli gönderinin EK ücreti (kargo ücretine dahil DEĞİL)
      disabled  taşıyıcı bu gönderi için kapalı -- seçtirilmemeli
    """
    sonuc = k.cagir("get_shipment_fee", {"orderId": siparis_id})
    veri = sonuc.get("veri")
    ham = veri if isinstance(veri, list) else (veri or {}).get("items") or []
    cikti = []
    for s in ham:
        if not isinstance(s, dict):
            continue
        kod = s.get("handlerCode") or s.get("code")
        if not kod:
            continue
        cikti.append({
            "tasiyici": kod,
            "ad": s.get("handler") or s.get("handlerName") or kod,
            "ucret": _sayi(s.get("fee") if s.get("fee") is not None
                           else s.get("price")),
            "kapida_ucret": _sayi(s.get("codFee")) or 0.0,
            "gun": _sayi(s.get("duration")),
            # Kapalı taşıyıcı listeye girer ama seçilemez: gizleseydik
            # sahip "Aras neden yok" diye sorardı, cevabı olmazdı.
            "kapali": bool(s.get("disabled")),
            "risk": s.get("riskLabel") or s.get("riskNote"),
        })
    return cikti


def ucret_sor(siparis_id: str) -> dict:
    """Hangi taşıyıcı ne kadar. Ücretsizdir; para harcamaz."""
    if not (siparis_id or "").strip():
        raise IslemHatasi("sipariş kimliği verilmedi")
    k = Kargo()
    try:
        liste = _ucret_listesi(k, siparis_id.strip())
    except KargoHatasi as hata:
        raise IslemHatasi(f"fiyat alınamadı: {str(hata)[:220]}") from hata
    if not liste:
        # SORULDU ama cevap boş: bu da bir bulgudur, "ücretsiz" değil.
        return {"siparis_id": siparis_id, "fiyatlar": [],
                "uyari": "uç fiyat listesi döndürmedi — taşıyıcı seçimi "
                         "yapılmadan barkod üretilmemeli"}
    # Ucuzdan pahalıya; kapalı ve fiyatsız olanlar en sona.
    return {"siparis_id": siparis_id,
            "fiyatlar": sorted(liste, key=lambda x: (
                bool(x.get("kapali")), x["ucret"] is None, x["ucret"] or 0))}


# ------------------------------------------------------------------- 4) barkod
def _karar_yaz(siparis_id: str, tasiyici: str, ucret: float | None,
               karsi_odemeli: bool, kapida_tutar: float | None,
               veren: str) -> int:
    """ISTENDI satırı. Dönen kimlik, sonucu işaretlemek için kullanılır."""
    yuk = json.dumps({
        "siparis_id": siparis_id, "tasiyici": tasiyici,
        "gosterilen_ucret": ucret, "karsi_odemeli": karsi_odemeli,
        "karsi_odeme_tutari": kapida_tutar, "veren": veren[:80],
    }, ensure_ascii=False)
    etiket = _dolar_etiket(yuk, "kk")
    sql = ("\\set ON_ERROR_STOP on\n"
           "\\pset tuples_only on\n\\pset format unaligned\n"
           "BEGIN;\n"
           "SET SESSION AUTHORIZATION human_approver;\n"
           "INSERT INTO core.kargo_karar (siparis_id,tasiyici,gosterilen_ucret,"
           "karsi_odemeli,karsi_odeme_tutari,karar,veren)\n"
           "SELECT j->>'siparis_id', j->>'tasiyici',\n"
           "       (j->>'gosterilen_ucret')::numeric, (j->>'karsi_odemeli')::bool,\n"
           "       (j->>'karsi_odeme_tutari')::numeric, 'ISTENDI', j->>'veren'\n"
           f"  FROM (SELECT ${etiket}${yuk}${etiket}$::jsonb AS j) t\n"
           "RETURNING karar_id;\n"
           "COMMIT;\n")
    r = db_run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=sql, capture_output=True, text=True, timeout=20, check=False)
    if r.returncode:
        stderr = (r.stderr or "")
        if "kargo_karar_tek_acik" in stderr:
            raise IslemHatasi(
                "bu sipariş için zaten bir barkod isteği var. Çift tıklama "
                "ya da açık ikinci sekme olabilir; kargo kararları "
                "listesinden durumuna bakın.")
        raise IslemHatasi(f"karar kaydı yazılamadı, para harcanmadı: "
                          f"{stderr.strip()[:200]}")
    for satir in (r.stdout or "").splitlines():
        if satir.strip().isdigit():
            return int(satir.strip())
    raise IslemHatasi("karar kaydı kimliği okunamadı, para harcanmadı")


def _karar_kapat(karar_id: int, durum: str, barkod: str | None,
                 hata: str | None) -> None:
    yuk = json.dumps({"karar": durum, "barkod": barkod,
                      "hata": (hata or "")[:400] or None}, ensure_ascii=False)
    etiket = _dolar_etiket(yuk, "kz")
    sql = ("\\set ON_ERROR_STOP on\n"
           "BEGIN;\n"
           "SET SESSION AUTHORIZATION human_approver;\n"
           "UPDATE core.kargo_karar SET karar = j->>'karar',\n"
           "       barkod = j->>'barkod', hata = j->>'hata'\n"
           f"  FROM (SELECT ${etiket}${yuk}${etiket}$::jsonb AS j) t\n"
           f" WHERE karar_id = {int(karar_id)};\n"
           "COMMIT;\n")
    _psql(sql)


def barkod_uret(*, siparis_id: str, tasiyici: str, gosterilen_ucret: Any,
                veren: str, karsi_odemeli: bool = False,
                kapida_tutar: Any = None) -> dict:
    """🔴 ŞİRKETİN BAKİYESİNDEN PARA DÜŞÜRÜR. Tek para harcayan fonksiyon."""
    siparis_id = (siparis_id or "").strip()
    tasiyici = (tasiyici or "").strip().upper()
    if not siparis_id:
        raise IslemHatasi("sipariş kimliği verilmedi")
    if tasiyici not in TASIYICILAR:
        raise IslemHatasi(f"taşıyıcı tanınmadı: {tasiyici or '(boş)'}")

    k = Kargo()

    # (a) Fiyatı UÇTAN yeniden sor. Ekranda görülen rakam eskimişse
    #     sahip, onaylamadığı bir tutarı ödemiş olurdu.
    beklenen = _sayi(gosterilen_ucret)
    try:
        liste = _ucret_listesi(k, siparis_id)
    except KargoHatasi as hata:
        raise IslemHatasi(f"fiyat doğrulanamadı, para harcanmadı: "
                          f"{str(hata)[:200]}") from hata
    satir = next((s for s in liste if s["tasiyici"] == tasiyici), None)
    if satir is None:
        raise IslemHatasi(
            f"{tasiyici} bu gönderi için fiyat listesinde yok; "
            "para harcanmadı")
    if satir.get("kapali"):
        raise IslemHatasi(
            f"{satir.get('ad') or tasiyici} bu gönderi için kapalı; "
            "para harcanmadı")
    guncel = satir["ucret"]
    if guncel is None:
        raise IslemHatasi(f"{satir.get('ad') or tasiyici} fiyat döndürmedi; "
                          "para harcanmadı")
    if beklenen is not None and abs(guncel - beklenen) > UCRET_TOLERANSI:
        raise IslemHatasi(
            f"fiyat değişmiş: ekranda {beklenen:.2f} TL, şu an "
            f"{guncel:.2f} TL. Onay yenilenmeden para harcanmaz.")

    # (b) Kararı YAZ. Buradan sonrası geri alınamaz.
    karar_id = _karar_yaz(siparis_id, tasiyici, guncel, karsi_odemeli,
                          _sayi(kapida_tutar), veren)

    # (c) Ancak şimdi para harcanır.
    try:
        sonuc = k.cagir("generate_shipment_code",
                        {"orderId": siparis_id, "handlerCode": tasiyici},
                        onayli=True)
    except KargoHatasi as hata:
        _karar_kapat(karar_id, "HATA", None, str(hata))
        raise IslemHatasi(
            f"barkod üretilemedi: {str(hata)[:200]} — 🔴 uç parayı düşürüp "
            "yine de hata döndürmüş olabilir. Tekrar denemeden ÖNCE "
            "gönderi listesinden barkodun oluşup oluşmadığına bakın."
        ) from hata

    veri = sonuc.get("veri") or {}
    barkod = (veri.get("trackingNumber") or veri.get("barcode")
              or veri.get("code"))
    _karar_kapat(karar_id, "ONAYLANDI", barkod, None)
    return {"ok": True, "siparis_id": siparis_id, "tasiyici": tasiyici,
            "ucret": guncel, "barkod": barkod, "karar_id": karar_id}
