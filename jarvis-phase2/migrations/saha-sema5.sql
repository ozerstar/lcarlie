-- SAHA ŞEMA 5: telefon görüşmesi raporları (10.11.2026)
--
-- Ofis ekibi hekimleri arayıp görüşme raporu girecek. Ayrı bir "arama"
-- tablosu açılmadı: bir hedefle yapılan her temas (ziyaret ya da telefon)
-- tek zaman çizgisinde görünsün diye aynı core.saha_ziyaret kullanılır,
-- sonuç değeri TEL_ önekiyle ayrılır.
--
-- ARAMAYIN: kişi aranmak istemedi. Bu sonuçtan sonra hedef aranmaz.
-- Kısıt yalnız GENİŞLER; mevcut hiçbir değer kaldırılmaz.
BEGIN;
ALTER TABLE core.saha_ziyaret DROP CONSTRAINT saha_ziyaret_sonuc_check;
ALTER TABLE core.saha_ziyaret ADD CONSTRAINT saha_ziyaret_sonuc_check
  CHECK (sonuc IN ('GORUSULDU', 'KAPALI', 'YETKILI_YOK', 'ILGILENMEDI',
                   'NUMUNE_BIRAKILDI', 'SIPARIS_SOZU', 'TEKRAR_GEL',
                   'TEL_RANDEVU', 'TEL_TEKRAR_ARA', 'TEL_MAIL', 'TEL_ULASILAMADI',
                   'TEL_ILGILENMEDI', 'ARAMAYIN'));
COMMIT;
