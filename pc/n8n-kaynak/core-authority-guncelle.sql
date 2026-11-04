-- =============================================================================
-- L'CARLIE - KAYNAK OTORITE HARITASI GUNCELLEMESI
--
-- 🔴 BU DOSYA HER CR'DE GUNCELLENIR.  Otorite haritasi bir kez yazilip
--    unutulursa yalan soylemeye baslar: CR-004'te BasitKargo baglandi
--    ama harita hala "SOURCE_NOT_CONNECTED" diyordu. Hem veri akiyor
--    hem harita "akmiyor" diyorsa, harita hicbir ise yaramaz.
--
-- 🔴 "CONNECTED" demek icin VERI GORMUS OLMAK gerekir; niyet yetmez.
--    Her satirda dogrulama yontemi ve zamani yazili.
--
-- Idempotent.
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- CR-004'te baglandi, harita guncellenmemisti
-- --------------------------------------------------------------------------
-- 🔴 TEK UPDATE. Ayni alan icin ikinci bir UPDATE yazilmaz: sonraki
--    oncekini ezer ve onceki blok OLU KOD haline gelir - okuyan hangisinin
--    gecerli oldugunu bilemez. CR-012'de bu hata yapildi ve birlestirildi.
UPDATE core.source_authority SET
  current_connection = 'CONNECTED',
  mirror = 'raw.bk_shipment (49 gonderi) -> mart.siparis_para (para zinciri)',
  freshness = 'gunluk 08:30 (ticari-kontrol.sh)',
  gap = 'Alici PII bilerek alinmaz. 39 gonderi Wix siparisiyle eslesmiyor - '
        'bunlarin ciro tarafi Wix''e elle girilene kadar olculemez. '
        'CR-012: siparis->kargolandi->teslim->tahsil->iade zinciri kuruldu, '
        'ama KAPSAMA DAR: 37 siparişin 9''unda gonderi kaydi eslesiyor, '
        '28''inde YOK. Eslesmeyenlerde teslim durumu "hayir" DEGIL '
        '"BILINMIYOR"dur; panel ikisini ayri gosterir, yoksa teslim orani '
        'oldugundan kotu okunur. '
        'Kapida odeme tahsilati BasitKargo cod_durum=TRANSFERRED beyanina '
        'dayanir, BANKA EKSTRESIYLE karsilastirilmaz.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-004: POST /api/v2/order/filter ile 49 id dogrulandi. '
                      'CR-012: "teslim edilen mutlaka kargolanmis" ve "COD tahsilati '
                      'teslimatsiz degil" degismezleri sinandi, ihlal 0'
WHERE alan = 'shipment';

UPDATE core.source_authority SET
  current_connection = 'CONNECTED',
  mirror = 'raw.bk_shipment.kargo_ucreti',
  freshness = 'gunluk 08:30',
  gap = 'Kargo maliyeti 49/49 tam. Urun maliyeti (COGS) AYRI ve hala yok.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-004: 49/49 dolu, toplam 7063.83 TL kaynakla birebir'
WHERE alan = 'shipping_cost';

-- --------------------------------------------------------------------------
-- CR-005: reklam harcamasi
-- --------------------------------------------------------------------------
-- 🔴 'PARTIAL', 'CONNECTED' DEGIL (ikinci tur denetimi).
--    ETL'in kendisi PARTIAL diyor (raw.yukleme_log), alarm DEGRADED tutuyor,
--    gap metni "yalniz 1 hesap okunuyor" diyor - ama bayrak CONNECTED'di.
--    Bu dosyanin kendi basligi "harita bir kez yazilip unutulursa yalan
--    soylemeye baslar" diyor; harita ile ETL birbirini yalanliyordu.
--    3 hesabin 2'si okunamiyorken "bagli" demek, eksik harcamayi tam
--    gostermek olur - ve eksik harcama ROAS'i OLDUGUNDAN YUKSEK gosterir.
UPDATE core.source_authority SET
  current_connection = 'PARTIAL',
  authority = 'Meta Ads (act_1301171572214198)',
  mirror = 'raw.meta_harcama (gun x kampanya)',
  freshness = 'gunluk 08:30, son 28 gun her seferinde yeniden yazilir',
  -- 🔴 Bosluklar ACIKCA yazilir. "Bagli" demek "eksiksiz" demek degildir.
  gap = 'YALNIZ 1 hesap okunuyor (1301171572214198). Diger iki hesap '
        '(560782561026922 eski, 1601342818221781 bos) sistem kullanicisina '
        'ATANMADI - erisim yok. Portfolyo adi alinamiyor (business_management '
        'izni bilerek verilmedi). Meta''nin kendi donusum rakami AYRI kolonda '
        'durur, Wix cirosu yerine KULLANILMAZ. Atif yok: oranlar karma (blended).',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-005: act_/insights ile 74 satir, 36 gun, 35329.52 TL cekildi'
