-- =============================================================================
-- L'CARLIE - KARAR SURE DOLUMU  (03.11.2026)
--
-- 🔴 NEDEN: core.karar'da 12 oneri PROPOSED bekliyordu, en eskisi 18.09.
--    Dokuzu ayni "reklam harcamasi ciroyu asiyor" tavsiyesinin farkli
--    gunlerde uretilmis kopyasiydi ve dayandiklari kanit (harcama) artik
--    sifir. Kimse karar vermedigi icin kuyruk eriyordu ama hic bosalmiyordu;
--    sahibin onay yukunu sisiriyor, yeni ve gecerli oneriyi gomuyordu.
--
-- 🔴 SILMEZ. Durum CANCELLED olur ve gecersizlik_nedeni yazilir; satir,
--    kanit baglantisi ve tarihce yerinde kalir. karar_gecis_kontrol()
--    PROPOSED -> CANCELLED gecisine insan kaydi istemez (ustunu_al ile ayni yol).
--
-- 🔴 YALNIZ PROPOSED. APPROVED/DEFERRED/EXECUTED olana dokunulmaz:
--    sahibin bilincli olarak beklettigi (DEFERRED) karar sure dolumuyla
--    kapanmaz.
--
-- Kullanim:  SELECT core.karar_suresi_doldu();        -- varsayilan 14 gun
--            SELECT core.karar_suresi_doldu(30);
-- =============================================================================
CREATE OR REPLACE FUNCTION core.karar_suresi_doldu(p_gun integer DEFAULT 14)
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
DECLARE n integer;
BEGIN
  IF p_gun IS NULL OR p_gun < 7 THEN
    RAISE EXCEPTION 'p_gun en az 7 olmali (verilen: %)', p_gun;
  END IF;
  UPDATE core.karar
     SET durum = 'CANCELLED',
         gecersizlik_nedeni = format(
           'SURESI_DOLDU: %s gun icinde karar verilmedi; kanit anlik goruntusu bayatladi. '
           'Gerekirse ayni oneri guncel kanitla yeniden uretilir.', p_gun)
   WHERE durum = 'PROPOSED'
     AND fixture = false
     AND olusturma < clock_timestamp() - make_interval(days => p_gun);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $function$;
