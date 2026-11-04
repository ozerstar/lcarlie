-- =============================================================================
-- L'CARLIE - RAW KATMANI (dis sistemlerin HAM aynasi)
--
-- CR-004 · 16.09.2026
--
-- 🔴 RAW'DA YORUM YOK, DUZELTME YOK.
--    Kaynak ne dediyse o yazilir. Cikarilan kolonlar yalnizca INDEKS ve
--    KOLAYLIK icindir; otorite her zaman 'ham' jsonb kolonudur.
--    Bir cikarma kurali yanlis cikarsa ham veriden YENIDEN turetilir.
--
-- 🔴 OLCUM 1 EKIM 2026'DA BASLAR (sahip karari).
--    Ama raw TUM gecmisi tutar - silmek veri kaybidir, hesaplamamak yeterli.
--    Donem ayrimi 'mart' katmaninda yapilir, burada DEGIL.
--
-- Idempotent: tekrar calistirilabilir.
-- =============================================================================

BEGIN;

-- Olcum baslangici - TEK yerden okunur, betiklere elle yazilmaz.
CREATE TABLE IF NOT EXISTS core.ayar (
  anahtar text PRIMARY KEY,
  deger   text NOT NULL,
  aciklama text,
  guncelleme timestamptz NOT NULL DEFAULT now()
);
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
('olcum_baslangici','2026-10-01T00:00:00+03',
 'Sahip karari 16.09.2026: ticari olcum bu andan itibaren baslar. Oncesi raw''da durur, mart''a girmez.')
ON CONFLICT (anahtar) DO NOTHING;

