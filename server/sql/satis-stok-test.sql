-- =============================================================================
-- K1/K2/K3 davranis testi (15.11.2026). BEGIN ... ROLLBACK: hicbir sey kalmaz.
-- Calistir: docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -f - < satis-stok-test.sql
-- Basarisiz test EXCEPTION atar; sonda 'SATIS-STOK TESTI: n/n GECTI' yazar.
-- =============================================================================
BEGIN;
CREATE TEMP TABLE t_sonuc (ad text, gecti boolean) ON COMMIT DROP;

-- Sentetik veri ----------------------------------------------------------------
-- (1) Trendyol: alici (odenen 600, liste 1000) + nobetci ayni siparis IKI paket satiri (liste 1000)
INSERT INTO core.alici_siparis (kanal, siparis_no, zaman, durum, tutar, liste_tutar, kalemler)
VALUES ('trendyol', 'TEST-K1A', now(), 'Delivered', 600, 1000,
        '[{"kod":"VIREON","adet":1,"tutar":600,"barkod":"8684869609110"}]');
INSERT INTO core.pazaryeri_siparis (kanal, siparis_no, paket_no, durum, siparis_zamani, tutar, kalemler)
VALUES ('trendyol', 'TEST-K1A', 'P1', 'Delivered', now(), 1000, '[{"ad":"Vireon","adet":1,"barkod":"8684869609110"}]'),
       ('trendyol', 'TEST-K1A', NULL, 'Delivered', now(), 1000, '[{"ad":"Vireon","adet":1,"barkod":"8684869609110"}]');
-- (2) Trendyol yalniz nobetcide (liste fiyati) -> ciro NULL
INSERT INTO core.pazaryeri_siparis (kanal, siparis_no, paket_no, durum, siparis_zamani, tutar, kalemler)
VALUES ('trendyol', 'TEST-K1B', 'P2', 'Created', now(), 1500, '[{"ad":"Hydravie","adet":1,"barkod":"8684869609233"}]');
-- (3) iptal edilmis Idefix siparisi
INSERT INTO core.alici_siparis (kanal, siparis_no, zaman, durum, tutar, liste_tutar, kalemler)
VALUES ('idefix', 'TEST-K1C', now(), 'cancelled', 900, 900,
        '[{"kod":"LIPVORA","adet":1,"tutar":900,"barkod":"8684869609134"}]');
-- (4) n11 siparisi: komisyon tablosunda n11 yok -> VERI_YOK
INSERT INTO core.alici_siparis (kanal, siparis_no, zaman, durum, tutar, liste_tutar, kalemler)
VALUES ('n11', 'TEST-K1D', now(), 'Delivered', 1200, 1200,
        '[{"kod":"SUNACNEA","adet":1,"tutar":1200,"barkod":"8684869609097"}]');
-- (5) L'CARLIE disi urun (klinik Schussler) -> girmez
INSERT INTO core.alici_siparis (kanal, siparis_no, zaman, durum, tutar, liste_tutar, kalemler)
VALUES ('trendyol', 'TEST-K1E', now(), 'Delivered', 1175, 1500,
        '[{"kod":"SCHUSSLER","adet":1,"tutar":1175,"barkod":"VST8680474330081"}]');
-- (5b) Wix: gunluk cekime girmemis siparis (alici_siparis), tek kalem
INSERT INTO core.alici_siparis (kanal, siparis_no, zaman, durum, tutar, liste_tutar, kalemler)
VALUES ('wix', 'TEST-W1', now(), 'PAID', 1470, 1470,
        '[{"kod":"BABYSOFT","adet":1,"tutar":0.0,"barkod":"8684869609523"}]');
-- (6) stok: VIREON icin yeni fiziksel sayim 100, sonra TEST-K1A (1 adet) -> 99
INSERT INTO core.stok_sayim (urun_adi, adet, nerede, giren, sayim_zamani, not_metni)
VALUES ('VIREON FOR MEN · Erkek Bakım Kremi', 100, 'DEPO', 'TEST', now() - interval '1 hour', 'test');
INSERT INTO core.stok_sayim (urun_adi, adet, nerede, giren, sayim_zamani, not_metni)
VALUES ('BOYLE BIR URUN YOK', 5, 'DEPO', 'TEST', now() - interval '1 hour', 'test');

-- Testler ------------------------------------------------------------------------
INSERT INTO t_sonuc SELECT 'tekrar_yok: (kanal,siparis,sira) tekil',
  (SELECT count(*) = count(DISTINCT (kanal, siparis_no, sira)) FROM mart.satis_kalem_tum);
INSERT INTO t_sonuc SELECT 'tek_kaynak: her siparis tek kaynaktan',
  NOT EXISTS (SELECT 1 FROM mart.satis_kalem_tum GROUP BY kanal, siparis_no HAVING count(DISTINCT kaynak) > 1);
