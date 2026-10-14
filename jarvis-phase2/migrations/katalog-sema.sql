-- KATALOG: sunum notu ve ürün ilgisi
--
-- NEDEN VAR: saha elemanı eczanede ürünleri anlatıyor, karşı taraf soru
-- soruyor ve bir şeye ilgi gösteriyor. O bilgi bugün hiçbir yere
-- yazılmıyor; akşam unutuluyor.
--
-- 🔴 BU TABLO ÖLÇÜM HALKASININ EKSİK HALKASI. Bu gece ölçtüm: 18.824
-- hedef var, 0 ziyaret, 0 sipariş. Reklamda aynı körlük iki ay sürdü ve
-- harcamanın %53'ü satın alma yoluna hiç çıkmadı. Saha da "hangi ürün
-- hangi kanalda ilgi görüyor" sorusunu cevaplayamadan başlarsa, altı ay
-- sonra yine tahminle konuşuruz.
--
-- İLGİ ile SİPARİŞ ayrı: "ilgilendi" satış değildir. Ayrı tutulmazsa
-- ilgi sayısı satış sanılır ve boru hattı olduğundan dolu görünür.
--
-- NOT hedefsiz de yazılabilir (hedef_anahtari NULL): ürün hakkında genel
-- bir not -- "eczacılar fiyatı yüksek buluyor" gibi -- belirli bir
-- eczaneye ait değildir ve oraya yazılması yanlış olurdu.

BEGIN;

CREATE TABLE IF NOT EXISTS core.katalog_not (
  not_id         bigserial PRIMARY KEY,
  urun_slug      text NOT NULL,
  hedef_anahtari text,                 -- NULL: ürüne ait genel not
  ziyaret_id     bigint REFERENCES core.saha_ziyaret(ziyaret_id),
  ilgi           text,                 -- NULL | YOK | SORDU | ILGILENDI | NUMUNE | SIPARIS_SOZU
  not_metni      text,
  giren          text NOT NULL,
  girildi        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS katalog_not_urun_idx  ON core.katalog_not (urun_slug, girildi DESC);
CREATE INDEX IF NOT EXISTS katalog_not_hedef_idx ON core.katalog_not (hedef_anahtari, girildi DESC);

-- İzinli ilgi değerleri koda değil ŞEMAYA yazılır: panel ile veritabanı
-- ayrı listeler tutarsa biri diğerini sessizce kabul eder.
ALTER TABLE core.katalog_not DROP CONSTRAINT IF EXISTS katalog_not_ilgi_ck;
ALTER TABLE core.katalog_not ADD CONSTRAINT katalog_not_ilgi_ck
  CHECK (ilgi IS NULL OR ilgi IN
         ('YOK', 'SORDU', 'ILGILENDI', 'NUMUNE', 'SIPARIS_SOZU'));

-- Boş not + ilgisiz kayıt anlamsızdır; yazılmasına izin vermek, listeyi
-- okunamaz kılar.
ALTER TABLE core.katalog_not DROP CONSTRAINT IF EXISTS katalog_not_bos_ck;
ALTER TABLE core.katalog_not ADD CONSTRAINT katalog_not_bos_ck
  CHECK (ilgi IS NOT NULL OR coalesce(btrim(not_metni), '') <> '');

-- Bayi (toptan) fiyatı. KATALOGDA BOŞ GÖRÜNÜR ta ki sahip girene kadar --
-- uydurulmuş bir bayi fiyatı, sahada verilmiş yanlış bir sözdür.
CREATE TABLE IF NOT EXISTS core.urun_bayi_fiyat (
  urun_slug   text PRIMARY KEY,
  bayi_fiyat  numeric(12, 2) NOT NULL CHECK (bayi_fiyat > 0),
  para        text NOT NULL DEFAULT 'TRY',
  en_az_adet  integer,
  gecerli_bas date NOT NULL DEFAULT current_date,
  giren       text NOT NULL,
  girildi     timestamptz NOT NULL DEFAULT now()
);

-- Ürün başına son durum: kaç sunum, kaç ilgi, kaç sipariş sözü.
CREATE OR REPLACE VIEW mart.katalog_ilgi AS
SELECT n.urun_slug,
       count(*)                                        AS kayit,
       count(DISTINCT n.hedef_anahtari)                AS hedef,
       count(*) FILTER (WHERE n.ilgi IN ('ILGILENDI', 'NUMUNE', 'SIPARIS_SOZU'))
                                                       AS ilgili,
       count(*) FILTER (WHERE n.ilgi = 'SIPARIS_SOZU') AS siparis_sozu,
       count(*) FILTER (WHERE n.ilgi = 'YOK')          AS ilgisiz,
       max(n.girildi)                                  AS son_kayit
  FROM core.katalog_not n
 GROUP BY n.urun_slug;

COMMIT;
