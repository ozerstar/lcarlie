-- =============================================================================
-- L'CARLIE - MART KATMANI  (CR-004 Faz 3)
--
-- 🔴 MART = GORUNUM (VIEW), TABLO DEGIL.
--    Tablo olsaydi raw guncellenince mart eskir ve "senkron mu?" sorusu
--    dogar. Gorunum olunca boyle bir soru YOKTUR: mart her zaman raw'in
--    o anki halidir. Veri kucuk (onlarca satir), performans gerekcesi yok.
--
-- 🔴 TEK BIR "CIRO" SAYISI URETILMEZ.  (sahip karari, CR-003/CR-004)
--      ciro_dogrulanmis  = PayTR ile tahsil edilmis, saglayici onayli
--      ciro_beyan_edilmis= cevrim disi/kapida odeme, ELLE isaretlenmis
--    Ikisi toplanip tek rakam verilirse, dogrulanmamis para dogrulanmis
--    gibi gorunur. Toplamak isteyen ikisini gorerek toplar.
--
-- 🔴 KATKI MARJI HESAPLANMAZ.  COGS (urun maliyeti) hicbir kaynakta yok
--    (core.source_authority: cogs = NONE). Maliyeti bilinmeyen bir seyin
--    marji uydurma olur. Yalniz BILINEN maliyet (kargo) gosterilir.
--
-- 🔴 SATIR GIZLENMEZ. Iptal/iade/numune kayitlari view'dan atilmaz,
--    SINIFLANDIRILIR. Atilan satir, yok olan sorudur.
--
-- 🔴 OLCUM KESIMI core.ayar'dan okunur, buraya elle yazilmaz.
-- =============================================================================

BEGIN;

-- 🔴 VIEW'LAR ONCE DUSURULUR.  CREATE OR REPLACE VIEW mevcut bir kolonun
--    ADINI ya da SIRASINI degistiremez ("cannot change name of view column");
--    yalnizca sona kolon eklemeye izin verir. Sema gelistikce kolon eklemek
--    kacinilmaz oldugundan, dosyanin HER SURUMDE yeniden uygulanabilir
--    kalmasi icin once dusurmek gerekir. Aksi halde masaustunde duzeltirsin,
--    sunucuda ESKI view calismaya devam eder - projenin defalarca yasadigi
--    sessiz surumlenme.
--    Sira en bagimlidan en temele; CASCADE gerisini halleder ama acik liste
--    neyin yeniden yaratilmasi gerektigini de belgeler.
DROP VIEW IF EXISTS mart.acik_isler         CASCADE;
DROP VIEW IF EXISTS mart.gunluk_marj        CASCADE;
DROP VIEW IF EXISTS mart.maliyet_eksik      CASCADE;
DROP VIEW IF EXISTS mart.urun_karlilik      CASCADE;
DROP VIEW IF EXISTS mart.siparis_kalem      CASCADE;
DROP VIEW IF EXISTS mart.harcama_uyari      CASCADE;
DROP VIEW IF EXISTS mart.gunluk_verimlilik  CASCADE;
DROP VIEW IF EXISTS mart.harcama            CASCADE;
DROP VIEW IF EXISTS mart.musteri            CASCADE;
DROP VIEW IF EXISTS mart.gunluk             CASCADE;
DROP VIEW IF EXISTS mart.gonderi            CASCADE;
DROP VIEW IF EXISTS mart.siparis            CASCADE;

-- 🔴 AYAR YOKSA HATA VERIR, NULL DONMEZ (16.09 denetiminde bulundu).
--    NULL donseydi `olusturma >= NULL` -> NULL olur ve HER olcumde filtresi
--    tum satirlari elerdi. Panel bunu hata degil "olcum baslamadi / —" diye
--    gosterirdi: yani silinmis bir yapilandirma, duzgun calisan bir sistem
--    gibi gorunurdu. Bu, projenin kendi "sifir ile yokluk ayni sey degildir"
--    ilkesinin tam tersi.
CREATE OR REPLACE FUNCTION mart.kesim() RETURNS timestamptz
LANGUAGE plpgsql STABLE AS $$
DECLARE v timestamptz;
BEGIN
  SELECT deger::timestamptz INTO v FROM core.ayar WHERE anahtar='olcum_baslangici';
  IF v IS NULL THEN
    RAISE EXCEPTION 'core.ayar icinde olcum_baslangici yok veya bos - olcum penceresi belirlenemez';
  END IF;
  RETURN v;
