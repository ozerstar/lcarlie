-- =============================================================================
-- L'CARLIE - URUN MALIYETININ TEK KAYNAGI: FINANS MERKEZI  (15.11.2026)
--
-- Sahip (15.11.2026): "Maliyet nasil bilinmiyor, urun maliyetleri Jarvis'in
-- finans merkezinde kayitli, her urun icin yazili. Bu baglantilari kuralim."
--
-- 🔴 KAYNAK: Jarvis paneli > Finans > Urun Karliligi
--    (webconsole/product_profit.py). Birim TAM maliyet = (uretim faturasi
--    + tester/TTS/UGR/genel giderlerin urune dusen payi) / uretilen adet.
--    KDV HARIC, kurus. Wix'in Maliyet alani 04.11'de buradan x1,20 yazildi
--    (KOPYA, kaynak degil).
--
-- 🔴 AKIS:  product_profit.report()  --(scripts/finans-maliyet-aktar.py,
--           saatlik timer)-->  core.finans_maliyet_yaz(jsonb)
--             -> core.finans_maliyet_anlik   (degisince yeni anlik; gecmis kalir)
--             -> core.urun_maliyet (kaynak FINANS, KDV HARIC, zamana gore surum)
--             -> core.maliyet_bul() -> mart.siparis_kalem / urun_karlilik /
--                gunluk_marj / siparis_ekonomi / platform_fiyat_matrisi / urun_karti
--
-- 🔴 OKUMA: tek sorgu  SELECT * FROM core.urun_maliyet_guncel;
--
-- 🔴 DURUM AYRIMI: maliyet yoksa durum='VERI_YOK' ve maliyet NULL - 0 DEGIL.
--
-- Idempotent. urun-maliyet-sema.sql'den SONRA calisir.
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- 1) URUN KIMLIK ESLEMESI: finans adi <-> Wix productId <-> barkod <-> UTS
-- --------------------------------------------------------------------------
-- 🔴 Eslestirme AD ile otomatik YAPILMAZ (CR-006). Finans merkezi yalniz
--    fatura satirindaki adi bilir ("Bright", "Hair"); bu tablo o adi bir kez,
--    ELLE ve OLCULEREK productId'ye baglar. Dogrulama: Wix SKU = UTS barkodu
--    (iki bilinen istisna notta), ad anahtari Wix adinda geciyor
--    (tests/test_finans_maliyet.py + asagidaki core.urun_kimlik_denetim).
CREATE TABLE IF NOT EXISTS core.urun_kimlik (
  finans_ad         text PRIMARY KEY,          -- product_profit 'product'
  urun_kod          text NOT NULL UNIQUE,      -- kanonik ad (VIREON, BRIGHT SMILE)
  urun_id           text NOT NULL UNIQUE,      -- Wix productId
  barkod            text,                      -- kutu/UTS barkodu (8684869609xxx)
  uts_no            text,                      -- UTS kayit no
  pazaryeri_barkod  text,                      -- pazaryeri ilaninda kullanilan
  notlar            text,
  guncelleme        timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE core.urun_kimlik IS
  'Urun kimligi koprusu: finans merkezi adi <-> Wix productId <-> barkod <-> UTS. Kaynak: UTS listesi (sahip 10.11.2026) + raw.wix_urun.';

INSERT INTO core.urun_kimlik (finans_ad, urun_kod, urun_id, barkod, uts_no, pazaryeri_barkod, notlar) VALUES
 ('Vireon',      'VIREON',         'b94c3b37-b362-34af-afba-6f5ecf9decf0', '8684869609110', '11669727', '8684869609110', NULL),
 ('Femisia',     'FEMISIA',        'd9d6fc12-de61-4cbb-9dbc-8dc51b1f3f61', '8684869609127', '11669827', '8684869609127', NULL),
 ('Liftelle',    'LIFTELLE',       'e653204e-65ca-20ec-d7b7-9ab6f26af5d8', '8684869609141', '11669967', '8684869609141', NULL),
 ('Dermanova',   'DERMANOVA',      '7738bdd9-64c4-c567-7779-d036279de3c8', '8684869609073', '11457387', '8684869609073', NULL),
 ('Intimblanc',  'INTIMBLANC',     '49bea734-a79a-e813-be29-822b73ed3940', '8684869609318', '11460827', '8684869609318', NULL),
 ('Hydravie',    'HYDRAVIE',       '75bdaa3f-67d2-3cf7-3a87-ff12dfb7ef7a', '8684869609233', '11456648', '8684869609233', NULL),
 ('Calmaros',    'CALMAROS',       'f44217c7-cf47-e116-6fd4-27b18b7d865f', '8684869609080', '11808347', '8684869609080', NULL),
 ('Dermavasc',   'DERMAVASC',      'd391afe5-0e82-4d38-cf2b-2209203f8531', '8684869609271', '11669927', '8684869609271', NULL),
 ('Luciderm',    'LUCIDERM',       '76a73d6b-9436-ea72-df4e-0760b0924b53', '8684869609295', '11463188', '8684869609295', NULL),
 ('Optywave',    'OPTYWAVE',       'cecfe4d9-108f-4aef-4409-7df2849962c5', '8684869609172', '11669107', '8684869609509',
   'UTS''de iki kayit: 9509 Optywave (12097787) ve 9172 Optywave Eyes Zone (11669107). Wix SKU 9172, Trendyol ilani 9509. Finans merkezinde tek urun (200 adet).'),
 ('Sunacnea',    'SUNACNEA',       'fed5d9ff-8e0a-7f0a-6181-535b613cae3c', '8684869609097', '11456567', '8684869609097', NULL),
 ('Seralimbo',   'SERALIMBO',      'e3d6bc36-4e3f-e08e-6243-762f503edbc2', '8684869609202', '11464307', '8684869609202', NULL),
 ('Dermabed',    'DERMABED',       'a8f41b06-3ba4-af05-fd06-61312df2cafe', '8684869609066', '11463907', '8684869609066', NULL),
 ('Cal Jaw',     'CALJAW',         '3c01d296-ec2e-d826-2b02-4cce7b49e794', '8684869609196', '11455707', '8684869609196', NULL),
 ('Kinesis+',    'KINESIS+',       '01e52995-4e40-1f5e-c796-c573e163a387', '8684869609547', '12516339', '8684869609547', NULL),
 ('Dermaguard',  'DERMAGUARD',     '1c745673-9e19-8e62-9abb-17aef9179ab8', '8684869609103', '11456487', '8684869609103', NULL),
 ('Lipvora',     'LIPVORA',        'f078b84d-a615-7475-f94f-cf29e0db227f', '8684869609134', '11463647', '8684869609134', NULL),
 ('Oragarde',    'ORAGARDE',       '97630910-b5a4-0473-0e64-82abfba14d64', '8684869609165', '11670007', '8684869609165', NULL),
 ('Bright',      'BRIGHT SMILE',   'dc98aad2-7cda-4b67-b409-dc2b65e18276', '8684869609394', '11456947', '8684869609394',
   'Finans merkezi fatura satirindan ilk kelimeyi aliyor: "Bright".'),
 ('Babysol',     'BABYSOL',        'cbb590ee-62e9-4890-6320-37ffe82b5c06', '8684869609530', '12515999', '8684869609530', NULL),
 ('Calmoris',    'CALMORIS',       '9db03a94-b621-632a-4336-00f82cd641aa', '8684869609578', '12516599', '8684869609578', NULL),
 ('Menthalis',   'MENTHALIS',      '3e766216-0047-bdc0-2b83-7772f4845492', '8684869609585', '12516719', '8684869609585', NULL),
 ('Dermamovera', 'DERMAMOVERA',    'e4a25721-f1ca-bb69-83a9-074ecedf84b8', '8684869609516', '12330119', '8684869609516', NULL),
 ('Minisooth',   'MINISOOTH',      'bd3a2d00-8f26-3ceb-00cd-437a815242d7', '8684869609325', '11457727', '8684869609325', NULL),
 ('Hair',        'HAIR NOURISHER', 'ade63a4b-b860-f463-ab68-aa3a112be205', '8684869609158', '11669447', '8684869609158',
   'Finans merkezi fatura satirindan ilk kelimeyi aliyor: "Hair".'),
 ('Babyrescue',  'BABY RESCUE',    '60777691-77f4-c54e-5970-37e2358844b1', '8684869609363', '11463527', '8684869609363', NULL),
 ('Dermastra',   'DERMASTRA',      'ad0036c3-b5ab-951d-7385-d191308fe379', '8684869609561', '12516499', '8684869609561', NULL),
 ('Babydent',    'BABYDENT',       'dbb43742-83ab-5573-54c0-ec5501c72f2c', '8684869609387', '11457187', '8684869609387', NULL),
 ('Babyshower',  'BABYSHOWER',     'babd8b05-d386-aad0-2cc4-2239e80bdc5d', '8684869609356', '11669307', '8684869609356', NULL),
 ('Easycomb',    'EASYCOMB',       'aa9ad907-f63f-7664-1df8-997e118bd84f', '8684869609370', '11460987', '8684869609370', NULL),
 ('Dermarnica',  'DERMARNICA',     '9362de58-3b15-8a78-8f87-698a555c9988', '8684869609554', '12516419', '8684869609554', NULL),
 ('Babysoft',    'BABYSOFT',       '24fed361-2f30-f048-0c9d-d9d60f1c0003', '8684869609523', '12515879', '8684869609523', NULL),
 ('Buguard',     'BUGUARD',        '12003267-dcf1-3add-17e8-163b08af5579', '8684869609301', '12329699', NULL,
   'Trendyol''daki 8684869609301 ilaninin basligi SOFTGUARD (Anti Mite & Akar) - UTS''de 9301 BUGUARD. Pazaryeri barkodu teyit edilmedi.'),
 -- 🔴 15.11.2026 sahip karari: "Wix'te neyse o" -> GTIN 8684869609400 (Wix SKU, EAN-13 saglamasi 0 dogru).
 --    UTS/kutu baskisindaki 9592 bilgi olarak notta kalir; eslestirme 9400 ile yapilir.
 ('Dorsivia',    'DORSIVIA',       '331165e3-5705-c501-6782-cb8d7950fa65', '8684869609400', '13346719', '8684869609400',
   'sahip 15.11: Wix degeri esas -> GTIN 8684869609400 (Wix SKU + Trendyol ilani). UTS kaydi (13346719) ve kutu baskisi 8684869609592; 9592 artik eslestirme anahtari DEGIL.'),
 ('Softguard',   'SOFTGUARD',      '2abdb739-3675-3c6b-a312-2283a12e395b', '8684869609608', NULL, NULL,
   'Tekstil spreyi - UTS kozmetik listesinde yok (beklenen).'),
 ('Dermacorn',   'DERMACORN',      '9433babc-a59e-334a-0915-4ae14726b9e0', '8684869609288', '11456187', '8684869609288', NULL)
ON CONFLICT (finans_ad) DO UPDATE SET
  urun_kod = EXCLUDED.urun_kod, urun_id = EXCLUDED.urun_id, barkod = EXCLUDED.barkod,
  uts_no = EXCLUDED.uts_no, pazaryeri_barkod = EXCLUDED.pazaryeri_barkod,
  notlar = EXCLUDED.notlar, guncelleme = clock_timestamp();

-- --------------------------------------------------------------------------
-- 2) FINANS MERKEZI ANLIKLARI (degisince yeni satir; gecmis silinmez)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.finans_maliyet_anlik (
  olcum_at            timestamptz NOT NULL,
  finans_ad           text NOT NULL,
  uretilen            numeric(14,3),
  uretim_kurus        bigint,      -- uretim faturalari toplami, KDV HARIC
  genel_kurus         bigint,      -- dagitilan genel gider payi, KDV HARIC
  ozel_kurus          bigint,      -- urune ozel eklenen, KDV HARIC
  toplam_kurus        bigint,
  birim_tam_kurus     bigint,      -- = core.urun_maliyet.maliyet*100 (FINANS)
  birim_uretim_kurus  bigint,
  satilan             numeric(14,3),
  ilk_uretim          text,        -- YYYY-MM
  dagitim             text NOT NULL,
  PRIMARY KEY (olcum_at, finans_ad)
);
COMMENT ON TABLE core.finans_maliyet_anlik IS
  'product_profit.report() ciktisinin urun basi anligi. Yalniz deger DEGISINCE yeni satir yazilir. KDV HARIC kurus.';

