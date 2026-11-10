-- saha-sema5 geri alma. TEL_*/ARAMAYIN kaydı varsa kısıt eklenemez ve
-- işlem DURUR -- bu bilerek: geri alma girilmiş görüşme raporunu silmez.
BEGIN;
ALTER TABLE core.saha_ziyaret DROP CONSTRAINT saha_ziyaret_sonuc_check;
ALTER TABLE core.saha_ziyaret ADD CONSTRAINT saha_ziyaret_sonuc_check
  CHECK (sonuc IN ('GORUSULDU', 'KAPALI', 'YETKILI_YOK', 'ILGILENMEDI',
                   'NUMUNE_BIRAKILDI', 'SIPARIS_SOZU', 'TEKRAR_GEL'));
COMMIT;
