-- =============================================================================
-- 037 · TARAYICI ISI: Jarvis'in PC'deki Chrome'a is vermesi
--
-- SAHIP KARARI (16.10.2026): "jarvis bir ise kuyruga yazsin, bilgisayarimdaki
-- worker alsin, Chrome'da ChatGPT/Claude'u acip yaptirsin, sonucu geri
-- yuklesin."
--
-- NEDEN AYRI TABLO -- OLCULDU, ZORUNLU
--   core.ai_task'in iki CHECK kisiti bu isi KABUL ETMEZ:
--     task_type   IN (ANALYZE, REDTEAM, PROPOSE_DECISION, PROPOSE_ACTION,
--                     SUMMARIZE, CLASSIFY)
--     source_type IN (ACIK_SORU, BULGU, KARAR, IC_MESAJ, MANUAL)
--   Yeni bir deger eklemek, 17 timer'in paylastigi kuyrugun kisitini
--   genisletmek demekti. Tarayici isi oraya girmez; kendi tablosunda durur
--   ve ai_task'a HIC dokunulmaz.
--
--   Kiralama (lease) deseni ise core.ai_claim_task'tan BIREBIR kopyalandi:
--   FOR UPDATE SKIP LOCKED + tek CTE icinde UPDATE. Iki worker ayni isi
--   alamaz; bu, uygulama katmaninda cozulmeye calisilacak bir sey degil.
--
-- 🔴 SINIRLAR BETIKTE DEGIL BURADA. Worker betigi degistirilse, kopyalansa
--    ya da elle calistirilsa bile:
--      1) tarayici_worker_enabled kapaliysa HIC is alinmaz
--      2) en_cok_deneme asilirsa is HATA olur, sonsuza kadar denenmez
--      3) INSAN_GEREKLI terminaldir -- CAPTCHA'li is yeniden denenmez
--      4) kira jetonu bilmeyen hicbir cagri isi bitiremez/hataya atamaz
--
-- 🔴 DURUM AYRIMI KORUNUR (bkz. jarvis/durum ayrimi kapisi):
--    BEKLIYOR  henuz alinmadi      -- worker kapali OLABILIR, kanit degil
--    CALISIYOR kiralandi, suruyor
--    BITTI     sonuc geldi         -- henuz sahibe SUNULMADI
--    SUNULDU   onay kuyruguna kondu
--    HATA      denemeler tukendi
--    INSAN_GEREKLI giris/CAPTCHA/hesap uyarisi -- insan bakmali
--    "Sonuc yok" ile "is hic alinmadi" ayri durumlardir ve ayri yazilir.
--
-- GERI ALMA: rollback/037_tarayici_isi_ROLLBACK.sql
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Merkezi anahtar. Worker'i PC'ye gitmeden kapatmanin tek yolu.
-- --------------------------------------------------------------------------
INSERT INTO core.ai_orchestrator_config (config_key, config_value, description)
VALUES ('tarayici_worker_enabled', 'true',
        'PC tarayici worker''i is alabilir mi. false ise tarayici_isi_al hic is dondurmez.')
ON CONFLICT (config_key) DO NOTHING;


