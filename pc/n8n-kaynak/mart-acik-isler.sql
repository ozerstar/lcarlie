-- =============================================================================
-- L'CARLIE - MART: ACIK ISLER  (CR-011'de kendi dosyasina alindi)
--
-- 🔴 NEDEN AYRI DOSYA:
--    Bu view CR-004'te mart-sema.sql'de dogdu, CR-006'da mart-marj.sql'de
--    UZERINE YAZILDI, CR-011'de bir de mart-konusma.sql gerekecekti.
--    Uc dosyada tanimli bir view, uc yerde bakim demektir - ve biri tek
--    basina uygulandiginda digerlerinin ekledigi dallar SESSIZCE KAYBOLUR
--    ("acik is azaldi" diye okunur, oysa liste kisalmistir).
--    Denetim bunu "bakim riski" olarak isaretlemisti (16.09.2026).
--
--    Artik TEK YERDE ve raw-uygula.sh'da EN SON uygulaniyor - boylece
--    bagimli oldugu tum view'lar (mart.gonderi, mart.siparis,
--    mart.maliyet_eksik, mart.konusma_cevapsiz) hazir olur.
--
-- 🔴 BOS OLMASI "IS YOK" DEMEKTIR, HATA DEGIL.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.acik_isler CASCADE;

CREATE VIEW mart.acik_isler AS
-- Siniflandirilamayan gonderi (yonu bilinmeyen) ------------------------------
SELECT 'SINIFLANDIRILMAMIS_GONDERI' AS tur, g.gonderi_id AS anahtar,
       format('%s · %s · %s', coalesce(g.barkod,'-'), coalesce(g.sehir,'-'),
              coalesce(array_to_string(g.urun_adlari,', '),'-')) AS detay,
       g.olusturma AS zaman,
       'BasitKargo kaydina EK BILGI yaz (NUMUNE-<tarih>) ya da Wix siparisiyle esle' AS yapilacak
  FROM mart.gonderi g WHERE g.alarm AND g.olcumde

-- Kimlik cakismasi -----------------------------------------------------------
UNION ALL
SELECT 'ACIK_KIMLIK_CAKISMASI', k.conflict_id::text,
       format('%s degeri %s musteriye bagli', k.kimlik_tipi, array_length(k.customer_ids,1)),
       k.tespit_at,
       'core.birlestirme_karari tablosuna BIRLESTIR/AYRI_TUT karari gir'
  FROM core.identity_conflict k WHERE k.durum='ACIK'

-- Odenmemis siparis ----------------------------------------------------------
UNION ALL
SELECT 'ODENMEMIS_SIPARIS', s.siparis_id,
       format('#%s · %s TL · %s', s.siparis_no, s.toplam, s.odeme_yontemi),
       s.olusturma,
       'Odeme geldi mi kontrol et; geldiyse Wix''te odendi isaretle'
  FROM mart.siparis s WHERE s.ciro_sinifi='ODENMEDI' AND s.olcumde

-- Kapida tahsilat bekleyen ---------------------------------------------------
UNION ALL
SELECT 'BEKLEYEN_KAPIDA_TAHSILAT', g.gonderi_id,
       format('%s TL · %s', g.cod_tutar, coalesce(g.cod_durum,'-')),
       g.olusturma,
       'BasitKargo tahsilat aktarimini izle'
  FROM mart.gonderi g
 WHERE g.cod_var AND g.cod_durum = 'COLLECTION_PENDING' AND g.olcumde