-- =============================================================================
-- WIX SIPARIS
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw.wix_order (
  siparis_id       text PRIMARY KEY,          -- Wix order.id (UUID) = birlestirme anahtari
  siparis_no       bigint,
  buyer_id         text,
  buyer_tipi       text,                      -- MEMBER | CONTACT
  olusturma        timestamptz,
  guncelleme       timestamptz,
  odeme_durumu     text,                      -- PAID | NOT_PAID | ...
  odeme_yontemi    text,                      -- PayTR | Cevrim Disi Odemeler
  teslimat_durumu  text,                      -- FULFILLED | NOT_FULFILLED | CANCELED
  -- 🔴 'toplam' KDV DAHILDIR (totals.total). Marj hesabinda KULLANILMAZ.
  --    Olculdu 16.09.2026: siparis 10037 -> subtotal 1000 + tax 200 = total 1200.
  --    37/37 siparişte totals.tax dolu, oran %20.
  --    KDV bizim paramiz DEGIL, devlete gider. KDV dahil ciradan maliyet
  --    cikarilirsa marj KDV kadar SISIK cikar: 1200-400=800 gorunur,
  --    gercegi 1000-400=600. Yani birim marj %33 fazla okunur.
  toplam           numeric(14,2),
  -- 🔴 KDV HARIC NET CIRO = toplam - kdv.  'ara_toplam' DEGIL!
  --    totals.subtotal INDIRIM ONCESI liste tutaridir, KDV matrahi degildir:
  --    37 siparişte subtotal toplami 83.849,09 iken toplam 82.073,50 - yani
  --    subtotal toplamdan BUYUK cikar (indirim henuz dusulmemis).
  --    Olculdu: kdv / (toplam - kdv) = 0,2000 -> 37/37 siparişte TAM %20.
  --    Dogru net ciro: 82.073,50 - 13.678,91 = 68.394,59.
  ara_toplam       numeric(14,2),             -- totals.subtotal - INDIRIM ONCESI liste, matrah DEGIL
  kdv              numeric(14,2),             -- totals.tax
  kargo_bedeli     numeric(14,2),             -- totals.shipping (musteriden alinan)
  siparis_indirimi numeric(14,2),             -- totals.discount (siparis seviyesi)
  para_birimi      text,
  kanal            text,
  arsivlendi       boolean,
  giren_id         text,                      -- enteredBy.id  (elle giris tespiti)
  giren_tipi       text,                      -- enteredBy.identityType
  ic_siparis       boolean,                   -- isInternalOrderCreate
  ham              jsonb NOT NULL,            -- 🔴 OTORITE BU
  cekim_at         timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS giren_id   text;
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS giren_tipi text;
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS ic_siparis boolean;
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS ara_toplam       numeric(14,2);
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS kdv              numeric(14,2);
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS kargo_bedeli     numeric(14,2);
ALTER TABLE raw.wix_order ADD COLUMN IF NOT EXISTS siparis_indirimi numeric(14,2);
CREATE INDEX IF NOT EXISTS wix_order_olusturma_idx ON raw.wix_order (olusturma);
CREATE INDEX IF NOT EXISTS wix_order_buyer_idx     ON raw.wix_order (buyer_id);

COMMENT ON COLUMN raw.wix_order.ham IS 'Kaynagin dondurdugu JSON, degistirilmeden. Otorite budur.';

CREATE TABLE IF NOT EXISTS raw.wix_order_item (
  siparis_id  text NOT NULL REFERENCES raw.wix_order(siparis_id) ON DELETE CASCADE,
  sira        int  NOT NULL,
  -- 🔴 URUN ESLESTIRMESI AD ILE YAPILAMAZ.  Olculdu (16.09.2026): 22 tekil
  --    urun 26 farkli adla gecmis. Ayni urun "VIREON FOR MEN (Erkek Bakim
  --    Kremi)" ve "VIREON FOR MEN · Erkek Bakim Kremi" diye iki ad tasiyor,
  --    ayrica "HAIR NOURIHER" yazim hatasi var. Ad ile baglanan maliyet
  --    4 uruna YANLIS baglanirdi. Otorite: urun_id.
  urun_id     text,
  urun_adi    text,
  sku         text,
  adet        numeric(12,3),
  birim_fiyat numeric(14,2),
  toplam      numeric(14,2),   -- lineItems[].totalPrice - INDIRIM ONCESI
  -- 🔴 INDIRIM AYRI KOLON (16.09.2026'da bulunan hata).
  --    Wix'te lineItems[].totalPrice indirimden ONCEKI tutardir; kalemin
  --    kendi 'discount' alani DUZ BIR METINDIR ("1680.00"), alt alani yok.
  --    Bu alan okunmadigi icin kalem cirosu toplami 97.528,00 cikiyordu -
  --    oysa siparis toplami 82.073,50. %18,8 SISKIN. Marj, kapsama orani
  --    ve urun karliligi hep bu sisik sayidan turuyordu.
  --    Dogrulandi: (totalPrice - discount) toplami 37/37 siparyste
  --    siparis toplamiyla BIREBIR tutuyor.
  indirim     numeric(14,2) NOT NULL DEFAULT 0,
  -- Net ciro TURETILMIS kolondur: hesaplama tek yerde durur, bir daha
  -- unutulamaz. Sorgu yazan kisinin cikarma yapmasi gerekmez.
  net_toplam  numeric(14,2) GENERATED ALWAYS AS (toplam - indirim) STORED,
  ham         jsonb NOT NULL,
  PRIMARY KEY (siparis_id, sira)
);
ALTER TABLE raw.wix_order_item ADD COLUMN IF NOT EXISTS urun_id text;
ALTER TABLE raw.wix_order_item ADD COLUMN IF NOT EXISTS indirim numeric(14,2) NOT NULL DEFAULT 0;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema='raw' AND table_name='wix_order_item'
                    AND column_name='net_toplam') THEN
    ALTER TABLE raw.wix_order_item
      ADD COLUMN net_toplam numeric(14,2) GENERATED ALWAYS AS (toplam - indirim) STORED;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS wix_item_urun_idx ON raw.wix_order_item (urun_id);

COMMENT ON COLUMN raw.wix_order_item.toplam IS
  'lineItems[].totalPrice - INDIRIM ONCESI. Ciro icin net_toplam kullan.';
COMMENT ON COLUMN raw.wix_order_item.net_toplam IS
  'toplam - indirim. Kalem cirosu BUDUR. Toplami siparis toplamiyla birebir tutar.';