-- --------------------------------------------------------------------------
-- 3) YAZICI: tek giris kapisi (jarvis_web cagirir, n8n yetkisiyle calisir)
-- --------------------------------------------------------------------------
-- p = {"dagitim":"esit","urunler":[{"product":"Vireon","produced":252,
--      "production":1386000,"general":889455,"special":0,"total_cost":...,
--      "unit_cost":9030,"unit_production":5500,"first_made":"2025-12","sold":87}, ...]}
CREATE OR REPLACE FUNCTION core.finans_maliyet_yaz(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = core, pg_temp AS $$
DECLARE
  r jsonb; v_an timestamptz := clock_timestamp(); v_ad text; v_urun text;
  v_birim bigint; v_sonuc text; v_baslangic timestamptz; v_dagitim text;
  v_ozet jsonb := '{}'::jsonb; v_eslesmeyen text[] := '{}'; v_veri_yok text[] := '{}';
  v_anlik int := 0; v_sayi int;
BEGIN
  v_dagitim := coalesce(p->>'dagitim', '');
  IF v_dagitim NOT IN ('esit','adet','ciro') THEN
    RAISE EXCEPTION 'dagitim gecersiz: %', v_dagitim;
  END IF;
  v_sayi := jsonb_array_length(coalesce(p->'urunler','[]'::jsonb));
  IF v_sayi = 0 OR v_sayi > 300 THEN
    RAISE EXCEPTION 'urunler 1..300 olmali (gelen %)', v_sayi;
  END IF;

  FOR r IN SELECT * FROM jsonb_array_elements(p->'urunler') LOOP
    v_ad := btrim(r->>'product');
    CONTINUE WHEN v_ad IS NULL OR v_ad = '';
    v_birim := nullif(r->>'unit_cost','')::numeric::bigint;

    -- anlik: yalniz degistiyse
    INSERT INTO core.finans_maliyet_anlik
      (olcum_at, finans_ad, uretilen, uretim_kurus, genel_kurus, ozel_kurus, toplam_kurus,
       birim_tam_kurus, birim_uretim_kurus, satilan, ilk_uretim, dagitim)
    SELECT v_an, v_ad, (r->>'produced')::numeric, (r->>'production')::numeric::bigint,
           (r->>'general')::numeric::bigint, (r->>'special')::numeric::bigint,
           (r->>'total_cost')::numeric::bigint, v_birim,
           nullif(r->>'unit_production','')::numeric::bigint, (r->>'sold')::numeric,
           r->>'first_made', v_dagitim
     WHERE NOT EXISTS (
       SELECT 1 FROM (SELECT * FROM core.finans_maliyet_anlik a
                       WHERE a.finans_ad = v_ad ORDER BY a.olcum_at DESC LIMIT 1) s
        WHERE s.birim_tam_kurus IS NOT DISTINCT FROM v_birim
          AND s.birim_uretim_kurus IS NOT DISTINCT FROM nullif(r->>'unit_production','')::numeric::bigint
          AND s.uretilen IS NOT DISTINCT FROM (r->>'produced')::numeric
          AND s.toplam_kurus IS NOT DISTINCT FROM (r->>'total_cost')::numeric::bigint
          AND s.satilan IS NOT DISTINCT FROM (r->>'sold')::numeric
          AND s.dagitim = v_dagitim);
    IF FOUND THEN v_anlik := v_anlik + 1; END IF;

    SELECT k.urun_id INTO v_urun FROM core.urun_kimlik k WHERE k.finans_ad = v_ad;
    IF v_urun IS NULL THEN
      v_eslesmeyen := v_eslesmeyen || v_ad;
      CONTINUE;
    END IF;
    -- 🔴 VERI_YOK != 0: uretim faturasi olmayan urunde birim maliyet YOK.
    --    Eski deger varsa KAPATILMAZ (sessizce silmek de bir uydurmadir);
    --    ozet 'veri_yok' listesinde gorunur.
    IF v_birim IS NULL OR v_birim <= 0 THEN
      v_veri_yok := v_veri_yok || v_ad;
      CONTINUE;
    END IF;
    -- Ilk FINANS kaydi tum gecmisi kapsar: birim maliyet BUTUN uretim
    -- faturalarinin ortalamasidir; daha eski bir olculmus deger yok.
    IF EXISTS (SELECT 1 FROM core.urun_maliyet m
                WHERE m.urun_id = v_urun AND m.kaynak = 'FINANS' AND m.iptal_at IS NULL) THEN
      v_baslangic := v_an;
    ELSE
      v_baslangic := '2025-01-01 00:00:00+03'::timestamptz;
    END IF;
    v_sonuc := core.maliyet_guncelle(v_urun, round(v_birim / 100.0, 2), 'FINANS',
                 format('Finans merkezi birim tam maliyet (KDV haric), dagitim=%s, %s', v_dagitim,
                        to_char(v_an AT TIME ZONE 'Europe/Istanbul', 'DD.MM.YYYY HH24:MI')),
                 v_baslangic);
    v_ozet := jsonb_set(v_ozet, ARRAY[v_sonuc],
                        to_jsonb(coalesce((v_ozet->>v_sonuc)::int, 0) + 1));
  END LOOP;

  INSERT INTO core.ayar (anahtar, deger, aciklama)
  VALUES ('finans_maliyet_son_kontrol', to_char(v_an, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
          'core.finans_maliyet_yaz son calisma ani (finans merkezi -> core.urun_maliyet)')
  ON CONFLICT (anahtar) DO UPDATE SET deger = EXCLUDED.deger, guncelleme = now();

  RETURN jsonb_build_object('an', v_an, 'sonuc', v_ozet, 'yeni_anlik', v_anlik,
                            'eslesmeyen', to_jsonb(v_eslesmeyen), 'veri_yok', to_jsonb(v_veri_yok));
END $$;

-- --------------------------------------------------------------------------
-- 4) 16.09 "ORTALAMA 400 TL" KAYITLARI GECERSIZ (sahip 15.11.2026)
-- --------------------------------------------------------------------------
-- SILINMEZ: geçmiş ölçümler (CR-010, CR-012 raporları) izlenebilir kalsin.
-- Aktif olanlar ayrica kapatilir (gecerli_bitis) ki maliyet_bul disinda
-- dogrudan "gecerli_bitis IS NULL" okuyan eski sorgular da onlari gormesin.
-- Ayni yol WIX'in eski 280 TL BABYSOL kaydini da kapsar: Wix artik kopya.
UPDATE core.urun_maliyet
   SET gecerli_bitis = coalesce(gecerli_bitis, clock_timestamp())
 WHERE iptal_at IS NULL AND gecerli_bitis IS NULL
   AND created_at < '2026-11-15 00:00:00+03'
   AND kaynak IN ('ELLE','WIX');
UPDATE core.urun_maliyet
   SET iptal_at = clock_timestamp(),
       iptal_gerekce = 'Sahip 15.11.2026: urun maliyetinin tek kaynagi finans merkezi '
                       '(Urun Karliligi, faturadan tam maliyet). 16.09 "ortalama 400 TL" '
                       'beyani ve Wix alanindan gelen degerler gecersiz.'
 WHERE iptal_at IS NULL
   AND created_at < '2026-11-15 00:00:00+03'
   AND kaynak IN ('ELLE','WIX');

-- --------------------------------------------------------------------------
-- 5) KDV / KARGO TABANI: FINANS degeri KDV HARIC ve kargo HARIC
-- --------------------------------------------------------------------------
-- 🔴 400 TL beyani KDV+kargo DAHILdi (29.09). Finans merkezinin rakami
--    ikisini de icermez. Ayar degismeseydi mart.siparis_ekonomi maliyeti
--    bir kez daha 1,2'ye boler ve olculen kargoyu katkidan dusmezdi.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
 ('maliyet_kdv_tabani', 'KDV_HARIC',
  '15.11.2026: urun maliyeti finans merkezinden (product_profit unit_cost) KDV HARIC gelir. '
  'Gosterimde KDV dahil = x1,20 (core.urun_maliyet_guncel). MEASURED (uretim faturasi).'),
 ('maliyet_kargo_dahil', 'HAYIR',
  '15.11.2026: finans merkezi birim maliyeti giden kargoyu ICERMEZ; olculen kargo katkidan ayrica dusulur.')
