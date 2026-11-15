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
  'YALNIZ WIX kalemleri (raw.wix_order). Tum kanallar: mart.satis_kalem_tum. Maliyet SIPARIS TARIHINDE gecerli olandir. Bilinmiyorsa marj NULL.';

-- ==========================================================================
-- K1 (sahip 15.11.2026 "bagla"): TUM KANALLARIN SATIS KALEMI
--
-- 🔴 mart.siparis_kalem BILEREK Wix'te kaldi: ona bagli 10+ view raw.wix_order'a
--    join'liyor ve reklam defteri (077, baska oturum) pazaryerini core.alici_siparis'ten
--    AYRICA ekliyor -> pazaryeri satirlarini oraya koymak Trendyol'u IKI KEZ sayardi.
--    Kar zinciri (urun_karlilik, gunluk_marj, maliyet_eksik, siparis_ekonomi ->
--    ekonomi_gunluk -> ticari_yasayabilirlik) artik BU view'dan okur.
--
-- 🔴 AYNI SIPARIS UC KAYNAKTA OLABILIR - oncelik (cift sayim yok):
--      trendyol: core.jarvis_channel_sale (finans: hakedis satiri, indirim+iade dahil)
--              > core.alici_siparis (Trendyol 'price' = ODENEN)
--              > core.pazaryeri_siparis (yalniz 'amount' = LISTE FIYATI -> ciro NULL, uydurulmaz)
--      idefix/n11/hepsiburada: alici_siparis > pazaryeri_siparis (paket tekrarlari tek)
--      wix: yalniz raw.wix_order (diger kaynaklardaki wix satirlari ALINMAZ)
--      elle: core.gonderi_notu SATIS (siparis_ref yok) + mart.gonderi ELLE_SATIS (kapida, Wix kaydi yok)
--    Hangi siparisin hangi kaynaktan alindigi: mart.satis_kaynak_mutabakat.
--
-- 🔴 L'CARLIE disi urun (Trendyol magazasindaki Schussler/Dr. Tuzlari - klinigin,
--    channel_sale.business='lemos'; barkodu 868486960... olmayan kalem) BU VIEW'A GIRMEZ.
--
-- 🔴 KOMISYON KDV DAHIL ODENEN TUTAR UZERINDEN (pazaryeri komisyonu satis fiyatina
--    uygulanir; komisyon faturasinin KDV'si indirilir -> maliyet = odenen x yuzde).
--    Pazaryeri: core.urun_platform_komisyon; yoksa NULL (VERI_YOK, uydurulmaz).
--    Wix: POS %5 core.maliyet_bileseni POS_KOMISYONU (sahip 14.10) YALNIZ PayTR
--    (kart) siparisine; havale/kapida 0 (beyanin kendisi: "uygulanmaz").
-- ==========================================================================
CREATE OR REPLACE FUNCTION core.ad_anahtar(p text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  -- Turkce harfler ONCE ceviriliyor: upper('ı') yerel ayara gore 'ı' kalabiliyor
  -- (turkce-metin-eslesme-tuzagi). Sonra yalniz A-Z0-9.
  SELECT regexp_replace(upper(translate(coalesce(p, ''), 'çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')), '[^A-Z0-9]', '', 'g')
$$;

CREATE OR REPLACE FUNCTION core.urun_id_ad(p text) RETURNS text
LANGUAGE sql STABLE AS $$
  -- Serbest metin urun adi -> Wix productId. "KINESIS + (Sporcu...)", "Seralımbo (gece...)",
  -- finans adi "Cal Jaw". En uzun urun kodu kazanir. Eslesmezse NULL (tahmin yok).
  SELECT k.urun_id
    FROM core.urun_kimlik k
   WHERE core.ad_anahtar(p) <> ''
     AND (core.ad_anahtar(p) LIKE core.ad_anahtar(k.urun_kod) || '%'
          OR core.ad_anahtar(p) = core.ad_anahtar(k.finans_ad))
   ORDER BY length(core.ad_anahtar(k.urun_kod)) DESC
   LIMIT 1
$$;

CREATE OR REPLACE FUNCTION core.urun_id_barkod(p text) RETURNS text
LANGUAGE sql STABLE AS $$
  SELECT k.urun_id FROM core.urun_kimlik k
   WHERE p IS NOT NULL AND (k.barkod = p OR k.pazaryeri_barkod = p)
   ORDER BY (k.barkod = p) DESC LIMIT 1
$$;

CREATE OR REPLACE VIEW mart.satis_kalem_tum AS
WITH
cs AS (   -- Trendyol hakedis satirlari, siparis x urun satiri
  SELECT c.order_no, c.item,
         min(c.sale_date) AS gun,
         max(c.product) FILTER (WHERE c.kind IN ('sale','return')) AS product,
         sum(c.quantity) FILTER (WHERE c.kind = 'sale') AS adet,
         round(sum(c.gross_cents) FILTER (WHERE c.kind = 'sale') / 100.0, 2) AS liste,
         round(sum(c.gross_cents) / 100.0, 2) AS odenen,
         round(sum(c.net_cents) / 100.0, 2) AS odenen_net,
         bool_or(c.kind = 'return') AS iade,
         row_number() OVER (PARTITION BY c.order_no ORDER BY c.item) AS sira
    FROM core.jarvis_channel_sale c
   WHERE c.channel = 'trendyol' AND c.business = 'lcarlie' AND c.kind <> 'shipping'
   GROUP BY c.order_no, c.item
),
cs_sip AS (SELECT DISTINCT order_no FROM core.jarvis_channel_sale WHERE channel = 'trendyol'),
a AS (    -- alici_siparis (Trendyol price / Idefix odenen), finans satiri olmayanlar
  SELECT a.kanal, a.siparis_no, a.zaman, a.durum, a.liste_tutar,
         jsonb_array_length(coalesce(a.kalemler, '[]'::jsonb)) AS kalem_sayisi,
         k.value AS kalem, k.ordinality AS sira
    FROM core.alici_siparis a
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.kalemler, '[]'::jsonb)) WITH ORDINALITY k(value, ordinality)
   WHERE a.kanal <> 'wix'
     AND NOT (a.kanal = 'trendyol' AND a.siparis_no IN (SELECT order_no FROM cs_sip))
),
p AS (    -- pazaryeri_siparis: yalniz baska kaynakta olmayan; paket tekrari tek satir
  SELECT DISTINCT ON (p.kanal, p.siparis_no)
         p.kanal, p.siparis_no, p.siparis_zamani, p.durum, p.tutar, p.kalemler
    FROM core.pazaryeri_siparis p
   WHERE p.kanal <> 'wix'
     AND NOT EXISTS (SELECT 1 FROM core.alici_siparis a WHERE a.kanal = p.kanal AND a.siparis_no = p.siparis_no)
     AND NOT (p.kanal = 'trendyol' AND p.siparis_no IN (SELECT order_no FROM cs_sip))
   ORDER BY p.kanal, p.siparis_no, (p.paket_no IS NOT NULL) DESC, p.son_guncelleme DESC
),
ham AS (
  -- WIX
  SELECT 'wix'::text AS kanal, 'WIX_API'::text AS kaynak, k.siparis_id, s.siparis_no::text AS siparis_no,
         k.sira, k.olusturma, k.ciro_sinifi, s.teslimat_durumu AS durum,
         k.urun_id, k.urun_adi AS kaynak_urun_adi, NULL::text AS kaynak_barkod,
         k.adet, k.satir_ciro, k.satir_ciro_net, k.satir_brut AS liste_tutar,
         'ODENEN'::text AS tutar_kaynagi, s.odeme_yontemi
    FROM mart.siparis_kalem k JOIN mart.siparis s ON s.siparis_id = k.siparis_id
  UNION ALL
  -- TRENDYOL: finans hakedis satiri
  SELECT 'trendyol', 'FINANS_KANAL_SATISI', 'trendyol:' || cs.order_no, cs.order_no,
         cs.sira::int, coalesce(al.zaman, (cs.gun::timestamp AT TIME ZONE 'Europe/Istanbul')),
         CASE WHEN cs.iade THEN 'IPTAL' ELSE 'DOGRULANMIS' END,
         CASE WHEN cs.iade THEN 'IADE' ELSE coalesce(al.durum, 'HAKEDIS') END,
         core.urun_id_ad(cs.product), coalesce(nullif(cs.product, ''), cs.item), NULL,
         cs.adet, cs.odenen, round(cs.odenen_net, 2), cs.liste,
         'ODENEN', NULL
    FROM cs LEFT JOIN core.alici_siparis al ON al.kanal = 'trendyol' AND al.siparis_no = cs.order_no
  UNION ALL
  -- PAZARYERI: alici_siparis kalemi (tutar = odenen)
  SELECT a.kanal, 'ALICI_SIPARIS', a.kanal || ':' || a.siparis_no, a.siparis_no,
         a.sira::int, a.zaman,
         CASE WHEN lower(coalesce(a.durum, '')) ~ '(cancel|unsupplied|return|iptal|iade|refund)' THEN 'IPTAL'
              WHEN lower(coalesce(a.durum, '')) ~ 'deliver' THEN 'DOGRULANMIS'
              ELSE 'BEYAN_EDILMIS' END,
         a.durum,
         coalesce(core.urun_id_barkod(a.kalem ->> 'barkod'), core.urun_id_ad(a.kalem ->> 'kod')),
         a.kalem ->> 'kod', nullif(a.kalem ->> 'barkod', ''),
         (a.kalem ->> 'adet')::numeric, (a.kalem ->> 'tutar')::numeric,
         round((a.kalem ->> 'tutar')::numeric / 1.20, 2),
         CASE WHEN a.kalem_sayisi = 1 THEN a.liste_tutar END,
         'ODENEN', NULL
    FROM a
  UNION ALL
  -- PAZARYERI: yalniz pazaryeri_siparis (Trendyol tutari LISTE FIYATI -> kullanilmaz)
  SELECT p.kanal, 'PAZARYERI_SIPARIS', p.kanal || ':' || p.siparis_no, p.siparis_no,
         k.ordinality::int, p.siparis_zamani,
         CASE WHEN lower(coalesce(p.durum, '')) ~ '(cancel|unsupplied|return|iptal|iade|refund)' THEN 'IPTAL'
              WHEN lower(coalesce(p.durum, '')) ~ 'deliver' THEN 'DOGRULANMIS'
              ELSE 'BEYAN_EDILMIS' END,
         p.durum,
         coalesce(core.urun_id_barkod(k.value ->> 'barkod'), core.urun_id_ad(k.value ->> 'ad')),
         k.value ->> 'ad', nullif(k.value ->> 'barkod', ''),
         (k.value ->> 'adet')::numeric,
         CASE WHEN p.kanal <> 'trendyol' AND jsonb_array_length(p.kalemler) = 1 THEN p.tutar END,
         CASE WHEN p.kanal <> 'trendyol' AND jsonb_array_length(p.kalemler) = 1 THEN round(p.tutar / 1.20, 2) END,
         CASE WHEN p.kanal = 'trendyol' AND jsonb_array_length(p.kalemler) = 1 THEN p.tutar END,
         CASE WHEN p.kanal = 'trendyol' THEN 'LISTE_FIYATI_KULLANILMADI'
              WHEN jsonb_array_length(p.kalemler) = 1 THEN 'PAZARYERI_SIPARIS_TUTARI'
              ELSE 'SATIR_TUTARI_YOK' END,
         NULL
    FROM p CROSS JOIN LATERAL jsonb_array_elements(p.kalemler) WITH ORDINALITY k(value, ordinality)
  UNION ALL
  -- WIX: gunluk cekimden (08:30) SONRA gelen siparis, raw.wix_order'a girene kadar
  --      core.alici_siparis'ten (15 dk). Cekim gelince bu satir kendiliginden duser
  --      (siparis_no ile) -> cift sayim yok. alici_siparis Wix kalem tutari 0 geliyor:
  --      tek kalemli sipariste siparis tutari, cok kalemlide NULL (uydurulmaz).
  SELECT 'wix', 'ALICI_SIPARIS', 'wix:' || a.siparis_no, a.siparis_no,
         k.ordinality::int, a.zaman,
         CASE WHEN lower(coalesce(a.durum, '')) ~ '(cancel|refund|iptal|iade)' THEN 'IPTAL'
              WHEN upper(coalesce(a.durum, '')) = 'PAID' THEN 'BEYAN_EDILMIS'
              ELSE 'ODENMEDI' END,
         a.durum,
         coalesce(core.urun_id_barkod(k.value ->> 'barkod'), core.urun_id_ad(k.value ->> 'kod')),
         k.value ->> 'kod', nullif(k.value ->> 'barkod', ''),
         (k.value ->> 'adet')::numeric,
         CASE WHEN jsonb_array_length(a.kalemler) = 1 THEN a.tutar END,
         CASE WHEN jsonb_array_length(a.kalemler) = 1 THEN round(a.tutar / 1.20, 2) END,
         CASE WHEN jsonb_array_length(a.kalemler) = 1 THEN a.liste_tutar END,
         CASE WHEN jsonb_array_length(a.kalemler) = 1 THEN 'ODENEN' ELSE 'SATIR_TUTARI_YOK' END,
         NULL
    FROM core.alici_siparis a
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.kalemler, '[]'::jsonb)) WITH ORDINALITY k(value, ordinality)
   WHERE a.kanal = 'wix'
     AND NOT EXISTS (SELECT 1 FROM raw.wix_order w WHERE w.siparis_no::text = a.siparis_no)
  UNION ALL
  -- ELLE: panelden girilen satis notu (insan beyani)
  SELECT 'elle', 'GONDERI_NOTU', 'elle:not-' || n.not_id, n.not_id::text,
         1, n.girildi, 'BEYAN_EDILMIS',
         coalesce(n.kanal, 'BILINMIYOR'),
         core.urun_id_ad(n.urun_adi), n.urun_adi, NULL,
         n.adet, n.elle_fiyat, round(n.elle_fiyat / 1.20, 2), NULL,
         CASE WHEN n.elle_fiyat IS NULL THEN 'BEYAN_TUTAR_YOK' ELSE 'BEYAN' END, NULL
    FROM core.gonderi_notu n
   WHERE n.tur = 'SATIS' AND n.siparis_ref IS NULL
  UNION ALL
  -- ELLE: kapida odeme + Wix kaydi yok (BasitKargo). Tahsil edilmeyen ciro DEGIL.
  SELECT 'elle', 'BASITKARGO_KAPIDA', 'elle:bk-' || g.gonderi_id, g.gonderi_id,
         1, g.olusturma,
         CASE WHEN g.cod_durum = 'TRANSFERRED' THEN 'DOGRULANMIS' ELSE 'ODENMEDI' END,
         g.cod_durum,
         CASE WHEN cardinality(g.urun_adlari) = 1 THEN core.urun_id_ad(g.urun_adlari[1]) END,
         array_to_string(g.urun_adlari, ' + '), g.barkod,
         CASE WHEN cardinality(g.urun_adlari) = 1 THEN 1 END,
         g.cod_tutar, round(g.cod_tutar / 1.20, 2), NULL,
         'KAPIDA_TAHSILAT', 'KAPIDA'
    FROM mart.gonderi g
   WHERE g.sinif = 'ELLE_SATIS'
     AND NOT EXISTS (SELECT 1 FROM core.gonderi_notu n WHERE n.tur = 'SATIS' AND n.siparis_ref = g.gonderi_id)
),
z AS (
  SELECT h.*,
         ui.urun_kod, ui.barkod AS kimlik_barkod, wu.ad AS wix_ad, wu.sku AS wix_sku,
         -- 🔴 L'CARLIE kalemi mi: urun eslesti VEYA barkod 868486960 onekli VEYA Wix/elle
         (h.kanal IN ('wix','elle') OR h.urun_id IS NOT NULL OR h.kaynak = 'FINANS_KANAL_SATISI'
          OR h.kaynak_barkod LIKE '868486960%') AS lcarlie,
         -- POS %5 beyani 14.10'da girildi; oran sozlesmenin kendisi, o tarihten once de gecerli
         -- (ayni PayTR). Siparis aninda kayit yoksa EN ESKI acik POS kaydi kullanilir; beyan degistirilmez.
         coalesce((SELECT b.deger FROM core.bilesen_bul('POS_KOMISYONU', h.olusturma) b),
                  (SELECT m.deger FROM core.maliyet_bileseni m WHERE m.bilesen = 'POS_KOMISYONU'
                      AND m.gecerli_bitis IS NULL ORDER BY m.gecerli_baslangic LIMIT 1)) AS pos_yuzde,
         (SELECT b.deger FROM core.bilesen_bul('KANAL_KOMISYONU', h.olusturma) b) AS wix_kanal_yuzde,
         upk.komisyon_yuzde AS pazaryeri_yuzde
    FROM ham h
    LEFT JOIN core.urun_kimlik ui ON ui.urun_id = h.urun_id
    LEFT JOIN raw.wix_urun wu ON wu.urun_id = h.urun_id
    LEFT JOIN core.urun_platform_komisyon upk ON upk.urun_id = h.urun_id AND upk.platform_kod = h.kanal
),
y AS (
  SELECT z.*,
         CASE WHEN z.kanal = 'wix' THEN CASE WHEN z.odeme_yontemi = 'PayTR' THEN z.pos_yuzde
                                             WHEN z.odeme_yontemi IS NULL THEN NULL   -- bilinmiyor, 0 degil
                                             ELSE 0 END
              ELSE 0 END AS odeme_komisyon_yuzde,
         CASE WHEN z.kanal = 'wix' THEN z.wix_kanal_yuzde
              WHEN z.kanal = 'elle' THEN 0
              ELSE z.pazaryeri_yuzde END AS kanal_komisyon_yuzde,
         core.maliyet_bul(z.urun_id, z.olusturma) AS birim_maliyet
    FROM z WHERE z.lcarlie
)
SELECT
  y.kanal,
  y.kaynak,
  y.siparis_id,
  y.siparis_no,
  y.sira,
  (y.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
  y.olusturma,
  y.ciro_sinifi,
  y.olusturma >= mart.kesim()                  AS olcumde,
  y.durum,
  y.urun_id,
  y.urun_kod,
  coalesce(y.wix_ad, y.kaynak_urun_adi)       AS urun_adi,
  coalesce(y.wix_sku, y.kaynak_barkod)        AS sku,
  coalesce(y.kaynak_barkod, y.kimlik_barkod)  AS barkod,
  y.adet,
  y.satir_ciro,                                -- 🔴 KDV DAHIL, musterinin ODEDIGI (liste degil)
  y.satir_ciro_net,                            -- KDV HARIC (pazaryeri/elle: /1,20 - kozmetik %20)
  y.liste_tutar,                               -- bilgi: indirim oncesi; hesaba GIRMEZ
  y.tutar_kaynagi,
  y.odeme_yontemi,
  y.odeme_komisyon_yuzde,
  y.kanal_komisyon_yuzde,
  round(y.satir_ciro * y.odeme_komisyon_yuzde / 100.0, 2) AS odeme_komisyonu,
  round(y.satir_ciro * y.kanal_komisyon_yuzde / 100.0, 2) AS kanal_komisyonu,
  CASE WHEN y.kanal = 'wix' AND y.odeme_komisyon_yuzde IS NULL THEN 'VERI_YOK'
       WHEN y.kanal NOT IN ('wix') AND y.kanal_komisyon_yuzde IS NULL THEN 'VERI_YOK'
       WHEN y.kanal = 'wix' AND y.kanal_komisyon_yuzde IS NULL THEN 'WIX_KANAL_BEYANSIZ'
       ELSE 'GIRILDI' END                       AS komisyon_durumu,
  y.birim_maliyet,
  y.birim_maliyet * y.adet                    AS satir_maliyet,
  CASE WHEN y.birim_maliyet IS NOT NULL AND y.satir_ciro_net IS NOT NULL
       THEN y.satir_ciro_net - y.birim_maliyet * y.adet END AS brut_marj,
  (y.birim_maliyet IS NOT NULL AND y.adet IS NOT NULL) AS maliyeti_biliniyor,
  -- kalem katkisi: brut marj - bilinen komisyonlar (kargo siparis duzeyinde, burada YOK)
  CASE WHEN y.birim_maliyet IS NOT NULL AND y.satir_ciro_net IS NOT NULL
       THEN round(y.satir_ciro_net - y.birim_maliyet * y.adet
                  - coalesce(y.satir_ciro * y.odeme_komisyon_yuzde / 100.0, 0)
                  - coalesce(y.satir_ciro * y.kanal_komisyon_yuzde / 100.0, 0), 2) END AS katki_kargo_oncesi
FROM y;

COMMENT ON VIEW mart.satis_kalem_tum IS
  'K1 15.11.2026: TUM kanallarin L''CARLIE satis kalemi (wix, trendyol, idefix, n11, hepsiburada, elle). Tutar ODENEN (Trendyol liste fiyati kullanilmaz). Kaynak onceligi ve cift sayim: mart.satis_kaynak_mutabakat. Kar zincirinin girdisi.';

-- Reklam / panel icin "gercek siparis ve ciro": gun x kanal (IPTAL ve odenmemis HARIC)
CREATE OR REPLACE VIEW mart.satis_kanal_gunluk AS
SELECT k.gun, k.kanal,
       count(DISTINCT k.siparis_id)                AS siparis,
       round(sum(k.satir_ciro), 2)                 AS ciro,          -- KDV dahil, ODENEN
       sum(k.adet)                                 AS adet,
       round(sum(k.satir_ciro_net), 2)             AS ciro_net,
       round(sum(k.satir_maliyet), 2)              AS cogs,
       round(sum(coalesce(k.odeme_komisyonu, 0) + coalesce(k.kanal_komisyonu, 0)), 2) AS komisyon,
       round(sum(k.katki_kargo_oncesi), 2)         AS katki_kargo_oncesi,
       count(*) FILTER (WHERE k.satir_ciro IS NULL)      AS tutari_bilinmeyen_kalem,
       count(*) FILTER (WHERE NOT k.maliyeti_biliniyor)  AS maliyeti_bilinmeyen_kalem,
       count(*) FILTER (WHERE k.komisyon_durumu = 'VERI_YOK') AS komisyonu_bilinmeyen_kalem
  FROM mart.satis_kalem_tum k
 WHERE k.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
 GROUP BY k.gun, k.kanal;

COMMENT ON VIEW mart.satis_kanal_gunluk IS
  'K1: gercek siparis/ciro gun x kanal (ciro = odenen KDV dahil; iptal/iade/odenmemis haric, cift sayimsiz). Reklam sayfasi (satis_sorgulari defter_gunluk) buradan okur.';

-- gun x kanal x urun (reklam sayfasi "defter" bicimi: gun, kanal, barkod, kod, siparis, adet, ciro)
CREATE OR REPLACE VIEW mart.satis_urun_gunluk AS
SELECT k.gun, k.kanal, k.barkod,
       coalesce(k.urun_kod, upper(k.urun_adi))     AS kod,
       count(DISTINCT k.siparis_id)                AS siparis,
       sum(k.adet)                                 AS adet,
       round(sum(k.satir_ciro), 2)                 AS ciro,          -- KDV dahil, ODENEN
       round(sum(k.satir_ciro_net), 2)             AS ciro_net,
       round(sum(k.satir_maliyet), 2)              AS cogs,
       round(sum(coalesce(k.odeme_komisyonu, 0) + coalesce(k.kanal_komisyonu, 0)), 2) AS komisyon,
       round(sum(k.katki_kargo_oncesi), 2)         AS katki_kargo_oncesi,
       k.urun_id
  FROM mart.satis_kalem_tum k
 WHERE k.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
 GROUP BY k.gun, k.kanal, k.barkod, coalesce(k.urun_kod, upper(k.urun_adi)), k.urun_id;

COMMENT ON VIEW mart.satis_urun_gunluk IS
  'K1: gercek satis gun x kanal x urun (ciro = odenen KDV dahil, iptal/iade/odenmemis haric). Reklam sayfasi (satis_sorgulari defter) buradan okur.';

-- Satis kaydinin tazeligi: core.alici_siparis (15 dk; Wix + pazaryeri, gunluk Wix cekimini
-- bekleyen siparisler de buradan). Wix gunluk cekimi ve finans hakedisi ayri sutunda.
CREATE OR REPLACE VIEW mart.satis_tazelik AS
SELECT (SELECT max(guncellendi) FROM core.alici_siparis)        AS son_olcum,
       (SELECT max(cekim_at) FROM raw.wix_order)                AS wix_son,
       (SELECT max(guncellendi) FROM core.alici_siparis)        AS pazaryeri_son,
       (SELECT max(son_guncelleme) FROM core.pazaryeri_siparis) AS nobetci_son,
       (SELECT max(fetched_at) FROM core.jarvis_channel_sale)   AS finans_hakedis_son;

-- Hangi pazaryeri siparisi hangi kaynaktan alindi (cift sayim denetimi)
CREATE OR REPLACE VIEW mart.satis_kaynak_mutabakat AS
WITH s AS (
  SELECT 'trendyol'::text AS kanal, order_no AS siparis_no, 'FINANS_KANAL_SATISI'::text AS kaynak,
         sum(gross_cents) / 100.0 AS tutar, bool_or(business = 'lcarlie') AS lcarlie
    FROM core.jarvis_channel_sale WHERE channel = 'trendyol' GROUP BY order_no
  UNION ALL
  SELECT kanal, siparis_no, 'ALICI_SIPARIS', tutar, NULL FROM core.alici_siparis WHERE kanal <> 'wix'
  UNION ALL
  SELECT kanal, siparis_no, 'PAZARYERI_SIPARIS', max(tutar), NULL
    FROM core.pazaryeri_siparis WHERE kanal <> 'wix' GROUP BY kanal, siparis_no
)
SELECT s.kanal, s.siparis_no,
       string_agg(s.kaynak || '=' || coalesce(round(s.tutar, 2)::text, '?'), ' | ' ORDER BY s.kaynak) AS kaynaklar,
       count(*) AS kaynak_sayisi,
       (SELECT min(k.kaynak) FROM mart.satis_kalem_tum k WHERE k.kanal = s.kanal AND k.siparis_no = s.siparis_no) AS secilen_kaynak,
       (SELECT round(sum(k.satir_ciro), 2) FROM mart.satis_kalem_tum k WHERE k.kanal = s.kanal AND k.siparis_no = s.siparis_no) AS sayilan_odenen,
       CASE WHEN bool_and(s.lcarlie) IS FALSE THEN 'LCARLIE_DISI (klinik urunu, kar zincirine girmez)'
            WHEN NOT EXISTS (SELECT 1 FROM mart.satis_kalem_tum k WHERE k.kanal = s.kanal AND k.siparis_no = s.siparis_no)
            THEN 'ALINMADI (L''CARLIE kalemi yok)'
            ELSE 'ALINDI' END AS sonuc
  FROM s GROUP BY s.kanal, s.siparis_no;

COMMENT ON VIEW mart.satis_kaynak_mutabakat IS
  'K1: pazaryeri siparisi x kaynaklar (finans/alici/pazaryeri) ve hangisinin sayildigi. Bir siparis tek kez sayilir.';

-- --------------------------------------------------------------------------
-- Urun bazinda karlilik
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.urun_karlilik AS
-- 🔴 15.11.2026 K1: TUM KANALLAR (mart.satis_kalem_tum). Onceki hali yalniz Wix'ti;
--    Trendyol/Idefix satisi urun karliliginda hic yoktu. Ilk 12 sutunun ANLAMI ayni
--    (ciro = odenen, KDV dahil), kapsami genisledi; kanal kirilimi sondaki sutunlarda.
SELECT
  k.urun_id,
  k.urun_adi,
  k.sku,
  count(*)                                   AS kalem,
  sum(k.adet)                                AS adet,
  sum(k.satir_ciro)                          AS ciro,        -- KDV dahil, ODENEN
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
        / nullif(sum(k.satir_ciro), 0), 1)   AS kapsama_yuzde,
  -- K1 ekleri (CREATE OR REPLACE yalniz SONA sutun ekleyebilir)
  round(sum(coalesce(k.odeme_komisyonu, 0) + coalesce(k.kanal_komisyonu, 0)), 2) AS komisyon,
  round(sum(k.katki_kargo_oncesi), 2)        AS katki_kargo_oncesi,
  count(*) FILTER (WHERE k.komisyon_durumu = 'VERI_YOK') AS komisyonu_bilinmeyen_kalem,
  coalesce(sum(k.adet) FILTER (WHERE k.kanal = 'wix'), 0)       AS wix_adet,
  coalesce(sum(k.adet) FILTER (WHERE k.kanal NOT IN ('wix','elle')), 0) AS pazaryeri_adet,
  coalesce(sum(k.adet) FILTER (WHERE k.kanal = 'elle'), 0)      AS elle_adet,
  round(coalesce(sum(k.satir_ciro_net) FILTER (WHERE k.kanal = 'wix'), 0), 2) AS wix_ciro_net,
  round(coalesce(sum(k.satir_ciro_net) FILTER (WHERE k.kanal NOT IN ('wix','elle')), 0), 2) AS pazaryeri_ciro_net,
  string_agg(DISTINCT k.kanal, ',')          AS kanallar
