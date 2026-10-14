-- SAHA ŞEMA 3: tek kanonik hedef anahtarı + branş çıkarımı
--
-- 🔴 NEDEN: ziyaret, bilgi ve durak tabloları kaynağa özel sütunlarla
-- anahtarlanmıştı (osm_tur+osm_id ya da nokta_id). Overture'ın oraya
-- koyacak bir yeri YOKTU. Sonuç: 18.845 hedefin 16.625'ine (%88) ziyaret
-- kaydedilemiyordu ve sahada öğrenilen bilgi yazılamıyordu. Kusur kodda
-- değil, şemadaydı: kaynağı anahtar yapmak, yeni kaynağı dışarıda bırakır.
--
-- ÇÖZÜM: mart.saha_hedef zaten tek bir metin anahtar üretiyor
-- ('osm:node:123' / 'ovt:08f...' / 'elle:7'). Artık üç tablo da ONU
-- taşıyor. Kaynağa özel sütunlar DURUYOR -- silmek, geçmişi okunamaz
-- kılardı; ama artık anahtar değiller.
--
-- 🔴 ZİYARET ARTIK GRUBA BAĞLANIR, TEK KAYDA DEĞİL. Aynı işletme OSM'de
-- ve Overture'da ayrı ayrı olabilir; görünüm bunları tek satıra indirir ve
-- hangisinin hayatta kalacağı ZENGİNLİK puanına bakar. Veri tazelendiğinde
-- kazanan değişebilir. Ziyareti tek anahtara bağlasaydık, o gün
-- "gidilmedi" diye yeniden listeye düşerdi ve saha elemanı aynı kapıyı
-- ikinci kez çalardı. Bu yüzden ziyaret, kaydın ait olduğu KOPYA GRUBUNA
-- bağlanır.
--
-- BRANŞ: Overture'da branş alanı yok ama kategori var
-- (obstetrics_and_gynecology gibi). Eşleme tablosu ile branşa çevrilir ve
-- kaynağı 'CIKARIM' yazılır. Beyan çıkarımı yener ama gizlemez: sahada
-- girilen branş her zaman öndedir, çıkarım olduğu ekranda görünür.

BEGIN;

-- 1) ZİYARET ---------------------------------------------------------------
ALTER TABLE core.saha_ziyaret    ADD COLUMN IF NOT EXISTS hedef_anahtari text;
ALTER TABLE core.saha_rota_durak ADD COLUMN IF NOT EXISTS hedef_anahtari text;

UPDATE core.saha_ziyaret SET hedef_anahtari =
       CASE WHEN nokta_id IS NOT NULL THEN 'elle:' || nokta_id
            WHEN osm_tur  IS NOT NULL THEN 'osm:' || osm_tur || ':' || osm_id END
 WHERE hedef_anahtari IS NULL;
UPDATE core.saha_rota_durak SET hedef_anahtari =
       CASE WHEN osm_tur IS NOT NULL THEN 'osm:' || osm_tur || ':' || osm_id END
 WHERE hedef_anahtari IS NULL;

-- Anahtarsız ziyaret kaydedilemez: kime gidildiği bilinmeyen bir ziyaret,
-- ziyaret değildir.
ALTER TABLE core.saha_ziyaret ALTER COLUMN hedef_anahtari SET NOT NULL;
CREATE INDEX IF NOT EXISTS saha_ziyaret_anahtar_idx
    ON core.saha_ziyaret (hedef_anahtari, ziyaret_at DESC);

-- 2) SAHA BİLGİ: birincil anahtar değişiyor --------------------------------
-- Eski PK (osm_tur, osm_id) NOT NULL zorunluluğu getiriyordu; Overture
-- kaydının osm_tur'u yok, bu yüzden satır AÇILAMIYORDU.
ALTER TABLE core.saha_bilgi ADD COLUMN IF NOT EXISTS hedef_anahtari text;
UPDATE core.saha_bilgi SET hedef_anahtari = 'osm:' || osm_tur || ':' || osm_id
 WHERE hedef_anahtari IS NULL AND osm_tur IS NOT NULL;
ALTER TABLE core.saha_bilgi DROP CONSTRAINT IF EXISTS saha_bilgi_pkey;
ALTER TABLE core.saha_bilgi ALTER COLUMN osm_tur DROP NOT NULL;
ALTER TABLE core.saha_bilgi ALTER COLUMN osm_id  DROP NOT NULL;
ALTER TABLE core.saha_bilgi ALTER COLUMN hedef_anahtari SET NOT NULL;
ALTER TABLE core.saha_bilgi ADD PRIMARY KEY (hedef_anahtari);

-- 3) BRANŞ EŞLEME ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.saha_brans_esleme (
  kategori text PRIMARY KEY,
  brans    text NOT NULL
);

INSERT INTO core.saha_brans_esleme (kategori, brans) VALUES
  ('obstetrics_and_gynecology',                 'KADIN_DOGUM'),
  ('reproductive_perinatal_and_womens_care',    'KADIN_DOGUM'),
  ('fertility_clinic',                          'KADIN_DOGUM'),
  ('dermatology',                               'DERMATOLOJI'),
  ('orthopedics',                               'ORTOPEDI'),
  ('urology',                                   'UROLOJI'),
  ('cardiology',                                'KARDIYOLOJI'),
  ('neurology',                                 'NOROLOJI'),
  ('physical_therapy',                          'FIZIK_TEDAVI'),
  ('rehabilitation_center',                     'FIZIK_TEDAVI'),
  ('pediatric_clinic',                          'COCUK'),
  ('pediatric_dentistry',                       'COCUK'),
  ('pediatrics',                                'COCUK'),
  ('dialysis_clinic',                           'DIYALIZ'),
  ('laboratory_testing',                        'LABORATUVAR'),
  ('laboratory',                                'LABORATUVAR'),
  ('medical_lab',                               'LABORATUVAR'),
  ('diagnostic_imaging',                        'GORUNTULEME'),
  ('radiology',                                 'GORUNTULEME'),
  ('general_dentistry',                         'GENEL'),
  ('cosmetic_dentistry',                        'ESTETIK'),
  ('orthodontics',                              'ORTODONTI'),
  ('oral_surgeon',                              'AGIZ_CENE'),
  ('endodontist',                               'ENDODONTI'),
  ('periodontist',                              'PERIODONTOLOJI'),
  ('ophthalmologist',                           'GOZ'),
  ('optometrist',                               'GOZ'),
  ('vision_or_eye_care_clinic',                 'GOZ'),
  ('ear_nose_throat',                           'KBB'),
  ('otolaryngologist',                          'KBB'),
  ('gastroenterologist',                        'GASTROENTEROLOJI'),
  ('endocrinologist',                           'ENDOKRINOLOJI'),
  ('oncologist',                                'ONKOLOJI'),
  ('psychiatrist',                              'PSIKIYATRI'),
  ('naturopathic_medicine',                     'ALTERNATIF'),
  ('complementary_and_alternative_medicine',    'ALTERNATIF'),
  ('acupuncture',                               'ALTERNATIF'),
  ('chiropractor',                              'ALTERNATIF'),
  ('veterinarian',                              'VETERINER'),
  ('podiatrist',                                'AYAK')
ON CONFLICT (kategori) DO UPDATE SET brans = EXCLUDED.brans;

COMMIT;
