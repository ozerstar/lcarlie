-- 021 — Satış diyaloğu öğrenme döngüsü: yaklaşım sürümleri ve sonuç ölçümü
--
-- SORUN
-- `jarvis/satis_dialog.py` cevabı üretiyor ama üslubu (`yaklasim`) koda
-- gömülü sabit bir metin. Sahip talebi (20.09.2026): *"müşteri geri
-- dönüşlerine göre kendini geliştirecek… 10 kişiye cevaplamış ve 2. mesaj
-- gelmemişse cevaplama tarzını değiştirecek."* Bunun için iki şey lazım:
-- üslubun SÜRÜMLENEBİLİR veri olması, ve her cevabın SONUCUNUN ölçülmesi.
--
-- NE ÖLÇÜLÜYOR
-- Tek ölçülebilir sinyal: cevaptan sonra müşteri tekrar yazdı mı.
-- `lcarlie.mesaj` üzerinden hesaplanabiliyor ve ölçüldü (20.09.2026):
-- 1.067 işletme mesajının 637'sine müşteri geri yazmış = %59,7.
--
-- 🔴 NE ÖLÇÜLMÜYOR -- ve öyle olduğu SÖYLENİYOR
-- "Satış oldu mu" burada BİLİNMİYOR. Ödemelerin %43'ünde otorite çevrim
-- dışı (bkz. CR-002.5) ve `konusma.sonuc` 274 kaydın 269'unda "bilinmiyor".
-- Bu yüzden `sonuc` alanı UNKNOWN başlar ve UNKNOWN ≠ SATILMADI. Geri
-- dönüş gelmemesi de satılmadığın KANITI değildir: müşteri siteden sessizce
-- sipariş vermiş olabilir. Ölçtüğümüz şey KONUŞMANIN DEVAMI, satış değil.
--
-- 🔴 NEDEN OTOMATİK UYGULAMA YOK
-- Yeni yaklaşım sürümü `TASLAK` doğar. `ONAYLI`ya insan taşır. Kohort
-- eşiği bir DEĞİŞİKLİK ÖNERİR, "işe yaradı" demez: 10 kişilik örneklem
-- küçüktür ve bu projede küçük örneklemden sonuç çıkarıp yanılmıştık
-- (GROWTH-004/005, `SMALL_SAMPLE` kuralı).

\set ON_ERROR_STOP on
BEGIN;

-- ---------------------------------------------------------------- yaklaşım
CREATE TABLE IF NOT EXISTS lcarlie.satis_yaklasim (
  id            bigserial PRIMARY KEY,
  surum         integer     NOT NULL,
  urun          text,                       -- NULL = tüm ürünler
  soru_tipi     text,                       -- NULL = tüm soru tipleri
  yonerge       text        NOT NULL,
  gerekce       text        NOT NULL,       -- NEDEN bu sürüm önerildi
  durum         text        NOT NULL DEFAULT 'TASLAK'
                CHECK (durum IN ('TASLAK','ONAYLI','EMEKLI','REDDEDILDI')),
  olusturan     text        NOT NULL,       -- 'kreatif_ekip' | operatör adı
  onaylayan     text,
  onay_zamani   timestamptz,
  olusturma     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT satis_yaklasim_surum_benzersiz UNIQUE (surum, urun, soru_tipi)
);

-- Aynı (ürün, soru tipi) için AYNI ANDA tek onaylı sürüm olabilir.
-- Yoksa hangi cevabın hangi üslupla gittiği belirsizleşir ve kohort
-- ölçümü anlamını yitirir.
CREATE UNIQUE INDEX IF NOT EXISTS satis_yaklasim_tek_onayli
  ON lcarlie.satis_yaklasim (coalesce(urun,''), coalesce(soru_tipi,''))
  WHERE durum = 'ONAYLI';

COMMENT ON TABLE lcarlie.satis_yaklasim IS
  'Cevabın ÜSLUBU, sürümlü. Kodda sabit değil ki öğrenme döngüsü '
  'değiştirebilsin. TASLAK doğar, ONAYLI''ya insan taşır.';

