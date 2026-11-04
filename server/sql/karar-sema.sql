-- =============================================================================
-- L'CARLIE - DECISION MEMORY + OUTCOME LOOP  (CR-015)
--
-- 🔴 AMAC: sistem "tavsiye veren" degil, "ne onerdigini ve SONUCUNU
--    hatirlayan" hale gelsin. CR-014 her kosumda 8 Red Team itirazi
--    uretiyordu ama hicbiri kaydedilmiyordu; yarin ayni itirazlar yeniden
--    uretilecek ve hangisinin dinlendigi bilinmeyecekti.
--
-- 🔴 BU CR HICBIR REKLAM/SITE DEGISIKLIGI YAPMAZ. Yalnizca ne yapildigini
--    KAYDEDECEK mekanizmayi kurar. Aksiyonu insan uygular, sisteme yazar.
--
-- 🔴 AI YOK. Durum makinesi, kimlik, dedup, uygunluk ve hesaplarin tamami
--    deterministik SQL. AI hicbir state yonetmez.
--
-- 🔴 PII GIRMEZ. Musteri mesaji, ad, telefon, e-posta bu semaya YAZILMAZ;
--    yalniz anonim toplu kanit referansi (anlik_id, bulgu_id) tutulur.
-- =============================================================================

BEGIN;

-- 🔴 CR-014'te yer tutucu olarak acilan duz tablo BIRAKILIYOR.
--    Bos (0 satir) oldugu dogrulandi; normalize sema onun yerine geciyor.
--    Bos olmayan bir tabloyu boyle dusurmek VERI KAYBI olurdu - once sayildi.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
              WHERE table_schema='core' AND table_name='karar_kaydi') THEN
    IF (SELECT count(*) FROM core.karar_kaydi) > 0 THEN
      RAISE EXCEPTION 'core.karar_kaydi BOS DEGIL - elle tasima gerekir, otomatik dusurulmedi';
    END IF;
    DROP TABLE core.karar_kaydi;
  END IF;
END $$;

-- ===========================================================================
-- 1) KARAR  (decision)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS core.karar (
  karar_id         bigserial PRIMARY KEY,
  olusturma        timestamptz NOT NULL DEFAULT clock_timestamp(),
  karar_tipi       text NOT NULL CHECK (karar_tipi IN (
                     'PRODUCT_PRIORITY','MEDIA_BUDGET','OFFER_TEST','CREATIVE_TEST',
                     'CRO_CHANGE','AUDIENCE_TEST','CRM_ACTION')),
  urun             text,
  kanal            text,
  oneri            text NOT NULL,
  -- 🔴 KANIT DEGISMEZLIGI: karar, verildigi ANDAKI anlik goruntuye baglanir.
  --    Sonraki ETL eski kararin kanitini yeniden yazamaz - kanit_anlik
  --    append-only ve buradaki FK o satiri isaret eder.
  anlik_id         bigint NOT NULL REFERENCES core.kanit_anlik(anlik_id),
  kanit_kalitesi   text NOT NULL CHECK (kanit_kalitesi IN ('LOW','MEDIUM','HIGH')),
  beklenen_etki    text,
  risk             text,
  -- 🔴 YANLISLAMA ZORUNLU. Curutulemeyen bir oneri, oneri degil inanctir.
  yanlislama_kosulu text NOT NULL,
  durum            text NOT NULL DEFAULT 'PROPOSED' CHECK (durum IN (
                     'PROPOSED','APPROVED','REJECTED','DEFERRED',
                     'EXECUTED','MEASURING','CONCLUDED','CANCELLED')),
  -- 🔴 IDEMPOTENCY: ayni (anlik, modul, oneri) ikinci kez islenirse yeni
  --    karar ACILMAZ. Gunluk brief ayni 29 bulguyu her gun uretse bile
  --    karar tablosu sismez.
  idempotency_key  text NOT NULL UNIQUE,
  -- 🔴 TEST FIXTURE ISARETI: uretim gorunumleri bunu DISLAR.
  fixture          boolean NOT NULL DEFAULT false,
  guncelleme       timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS karar_durum_idx ON core.karar (durum, fixture);
COMMENT ON TABLE core.karar IS
  'Karar kaydi. anlik_id ile kanit DONDURULUR; idempotency_key duplicate engeller.';

-- ===========================================================================
-- 2) KARAR KANITI  (decision_evidence)
-- ===========================================================================
-- 🔴 Kararin dayandigi BULGU satirlari. Kanit metni burada TEKRAR
--    YAZILMAZ; bulgu_id ile isaret edilir - tek kaynak ilkesi.
CREATE TABLE IF NOT EXISTS core.karar_kanit (
  karar_id  bigint NOT NULL REFERENCES core.karar(karar_id) ON DELETE CASCADE,
  bulgu_id  bigint NOT NULL REFERENCES core.buyume_bulgu(bulgu_id) ON DELETE RESTRICT,
  PRIMARY KEY (karar_id, bulgu_id)
);

