-- =============================================================================
-- CR-017  ·  GTM KOK NEDEN DENETIMI  (17.09.2026)  -  READ-ONLY AUDIT
--
-- HICBIR PRODUCTION TAG DEGISTIRILMEDI / SILINMEDI / YAYINLANMADI.
-- GTM calisma alani degisikligi: 0. Beklemedeki degisiklik: 0.
--
-- SORU: G-KCPFLRG2RV'ye ayni kullanici eylemi icin neden IKI collect hit gidiyor?
-- CEVAP: B - DIRECT_GOOGLE_TAG + GTM_DUPLICATE  (asagida iki bagimsiz kanitla)
-- =============================================================================

BEGIN;

INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES

-- ---------------------------------------------------------------------------
-- A/B/C) GTM ENVANTERI  -  etiketler, hedef ID'leri, tetikleyiciler
-- ---------------------------------------------------------------------------
  ('cr017_gtm_envanteri', 'UC_ETIKET_IKISI_GA4',
   'GTM-5XR5TQKP (hesap lcarlie, kapsayici no 261286099) icinde TOPLAM 3 ETIKET var ve '
   'hepsi Meta pikseli 2469140530193842 kurulum sihirbazinin urettigi otomatik etiketler. '
   'IKISI GA4 HEDEFLI: '
   '(1) FB_CONVERSIONS_API-2469140530193842-Web-Tag-GA4_Config · tur: Google etiketi · '
   'Etiket kimligi: G-KCPFLRG2RV · ayar: send_page_view=true · tetikleyici: DOM Hazir. '
   '(2) FB_CONVERSIONS_API-2469140530193842-Web-Tag-GA4_Event · tur: GA4 Etkinligi · '
   'Olcum Kimligi: G-KCPFLRG2RV · Etkinlik Adi: {{Event}} (DINAMIK) · '
   'parametreler: user_data, currency, items, transaction_id, value, event_id, event_name, '
   'first_party_collection=true, x-fb-ck-fbp, x-fb-ck-fbc · '
   'tetikleyici: Custom_Event VEYA DOM Hazir. '
   '(3) FB_CONVERSIONS_API-2469140530193842-Web-Tag-Pixel_Template · tur: Meta Pixel. '
   'TETIKLEYICI KOSULU (kritik): Custom_Event tetikleyicisinin etkinlik adi REGEX ".+" ve '
   'kosul "Event sunu icermez: gtm." -> yani gtm. ile baslamayan HER dataLayer event''ini '
   'yakalayacak sekilde tanimli. '
   '🔴 AW-17698757160 BU KAPSAYICIDA HIC GECMIYOR: GTM icinde Google Ads''e ait tek bir '
   'etiket yok. Google Ads etiketi Wix''in kendi entegrasyonundan yukleniyor.'),

  ('cr017_gtm_hedef_referansi', 'AYNI_HEDEFI_IKI_ETIKET_KULLANIYOR',
   'GTM konsolu "Hedefler" ekrani: G-KCPFLRG2RV (tur: Google Analytics web akisi, '
   'kullanici erisimi: Bagli degil) yaninda "2" rozeti var ve Etiket referanslari '
   'bolumu bunu aciklıyor: ayni hedefi IKI etiket referans veriyor - GA4_Config ve GA4_Event. '
   'Yani GA4 olcum kimligi GTM icinde zaten iki yerden ele aliniyor; ustune Wix''in '
   'Google Etiketi yuvasindaki DOGRUDAN config ucuncu bir yol aciyor.'),