-- ------------------------------------------------------------------ cevap
CREATE TABLE IF NOT EXISTS lcarlie.satis_cevap (
  id              bigserial PRIMARY KEY,
  konusma_id      bigint      REFERENCES lcarlie.konusma(id) ON DELETE CASCADE,
  tetik_mesaj_id  bigint      REFERENCES lcarlie.mesaj(id) ON DELETE SET NULL,
  yaklasim_id     bigint      REFERENCES lcarlie.satis_yaklasim(id),
  urun            text,
  soru_tipi       text        NOT NULL,
  metin           text        NOT NULL,
  mevzuat         text        NOT NULL,     -- TEMIZ | OLGU_EKSIK | ...
  model           text,
  gonderildi      boolean     NOT NULL DEFAULT false,
  gonderim_zamani timestamptz,
  -- Sonuç ölçümü. NULL = henüz bakılmadı; UNKNOWN = bakıldı, bilinmiyor.
  donus_zamani    timestamptz,              -- müşteri tekrar yazdıysa
  donus_sn        integer,
  sonuc           text        NOT NULL DEFAULT 'UNKNOWN'
                  CHECK (sonuc IN ('UNKNOWN','DONUS_VAR','DONUS_YOK','PENCERE_ACIK')),
  olusturma       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS satis_cevap_kohort
  ON lcarlie.satis_cevap (yaklasim_id, urun, soru_tipi)
  WHERE gonderildi;
CREATE INDEX IF NOT EXISTS satis_cevap_konusma
  ON lcarlie.satis_cevap (konusma_id);

COMMENT ON COLUMN lcarlie.satis_cevap.sonuc IS
  'DONUS_YOK, satılmadı DEMEK DEĞİLDİR: müşteri siteden sessizce sipariş '
  'vermiş olabilir. PENCERE_ACIK = cevabın üstünden yeterli süre geçmedi, '
  'henüz karar verilemez.';

-- ------------------------------------------------------------- kohort görünümü
-- Panelin ve öğrenme döngüsünün baktığı tek yer. Oran BURADA hesaplanır ki
-- iki ayrı yerde iki farklı sayı çıkmasın.
CREATE OR REPLACE VIEW mart.satis_kohort AS
SELECT
  c.yaklasim_id,
  y.surum                                        AS yaklasim_surum,
  y.durum                                        AS yaklasim_durum,
  coalesce(c.urun, '(ürün yok)')                 AS urun,
  c.soru_tipi,
  count(*)                                       AS gonderilen,
  count(*) FILTER (WHERE c.sonuc = 'DONUS_VAR')  AS donus_var,
  count(*) FILTER (WHERE c.sonuc = 'DONUS_YOK')  AS donus_yok,
  count(*) FILTER (WHERE c.sonuc = 'PENCERE_ACIK') AS pencere_acik,
  -- Oran YALNIZ karar verilmiş kayıtlardan hesaplanır; penceresi açık olan
  -- kayıt paydaya girerse oran olduğundan düşük görünür.
  CASE WHEN count(*) FILTER (WHERE c.sonuc IN ('DONUS_VAR','DONUS_YOK')) > 0
       THEN round(100.0 * count(*) FILTER (WHERE c.sonuc = 'DONUS_VAR')
                  / count(*) FILTER (WHERE c.sonuc IN ('DONUS_VAR','DONUS_YOK')), 1)
  END                                            AS donus_yuzde,
  -- 🔴 Küçük örneklemde oran gösterilir ama KARAR VERİLMEZ.
  CASE WHEN count(*) FILTER (WHERE c.sonuc IN ('DONUS_VAR','DONUS_YOK')) < 10
       THEN 'SMALL_SAMPLE' ELSE 'OLCULEBILIR' END AS olcum_durumu,
  min(c.gonderim_zamani)                         AS ilk_gonderim,
  max(c.gonderim_zamani)                         AS son_gonderim,
  round(avg(c.donus_sn) FILTER (WHERE c.donus_sn IS NOT NULL))::int AS ort_donus_sn
FROM lcarlie.satis_cevap c
LEFT JOIN lcarlie.satis_yaklasim y ON y.id = c.yaklasim_id
WHERE c.gonderildi
GROUP BY c.yaklasim_id, y.surum, y.durum, coalesce(c.urun, '(ürün yok)'), c.soru_tipi;

COMMENT ON VIEW mart.satis_kohort IS
  'Yaklaşım sürümü × ürün × soru tipi başına dönüş oranı. '
  'olcum_durumu=SMALL_SAMPLE iken oran OKUNUR ama karar verilmez.';

-- ------------------------------------------------------------------ yetki
GRANT USAGE ON SCHEMA lcarlie TO ai_reader;
GRANT SELECT ON lcarlie.satis_yaklasim, lcarlie.satis_cevap TO ai_reader;
GRANT SELECT ON mart.satis_kohort TO ai_reader;

-- Yazma ai_reader'a AÇILMIYOR. Cevap kaydını yazan taraf n8n/uygulama
-- kimliğidir; okuma tarafı yalnız okur. Sınır aynen duruyor.

-- --------------------------------------------------------- başlangıç sürümü
-- Kodda duran `VARSAYILAN_YAKLASIM` ile birebir aynı metin. Buraya
-- konuyor ki ilk cevaptan itibaren her kayıt bir sürüme bağlansın --
-- "sürümsüz cevap" diye bir şey olmasın.
INSERT INTO lcarlie.satis_yaklasim (surum, urun, soru_tipi, yonerge, gerekce,
                                    durum, olusturan, onaylayan, onay_zamani)
SELECT 1, NULL, NULL,
       'Sıcak ve doğal yaz, sohbet gibi. Soruyu cevapla, sonra tek bir adım öner.',
       'Başlangıç sürümü: ölçüm bununla başlar, kıyas tabanı budur.',
       'ONAYLI', 'kurulum', 'ozer', now()
WHERE NOT EXISTS (SELECT 1 FROM lcarlie.satis_yaklasim WHERE surum = 1);

COMMIT;
