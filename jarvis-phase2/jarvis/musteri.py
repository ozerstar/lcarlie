"""MÜŞTERİ KARTI ve İADE TAKİBİ.

Sahip 21.09.2026: *"iade değişim takibi"* ve *"müşteri kartı — kim kaç kere
almış"*.

🔴 KİŞİSEL VERİ NEREDE DURUR, NEREDE DURMAZ
Ad, telefon ve e-posta `raw.wix_order.ham->'buyerInfo'` içinde. Bu modül
onları İSTEK ANINDA okur ve yalnız oturum açmış panele verir; hiçbir
`mart` görünümüne, hiçbir `core` tablosuna ve CompanyMemory'ye YAZMAZ.
Sebep [[lcarlie-konusma-paneli]] ile aynı: müşteri verisi şirket
hafızasına girerse modelin kanıt katmanına karışır ve oradan çıkarılamaz.
Toplu analiz (kaç kere aldı, ne kadar harcadı) `buyer_id` üzerinden
yapılır -- ad olmadan da doğru çalışır.

🔴 "İADE YOK" DEMEK, "İADE OLMADI" DEMEK DEĞİL
Ölçüm (21.09.2026): 37 Wix siparişinin HİÇBİRİNDE `refunds` kaydı yok,
ödeme durumları yalnız PAID (32) ve NOT_PAID/CANCELED (5). BasitKargo'da
tek bir INCOMING gönderi var. Bu, iade yaşanmadığının değil, iade sürecinin
SİSTEMDE İZLENMEDİĞİNİN ölçüsüdür -- telefonla halledilen bir iade hiçbir
yere düşmez. Panel bu ayrımı açıkça yazar.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any


def _oku(sql: str, zaman: int = 25) -> list[dict]:
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=zaman, check=False)
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


def _ad(m: dict) -> str:
    """Görünen ad. Yoksa e-posta, o da yoksa kısaltılmış kimlik."""
    parca = " ".join(x for x in ((m.get("ad") or "").strip(),
                                 (m.get("soyad") or "").strip()) if x)
    if parca:
        return parca
    if m.get("eposta"):
        return str(m["eposta"])
    kimlik = str(m.get("buyer_id") or "")
    return (kimlik[:8] + "…") if kimlik else "bilinmiyor"


# ------------------------------------------------------------------ müşteri
def musteri_listesi(limit: int = 60) -> dict:
    """Müşteriler: kaç kere almış, ne kadar harcamış, en son ne zaman."""
    satirlar = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT w.buyer_id,"
        "        max(w.ham->'buyerInfo'->>'firstName') AS ad,"
        "        max(w.ham->'buyerInfo'->>'lastName')  AS soyad,"
        "        max(w.ham->'buyerInfo'->>'email')     AS eposta,"
        "        max(w.ham->'buyerInfo'->>'phone')     AS telefon,"
        "        count(*)::int AS siparis,"
        # 🔴 İptal edilen sipariş HARCAMA DEĞİLDİR. Hepsini toplasaydık
        # "en iyi müşteri" listesi iptal edenlerle dolardı.
        "        count(*) FILTER (WHERE w.odeme_durumu = 'PAID')::int AS odenen,"
        "        COALESCE(sum(w.toplam) FILTER (WHERE w.odeme_durumu = 'PAID'), 0)"
        "          ::numeric(14,2) AS harcama,"
        "        min(w.olusturma)::date AS ilk,"
        "        max(w.olusturma)::date AS son"
        "   FROM raw.wix_order w"
        "  WHERE w.buyer_id IS NOT NULL"
        "  GROUP BY w.buyer_id"
        f" ORDER BY 6 DESC, 8 DESC LIMIT {int(limit)}) x")
    for m in satirlar:
        m["gorunen_ad"] = _ad(m)
    tekrar = [m for m in satirlar if int(m.get("siparis") or 0) > 1]
    return {
        "musteriler": satirlar,
        "toplam_musteri": len(satirlar),
        "tekrar_eden": len(tekrar),
        "tekrar_orani": (round(100.0 * len(tekrar) / len(satirlar), 1)
                         if satirlar else None),
        "not": ("Harcama yalnız ÖDENMİŞ siparişleri sayar; iptal edilen "
                "sipariş harcama değildir. Kimlik Wix alıcı kaydıdır: "
                "kapıda ödeme ve telefon satışları bu listede YOKTUR."),
    }


def musteri_karti(buyer_id: str) -> dict:
    """Tek müşterinin tam geçmişi: siparişleri ve içindeki ürünler."""
    kimlik = (buyer_id or "").strip()
    if not kimlik:
        return {"hata": "müşteri kimliği verilmedi"}
    # 🔴 Kimlik SQL'e gömülmez; parametre olarak jsonb içinden geçirilir.
    yuk = json.dumps({"id": kimlik}, ensure_ascii=False).replace("'", "''")
    kosul = f"w.buyer_id = ('{yuk}'::jsonb->>'id')"

    kisi = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT w.buyer_id,"
        "        max(w.ham->'buyerInfo'->>'firstName') AS ad,"
        "        max(w.ham->'buyerInfo'->>'lastName')  AS soyad,"
        "        max(w.ham->'buyerInfo'->>'email')     AS eposta,"
        "        max(w.ham->'buyerInfo'->>'phone')     AS telefon"
        f"   FROM raw.wix_order w WHERE {kosul} GROUP BY w.buyer_id) x")
    if not kisi:
        return {"hata": "müşteri bulunamadı"}
    k = kisi[0]
    k["gorunen_ad"] = _ad(k)

    siparisler = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT w.siparis_id, w.siparis_no, w.olusturma::date AS gun,"
        "        w.odeme_durumu, w.teslimat_durumu, w.odeme_yontemi,"
        "        w.toplam::numeric(14,2) AS toplam,"
        "        (SELECT string_agg(k.urun_adi || ' ×' || k.adet::int, ', ')"
        "           FROM mart.siparis_kalem k WHERE k.siparis_id = w.siparis_id)"
        "          AS urunler,"
        "        (SELECT g.durum || COALESCE(' · ' || g.tasiyici, '')"
        "           FROM mart.gonderi g WHERE g.siparis_id = w.siparis_id"
        "          LIMIT 1) AS kargo"
        f"   FROM raw.wix_order w WHERE {kosul}"
        "  ORDER BY w.olusturma DESC) x")

    odenen = [s for s in siparisler if s.get("odeme_durumu") == "PAID"]
    return {
        "musteri": k,
        "siparisler": siparisler,
        "siparis_adedi": len(siparisler),
        "odenen_adet": len(odenen),
        "harcama": round(sum(float(s.get("toplam") or 0) for s in odenen), 2),
    }


# --------------------------------------------------------------------- iade
def iade_ozeti() -> dict:
    """İade, değişim ve iptal — ÜÇ AYRI KAYNAKTAN, karıştırılmadan.

    🔴 Üçü aynı şey değil ve toplanmaz:
      · Wix para iadesi  -> müşteriye para geri döndü
      · iptal sipariş    -> hiç ödenmedi, para dönmedi
      · gelen kargo      -> ürün fiziksel olarak geri geldi
    Bir iade her üçünde de görünebilir ya da hiçbirinde görünmeyebilir.
    """
    wix_iade = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT siparis_id, siparis_no, olusturma::date AS gun,"
        "        toplam::numeric(14,2) AS toplam,"
        "        jsonb_array_length(COALESCE(ham->'refunds','[]'::jsonb)) AS iade_adedi"
        "   FROM raw.wix_order"
        "  WHERE jsonb_array_length(COALESCE(ham->'refunds','[]'::jsonb)) > 0"
        "  ORDER BY olusturma DESC) x")

    iptal = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT w.siparis_id, w.siparis_no, w.olusturma::date AS gun,"
        "        w.toplam::numeric(14,2) AS toplam, w.odeme_durumu,"
        "        w.teslimat_durumu,"
        "        (SELECT string_agg(k.urun_adi, ', ')"
        "           FROM mart.siparis_kalem k WHERE k.siparis_id = w.siparis_id)"
        "          AS urunler"
        "   FROM raw.wix_order w"
        "  WHERE w.teslimat_durumu = 'CANCELED' OR w.odeme_durumu = 'NOT_PAID'"
        "  ORDER BY w.olusturma DESC) x")

    gelen_kargo = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT gonderi_id, olusturma::date AS gun, durum, tasiyici,"
        "        son_hareket, sehir,"
        "        array_to_string(urun_adlari, ', ') AS urun"
        "   FROM raw.bk_shipment WHERE yon = 'INCOMING'"
        "  ORDER BY olusturma DESC) x")

    # Elle beyan edilen iade/değişim (insan beyanı, SATIŞLAR panelinden)
    beyan = _oku(
        "SELECT row_to_json(x) FROM ("
        " SELECT not_id, siparis_ref, tur, alici, urun_adi, adet,"
        "        elle_fiyat, not_metni, giren, girildi::date AS gun"
        "   FROM core.gonderi_notu WHERE tur IN ('IADE', 'DEGISIM')"
        "  ORDER BY girildi DESC) x")

    toplam = len(wix_iade) + len(gelen_kargo) + len(beyan)
    return {
        "wix_para_iadesi": wix_iade,
        "iptal_siparis": iptal,
        "gelen_kargo": gelen_kargo,
        "elle_beyan": beyan,
        "kayitli_iade_toplami": toplam,
        # 🔴 Bu cümle bilerek "iade yok" demiyor.
        "not": ("Kayıtlı iade sayısı düşükse bu, iade yaşanmadığı anlamına "
                "gelmez: telefonla halledilen bir iade hiçbir sisteme "
                "düşmez. Yaşanan iadeleri SATIŞLAR panelinden 'iade' ya da "
                "'değişim' olarak beyan ederseniz burada görünür."),
    }
