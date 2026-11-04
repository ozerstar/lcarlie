-- 045 — Idefix yazma izni ACILIYOR (sahip karari 22.10.2026)
--
-- KARAR
-- Ozer: "idefixe urun yuklicez yazmalari ac". Idefix hesabinda sifir urun
-- var (22.10'da olculdu: totalCount=0, panelde URUNLERIM 0); yani yukleme
-- yapilmadan bu kanal satis uretemez.
--
-- BU BAYRAK NE YAPAR, NE YAPMAZ
-- yazma_izni=true yalniz "Idefix'e yazmak serbesttir" kaydidir. Tek basina
-- HICBIR SEY yuklemez. Fiili yukleme icin hala sart olanlar:
--   1. urun yukleme hatti (pool/{vendorId}/create + inventory-upload)
--   2. Idefix tarafi kimlikler: kategori, marka, gonderim/iade adresi, kargo
--   3. MEVZUAT KAPISI -- Trendyol'da yasak ifadeli basliklar HALA canli
--      (DERMAVASC "(Onarici Bakim Kremi)", DERMASTRA, MINISOOTH). Ayni
--      hata Idefix'e KOPYALANMAMALIDIR. Bkz. katalog yazim kilavuzu.
--   4. sahibin onayi -- "hepsi gene benim onayima baksin" (tek onay kapisi)
--
-- GERI ALMA
-- UPDATE core.platform SET yazma_izni = false WHERE kod = 'idefix';

\set ON_ERROR_STOP on
BEGIN;

UPDATE core.platform
   SET yazma_izni = true,
       not_ = 'Satici hesabi VAR (seller_id 22204, LEMOS Medikal Saglik). '
              'API baglandi 22.10.2026. YAZMA IZNI ACIK -- sahip karari: '
              'urun yuklenecek. Hesapta su an 0 urun listeli. Komisyon orani '
              'API''de yok, insan beyani gerekir.',
       guncelleme = now()
 WHERE kod = 'idefix';

SELECT kod, aktif, yazma_izni, fiyat_otoritesi FROM core.platform ORDER BY kod;

COMMIT;
