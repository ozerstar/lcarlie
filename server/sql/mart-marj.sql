-- =============================================================================
-- L'CARLIE - MART: KATKI MARJI  (CR-006 Faz 4)
--
-- 🔴 MARJ TEK BASINA OKUNMAZ.  Her marj satirinin yaninda "bu rakamin
--    ne kadari olculdu" bilgisi durur (maliyeti_bilinen_oran). Bugun
--    cironun %2,6'sinin maliyeti biliniyor; kapsama yazilmadan gosterilen
--    bir marj, bilinmeyeni yok saymis olur.
--
-- 🔴 MALIYETI BILINMEYEN KALEMIN MARJI **NULL**, SIFIR DEGIL.
--    Toplamlarda da NULL'lar 0 sayilmaz; ayri sayilir ve raporlanir.
--
-- 🔴 UC AYRI SEVIYE, KARISTIRILMAZ:
--      brut_marj      = ciro - COGS                 (urun karliligi)
--      katki_marji    = ciro - COGS - kargo         (siparis karliligi)
--      reklam SONRASI = gunluk seviyede, mart.gunluk_marj icinde
--    Reklam kalem bazinda dagitilamaz (atif yok), o yuzden ayri seviye.
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Kalem bazinda maliyet ve marj
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.siparis_kalem AS
SELECT
  i.siparis_id,
  i.sira,
  s.gun,
  s.olusturma,
  s.ciro_sinifi,
  s.olcumde,
  i.urun_id,
  coalesce(u.ad, i.urun_adi)      AS urun_adi,   -- katalog adi esas, yoksa siparisteki
  u.sku,
  i.adet,
  i.birim_fiyat,
  i.toplam                        AS satir_brut,    -- indirim ONCESI
  i.indirim,
  -- 🔴 CIRO = NET TUTAR.  i.toplam (totalPrice) indirim oncesidir; onu ciro
  --    saymak toplami %18,8 sisiriyordu. net_toplam turetilmis kolondur ve
  --    toplami siparis toplamiyla birebir tutar (37/37 dogrulandi).
  i.net_toplam                    AS satir_ciro,      -- 🔴 KDV DAHIL

  -- 🔴 MARJ KDV HARIC CIRODAN HESAPLANIR (CR-012'de bulunan hata).
  --    satir_ciro (net_toplam) KDV DAHILDIR: kalem toplami 82.073,50 =
  --    siparis toplami, ve siparis toplami totals.total yani KDV dahil.
  --    KDV bizim paramiz degil; KDV dahil ciradan maliyet cikarmak marji
  --    KDV kadar sisirir. Olculdu: marj 49.823,50 -> 37.786,25, yani
  --    %31,9 SISIKTI. CR-008'deki indirim hatasindan BUYUK bir sapma.
  --
  --    Oransal dagitim kullanilir (bolme degil): siparişin kendi
  --    net/toplam oraniyla carpilir. Boylece kalemlerin net toplami
  --    siparişin net tutarina BIREBIR esit kalir ve ileride bir kalem
  --    farkli KDV oranina girerse hesap yine tutar.
  -- 🔴 w.kdv NULL ise sonuc NULL - "KDV yok" VARSAYILMAZ.
  round(i.net_toplam * (w.toplam - w.kdv) / nullif(w.toplam, 0), 2)
                                  AS satir_ciro_net,  -- KDV HARIC

  -- 🔴 SIPARIS TARIHINDEKI maliyet - bugunku degil.
  core.maliyet_bul(i.urun_id, s.olusturma)            AS birim_maliyet,
  core.maliyet_bul(i.urun_id, s.olusturma) * i.adet   AS satir_maliyet,

  -- 🔴 MALIYETIN KDV TABANI HENUZ TEYIT EDILMEDI (acik soru, sahipte).
  --    Beyan edilen 400 TL'nin KDV dahil mi haric mi oldugu bilinmiyor.
  --    Standart uygulama: COGS KDV HARIC tutulur (alis KDV'si indirilir).
  --    Bu varsayimla hesaplaniyor ve varsayim GIZLENMIYOR - core.ayar
  --    icinde 'maliyet_kdv_tabani' bos oldugu surece mart.maliyet_kalite
  --    bunu TEYIT_EDILMEDI olarak gosterir.
  --    Etki olculdu: 400 KDV dahil olsaydi taban 333,33 olurdu ve bu veri
  --    setinde marj 3.733 TL daha yuksek cikardi.
  CASE WHEN core.maliyet_bul(i.urun_id, s.olusturma) IS NOT NULL
       THEN round(i.net_toplam * (w.toplam - w.kdv) / nullif(w.toplam, 0), 2)
            - core.maliyet_bul(i.urun_id, s.olusturma) * i.adet
  END                                                 AS brut_marj,

  (core.maliyet_bul(i.urun_id, s.olusturma) IS NOT NULL) AS maliyeti_biliniyor
FROM raw.wix_order_item i
JOIN mart.siparis s ON s.siparis_id = i.siparis_id
JOIN raw.wix_order w ON w.siparis_id = i.siparis_id
LEFT JOIN raw.wix_urun u ON u.urun_id = i.urun_id;

COMMENT ON VIEW mart.siparis_kalem IS
  'Kalem bazinda ciro/maliyet/marj. Maliyet SIPARIS TARIHINDE gecerli olandir. Bilinmiyorsa marj NULL.';

-- --------------------------------------------------------------------------
-- Urun bazinda karlilik
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.urun_karlilik AS
SELECT
  k.urun_id,
  k.urun_adi,
  k.sku,
  count(*)                                   AS kalem,
  sum(k.adet)                                AS adet,
  sum(k.satir_ciro)                          AS ciro,        -- KDV dahil
  sum(k.satir_ciro_net)                      AS ciro_net,    -- 🔴 KDV haric
  sum(k.satir_maliyet)                       AS maliyet,
  sum(k.brut_marj)                           AS brut_marj,
  -- 🔴 YUZDE, KDV HARIC CIRO UZERINDEN.  KDV dahil ciroya bolmek marj
  --    yuzdesini olduğundan DUSUK gosterirdi (payda sisik) - marjin
  --    kendisi ise KDV dahil ciradan hesaplanirsa YUKSEK cikardi.
  --    Iki hata birbirini kismen gizliyordu; ikisi de duzeltildi.
  --    Yalniz maliyeti BILINEN satirlar paydaya girer.
  round(100.0 * sum(k.brut_marj)
        / nullif(sum(k.satir_ciro_net) FILTER (WHERE k.maliyeti_biliniyor), 0), 1)
                                             AS brut_marj_yuzde,
  count(*) FILTER (WHERE k.maliyeti_biliniyor) AS maliyeti_bilinen_kalem,
  round(100.0 * coalesce(sum(k.satir_ciro) FILTER (WHERE k.maliyeti_biliniyor), 0)
        / nullif(sum(k.satir_ciro), 0), 1)   AS kapsama_yuzde
FROM mart.siparis_kalem k
-- 🔴 IPTAL **ve ODENMEDI** haric.  Onceki hali yalniz IPTAL'i eliyordu;
--    odenmemis siparis mart.gunluk'ta "tutar_bekleyen" sayilirken burada
--    "ciro" sayiliyordu. Ayni gun icin iki view iki farkli ciro veriyordu
--    ve marj tahsil EDILMEMIS parayla hesaplaniyordu.
WHERE k.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
GROUP BY 1,2,3;

COMMENT ON VIEW mart.urun_karlilik IS
  'Urun bazinda karlilik. kapsama_yuzde okunmadan brut_marj_yuzde yorumlanmaz.';

-- --------------------------------------------------------------------------
-- Gunluk marj  (kargo ve reklam dahil)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.gunluk_marj AS
WITH k AS (
  SELECT gun,
         sum(satir_ciro)                                   AS ciro,
         sum(satir_ciro_net)                               AS ciro_net,
         sum(satir_maliyet)                                AS cogs,
         sum(brut_marj)                                    AS brut_marj,
         sum(satir_ciro_net) FILTER (WHERE maliyeti_biliniyor) AS ciro_olculen
    FROM mart.siparis_kalem
   WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS') AND olcumde
   GROUP BY gun
), kg AS (
  -- 🔴 GIDER SATIRI GIZLENMEZ, SINIFLANDIRILIR (ikinci tur denetimi).
  --    Onceki hali yalniz sinif='SATIS' kargosunu topluyordu; mart.gunluk
  --    ise TUM gonderileri. Iki view iki farkli "kargo" veriyordu
  --    (1.075,54 vs 7.063,83 - %85 fark) ve SINIFLANDIRILMAMIS 39
  --    gonderinin 5.114,65 TL kargosu marj merdiveninde HIC gorunmuyordu,
  --    yani katki marji oldugundan YUKSEK cikiyordu.
  --    Bu, projenin kok bulgusunun ("birbirinden turemis iki sayiyi kimse
  --    yan yana koymadi") gider tarafindaki esiydi.
  SELECT gun,
         sum(kargo_ucreti) FILTER (WHERE sinif = 'SATIS')  AS kargo,
         sum(kargo_ucreti) FILTER (WHERE sinif = 'IADE')   AS iade_kargo,
         -- 🔴 UNKNOWN gonderi gideri BURAYA duser: ne satis ne numune.
         --    Para GERCEKTEN odendi, o yuzden yok sayilmaz; ama pazarlama
         --    gideri diye ETIKETLENMEZ - sinifi bilinmiyor.
         sum(kargo_ucreti) FILTER (WHERE sinif NOT IN ('SATIS','IADE','NUMUNE'))
                                                           AS sinifsiz_kargo,
         sum(kargo_ucreti)                                 AS kargo_tum
    FROM mart.gonderi WHERE olcumde GROUP BY gun
), nm AS (
  -- Numune/UGC: kargo maliyeti var, ciro YOK -> pazarlama gideri
  SELECT gun, sum(kargo_ucreti) AS numune_kargo
    -- 🔴 YALNIZ ACIKCA ISARETLENMIS NUMUNE. Varsayimla numune sayilan
    --    gonderi artik YOK (UNKNOWN'a dustu) ve pazarlama giderine girmez.
    FROM mart.gonderi WHERE olcumde AND sinif = 'NUMUNE' GROUP BY gun
), r AS (
  SELECT gun, sum(harcama) AS reklam
    FROM raw.meta_harcama WHERE kampanya_id <> '_HESAP' GROUP BY gun
)
SELECT
  coalesce(k.gun, kg.gun, nm.gun, r.gun)       AS gun,
  coalesce(k.ciro, 0)                          AS ciro,      -- KDV dahil
  coalesce(k.ciro_net, 0)                      AS ciro_net,  -- 🔴 marj bundan
  round(k.cogs,2)      AS cogs,
  round(k.brut_marj,2) AS brut_marj,
  coalesce(kg.kargo, 0)                        AS kargo,
  coalesce(kg.iade_kargo, 0)                   AS iade_gideri,
  coalesce(kg.sinifsiz_kargo, 0)               AS sinifsiz_kargo,
  coalesce(nm.numune_kargo, 0)                 AS numune_gideri,
  coalesce(kg.kargo_tum, 0)                    AS kargo_tum,
  coalesce(r.reklam, 0)                        AS reklam,

  -- 🔴 COGS bilinmiyorsa katki marji da NULL. Kargoyu tek basina cikarip
  --    "marj bu" demek, en buyuk gider kalemini yok saymak olurdu.
  CASE WHEN k.brut_marj IS NOT NULL
       THEN round(k.brut_marj - coalesce(kg.kargo, 0), 2) END AS katki_marji,
  -- 🔴 Reklam sonrasi rakamda TUM kargo dusulur - siniflandirilmamis ve
  --    iade dahil. O paralar gercekten odendi; sinifi bilinmiyor diye
  --    yok sayilamaz.
  CASE WHEN k.brut_marj IS NOT NULL
       THEN round(k.brut_marj - coalesce(kg.kargo_tum, 0) - coalesce(r.reklam, 0), 2)
  END                                                     AS reklam_sonrasi,

  -- Bu satirin ne kadari gercekten olculdu (ikisi de KDV haric - ayni taban)
  round(100.0 * coalesce(k.ciro_olculen, 0) / nullif(k.ciro_net, 0), 1)
                                                          AS maliyeti_bilinen_oran
FROM k
FULL OUTER JOIN kg ON kg.gun = k.gun
FULL OUTER JOIN nm ON nm.gun = coalesce(k.gun, kg.gun)
FULL OUTER JOIN r  ON r.gun  = coalesce(k.gun, kg.gun, nm.gun)
WHERE coalesce(k.gun, kg.gun, nm.gun, r.gun)
      >= (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date
ORDER BY 1;

COMMENT ON VIEW mart.gunluk_marj IS
  'Gunluk marj merdiveni: ciro -> brut -> katki (kargo dusulmus) -> reklam sonrasi. COGS bilinmiyorsa NULL.';

-- --------------------------------------------------------------------------
-- Maliyeti eksik olan satan urunler  (acik is)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.maliyet_eksik AS
SELECT
  k.urun_id,
  k.urun_adi,
  k.sku,
  count(*)              AS satilan_kalem,
  sum(k.adet)           AS satilan_adet,
  sum(k.satir_ciro)     AS olculemeyen_ciro,
  max(k.gun)            AS son_satis
FROM mart.siparis_kalem k
WHERE NOT k.maliyeti_biliniyor AND k.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
GROUP BY 1,2,3
ORDER BY sum(k.satir_ciro) DESC;

COMMENT ON VIEW mart.maliyet_eksik IS
  'Satmis ama maliyeti girilmemis urunler, ciroya gore sirali - once en cok satan girilsin.';

COMMIT;