CREATE TABLE core.tarayici_isi (
  is_id            bigserial PRIMARY KEY,
  olusturuldu      timestamptz NOT NULL DEFAULT clock_timestamp(),
  guncellendi      timestamptz NOT NULL DEFAULT clock_timestamp(),
  isteyen          text        NOT NULL CHECK (btrim(isteyen) <> '' AND length(isteyen) <= 80),
  hedef            text        NOT NULL CHECK (hedef IN ('chatgpt_image','chatgpt_chat','claude_chat')),
  istem            text        NOT NULL CHECK (btrim(istem) <> '' AND length(istem) <= 8000),
  girdi_dosyalari  jsonb       NOT NULL DEFAULT '[]'::jsonb
                               CHECK (jsonb_typeof(girdi_dosyalari) = 'array'),
  durum            text        NOT NULL DEFAULT 'BEKLIYOR'
                               CHECK (durum IN ('BEKLIYOR','CALISIYOR','BITTI',
                                                'SUNULDU','HATA','INSAN_GEREKLI')),
  kiralayan        text,
  kira_zamani      timestamptz,
  kira_sonu        timestamptz,
  kira_jetonu      uuid,
  deneme           integer     NOT NULL DEFAULT 0 CHECK (deneme >= 0),
  en_cok_deneme    integer     NOT NULL DEFAULT 2 CHECK (en_cok_deneme > 0),
  sonuc_metin      text,
  sonuc_dosyalari  jsonb       NOT NULL DEFAULT '[]'::jsonb
                               CHECK (jsonb_typeof(sonuc_dosyalari) = 'array'),
  ekran_goruntusu  text,
  hata             text,
  -- Sonuc metni mevzuat kapisindan gecti mi. Kapi jarvis/tarayici.py'de
  -- isletilir; buradaki alan KARARIN KAYDIDIR, kararin kendisi degil.
  uyum_durumu      text        CHECK (uyum_durumu IN ('GECTI','BLOKLU')),
  -- jarvis:TARAYICI_SONUC:<slug> idempotency anahtarinin slug'i.
  slug             text UNIQUE CHECK (slug IS NULL OR slug ~ '^[A-Za-z0-9_.-]{1,80}$'),
  idempotency_key  text        NOT NULL UNIQUE
                               CHECK (btrim(idempotency_key) <> '' AND length(idempotency_key) <= 200)
);

-- Kuyruk taramasi her 15 saniyede bir kosacak; sirali tarama yeterli degil.
CREATE INDEX tarayici_isi_bekleyen_ix
    ON core.tarayici_isi (durum, is_id)
    WHERE durum IN ('BEKLIYOR','CALISIYOR');
CREATE INDEX tarayici_isi_sunulacak_ix
    ON core.tarayici_isi (durum, is_id)
    WHERE durum IN ('BITTI','HATA','INSAN_GEREKLI');

REVOKE ALL ON core.tarayici_isi FROM PUBLIC;
REVOKE ALL ON SEQUENCE core.tarayici_isi_is_id_seq FROM PUBLIC;


-- --------------------------------------------------------------------------
-- Nabiz. Yeni bir "worker_heartbeat" kavrami UYDURULMAZ: panelin SISTEM
-- sekmesi zaten state/hosts/pc1.json'u okuyor ve tazelik sozlugu
-- (TAZE/BAYAT/RAPOR_YOK) orada tanimli. Buradaki tablo o dosyanin
-- veritabani ikizi degil; worker'in KUYRUGA bakip bakmadigini soyler,
-- makinenin acik olup olmadigini SOYLEMEZ.
-- --------------------------------------------------------------------------
CREATE TABLE core.tarayici_nabiz (
  worker       text PRIMARY KEY CHECK (btrim(worker) <> '' AND length(worker) <= 80),
  son_gorulme  timestamptz NOT NULL DEFAULT clock_timestamp(),
  ayrinti      jsonb NOT NULL DEFAULT '{}'::jsonb
               CHECK (jsonb_typeof(ayrinti) = 'object')
);
REVOKE ALL ON core.tarayici_nabiz FROM PUBLIC;