WHERE alan = 'ad_spend';

-- --------------------------------------------------------------------------
-- CR-006: urun maliyeti
-- --------------------------------------------------------------------------
-- 🔴 "PARTIAL" cunku yapi kurulu ve akiyor ama VERI neredeyse yok.
--    CONNECTED demek yanlis olurdu: baglanti var, icerik yok.
UPDATE core.source_authority SET
  current_connection = 'PARTIAL',
  authority = 'Wix urun Maliyet alani (sahip girisi)',
  mirror = 'raw.wix_urun.maliyet -> core.urun_maliyet (zamana gore versiyonlu)',
  freshness = 'gunluk 08:30; degisim yakalanip tarihlenir',
  -- 🔴 KAPSAMA ile KALITE AYRI SEYDIR (CR-012 denetim bulgusu).
  --    "%96,2 kapsama" tehlikeli derecede iyimser bir cumle: 36 urunun
  --    36'sinda maliyet VAR ama hepsi AYNI 400 TL sahip tahmini.
  --    Olculmus maliyet sayisi: 0. Yani kapsama yuksek, kalite SIFIR.
  gap = 'KAPSAMA %96,2 ama KALITE SIFIR: 36 urunun 36''sinda maliyet var, '
        'hepsi AYNI 400 TL SAHIP TAHMINI (mart.maliyet_kalite: OLCULMUS=0, '
        'TAHMIN=36). Urun bazinda karlilik karsilastirmasi bu veriyle '
        'YAPILAMAZ - hepsi ayni sayi. SKU bazinda reklam karari verilirse '
        'yanlis urun secilir. '
        'MALIYETIN KDV TABANI TEYIT EDILMEDI: 400 TL''nin KDV dahil mi haric '
        'mi oldugu sahibe sorulmadi. Hesap KDV HARIC varsayar (COGS standardi); '
        'varsayim panelde ve core.ayar.maliyet_kdv_tabani''nda GORUNUR tutulur. '
        'Etki bu veri setinde 3.733 TL. '
        'Maliyet girilmeyen kalemde marj NULL doner - 0 veya tahmin URETILMEZ. '
        'Maliyet bugun girilince GECMIS siparisler icin gecerli sayilmaz; '
        'gecmise donuk beyan core.maliyet_gecmise_don() ile ve GEREKCELI yapilir. '
        'Numune/UGC gonderilerinin urun maliyeti henuz baglanmadi (BasitKargo '
        'tarafinda productId yok, yalniz urun adi var).',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-012: mart.maliyet_kalite ile olculdu - 36 kayit, tamami TAHMIN'
WHERE alan = 'cogs';


-- --------------------------------------------------------------------------
-- Bayat kalan satirlar  (ikinci tur denetimi)
-- --------------------------------------------------------------------------
-- 🔴 Bu satirlarin gap metinleri CR-004 ONCESINE aitti ve ARTIK YANLISTI.
--    "Ayna YOK - 37 siparisin hicbiri Postgres'te degil" diyen satirin
--    aynasi artik var (raw.wix_order, 37 kayit). Tam da bu dosyanin
--    uyardigi hal: harita hem veri akarken "akmiyor" diyor.
UPDATE core.source_authority SET
  mirror = 'raw.wix_order (37 siparis) + raw.wix_order_item (55 kalem)',
  freshness = 'gunluk 08:30',
  gap = 'Kalem indirimi 16.09.2026''ya kadar okunmuyordu, ciro %18,8 sisikti - '
        'duzeltildi ve ham veriden yeniden turetildi. '
        'AYNI GUN IKINCI HATA (CR-012): totals.total KDV DAHILDIR ve marj bu '
        'sayidan hesaplaniyordu; KDV %20, tutari 13.678,91 TL. Net ciro '
        'toplam-kdv = 68.394,59 (KDV dahil 82.073,50). Marj 47.073,50 yerine '
        '35.494,58 olmaliydi - %24,6 sisik. totals.subtotal MATRAH DEGILDIR '
        '(indirim oncesi liste), net ciro icin KULLANILMAZ. '
        'WhatsApp/telefon siparisleri Wix''e ELLE girilmedikce bu aynada gorunmez.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-012: kdv/(toplam-kdv)=0,2000 -> 37/37 siparişte tam %20; '
                      'kalem KDV haric toplami = siparis KDV haric toplami birebir'
WHERE alan = 'order';

