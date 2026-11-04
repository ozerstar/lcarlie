-- =============================================================================
-- L'CARLIE - SOURCE AUTHORITY MAP  (makine okunur)
--
-- CR-003 · 16.09.2026 · gercek sistemle DOGRULANDI
--
-- 🔴 POSTGRESQL HICBIR ALANIN SOURCE OF TRUTH'U DEGILDIR.
--    Yalnizca 'decision_records' Postgres'te DOGAR. Diger her sey
--    bir dis sistemin AYNASIDIR. Bu tablo, ileride biri "Postgres'te
--    yaziyor demek ki dogru" dedigi an ona ne oldugunu hatirlatir.
--
-- 🔴 DOGRULANMAYAN HICBIR SATIR 'CONNECTED' YAZILMADI.
--    BasitKargo urun dokumaninda tam API var - ama BIZIM tarafta
--    hicbir baglanti yok. Yetenek ile baglanti ayri seylerdir.
--
-- current_connection:
--   CONNECTED            : canli dogrulandi, veri akiyor
--   PARTIAL              : erisim var ama eksik/akmiyor
--   SOURCE_NOT_CONNECTED : kaynak sistem var, bizde baglanti YOK
--   NONE                 : kaynak sistem de yok
--   UNKNOWN              : otorite belirlenemedi
-- =============================================================================

BEGIN;

INSERT INTO core.source_authority
  (alan, authority, mirror, freshness, current_connection, gap, dogrulama_zamani, dogrulama_yontemi, notlar)
VALUES

-- --- SIPARIS ------------------------------------------------------------------
('order', 'Wix Stores', 'raw.wix_order (CR-004)', 'canli (API)', 'CONNECTED',
 'Ayna YOK - 37 siparisin hicbiri Postgres''te degil. Tam ETL CR-004.',
 now(), 'stores/v2/orders/query -> HTTP 200, 37 siparis',
 '32 tekil buyer_id. Kanal %100 WEB.'),

-- --- ODEME: ONLINE ------------------------------------------------------------
('payment_online', 'PayTR', 'Wix paymentStatus', 'canli (Wix uzerinden)', 'SOURCE_NOT_CONNECTED',
 'PayTR API/panel baglantisi yok. Tahsilat, mutabakat ve komisyon verisi alinamiyor.',
 now(), 'Wix billingInfo.paymentMethod dagilimi: PayTR=21',
 'Wix paymentStatus PayTR icin GUVENILIR ayna sayilabilir; otorite yine PayTR.'),

-- --- ODEME: CEVRIM DISI  🔴 ------------------------------------------------------
('payment_offline', 'UNKNOWN', 'Wix paymentStatus (INSAN BEYANI)', 'elle, gecikmeli', 'UNKNOWN',
 'ODEMELERIN %43''U BURADA. "PAID" bilgisini bir insan elle isaretliyor; hangi '
 'operasyon/muhasebe kaydina dayandigi BELIRLENMEDI. Gercek tahsilat kaynagi '
 'tespit edilene kadar bu siparisler CIRO olarak sayilmamalidir.',
 now(), 'Wix billingInfo.paymentMethod: "Cevrim Disi Odemeler"=16 / 37',
 'MANUEL EYLEM: kim, ne zaman, neye bakarak PAID isaretliyor? Banka ekstresi mi, kapida odeme mi?'),

-- --- FIYAT --------------------------------------------------------------------
('price', 'Wix Stores katalog', 'fiyat-gecmisi.jsonl + urunler.js', 'gunluk 09:00 cron', 'CONNECTED',
 'urunler.js ELLE yazili - bayatlama riski. Ayna Postgres''te degil, dosyada.',
 now(), 'fiyat-log.sh cron calisiyor; products/query -> 200, 36 urun',
 'Fiyat Etiketi Yonetmeligi m.11/1 ispat kaydi bu logdur.'),

-- --- ENVANTER  🔴 OTORITE DOGRULANMADI -------------------------------------------
('inventory', 'UNKNOWN (Wix mi fiziksel depo mu)', 'Wix inventoryItems', 'canli (Wix)', 'PARTIAL',
 'Wix API erisilebiliyor ama 39 kalemin YALNIZ 9''unda trackQuantity acik. '
 '30 kalemde Wix stok TUTMUYOR - yani Wix bu kalemlerde otorite OLAMAZ. '
 'Fiziksel deponun kayit tuttugu dogrulanamadi. VARSAYILMADI.',
 now(), 'stores/v2/inventoryItems/query -> 200, 39 kalem, 9 takipli',
 'MANUEL EYLEM: stok fiilen nerede tutuluyor? 30 kalemde takip neden kapali?'),