-- ---------------------------------------------------------------------------
-- D/E/F) HIT ATFI  -  her hit'i kaynagina bagladim
-- ---------------------------------------------------------------------------
  ('cr017_hit_atfi_yontemi', 'GTM_PARAMETRESI_PARMAK_IZI',
   'Ayirt edici alan collect istegindeki `gtm` parametresi: '
   'GTM kapsayicisindan cikan hit''ler kapsayici numarasini TASIYOR (…z89261286099za200), '
   'Wix''in dogrudan Google etiketinden cikanlar TASIMIYOR (…3791za200). '
   'Bagimsiz DOGRULAMA: GTM kaynakli hit''ler ep.event_name ve ep.x-fb-ck-fbp parametrelerini '
   'tasiyor - bunlar TAM OLARAK GA4_Event etiketinde tanimli parametreler. '
   'Wix kaynakli hit''ler bunlari tasimiyor, onun yerine ep.event_action / ep.event_category / '
   'ep.event_label tasiyor ve _ee=1 ile isaretli. '
   'Yani iki kanit birbirini dogruluyor: tag konfigurasyonu + calisma zamani payload.'),

  ('cr017_hit_atfi_sonuc', 'VIEW_ITEM_VE_PAGE_VIEW_CIFT',
   'OLCULEN (native urun sayfasi, tek oturum, ayni sid): '
   'gtm.dom     _s=1  -> GTM          🔴 GA4''e "gtm.dom" ADINDA COP EVENT gidiyor. '
   'view_item   _s=2  -> WIX_DIRECT (_ee=1) · view_item _s=3 -> GTM   => CIFT. '
   'page_view   _s=4  -> WIX_DIRECT (_ee=1) · page_view _s=5 -> GTM   => CIFT. '
   'add_to_cart _s=6  -> WIX_DIRECT (_ee=1)                            => bu kosuda TEK. '
   '🔴 add_to_cart ARALIKLI: 3 gozlemin 1''inde cift (_s=6 ve _s=7), 2''sinde tek. '
   'Neden tam izole EDILMEDI. Olasi aciklama: GTM etiketleri DOM Hazir''da atesleniyor ve '
   'Wix''in gtag(''event'',...) cagrisi GTM''e Ozel Etkinlik olarak gorunmuyor; add_to_cart '
   'DOM Hazir''dan cok sonra olustugu icin cogu kosuda GTM tarafindan tekrarlanmiyor. '
   'VARSAYIM DEGIL, HIPOTEZ olarak kayitli.'),

-- ---------------------------------------------------------------------------
-- G) PURCHASE
-- ---------------------------------------------------------------------------
  ('cr017_gtm_purchase_durumu', 'OZEL_PURCHASE_TAGI_YOK_RISK_VAR',
   'GTM''de purchase''a OZEL bir etiket YOK. Ancak GA4_Event etiketinin Etkinlik Adi {{Event}} '
   'DINAMIK ve tetikleyici regex ".+" oldugu icin, dataLayer''a {event:''purchase''} seklinde '
   'bir push duserse AYNI ETIKET purchase''i da G-KCPFLRG2RV''ye iletir. '
   'Etikette transaction_id ve value parametreleri ZATEN tanimli - yani purchase''i iletmeye '
   'hazir kurulmus. '
   '🔴 Wix''in Tesekkur Sayfasi''nda purchase uretip uretmedigi ve bunun GTM tarafindan '
   'tekrarlanip tekrarlanmadigi OLCULMEDI - gercek siparis gerektirir, test siparisi '
   'URETILMEDI. Durum: NOT_VERIFIED.'),

-- ---------------------------------------------------------------------------
-- H) KOK NEDEN
-- ---------------------------------------------------------------------------
  ('cr017_cift_hit_kok_neden', 'B_DIRECT_GOOGLE_TAG_ARTI_GTM_DUPLICATE',
   'SINIFLAMA: B (DIRECT_GOOGLE_TAG + GTM_DUPLICATE). '
   'C (GOOGLE_ADS_DESTINATION_FORWARDING) ELENDI: AW-17698757160 GTM kapsayicisinda hic '
   'gecmiyor ve GA4 hedefinin etiket referanslari yalniz iki GTM etiketi. '
   'D (SAME_TAG_INTENTIONAL_MULTI_HIT) ELENDI: iki hit FARKLI gtm parametresi ve FARKLI '
   'parametre setleri tasiyor - ayni etiketin bilincli cok-hit''i degil, iki AYRI gonderici. '
   'MEKANIZMA: G-KCPFLRG2RV ayni sayfada IKI KEZ config ediliyor - (1) Wix > Pazarlama '
   'Entegrasyonlari > Google Etiketi (17.09.2026''da BEN ekledim), (2) GTM icindeki '
   'GA4_Config Google etiketi (bir ay once Meta CAPI sihirbazi kurmus). '
   'Ustune GA4_Event etiketi DOM Hazir''da {{Event}} ile ikinci bir gonderim yapiyor. '
   '🔴 ZAMANLAMA SORUMLULUGU: GTM etiketleri BENDEN ONCE vardi (bir ay once). Bu demektir ki '
   'GA4 bu kimlige zaten GTM uzerinden veri gonderiyordu; 17.09''da Wix yuvasina ayni kimligi '
   'eklemem IKINCI gondericiyi ekledi. Yani cift hit''in bugunku halini BENIM DEGISIKLIGIM '
   'tamamladi. Onceki raporumdaki "cift sayim olusmadi" ifadesi bu nedenle YANLISTI.'),

  ('cr017_ga4_cop_event', 'GTM_DOM_EVENTI_GA4E_GIDIYOR',
   '🔴 Cift sayimdan BAGIMSIZ ikinci bir kirlilik: GA4_Event etiketi DOM Hazir tetikleyicisiyle '
   'de atesleniyor ve o anda {{Event}} degeri "gtm.dom" oluyor. Sonuc: GA4''e her sayfa '
   'yuklemesinde "gtm.dom" ADINDA bir event gidiyor (olculdu: tid=G-KCPFLRG2RV en=gtm.dom _s=1). '
   'Bu GA4 event listesini kirletir ve event sayimlarini sisirir.'),

