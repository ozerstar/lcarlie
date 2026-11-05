-- Tarayici tek is sonucu sorgusu.
BEGIN;
CREATE OR REPLACE FUNCTION core.tarayici_isi_durum(p_is_id bigint)
RETURNS TABLE(is_id bigint, hedef text, durum text, sonuc_metin text,
              sonuc_dosyalari jsonb, hata text, deneme integer)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
  SELECT t.is_id, t.hedef, t.durum, t.sonuc_metin, t.sonuc_dosyalari,
         t.hata, t.deneme
    FROM core.tarayici_isi t WHERE t.is_id = p_is_id;
$fn$;
ALTER FUNCTION core.tarayici_isi_durum(bigint) OWNER TO function_owner;
REVOKE ALL ON FUNCTION core.tarayici_isi_durum(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.tarayici_isi_durum(bigint) TO ai_reader, ai_writer, jarvis_web, human_approver;
COMMIT;