ON CONFLICT (anahtar) DO UPDATE SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = now();

-- --------------------------------------------------------------------------
-- 6) OKUMA YUZU: core.urun_maliyet_guncel  (TEK SORGU)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW core.urun_maliyet_guncel AS
WITH son AS (
  SELECT DISTINCT ON (a.finans_ad) a.*
    FROM core.finans_maliyet_anlik a
   ORDER BY a.finans_ad, a.olcum_at DESC
), aktif AS (
  SELECT DISTINCT ON (m.urun_id) m.urun_id, m.maliyet, m.kaynak, m.gecerli_baslangic, m.gerekce
    FROM core.urun_maliyet m
   WHERE m.iptal_at IS NULL
     AND m.gecerli_baslangic <= now()
     AND (m.gecerli_bitis IS NULL OR m.gecerli_bitis > now())
   ORDER BY m.urun_id, (m.kaynak = 'FINANS') DESC, m.gecerli_baslangic DESC
)
SELECT w.urun_id,
       coalesce(k.urun_kod, w.ad)                         AS urun_kod,
       w.ad                                               AS wix_adi,
       k.finans_ad,
       k.barkod, k.uts_no, w.sku AS wix_sku, k.pazaryeri_barkod,
       CASE WHEN k.urun_id IS NOT NULL OR w.sku LIKE '868486960%'
              OR w.ad ~* '(roll-?on|krem|sprey|balm|losyon|yag)' THEN 'KOZMETIK'
            ELSE 'DIGER' END                              AS urun_turu,
       w.gorunur                                          AS wix_yayinda,
       a.maliyet                                          AS birim_maliyet_kdv_haric,
       round(a.maliyet * 1.20, 2)                         AS birim_maliyet_kdv_dahil,
       round(s.birim_uretim_kurus / 100.0, 2)             AS birim_uretim_kdv_haric,
       round(s.birim_uretim_kurus * 1.20 / 100.0, 2)      AS birim_uretim_kdv_dahil,
       round((s.birim_tam_kurus - s.birim_uretim_kurus) / 100.0, 2) AS birim_genel_pay_kdv_haric,
       s.uretilen, s.satilan, s.ilk_uretim, s.dagitim,
       a.kaynak                                           AS maliyet_kaynagi,
       a.gecerli_baslangic,
       s.olcum_at                                         AS finans_olcum_at,
       (SELECT deger FROM core.ayar WHERE anahtar = 'finans_maliyet_son_kontrol') AS finans_son_kontrol,
       CASE WHEN a.maliyet IS NOT NULL AND a.kaynak = 'FINANS' THEN 'GIRILDI'
            WHEN a.maliyet IS NOT NULL                     THEN 'FINANS_DISI'
            ELSE 'VERI_YOK' END                           AS durum,
       CASE WHEN a.maliyet IS NOT NULL AND a.kaynak = 'FINANS' THEN NULL
            WHEN a.maliyet IS NOT NULL THEN 'aktif maliyet finans merkezinden degil ('||a.kaynak||')'
            WHEN k.urun_id IS NULL     THEN 'finans merkezinde bu urunun uretim faturasi / eslesmesi yok'
            WHEN s.finans_ad IS NULL   THEN 'eslesme var ama finans merkezi bu urunu raporlamadi'
            ELSE 'finans merkezinde birim maliyet hesaplanamadi (uretilen adet 0)' END AS durum_nedeni,
       nullif(w.maliyet, 0)                               AS wix_maliyet_alani,
       CASE WHEN a.maliyet IS NULL                         THEN NULL
            WHEN coalesce(w.maliyet, 0) = 0                THEN 'WIX_BOS'
            WHEN abs(w.maliyet - round(a.maliyet * 1.20, 2)) <= 0.01 THEN 'AYNI'
            ELSE 'FARKLI' END                             AS wix_durumu
  FROM raw.wix_urun w
  LEFT JOIN core.urun_kimlik k ON k.urun_id = w.urun_id
  LEFT JOIN son   s ON s.finans_ad = k.finans_ad
  LEFT JOIN aktif a ON a.urun_id = w.urun_id;

