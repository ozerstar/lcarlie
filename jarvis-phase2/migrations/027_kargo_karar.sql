-- 027 — KARGO KARARI: barkod üretimi PARA HARCAR, kaydı tutulur (21.09.2026)
--
-- Sahip: *"taşıyıcıyı seçebilmek, karşı ödemeli mi biz mi ödemeli gibi
-- bilgileri seçebilme gibi panel istiyorum. burası bizim merkez üssümüz."*
--
-- NEDEN AYRI BİR TABLO
-- BasitKargo ucunun kendi açıklaması `generate_shipment_code` için birebir
-- şunu diyor: *"THIS CHARGES THE FIRM'S BALANCE and calls the carrier."*
-- Yani bu, panelde tıklanan diğer düğmelere benzemez: geri alınamaz ve
-- şirketin parasını harcar. `jarvis/basitkargo.py` bu aracı `PARALI`
-- kümesinde tutar ve `onayli=True` verilmeden çağırmayı reddeder.
--
-- 🔴 BU TABLO O BAYRAĞIN KARŞILIĞIDIR. Bayrağı veren her çağrı, çağrıdan
-- ÖNCE buraya bir satır yazmak zorundadır. Satır yazılmadan para harcanmaz;
-- para harcandıysa satırı vardır. Kaydın sonradan yazılması yeterli olmazdı:
-- çağrı patlarsa hiç iz kalmaz, oysa para gitmiş olabilir.
--
-- 🔴 İNSAN BEYANIDIR -> human_approver yazar, ai_writer YAZAMAZ.
-- Sebep `core.gonderi_notu` ile aynı ve burada daha ağır: makinenin
-- "bunu insan onayladı" satırını kendisinin yazabilmesi, para gatesini
-- tamamen anlamsız kılardı.
--
-- ÇİFT HARCAMA KORUMASI
-- Kısmî tekil dizin, aynı siparişin İSTENDİ veya ONAYLANDI durumunda ikinci
-- kez istenmesini veritabanı seviyesinde engeller. Panelde çift tıklama,
-- iki sekme, yenilenen sayfa -- üçü de aynı yere çıkar ve ikincisi yazamaz.
-- HATA satırı engellemez, çünkü başarısız denemeden sonra tekrar denemek
-- meşrudur; ama tekrar denemeden önce çağıran taraf barkodun gerçekten
-- oluşmadığını doğrulamak ZORUNDADIR (uç, parayı düşürüp yine de hata
-- döndürmüş olabilir).
--
-- Geri alma: migrations/rollback/027_kargo_karar_ROLLBACK.sql

BEGIN;

CREATE TABLE IF NOT EXISTS core.kargo_karar (
    karar_id           bigserial PRIMARY KEY,
    siparis_id         text        NOT NULL,   -- BasitKargo orderId
    tasiyici           text        NOT NULL,   -- handlerCode: ARAS, MNG, …
    -- Operatörün ONAY ANINDA GÖRDÜĞÜ ücret. Sonradan uçtan sorulan fiyat
    -- değil: kararın neye bakılarak verildiği.
    gosterilen_ucret   numeric,
    karsi_odemeli      boolean     NOT NULL DEFAULT false,
    karsi_odeme_tutari numeric,
    karar              text        NOT NULL,
    barkod             text,                   -- oluşan takip kodu
    hata               text,
    veren              text        NOT NULL,   -- panel oturumu
    verildi            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT kargo_karar_durum CHECK (karar IN ('ISTENDI', 'ONAYLANDI', 'HATA')),
    CONSTRAINT kargo_karar_ucret CHECK (gosterilen_ucret IS NULL OR gosterilen_ucret >= 0),
    -- Karşı ödemeli ise tutar zorunlu: kapıda ne tahsil edileceği belirsiz
    -- bir gönderi, kuryenin yanlış para toplaması demektir.
    CONSTRAINT kargo_karar_kapida CHECK (
        NOT karsi_odemeli OR (karsi_odeme_tutari IS NOT NULL AND karsi_odeme_tutari > 0))
);

COMMENT ON TABLE core.kargo_karar IS
 'Barkod üretimi (para harcayan çağrı) için insan onayının kaydı. '
 'Çağrıdan ÖNCE yazılır; satırı olmayan çağrı yapılmaz.';

CREATE UNIQUE INDEX IF NOT EXISTS kargo_karar_tek_acik
    ON core.kargo_karar (siparis_id)
 WHERE karar IN ('ISTENDI', 'ONAYLANDI');

CREATE INDEX IF NOT EXISTS kargo_karar_zaman ON core.kargo_karar (verildi DESC);

-- Panel görünümü: ham tabloyu değil bunu okur.
CREATE OR REPLACE VIEW mart.kargo_karar_ozet AS
SELECT karar_id, siparis_id, tasiyici, gosterilen_ucret,
       karsi_odemeli, karsi_odeme_tutari, karar, barkod, hata, veren, verildi
  FROM core.kargo_karar
 ORDER BY verildi DESC;

GRANT SELECT ON core.kargo_karar, mart.kargo_karar_ozet TO ai_reader;
-- 🔴 ai_writer'a YAZMA VERİLMEZ.
GRANT SELECT, INSERT, UPDATE ON core.kargo_karar TO human_approver;
GRANT USAGE ON SEQUENCE core.kargo_karar_karar_id_seq TO human_approver;

COMMIT;
