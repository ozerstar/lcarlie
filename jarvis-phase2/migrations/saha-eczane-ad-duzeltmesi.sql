-- SAHA: adinda 'eczane' gecen hedefler ECZANE sayilir.
-- Gerekce ve olcum gorunumun icindeki yorumda.
CREATE OR REPLACE VIEW mart.saha_hedef AS
SELECT k.hedef_anahtari,
    k.kaynak,
    k.osm_tur,
    k.osm_id,
    k.nokta_id,
    k.overture_id,
    k.grup,
    k.kategori,
    k.website,
    k.sosyal,
    k.adres,
    k.enlem,
    k.boylam,
    k.guven,
    k.ilk_gorulme,
    k.son_gorulme,
    k.kayip_at,
    k.zenginlik,
    k.ilce,
    k.ilce_ham,
    k.ilce_kaynagi,
    COALESCE(b.ad, k.ad) AS ad,
    -- 🔴 AD TABANLI DUZELTME.
    -- Sinif Overture'in KATEGORI etiketinden gelir; Overture'da
    -- 'doctor' diye etiketlenmis bir eczane DOKTOR olarak dusuyordu.
    -- OLCULDU 25.09.2026: adinda 'eczane' gecen 32 hedef ECZANE DISI
    -- bir turdeydi -- 19 DOKTOR, 5 KLINIK, 5 HASTANE, 1 HUZUREVI,
    -- 1 GUZELLIK, 1 OTEL. Saha elemani 'ECZANE' filtresiyle bakinca
    -- bu 32'sini HIC gormuyordu; eczane ana kanal oldugu icin bu
    -- dogrudan kacirilmis ziyaret demek.
    --
    -- Kural yalniz EKLER, hicbir seyi ECZANE'den CIKARMAZ.
    -- Kelime siniri sart: 'Eczanevit' gibi marka adlari yakalanmamali
    -- (olculdu -- yakalanmiyor). Ad olarak b.ad tercih edilir cunku
    -- insan duzeltmesi kaynaktan onceliklidir.
    CASE WHEN lower(COALESCE(b.ad, k.ad)) ~ '\meczane(si)?\M'
         THEN 'ECZANE'::text ELSE k.tur END AS tur,
    COALESCE(b.brans, k.brans) AS brans,
        CASE
            WHEN b.brans IS NOT NULL THEN 'BEYAN'::text
            ELSE k.brans_kaynagi
        END AS brans_kaynagi,
    COALESCE(b.telefon, k.telefon) AS telefon,
    COALESCE(b.eposta, k.eposta) AS eposta,
    COALESCE(b.ilgili_kisi, k.ilgili_kisi) AS ilgili_kisi,
    COALESCE(b.notlar, k.notlar) AS notlar,
    COALESCE(core.tr_anahtar(b.ad), k.ad_ara) AS ad_ara,
    COALESCE(b.hedef_disi, k.kalip_disi) AS hedef_disi,
        CASE
            WHEN b.hedef_disi IS TRUE THEN 'elle işaretlendi'::text
            WHEN b.hedef_disi IS FALSE THEN NULL::text
            ELSE k.kalip_neden
        END AS hedef_disi_neden,
    COALESCE(z.ziyaret_sayisi, 0::bigint) AS ziyaret_sayisi,
    z.son_ziyaret,
    z.son_sonuc
   FROM mart.saha_kaynak k
     LEFT JOIN core.saha_bilgi b ON b.hedef_anahtari = k.hedef_anahtari
     LEFT JOIN LATERAL ( SELECT count(*) AS ziyaret_sayisi,
            max(v.ziyaret_at) AS son_ziyaret,
            (array_agg(v.sonuc ORDER BY v.ziyaret_at DESC))[1] AS son_sonuc
           FROM core.saha_ziyaret v
             JOIN mart.saha_tum t ON t.hedef_anahtari = v.hedef_anahtari
          WHERE t.grup = k.grup) z ON true;