-- --- REKLAM HARCAMASI ---------------------------------------------------------
('ad_spend', 'Meta Ads', NULL, NULL, 'SOURCE_NOT_CONNECTED',
 'Hicbir baglanti yok. ROAS/CAC hesaplanamaz.',
 now(), 'n8n credential=0, .env''de Ads tokeni yok',
 '3 reklam hesabi mevcut (SAGLIKLI YASAM REHBERI portfolyosu).'),

-- --- DAVRANIS -----------------------------------------------------------------
('behavior', 'GA4 / GTM', NULL, 'canli (sitede)', 'PARTIAL',
 'GTM sitede calisiyor ama VDS''e HIC veri akmiyor. GA4 API baglantisi yok.',
 now(), 'lcarlie.shop ana sayfasinda GTM-5XR5TQKP bulundu',
 'Meta pikseli GTM icinde; ham HTML''de fbq yok.'),

-- --- KONUSMA: WHATSAPP --------------------------------------------------------
('conversation_whatsapp', 'Meta - WhatsApp Business Uygulamasi', 'n8n staticData (yalniz test)', NULL, 'SOURCE_NOT_CONNECTED',
 'Numara Cloud API''ye BAGLI DEGIL - Business App''te. Webhook''a gercek mesaj '
 'YAPISAL OLARAK dusemez ve gecmis okuma API''si yok.',
 now(), 'CR-001/CR-002.5 olcumu: 0 gercek mesaj; tum kayitlar karantinada test',
 'Cloud API''ye tasima ayri ve riskli is - Meta AI o kanali yurutuyor.'),

-- --- KONUSMA: INSTAGRAM -------------------------------------------------------
('conversation_instagram', 'Meta - Instagram DM', 'lcarlie.mesaj (bos)', NULL, 'SOURCE_NOT_CONNECTED',
 'Token .env''de VAR ama /conversations?platform=instagram surekli '
 '"Please reduce the amount of data" donuyor - alanlar daraltilsa da. '
 'Okuma FIILEN calismiyor. n8n''de 0 credential, 0 dugum.',
 now(), 'graph.facebook.com v21.0 /{page}/conversations?platform=instagram -> hata',
 'IG hesabi sayfaya bagli dogrulandi (id 17841403255774414).'),

-- --- KONUSMA: MESSENGER  ✅ YENI ------------------------------------------------
('conversation_messenger', 'Meta - Messenger', 'lcarlie.mesaj (bos)', 'canli (API)', 'PARTIAL',
 'Okuma CALISIYOR (10 konusma / 83 mesaj) ama n8n''e BAGLI DEGIL: '
 '0 credential, 0 dugum, ayna tablosu bos. Veri hic cekilmiyor.',
 now(), 'FB_PAGE_TOKEN ile /{page}/conversations -> 10 konusma, 83 mesaj',
 'Sayfa dogrulandi: L''carlie Natural Cosmetics (1222783064240254).'),

-- --- KARGO / TESLIMAT  🔴 ---------------------------------------------------------
-- 🔴 PANEL DOGRULAMASI (16.09.2026): BasitKargo hesabi CANLI ve Wix
--    entegrasyonu 29 Haz 2026''den beri AKTIF (magaza "L''CARLIE", marka
--    "Lcarlie.shop"). Yani veri ORADA duruyor ve duzenli akiyor.
--    Bizim tarafta HICBIR programatik erisim yok: API token URETILMEMIS
--    ("Yeni Token Uret" dugmesi bos bir listenin ustunde), webhook
--    TANIMLANMAMIS ("Yeni Webhook Olustur"). Yani ne cekebiliyoruz ne
--    de bize itiliyor. Baglanti durumu bu yuzden SOURCE_NOT_CONNECTED.
('shipment', 'BasitKargo', 'BasitKargo paneli (bizde ayna YOK) · Wix trackingInfo (kismi)',
 'canli (panelde)', 'SOURCE_NOT_CONNECTED',
 'Veri BasitKargo''da MEVCUT ama bize akmiyor: API token uretilmemis, webhook '
 'tanimlanmamis, n8n''de 0 credential/0 dugum, .env''de anahtar yok. '
 'Wix''teki takip bilgisi teslim edilmis 32 siparisin yalniz 10''unda var - '
 'yani Wix da tam ayna DEGIL.',
 now(), 'basitkargo.com/panel/integrations + /panel/stats goruntulendi',
 'Panelde olculen (Eylul 2026): siparis 10 · gonderilen 9 · TESLIM 4 · IADE 0 · '
 'KAYIP 0 · ort. teslimat 1 gun · ort. desi 1.12. Tasiyici performansi: '
 'HepsiJET 3 (%100 basari, "Onerilen"), Surat 6 (%16.7 basari, "Dikkat"). '
 'Aylik gecmis Ocak 2026''ya kadar filtrelenebiliyor. API dokumani: Bearer, '
 'webhook, POST /v2/order, POST /v2/order/filter (toplu export), COD durumu. '
 'YETENEK VAR + VERI VAR + BAGLANTI YOK.'),