-- ===========================================================================
-- 3) RED TEAM HAFIZASI  (decision_review)
-- ===========================================================================
-- 🔴 RED TEAM ONERIYI EZMEZ. Ayri tablo, ayri satir. Analyst ne dediyse
--    core.karar'da durur; itiraz burada durur. Ikisi birlikte okunur.
CREATE TABLE IF NOT EXISTS core.karar_red_team (
  inceleme_id  bigserial PRIMARY KEY,
  karar_id     bigint NOT NULL REFERENCES core.karar(karar_id) ON DELETE CASCADE,
  sonuc        text NOT NULL CHECK (sonuc IN ('SUPPORT','CHALLENGE','INSUFFICIENT_EVIDENCE')),
  itiraz_tipi  text,     -- ATIF | KAPSAMA | ORNEKLEM | FINANSAL | OPERASYON | MEVZUAT | ALTERNATIF | MALIYET
  gerekce      text NOT NULL,
  kanit_referansi text,  -- hangi view/tablo/sayi
  olusturma    timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS karar_rt_idx ON core.karar_red_team (karar_id, sonuc);

-- ===========================================================================
-- 4) INSAN KARARI  (human decision)
-- ===========================================================================
-- 🔴 AYRI TABLO ve ZORUNLU. Sistem kendi kendine APPROVED yazamaz;
--    durum gecisi tetikleyicisi bu tabloda kayit arar.
CREATE TABLE IF NOT EXISTS core.karar_insan (
  karar_id     bigint PRIMARY KEY REFERENCES core.karar(karar_id) ON DELETE CASCADE,
  karar        text NOT NULL CHECK (karar IN ('APPROVE','REJECT','DEFER','MODIFY')),
  karar_zamani timestamptz NOT NULL DEFAULT clock_timestamp(),
  karar_notu   text,
  onaylayan    text NOT NULL
);

-- ===========================================================================
-- 5) AKSIYON LOGU  (action log)
-- ===========================================================================
-- 🔴 SISTEM AKSIYON UYGULAMAZ - yalnizca insanin yaptigini KAYDEDER.
CREATE TABLE IF NOT EXISTS core.karar_aksiyon (
  aksiyon_id     bigserial PRIMARY KEY,
  karar_id       bigint NOT NULL REFERENCES core.karar(karar_id) ON DELETE CASCADE,
  aksiyon_tipi   text NOT NULL CHECK (aksiyon_tipi IN (
                   'budget_changed','campaign_paused','campaign_launched','creative_launched',
                   'landing_page_changed','offer_changed','price_changed','crm_message_sent',
                   'no_action')),
  aciklama       text NOT NULL,
  uygulandi      timestamptz NOT NULL DEFAULT clock_timestamp(),
  uygulayan      text NOT NULL,
  dis_referans   text,      -- Meta kampanya id, Wix sayfa vb.
  onceki_durum   text,
  sonraki_durum  text
);
CREATE INDEX IF NOT EXISTS karar_aksiyon_idx ON core.karar_aksiyon (karar_id);

