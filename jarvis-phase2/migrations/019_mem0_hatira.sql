-- 019 — mem0 hatıra katmanı: şema, rol, ve KANIT SINIRI
--
-- NE EKLENİYOR
-- Jarvis'in bugüne kadarki hatırlaması iki dosyaydı: son 6 tur (pencere) ve
-- elle yazılmış notlar. Arama yoktu. "Dün Vireon fiyatını konuşmuştuk" gibi
-- bir cümle, notlarda "VIREON birim fiyat" diye geçiyorsa BULUNAMIYORDU --
-- bu projede 11 kez çarptığımız Türkçe tam-kelime eşleşme tuzağının ta kendisi.
-- mem0 anlamsal arama getiriyor: eşleşme kelimeye değil anlama bakıyor.
--
-- NEDEN AYRI ŞEMA, NEDEN AYRI ROL
-- mem0'ın kendi tablosu şu üçünü tutar ve BAŞKA HİÇBİR ŞEYİ:
--     id UUID, vector vector(N), payload JSONB
-- Karşılaştırın: ai_semantic.memory_embedding'de evidence_ref NOT NULL,
-- model_id NOT NULL, model_revision NOT NULL ve içerik üzerinde UNIQUE var.
-- Yani bu sistemin kendi gömme tablosu "her gömme bir kanıta işaret eder"
-- kuralını ŞEMA DÜZEYİNDE zorluyor. mem0'ın tablosu hiçbir şey zorlamıyor.
--
-- Bu bir kusur değil, farklı iş: mem0 TERCİH ve BAĞLAM hatırlar
-- ("kullanıcı yüzde bazlı toplu fiyat müdahalesi istiyor"), şirket GERÇEĞİ
-- değil. Şirket gerçeği mart görünümlerinden gelmeye devam eder.
--
-- Sınır bu yüzden core/mart sınırının aynısı gibi kuruluyor:
--     mem0_writer  ->  YALNIZ mem0 şeması. core, mart, raw okuyamaz.
--     ai_reader    ->  YALNIZ mart görünümleri. (değişmedi)
-- mem0'ın hatırladığı bir şey cevapta ŞİRKET VERİSİ olarak kullanılamaz;
-- kullanılırsa kanıt zinciri sessizce kopar. Sınırı kod değil, yetki tutar.
--
-- SEARCH_PATH NEDEN ROLE SABİTLENİYOR
-- mem0'ın pgvector sürücüsü tabloyu şemasız tek tanımlayıcıyla yaratıyor
-- (sql.Identifier(collection_name)) -- yani tablo search_path'in ilk yazılabilir
-- şemasına düşer. Sabitlemezsek public'e düşerdi. Role sabitliyoruz.
--
-- BOYUT NEDEN 1024
-- ai_semantic.memory_embedding zaten vector(1024). Gemini'nin embedder'ı
-- output_dimensionality parametresini geçiriyor (mem0/embeddings/gemini.py),
-- yani 1024 isteyebiliyoruz. Aynı boyutta kalmak, ileride iki katmanı
-- karşılaştırmayı mümkün bırakır; farklı boyut o kapıyı kapatırdı.

\set ON_ERROR_STOP on
BEGIN;

CREATE SCHEMA IF NOT EXISTS mem0;

COMMENT ON SCHEMA mem0 IS
  'mem0 hatira katmani. TERCIH ve BAGLAM tutar, sirket gercegi TUTMAZ. '
  'Buradaki bir satir kanit degildir: evidence_ref yoktur. Sirket verisi '
  'mart gorunumlerinden gelir. Bkz. ai_semantic.memory_embedding.';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mem0_writer') THEN
    CREATE ROLE mem0_writer LOGIN NOINHERIT;
  END IF;
END $$;

-- Tablo mem0'in kendisi tarafindan yaratilacak; bu yuzden CREATE gerekli.
GRANT USAGE, CREATE ON SCHEMA mem0 TO mem0_writer;
ALTER ROLE mem0_writer SET search_path = mem0;

-- public'e dusmesin diye REVOKE YAZMIYORUZ: PostgreSQL 15'ten beri PUBLIC'in
-- public semasinda CREATE hakki zaten yok (17.11'de olculdu: false) ve bu
-- veritabaninin public semasinda n8n'in 136 tablosu duruyor -- oraya
-- dokunmanin faydasi yok, riski var. Yalniz DOGRULUYORUZ.

-- Dogrula: sinir gercekten duruyor mu.
DO $$
DECLARE
  t text;
BEGIN
  IF NOT has_schema_privilege('mem0_writer','mem0','CREATE') THEN
    RAISE EXCEPTION 'mem0_writer kendi semasinda tablo yaratamiyor';
  END IF;
  IF has_schema_privilege('mem0_writer','public','CREATE') THEN
    RAISE EXCEPTION 'mem0_writer public semasina yazabiliyor -- tablo oraya duserdi';
  END IF;

  -- core / mart / raw: tek bir tablo bile okunabiliyorsa sinir delinmis demektir.
  FOR t IN
    SELECT c.oid::regclass::text
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('core','mart','raw','ai_semantic') AND c.relkind IN ('r','v','m')
  LOOP
    IF has_table_privilege('mem0_writer', t, 'SELECT') THEN
      RAISE EXCEPTION 'mem0_writer % okuyabiliyor -- kanit siniri delinmis', t;
    END IF;
  END LOOP;

  IF (SELECT rolinherit FROM pg_roles WHERE rolname='mem0_writer') THEN
    RAISE EXCEPTION 'mem0_writer NOINHERIT degil -- uyelikle yetki devralabilir';
  END IF;
END $$;

COMMIT;