-- --- KARGO MALIYETI  ✅ YENI ------------------------------------------------------
-- 🔴 CR-003''te "COGS yok, contribution margin hesaplanamaz" demistim.
--    Eksik olan URUN maliyeti; KARGO maliyeti ayri bir girdi ve BasitKargo''da
--    siparis basina MEVCUT. Iki eksigi tek kova sayip "hic veri yok" demek
--    yanlis olurdu - duzeltiliyor.
('shipping_cost', 'BasitKargo', 'yok', 'canli (panelde)', 'SOURCE_NOT_CONNECTED',
 'Siparis basina kargo maliyeti BasitKargo''da var ama bize akmiyor. '
 'Contribution margin icin gereken iki girdiden BIRI cozulmus durumda; '
 'eksik olan URUN maliyeti (COGS).',
 now(), 'basitkargo.com/panel/stats (Eylul 2026)',
 'Olculen: toplam kargo maliyeti ₺990,87 · ort. kargo ₺110,10 · '
 'basarili kargo maliyeti ₺110,10 · ort. desi 1.12.'),

-- --- SIPARIS KAYNAGI UYUSMAZLIGI  🔴 YENI -----------------------------------------
('order_channel_mismatch', 'Wix + BasitKargo (IKISI BIRDEN)', 'yok', 'canli', 'PARTIAL',
 'BasitKargo Eylul''de 9 gonderinin kaynagini soyle gosteriyor: Wix 4, '
 '"Web Panel" 5. Yani gonderilerin YARIDAN COGU Wix entegrasyonundan '
 'GELMIYOR, panele elle giriliyor. Wix''in siparislerin TAMAMININ otoritesi '
 'oldugu varsayimi bu yuzden dogrulanmadi.',
 now(), 'basitkargo.com/panel/stats -> "Satis Kanali Performansi"',
 'Wix 4 siparis ₺10.889 (ort ₺2.722) · Web Panel 5 siparis ₺4.800 (ort ₺960). '
 'MANUEL EYLEM: "Web Panel" gonderileri Wix siparislerinin elle yeniden '
 'girilmis hali mi, yoksa Wix''te HIC OLMAYAN satislar mi? '
 'CR-004 siparis aynasinin kapsamini bu belirler.'),

-- --- COGS ---------------------------------------------------------------------
('cogs', 'Manuel finans kaydi (henuz yok)', NULL, NULL, 'NONE',
 'Wix''te 36 urunden YALNIZ 1''inde maliyet dolu. Contribution margin '
 'hesaplanamaz - hesaplanirsa YANLIS olur.',
 now(), 'stores/v1/products/query costRange alani: 1/36 dolu',
 'CR-004 icin manuel finans tablosu gerekebilir.'),

-- --- KARAR KAYITLARI ----------------------------------------------------------
('decision_records', 'PostgreSQL (core/mart)', NULL, 'canli', 'CONNECTED',
 'Tek "dogdugu yer Postgres olan" alan. Henuz kayit uretilmiyor.',
 now(), 'core semasi kuruldu (CR-003)',
 'Diger tum alanlarda Postgres yalnizca AYNA''dir.')

ON CONFLICT (alan) DO UPDATE SET
  authority          = EXCLUDED.authority,
  mirror             = EXCLUDED.mirror,
  freshness          = EXCLUDED.freshness,
  current_connection = EXCLUDED.current_connection,
  gap                = EXCLUDED.gap,
  dogrulama_zamani   = EXCLUDED.dogrulama_zamani,
  dogrulama_yontemi  = EXCLUDED.dogrulama_yontemi,
  notlar             = EXCLUDED.notlar;

COMMIT;