-- ===========================================================================
-- 6) SONUC  (outcome)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS core.karar_sonuc (
  karar_id          bigint PRIMARY KEY REFERENCES core.karar(karar_id) ON DELETE CASCADE,
  olcum_baslangic   date,
  olcum_bitis       date,
  ana_metrik        text NOT NULL,
  baz_deger         numeric,
  gozlenen_deger    numeric,
  mutlak_degisim    numeric GENERATED ALWAYS AS (gozlenen_deger - baz_deger) STORED,
  goreli_degisim    numeric,
  -- 🔴 VERI KALITESI cikis kodu sozlesmesiyle AYNI dili konusur.
  --    0 gozlem SUCCESS DEGILDIR; eksik kaynak HEALTHY DEGILDIR.
  veri_kalitesi     text NOT NULL CHECK (veri_kalitesi IN ('SUCCESS','NO_DATA','PARTIAL','FAILED')),
  orneklem          int,
  sonuc_durumu      text NOT NULL CHECK (sonuc_durumu IN (
                      'POSITIVE','NEGATIVE','INCONCLUSIVE','NOT_MEASURABLE')),
  -- 🔴 YANLISLANDI MI: kanit yetmiyorsa 'unknown'. Zorla true/false yok.
  yanlislandi       text NOT NULL DEFAULT 'unknown' CHECK (yanlislandi IN ('true','false','unknown')),
  uygunluk_gerekcesi text,
  kapatan           text,
  kapanis           timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- ===========================================================================
-- 7) DURUM GECIS TETIKLEYICISI
-- ===========================================================================
-- 🔴 EN KRITIK KURAL: INSAN ONAYI OLMADAN 'EXECUTED' OLAMAZ.
--    Bu bir uygulama katmani sozu degil, VERITABANI KISITI - koda
--    guvenmek yeterli degil, cunku kodu baska biri degistirebilir.
CREATE OR REPLACE FUNCTION core.karar_gecis_kontrol()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.durum IS DISTINCT FROM OLD.durum THEN
    -- Insan karari gerektiren gecisler
    IF NEW.durum IN ('APPROVED','REJECTED','DEFERRED') THEN
      IF NOT EXISTS (SELECT 1 FROM core.karar_insan i WHERE i.karar_id = NEW.karar_id) THEN
        RAISE EXCEPTION 'Karar #%: insan karari kaydedilmeden durum % olamaz',
          NEW.karar_id, NEW.durum;
      END IF;
    END IF;
    IF NEW.durum IN ('EXECUTED','MEASURING','CONCLUDED') THEN
      IF NOT EXISTS (SELECT 1 FROM core.karar_insan i
                      WHERE i.karar_id = NEW.karar_id AND i.karar IN ('APPROVE','MODIFY')) THEN
        RAISE EXCEPTION 'Karar #%: insan ONAYI (APPROVE/MODIFY) olmadan durum % olamaz',
          NEW.karar_id, NEW.durum;
      END IF;
    END IF;
    -- 🔴 EXECUTED icin aksiyon kaydi da sart: "yapildi" diyorsak NE yapildigi yazili olmali.
    IF NEW.durum = 'EXECUTED' AND NOT EXISTS
         (SELECT 1 FROM core.karar_aksiyon a WHERE a.karar_id = NEW.karar_id) THEN
      RAISE EXCEPTION 'Karar #%: aksiyon kaydi olmadan EXECUTED olamaz', NEW.karar_id;
    END IF;
    IF NEW.durum = 'CONCLUDED' AND NOT EXISTS
         (SELECT 1 FROM core.karar_sonuc s WHERE s.karar_id = NEW.karar_id) THEN
      RAISE EXCEPTION 'Karar #%: sonuc kaydi olmadan CONCLUDED olamaz', NEW.karar_id;
    END IF;
  END IF;
  NEW.guncelleme := clock_timestamp();
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS karar_gecis ON core.karar;
CREATE TRIGGER karar_gecis BEFORE UPDATE ON core.karar
  FOR EACH ROW EXECUTE FUNCTION core.karar_gecis_kontrol();

-- ===========================================================================
-- 8) KARAR ADAYI URETIMI  (brief -> decision candidate)
-- ===========================================================================
-- 🔴 HER BRIEF SATIRI OTOMATIK KARAR OLMAZ. Yalnizca:
--      - insan_onayi = true
--      - modul oneri niteliginde (URUN / META / KREATIF)
--      - sinif INSUFFICIENT_DATA DEGIL
--    olanlar aday olur. CRO/PAZAR/RED_TEAM satirlari bilgi'dir, oneri degil.
CREATE OR REPLACE FUNCTION core.karar_adaylari_uret(p_anlik bigint DEFAULT NULL,
                                                    p_fixture boolean DEFAULT false)
