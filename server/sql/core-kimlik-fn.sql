-- =============================================================================
-- L'CARLIE - KIMLIK BIRLESTIRME MANTIGI
--
-- CR-003 · 16.09.2026
--
-- 🔴 UC DEGISMEZ KURAL:
--   1. HAM DEGER KAYBOLMAZ.
--   2. BELIRSIZ ESLESME ZORLA BIRLESTIRILMEZ - cakisma kaydedilir.
--   3. AYNI VERI TEKRAR ISLENDIGINDE hicbir sey degismez (idempotent).
--
-- Guven skorlari (match_confidence):
--   100  kaynak sistemin kendi musteri kimligi (wix_buyer_id, wa_id, ig_id)
--    90  normalize e-posta
--    80  normalize telefon (E.164) - paylasilan hat ihtimali e-postadan yuksek
--     0  normalize EDILEMEDI (INVALID) -> eslestirmede KULLANILMAZ
--
-- 🔴 ILK TASARIMDA BULUNAN KUSUR (16.09.2026, canli veriyle yakalandi):
--    Cakisma yalnizca "bu deger ZATEN >1 musteriye bagli" durumunda
--    tetikleniyordu. Oysa gercek vaka sudur: deger musteri-1'e bagli ve
--    simdi musteri-2'ye baglanmak isteniyor. O an >1 musteri YOK, bir tane
--    var - yani cakisma HIC GORULMUYORDU. Wix'teki gercek vaka (ayni kisi
--    hem MEMBER hem CONTACT olarak kayitli) bu yuzden sessizce gecerdi.
--    Cozum: baglama aninda "bu degerin mevcut sahipleri kim" diye bakilir.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- core.kimlik_bagla(...)
--
-- BILINEN bir musteriye bir kimlik parcasi baglar.
-- Deger baska bir musteride de duruyorsa CAKISMA kaydeder - BIRLESTIRMEZ.
--
-- Donen sonuc: MATCHED | CONFLICT | INVALID | UNKNOWN
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.kimlik_bagla(
  p_customer_id        bigint,
  p_kaynak             text,
  p_kimlik_tipi        text,
  p_deger_ham          text,
  p_source_customer_id text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
  v_normal     text;
  v_gecerli    boolean := true;
  v_method     text;
  v_conf       smallint;
  v_digerleri  bigint[];
  v_sonuc      text;
  v_reason     text;
BEGIN
  IF p_deger_ham IS NULL OR btrim(p_deger_ham) = '' THEN
    RETURN 'UNKNOWN';
  END IF;

  CASE p_kimlik_tipi
    WHEN 'phone' THEN v_normal := core.telefon_e164(p_deger_ham);  v_method := 'phone_e164'; v_conf := 80;
    WHEN 'email' THEN v_normal := core.eposta_normal(p_deger_ham); v_method := 'email';      v_conf := 90;
    ELSE              v_normal := btrim(p_deger_ham);              v_method := 'source_id';  v_conf := 100;
  END CASE;

  IF v_normal IS NULL THEN
    -- 🔴 Normalize edilemeyen deger TAHMIN EDILMEZ. Ham hali saklanir,
    --    eslestirmede kullanilmaz.
    v_gecerli := false; v_conf := 0;
    v_sonuc := 'INVALID';
    v_reason := 'normalize edilemedi - eslestirmede kullanilmadi';
  ELSE
    -- Bu normalize deger BASKA musterilerde de var mi?
    SELECT array_agg(DISTINCT ci.customer_id)
      INTO v_digerleri
      FROM core.customer_identity ci
     WHERE ci.kimlik_tipi = p_kimlik_tipi
       AND ci.deger_normal = v_normal
       AND ci.gecerli
       AND ci.customer_id <> p_customer_id;

    IF v_digerleri IS NULL OR array_length(v_digerleri,1) IS NULL THEN
      v_sonuc := 'MATCHED';
      v_reason := format('%s ile tek musteriye bagli', v_method);
    ELSE
      -- 🔴 CAKISMA. Otomatik birlestirme YOK - iki ayri kisi olabilir ve
      --    birlestirme GERI ALINAMAZ. Insan karari beklenir.
      v_sonuc := 'CONFLICT';
      v_reason := format('%s degeri ayrica su musterilerde: %s', v_method, v_digerleri::text);
    END IF;
  END IF;

  -- Kimlik satiri (IDEMPOTENT) -------------------------------------------------
  INSERT INTO core.customer_identity (
    customer_id, kaynak, kimlik_tipi, source_customer_id,
    deger_ham, deger_normal, gecerli, match_method, match_confidence, match_reason
  ) VALUES (
    p_customer_id, p_kaynak, p_kimlik_tipi, p_source_customer_id,
    p_deger_ham, v_normal, v_gecerli, v_method, v_conf, v_reason
  )
  ON CONFLICT (kaynak, kimlik_tipi, deger_ham, COALESCE(source_customer_id,''))
  DO UPDATE SET
       deger_normal = EXCLUDED.deger_normal,
       gecerli      = EXCLUDED.gecerli,
       match_reason = EXCLUDED.match_reason,
       updated_at   = now();

  -- Cakismayi kaydet -----------------------------------------------------------
  IF v_sonuc = 'CONFLICT' THEN
    INSERT INTO core.identity_conflict (kimlik_tipi, deger_normal, customer_ids, kaynak_kayitlar)
    VALUES (
      p_kimlik_tipi, v_normal,
      (SELECT array_agg(DISTINCT x) FROM unnest(v_digerleri || p_customer_id) x),
      jsonb_build_array(jsonb_build_object(
        'kaynak', p_kaynak, 'source_customer_id', p_source_customer_id,
        'customer_id', p_customer_id))
    )
    ON CONFLICT (kimlik_tipi, deger_normal) WHERE durum = 'ACIK'
    DO UPDATE SET
      -- 🔴 Tekrar islemede cakisma KAYBOLMAZ; customer listesi genisler,
      --    ayni kaynak kaydi IKI KEZ eklenmez (idempotent).
      customer_ids    = (SELECT array_agg(DISTINCT x)
                           FROM unnest(core.identity_conflict.customer_ids || EXCLUDED.customer_ids) x),
      kaynak_kayitlar = CASE
                          WHEN core.identity_conflict.kaynak_kayitlar @> EXCLUDED.kaynak_kayitlar
                            THEN core.identity_conflict.kaynak_kayitlar
                          ELSE core.identity_conflict.kaynak_kayitlar || EXCLUDED.kaynak_kayitlar
                        END;

    -- Cakismaya taraf olan TUM musteriler isaretlenir.
    UPDATE core.customer c
       SET identity_status = 'CONFLICT', updated_at = now()
     WHERE c.customer_id = ANY(v_digerleri || p_customer_id)
       AND c.identity_status <> 'CONFLICT';
  END IF;

  -- Gosterim alanlarini tazele (TURETILMIS - otorite degil) ---------------------
  UPDATE core.customer c
     SET phone_normalized = (SELECT ci.deger_normal FROM core.customer_identity ci
                              WHERE ci.customer_id = c.customer_id
                                AND ci.kimlik_tipi='phone' AND ci.gecerli
                              ORDER BY ci.match_confidence DESC, ci.identity_id LIMIT 1),
         email_normalized = (SELECT ci.deger_normal FROM core.customer_identity ci
                              WHERE ci.customer_id = c.customer_id
                                AND ci.kimlik_tipi='email' AND ci.gecerli
                              ORDER BY ci.match_confidence DESC, ci.identity_id LIMIT 1),
         identity_status  = CASE
             WHEN c.identity_status = 'CONFLICT' THEN 'CONFLICT'   -- cakisma EZILMEZ
             WHEN v_sonuc = 'MATCHED' THEN 'MATCHED'
             WHEN v_sonuc = 'INVALID' AND c.identity_status IN ('UNKNOWN','INVALID') THEN 'INVALID'
             ELSE c.identity_status END,
         match_method     = COALESCE(c.match_method, v_method),
         match_confidence = GREATEST(COALESCE(c.match_confidence,0), v_conf),
         updated_at       = now()
   WHERE c.customer_id = p_customer_id;

  RETURN v_sonuc;
END;
$$;

COMMENT ON FUNCTION core.kimlik_bagla(bigint,text,text,text,text) IS
  'Bilinen musteriye kimlik baglar. Deger baska musteride varsa CAKISMA kaydeder, birlestirmez. Idempotent.';

-- -----------------------------------------------------------------------------
-- core.kaynak_musteri_ekle(...)
--
-- Bir kaynak sistem musterisini (Wix alicisi, WhatsApp gonderen vb.) tum
-- kimlik parcalariyla isler.
--
-- Sira onemli: ONCE kaynak kimligi musteriyi sabitler (100 guven),
-- SONRA e-posta ve telefon o musteriye baglanir.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.kaynak_musteri_ekle(
  p_kaynak             text,
  p_kaynak_kimlik_tipi text,
  p_source_customer_id text,
  p_telefon_ham        text DEFAULT NULL,
  p_eposta_ham         text DEFAULT NULL
)
RETURNS TABLE (customer_id bigint, telefon_sonuc text, eposta_sonuc text)
LANGUAGE plpgsql AS $$
DECLARE
  v_musteri bigint;
  v_tel text := 'UNKNOWN';
  v_eps text := 'UNKNOWN';
BEGIN
  IF p_source_customer_id IS NULL OR btrim(p_source_customer_id) = '' THEN
    RAISE EXCEPTION 'source_customer_id zorunlu (kaynak=%)', p_kaynak;
  END IF;

  -- 1) Kaynak kimliginden musteriyi bul veya olustur (IDEMPOTENT) --------------
  SELECT ci.customer_id INTO v_musteri
    FROM core.customer_identity ci
   WHERE ci.kaynak = p_kaynak
     AND ci.kimlik_tipi = p_kaynak_kimlik_tipi
     AND ci.deger_ham = p_source_customer_id
   LIMIT 1;

  IF v_musteri IS NULL THEN
    INSERT INTO core.customer (identity_status, match_method, match_confidence)
    VALUES ('MATCHED', 'source_id', 100)
    RETURNING core.customer.customer_id INTO v_musteri;

    PERFORM core.kimlik_bagla(v_musteri, p_kaynak, p_kaynak_kimlik_tipi,
                              p_source_customer_id, p_source_customer_id);
  END IF;

  -- 2) E-posta ----------------------------------------------------------------
  IF p_eposta_ham IS NOT NULL AND btrim(p_eposta_ham) <> '' THEN
    v_eps := core.kimlik_bagla(v_musteri, p_kaynak, 'email', p_eposta_ham, p_source_customer_id);
  END IF;

  -- 3) Telefon ----------------------------------------------------------------
  IF p_telefon_ham IS NOT NULL AND btrim(p_telefon_ham) <> '' THEN
    v_tel := core.kimlik_bagla(v_musteri, p_kaynak, 'phone', p_telefon_ham, p_source_customer_id);
  END IF;

  RETURN QUERY SELECT v_musteri, v_tel, v_eps;
END;
$$;

COMMENT ON FUNCTION core.kaynak_musteri_ekle(text,text,text,text,text) IS
  'Kaynak sistem musterisini kimlik parcalariyla isler. Tekrar calistirilabilir.';

-- Ilk tasarimdaki hatali fonksiyon kaldirilir (imzasi farkli oldugu icin
-- ayrica DROP gerekiyor; birakilirsa yanlislikla cagrilabilir).
DROP FUNCTION IF EXISTS core.kimlik_ekle(text,text,text,text,bigint);

COMMIT;
