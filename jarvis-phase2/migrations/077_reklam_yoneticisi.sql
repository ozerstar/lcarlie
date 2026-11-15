-- 077 REKLAM YONETICISI (15.11.2026)
-- Sahip: "Meta Business'taki gibi kreatifler, hangi kreatif ne getirmis, kac
-- lira harcamis; yaninda Jarvis ve reklam ekiplerinin onerileri."
--
-- Panel (jarvis_web) kisisel veriye ERISMEZ: core.alici_siparis alici adi/
-- adresi tutar, panele yalniz gun x kanal x urun TOPLAMI acilir (gorunum
-- sahibinin yetkisiyle calisir). raw.meta_kreatif.ham da acilmaz; metin
-- alanlari gorunumde cikarilir.
--
-- Oneri tablolari: scripts/reklam-oneri.py (root, n8n) yazar; panel okur.
-- Onay gereken oneri ayrica core.ai_sistem_onerisi ile ana onay kuyruguna
-- (WhatsApp onay hatti) duser. Hicbir reklam ayari otomatik degismez:
-- REQUEST_HUMAN_REVIEW'in uygulayicisi yoktur.
BEGIN;

-- 1) Kreatif metni + Trendyol urunu (ham JSON'dan)
CREATE OR REPLACE VIEW mart.reklam_kreatif AS
SELECT k.ad_id, k.kreatif_id, k.kreatif_adi, k.nesne_tipi, k.video_id, k.cta,
       COALESCE(NULLIF(k.hedef_url, ''), k.ham #>> '{creative,asset_feed_spec,link_urls,0,website_url}') AS hedef_url,
       COALESCE(NULLIF(k.baslik, ''), k.ham #>> '{creative,asset_feed_spec,titles,0,text}',
                k.ham #>> '{creative,title}') AS baslik,
       COALESCE(NULLIF(k.govde, ''), k.ham #>> '{creative,asset_feed_spec,bodies,0,text}',
                k.ham #>> '{creative,body}') AS govde,
       k.ham #>> '{creative,asset_feed_spec,descriptions,0,text}' AS aciklama,
       t.barkod AS trendyol_barkod,
       k.cekim_at
FROM raw.meta_kreatif k
LEFT JOIN raw.trendyol_urun t
  ON t.content_id = (regexp_match(COALESCE(k.hedef_url, ''), '-p-([0-9]+)'))[1]::bigint;
COMMENT ON VIEW mart.reklam_kreatif IS 'Reklam Yoneticisi: kreatif metni ve Trendyol barkodu (ham JSON panele acilmaz). 077.';

-- 2) Defter: gun x kanal x urun (odenen tutar; kisisel veri YOK)
CREATE OR REPLACE VIEW mart.reklam_defter_satis AS
SELECT (a.zaman AT TIME ZONE 'Europe/Istanbul')::date AS gun, a.kanal,
       NULLIF(k ->> 'barkod', '') AS barkod, upper(k ->> 'kod') AS kod,
       count(DISTINCT a.siparis_no) AS siparis,
       sum(COALESCE((k ->> 'adet')::numeric, 0)) AS adet,
       round(sum(COALESCE((k ->> 'tutar')::numeric, 0)), 2) AS ciro
FROM core.alici_siparis a
CROSS JOIN LATERAL jsonb_array_elements(a.kalemler) k
WHERE a.kanal <> 'wix'
  AND lower(COALESCE(a.durum, '')) !~ '(cancel|unsupplied|return|iptal|iade|refund)'
GROUP BY 1, 2, 3, 4
UNION ALL
SELECT s.gun, 'wix', ui.barkod, ui.urun_kod,
       count(DISTINCT s.siparis_id), sum(s.adet), round(sum(s.satir_ciro), 2)
FROM mart.siparis_kalem s
LEFT JOIN core.urun_kimlik ui ON ui.urun_id = s.urun_id
WHERE s.ciro_sinifi IN ('DOGRULANMIS', 'BEYAN_EDILMIS')
GROUP BY 1, 2, 3, 4;
COMMENT ON VIEW mart.reklam_defter_satis IS 'Reklam Yoneticisi defteri: gun x kanal x urun, ODENEN tutar (Trendyol price, liste fiyati degil). Pazaryeri core.alici_siparis (15 dk), Wix mart.siparis_kalem. 077.';

-- 3) Defter: gun x kanal siparis toplami (bir siparis bir kez)
CREATE OR REPLACE VIEW mart.reklam_defter_gunluk AS
SELECT (a.zaman AT TIME ZONE 'Europe/Istanbul')::date AS gun, a.kanal,
       count(*) AS siparis, round(sum(a.tutar), 2) AS ciro
FROM core.alici_siparis a
WHERE a.kanal <> 'wix'
  AND lower(COALESCE(a.durum, '')) !~ '(cancel|unsupplied|return|iptal|iade|refund)'
GROUP BY 1, 2
UNION ALL
SELECT s.gun, 'wix', count(DISTINCT s.siparis_id), round(sum(s.satir_ciro), 2)
FROM mart.siparis_kalem s
WHERE s.ciro_sinifi IN ('DOGRULANMIS', 'BEYAN_EDILMIS')
GROUP BY 1, 2;
COMMENT ON VIEW mart.reklam_defter_gunluk IS 'Reklam Yoneticisi: gun x kanal siparis ve ciro (MER icin). 077.';

CREATE OR REPLACE VIEW mart.reklam_defter_tazelik AS
SELECT max(guncellendi) AS son_olcum, count(*) AS siparis_kaydi FROM core.alici_siparis;
COMMENT ON VIEW mart.reklam_defter_tazelik IS 'Pazaryeri satis kaydinin son guncellenme ani (scripts/reklam-olcum.py, 15 dk). 077.';

-- 4) Urun ekonomisi: maliyet (finans merkezi) + fiyat + komisyon
CREATE OR REPLACE VIEW mart.reklam_urun_ekonomi AS
SELECT m.urun_kod, m.barkod, m.pazaryeri_barkod,
       m.birim_maliyet_kdv_haric AS maliyet, m.durum AS maliyet_durum,
       (SELECT c.komisyon_yuzde FROM core.urun_platform_komisyon c
         WHERE c.urun_id = m.urun_id AND c.platform_kod = 'trendyol') AS ty_komisyon,
       (SELECT c.komisyon_yuzde FROM core.urun_platform_komisyon c
         WHERE c.urun_id = m.urun_id AND c.platform_kod = 'idefix') AS idefix_komisyon,
       (SELECT NULLIF(t.ham #>> '{fiyat,salePrice}', '')::numeric FROM raw.trendyol_urun t
         WHERE t.barkod IN (m.pazaryeri_barkod, m.barkod)
         ORDER BY (t.barkod = m.pazaryeri_barkod) DESC NULLS LAST LIMIT 1) AS ty_fiyat,
       (SELECT f.gecerli_fiyat FROM mart.platform_fiyat_matrisi f
         WHERE f.urun_id = m.urun_id AND f.platform_kod = 'wix' LIMIT 1) AS wix_fiyat,
       (SELECT b.deger FROM core.maliyet_bileseni b
         WHERE b.bilesen = 'POS_KOMISYONU' AND b.gecerli_bitis IS NULL
         ORDER BY b.gecerli_baslangic DESC LIMIT 1) AS pos_yuzde
FROM core.urun_maliyet_guncel m
WHERE COALESCE(m.urun_turu, 'KOZMETIK') = 'KOZMETIK';
COMMENT ON VIEW mart.reklam_urun_ekonomi IS 'Reklam Yoneticisi basabas girdisi: maliyet core.urun_maliyet_guncel (tek kaynak), Trendyol satis fiyati + komisyonu, Wix fiyati, POS. 077.';

-- 5) Oneri hatti
CREATE TABLE IF NOT EXISTS core.reklam_oneri_kosu (
  id          bigserial PRIMARY KEY,
  bas_at      timestamptz NOT NULL DEFAULT now(),
  bit_at      timestamptz,
  tetik       text NOT NULL CHECK (tetik IN ('ZAMANLI', 'KRITIK', 'ELLE')),
  durum       text NOT NULL CHECK (durum IN ('SURUYOR', 'TAMAM', 'KISMI', 'HATA')),
  donem_bas   date,
  donem_bit   date,
  model       text,
  ozet        jsonb NOT NULL DEFAULT '[]'::jsonb,
  hata        text
);
COMMENT ON TABLE core.reklam_oneri_kosu IS 'Reklam uzman ikilisi (META_MEDIA + MARKETPLACE) oneri kosusu; ozet = "Ne yapmaliyim" 3 madde. scripts/reklam-oneri.py. 077.';

CREATE TABLE IF NOT EXISTS core.reklam_oneri (
  id            bigserial PRIMARY KEY,
  kosu_id       bigint NOT NULL REFERENCES core.reklam_oneri_kosu(id) ON DELETE CASCADE,
  departman     text NOT NULL CHECK (departman IN ('META_MEDIA', 'MARKETPLACE')),
  kapsam        text NOT NULL CHECK (kapsam IN ('HESAP', 'KAMPANYA', 'SET', 'REKLAM', 'YERLESIM', 'URUN')),
  hedef_id      text,
  hedef_ad      text,
  oncelik       smallint NOT NULL DEFAULT 2 CHECK (oncelik BETWEEN 1 AND 3),
  ne            text NOT NULL,
  neden         text NOT NULL,
  beklenen_etki text,
  risk          text,
  geri_alma     text,
  olcum         text,
  onay_gerekir  boolean NOT NULL,
  kaynak        text NOT NULL CHECK (kaynak IN ('KURAL', 'MODEL')),
  anahtar       text NOT NULL,
  ozet          text,
  action_id     bigint,
  olusturma     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reklam_oneri_kosu_idx ON core.reklam_oneri (kosu_id);
COMMENT ON TABLE core.reklam_oneri IS 'Reklam onerileri (NE/NEDEN/ETKI/RISK/GERI ALMA/OLCUM/ONAY). action_id = onay kuyrugundaki oneri. Hicbir reklam ayari otomatik degismez. 077.';

GRANT SELECT ON mart.reklam_kreatif, mart.reklam_defter_satis, mart.reklam_defter_gunluk,
                mart.reklam_defter_tazelik, mart.reklam_urun_ekonomi,
                core.reklam_oneri_kosu, core.reklam_oneri TO jarvis_web, ai_reader;

COMMIT;