UPDATE core.source_authority SET
  mirror = 'raw.bk_shipment.cod_var / cod_tutar / cod_durum',
  freshness = 'gunluk 08:30',
  gap = 'Tahsil edilmemis para artik takip ediliyor: mart.acik_isler icinde '
        'BEKLEYEN_KAPIDA_TAHSILAT dali var. Tahsilatin BANKAYA gectigi '
        'BasitKargo beyanina dayanir, banka ekstresiyle karsilastirilmaz.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-008: 11 COD gonderi, 4 COLLECTION_PENDING / 7 TRANSFERRED'
WHERE alan = 'payment_cod';

UPDATE core.source_authority SET
  gap = 'Wix stok alani GERCEK STOK DEGIL: 36/36 urunde 250 sabit. '
        'Sahip beyani: stok fiilen elde tutuluyor. Envanter otoritesi YOK.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-006: 36 urunun tamaminda stok_adet=250 olculdu'
WHERE alan = 'inventory';

-- 🔴 "DOGRULANMIS" ETIKETI FAZLA IDDIALI (ikinci tur denetimi).
--    Sinif adi "saglayici onayli" ima ediyor ama dayanak Wix'in
--    odeme_yontemi='PayTR' alani - PayTR'in KENDISI degil. CR-002.5'te
--    ogrenilen "Wix 'tahsil edildi' otoritesi DEGILDIR" dersi burada da
--    gecerli. Etiket kalir (degistirmek tum raporlari kirar) ama sinir
--    ACIKCA yazilir.
UPDATE core.source_authority SET
  gap = 'PayTR API''sine baglanti YOK. mart.siparis''teki "DOGRULANMIS" sinifi '
        'PayTR''in degil, WIX''IN beyanina dayanir (billingInfo.paymentMethod). '
        'Gercek dogrulama icin PayTR mutabakati gerekir - yapilmiyor.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-008: baglanti denenmedi, sinir belgelendi'
WHERE alan = 'payment_online';

-- --------------------------------------------------------------------------
-- CR-011: konusma verisi  (atif DENENDI, YAPILAMADI)
-- --------------------------------------------------------------------------
-- 🔴 "PARTIAL" cunku veri akiyor ama SATISA BAGLANAMIYOR.
--    Denendi ve olculdu (16.09.2026): 259 konusan kisi, ayni donemde 11
--    Wix musterisi, TAM AD ESLESMESI SIFIR. Messenger musteriyi PSID ile
--    tanir; bu kimlik Meta'ya ozeldir, Wix'te karsiligi YOKTUR. Mesaj
--    metinlerinde telefon 1/1468, e-posta 0/1468.
--    Ilk ad eslesmesi 6 bulundu ama 37 musteride yalniz 31 tekil ilk ad
--    var - ilk ad tekil kimlik DEGIL. O eslestirme uydurma atif uretirdi.
UPDATE core.source_authority SET
  current_connection = 'PARTIAL',
  authority = 'Meta Messenger (Sayfa gelen kutusu)',
  mirror = 'lcarlie.konusma (259) + lcarlie.mesaj (1468) -> mart.konusma_gunluk',
  freshness = '4 saatte bir (meta-aktar.sh)',
  gap = 'ATIF YAPILAMIYOR: PSID''nin Wix''te karsiligi yok, ad eslesmesi SIFIR. '
        'Olculen sey yalniz HACIM ve CEVAPSIZLIK. Gunluk konusma sayisi siparisle '
        'yan yana konabilir ama bu NEDENSELLIK DEGILDIR. '
        'Gercek atif icin: ajan musteriden telefon/e-posta almali ya da siparise '
        'referans kodu tasinmali - ikisi de urun karari. '
        'Instagram ve WhatsApp konusmasi bu aynada HIC YOK (259/259 messenger).',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-011: ad eslestirmesi 3 yontemle denendi (tam/onek/normalize+ilk ad), hepsi yetersiz'
WHERE alan = 'conversation_messenger';

-- 🔴 Guncellenmesi beklenen satir yoksa bu SESSIZ GECILMEZ: alan adi
--    degismis ya da seed eksik demektir.
DO $$
DECLARE eksik text;
BEGIN
  SELECT string_agg(a, ', ') INTO eksik
    FROM unnest(ARRAY['shipment','shipping_cost','ad_spend','cogs']) a
   WHERE NOT EXISTS (SELECT 1 FROM core.source_authority s WHERE s.alan = a);
  IF eksik IS NOT NULL THEN
    RAISE EXCEPTION 'Otorite haritasinda beklenen alan yok: %', eksik;
  END IF;
END $$;

COMMIT;