RETURNS TABLE (yeni int, atlanan int) LANGUAGE plpgsql AS $$
DECLARE v_anlik bigint; v_yeni int := 0; v_atlanan int := 0; r record; v_key text;
BEGIN
  v_anlik := coalesce(p_anlik, (SELECT max(anlik_id) FROM core.kanit_anlik));
  IF v_anlik IS NULL THEN RAISE EXCEPTION 'Kanit anlik goruntusu yok - aday uretilemez'; END IF;

  FOR r IN
    SELECT b.*, a.kanit_sinifi
      FROM core.buyume_bulgu b
      JOIN core.kanit_anlik a ON a.anlik_id = b.anlik_id
     WHERE b.anlik_id = v_anlik
       AND b.modul IN ('URUN','META','KREATIF')
       AND b.insan_onayi
       AND coalesce(b.sinif,'') <> 'INSUFFICIENT_DATA'
       AND b.yanlislama IS NOT NULL
  LOOP
    -- 🔴 Deterministik anahtar: ayni bulgu ikinci kez islenirse ayni key.
    v_key := md5(r.anlik_id::text || '|' || r.modul || '|' || r.baslik);
    BEGIN
      INSERT INTO core.karar (karar_tipi, urun, kanal, oneri, anlik_id, kanit_kalitesi,
                              beklenen_etki, risk, yanlislama_kosulu, idempotency_key, fixture)
      VALUES (CASE r.modul WHEN 'URUN' THEN 'PRODUCT_PRIORITY'
                           WHEN 'META' THEN 'MEDIA_BUDGET'
                           ELSE 'CREATIVE_TEST' END,
              CASE WHEN r.modul='URUN' THEN split_part(r.baslik,' — ',1) END,
              CASE WHEN r.modul='META' THEN 'meta' END,
              r.baslik, r.anlik_id, r.kanit_sinifi,
              r.beklenen_etki, r.risk, r.yanlislama, v_key, p_fixture);
      v_yeni := v_yeni + 1;
      INSERT INTO core.karar_kanit (karar_id, bulgu_id)
      VALUES (currval('core.karar_karar_id_seq'), r.bulgu_id);
    EXCEPTION WHEN unique_violation THEN
      v_atlanan := v_atlanan + 1;   -- ayni oneri zaten var: DUPLICATE ACILMADI
    END;
  END LOOP;

  -- Red Team sonuclari her adaya AYRI kayit olarak baglanir (oneriyi ezmez).
  INSERT INTO core.karar_red_team (karar_id, sonuc, itiraz_tipi, gerekce, kanit_referansi)
  SELECT k.karar_id, rt.hukum, rt.baslik, rt.gerekce, 'mart.red_team'
    FROM core.karar k CROSS JOIN mart.red_team rt
   WHERE k.anlik_id = v_anlik
     AND NOT EXISTS (SELECT 1 FROM core.karar_red_team x
                      WHERE x.karar_id=k.karar_id AND x.itiraz_tipi=rt.baslik);

  RETURN QUERY SELECT v_yeni, v_atlanan;
END $$;

-- ===========================================================================
-- 9) SONUC UYGUNLUK KAPISI
-- ===========================================================================
-- 🔴 KUCUK ORNEKLEMDE SAHTE BASARI/BASARISIZLIK URETILMEZ.
--    Bu fonksiyon "olcebilir miyiz" sorusunu kararin KENDISINDEN bagimsiz,
--    deterministik kurallarla cevaplar. Uygun degilse sonuc NOT_MEASURABLE
--    ya da INCONCLUSIVE olur - POSITIVE/NEGATIVE asla zorlanmaz.
CREATE OR REPLACE FUNCTION core.sonuc_uygun_mu(p_karar bigint)
RETURNS TABLE (uygun boolean, orneklem int, gerekce text) LANGUAGE plpgsql STABLE AS $$
DECLARE v_aksiyon timestamptz; v_gun int; v_orneklem int; v_taze boolean; v_eksik int;
BEGIN
  SELECT min(uygulandi) INTO v_aksiyon FROM core.karar_aksiyon WHERE karar_id = p_karar;
  IF v_aksiyon IS NULL THEN
    RETURN QUERY SELECT false, 0, 'aksiyon kaydi yok - olculecek bir degisiklik yok'; RETURN;
  END IF;
  v_gun := greatest(0, (clock_timestamp()::date - v_aksiyon::date));
  SELECT coalesce(sum(siparis),0)::int INTO v_orneklem
    FROM mart.nakit_gunluk WHERE gun > v_aksiyon::date;
  SELECT min(son) > now() - interval '30 hours' INTO v_taze
    FROM (SELECT max(bitis) AS son FROM raw.yukleme_log GROUP BY kaynak) t;
  SELECT count(*) INTO v_eksik FROM mart.nakit_veri_kalitesi WHERE durum='MISSING';

  IF v_gun < 7 THEN
    RETURN QUERY SELECT false, v_orneklem,
      format('olcum penceresi cok kisa (%s gun < 7)', v_gun); RETURN;
  END IF;
  IF v_orneklem < 10 THEN
    RETURN QUERY SELECT false, v_orneklem,
      format('orneklem yetersiz (%s siparis < 10) - POSITIVE/NEGATIVE uretilmez', v_orneklem); RETURN;
  END IF;
  IF NOT coalesce(v_taze,false) THEN
    RETURN QUERY SELECT false, v_orneklem, 'veri bayat (ETL 30 saatten eski)'; RETURN;
  END IF;
  IF v_eksik > 5 THEN
    RETURN QUERY SELECT false, v_orneklem,
      format('%s kritik kaynak MISSING - kapsama yetersiz', v_eksik); RETURN;
  END IF;
  RETURN QUERY SELECT true, v_orneklem, 'uygun';
