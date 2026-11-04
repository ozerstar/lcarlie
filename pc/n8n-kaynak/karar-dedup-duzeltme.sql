-- =============================================================================
-- L'CARLIE - KARAR DEDUP DUZELTMESI  (CR-016 icinde bulunan hata)
--
-- 🔴 HATA: idempotency_key = md5(anlik_id | modul | baslik) idi.
--    anlik_id her brief kosumunda degistigi icin AYNI oneri her hafta
--    YENI karar olarak aciliyordu: 6 karar -> 12 karar.
--    Dedup "ayni kosumda iki kez" durumunu engelliyordu ama asil sorun
--    "ayni oneri her hafta tekrar" idi - CR-016'nin acikca uyardigi hal.
--
-- 🔴 COZUM: anahtar ICERIK tabanli (modul|baslik). Ama "bir daha asla
--    onerilemez" de yanlis olur - durum degisirse yeniden onerilebilmeli.
--    Bu yuzden TAM unique degil, KISMI unique: yalniz ACIK kararlar
--    (PROPOSED/DEFERRED) icin tekillik. Kapanmis bir oneri tekrar gundeme
--    gelebilir; acik olan ikilenemez.
-- =============================================================================

BEGIN;

-- 1) Eski tam-unique kisiti kaldir
ALTER TABLE core.karar DROP CONSTRAINT IF EXISTS karar_idempotency_key_key;

-- 2) Icerik tabanli anahtari yeniden hesapla (anlik_id CIKARILDI)
UPDATE core.karar
   SET idempotency_key = md5(
         CASE WHEN karar_tipi='PRODUCT_PRIORITY' THEN 'URUN'
              WHEN karar_tipi='MEDIA_BUDGET'     THEN 'META'
              ELSE 'KREATIF' END || '|' || oneri)
 WHERE NOT fixture;

-- 3) Duplicate'leri kapat: ayni anahtardan EN ESKI acik kalir, digerleri
--    CANCELLED olur ve hangisinin yerine gectigi YAZILIR.
--    🔴 SILINMEZ - "bu oneriyi bir zamanlar yaptik" bilgisi korunur.
WITH ilk AS (
  SELECT idempotency_key, min(karar_id) AS asil
    FROM core.karar
   WHERE NOT fixture AND durum IN ('PROPOSED','DEFERRED')
   GROUP BY idempotency_key
)
UPDATE core.karar k
   SET durum = 'CANCELLED',
       ustunu_alan = i.asil,
       gecersizlik_nedeni = 'CR-016: ayni oneri farkli kanit anlik goruntusunde tekrar uretildi - '
                            'idempotency anahtari anlik_id icerdigi icin. Asil kayit #' || i.asil
  FROM ilk i
 WHERE k.idempotency_key = i.idempotency_key
   AND k.karar_id <> i.asil
   AND NOT k.fixture
   AND k.durum IN ('PROPOSED','DEFERRED');

-- 4) KISMI UNIQUE: yalniz ACIK kararlar icin tekillik
DROP INDEX IF EXISTS core.karar_acik_tekil;
CREATE UNIQUE INDEX karar_acik_tekil
    ON core.karar (idempotency_key)
 WHERE durum IN ('PROPOSED','DEFERRED') AND NOT fixture;

-- 5) Aday uretecini icerik tabanli anahtara gecir
CREATE OR REPLACE FUNCTION core.karar_adaylari_uret(p_anlik bigint DEFAULT NULL,
                                                    p_fixture boolean DEFAULT false)
RETURNS TABLE (yeni int, atlanan int) LANGUAGE plpgsql AS $$
DECLARE v_anlik bigint; v_yeni int := 0; v_atlanan int := 0; r record; v_key text;
BEGIN
  v_anlik := coalesce(p_anlik, (SELECT max(anlik_id) FROM core.kanit_anlik));
  IF v_anlik IS NULL THEN RAISE EXCEPTION 'Kanit anlik goruntusu yok - aday uretilemez'; END IF;

  -- 🔴 YALNIZ ILK 5 ONERI.  CR-016: "29 maddelik bilgi coplugu uretme".
  --    Siralama mart.karar_oncelik'ten gelir (deterministik puan).
  FOR r IN
    SELECT o.*, a.kanit_sinifi AS anlik_kalitesi, b.bulgu_id AS kaynak_bulgu
      FROM mart.karar_oncelik o
      JOIN core.buyume_bulgu b ON b.bulgu_id = o.bulgu_id
      JOIN core.kanit_anlik a  ON a.anlik_id = b.anlik_id
     WHERE b.anlik_id = v_anlik
     ORDER BY o.puan DESC, o.bulgu_id
     LIMIT 5
  LOOP
    -- 🔴 ICERIK tabanli anahtar: anlik_id YOK. Ayni oneri her hafta
    --    yeniden acilmaz; kapanmissa yeniden onerilebilir (kismi unique).
    v_key := md5(r.modul || '|' || r.baslik);
    BEGIN
      INSERT INTO core.karar (karar_tipi, urun, kanal, oneri, anlik_id, kanit_kalitesi,
                              beklenen_etki, risk, yanlislama_kosulu, idempotency_key, fixture)
      VALUES (CASE r.modul WHEN 'URUN' THEN 'PRODUCT_PRIORITY'
                           WHEN 'META' THEN 'MEDIA_BUDGET'
                           ELSE 'CREATIVE_TEST' END,
              CASE WHEN r.modul='URUN' THEN split_part(r.baslik,' — ',1) END,
              CASE WHEN r.modul='META' THEN 'meta' END,
              r.baslik, v_anlik, r.anlik_kalitesi,
              r.beklenen_etki, r.risk, r.yanlislama, v_key, p_fixture);
      v_yeni := v_yeni + 1;
      INSERT INTO core.karar_kanit (karar_id, bulgu_id)
      VALUES (currval('core.karar_karar_id_seq'), r.kaynak_bulgu);
    EXCEPTION WHEN unique_violation THEN
      v_atlanan := v_atlanan + 1;
    END;
  END LOOP;

  INSERT INTO core.karar_red_team (karar_id, sonuc, itiraz_tipi, gerekce, kanit_referansi)
  SELECT k.karar_id, rt.hukum, rt.baslik, rt.gerekce, 'mart.red_team'
    FROM core.karar k CROSS JOIN mart.red_team rt
   WHERE k.durum IN ('PROPOSED','DEFERRED') AND NOT k.fixture
     AND NOT EXISTS (SELECT 1 FROM core.karar_red_team x
                      WHERE x.karar_id=k.karar_id AND x.itiraz_tipi=rt.baslik);

  RETURN QUERY SELECT v_yeni, v_atlanan;
END $$;

COMMIT;
