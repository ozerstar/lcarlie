-- =============================================================================
-- L'CARLIE - KARAR ONCELIGI + PAZAR ARASTIRMASI  (CR-016)
--
-- 🔴 EN FAZLA 5 ONERI.  CR-014 brief'i 29 bulgu uretiyordu; bilgi coplugu
--    karar kolaylastirmaz, zorlastirir. Bu dosya bulgulari ONCELIKLENDIRIR
--    ve yalniz ilk 5'i karar onerisi yapar.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- KARAR ONCELIGI  -  deterministik puanlama
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.karar_oncelik CASCADE;
CREATE VIEW mart.karar_oncelik AS
WITH b AS (
  -- 🔴 Iki tabloda da kanit_sinifi var; takma ad ZORUNLU yoksa ambiguous.
  SELECT bb.*, ka.kanit_sinifi AS anlik_kalitesi
    FROM core.buyume_bulgu bb
    JOIN core.kanit_anlik ka USING (anlik_id)
   WHERE bb.anlik_id = (SELECT max(anlik_id) FROM core.kanit_anlik)
     AND bb.modul IN ('URUN','META','KREATIF')
     AND coalesce(bb.sinif,'') <> 'INSUFFICIENT_DATA'
)
SELECT b.bulgu_id, b.modul, b.sinif, b.baslik, b.kanit, b.beklenen_etki,
       b.risk, b.yanlislama, b.anlik_kalitesi AS kanit_sinifi,
       -- 🔴 PUANLAMA DETERMINISTIK VE GEREKCELI:
       --    + nakit etkisi dogrudan olan (META/CRITICAL) en yukarida
       --    + ucuz ve geri alinabilir olan (KREATIF testi) sonra
       --    + urun onceligi en altta cunku huni zarardayken olcek anlamsiz
       (CASE WHEN b.modul='META'    AND b.sinif='CRITICAL'          THEN 100 ELSE 0 END
      + CASE WHEN b.modul='KREATIF'                                 THEN  60 ELSE 0 END
      + CASE WHEN b.modul='URUN'    AND b.sinif='FIX_FUNNEL_FIRST'  THEN  40 ELSE 0 END
      + CASE WHEN b.anlik_kalitesi='HIGH' THEN 10 WHEN b.anlik_kalitesi='MEDIUM' THEN 5 ELSE 0 END
       ) AS puan,
       CASE WHEN b.modul='META' AND b.sinif='CRITICAL'
              THEN 'nakit cikisini dogrudan durdurur - geri alinabilir'
            WHEN b.modul='KREATIF'
              THEN 'ucuz test, musteri sorusundan turemis, geri alinabilir'
            ELSE 'huni duzelmeden olcek anlamsiz - beklemeli' END AS oncelik_gerekcesi
  FROM b
 ORDER BY puan DESC, b.bulgu_id;

COMMENT ON VIEW mart.karar_oncelik IS
  'Bulgulari deterministik puanla siralar. Brief yalniz ilk 5''ini oneri yapar.';

-- ---------------------------------------------------------------------------
-- SUPERSEDE  -  eski adaylar SILINMEZ, iliskiyle yonetilir
-- ---------------------------------------------------------------------------
-- 🔴 SILME YOK.  Eski karar adayi gecersiz hale geldiyse durumu degisir ve
--    hangi kararin onun yerine gectigi YAZILIR. Silmek, "bu oneriyi bir
--    zamanlar yaptik" bilgisini yok etmek olurdu - Decision Memory'nin
--    varlik sebebine aykiri.
ALTER TABLE core.karar ADD COLUMN IF NOT EXISTS ustunu_alan bigint REFERENCES core.karar(karar_id);
ALTER TABLE core.karar ADD COLUMN IF NOT EXISTS gecersizlik_nedeni text;

CREATE OR REPLACE FUNCTION core.karar_ustunu_al(p_eski bigint, p_yeni bigint, p_neden text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT durum FROM core.karar WHERE karar_id=p_eski) NOT IN ('PROPOSED','DEFERRED') THEN
    RAISE EXCEPTION 'Karar #% PROPOSED/DEFERRED degil - ustu alinamaz', p_eski;
  END IF;
  UPDATE core.karar
     SET ustunu_alan = p_yeni, gecersizlik_nedeni = p_neden, durum = 'CANCELLED'
   WHERE karar_id = p_eski;
END $$;

COMMENT ON FUNCTION core.karar_ustunu_al(bigint,bigint,text) IS
  'Eski adayi CANCELLED yapar ve yerine geceni isaret eder. SILMEZ.';

-- ---------------------------------------------------------------------------
-- PAZAR ARASTIRMASI  -  gercek kaynak + tarih + ayrim
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.pazar_arastirma CASCADE;
CREATE VIEW mart.pazar_arastirma AS
SELECT * FROM (VALUES
  ('KATEGORI_FIYAT_TABANI', 'FACT',
   'Komsu kategori "genital bolge temizleyici (erkek)" 45,00 TL''den basliyor, 59 urun listeleniyor',
   'cimri.com fiyat karsilastirma', '16.09.2026',
   'Bu kategori VIREON ile AYNI DEGIL (temizleyici vs bakim kremi) - dogrudan rakip sayilamaz'),
  ('FIYAT_KONUMU', 'INTERPRETATION',
   'VIREON 2.400 TL (indirimli 1.200) - komsu kategorinin taban fiyatinin 26-53 kati',
   'ic veri + cimri.com', '16.09.2026',
   'Fark, urunun farkli bir kategoride konumlandigini gosterir; ama musteri karsilastirmayi YAPIYOR olabilir'),
  ('FIYAT_ITIRAZI_HIPOTEZI', 'HYPOTHESIS',
   'Konusmalarin %55''i fiyat soruyor; fiyat itirazinin kaynagi komsu kategoriyle karsilastirma olabilir',
   'mart.soru_konu (143/259) + kategori taban fiyati', '16.09.2026',
   'TEST EDILMEDI. Dogrulamak icin musteriye "neyle karsilastirdiniz" sorulmali'),
  ('RAKIP_IZLEME', 'NOT_CONNECTED',
   'Yapisal rakip reklam/fiyat izleme kaynagi bagli degil - tekil arama yapildi, surekli akis YOK',
   'MANUAL_RESEARCH_REQUIRED', '16.09.2026',
   'Tek seferlik arama trend gostermez; rakip kreatifi/teklifi izlenemiyor'),
  ('ARAMA_TALEBI', 'NOT_CONNECTED',
   'Arama hacmi / SEO veri kaynagi bagli degil',
   'MANUAL_RESEARCH_REQUIRED', '16.09.2026',
   'Kategori talebinin buyuyup buyumedigi BILINMIYOR')
) AS t(kod, seviye, bulgu, kaynak, tarih, yorum);

COMMENT ON VIEW mart.pazar_arastirma IS
  'Pazar/rakip bulgulari. FACT/INTERPRETATION/HYPOTHESIS/NOT_CONNECTED AYRI. '
  'Kaynak ve tarih her satirda zorunlu. Uydurma veri YOK.';

COMMIT;