-- Maliyeti girilmemis urun ---------------------------------------------------
UNION ALL
SELECT 'MALIYET_GIRILMEMIS', m.urun_id,
       format('%s · %s TL ciro · %s kalem', left(m.urun_adi,40),
              m.olculemeyen_ciro, m.satilan_kalem),
       (m.son_satis)::timestamptz,
       'Wix''te urunun Maliyet alanini doldur (Urunler -> urun -> Maliyet)'
  FROM mart.maliyet_eksik m
 WHERE m.son_satis >= (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date

-- Sinifi bilinmeyen gonderi - INSAN KARAR KUYRUGU -----------------------------
-- 🔴 BU SATIR ESKIDEN 'VARSAYILAN_NUMUNE_SAYIMI' IDI ve bir OZET satiriydi.
--    Arkasindaki kural suydu: "kapida odeme yok + Wix kaydi yok => numune".
--    Bu bir olcum degil VARSAYIMDI ve ayni desene havale/EFT ile odenmis
--    satis, hediye, barter, UGC, PR ve personel gonderisi de uyuyor. Varsayim
--    kaldirildi: sinif artik UNKNOWN ve her gonderi TEK TEK insan karari
--    bekler - ozet bir satir, 31 ayri kararin uzerini ortuyordu.
--
-- 🔴 BU KALEM BILEREK `olcumde` ILE SINIRLANMADI. Siniflandirma 1 Ekim'den
--    ONCE duzeltilmeli; kesimden sonrasina bakan bir kuyruk, tam da
--    duzeltilmesi gereken donemi gizlerdi.
UNION ALL
-- 🔴 TUR ADI 'SINIFLANDIRILMAMIS_GONDERI' DEGIL: o ad bu view'in ilk
--    dalinda (yonu okunamayan gonderi, alarm=true) zaten kullaniliyor.
--    Ayni ada iki farkli is koymak, panelde "1 is" gibi gorunup iki ayri
--    mudahaleyi tek sayiya karistirirdi.
SELECT 'SINIFI_BILINMEYEN_GONDERI', g.gonderi_id,
       format('%s · %s · %s TL kargo · EK BILGI: %s',
              coalesce(g.barkod,'-'), coalesce(g.sehir,'-'),
              to_char(coalesce(g.kargo_ucreti,0),'FM999990.00'),
              coalesce(nullif(g.ek_bilgi,''),'(bos)')),
       g.olusturma,
       'Bu gonderi neydi? Numune ise BasitKargo EK BILGI alanina NUMUNE-<tarih> yaz; '
       'satis ise Wix''e siparis olarak gir. Isaretlenene kadar ne ciroya ne pazarlama giderine yazilir.'
  FROM mart.gonderi g WHERE g.sinif = 'UNKNOWN'

-- Tutari belirlenemeyen siparis ----------------------------------------------
UNION ALL
SELECT 'TUTARI_BILINMEYEN_SIPARIS', s.siparis_id,
       format('#%s · %s TL · odeme=%s teslimat=%s', s.siparis_no, s.toplam,
              coalesce(s.odeme_durumu,'(bos)'), coalesce(s.teslimat_durumu,'(bos)')),
       s.olusturma,
       'Wix''te siparisin odeme/teslimat durumunu kontrol et - alan bos gorunuyor'
  FROM mart.siparis s WHERE s.ciro_sinifi = 'BILINMIYOR' AND s.olcumde

-- Yonu bilinmeyen gonderi ----------------------------------------------------
UNION ALL
SELECT 'YONU_BILINMEYEN_GONDERI', g.gonderi_id,
       format('%s · %s', coalesce(g.barkod,'-'), coalesce(g.sehir,'-')),
       g.olusturma,
       'BasitKargo kaydinda gonderi yonu (OUTGOING/INCOMING) okunamadi'
  FROM mart.gonderi g WHERE g.sinif = 'YON_BILINMIYOR' AND g.olcumde

-- Cevapsiz musteri mesaji  (CR-011) ------------------------------------------
-- 🔴 Atif kurulamadi ama BU olculuyor: cevaplanmamis mesaj = kacan satis.
--    24 saati gecenler listelenir; PII tasinmaz (takma kimlik).
UNION ALL
-- 🔴 "yapilacak" HER SATIRDA AYNI OLMALI.  Panel bu kolonu tur bazinda
--    min() ile ozetliyor; icine konusma kimligi konursa 10 kalemlik grubun
--    yaninda TEK bir kimlik yazar ve "yapilacak is bu konusmayi cevaplamak"
--    gibi okunur. Kimlik detay kolonuna ait, talimata degil.
SELECT 'CEVAPSIZ_MESAJ', c.konusma_id::text,
       format('%s · %s · %s mesajlik konusma · %s saattir bekliyor',
              c.musteri_takma, c.kanal, c.mesaj_sayisi, c.bekleme_saat),
       c.son_mesaj,
       'Meta gelen kutusundan cevapla (Sayfa gelen kutusu, filtresiz liste)'
  FROM mart.konusma_cevapsiz c
 WHERE c.bekleme_saat > 24;

COMMENT ON VIEW mart.acik_isler IS
  'Insan karari bekleyen her sey TEK listede ve TEK dosyada. Bos olmasi is yok demektir, hata degil.';

COMMIT;
