-- =============================================================================
-- urun-maliyet-finans.sql DAVRANIS TESTI (15.11.2026)
-- Her sey BEGIN ... ROLLBACK icinde: veritabaninda iz BIRAKMAZ.
-- Basarisiz olan ilk kontrol RAISE EXCEPTION ile durur.
-- Calistir: docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 < urun-maliyet-finans-test.sql
-- =============================================================================
BEGIN;
DO $$
DECLARE v text; n numeric; r jsonb; v_id text := 'b94c3b37-b362-34af-afba-6f5ecf9decf0'; -- VIREON
        v_eski numeric; v_yeni numeric; v_an timestamptz;
BEGIN
  -- 1) Wix artik kaynak degil: deger ne olursa olsun yazmaz
  v := core.maliyet_guncelle(v_id, 999.99, 'WIX');
  IF v <> 'WIX_KOPYA' THEN RAISE EXCEPTION 'WIX yazabildi: %', v; END IF;
  v := core.maliyet_guncelle(v_id, 0, 'WIX');
  IF v <> 'WIX_KOPYA' THEN RAISE EXCEPTION 'WIX bos degerle kapatabildi: %', v; END IF;

  -- 2) Elle giris finans maliyetini ezemez
  v := core.maliyet_gecmise_don(v_id, 400, '2026-06-01', 'test');
  IF v <> 'KORUNDU_FINANS' THEN RAISE EXCEPTION 'ELLE finansi ezdi: %', v; END IF;

  -- 3) Iptal edilmis 400 TL hicbir tarih icin donmez; gecmis siparis FINANS degeri alir
  SELECT count(*) INTO n FROM core.urun_maliyet WHERE iptal_at IS NULL AND kaynak <> 'FINANS';
  IF n > 0 THEN RAISE EXCEPTION 'gecerli FINANS disi kayit var: %', n; END IF;
  SELECT birim_maliyet_kdv_haric INTO v_eski FROM core.urun_maliyet_guncel WHERE urun_id = v_id;
  IF core.maliyet_bul(v_id, '2026-06-01') IS DISTINCT FROM v_eski THEN
    RAISE EXCEPTION 'gecmis siparis finans degerini almiyor: % <> %', core.maliyet_bul(v_id, '2026-06-01'), v_eski;
  END IF;
  SELECT count(*) INTO n FROM mart.siparis_kalem WHERE birim_maliyet = 400;
  IF n > 0 THEN RAISE EXCEPTION 'siparis_kalem hala 400 TL kullaniyor: % kalem', n; END IF;

  -- 4) Finans merkezinde deger degisirse YENI SURUM; eski siparis eski degerde kalir
  v_an := clock_timestamp();
  r := core.finans_maliyet_yaz(jsonb_build_object('dagitim','esit','urunler', jsonb_build_array(
         jsonb_build_object('product','Vireon','produced',252,'production',1386000,'general',900000,
                            'special',0,'total_cost',2286000,'unit_cost',9071,'unit_production',5500,
                            'first_made','2025-12','sold',87),
         jsonb_build_object('product','Hayalet Urun','produced',10,'production',1000,'general',0,
                            'special',0,'total_cost',1000,'unit_cost',100,'unit_production',100,
                            'first_made','2026-11','sold',0),
         jsonb_build_object('product','Optywave','produced',0,'production',0,'general',0,
                            'special',0,'total_cost',0,'unit_cost',NULL,'unit_production',NULL,
                            'first_made',NULL,'sold',0))));
  IF (r->'sonuc'->>'YENI_SURUM')::int IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'yeni surum acilmadi: %', r; END IF;
  IF NOT (r->'eslesmeyen') ? 'Hayalet Urun' THEN RAISE EXCEPTION 'eslesmeyen ad raporlanmadi: %', r; END IF;
  IF NOT (r->'veri_yok') ? 'Optywave' THEN RAISE EXCEPTION 'VERI_YOK raporlanmadi: %', r; END IF;
  -- (islem icinde now() sabit; yeni surum clock_timestamp() ile acildigi icin o anla sorulur)
  v_yeni := core.maliyet_bul(v_id, clock_timestamp());
  IF v_yeni <> 90.71 THEN RAISE EXCEPTION 'yeni surum gecerli degil: %', v_yeni; END IF;
  IF core.maliyet_bul(v_id, '2026-06-01') IS DISTINCT FROM v_eski THEN
    RAISE EXCEPTION 'yeni surum gecmisi degistirdi';
  END IF;
  -- 5) VERI_YOK eski degeri SILMEZ (Optywave'in finans degeri durur)
  IF (SELECT birim_maliyet_kdv_haric FROM core.urun_maliyet_guncel
       WHERE urun_id = 'cecfe4d9-108f-4aef-4409-7df2849962c5') IS NULL THEN
    RAISE EXCEPTION 'VERI_YOK eski finans degerini sildi';
  END IF;
  -- 6) KDV dahil gosterim = x1,20
  SELECT count(*) INTO n FROM core.urun_maliyet_guncel
   WHERE birim_maliyet_kdv_haric IS NOT NULL
     AND birim_maliyet_kdv_dahil <> round(birim_maliyet_kdv_haric * 1.20, 2);
  IF n > 0 THEN RAISE EXCEPTION 'KDV dahil alan x1,20 degil: % satir', n; END IF;
  -- 7) Durum ayrimi: maliyeti olmayan urunde maliyet NULL, durum VERI_YOK (0 degil)
  SELECT count(*) INTO n FROM core.urun_maliyet_guncel
   WHERE (durum = 'VERI_YOK' AND birim_maliyet_kdv_haric IS NOT NULL)
      OR (durum = 'GIRILDI'  AND birim_maliyet_kdv_haric IS NULL)
      OR birim_maliyet_kdv_haric = 0;
  IF n > 0 THEN RAISE EXCEPTION 'durum/maliyet celiskisi: % satir', n; END IF;
  -- 8) Gecersiz dagitim reddedilir
  BEGIN
    PERFORM core.finans_maliyet_yaz('{"dagitim":"x","urunler":[{"product":"Vireon"}]}');
    RAISE EXCEPTION 'gecersiz dagitim kabul edildi';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM NOT LIKE 'dagitim gecersiz%' THEN RAISE; END IF;
  END;
  RAISE NOTICE 'urun-maliyet-finans testi: 8/8 GECTI';
END $$;
ROLLBACK;
