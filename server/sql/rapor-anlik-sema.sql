-- =============================================================================
-- L'CARLIE - GUNLUK ANLIK GORUNTU  (CR-012)
--
-- 🔴 NEDEN VAR - bagimsiz denetimin en keskin mimari yakalamasi (16.09.2026):
--
--    mart'in tamami VIEW. Bu "her rakam ham veriden yeniden turetilebilir"
--    demek - guzel. Ama bedeli su: BUGUN marj SQL'ini duzeltince
--    5 EKIM'IN MARJI DA GERIYE DONUK DEGISIR.
--
--    Analiz icin dogru, karar hesabi icin yikici:
--      "5 Ekim'de sistem bana NE SOYLEDI ve ben o bilgiyle hangi karari
--       verdim?"  ->  bugunku view bunu cevaplayamaz.
--
--    Bu tam olarak bugun yasandi: KDV hatasi duzeltilince gecmis tum
--    gunlerin marji degisti. Duzeltme dogruydu; ama duzeltmeden ONCE
--    ekranda ne yazdigi hicbir yerde kayitli degildi.
--
-- 🔴 COZUM MART'I TABLOYA CEVIRMEK DEGIL. mart view kalir.
--    Yanina gunde TEK SATIR kayit dusulur: o gun ekranda ne yaziyordu,
--    hangi kod surumuyle, hangi kapsama durumunda.
--
-- 🔴 BU TABLO ASLA GUNCELLENMEZ, YALNIZ EKLENIR.  Gecmisi duzeltmek
--    "gecmiste ne bildigimizi" yok etmek olur - tablonun tek varlik
--    sebebi budur. Ayni gun icin ikinci kayit gelirse YENI SATIR olur
--    (calisma_no artar), eskisi durur.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS core.rapor_anlik (
  kayit_id        bigserial PRIMARY KEY,
  rapor_gunu      date        NOT NULL,
  calisma_no      int         NOT NULL,     -- ayni gun icindeki kacinci kosum
  yazildi         timestamptz NOT NULL DEFAULT clock_timestamp(),

  -- 🔴 METRIK SURUMU: hesap mantigi degistiginde ELLE artirilir.
  --    Boylece iki satirin karsilastirilabilir olup olmadigi bilinir.
  --    Surum ayni degilse iki gunun marji YAN YANA KONMAZ.
  metrik_surumu   text        NOT NULL,

  -- Girdilerin tazeligi ve kapsama durumu - rakamin baglami
  karar_hazir     boolean,
  eksikler        text,
  kapsama_json    jsonb,

  -- 🔴 Rakamlar JSONB: sema degistiginde eski satirlar BOZULMAZ.
  --    Sabit kolon olsaydi yeni metrik eklendiginde gecmis satirlara
  --    NULL yazmak gerekirdi ve "o gun olculmedi" ile "o gun 0'di"
  --    ayirt edilemezdi.
  metrikler       jsonb       NOT NULL,

  UNIQUE (rapor_gunu, calisma_no)
);

COMMENT ON TABLE core.rapor_anlik IS
  'Gunde bir satir: o gun ekranda ne yaziyordu. ASLA guncellenmez, yalniz eklenir.';
COMMENT ON COLUMN core.rapor_anlik.metrik_surumu IS
  'Hesap mantigi surumu. Farkli surumdeki iki satirin rakamlari yan yana konmaz.';

-- --------------------------------------------------------------------------
-- Yazma fonksiyonu
-- --------------------------------------------------------------------------
-- 🔴 UPDATE YOK. Ayni gun tekrar calisirsa calisma_no artar.
CREATE OR REPLACE FUNCTION core.anlik_yaz(p_surum text)
RETURNS TABLE (gun date, no int, hazir boolean)
LANGUAGE plpgsql AS $$
DECLARE
  v_gun  date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date;
  v_no   int;
  v_haz  record;
  v_met  jsonb;
  v_kap  jsonb;
BEGIN
  SELECT coalesce(max(calisma_no), 0) + 1 INTO v_no
    FROM core.rapor_anlik WHERE rapor_gunu = v_gun;

  SELECT * INTO v_haz FROM mart.hazirlik_ozet;

  -- Kapsama: neyin ne kadari olculuyor
  SELECT jsonb_build_object(
    'maliyet_kapsama_yuzde', (SELECT round(100.0 * coalesce(sum(satir_ciro_net) FILTER (WHERE maliyeti_biliniyor),0)
                                           / nullif(sum(satir_ciro_net),0), 1)
                                FROM mart.siparis_kalem
                               WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),
    'maliyet_olculmus_urun',  (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='OLCULMUS'),
    'maliyet_tahmin_urun',    (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='TAHMIN'),
    'maliyet_kdv_tabani',     (SELECT coalesce(max(kdv_tabani),'TEYIT_EDILMEDI') FROM mart.maliyet_kalite),
    'reklam_hesap_durumu',    (SELECT current_connection FROM core.source_authority WHERE alan='ad_spend'),
    'gonderi_eslesmeyen',     (SELECT count(*) FROM mart.siparis_para WHERE NOT gonderi_kaydi_var)
  ) INTO v_kap;

  -- 🔴 Olcum penceresi ICINDEKI rakamlar. Pencere acilmadiysa hepsi 0
  --    olur - bu dogrudur ve o gun gercekten oyle gorunuyordu.
  SELECT jsonb_build_object(
    'siparis',            coalesce((SELECT count(*) FROM mart.siparis WHERE olcumde),0),
    'ciro_dogrulanmis',   coalesce((SELECT sum(ciro_dogrulanmis)     FROM mart.siparis WHERE olcumde),0),
    'ciro_beyan',         coalesce((SELECT sum(ciro_beyan_edilmis)   FROM mart.siparis WHERE olcumde),0),
    'ciro_net_dogrulanmis',coalesce((SELECT sum(ciro_dogrulanmis_net) FROM mart.siparis WHERE olcumde),0),
    'ciro_net_beyan',     coalesce((SELECT sum(ciro_beyan_edilmis_net) FROM mart.siparis WHERE olcumde),0),
    'kdv',                coalesce((SELECT sum(kdv) FROM mart.siparis WHERE olcumde
                                     AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),0),
    'teslim_net_satis',   coalesce((SELECT sum(teslim_net_satis) FROM mart.siparis_para WHERE olcumde),0),
    'cod_bekleyen',       coalesce((SELECT sum(cod_bekleyen)     FROM mart.siparis_para WHERE olcumde),0),
    'reklam_harcamasi',   coalesce((SELECT sum(reklam_harcamasi) FROM mart.gunluk_verimlilik),0),
    'brut_marj',          (SELECT sum(brut_marj) FROM mart.siparis_kalem
                            WHERE olcumde AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),
    'acik_is',            coalesce((SELECT count(*) FROM mart.acik_isler),0),
    'cevapsiz_mesaj',     coalesce((SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat > 24),0)
  ) INTO v_met;

  INSERT INTO core.rapor_anlik (rapor_gunu, calisma_no, metrik_surumu,
                                karar_hazir, eksikler, kapsama_json, metrikler)
  VALUES (v_gun, v_no, p_surum, v_haz.karar_hazir, v_haz.eksikler, v_kap, v_met);

  RETURN QUERY SELECT v_gun, v_no, v_haz.karar_hazir;
END $$;

COMMENT ON FUNCTION core.anlik_yaz(text) IS
  'Gunun anlik goruntusunu yazar. Ayni gun tekrar cagrilirsa YENI satir acar, eskisini bozmaz.';

COMMIT;
