-- =====================================================================
-- 028  İÇİNDEKİLER (INCI) AMBARA ALINIYOR
--
-- 🔴 NEDEN VAR (27.09.2026 ölçümü). Gelen kutusunda 19 gündür bekleyen
--    soruların tamamı aynıydı: **"İçindekiler nelerdir?"**. Cevaplanamadı,
--    çünkü `core`, `mart`, `raw`, `lcarlie` şemalarında
--    `icindekiler|inci|ingredient|formul` diye TEK BİR SÜTUN YOKTU.
--
--    Veri aslında vardı: `jarvis-phase2/varliklar/kutu-gercegi/*.json`
--    içinde, ürün başına "kutu gerçeği" olarak. Ama ambara hiç
--    bağlanmamıştı; yani ajan bu soruya ancak UYDURARAK cevap verebilirdi.
--    Bu projede bir kez yaşandı (model içindekileri uydurdu) ve
--    kozmetikte mevzuat riskidir.
--
-- 🔴 EKSİK ÜRÜN GİZLENMEZ. 39 üründen 33'ünde INCI var, 6'sında YOK
--    (hydravie, kinesis+, liftella, lipvora, minisooth, optywave).
--    Tablo bunları SATIR OLARAK tutar, `inci IS NULL` ile. Boş satır
--    yazmak yerine ürünü hiç yazmamak, "sorulmadı" ile "yok"u
--    karıştırırdı -- bu projenin tekrar eden kök hatası.
--
-- ⚠️ BU VERİ KUTUDAN OKUNMUŞ BEYANDIR, laboratuvar analizi değildir.
--    Kaynak ve kaynak türü her satırda saklanır.
--
-- Geri alma: migrations/rollback/028_urun_inci_ROLLBACK.sql
-- =====================================================================
\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS core.urun_inci (
    urun_anahtari text PRIMARY KEY,
    urun_adi      text,
    -- 🔴 NULL = kutu gerçeğinde INCI bölümü BOŞ. Bilgi yok demektir,
    --    "içindekiler yok" demek DEĞİL.
    inci          text,
    kaynak        text,          -- hangi belgeden
    kaynak_tur    text,          -- belge türü (ambalaj, ürün dosyası…)
    guncelleme    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT urun_inci_bos_metin CHECK (inci IS NULL OR length(btrim(inci)) > 0)
);

COMMENT ON TABLE core.urun_inci IS
 'Ürün içindekiler (INCI) listesi. Kaynak: varliklar/kutu-gercegi/*.json. '
 'KUTUDAN OKUNMUŞ BEYANDIR, laboratuvar analizi değildir. inci IS NULL '
 'olan ürünlerde bilgi YOKTUR; ajan bu durumda cevap üretmemeli, insana '
 'aktarmalıdır.';

COMMENT ON COLUMN core.urun_inci.inci IS
 'NULL = kutu gerçeğinde bölüm boş. Boş metin YASAK (CHECK).';

-- ------------------------------------------------------------ kapsama
-- Ajanın "elimde var mı" sorusunu TEK SORGUDA cevaplaması için.
CREATE OR REPLACE VIEW mart.urun_inci_durum AS
SELECT urun_anahtari,
       urun_adi,
       (inci IS NOT NULL)                         AS bilgi_var,
       CASE WHEN inci IS NULL THEN NULL
            ELSE length(inci) END                 AS uzunluk,
       kaynak,
       kaynak_tur,
       guncelleme
  FROM core.urun_inci;

COMMENT ON VIEW mart.urun_inci_durum IS
 'Hangi üründe içindekiler bilgisi VAR, hangisinde YOK. bilgi_var=false '
 'olan üründe ajan içindekiler sorusuna cevap ÜRETMEMELİ.';

-- ---------------------------------------------------------- yetkiler
GRANT SELECT ON core.urun_inci, mart.urun_inci_durum TO ai_reader;
-- 🔴 ai_writer'a YAZMA VERİLMEZ: bu veri kutudan okunur, üretilmez.
--    Yükleyici human_approver olarak yazar.
GRANT SELECT, INSERT, UPDATE, DELETE ON core.urun_inci TO human_approver;

COMMIT;