-- --------------------------------------------------------------------------
-- EKLEME. Jarvis (ai_writer) burayi cagirir.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_isi_ekle(
    p_isteyen text,
    p_hedef   text,
    p_istem   text,
    p_idempotency_key text,
    p_girdi_dosyalari jsonb DEFAULT '[]'::jsonb
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
DECLARE
  v_is_id bigint;
BEGIN
  IF p_idempotency_key IS NULL OR btrim(p_idempotency_key) = '' THEN
    RAISE EXCEPTION 'idempotency_key zorunlu';
  END IF;
  IF p_girdi_dosyalari IS NULL OR jsonb_typeof(p_girdi_dosyalari) <> 'array' THEN
    RAISE EXCEPTION 'girdi_dosyalari bir JSON dizisi olmali';
  END IF;

  -- Ayni anahtarla ikinci kez cagrilmasi HATA DEGILDIR: var olan isin
  -- kimligi doner. Boylece aglanan bir yanit ya da yeniden denenen bir
  -- cagri ikinci is acmaz.
  SELECT is_id INTO v_is_id FROM core.tarayici_isi
   WHERE idempotency_key = p_idempotency_key;
  IF v_is_id IS NOT NULL THEN
    RETURN v_is_id;
  END IF;

  INSERT INTO core.tarayici_isi (isteyen, hedef, istem, girdi_dosyalari, idempotency_key)
  VALUES (btrim(p_isteyen), p_hedef, p_istem, p_girdi_dosyalari, btrim(p_idempotency_key))
  RETURNING is_id INTO v_is_id;
  RETURN v_is_id;
END $fn$;


-- --------------------------------------------------------------------------
-- ALMA. ATOMIK. core.ai_claim_task deseni.
--
-- 🔴 Iki worker ayni anda ayni isi ALAMAZ: aday satir FOR UPDATE SKIP
--    LOCKED ile kilitlenir ve UPDATE ayni ifadenin icinde olur. Ikinci
--    worker o satiri hic gormez, bir sonrakine gecer.
-- 🔴 Suresi dolmus kira yeniden aday olur: worker cokerse is sonsuza
--    kadar CALISIYOR'da kalmasin. deneme siniri yine gecerlidir.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_isi_al(
    p_worker  text,
    p_kira_s  integer DEFAULT 420
) RETURNS TABLE(is_id bigint, hedef text, istem text,
                girdi_dosyalari jsonb, kira_jetonu uuid, deneme integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
DECLARE
  v_acik boolean;
BEGIN
  SELECT config_value::boolean INTO v_acik
    FROM core.ai_orchestrator_config WHERE config_key = 'tarayici_worker_enabled';
  IF NOT COALESCE(v_acik, false) THEN
    RETURN;   -- kapali: hic is verilmez, hata da yukselmez
  END IF;
  IF p_worker IS NULL OR btrim(p_worker) = '' THEN
    RAISE EXCEPTION 'worker adi zorunlu';
  END IF;
  IF p_kira_s IS NULL OR p_kira_s < 60 OR p_kira_s > 1800 THEN
    RAISE EXCEPTION 'kira suresi 60-1800 sn araliginda olmali';
  END IF;

  RETURN QUERY
  WITH aday AS (
    SELECT t.is_id FROM core.tarayici_isi t
     WHERE (t.durum = 'BEKLIYOR'
            OR (t.durum = 'CALISIYOR' AND t.kira_sonu < clock_timestamp()))
       AND t.deneme < t.en_cok_deneme
     ORDER BY t.is_id
     FOR UPDATE SKIP LOCKED LIMIT 1
  ), alinan AS (
    UPDATE core.tarayici_isi t
       SET durum = 'CALISIYOR',
           kiralayan = btrim(p_worker),
           kira_zamani = clock_timestamp(),
           kira_sonu = clock_timestamp() + make_interval(secs => p_kira_s),
           kira_jetonu = gen_random_uuid(),
           deneme = t.deneme + 1,
           hata = NULL,
           guncellendi = clock_timestamp()
      FROM aday a WHERE t.is_id = a.is_id
    RETURNING t.is_id, t.hedef, t.istem, t.girdi_dosyalari, t.kira_jetonu, t.deneme
  ) SELECT * FROM alinan;
END $fn$;


-- --------------------------------------------------------------------------
-- BITIRME. Kira jetonu olmadan cagrilamaz.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_isi_bitir(
    p_is_id   bigint,
    p_jeton   uuid,
    p_metin   text,
    p_dosyalar jsonb DEFAULT '[]'::jsonb,
    p_ekran   text DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
BEGIN
  IF p_dosyalar IS NULL OR jsonb_typeof(p_dosyalar) <> 'array' THEN
    RAISE EXCEPTION 'dosyalar bir JSON dizisi olmali';
  END IF;
  -- Ne metin ne dosya varsa bu bir basari DEGILDIR. "Bos sonucu basarili
  -- sayma" kurali: ici bos bir sonuc, sahibin onuna konacak bir sey degil.
  IF (p_metin IS NULL OR btrim(p_metin) = '') AND jsonb_array_length(p_dosyalar) = 0 THEN
    RAISE EXCEPTION 'sonuc bos: ne metin ne dosya var';
  END IF;

  UPDATE core.tarayici_isi
     SET durum = 'BITTI', sonuc_metin = p_metin, sonuc_dosyalari = p_dosyalar,
         ekran_goruntusu = COALESCE(p_ekran, ekran_goruntusu),
         kira_jetonu = NULL, kira_sonu = NULL, guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND kira_jetonu = p_jeton AND durum = 'CALISIYOR';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'is bitirilemedi: kimlik/jeton/durum uyusmuyor (is_id=%)', p_is_id;
  END IF;
END $fn$;


-- --------------------------------------------------------------------------
-- HATA. Deneme hakki kaldiysa is BEKLIYOR'a doner; tukendiyse HATA olur.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_isi_hata(
    p_is_id bigint,
    p_jeton uuid,
    p_hata  text,
    p_ekran text DEFAULT NULL
) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
DECLARE
  v_durum text;
BEGIN
  UPDATE core.tarayici_isi
     SET durum = CASE WHEN deneme >= en_cok_deneme THEN 'HATA' ELSE 'BEKLIYOR' END,
         hata = left(COALESCE(p_hata, 'sebep bildirilmedi'), 1000),
         ekran_goruntusu = COALESCE(p_ekran, ekran_goruntusu),
         kiralayan = NULL, kira_jetonu = NULL, kira_sonu = NULL,
         guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND kira_jetonu = p_jeton AND durum = 'CALISIYOR'
  RETURNING durum INTO v_durum;
  IF v_durum IS NULL THEN
    RAISE EXCEPTION 'hata yazilamadi: kimlik/jeton/durum uyusmuyor (is_id=%)', p_is_id;
  END IF;
  RETURN v_durum;
END $fn$;


-- --------------------------------------------------------------------------
-- INSAN GEREKLI. TERMINAL: yeniden denenmez.
--
-- 🔴 Giris ekrani, CAPTCHA ya da hesap uyarisi gorulduyse is burada DURUR.
--    Yeniden denemek, bot dogrulamasini asmaya calismak demek olurdu --
--    worker bunu yapmaz, insana birakir.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_isi_insan(
    p_is_id bigint,
    p_jeton uuid,
    p_sebep text,
    p_ekran text DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
BEGIN
  UPDATE core.tarayici_isi
     SET durum = 'INSAN_GEREKLI',
         hata = left(COALESCE(p_sebep, 'insan mudahalesi gerekli'), 1000),
         ekran_goruntusu = COALESCE(p_ekran, ekran_goruntusu),
         kira_jetonu = NULL, kira_sonu = NULL, guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND kira_jetonu = p_jeton AND durum = 'CALISIYOR';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'insan durumu yazilamadi: kimlik/jeton/durum uyusmuyor (is_id=%)', p_is_id;
  END IF;
END $fn$;


-- --------------------------------------------------------------------------
-- SUNULDU. Sonuc onay kuyruguna konduktan sonra isaretlenir; boylece
-- ayni sonuc ikinci kez oneri uretmez.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_isi_sunuldu(
    p_is_id bigint,
    p_slug  text,
    p_uyum  text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
BEGIN
  IF p_slug IS NULL OR p_slug !~ '^[A-Za-z0-9_.-]{1,80}$' THEN
    RAISE EXCEPTION 'slug gecersiz';
  END IF;
  UPDATE core.tarayici_isi
     SET durum = 'SUNULDU', slug = p_slug, uyum_durumu = p_uyum,
         guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND durum IN ('BITTI','HATA','INSAN_GEREKLI');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'sunuldu yazilamadi: is_id=% uygun durumda degil', p_is_id;
  END IF;
END $fn$;


-- --------------------------------------------------------------------------
-- NABIZ YAZMA.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_nabiz_yaz(
    p_worker  text,
    p_ayrinti jsonb DEFAULT '{}'::jsonb
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
BEGIN
  IF p_worker IS NULL OR btrim(p_worker) = '' THEN
    RAISE EXCEPTION 'worker adi zorunlu';
  END IF;
  IF p_ayrinti IS NULL OR jsonb_typeof(p_ayrinti) <> 'object' THEN
    RAISE EXCEPTION 'ayrinti bir JSON nesnesi olmali';
  END IF;
  INSERT INTO core.tarayici_nabiz (worker, son_gorulme, ayrinti)
  VALUES (btrim(p_worker), clock_timestamp(), p_ayrinti)
  ON CONFLICT (worker) DO UPDATE
    SET son_gorulme = clock_timestamp(), ayrinti = EXCLUDED.ayrinti;
END $fn$;


-- --------------------------------------------------------------------------
-- OKUMA. Panel ve dongu buradan okur.
--
-- 🔴 Sayim her durumu AYRI dondurur ve yoklugu sifirla karistirmaz:
--    cagiran taraf "BEKLIYOR=0" ile "tablo okunamadi"yi ayirt edebilsin.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.tarayici_sayim()
RETURNS TABLE(durum text, adet bigint)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
  SELECT d.durum, COUNT(t.is_id)
    FROM (VALUES ('BEKLIYOR'),('CALISIYOR'),('BITTI'),('SUNULDU'),
                 ('HATA'),('INSAN_GEREKLI')) AS d(durum)
    LEFT JOIN core.tarayici_isi t ON t.durum = d.durum
   GROUP BY d.durum ORDER BY d.durum;
$fn$;

CREATE OR REPLACE FUNCTION core.tarayici_sunulacak(p_limit integer DEFAULT 20)
RETURNS TABLE(is_id bigint, hedef text, istem text, durum text, isteyen text,
              sonuc_metin text, sonuc_dosyalari jsonb, ekran_goruntusu text,
              hata text, olusturuldu timestamptz, deneme integer)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
  SELECT t.is_id, t.hedef, t.istem, t.durum, t.isteyen, t.sonuc_metin,
         t.sonuc_dosyalari, t.ekran_goruntusu, t.hata, t.olusturuldu, t.deneme
    FROM core.tarayici_isi t
   WHERE t.durum IN ('BITTI','HATA','INSAN_GEREKLI')
   ORDER BY t.is_id
   LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 20), 100));
$fn$;

CREATE OR REPLACE FUNCTION core.tarayici_nabiz_oku()
RETURNS TABLE(worker text, son_gorulme timestamptz, yas_s numeric, ayrinti jsonb)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
  SELECT n.worker, n.son_gorulme,
         round(EXTRACT(EPOCH FROM (clock_timestamp() - n.son_gorulme))::numeric, 1),
         n.ayrinti
    FROM core.tarayici_nabiz n ORDER BY n.worker;
$fn$;

CREATE OR REPLACE FUNCTION core.tarayici_isi_getir(p_is_id bigint)
RETURNS TABLE(is_id bigint, hedef text, istem text, durum text,
              girdi_dosyalari jsonb, slug text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
  SELECT t.is_id, t.hedef, t.istem, t.durum, t.girdi_dosyalari, t.slug
    FROM core.tarayici_isi t WHERE t.is_id = p_is_id;
$fn$;


-- --------------------------------------------------------------------------
-- ROLLER VE YETKILER
--
-- tarayici_worker: PC'deki worker'in SSH kapisinin SET ROLE ile dustugu
-- rol. Kapi betigi hatali olsa bile bu rolun yapabilecegi seyler burada
-- sinirli: is alir, bitirir, hata/insan yazar, nabiz atar. Istem EKLEYEMEZ,
-- SUNULDU yazamaz, tabloyu dogrudan okuyamaz.
-- --------------------------------------------------------------------------
DO $roller$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tarayici_worker') THEN
    CREATE ROLE tarayici_worker NOLOGIN;
  END IF;
END $roller$;

-- 🔴 SEMA USAGE'I ATLANMAZ. EXECUTE grant'i tek basina YETMEZ: sema
--    uzerinde USAGE olmadan fonksiyon adi hic cozulmez ve cagri
--    "permission denied for schema core" ile duser. Ilk kurulumda tam
--    bu yuzden dustu; EXECUTE verilmis ama USAGE verilmemisti.
--    USAGE yalniz adlari gorunur kilar, tablolara eris VERMEZ --
--    tablolarin kendisinde tarayici_worker'in hicbir hakki yok.
GRANT USAGE ON SCHEMA core TO tarayici_worker;

ALTER TABLE core.tarayici_isi   OWNER TO function_owner;
ALTER TABLE core.tarayici_nabiz OWNER TO function_owner;
ALTER SEQUENCE core.tarayici_isi_is_id_seq OWNER TO function_owner;

ALTER FUNCTION core.tarayici_isi_ekle(text,text,text,text,jsonb)     OWNER TO function_owner;
ALTER FUNCTION core.tarayici_isi_al(text,integer)                    OWNER TO function_owner;
ALTER FUNCTION core.tarayici_isi_bitir(bigint,uuid,text,jsonb,text)  OWNER TO function_owner;
ALTER FUNCTION core.tarayici_isi_hata(bigint,uuid,text,text)         OWNER TO function_owner;
ALTER FUNCTION core.tarayici_isi_insan(bigint,uuid,text,text)        OWNER TO function_owner;
ALTER FUNCTION core.tarayici_isi_sunuldu(bigint,text,text)           OWNER TO function_owner;
ALTER FUNCTION core.tarayici_nabiz_yaz(text,jsonb)                   OWNER TO function_owner;
ALTER FUNCTION core.tarayici_sayim()                                 OWNER TO function_owner;
ALTER FUNCTION core.tarayici_sunulacak(integer)                      OWNER TO function_owner;
ALTER FUNCTION core.tarayici_nabiz_oku()                             OWNER TO function_owner;
ALTER FUNCTION core.tarayici_isi_getir(bigint)                       OWNER TO function_owner;

REVOKE ALL ON FUNCTION core.tarayici_isi_ekle(text,text,text,text,jsonb)    FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_isi_al(text,integer)                   FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_isi_bitir(bigint,uuid,text,jsonb,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_isi_hata(bigint,uuid,text,text)        FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_isi_insan(bigint,uuid,text,text)       FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_isi_sunuldu(bigint,text,text)          FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_nabiz_yaz(text,jsonb)                  FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_sayim()                                FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_sunulacak(integer)                     FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_nabiz_oku()                            FROM PUBLIC;
REVOKE ALL ON FUNCTION core.tarayici_isi_getir(bigint)                      FROM PUBLIC;

-- Jarvis is EKLER, sonuc OKUR; is ALAMAZ ve SUNULDU yazamaz.
GRANT EXECUTE ON FUNCTION core.tarayici_isi_ekle(text,text,text,text,jsonb) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.tarayici_sayim()            TO ai_writer, ai_reader, jarvis_web, human_approver;
GRANT EXECUTE ON FUNCTION core.tarayici_sunulacak(integer)  TO ai_writer, ai_reader, jarvis_web, human_approver;
GRANT EXECUTE ON FUNCTION core.tarayici_nabiz_oku()         TO ai_writer, ai_reader, jarvis_web, human_approver;
GRANT EXECUTE ON FUNCTION core.tarayici_isi_getir(bigint)   TO ai_writer, ai_reader, jarvis_web, human_approver;

-- Worker is ALIR ve KAPATIR; is ekleyemez.
GRANT EXECUTE ON FUNCTION core.tarayici_isi_al(text,integer)                   TO tarayici_worker;
GRANT EXECUTE ON FUNCTION core.tarayici_isi_bitir(bigint,uuid,text,jsonb,text) TO tarayici_worker;
GRANT EXECUTE ON FUNCTION core.tarayici_isi_hata(bigint,uuid,text,text)        TO tarayici_worker;
GRANT EXECUTE ON FUNCTION core.tarayici_isi_insan(bigint,uuid,text,text)       TO tarayici_worker;
GRANT EXECUTE ON FUNCTION core.tarayici_nabiz_yaz(text,jsonb)                  TO tarayici_worker;
GRANT EXECUTE ON FUNCTION core.tarayici_isi_getir(bigint)                      TO tarayici_worker;

-- SUNULDU'yu yalniz insan otoritesi yazar (oneriyi o aciyor).
GRANT EXECUTE ON FUNCTION core.tarayici_isi_sunuldu(bigint,text,text) TO human_approver;

COMMIT;