COMMENT ON VIEW core.urun_maliyet_guncel IS
  'URUN MALIYETININ TEK OKUMA YUZU (15.11.2026). Kaynak finans merkezi (product_profit). '
  'birim_maliyet_kdv_haric = marj hesabi tabani; kdv_dahil = gosterim (x1,20). '
  'durum VERI_YOK ise maliyet NULL - 0 degil. wix_durumu Wix Maliyet alaninin finansla tutarliligi.';

-- Eslesmeyenler: finans merkezinde olup kimlik koprusunde olmayan adlar ve
-- koprude olup Wix'te bulunmayan productId'ler.
CREATE OR REPLACE VIEW core.urun_kimlik_denetim AS
SELECT 'FINANS_ADI_ESLESMEDI' AS bulgu, s.finans_ad AS anahtar, NULL::text AS ayrinti
  FROM (SELECT DISTINCT finans_ad FROM core.finans_maliyet_anlik) s
 WHERE NOT EXISTS (SELECT 1 FROM core.urun_kimlik k WHERE k.finans_ad = s.finans_ad)
UNION ALL
SELECT 'WIX_URUNU_YOK', k.finans_ad, k.urun_id
  FROM core.urun_kimlik k
 WHERE NOT EXISTS (SELECT 1 FROM raw.wix_urun w WHERE w.urun_id = k.urun_id)
