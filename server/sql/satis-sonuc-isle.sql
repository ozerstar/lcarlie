-- Gönderilen cevapların SONUCUNU işaretler: müşteri tekrar yazdı mı.
--
-- NEDEN AYRI BİR BETİK (jarvis içinde değil)
-- Bu bir YAZMA işi. `ai_reader` yalnız okur ve öyle kalmalı; sınırı delmek
-- yerine yazma, uygulamanın kendi kimliğiyle burada yapılıyor. Jarvis bu
-- tablonun yalnız `mart.satis_kohort` görünümünü okuyor.
--
-- 🔴 PENCERE KURALI
-- Cevabın üstünden yeterli süre geçmeden "dönüş yok" denemez: müşteri 6
-- saat sonra da yazabilir. Bu yüzden üç durum var, iki değil:
--   DONUS_VAR    cevaptan sonra müşteri mesajı GELDİ
--   DONUS_YOK    gelmedi VE pencere kapandı
--   PENCERE_ACIK gelmedi AMA henüz erken -- karar YOK
-- Oran yalnız ilk ikisinden hesaplanır; `PENCERE_ACIK` paydaya girerse oran
-- olduğundan düşük görünür ve boş yere üslup değiştirilir.
--
-- Pencere 24 saat: Meta'nın standart mesajlaşma penceresiyle aynı, yani
-- konuşmanın zaten canlı sayıldığı süre.
--
-- Tekrar çalıştırmak güvenlidir (idempotent): karar verilmiş kayda
-- dokunmaz, yalnız UNKNOWN ve PENCERE_ACIK olanları tazeler.

\set ON_ERROR_STOP on
\set pencere_saat 24

BEGIN;

WITH aday AS (
  SELECT c.id, c.konusma_id, c.gonderim_zamani
  FROM lcarlie.satis_cevap c
  WHERE c.gonderildi
    AND c.gonderim_zamani IS NOT NULL
    AND c.sonuc IN ('UNKNOWN', 'PENCERE_ACIK')
),
donus AS (
  SELECT a.id,
         a.gonderim_zamani,
         (SELECT min(m.zaman)
            FROM lcarlie.mesaj m
           WHERE m.konusma_id = a.konusma_id
             AND m.gonderen = 'musteri'
             AND m.zaman > a.gonderim_zamani) AS ilk_donus
  FROM aday a
)
UPDATE lcarlie.satis_cevap c
   SET donus_zamani = d.ilk_donus,
       donus_sn = CASE WHEN d.ilk_donus IS NOT NULL
                       THEN extract(epoch FROM d.ilk_donus - d.gonderim_zamani)::int
                  END,
       sonuc = CASE
                 WHEN d.ilk_donus IS NOT NULL THEN 'DONUS_VAR'
                 WHEN now() - d.gonderim_zamani
                      > (:'pencere_saat' || ' hours')::interval THEN 'DONUS_YOK'
                 ELSE 'PENCERE_ACIK'
               END
  FROM donus d
 WHERE c.id = d.id
   -- IS DISTINCT FROM: NULL'lu karşılaştırma sessizce false dönüp satırı
   -- atlardı; bu tuzak projede daha önce yaşandı (CR-008).
   AND (c.sonuc IS DISTINCT FROM
        CASE WHEN d.ilk_donus IS NOT NULL THEN 'DONUS_VAR'
             WHEN now() - d.gonderim_zamani
                  > (:'pencere_saat' || ' hours')::interval THEN 'DONUS_YOK'
             ELSE 'PENCERE_ACIK' END
        OR c.donus_zamani IS DISTINCT FROM d.ilk_donus);

COMMIT;

\echo '--- sonuc dagilimi ---'
SELECT sonuc, count(*) FROM lcarlie.satis_cevap GROUP BY sonuc ORDER BY 2 DESC;
