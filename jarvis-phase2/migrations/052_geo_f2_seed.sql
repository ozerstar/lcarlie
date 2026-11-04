-- SUNACNEA web search starter set (tr/TR). Agent-drafted neutral prompts.
BEGIN;

INSERT INTO core.geo_brand (canonical_name, bizim_mi)
VALUES ('L''CARLIÉ', true)
ON CONFLICT DO NOTHING;

INSERT INTO core.geo_alias
  (canonical_brand_id, alias, normalized_alias, alias_type, language)
SELECT brand_id, 'L''CARLIÉ', 'lcarlie', 'OFFICIAL', 'tr'
FROM core.geo_brand WHERE canonical_name = 'L''CARLIÉ'
ON CONFLICT DO NOTHING;

INSERT INTO core.geo_query
  (sorgu_metni, language, country, niyet, kume_anahtari, urun,
   kaynak, oncelik, set_surum)
VALUES
  ('L''CARLIÉ resmi sitesi', 'tr', 'TR', 'NAVIGATIONAL', 'sunacnea-v1', NULL, 'AGENT_DRAFT', 1, 'sunacnea-tr-v1'),
  ('L''CARLIÉ SUNACNEA', 'tr', 'TR', 'PRODUCT', 'sunacnea-v1', 'SUNACNEA', 'AGENT_DRAFT', 1, 'sunacnea-tr-v1'),
  ('SUNACNEA ürün bilgisi', 'tr', 'TR', 'PRODUCT', 'sunacnea-v1', 'SUNACNEA', 'AGENT_DRAFT', 2, 'sunacnea-tr-v1'),
  ('SUNACNEA içerik listesi', 'tr', 'TR', 'INGREDIENTS', 'sunacnea-v1', 'SUNACNEA', 'AGENT_DRAFT', 2, 'sunacnea-tr-v1'),
  ('SUNACNEA nasıl kullanılır', 'tr', 'TR', 'USAGE', 'sunacnea-v1', 'SUNACNEA', 'AGENT_DRAFT', 3, 'sunacnea-tr-v1'),
  ('SUNACNEA kullanıcı yorumları', 'tr', 'TR', 'REVIEWS', 'sunacnea-v1', 'SUNACNEA', 'AGENT_DRAFT', 3, 'sunacnea-tr-v1'),
  ('L''CARLIÉ güneş bakım ürünleri', 'tr', 'TR', 'CATEGORY', 'sunacnea-v1', NULL, 'AGENT_DRAFT', 3, 'sunacnea-tr-v1'),
  ('SUNACNEA nereden alınır', 'tr', 'TR', 'SHOPPING', 'sunacnea-v1', 'SUNACNEA', 'AGENT_DRAFT', 4, 'sunacnea-tr-v1')
ON CONFLICT DO NOTHING;

COMMIT;