-- =============================================================================
-- BASITKARGO GONDERI
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw.bk_shipment (
  gonderi_id      text PRIMARY KEY,           -- BasitKargo order.id
  barkod          text,
  foreign_code    text,                       -- 🔴 Wix siparis UUID'si (varsa)
  icerik_kodu     text,                       -- content.code (entegrasyonda foreignCode ile ayni)
  ek_bilgi        text,                       -- content.name - numune isaretlemesi buraya (BOS: 0/49)
  yon             text,                       -- 🔴 OUTGOING | INCOMING (INCOMING = iade, SATIS DEGIL)
  gonderi_no      text,                       -- orderNumber
  durum           text,                       -- NEW | READY_TO_SHIP | SHIPPED | COMPLETED
  tasiyici        text,
  olusturma       timestamptz,
  guncelleme      timestamptz,
  kargoya_verilis timestamptz,
  teslim          timestamptz,
  son_hareket     text,
  desi            numeric(10,2),
  kargo_ucreti    numeric(14,2),              -- priceInfo.shipmentFee
  toplam_maliyet  numeric(14,2),              -- priceInfo.totalCost
  cod_var         boolean NOT NULL DEFAULT false,
  cod_tutar       numeric(14,2),
  cod_durum       text,                       -- COLLECTION_PENDING | TRANSFERRED
  siparis_tutari  numeric(14,2),              -- orderTotal (elle girilenlerde cogunlukla BOS)
  urun_adlari     text[],                     -- content.items[].name
  sehir           text,                       -- 🔴 yalnizca sehir - ad/telefon/adres RAW'A ALINMAZ
  ilce            text,
  ham             jsonb NOT NULL,
  cekim_at        timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE raw.bk_shipment ADD COLUMN IF NOT EXISTS icerik_kodu text;
ALTER TABLE raw.bk_shipment ADD COLUMN IF NOT EXISTS yon         text;
ALTER TABLE raw.bk_shipment ADD COLUMN IF NOT EXISTS gonderi_no  text;
ALTER TABLE raw.bk_shipment ADD COLUMN IF NOT EXISTS ilce        text;
CREATE INDEX IF NOT EXISTS bk_olusturma_idx    ON raw.bk_shipment (olusturma);
CREATE INDEX IF NOT EXISTS bk_foreign_idx      ON raw.bk_shipment (foreign_code) WHERE foreign_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS bk_cod_idx          ON raw.bk_shipment (cod_durum) WHERE cod_var;

-- 🔴 PII KARARI: BasitKargo gonderisinde alici ADI, TELEFONU ve ADRESI var.
--    Bunlar ticari olcum icin GEREKMIYOR - yalnizca sehir tutuluyor (bolgesel
--    dagilim icin). 'ham' jsonb'de de alici bloku TEMIZLENEREK saklanir.
--    Musteri kimligi Wix tarafindan gelir; kargo tarafinda PII tasimaya
--    gerek yok. (CR-002.5 "raw PII erisimi minimum tutulur" kurali.)
-- 🔴 ZAMAN DILIMI: BasitKargo tarihleri OFFSET'SIZ gelir ("2026-09-15T01:19:47").
--    +03 (Turkiye) varsayilir. Bu varsayim yuklemeden sonra foreignCode ile bagli
--    9 gonderide "BK olusturma >= Wix siparis tarihi" testiyle DOGRULANIR.
--    Test gecmezse varsayim yanlistir ve cikarma fonksiyonu duzeltilip ham veriden
--    yeniden turetilir (raw.bk_shipment_yaz(ham)).
COMMENT ON TABLE raw.bk_shipment IS
  'BasitKargo gonderi aynasi. Alici PII (ad/telefon/adres) BILEREK ALINMAZ - yalniz sehir/ilce. Tarihler +03 varsayimiyla cozulur.';

-- =============================================================================
-- YUKLEME GUNLUGU  (0 satir = SUCCESS DEGIL)
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw.yukleme_log (
  id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  kaynak      text NOT NULL,
  durum       text NOT NULL CHECK (durum IN ('SUCCESS','NO_DATA','PARTIAL','FAILED')),
  okunan      int,
  yazilan     int,
  guncellenen int,
  mesaj       text,
  baslangic   timestamptz NOT NULL,
  bitis       timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE raw.yukleme_log IS
  'Her ETL calismasi. 🔴 Kaynaga ERISILEMEDI=FAILED, erisildi-kayit yok=NO_DATA. Ikisi ayri.';

COMMIT;