UNION ALL
SELECT 'WIX_SKU_UTS_FARKLI', k.finans_ad, format('Wix SKU %s, UTS/kutu %s', w.sku, k.barkod)
  FROM core.urun_kimlik k JOIN raw.wix_urun w ON w.urun_id = k.urun_id
 WHERE k.barkod IS DISTINCT FROM w.sku
UNION ALL
SELECT 'KOZMETIK_FINANSTA_YOK', w.ad, w.urun_id
  FROM raw.wix_urun w
 WHERE (w.sku LIKE '868486960%' OR w.ad ~* '(roll-?on|krem|sprey|balm|losyon|yag)')
   AND NOT EXISTS (SELECT 1 FROM core.urun_kimlik k WHERE k.urun_id = w.urun_id);

-- --------------------------------------------------------------------------
-- 7) YETKILER
-- --------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jarvis_web') THEN
    GRANT USAGE ON SCHEMA core TO jarvis_web;
    GRANT SELECT ON core.urun_maliyet_guncel, core.urun_kimlik, core.urun_kimlik_denetim,
                    core.finans_maliyet_anlik TO jarvis_web;
    GRANT EXECUTE ON FUNCTION core.finans_maliyet_yaz(jsonb) TO jarvis_web;
    -- core.maliyet_bul() cagirani yetkisiyle calisir: panel mart.siparis_kalem'i
    -- okurken "permission denied for table urun_maliyet" aliyordu (15.11 olculdu).
    GRANT SELECT ON core.urun_maliyet TO jarvis_web;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_reader') THEN
    GRANT SELECT ON core.urun_maliyet_guncel, core.urun_kimlik, core.urun_kimlik_denetim,
                    core.finans_maliyet_anlik TO ai_reader;
  END IF;
END $$;
REVOKE ALL ON FUNCTION core.finans_maliyet_yaz(jsonb) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jarvis_web') THEN
    GRANT EXECUTE ON FUNCTION core.finans_maliyet_yaz(jsonb) TO jarvis_web;
  END IF;
END $$;

COMMIT;