INSERT INTO t_sonuc SELECT 'cift_sayim_yok: TEST-K1A 3 kaynakta, 1 satir, odenen 600',
  (SELECT count(*) = 1 AND sum(satir_ciro) = 600 AND min(kaynak) = 'ALICI_SIPARIS'
     FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1A');
INSERT INTO t_sonuc SELECT 'liste_fiyati_ciro_degil: TEST-K1B ciro NULL',
  (SELECT count(*) = 1 AND bool_and(satir_ciro IS NULL) AND min(tutar_kaynagi) = 'LISTE_FIYATI_KULLANILMADI'
     FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1B');
INSERT INTO t_sonuc SELECT 'liste_fiyati_kritik_eksik: siparis_ekonomi gercek_tutar',
  (SELECT 'gercek_tutar(liste fiyati kullanilmadi)' = ANY(kritik_eksik) FROM mart.siparis_ekonomi WHERE siparis_id = 'trendyol:TEST-K1B');
INSERT INTO t_sonuc SELECT 'iptal_disarida: TEST-K1C kanal gunlukte yok',
  (SELECT ciro_sinifi = 'IPTAL' FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1C')
  AND NOT EXISTS (SELECT 1 FROM mart.satis_urun_gunluk WHERE kanal = 'idefix' AND gun = current_date AND kod = 'LIPVORA'
                   AND ciro >= 900);
INSERT INTO t_sonuc SELECT 'komisyon_uydurulmaz: n11 VERI_YOK',
  (SELECT kanal_komisyonu IS NULL AND komisyon_durumu = 'VERI_YOK' FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1D')
  AND (SELECT 'kanal_komisyonu(VERI_YOK)' = ANY(kritik_eksik) FROM mart.siparis_ekonomi WHERE siparis_id = 'n11:TEST-K1D');
INSERT INTO t_sonuc SELECT 'komisyon_odenen_uzerinden: trendyol VIREON 600 x %',
  (SELECT k.kanal_komisyonu = round(600 * p.komisyon_yuzde / 100.0, 2)
     FROM mart.satis_kalem_tum k JOIN core.urun_platform_komisyon p ON p.urun_id = k.urun_id AND p.platform_kod = 'trendyol'
    WHERE k.siparis_no = 'TEST-K1A');
INSERT INTO t_sonuc SELECT 'kdv_ayrimi: net = odenen / 1,20',
  (SELECT satir_ciro_net = 500 FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1A');
INSERT INTO t_sonuc SELECT 'maliyet_finans: birim maliyet core.maliyet_bul',
  (SELECT birim_maliyet = core.maliyet_bul(urun_id, olusturma) AND birim_maliyet IS NOT NULL
     FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1A');
INSERT INTO t_sonuc SELECT 'lcarlie_disi_girmez: Schussler',
  NOT EXISTS (SELECT 1 FROM mart.satis_kalem_tum WHERE siparis_no = 'TEST-K1E');
INSERT INTO t_sonuc SELECT 'finans_lemos_girmez: business=lemos satiri yok',
  NOT EXISTS (SELECT 1 FROM mart.satis_kalem_tum k JOIN core.jarvis_channel_sale c
               ON c.channel = 'trendyol' AND c.order_no = k.siparis_no WHERE c.business = 'lemos' AND c.kind = 'sale'
               AND NOT EXISTS (SELECT 1 FROM core.jarvis_channel_sale c2 WHERE c2.order_no = c.order_no AND c2.business = 'lcarlie'));
INSERT INTO t_sonuc SELECT 'wix_kopyalanmaz: cekilmis Wix siparisi alici_siparis''ten tekrar gelmez',
  NOT EXISTS (SELECT 1 FROM mart.satis_kalem_tum k WHERE k.kanal = 'wix' AND k.kaynak <> 'WIX_API'
               AND EXISTS (SELECT 1 FROM raw.wix_order w WHERE w.siparis_no::text = k.siparis_no))
  AND (SELECT count(*) = 1 AND min(kaynak) = 'ALICI_SIPARIS' AND sum(satir_ciro) = 1470
         AND bool_and(odeme_komisyon_yuzde IS NULL)
         FROM mart.satis_kalem_tum WHERE kanal = 'wix' AND siparis_no = 'TEST-W1')
  AND EXISTS (SELECT 1 FROM mart.siparis_ekonomi WHERE siparis_id = 'wix:TEST-W1' AND kanal = 'wix'
              AND 'odeme_komisyonu' = ANY(kritik_eksik));
INSERT INTO t_sonuc SELECT 'K6_pos: PayTR %5, havale 0',
  (SELECT bool_and(odeme_komisyon_yuzde = 5) FROM mart.satis_kalem_tum WHERE kanal = 'wix' AND odeme_yontemi = 'PayTR')
  AND (SELECT bool_and(odeme_komisyon_yuzde = 0) FROM mart.satis_kalem_tum WHERE kanal = 'wix' AND odeme_yontemi <> 'PayTR');
INSERT INTO t_sonuc SELECT 'tazelik: son_olcum alici_siparis',
  (SELECT son_olcum = (SELECT max(guncellendi) FROM core.alici_siparis) FROM mart.satis_tazelik);
INSERT INTO t_sonuc SELECT 'zincir: urun_karlilik ciro = satis_kalem_tum gerceklesen',
  (SELECT sum(ciro) FROM mart.urun_karlilik)
  = (SELECT sum(satir_ciro) FROM mart.satis_kalem_tum WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS'));
INSERT INTO t_sonuc SELECT 'zincir: siparis_ekonomi pazaryeri siparisi var',
  EXISTS (SELECT 1 FROM mart.siparis_ekonomi WHERE siparis_id = 'trendyol:TEST-K1A' AND kanal = 'trendyol'
          AND gelir_durumu = 'REALIZED' AND net_ciro_kdv_haric = 500);
INSERT INTO t_sonuc SELECT 'zincir: ekonomi_gunluk bugun pazaryeri net >= 500',
  (SELECT pazaryeri_net_ciro >= 500 FROM mart.ekonomi_gunluk WHERE gun = current_date);
INSERT INTO t_sonuc SELECT 'pazaryeri_kargo_kritik: VERI_YOK yaziliyor',
  (SELECT 'giden_kargo(pazaryeri kesintisi VERI_YOK)' = ANY(kritik_eksik) FROM mart.siparis_ekonomi WHERE siparis_id = 'trendyol:TEST-K1A');
INSERT INTO t_sonuc SELECT 'ad_eslesme: Turkce/bosluklu adlar',
  core.urun_id_ad('KINESIS + (Sporcu Bakım Kremi)') = (SELECT urun_id FROM core.urun_kimlik WHERE urun_kod = 'KINESIS+')
  AND core.urun_id_ad('Seralımbo (gece Bakım Kremi)') = (SELECT urun_id FROM core.urun_kimlik WHERE urun_kod = 'SERALIMBO')
  AND core.urun_id_ad('Cal Jaw') = (SELECT urun_id FROM core.urun_kimlik WHERE urun_kod = 'CALJAW')
  AND core.urun_id_ad('Viren Femisia Tester Paketi') IS NULL;
INSERT INTO t_sonuc SELECT 'stok: sayim 100 - sonraki satis 1 = 99',
  (SELECT hesaplanan_stok = 99 AND sayim_turu = 'FIZIKSEL_SAYIM' FROM core.stok_guncel WHERE urun_kod = 'VIREON');
INSERT INTO t_sonuc SELECT 'stok: eslesmeyen sayim listelenir',
  EXISTS (SELECT 1 FROM core.stok_tutarsizlik WHERE urun_kod = 'BOYLE BIR URUN YOK' AND bulgu LIKE 'SAYIM_ADI_ESLESMEDI%');
INSERT INTO t_sonuc SELECT 'stok: 36 urun, hepsi bir kaynak yaziyor',
  (SELECT count(*) = (SELECT count(*) FROM core.urun_kimlik) AND bool_and(kaynak IS NOT NULL) FROM core.stok_guncel);
INSERT INTO t_sonuc SELECT 'K3 DORSIVIA: barkod 9400 (Wix), eslesme 9400',
  (SELECT barkod = '8684869609400' AND notlar LIKE 'sahip 15.11: Wix degeri esas%' FROM core.urun_kimlik WHERE urun_kod = 'DORSIVIA')
  AND core.urun_id_barkod('8684869609400') = (SELECT urun_id FROM core.urun_kimlik WHERE urun_kod = 'DORSIVIA')
  AND NOT EXISTS (SELECT 1 FROM core.urun_kimlik_denetim WHERE anahtar = 'Dorsivia');
INSERT INTO t_sonuc SELECT 'panel_rolu: jarvis_web yeni gorunumleri okuyabilir',
  has_table_privilege('jarvis_web', 'mart.satis_urun_gunluk', 'SELECT')
  AND has_table_privilege('jarvis_web', 'mart.satis_kanal_gunluk', 'SELECT')
  AND has_table_privilege('jarvis_web', 'mart.satis_tazelik', 'SELECT')
  AND has_table_privilege('jarvis_web', 'core.stok_guncel', 'SELECT');

DO $$
DECLARE r record; n int; g int;
BEGIN
  SELECT count(*), count(*) FILTER (WHERE gecti) INTO n, g FROM t_sonuc;
  FOR r IN SELECT * FROM t_sonuc WHERE gecti IS NOT TRUE LOOP
    RAISE WARNING 'KALDI: %', r.ad;
  END LOOP;
  IF g < n THEN RAISE EXCEPTION 'SATIS-STOK TESTI: %/% GECTI', g, n; END IF;
  RAISE NOTICE 'SATIS-STOK TESTI: %/% GECTI', g, n;
END $$;
ROLLBACK;
