-- =============================================================================
-- 037 GERI ALMA
--
-- 🔴 TABLO DUSURULUNCE BEKLEYEN ISLER DE GIDER. Geri almadan once
--    kuyrugun bos oldugunu dogrula:
--      SELECT durum, count(*) FROM core.tarayici_isi GROUP BY 1;
--
-- 🔴 tarayici_worker ROLU DUSURULMEZ. Rolu dusurmek, SSH kapisinin
--    SET ROLE cagrisini hataya dusurur ve PC'deki worker "sebebi
--    anlasilmayan" bir hatayla doner. Rol bos kalir, zararsizdir;
--    gercekten silinecekse elle, worker kaldirildiktan SONRA silinir.
-- =============================================================================

BEGIN;

DROP FUNCTION IF EXISTS core.tarayici_isi_getir(bigint);
DROP FUNCTION IF EXISTS core.tarayici_nabiz_oku();
DROP FUNCTION IF EXISTS core.tarayici_sunulacak(integer);
DROP FUNCTION IF EXISTS core.tarayici_sayim();
DROP FUNCTION IF EXISTS core.tarayici_nabiz_yaz(text,jsonb);
DROP FUNCTION IF EXISTS core.tarayici_isi_sunuldu(bigint,text,text);
DROP FUNCTION IF EXISTS core.tarayici_isi_insan(bigint,uuid,text,text);
DROP FUNCTION IF EXISTS core.tarayici_isi_hata(bigint,uuid,text,text);
DROP FUNCTION IF EXISTS core.tarayici_isi_bitir(bigint,uuid,text,jsonb,text);
DROP FUNCTION IF EXISTS core.tarayici_isi_al(text,integer);
DROP FUNCTION IF EXISTS core.tarayici_isi_ekle(text,text,text,text,jsonb);

DROP TABLE IF EXISTS core.tarayici_nabiz;
DROP TABLE IF EXISTS core.tarayici_isi;

DELETE FROM core.ai_orchestrator_config WHERE config_key = 'tarayici_worker_enabled';

COMMIT;