END $$;

-- ==========================================================================
-- SIPARIS
-- ==========================================================================
CREATE OR REPLACE VIEW mart.siparis AS
SELECT
  w.siparis_id,
  w.siparis_no,
  w.olusturma,
  (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
  ci.customer_id,
  w.odeme_yontemi,
  w.odeme_durumu,
  w.teslimat_durumu,
  w.arsivlendi,
  w.toplam,
  -- 🔴 KDV HARIC NET CIRO (CR-012).  'toplam' KDV DAHILDIR ve MARJ HESABINDA
  --    KULLANILMAZ: KDV bizim paramiz degil, devlete gider. Olculdu:
  --    37/37 siparişte kdv/(toplam-kdv) = 0,2000. Toplamda 82.073,50 KDV
  --    dahil -> 68.394,59 net; arada 13.678,91 KDV var. Bu fark marja
  --    oldugu gibi yansiyordu, yani marj %20 SISIKTI.
  -- 🔴 kdv NULL ise net de NULL doner - "KDV sifir" varsayilmaz.
  (w.toplam - w.kdv)                          AS toplam_kdv_haric,
  w.kdv,

  -- Siniflandirma: neden sayilir / neden sayilmaz
  --
  -- 🔴 NULL SEMANTIGI (16.09.2026 denetiminde bulundu).
  --    Onceki hali `w.odeme_durumu <> 'PAID'` yaziyordu. SQL'de NULL ile
  --    karsilastirma NULL doner (false DEGIL), yani odeme durumu BILINMEYEN
  --    bir siparis bu daldan gecip "DOGRULANMIS" sayiliyordu - ama tutar
  --    kolonlari acikca '=PAID' aradigi icin o para UC KOLONUN DA disinda
  --    kaliyordu. Yani sipariş "dogrulanmis ciro" sayisina girer, parasi
  --    hicbir yere yazilmazdi: sessizce buharlasirdi.
  --    Cozum: IS DISTINCT FROM + acik BILINMIYOR dali.
  CASE
    WHEN w.odeme_durumu IS NULL OR w.teslimat_durumu IS NULL THEN 'BILINMIYOR'
    WHEN w.teslimat_durumu = 'CANCELED'          THEN 'IPTAL'
    WHEN w.odeme_durumu IS DISTINCT FROM 'PAID'  THEN 'ODENMEDI'
    WHEN w.odeme_yontemi = 'PayTR'               THEN 'DOGRULANMIS'
    ELSE 'BEYAN_EDILMIS'
  END AS ciro_sinifi,

  -- 🔴 Ucu de AYRI kolon. Tek 'ciro' kolonu bilerek YOK.
  --    Kosullar ciro_sinifi ile BIREBIR ayni mantigi kullanir; boylece
  --    "bir sinifta sayilip hicbir tutara girmeyen siparis" olusamaz.
  CASE WHEN w.odeme_durumu IS NOT NULL AND w.teslimat_durumu IS NOT NULL
            AND w.teslimat_durumu <> 'CANCELED' AND w.odeme_durumu='PAID'
            AND w.odeme_yontemi='PayTR'  THEN w.toplam END AS ciro_dogrulanmis,
  CASE WHEN w.odeme_durumu IS NOT NULL AND w.teslimat_durumu IS NOT NULL
            AND w.teslimat_durumu <> 'CANCELED' AND w.odeme_durumu='PAID'
            AND w.odeme_yontemi IS DISTINCT FROM 'PayTR' THEN w.toplam END AS ciro_beyan_edilmis,
  CASE WHEN w.odeme_durumu IS NOT NULL AND w.teslimat_durumu IS NOT NULL
            AND w.teslimat_durumu <> 'CANCELED'
            AND w.odeme_durumu IS DISTINCT FROM 'PAID' THEN w.toplam END AS tutar_bekleyen,
  -- Sinifi belirlenemeyen siparisin tutari da KAYBOLMAZ, ayri kolonda durur.
  CASE WHEN w.odeme_durumu IS NULL OR w.teslimat_durumu IS NULL
       THEN w.toplam END AS tutar_bilinmiyor,

  -- 🔴 AYNI SINIFLARIN KDV HARIC HALI (CR-012).  KDV dahil kolonlar
  --    SILINMEDI - fatura/tahsilat KDV dahil tutar uzerinden yurur ve
  --    banka o rakami gorur. Ama MARJ ve ROAS bu net kolonlardan hesaplanir.
  --    Kosullar yukaridakilerle BIREBIR ayni; yalniz tutar degisiyor.
  CASE WHEN w.odeme_durumu IS NOT NULL AND w.teslimat_durumu IS NOT NULL
            AND w.teslimat_durumu <> 'CANCELED' AND w.odeme_durumu='PAID'
            AND w.odeme_yontemi='PayTR'  THEN w.toplam - w.kdv END AS ciro_dogrulanmis_net,
  CASE WHEN w.odeme_durumu IS NOT NULL AND w.teslimat_durumu IS NOT NULL
            AND w.teslimat_durumu <> 'CANCELED' AND w.odeme_durumu='PAID'
            AND w.odeme_yontemi IS DISTINCT FROM 'PayTR' THEN w.toplam - w.kdv END AS ciro_beyan_edilmis_net,

  (w.olusturma >= mart.kesim()) AS olcumde,
  w.giren_tipi,
  w.kanal
FROM raw.wix_order w
LEFT JOIN core.customer_identity ci
       ON ci.kaynak='wix' AND ci.kimlik_tipi='wix_buyer_id'
      AND ci.source_customer_id = w.buyer_id;

COMMENT ON VIEW mart.siparis IS
  'Wix siparisleri, ciro sinifi ayrilmis. olcumde=false olanlar 1 Ekim 2026 oncesidir.';

-- ==========================================================================
-- GONDERI
-- ==========================================================================
CREATE OR REPLACE VIEW mart.gonderi AS
SELECT
  b.gonderi_id,
  b.barkod,
  b.olusturma,
  (b.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
  b.foreign_code AS siparis_id,
  w.siparis_no,
  b.ek_bilgi,
  b.durum,
  b.tasiyici,
  b.sehir,
  b.kargo_ucreti,
  b.toplam_maliyet,
  b.cod_var,
  b.cod_tutar,
  b.cod_durum,

  -- 🔴 KAPIDA ODEME KOMISYONU OLCULEBILIYOR (17.09.2026'da bulundu).
  --    Daha once "COD maliyeti digerlerinden ayrismiyor" denmisti - YANLISTI.
  --    BasitKargo codInfo.fee alani gonderi bazinda komisyonu veriyor
  --    (olculdu: CREDIT_CARD %6,38-7,86 · CASH %1,90-4,80).
  -- 🔴 AMA YALNIZ TAHSILAT GERCEKLESINCE DOLUYOR. COLLECTION_PENDING
  --    gonderilerde fee NULL'dur ve bu "olcemiyoruz" DEGIL, "henuz
  --    gerceklesmedi" demektir. Ikisi ayri davranir: biri zamanla
  --    KENDILIGINDEN kapanir, digeri ancak biri is yaparsa.
  --    Ayni kutuya konursa bekleyen kalem hic takip edilmez.
  (b.ham#>>'{codInfo,fee}')::numeric AS cod_komisyon,
  CASE
    WHEN NOT b.cod_var                               THEN 'YOK'
    WHEN b.ham#>>'{codInfo,fee}' IS NOT NULL         THEN 'MEASURED'
    WHEN b.cod_durum = 'COLLECTION_PENDING'          THEN 'NOT_YET_KNOWN'
    ELSE 'UNKNOWN'
  END AS cod_komisyon_sinifi,
  b.urun_adlari,

  -- 🔴 SIRA ONEMLI. Bir iade gonderisi foreignCode tasiyabilir; once
  --    yon bakilmazsa iade "satis" sayilir.
  -- 🔴 yon NULL ISE (16.09 denetimi): eski hali NULL'i hicbir dala
  --    sokmuyordu; yonu bilinmeyen bir gonderi, siparisle eslesiyorsa
  --    dogrudan "SATIS" sayiliyordu - yani bir iade satis olarak okunabilirdi.
  -- 🔴 SAHIP KURALI (16.09.2026): kapida odemeli bir gonderinin Wix kaydi
  --    yoksa, o bir WhatsApp/telefon siparisidir. Sahip beyani:
  --    "basıt kargonun kapıda ödeme bilgisine göre ben işaretliyorum".
  --    Bu kural, olculemeyen cironun bir kismini OLCULEBILIR hale getirir:
  --    9 gonderi · 11.075 TL. Tutar kaynagi codInfo.amount'tur.
  --    SIRA ONEMLI: foreignCode varsa zaten SATIS'tir (cift sayim olmaz).
  -- 🔴 SAHIP KARARI (16.09.2026): kapida odemesi ve Wix kaydi olmayan
  --    gonderiler numune/UGC sayilir - pazarlama gideri, satis DEGIL.
  --
  --    AMA AYRI SINIF: 'NUMUNE' yalnizca ACIKCA EK BILGI ile isaretlenmis
  --    olandir. Isaret yoksa NUMUNE DENMEZ.
  --
  -- 🔴🔴 KURAL DEGISTI (16.09.2026, Chief Architect duzeltmesi).
  --    ESKI HALI: "kapida odeme yok + Wix kaydi yok -> NUMUNE_VARSAYILAN"
  --    Bu, BILINMEYENI VARSAYARAK SINIFLANDIRMAKTI - projenin defalarca
  --    duzelttigi hatanin aynisi. Ayni dala duseceklerin listesi:
  --      havale/EFT ile alinan telefon siparisi · hediye · barter ·
  --      UGC · PR gonderisi · personel gonderisi · elle satis
  --    Yani bir SATIS, pazarlama gideri olarak okunabiliyordu ve cirosu
  --    hic gorunmuyordu.
  --
  --    YENI HALI: acik isaret yoksa 'UNKNOWN'.
  --      - satis sayilmaz
  --      - pazarlama giderine OTOMATIK dahil edilmez
  --      - insan kontrol kuyruguna duser (mart.acik_isler)
  --    Gercekten numune oldugu KANITLANAN sonradan NUMUNE olur.
  CASE
    WHEN b.yon IS NULL                          THEN 'YON_BILINMIYOR'
    WHEN b.yon = 'INCOMING'                     THEN 'IADE'
    WHEN b.ek_bilgi ILIKE 'NUMUNE-%'            THEN 'NUMUNE'
    WHEN w.siparis_id IS NOT NULL               THEN 'SATIS'
    WHEN b.cod_var AND b.cod_tutar > 0          THEN 'ELLE_SATIS'
    ELSE 'UNKNOWN'
  END AS sinif,

  -- Elle satisin cirosu: kapida odeme tutari.
  -- 🔴 TAHSIL EDILEN ile BEKLEYEN AYRI. TRANSFERRED = para hesaba gecti,
  --    COLLECTION_PENDING = henuz gecmedi. Ikisini toplamak, alinmamis
  --    parayi ciro saymak olur - projenin "dogrulanmis/beyan" ayriminin
  --    ayni mantigi.
  CASE WHEN b.yon IS DISTINCT FROM 'INCOMING' AND w.siparis_id IS NULL
            AND b.cod_var AND b.cod_durum = 'TRANSFERRED'
       THEN b.cod_tutar END AS elle_ciro_tahsil,
  CASE WHEN b.yon IS DISTINCT FROM 'INCOMING' AND w.siparis_id IS NULL
            AND b.cod_var AND b.cod_durum IS DISTINCT FROM 'TRANSFERRED'
       THEN b.cod_tutar END AS elle_ciro_bekleyen,

  -- Sahip kurali: foreignCode BOS + ek bilgi BOS  ->  ALARM
  -- 🔴 IS DISTINCT FROM sart: `b.yon <> 'INCOMING'` ifadesi yon NULL iken
  --    NULL doner; `count(*) FILTER (WHERE alarm)` ve `WHERE g.alarm`
  --    NULL'i saymaz. Yani tam da insan mudahalesi gereken kayit (yonu
  --    bilinmeyen + eslesmeyen + etiketsiz) her listeden SESSIZCE dusуyordu.
  -- 🔴 ALARM YALNIZ YONU OKUNAMAYAN GONDERI ICINDIR - o, kaydin kendisinin
  --    bozuk oldugu tek durumdur (veri hatasi).
  --    UNKNOWN sinifi alarm DEGIL: kayit saglam, sadece NE OLDUGU bilinmiyor
  --    (is bilgisi eksik). Ikisi ayri mudahale ister, bu yuzden ayri durur -
  --    ama UNKNOWN da gorunmez degil: panelde ayri satir, mart.acik_isler'de
  --    'SINIFI_BILINMEYEN_GONDERI' olarak TEK TEK insan karar kuyrugunda.
  (b.yon IS NULL) AS alarm,

  (b.olusturma >= mart.kesim()) AS olcumde,

  CASE WHEN b.teslim IS NOT NULL AND b.kargoya_verilis IS NOT NULL
       THEN round(extract(epoch FROM b.teslim - b.kargoya_verilis)/86400.0, 2)
  END AS transit_gun
FROM raw.bk_shipment b
LEFT JOIN raw.wix_order w ON w.siparis_id = b.foreign_code;

COMMENT ON VIEW mart.gonderi IS
  'BasitKargo gonderileri. alarm=true (yon okunamadi) ve sinif=UNKNOWN (ne oldugu bilinmiyor) '
  'olanlar insan mudahalesi ister. UNKNOWN varsayimla numune sayilmaz.';

-- ==========================================================================
-- GUNLUK OZET
-- ==========================================================================
CREATE OR REPLACE VIEW mart.gunluk AS
WITH s AS (
  SELECT gun,
         count(*) FILTER (WHERE ciro_sinifi='DOGRULANMIS')   AS siparis_dogrulanmis,
         count(*) FILTER (WHERE ciro_sinifi='BEYAN_EDILMIS') AS siparis_beyan,
         count(*) FILTER (WHERE ciro_sinifi='ODENMEDI')      AS siparis_odenmedi,
         count(*) FILTER (WHERE ciro_sinifi='IPTAL')         AS siparis_iptal,
         -- 🔴 BILINMIYOR sinifi da SAYILIR (ikinci tur denetimi).
         --    mart.siparis'e 'BILINMIYOR' dali ve tutar_bilinmiyor kolonu
         --    eklenmisti ama BURADA okunmuyordu: para siparis seviyesinde
         --    kaybolmuyordu ama bir katman yukarida yine buharlasiyordu.
         count(*) FILTER (WHERE ciro_sinifi='BILINMIYOR')    AS siparis_bilinmiyor,
         coalesce(sum(ciro_dogrulanmis),0)   AS ciro_dogrulanmis,
         coalesce(sum(ciro_beyan_edilmis),0) AS ciro_beyan_edilmis,
         coalesce(sum(tutar_bekleyen),0)     AS tutar_bekleyen,
         coalesce(sum(tutar_bilinmiyor),0)   AS tutar_bilinmiyor
    FROM mart.siparis WHERE olcumde GROUP BY gun
), g AS (
  SELECT gun,
         count(*) FILTER (WHERE sinif='SATIS')  AS gonderi_satis,
         count(*) FILTER (WHERE sinif='NUMUNE') AS gonderi_numune,
         count(*) FILTER (WHERE sinif='IADE')   AS gonderi_iade,
         -- 🔴 UNKNOWN AYRI SAYILIR ve pazarlama giderine KARISMAZ.
         count(*) FILTER (WHERE sinif='UNKNOWN') AS gonderi_bilinmiyor,
         coalesce(sum(kargo_ucreti) FILTER (WHERE sinif='UNKNOWN'),0) AS bilinmeyen_kargo,
         count(*) FILTER (WHERE sinif='SINIFLANDIRILMAMIS') AS gonderi_sinifsiz,
         count(*) FILTER (WHERE sinif='YON_BILINMIYOR')     AS gonderi_yon_bilinmiyor,
         -- 🔴 WhatsApp/telefon siparisi (sahip kurali): kapida odemeli +
         --    Wix kaydi yok. Cirosu AYRI kolonlarda cunku kaynagi Wix degil
         --    BasitKargo - okuyan hangi rakamin nereden geldigini bilmeli.
         count(*) FILTER (WHERE sinif='ELLE_SATIS')         AS gonderi_elle_satis,
         coalesce(sum(elle_ciro_tahsil),0)                  AS ciro_elle_tahsil,
         coalesce(sum(elle_ciro_bekleyen),0)                AS ciro_elle_bekleyen,
         count(*) FILTER (WHERE alarm)          AS gonderi_alarm,
         coalesce(sum(kargo_ucreti),0)                             AS kargo_maliyeti,
         coalesce(sum(kargo_ucreti) FILTER (WHERE sinif='NUMUNE'),0) AS numune_kargo_maliyeti
    FROM mart.gonderi WHERE olcumde GROUP BY gun
)
SELECT coalesce(s.gun, g.gun) AS gun,
       coalesce(s.siparis_dogrulanmis,0) AS siparis_dogrulanmis,
       coalesce(s.siparis_beyan,0)       AS siparis_beyan,
       coalesce(s.siparis_odenmedi,0)    AS siparis_odenmedi,
       coalesce(s.siparis_iptal,0)       AS siparis_iptal,
       coalesce(s.siparis_bilinmiyor,0)  AS siparis_bilinmiyor,
       coalesce(s.ciro_dogrulanmis,0)    AS ciro_dogrulanmis,
       coalesce(s.ciro_beyan_edilmis,0)  AS ciro_beyan_edilmis,
       coalesce(s.tutar_bekleyen,0)      AS tutar_bekleyen,
       coalesce(s.tutar_bilinmiyor,0)    AS tutar_bilinmiyor,
       coalesce(g.gonderi_satis,0)       AS gonderi_satis,
       coalesce(g.gonderi_numune,0)      AS gonderi_numune,
       coalesce(g.gonderi_iade,0)        AS gonderi_iade,
       coalesce(g.gonderi_bilinmiyor,0)        AS gonderi_bilinmiyor,
       coalesce(g.bilinmeyen_kargo,0)          AS bilinmeyen_kargo,
       coalesce(g.gonderi_sinifsiz,0)    AS gonderi_sinifsiz,
       coalesce(g.gonderi_yon_bilinmiyor,0) AS gonderi_yon_bilinmiyor,
       coalesce(g.gonderi_elle_satis,0)  AS gonderi_elle_satis,
       coalesce(g.ciro_elle_tahsil,0)    AS ciro_elle_tahsil,
       coalesce(g.ciro_elle_bekleyen,0)  AS ciro_elle_bekleyen,
       coalesce(g.gonderi_alarm,0)       AS gonderi_alarm,
       coalesce(g.kargo_maliyeti,0)      AS kargo_maliyeti,
       coalesce(g.numune_kargo_maliyeti,0) AS numune_pazarlama_maliyeti
  FROM s FULL OUTER JOIN g ON g.gun = s.gun
 ORDER BY 1;

-- 🔴 'katki_marji' / 'kar' KOLONU YOK. COGS bilinmiyor (source_authority:
--    cogs=NONE). Maliyet bilinmeden marj yazmak uydurmadir. COGS kaynagi
--    baglandiginda bu view'a eklenir.
COMMENT ON VIEW mart.gunluk IS
  'Gunluk ticari ozet. Ciro IKI AYRI kolon (dogrulanmis/beyan). Kar/marj YOK - COGS kaynagi bagli degil.';

-- ==========================================================================
-- MUSTERI OZETI
-- ==========================================================================
CREATE OR REPLACE VIEW mart.musteri AS
SELECT c.customer_id,
       c.identity_status,
       c.match_method,
       count(s.siparis_id) FILTER (WHERE s.olcumde)                        AS siparis_olcumde,
       count(s.siparis_id)                                                 AS siparis_tum_zaman,
       coalesce(sum(s.ciro_dogrulanmis)   FILTER (WHERE s.olcumde),0)      AS ciro_dogrulanmis,
       coalesce(sum(s.ciro_beyan_edilmis) FILTER (WHERE s.olcumde),0)      AS ciro_beyan_edilmis,
       min(s.olusturma) AS ilk_siparis,
       max(s.olusturma) AS son_siparis
  FROM core.customer c
  LEFT JOIN mart.siparis s ON s.customer_id = c.customer_id
 GROUP BY 1,2,3;

COMMIT;
