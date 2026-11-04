-- =============================================================================
-- L'CARLIE - MART: REKLAM VERIMLILIGI  (CR-005 Faz 3)
--
-- 🔴 BURADAKI RAKAMLAR **ATIF DEGILDIR**.
--    Hesaplanan sey KARMA (blended) orandir: gunun TUM cirosu / gunun TUM
--    reklam harcamasi. "Bu satisi su reklam getirdi" demez ve diyemez -
--    oyle demek icin tiklama-siparis eslestirmesi gerekir, o ayri bir is.
--    Meta'nin kendi atifli rakami raw.meta_harcama.meta_donusum_degeri'nde
--    AYRI durur; ikisi TOPLANMAZ, birbirinin yerine KULLANILMAZ.
--    Kolon adlari bu yuzden 'karma_' onekli: okuyan yanilmasin.
--
-- 🔴 CIRO IKIYE AYRI OLDUGU ICIN ORAN DA IKIYE AYRI.
--    Tek bir ROAS uretmek, dogrulanmamis parayi dogrulanmis gibi gosterir.
--
-- 🔴 SIFIRA BOLME: harcama 0 ise oran NULL doner, 0 DEGIL. "Oran sifir"
--    ile "oran hesaplanamaz" ayri seylerdir.
--
-- 🔴 KAR/MARJ YOK. COGS hala bagli degil (source_authority: cogs=NONE).
--    Harcama bilinmesi marj hesaplamaya yetmez - urun maliyeti de lazim.
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Gunluk harcama ozeti
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.harcama AS
SELECT h.gun,
       h.hesap_id,
       coalesce(a.ad, h.hesap_id)  AS hesap_adi,
       h.kampanya_id,
       h.kampanya_adi,
       h.kaynak,
       h.harcama,
       h.gosterim,
       h.tiklama,
       h.link_tiklama,
       h.meta_donusum,
       h.meta_donusum_degeri,
       (h.gun >= (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date) AS olcumde
  FROM raw.meta_harcama h
  LEFT JOIN raw.meta_hesap a ON a.hesap_id = h.hesap_id
 WHERE h.kampanya_id <> '_HESAP';   -- hesap toplami ayri satir, cift saymayi onler

COMMENT ON VIEW mart.harcama IS
  'Gun x kampanya harcama. _HESAP satirlari haric tutulur (cift sayim).';

-- --------------------------------------------------------------------------
-- Gunluk verimlilik  (mart.gunluk'un yanina, ONU DEGISTIRMEDEN)
-- --------------------------------------------------------------------------
-- 🔴 mart.gunluk'a kolon EKLEMEK yerine ayri view: CR-004'te kurulan
--    gorunumun kolon sirasina bagli bir sey varsa bozulmasin, ve
--    "ciro" ile "reklam" ayri okunabilsin.
CREATE OR REPLACE VIEW mart.gunluk_verimlilik AS
WITH hrc AS (
  SELECT gun,
         sum(harcama)             AS harcama,
         sum(gosterim)            AS gosterim,
         sum(link_tiklama)        AS link_tiklama,
         sum(meta_donusum_degeri) AS meta_iddia_gelir
    FROM raw.meta_harcama
   WHERE kampanya_id <> '_HESAP'
   GROUP BY gun
), yeni AS (
  -- O gun ILK siparisini veren musteri = yeni musteri.
  -- 🔴 Ilk gun IC sorguda hesaplanir: disarida "GROUP BY min(...)" yazmak
  --    "aggregate functions are not allowed in GROUP BY" hatasi verir.
  SELECT ilk_gun AS gun, count(*) AS yeni_musteri
    FROM (SELECT customer_id,
                 (min(olusturma) AT TIME ZONE 'Europe/Istanbul')::date AS ilk_gun
            FROM mart.siparis
           WHERE customer_id IS NOT NULL AND ciro_sinifi <> 'IPTAL'
           GROUP BY customer_id) t
   GROUP BY 1
)
SELECT
  coalesce(g.gun, hrc.gun, yeni.gun)                        AS gun,
  coalesce(g.ciro_dogrulanmis, 0)                           AS ciro_dogrulanmis,
  coalesce(g.ciro_beyan_edilmis, 0)                         AS ciro_beyan_edilmis,
  coalesce(hrc.harcama, 0)                                  AS reklam_harcamasi,
  coalesce(hrc.gosterim, 0)                                 AS gosterim,
  coalesce(hrc.link_tiklama, 0)                             AS link_tiklama,
  coalesce(yeni.yeni_musteri, 0)                            AS yeni_musteri,

  -- 🔴 IKI AYRI ORAN. Tek 'roas' kolonu bilerek YOK.
  --    nullif(): harcama 0 iken NULL doner - "hesaplanamaz" demektir.
  round(coalesce(g.ciro_dogrulanmis,0) / nullif(hrc.harcama,0), 2)
                                                            AS karma_roas_dogrulanmis,
  round((coalesce(g.ciro_dogrulanmis,0) + coalesce(g.ciro_beyan_edilmis,0))
        / nullif(hrc.harcama,0), 2)                         AS karma_roas_beyan_dahil,

  -- Yeni musteri basina reklam maliyeti (karma CAC)
  round(hrc.harcama / nullif(yeni.yeni_musteri,0), 2)       AS karma_musteri_maliyeti,

  -- Meta'nin KENDI iddiasi - karsilastirma icin, kullanmak icin degil
  coalesce(hrc.meta_iddia_gelir, 0)                         AS meta_iddia_gelir,
  coalesce(g.gonderi_alarm, 0)                              AS gonderi_alarm
FROM mart.gunluk g
FULL OUTER JOIN hrc  ON hrc.gun  = g.gun
FULL OUTER JOIN yeni ON yeni.gun = coalesce(g.gun, hrc.gun)
WHERE coalesce(g.gun, hrc.gun, yeni.gun)
      >= (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date
ORDER BY 1;

COMMENT ON VIEW mart.gunluk_verimlilik IS
  'Gunluk ciro + reklam. Oranlar KARMA (blended), ATIF DEGIL. Harcama 0 ise oran NULL - "hesaplanamaz".';

-- --------------------------------------------------------------------------
-- Acik isler: reklam tarafi
-- --------------------------------------------------------------------------
-- 🔴 "Harcama var, ciro yok" bir ARIZA sinyalidir; sessiz gecilmez.
--    Ama tek gunluk dalgalanma alarm degildir - 3 gunluk pencereye bakilir.
CREATE OR REPLACE VIEW mart.harcama_uyari AS
WITH p AS (
  SELECT gun,
         sum(reklam_harcamasi) OVER (ORDER BY gun ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS h3,
         sum(ciro_dogrulanmis + ciro_beyan_edilmis) OVER (ORDER BY gun ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS c3
    FROM mart.gunluk_verimlilik
)
SELECT gun, h3 AS son3gun_harcama, c3 AS son3gun_ciro
  FROM p
 WHERE h3 > 0 AND c3 = 0;

COMMENT ON VIEW mart.harcama_uyari IS
  '3 gun ust uste harcama var ama hic ciro yok. Tek gunluk bosluk uyari SAYILMAZ.';

COMMIT;