-- ---------------------------------------------------------------------------
-- I/J/K) DUZELTME ONERISI  -  UYGULANMADI
-- ---------------------------------------------------------------------------
  ('cr017_cift_hit_duzeltme_onerisi', 'ONERILDI_UYGULANMADI',
   'MINIMUM DUZELTME (tek degisiklik, en az yan etki): GTM icindeki GA4_Config ve GA4_Event '
   'etiketlerini GA4 hedefinden ayirmak - yani GA4 gonderimini TEK kaynakta toplamak. '
   'HANGISI KALMALI: Wix > Pazarlama Entegrasyonlari > Google Etiketi (G-KCPFLRG2RV). '
   'GEREKCE: (a) urun bagimsiz ve kodsuz, (b) ecommerce parametrelerini (items, currency) '
   'Wix''in kendisi dolduruyor, (c) GTM''deki etiketler Meta CAPI sihirbazinin yan urunu - '
   'asil isleri Meta pikseli, GA4 kismi istenmeden gelmis, (d) GTM tarafi ayrica gtm.dom '
   'cop event''i uretiyor. '
   '🔴 DIKKAT: GA4_Event etiketi SILINMEMELI diye dusunuyorum - Meta CAPI event eslemesi icin '
   'event_id/x-fb-ck-* degiskenlerini paylasan bir yapi var; once Pixel_Template etiketinin '
   'bu etikete bagimli olup olmadigi incelenmeli. Minimum mudahale: GA4 etiketlerinin '
   'olcum kimligini bosaltmak/duraklatmak, SILMEK degil. '
   'ROLLBACK: GTM surum tabanlidir - her yayinlanan degisiklik bir Surum olusturur ve '
   '"Surumler" ekranindan onceki surume tek adimda geri donulebilir. Ayrica degisiklik '
   'once Onizleme (Tag Assistant) ile yayinlanmadan test edilebilir. '
   'Wix tarafi rollback: Google Etiketi yuvasindan G-KCPFLRG2RV kaldirilir (tek adim). '
   '🔴 HICBIRI YAPILMADI - Chief Architect onayi bekleniyor.'),

  ('cr017_raw_browser_duplicate_risk', 'TRUE',
   'Tarayici agina IKI ayri collect hit cikiyor (view_item ve page_view icin her kosuda, '
   'add_to_cart icin araliklı). GA4''un sunucu tarafinda bunlari tekillestirdigi '
   'VARSAYILMIYOR - GA4 property erisimi (DebugView/Realtime) olmadan dogrulanamaz ve '
   'o erisim BLOCKED_BY_EXTERNAL_CREDENTIAL. '
   'Bu bayrak, GA4 DebugView ile tek eylemin kac event urettigi GORULENE kadar TRUE kalir. '
   '🔴 BU BAYRAK TRUE IKEN: yeni Custom Code bridge EKLENMEZ, Velo enstrumantasyonu '
   'EKLENMEZ, purchase event EKLENMEZ, funnel MEASURED/READY ILAN EDILMEZ.')

ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- Onceki risk kaydini kok neden bulundugu icin guncelle (audit trail: silinmiyor).
UPDATE core.ayar SET
  deger = 'KOK_NEDEN_BULUNDU_BKZ_cr017_cift_hit_kok_neden',
  aciklama = aciklama || ' || 17.09.2026 GUNCELLEME: hipotez DOGRULANDI. Kok neden '
             'B (DIRECT_GOOGLE_TAG + GTM_DUPLICATE). Ayrinti: cr017_cift_hit_kok_neden, '
             'cr017_gtm_envanteri, cr017_hit_atfi_sonuc.',
  guncelleme = clock_timestamp()
WHERE anahtar = 'cr017_ga4_cift_hit_riski'
  AND aciklama NOT LIKE '%17.09.2026 GUNCELLEME: hipotez DOGRULANDI%';

COMMIT;
