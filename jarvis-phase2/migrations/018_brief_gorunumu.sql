-- 018 — mart.gunluk_brief: yönetici özeti okunabilir olsun
--
-- SORUN
-- lcarlie-executive-brief servisi her gün bir yönetici özeti üretiyor ve
-- core.ai_executive_brief + core.ic_mesaj'a yazıyor. Ama SOHBET OKUYAMIYOR:
--   has_table_privilege('ai_reader','core.ai_executive_brief','SELECT') = false
-- Üretiliyor, kimse görmüyor.
--
-- NEDEN ai_reader'A core YETKİSİ VERİLMİYOR
-- Mimarinin kuralı açık: ai_reader mart GÖRÜNÜMLERİNİ okur, core
-- TABLOLARINI okumaz. core yazma tarafı, mart okuma tarafı.
-- mart.sirket_gundemi de tam bu yüzden var (core.acik_soru'nun önünde).
-- Yetki vermek sınırı delmek olurdu; doğrusu aynı deseni izlemek.
--
-- NE AÇILIYOR, NE AÇILMIYOR
-- Yalnız BRIEF mesajları. core.ic_mesaj'da başka iç yazışmalar da var;
-- görünüm onları TAŞIMAZ -- yalnız ai_executive_brief'in işaret ettiği
-- mesajlar görünür. Genel bir "tüm iç mesajlar" penceresi açılmıyor.

\set ON_ERROR_STOP on
BEGIN;

CREATE OR REPLACE VIEW mart.gunluk_brief AS
SELECT
  b.brief_key,
  b.provider,
  b.model,
  b.context_hash,
  b.created_at,
  m.konu,
  m.icerik,
  m.kimden,
  m.kime,
  m.durum,
  now() - b.created_at AS yas
FROM core.ai_executive_brief b
LEFT JOIN core.ic_mesaj m ON m.mesaj_id = b.message_id
ORDER BY b.created_at DESC;

COMMENT ON VIEW mart.gunluk_brief IS
  'Gunluk yonetici ozeti. YALNIZ brief mesajlari -- core.ic_mesaj''daki '
  'diger ic yazismalar bu gorunumden GORUNMEZ. ai_reader core tablolarini '
  'okumaz; okuma tarafi mart''tir.';

GRANT SELECT ON mart.gunluk_brief TO ai_reader;

-- Doğrula: görünüm okunabilir, alttaki tablolar HÂLÂ kapalı.
DO $$
BEGIN
  IF NOT has_table_privilege('ai_reader','mart.gunluk_brief','SELECT') THEN
    RAISE EXCEPTION 'ai_reader gorunumu okuyamiyor -- grant islemedi';
  END IF;
  IF has_table_privilege('ai_reader','core.ai_executive_brief','SELECT') THEN
    RAISE EXCEPTION 'ai_reader ham brief tablosunu okuyabiliyor -- yalniz gorunum verilmeliydi';
  END IF;
  IF has_table_privilege('ai_reader','core.ic_mesaj','SELECT') THEN
    RAISE EXCEPTION 'ai_reader tum ic mesajlari okuyabiliyor -- sinir delinmis';
  END IF;
END $$;

COMMIT;
