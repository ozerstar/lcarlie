-- =============================================================================
-- L'CARLIE - DECISION MEMORY GORUNUMLERI  (CR-015)
--
-- 🔴 TUM GORUNUMLER FIXTURE'I DISLAR.  Test senaryolari uretim sayimina
--    KARISMAZ; `fixture=true` satirlar yalniz mart.karar_fixture'da gorunur.
-- 🔴 PII YOK: burada yalniz karar metni, durum ve sayilar var.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.karar_kalibrasyon CASCADE;
DROP VIEW IF EXISTS mart.karar_fixture     CASCADE;
DROP VIEW IF EXISTS mart.karar_son         CASCADE;
DROP VIEW IF EXISTS mart.karar_ozet        CASCADE;

-- ---------------------------------------------------------------------------
-- PANEL OZETI
-- ---------------------------------------------------------------------------
CREATE VIEW mart.karar_ozet AS
SELECT
  count(*) FILTER (WHERE durum NOT IN ('CONCLUDED','CANCELLED','REJECTED'))  AS acik_karar,
  count(*) FILTER (WHERE durum = 'PROPOSED')                                 AS insan_onayi_bekleyen,
  count(*) FILTER (WHERE durum IN ('EXECUTED','MEASURING'))                  AS uygulandi_olculuyor,
  count(*) FILTER (WHERE durum = 'CONCLUDED')                                AS sonuclanan,
  count(*) FILTER (WHERE durum = 'REJECTED')                                 AS reddedilen,
  count(*) FILTER (WHERE durum = 'DEFERRED')                                 AS ertelenen,
  (SELECT count(*) FROM core.karar_sonuc s JOIN core.karar k2 USING (karar_id)
    WHERE NOT k2.fixture AND s.sonuc_durumu IN ('INCONCLUSIVE','NOT_MEASURABLE')) AS sonucsuz,
  -- 🔴 TEKIL ITIRAZ SAYILIR, satir degil.  Her Red Team itirazi her karara
  --    ayri satir olarak baglaniyor; ham satir sayimi 7 itirazi 6 kararda
  --    "42 itiraz" gibi gosteriyordu. Sisik gorunen sayi, okuyani yanlis
  --    yonlendirir - projenin "rakam kendi basina yalan soylememeli"
  --    ilkesinin ihlali olurdu.
  (SELECT count(DISTINCT rt.itiraz_tipi) FROM core.karar_red_team rt
     JOIN core.karar k3 USING (karar_id)
    WHERE NOT k3.fixture AND rt.sonuc='CHALLENGE')                           AS red_team_itirazi,
  (SELECT count(DISTINCT rt.karar_id) FROM core.karar_red_team rt
     JOIN core.karar k4 USING (karar_id)
    WHERE NOT k4.fixture AND rt.sonuc='CHALLENGE')                           AS itiraz_alan_karar,
  count(*)                                                                    AS toplam
  FROM core.karar WHERE NOT fixture;

COMMENT ON VIEW mart.karar_ozet IS 'Panel ozeti. fixture kayitlari HARIC.';

-- ---------------------------------------------------------------------------
-- SON KARARLAR
-- ---------------------------------------------------------------------------
CREATE VIEW mart.karar_son AS
SELECT k.karar_id,
       (k.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS tarih,
       k.karar_tipi, left(k.oneri, 60) AS oneri,
       k.kanit_kalitesi,
       coalesce(i.karar, '—')                             AS insan_karari,
       k.durum,
       coalesce(s.sonuc_durumu, '—')                      AS sonuc,
       coalesce(s.yanlislandi, '—')                       AS yanlislandi,
       (SELECT count(*) FROM core.karar_red_team rt
         WHERE rt.karar_id=k.karar_id AND rt.sonuc='CHALLENGE') AS itiraz
  FROM core.karar k
  LEFT JOIN core.karar_insan i ON i.karar_id = k.karar_id
  LEFT JOIN core.karar_sonuc s ON s.karar_id = k.karar_id
 WHERE NOT k.fixture
 ORDER BY k.karar_id DESC;

-- ---------------------------------------------------------------------------
-- FIXTURE (test senaryolari)  -  AYRI, uretimle karismaz
-- ---------------------------------------------------------------------------
CREATE VIEW mart.karar_fixture AS
SELECT k.karar_id, left(k.oneri,52) AS senaryo, k.durum,
       coalesce(i.karar,'—') AS insan_karari,
       coalesce(a.aksiyon_tipi,'—') AS aksiyon,
       coalesce(s.sonuc_durumu,'—') AS sonuc,
       coalesce(s.veri_kalitesi,'—') AS veri_kalitesi,
       coalesce(s.orneklem,0) AS orneklem,
       coalesce(s.yanlislandi,'—') AS yanlislandi,
       left(coalesce(s.uygunluk_gerekcesi,'—'),52) AS uygunluk
  FROM core.karar k
  LEFT JOIN core.karar_insan i ON i.karar_id=k.karar_id
  LEFT JOIN LATERAL (SELECT aksiyon_tipi FROM core.karar_aksiyon
                      WHERE karar_id=k.karar_id ORDER BY aksiyon_id LIMIT 1) a ON true
  LEFT JOIN core.karar_sonuc s ON s.karar_id=k.karar_id
 WHERE k.fixture ORDER BY k.karar_id;

-- ---------------------------------------------------------------------------
-- KALIBRASYON VERI YAPISI  (CR-016+ icin; MODEL KURULMADI)
-- ---------------------------------------------------------------------------
-- 🔴 Bu CR'de ML/kalibrasyon MODELI kurulmuyor. Yalnizca ileride
--    "HIGH kanit kac kez dogru cikti" sorusunun CEVAPLANABILIR olmasi icin
--    iliski saklaniyor. Bugun satir sayisi az; oran GOSTERILMEZ.
CREATE VIEW mart.karar_kalibrasyon AS
SELECT k.kanit_kalitesi,
       coalesce(i.karar,'KARAR_YOK')                       AS insan_karari,
       coalesce(s.sonuc_durumu,'SONUC_YOK')                AS sonuc,
       count(*)                                            AS adet,
       -- 🔴 Oran YAZILMAZ: n cok kucuk. Ham adet konusulur.
       'n cok kucuk - oran uretilmiyor'::text              AS not
  FROM core.karar k
  LEFT JOIN core.karar_insan i ON i.karar_id=k.karar_id
  LEFT JOIN core.karar_sonuc s ON s.karar_id=k.karar_id
 WHERE NOT k.fixture
 GROUP BY 1,2,3;

COMMENT ON VIEW mart.karar_kalibrasyon IS
  'Kanit kalitesi x insan karari x sonuc iliskisi. Model YOK, oran YOK - yalniz ham adet.';

COMMIT;