END $$;

COMMENT ON FUNCTION core.sonuc_uygun_mu(bigint) IS
  'Sonuc olculebilir mi? Pencere>=7 gun, orneklem>=10, veri taze, MISSING<=5. '
  'Uygun degilse POSITIVE/NEGATIVE URETILMEZ.';

-- ===========================================================================
-- 10) SONUC KAPATMA
-- ===========================================================================
CREATE OR REPLACE FUNCTION core.karar_sonuclandir(
  p_karar bigint, p_metrik text, p_baz numeric, p_gozlenen numeric, p_kapatan text)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE u record; v_durum text; v_kalite text; v_yanlis text; v_goreli numeric;
BEGIN
  SELECT * INTO u FROM core.sonuc_uygun_mu(p_karar);
  v_goreli := CASE WHEN p_baz IS NULL OR p_baz = 0 THEN NULL
                   ELSE round(100.0*(p_gozlenen-p_baz)/p_baz, 1) END;

  IF NOT u.uygun THEN
    -- 🔴 Uygun degilse yon BELIRTILMEZ.
    v_durum := CASE WHEN u.orneklem = 0 THEN 'NOT_MEASURABLE' ELSE 'INCONCLUSIVE' END;
    v_kalite := CASE WHEN u.orneklem = 0 THEN 'NO_DATA' ELSE 'PARTIAL' END;
    v_yanlis := 'unknown';
  ELSE
    v_durum := CASE WHEN p_gozlenen IS NULL OR p_baz IS NULL THEN 'INCONCLUSIVE'
                    WHEN p_gozlenen > p_baz THEN 'POSITIVE'
                    WHEN p_gozlenen < p_baz THEN 'NEGATIVE'
                    ELSE 'INCONCLUSIVE' END;
    v_kalite := 'SUCCESS';
    v_yanlis := CASE WHEN v_durum='NEGATIVE' THEN 'true'
                     WHEN v_durum='POSITIVE' THEN 'false' ELSE 'unknown' END;
  END IF;

  INSERT INTO core.karar_sonuc (karar_id, olcum_baslangic, olcum_bitis, ana_metrik,
         baz_deger, gozlenen_deger, goreli_degisim, veri_kalitesi, orneklem,
         sonuc_durumu, yanlislandi, uygunluk_gerekcesi, kapatan)
  VALUES (p_karar,
          (SELECT min(uygulandi)::date FROM core.karar_aksiyon WHERE karar_id=p_karar),
          clock_timestamp()::date, p_metrik, p_baz, p_gozlenen, v_goreli,
          v_kalite, u.orneklem, v_durum, v_yanlis, u.gerekce, p_kapatan)
  ON CONFLICT (karar_id) DO UPDATE SET
    gozlenen_deger=EXCLUDED.gozlenen_deger, goreli_degisim=EXCLUDED.goreli_degisim,
    veri_kalitesi=EXCLUDED.veri_kalitesi, orneklem=EXCLUDED.orneklem,
    sonuc_durumu=EXCLUDED.sonuc_durumu, yanlislandi=EXCLUDED.yanlislandi,
    uygunluk_gerekcesi=EXCLUDED.uygunluk_gerekcesi, kapanis=clock_timestamp();

  UPDATE core.karar SET durum='CONCLUDED' WHERE karar_id=p_karar;
  RETURN v_durum;
END $$;

COMMIT;