FROM mart.satis_kalem_tum k
-- 🔴 IPTAL **ve ODENMEDI** haric.  Onceki hali yalniz IPTAL'i eliyordu;
--    odenmemis siparis mart.gunluk'ta "tutar_bekleyen" sayilirken burada
--    "ciro" sayiliyordu. Ayni gun icin iki view iki farkli ciro veriyordu
--    ve marj tahsil EDILMEMIS parayla hesaplaniyordu.
WHERE k.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
GROUP BY 1,2,3;

COMMENT ON VIEW mart.urun_karlilik IS
  'Urun bazinda karlilik, TUM kanallar (K1 15.11.2026). kapsama_yuzde okunmadan brut_marj_yuzde yorumlanmaz.';

-- --------------------------------------------------------------------------
-- Gunluk marj  (kargo ve reklam dahil)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.gunluk_marj AS
WITH k AS (
  -- 🔴 15.11.2026 K1: TUM KANALLAR. Komisyon (pazaryeri + Wix POS) artik katkidan dusulur.
  --    Pazaryeri KARGOSU (Trendyol hakedisten kesilir) VERI_YOK -> burada YOK;
  --    o yuzden pazaryeri katkisi bir UST SINIRDIR (siparis_ekonomi kritik_eksik'te yazar).
  SELECT gun,
         sum(satir_ciro)                                   AS ciro,
         sum(satir_ciro_net)                               AS ciro_net,
         sum(satir_maliyet)                                AS cogs,
         sum(brut_marj)                                    AS brut_marj,
         sum(satir_ciro_net) FILTER (WHERE maliyeti_biliniyor) AS ciro_olculen,
         sum(odeme_komisyonu)                              AS odeme_komisyonu,
         sum(kanal_komisyonu)                              AS kanal_komisyonu,
         count(*) FILTER (WHERE komisyon_durumu = 'VERI_YOK') AS komisyon_bilinmeyen,
         sum(satir_ciro_net) FILTER (WHERE kanal = 'wix')  AS wix_ciro_net,
         sum(satir_ciro_net) FILTER (WHERE kanal NOT IN ('wix','elle')) AS pazaryeri_ciro_net,
         sum(satir_ciro_net) FILTER (WHERE kanal = 'elle') AS elle_ciro_net
    FROM mart.satis_kalem_tum
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
       THEN round(k.brut_marj - coalesce(k.odeme_komisyonu, 0) - coalesce(k.kanal_komisyonu, 0)
                  - coalesce(kg.kargo, 0), 2) END AS katki_marji,
  -- 🔴 Reklam sonrasi rakamda TUM kargo dusulur - siniflandirilmamis ve
  --    iade dahil. O paralar gercekten odendi; sinifi bilinmiyor diye
  --    yok sayilamaz.
  CASE WHEN k.brut_marj IS NOT NULL
       THEN round(k.brut_marj - coalesce(k.odeme_komisyonu, 0) - coalesce(k.kanal_komisyonu, 0)
                  - coalesce(kg.kargo_tum, 0) - coalesce(r.reklam, 0), 2)
  END                                                     AS reklam_sonrasi,

  -- Bu satirin ne kadari gercekten olculdu (ikisi de KDV haric - ayni taban)
  round(100.0 * coalesce(k.ciro_olculen, 0) / nullif(k.ciro_net, 0), 1)
                                                          AS maliyeti_bilinen_oran,
  -- K1 ekleri (sona)
  round(coalesce(k.odeme_komisyonu, 0) + coalesce(k.kanal_komisyonu, 0), 2) AS komisyon,
  coalesce(k.komisyon_bilinmeyen, 0)           AS komisyonu_bilinmeyen_kalem,
  round(coalesce(k.wix_ciro_net, 0), 2)        AS wix_ciro_net,
  round(coalesce(k.pazaryeri_ciro_net, 0), 2)  AS pazaryeri_ciro_net,
  round(coalesce(k.elle_ciro_net, 0), 2)       AS elle_ciro_net
FROM k
FULL OUTER JOIN kg ON kg.gun = k.gun
FULL OUTER JOIN nm ON nm.gun = coalesce(k.gun, kg.gun)
FULL OUTER JOIN r  ON r.gun  = coalesce(k.gun, kg.gun, nm.gun)
WHERE coalesce(k.gun, kg.gun, nm.gun, r.gun)
      >= (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date
ORDER BY 1;

COMMENT ON VIEW mart.gunluk_marj IS
  'Gunluk marj merdiveni, TUM kanallar (K1): ciro -> brut -> katki (komisyon + kargo dusulmus) -> reklam sonrasi. Pazaryeri kargosu VERI_YOK. COGS bilinmiyorsa NULL.';

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
FROM mart.satis_kalem_tum k   -- K1: tum kanallar
WHERE NOT k.maliyeti_biliniyor AND k.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
GROUP BY 1,2,3
ORDER BY sum(k.satir_ciro) DESC;

COMMENT ON VIEW mart.maliyet_eksik IS
  'Satmis ama maliyeti girilmemis urunler, ciroya gore sirali - once en cok satan girilsin.';

-- K1 yetkileri: panel (jarvis_web, direct-pg) + Jarvis okuyucu (ai_reader).
-- 🔴 core.bilesen_bul / maliyet_bul / urun_id_* CAGIRANIN yetkisiyle calisir
--    (lcarlie-panel-db-rolu): view yetkisi tek basina yetmez.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jarvis_web') THEN
    GRANT SELECT ON mart.satis_kalem_tum, mart.satis_kanal_gunluk, mart.satis_urun_gunluk,
                    mart.satis_tazelik, mart.satis_kaynak_mutabakat, mart.urun_karlilik,
                    mart.gunluk_marj TO jarvis_web;
    GRANT SELECT ON core.maliyet_bileseni, core.urun_kimlik TO jarvis_web;
    -- mart.kesim() (olcumde) core.ayar'i cagiranin yetkisiyle okur; ayar tablosunda sir yok (ai_reader zaten okuyor)
    GRANT SELECT ON core.ayar TO jarvis_web;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_reader') THEN
    GRANT SELECT ON mart.satis_kalem_tum, mart.satis_kanal_gunluk, mart.satis_urun_gunluk,
                    mart.satis_tazelik, mart.satis_kaynak_mutabakat TO ai_reader;
    GRANT SELECT ON core.maliyet_bileseni TO ai_reader;
  END IF;
END $$;

COMMIT;
