// =====================================================================
// L'CARLIE - URUN BILGI TABANI
//
// KAYNAK: KAYNAK_Katalog_YENI_uyumlu_docx.txt (mevzuata uygun YENI katalog)
//         + 02_URUN_GERCEGI.md (fiyat ve durum)
// ESKI katalog PDF'i kaynak olarak KULLANILMADI (iddia bakimindan bloklu).
//
// KAPSAM KARARI (12.09.2026): Sadece "site metni temiz" ve Ay 1 odagindaki
// iki urun. Diger 37 urun icin ajan siteye yonlendirir.
// VIREON/FEMISIA/INTIMBLANC/LIFTELLE/SOFTGUARD/BUGUARD kanal disi - filtre bloklar.
// =====================================================================

const URUNLER = {
  LUCIDERM: {
    ad: 'LUCIDERM',
    altBaslik: 'Yüz Temizleme Köpüğü',
    fiyat: '1.200 TL',
    hacim: null,               // Sitede hacim yok - UYDURULMADI
    fiyatTarihi: '12.09.2026 (Wix Stores ile dogrulandi)',
    urunSayfasi: 'https://www.lcarlie.shop/product-page/luciderm',
    sku: '8684869609295',
    stokTakibi: false,

    // Sitedeki dil katalogtan DAHA TEMIZ: katalog "yagli ve akneye egilimli
    // ciltler" diyor, site "tum cilt tipleri" diyor. Hastalik adi gecmeyen
    // site dili tercih edildi.
    aciklama: 'Tüm cilt tiplerinin günlük yüz temizleme rutinine eşlik etmek üzere geliştirilmiş, ' +
              'bitki bazlı yüz temizleme köpüğüdür. Cildi kurutmadan temizlemeye yardımcı olmayı amaçlar. ' +
              'Günlük kullanıma uygundur.',

    aktifler: [
      'Lavanta & Melisa Suyu',
      'Aloe Vera',
      'Çay Ağacı & Niaouli Yağı',
      'Beyaz Söğüt Kabuğu Ekstresi',
      'Yulaf Seramidi',
      'Yeşil Çay & Biberiye Ekstresi'
    ],

    inci: 'Aqua, Lavandula Angustifolia Flower Water, Melissa Officinalis Water, ' +
          'Aloe Barbadensis Leaf Juice, Decyl Glucoside, Cocamidopropyl Betaine, ' +
          'Sodium Cocoyl Glutamate, Melaleuca Alternifolia Oil, Melaleuca Quinquenervia Oil, ' +
          'Lavandula Angustifolia Oil, Chamomilla Recutita CO2 Extract, Hamamelis Virginiana Extract, ' +
          'Salix Alba Bark Extract, Rosmarinus Officinalis Extract, Avena Sativa (Oat) Kernel Ceramide, ' +
          'Betaine, Sodium Hyaluronate, Camellia Sinensis Leaf CO2 Extract, Cichorium Intybus Root Extract, ' +
          'Glycerin, Lactic Acid, Benzyl Alcohol, Salicylic Acid, Sorbic Acid.',

    kullanim: 'Sabah ve akşam nemli yüze 1–2 pompa uygulanır, parmak uçlarıyla köpürtülüp ılık suyla durulanır. ' +
              'Göz çevresiyle doğrudan temastan kaçınılır.',

    anahtarKelimeler: ['luciderm', 'lusiderm', 'temizleme kopugu', 'yuz temizleme', 'kopuk'],
    gunesUrunu: false,
    dogrulamaNotu: 'Sitedeki aciklamada yazim hatasi var: "L\'CARLIE Lucidem" (marka adi eksik R, aksan yok).'
  },

  CALMAROS: {
    ad: 'CALMAROS',
    altBaslik: 'Ferahlatıcı Tonik Sprey',
    canonicalAd: 'CALMAROS Ferahlatıcı Tonik Sprey',
    fiyat: '1.850 TL',
    hacim: null,               // Ne kutuda ne sitede var - UYDURULMADI
    fiyatTarihi: '13.09.2026 (Wix Stores ile dogrulandi)',
    urunSayfasi: 'https://www.lcarlie.shop/product-page/calmaros',
    sku: '8684869609080',
    stokTakibi: false,
    rafOmru: '24 ay',

    // 🔴 CILT TIPI IDDIASI BILEREK YOK.
    // Kutu metni "hassas ve kizarikliga yatkin ciltler icin ozel olarak
    // gelistirilmis" diyor; SITE ise sadece "ferahlik ve bakim hissi" diyor.
    // Ayrica Master Matrix formulde karanfil ve tarcin kabugu yagi oldugunu
    // ve urunun otomatik "ultra hassas" varsayilani OLMADIGINI yaziyor.
    // Bu celiski cozulene kadar ajan kime uygun oldugunu iddia etmez.
    aciklama: 'Günlük bakımda ferahlık ve hafif nem hissi sunmak üzere tasarlanmış tonik spreydir. ' +
              'Bakım rutininin farklı anlarında pratik biçimde kullanılabilir. ' +
              'Temiz cilde sabah ve akşam uygulanır.',

    aktifler: [
      'Gül Suyu',
      'Papatya Suyu',
      'Aynısefa Ekstresi',
      'Aloe Vera',
      'Lavanta Suyu',
      'Yeşil Çay Ekstresi'
    ],

    inci: 'Rosa Damascena Flower Water, Chamomilla Recutita (Matricaria) Flower Water, ' +
          'Calendula Officinalis Flower Extract, Aloe Barbadensis Leaf Juice, ' +
          'Lavandula Angustifolia Flower Water, Eugenia Caryophyllus Bud Oil, ' +
          'Cinnamomum Zeylanicum Bark Oil, Camellia Sinensis Leaf Extract, Glycerin, ' +
          'Aqua, Benzyl Alcohol, Salicylic Acid, Sorbic Acid.',

    kullanim: 'Temiz cilde sabah ve akşam, yaklaşık 20 cm mesafeden püskürtülür. ' +
              'İsteğe bağlı olarak pamuk yardımıyla da uygulanabilir. Göz ile temas ettirilmez.',

    anahtarKelimeler: ['calmaros', 'calmarosa', 'calmaris', 'tonik sprey', 'ferahlatici tonik'],
    gunesUrunu: false,
    dogrulamaNotu: 'Kutu metni "CalmaRos", site "CALMAROS" yaziyor - kanonik ad teyit edilmeli. ' +
                   'Kutu ile site cilt tipi ifadesinde ayrisiyor.'
  },

  HYDRAVIE: {
    ad: 'HYDRAVIE',
    // "El & Yuz" GERI ALINDI (12.09.2026 - kutu icerik metni bulundu).
    // Sise on yuzu sadece "For Dry and Sensitive Skin" diyor ve kullanim
    // bolgesi yazmiyor; ama RESMI KUTU ICERIK METNI acikca
    // "El & Yuz Nemlendirici Krem" / "Hand & Face Moisturizing Cream" diyor.
    // Kaynak: 02 LEMOS-MOY\lemos\kutu-icerik-son\23-hydravie.pdf
    altBaslik: 'El & Yüz Nemlendirici Krem',
    canonicalAd: 'HYDRAVIE El & Yüz Nemlendirici Krem',
    // 🔴 ACIK CELISKI: Kutu metni "Tum cilt tipleri icin uygundur" diyor,
    // sise on yuzu "For Dry and Sensitive Skin" diyor, site "kuru ve hassas"
    // diyor. Ajan cilt TIPI iddiasinda bulunmuyor - sadece nem bakimi diyor.
    raffOmru: '24 ay',
    // Fiyat kaynagi: 02_URUN_GERCEGI.md (06.09.2026).
    // TODO: Wix Stores entegrasyonu gelince fiyat canli API'den cekilmeli,
    //       boylece burada bayatlamaz.
    fiyat: '1.200 TL',
    hacim: '50 ml',
    // Wix Stores canli API'den dogrulandi (12.09.2026): 1200 TRY, inStock.
    fiyatTarihi: '12.09.2026 (Wix Stores ile dogrulandi)',
    urunSayfasi: 'https://www.lcarlie.shop/product-page/hydravie',
    sku: '8684869609233',
    // 🔴 Wix'te trackInventory=false -> "inStock" her zaman true doner.
    // Bu urun icin GERCEK stok bilgisi yok, stok vaadi verilmez.
    stokTakibi: false,

    // Katalogtaki uyumlu dilden, kisaltilarak
    // Resmi kutu metnine dayanir. CILT TIPI iddiasi BILEREK YOK - kutu "tum cilt
    // tipleri", sise "kuru ve hassas" diyor, celiski cozulene kadar soylenmez.
    aciklama: 'Bitkisel özler ve doğal yağlarla formüle edilmiş, el ve yüz için günlük bakım kremidir. ' +
              'Cildin nem dengesini korumaya ve yumuşatmaya yardımcı olur. ' +
              'Hafif dokusu sayesinde hızlı emilir. Sabah ve akşam kullanıma uygundur.',

    // 🔴 "Ceramide Kompleksi" BILEREK YOK.
    // Katalog aciklamasinda geciyor ama INCI listesinde seramid BULUNMUYOR.
    // Resmi urun dosyasiyla cozulene kadar seramid iddiasi kullanilmaz.
    aktifler: [
      'Squalane & Shea Butter',
      'Bakuchiol',
      'Nar Çekirdeği Yağı',
      'Sodium Hyaluronate',
      'Niacinamide',
      'Panthenol'
    ],

    // 🔴 INCI KAYNAGI: canli urun sayfasi (guncelleme 03.09.2026).
    // Katalog metnindeki liste EKSIK: "Decyl Glucoside" ve "Potassium Sorbate"
    // katalogda yok, sitede var. Eksik INCI listesi hassasiyeti olan musteri
    // icin risk oldugundan GENIS olan (site) listesi kullaniliyor.
    // Resmi urun dosyasi/etiket ile teyit edilmeli.
    inci: 'Aqua, Aloe Barbadensis Leaf Juice, Panthenol, Glycerin, Sodium Hyaluronate, ' +
          'Niacinamide, Squalane, Butyrospermum Parkii Butter, Cocos Nucifera Oil, ' +
          'Simmondsia Chinensis Seed Oil, Punica Granatum Seed Oil, Bakuchiol, Tocopherol, ' +
          'Calendula Officinalis Flower Oil, Chamomilla Recutita Flower Oil, Allantoin, ' +
          'Cetearyl Alcohol, Cetearyl Glucoside, Benzyl Alcohol, Salicylic Acid, Sorbic Acid, ' +
          'Decyl Glucoside, Potassium Sorbate.',

    kullanim: 'Temiz cilde, el ve yüz bölgesine ince bir tabaka halinde uygulanır. Günlük kullanıma uygundur.',

    anahtarKelimeler: ['hydravie', 'hidravie', 'nemlendirici', 'nemlendirci', 'el kremi', 'yuz kremi'],
    gunesUrunu: false,
    dogrulamaNotu: 'Seramid iddiasi bloklu (INCI teyidi bekliyor).'
  },

  SUNACNEA: {
    ad: 'SUNACNEA',
    // 🔴 Kilitli lockup - urun adi tek basina iddiadir, her yerde TAM yazilir.
    lockup: 'SUNACNEA · SPF 30 Günlük Güneş Koruyucu',
    altBaslik: 'Mineral Filtreli Güneş Koruyucu',
    fiyat: '1.200 TL',
    // AMBALAJ ETIKETINDEN dogrulandi (12.09.2026 foto incelemesi):
    // "50 ml e / 1.69 fl oz". Katalogda ve sitede hacim hic yazmiyordu.
    hacim: '50 ml',
    // 🔴 14.09.2026 SAHIP KARARI: resmi barkodlu fiyat listesi 1.200 TL diyordu,
    //    site ve ajan 990 TL. Sahip "liste dogru" dedi -> Wix'te fiyat 1.200'e
    //    cekildi ve buraya da yazildi. Ikisi ayri kalirsa musteriye yanlis
    //    fiyat beyan edilmis olur.
    fiyatTarihi: '14.09.2026 (Wix Stores ile dogrulandi: 1.200 TRY)',
    urunSayfasi: 'https://www.lcarlie.shop/product-page/sunacnea-30-spf',
    sku: '8684869609097',
    stokTakibi: true,          // Wix'te gercek stok takibi acik

    // ✅ SPF DEGERI SAHIP KARARIYLA SABITLENDI (Ozer Yildiz, 13.09.2026): 30
    // Ust kaynaklarla uyumlu: sise etiketi "30 SPF", guvenlik raporu
    // "42-L'CARLIE SUNACNEA 30 SPF.pdf". Acik soru kapandi.
    // NOT: Musteriye giden metinde mevzuatin sart kostugu lockup kullanilir
    // ("SUNACNEA · SPF 30 Gunluk Gunes Koruyucu") - bu ayri bir gereklilik.
    spf: '30',
    spfKaynak: 'Sahip karari 13.09.2026 + sise etiketi + guvenlik raporu',
    // 🔴 SITEDEKI URUN ADI LOCKUP'A UYMUYOR: "SUNACNEA +30 SPF (Gunes Kremi)".
    // 03_MEVZUAT §4 "SUNACNEA · SPF 30 Gunluk Gunes Koruyucu" sart kosuyor.
    // Ajan HER ZAMAN dogru lockup'i kullanir; site tarafi duzeltilmeli.
    siteAdiUyumsuz: 'SUNACNEA +30 SPF (Güneş Kremi)',

    // "akneye egilimli" ifadesi BILEREK KULLANILMIYOR.
    // Katalogun onayli alt basligi oyle, ancak 03_MEVZUAT §11 SUNACNEA icin
    // "akne/sivilce/leke geciyor mu" kontrolunu ayrica sart kosuyor.
    // Otomatik ajanin agzindan hastalik/semptom adi cikmaz.
    aciklama: 'Hassas ciltler için geliştirilmiş mineral filtreli güneş koruyucu kremdir. ' +
              'İçeriğindeki çinko oksit ile geniş spektrumlu (UVA/UVB) güneş koruması sağlar. ' +
              'Hafif yapısı sayesinde ciltte ağırlık hissi oluşturmaz, günlük kullanıma uygundur.',

    aktifler: [
      'Zinc Oxide (Non-Nano)',
      'Tamanu Yağı',
      'Nar & Üzüm Çekirdeği Yağları',
      'Aronia Fermenti',
      'Sandal Ağacı & Mür Yağı'
    ],

    inci: 'Aqua, Calophyllum Inophyllum Seed Oil, Punica Granatum Seed Oil, Vitis Vinifera Seed Oil, ' +
          'Commiphora Myrrha Oil, Santalum Album Extract, Zinc Oxide (Non-Nano), Butyrospermum Parkii Butter, ' +
          'Cocos Nucifera Oil, Aloe Barbadensis Leaf Juice, Aronia Melanocarpa Fruit Ferment Filtrate, ' +
          'Glycerin, Cetearyl Olivate, Sorbitan Olivate, Tocopherol, Benzyl Alcohol, Salicylic Acid, Sorbic Acid.',

    kullanim: 'Güneşe çıkmadan önce yeterli miktarda uygulanır ve gün içinde ihtiyaç duyuldukça yenilenir.',

    anahtarKelimeler: ['sunacnea', 'sunacne', 'gunes koruyucu', 'gunes kremi', 'spf'],
    gunesUrunu: true,
    dogrulamaNotu: 'Hacim bilgisi katalogda yok. Lockup her cevapta tam gecmeli.'
  },

  // ===================================================================
  // 13.09.2026 GENISLETME - 26 urun eklendi (toplam 30)
  //
  // Kaynak: lcarlie.shop canli katalog (URUN-KATALOGU.md), mevzuat
  // duzeltmeleri YAPILDIKTAN SONRA alindi.
  //
  // 🔴 ACIKLAMALAR KISALTILDI ve KATALOG-YAZIM-KILAVUZU'na gore yazildi.
  //    Her biri mevzuat filtresinden gecirildi.
  //
  // 🔴 INCI: yeni urunlerde tam liste TASINMIYOR (dosya 90KB'a cikiyordu).
  //    Ajan one cikan icerikleri sayar, tam listeyi urun sayfasina yonlendirir.
  //    INCI zaten kutuda ve urun sayfasinda yasal olarak mevcut.
  //
  // 🔴 URUN ADI IDDIA ICEREN 3 URUN: sitedeki ad filtreden BLOKLU geciyor
  //    (DERMAVASC "Onarici", DERMASTRA "Elastikiyeti", DERMAMOVERA "Kas").
  //    Ajan notr altBaslik kullanir - yoksa kendi cevabi bloklanir.
  //
  // KANAL DISI (eklenmedi): VIREON, FEMISIA, INTIMBLANC, LIFTELLE,
  //    SOFTGUARD, BUGUARD. Sorulursa insana aktarilir, adi tekrarlanmaz.
  // ===================================================================

  BRIGHTSMILE: {
    ad: 'BRIGHT SMILE', altBaslik: 'Diş Macunu', fiyat: '950 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/bright-smile',
    aciklama: 'Doğal mineraller ve bitkisel özlerle formüle edilmiş, günlük ağız bakımına yönelik diş macunudur. Diş yüzeyinin temizlenmesine ve ağızda ferahlık hissi oluşmasına yardımcı olur.',
    aktifler: ['Bambu Aktif Karbon', 'Zeolit', 'Diatom Toprağı', 'Ksilitol', 'Aloe Vera', 'Nane & Çay Ağacı Yağı'],
    inci: null,
    kullanim: 'Günde en az 2 kez, bezelye tanesi kadar ürün diş fırçasına alınarak 2–3 dakika fırçalanır. Yutulmaz.',
    anahtarKelimeler: ['bright smile', 'brightsmile', 'dis macunu', 'macun'],
    gunesUrunu: false
  },

  BABYDENT: {
    ad: 'BABYDENT', altBaslik: 'Bebek ve Çocuklar İçin Diş Bakım Jeli', fiyat: '1.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/babydent',
    aciklama: 'Çocukların ilk dişlerinden itibaren günlük ağız bakım rutinine eşlik etmek üzere formüle edilmiş diş bakım jelidir. Yutulmaya uygun yapıya sahiptir, durulama gerektirmez.',
    aktifler: ['Aloe Vera', 'Hatmi Kökü Ekstresi', 'Mavi Papatya Yağı', 'Ksilitol', 'Probiyotik Kompleks'],
    inci: null,
    kullanim: 'Temiz bir bez veya yumuşak bebek diş fırçasıyla az miktarda ürün diş yüzeylerine nazikçe uygulanır. Durulama gerektirmez.',
    anahtarKelimeler: ['babydent', 'baby dent', 'bebek dis', 'cocuk dis jeli'],
    gunesUrunu: false
  },

  EASYCOMB: {
    ad: 'EASYCOMB', altBaslik: 'Bebek ve Çocuklar İçin Saç Bakım Spreyi', fiyat: '1.020 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/easycomb',
    aciklama: 'Bebek ve çocukların saç bakım rutinine eşlik etmek üzere bitki bazlı içeriklerle formüle edilmiş saç bakım spreyidir. Saçın kolay taranmasına yardımcı olur, durulama gerektirmez.',
    aktifler: ['Aloe Vera', 'Jojoba Yağı', 'Lavanta Suyu', 'Papatya Suyu', 'Avokado Yağı'],
    inci: null,
    kullanim: 'Nemli veya kuru saça, özellikle tarama öncesinde saç uçları ve boylarına uygulanır. Durulama gerektirmez.',
    anahtarKelimeler: ['easycomb', 'easy comb', 'tarama spreyi', 'sac spreyi'],
    gunesUrunu: false
  },

  BABYRESCUE: {
    ad: 'BABY RESCUE', altBaslik: 'Bakım Stick Balmı', fiyat: '900 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/baby-rescue',
    aciklama: 'Günlük cilt bakım rutinine eşlik etmek üzere formüle edilmiş, stick balm formunda bir bakım ürünüdür. Cildin nem dengesinin korunmasına ve yumuşak bir his kazanmasına yardımcı olur.',
    aktifler: ['Shea Yağı', 'Avokado Yağı', 'Hodan Yağı', 'Tamanu Yağı', 'Arnika Ekstresi', 'Balmumu'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde, ihtiyaç duyulan bölgeye günde 2–3 kez ince bir tabaka halinde uygulanır.',
    anahtarKelimeler: ['baby rescue', 'babyrescue', 'stick balm'],
    gunesUrunu: false
  },

  BABYSHOWER: {
    ad: 'BABYSHOWER', altBaslik: 'Bebek Şampuanı', fiyat: '1.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/babyshower',
    aciklama: 'Bebeklerin hassas saç derisi ve cilt yapısı dikkate alınarak geliştirilmiş, bitkisel bazlı içeriklerle formüle edilmiş çocuk şampuanıdır. Günlük kullanıma uygundur.',
    aktifler: ['Hindistan Cevizi Türevli Temizleyiciler', 'Aloe Vera', 'Papatya Hidrosolü', 'Hodan Yağı', 'Panthenol'],
    inci: null,
    kullanim: 'Islak saça ve vücuda nazikçe masaj yaparak uygulanır, köpürdükten sonra durulanır.',
    anahtarKelimeler: ['babyshower', 'baby shower', 'bebek sampuan', 'sampuan'],
    gunesUrunu: false
  },

  BABYSOFT: {
    ad: 'BABYSOFT', altBaslik: 'Bebek Vücut Losyonu', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/babysoft',
    aciklama: 'Bebeklerin hassas cilt bakım rutinine eşlik etmek üzere bitkisel yağlar ve destekleyici içeriklerle formüle edilmiş bakım losyonudur. Ciltte pürüzsüz bir his bırakılmasına yardımcı olur.',
    aktifler: ['Shea Yağı', 'Hindistan Cevizi Yağı', 'Jojoba Yağı', 'Yulaf Ekstresi', 'Seramid NP', 'Provitamin B5'],
    inci: null,
    kullanim: 'Temiz cilde günde 1–2 kez nazik masajla uygulanır. Banyo sonrası hafif nemli cilde uygulanması önerilir.',
    anahtarKelimeler: ['babysoft', 'baby soft', 'bebek losyon', 'vucut losyonu'],
    gunesUrunu: false
  },

  BABYSOL: {
    ad: 'BABYSOL', altBaslik: 'SPF 50+ Bebek Güneş Kremi',
    lockup: 'BABYSOL · SPF 50+ Bebek Güneş Koruyucu',
    fiyat: '1.250 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/babysol',
    aciklama: 'Bebeklerin hassas cilt yapısı dikkate alınarak geliştirilmiş, fiziksel filtre içeren güneş bakım ürünüdür. Non-nano çinko oksit içerir.',
    aktifler: ['Non-nano Çinko Oksit', 'Tamanu Yağı', 'Shea Yağı', 'Aloe Vera', 'Bisabolol', 'Seramid NP'],
    inci: null,
    kullanim: 'Güneşe çıkmadan 15 dakika önce temiz ve kuru cilde eşit şekilde uygulanır. Su teması, terleme veya havluyla kurulama sonrası tekrarlanır.',
    anahtarKelimeler: ['babysol', 'baby sol', 'bebek gunes'],
    gunesUrunu: true,
    dogrulamaNotu: 'SPF 50+ sahip karariyla kesinlesti (13.09.2026). Kutuda SPF degeri yazmiyor.'
  },

  MINISOOTH: {
    ad: 'MINISOOTH', altBaslik: 'Bebek Bakım Kremi', fiyat: '1.200 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/minisooth-bebek-pi%C5%9Fik-kremi',
    aciklama: 'Hassas bebek cildinin günlük bakım rutinine eşlik etmek üzere geliştirilmiş bakım kremidir. Yumuşak dokusu sayesinde kolayca yayılır, bez bölgesi bakım rutininde pratik kullanım sunar.',
    aktifler: ['Çinko Oksit', 'Mango Yağı', 'Shea Yağı', 'Panthenol', 'Yulaf Özü', 'Centella Ekstresi'],
    inci: null,
    kullanim: 'Temizlenmiş ve kurulanmış bez bölgesine ince bir tabaka halinde uygulanır. Her bez değişiminden önce düzenli olarak kullanılır.',
    anahtarKelimeler: ['minisooth', 'mini sooth', 'bez bolgesi', 'pisik'],
    gunesUrunu: false
  },

  DERMACORN: {
    ad: 'DERMACORN', altBaslik: 'Sertleşmiş Bölge Bakımı', fiyat: '900 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermacorn',
    aciklama: 'Sertleşmiş ve kalınlaşmış cilt görünümüne sahip bölgelerin bakımına yönelik bitkisel içeriklerle formüle edilmiş bakım ürünüdür. Damlalıklı başlığı pratik uygulama sağlar.',
    aktifler: ['Söğüt Kabuğu Ekstresi', 'Üre', 'Shea Esteri', 'Jojoba Yağı', 'Çay Ağacı Yağı'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde günde 1–2 kez ince bir tabaka halinde uygulanır. Masaj yapılmadan emilmesi beklenir.',
    anahtarKelimeler: ['dermacorn', 'derma corn', 'sertlesmis bolge'],
    gunesUrunu: false
  },

  DERMAVASC: {
    ad: 'DERMAVASC', altBaslik: 'Yoğun Bakım Kremi', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermavasc',
    aciklama: 'Bitkisel özler ve doğal yağlardan oluşan formülüyle günlük cilt bakım rutinine eşlik etmek üzere geliştirilmiş bakım kremidir. Ciltte ferah ve konforlu bir his bırakmayı hedefler.',
    aktifler: ['At Kestanesi Ekstresi', 'Cadı Fındığı', 'Yaban Mersini', 'Tamanu Yağı', 'Shea Yağı', 'Aloe Vera'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde ince bir tabaka hâlinde uygulanır. Günde 2–3 kez tekrarlanabilir.',
    anahtarKelimeler: ['dermavasc', 'derma vasc'],
    gunesUrunu: false,
    dogrulamaNotu: 'Sitedeki ad "Onarici Bakim Kremi" - iddia iceriyor, ajan notr altBaslik kullanir.'
  },

  DERMARNICA: {
    ad: 'DERMARNICA', altBaslik: 'Arnica Özlü Bitkisel Bakım Kremi', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermarnica',
    aciklama: 'Arnica montana ekstresi ağırlıklı bitkisel içeriklerle formüle edilmiş cilt bakım kremidir. Kolay emilen yapısı sayesinde ciltte yağlı veya ağır bir his bırakmaz.',
    aktifler: ['Arnica Ekstresi', 'Centella (Gotu Kola)', 'Kantaron Yağı', 'Hodan Yağı', 'Aynısefa Ekstresi'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde günde 2–3 kez nazikçe masaj yapılarak uygulanır. Göz çevresine uygulanmaz.',
    anahtarKelimeler: ['dermarnica', 'derma arnica', 'arnika krem'],
    gunesUrunu: false
  },

  KINESIS: {
    ad: 'KINESIS+', altBaslik: 'Sporcu Bakım Kremi', fiyat: '1.950 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/kinesis',
    aciklama: 'Spor yapanlar ve aktif yaşam süren bireylerin günlük bakım rutinine eşlik etmek üzere geliştirilmiş bakım kremidir. Masajla uygulandığında ciltte sıcaklık ve ferahlık hissi oluşmasına katkı sağlar.',
    aktifler: ['Susam Yağı', 'Avokado Yağı', 'Tamanu Yağı', 'Tarçın & Nane Yağı', 'Aloe Vera', 'Çinko & Magnezyum'],
    inci: null,
    // "spor oncesi veya sonrasi" filtrenin oncesi/sonrasi kuralina takiliyordu
    // (sonuc iddiasi sanildi). Anlam ayni, ifade degisti.
    kullanim: 'Temiz ve kuru cilde günde 2 kez 5–10 pompa alınarak dairesel hareketlerle masaj yapılır. Antrenmandan önce veya sonra kullanılabilir.',
    anahtarKelimeler: ['kinesis', 'sporcu krem', 'spor kremi'],
    gunesUrunu: false
  },

  DERMASTRA: {
    ad: 'DERMASTRA', altBaslik: 'Cilt Bakım Kremi', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermastra',
    aciklama: 'Gerilme hissine sahip cilt bölgelerinin bakım rutinine eşlik etmek üzere bitkisel yağlar ve mineral içeriklerle formüle edilmiş bakım kremidir. Hızla emilir, ciltte yağlı his bırakmaz.',
    aktifler: ['Liposomal C Vitamini', 'Ozonize Sarı Kantaron Yağı', 'Tamanu Yağı', 'Nar Çekirdeği Yağı', 'Shea Yağı'],
    inci: null,
    kullanim: 'Günde 2 kez temiz ve kuru cilde dairesel masaj hareketleriyle uygulanır.',
    anahtarKelimeler: ['dermastra', 'derma stra'],
    gunesUrunu: false,
    dogrulamaNotu: 'Sitedeki ad "Cilt Elastikiyeti Destekleyici" - iddia iceriyor, ajan notr altBaslik kullanir.'
  },

  DORSIVIA: {
    ad: 'DORSIVIA', altBaslik: 'Isınma Etkili Masaj Kremi', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dorsivia',
    aciklama: 'Bel ve sırt gibi gün içinde yoğun kullanılan bölgelerin bakım rutinine eşlik etmek üzere geliştirilmiş masaj ve bakım kremidir. Capsicum içeriği masaj sırasında sıcaklık hissi oluşturur.',
    aktifler: ['Capsicum Ekstresi', 'Kış Yeşili (Wintergreen)', 'Arnika Ekstresi', 'Tamanu Yağı', 'Sedir & Vetiver Yağı'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde günde 1–2 kez ince bir tabaka halinde uygulanır, dairesel masaj hareketleriyle yayılır.',
    anahtarKelimeler: ['dorsivia', 'masaj kremi', 'isinma kremi'],
    gunesUrunu: false
  },

  SERALIMBO: {
    ad: 'SERALIMBO', altBaslik: 'Gece Bakım Kremi', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/seralimbo',
    aciklama: 'Gün sonunda bacaklara bakım ve masaj rutinine eşlik etmek üzere geliştirilmiş gece bakım kremidir. Hafif yapısı sayesinde ciltte yağlı bir his bırakmadan kolayca emilir.',
    aktifler: ['Tamanu Yağı', 'Hodan Yağı', 'Shea Yağı', 'Arnika Ekstresi', 'Magnezyum', 'Vetiver & Nane Yağı'],
    inci: null,
    kullanim: 'Yatmadan önce temiz cilde; diz, baldır ve ayak bileği gibi bölgelere hafif masaj hareketleriyle uygulanır.',
    anahtarKelimeler: ['seralimbo', 'sera limbo', 'gece kremi', 'bacak kremi'],
    gunesUrunu: false
  },

  CALJAW: {
    ad: 'CAL JAW', altBaslik: 'Gece Çene Bakım Roll-On\'u', fiyat: '1.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/calmjaw',
    aciklama: 'Gece bakım rutinine eşlik etmek üzere bitkisel yağların dengeli bir karışımıyla formüle edilmiş roll-on bakım yağıdır. Roll-on başlığı kontrollü ve pratik uygulama sağlar.',
    aktifler: ['Hodan Yağı', 'Lavanta Yağı', 'Vetiver Yağı', 'Akgünlük (Frankincense)', 'Ylang Ylang'],
    inci: null,
    kullanim: 'Temiz ve kuru cilt üzerine ince bir tabaka halinde, roll-on başlığıyla dairesel hareketler yapılarak uygulanır. Göz çevresiyle temas ettirilmez.',
    anahtarKelimeler: ['cal jaw', 'caljaw', 'calm jaw', 'cene roll'],
    gunesUrunu: false,
    dogrulamaNotu: 'Sitede "CAL JAW", Master Matrix kanonik adi "CALM JAW", slug calmjaw. Ad birlestirilmeli.'
  },

  OPTYWAVE: {
    ad: 'OPTYWAVE', altBaslik: 'Göz Çevresi Bakım Roll-On\'u', fiyat: '1.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/optywave',
    aciklama: 'Göz çevresi bakım rutinine eşlik etmek üzere geliştirilmiş, bitkisel yağ bazlı roll-on bakım ürünüdür. Hafif dokusu sayesinde yağlı bir his bırakmaz.',
    aktifler: ['Astaksantin', 'Lutein', 'Zeaksantin', 'Hodan Yağı', 'Aynısefa Ekstresi', 'Üzüm Çekirdeği Yağı'],
    inci: null,
    kullanim: 'Günde 1–2 kez temiz göz çevresine roll-on başlıkla dairesel hareketlerle nazikçe uygulanır. Gözle doğrudan temas ettirilmez.',
    anahtarKelimeler: ['optywave', 'opty wave', 'goz cevresi'],
    gunesUrunu: false
  },

  ORAGARDE: {
    ad: 'ORAGARDE', altBaslik: 'Ağız Bakım Spreyi', fiyat: '900 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/oragarde',
    // "Alkol icermeyen" YAZILAMAZ - icermez kalibi (adillik kriteri).
    // Yasal olarak kullanilabilen bir bilesenin yoklugu reklam unsuru yapilamaz.
    aciklama: 'Bitkisel kaynaklı aromatik yağların dengeli birleşimiyle formüle edilmiş ağız bakım spreyidir. Sprey formu gün içinde pratik kullanım sunar.',
    aktifler: ['Mür Ekstresi', 'Karanfil Yağı', 'Niaouli Yağı', 'Limon Kabuğu Yağı', 'Ksilitol'],
    inci: null,
    kullanim: 'Günde 2–3 kez ağıza 2 fıs püskürtülerek uygulanır. Çalkalamaya gerek yoktur, yutulmaz. 4 yaş altı çocuklar için uygun değildir.',
    anahtarKelimeler: ['oragarde', 'ora garde', 'agiz spreyi'],
    gunesUrunu: false
  },

  HAIRNOURISHER: {
    ad: 'HAIR NOURISHER', altBaslik: 'Saç Bakım Yağı', fiyat: '1.200 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/hair-nouriher',
    aciklama: 'Saç derisi bakım rutinine eşlik etmek üzere bitkisel yağlar, vitaminler ve bitki özlerinden oluşan bakım yağıdır. Durulama gerektirmez.',
    aktifler: ['Hindistan Cevizi Yağı', 'Jojoba Yağı', 'Kenevir Tohumu Yağı', 'Centella Asiatica', 'Nane & Selvi Yağı'],
    inci: null,
    kullanim: 'Temiz saç derisine günde 1–2 kez 4–5 damla bölgesel olarak uygulanır, parmak uçlarıyla nazik masajla yayılır. Durulama gerektirmez.',
    anahtarKelimeler: ['hair nourisher', 'hairnourisher', 'sac yagi', 'sac bakim yagi'],
    gunesUrunu: false
  },

  LIPVORA: {
    ad: 'LIPVORA', altBaslik: 'Dudak Nemlendirici Balm', fiyat: '900 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/lipvora',
    aciklama: 'Bitkisel yağlar ve doğal balmumlarıyla zenginleştirilmiş dudak balmıdır. Dudaklarda yumuşak, parlak ve bakımlı bir görünüm elde edilmesine yardımcı olur.',
    aktifler: ['Jojoba Yağı', 'Shea Yağı', 'Hodan Yağı', 'Arı Mumu', 'Candelilla Mumu', 'E Vitamini'],
    inci: null,
    kullanim: 'Temiz dudaklara ihtiyaç duyuldukça uygulanır. Makyaj altına baz olarak veya tek başına kullanılabilir.',
    anahtarKelimeler: ['lipvora', 'lip vora', 'dudak balm', 'dudak nemlendirici'],
    gunesUrunu: false
  },

  DERMAGUARD: {
    ad: 'DERMAGUARD', altBaslik: 'Ayak ve Tırnak Bakım Kremi', fiyat: '1.200 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermaguard',
    aciklama: 'Bitkisel yağlar ve doğal özlerle zenginleştirilmiş formülüyle ayak ve cilt bakımına yönelik geliştirilmiştir. Ayak bakım rutininde hijyenik dengeye katkı sağlar.',
    aktifler: ['Çay Ağacı Yağı', 'Kekik Yağı', 'Mersin Yağı', 'Shea Yağı', 'Tatlı Badem Yağı', 'Çörek Otu Yağı'],
    inci: null,
    kullanim: 'Günde 2 kez temiz ve kuru cilde masaj yapılarak uygulanır.',
    anahtarKelimeler: ['dermaguard', 'derma guard', 'ayak kremi', 'tirnak bakim'],
    gunesUrunu: false
  },

  DERMAMOVERA: {
    ad: 'DERMAMOVERA', altBaslik: 'Masaj ve Bakım Kremi', fiyat: '1.950 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermamovera',
    aciklama: 'Bitkisel içerikli bakım kremidir. Masajla uygulandığında ciltte ısınma, ferahlık ve konfor hissi sağlar.',
    aktifler: ['Tamanu Yağı', 'Arnika Ekstresi', 'Zencefil & Zerdeçal Yağı', 'Mür Yağı', 'Shea Yağı', 'Aloe Vera'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde günde 2–3 kez ince bir tabaka halinde uygulanır; diz, dirsek, omuz, bel ve bilek bölgelerine nazikçe masaj yapılır.',
    anahtarKelimeler: ['dermamovera', 'derma movera'],
    gunesUrunu: false,
    dogrulamaNotu: 'Sitedeki ad "Kas ve Eklem Bakim Kremi" - iddia iceriyor, ajan notr altBaslik kullanir.'
  },

  DERMABED: {
    ad: 'DERMABED', altBaslik: 'Bariyer ve Koruyucu Bakım Kremi', fiyat: '1.950 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermabed',
    aciklama: 'Uzun süreli yatış, sürtünme veya basınca bağlı olarak hassaslaşan cilt bölgeleri için geliştirilmiş bitkisel içerikli bariyer bakım kremidir. Cilt bütünlüğü korunmuş alanlarda kullanılır.',
    aktifler: ['Tamanu Yağı', 'Ozonize Sarı Kantaron', 'Aynısefa Ekstresi', 'Shea Yağı', 'Hodan Yağı', 'Aloe Vera'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde ince bir tabaka hâlinde uygulanır; sırt, kalça, topuk, dirsek ve diz arkası gibi bölgelere günde 2–3 kez nazikçe masaj yapılır.',
    anahtarKelimeler: ['dermabed', 'derma bed', 'bariyer krem'],
    gunesUrunu: false
  },

  DERMANOVA: {
    ad: 'DERMANOVA', altBaslik: 'İz Görünümü Bakım Kremi', fiyat: '2.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/dermanova',
    aciklama: 'Bitkisel yağlar ve doğal ekstrelerle zenginleştirilmiş formülüyle cilt bariyerinin korunmasını destekler ve iz görünümünün azalmasına yardımcı olur.',
    aktifler: ['Tamanu Yağı', 'Ozonize Kantaron', 'Aynısefa Ekstresi', 'Hodan Yağı', 'Shea Yağı', 'Palmarosa Yağı'],
    inci: null,
    kullanim: 'Temiz ve kuru cilde ince bir tabaka halinde uygulanır, nazikçe masaj yapılarak yedirilir. Gün içinde ihtiyaç duydukça tekrarlanabilir.',
    anahtarKelimeler: ['dermanova', 'derma nova', 'iz krem'],
    gunesUrunu: false
  },

  MENTHALIS: {
    ad: 'MENTHALIS', altBaslik: 'Canlandırıcı Bitki Yağları Roll-On', fiyat: '1.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/menthalis',
    // 🔴 LAVANTA CIKARILDI (14.09.2026). Kutu formul tablosu KAPALI ve
    //    icinde lavanta YOK: Tatli Badem %60 · Peppermint %10 · Bergamot %8 ·
    //    Ylang Ylang %6 · Servi %5 · Niaouli %5 · Palmarosa %4 · E Vit %2 = %100.
    //    INCI'de olmayan bir bileseni saymak belgesiz icerik beyanidir.
    //    Ayni hata sitede de vardi, orada da duzeltildi.
    aciklama: 'Nane, bergamot, niaouli, ylang ylang, servi ve palmarosa bitki yağlarının dengeli birleşimiyle geliştirilen ferahlatıcı bakım roll-onudur. Cilde uygulandığında serinletici ve tazeleyici bir his sağlar.',
    aktifler: ['Tatlı Badem Yağı', 'Nane Yağı', 'Bergamot Yağı', 'Ylang Ylang Yağı', 'Servi Yağı', 'Niaouli Yağı', 'Palmarosa Yağı', 'E Vitamini'],
    inci: null,
    kullanim: 'Yüz bölgesine ince bir tabaka hâlinde uygulanır. Gün içinde ihtiyaç duyuldukça tekrarlanabilir. Fototoksik bileşen içerdiğinden uygulama sonrası doğrudan güneş ışığından kaçınılır.',
    anahtarKelimeler: ['menthalis', 'mentalis', 'nane roll'],
    gunesUrunu: false,
    dogrulamaNotu: 'Sitede INCI listesi HIC YOK - icerik beyani zorunlu, eklenmeli.'
  },

  CALMORIS: {
    ad: 'CALMORIS', altBaslik: 'Rahatlatıcı Bakım Roll-On', fiyat: '1.100 TL', hacim: null,
    urunSayfasi: 'https://www.lcarlie.shop/product-page/calmoris',
    aciklama: 'Lavanta, bergamot, ylang ylang, günlük, vetiver ve paçuli yağlarının dengeli birleşiminden oluşan bitkisel içerikli roll-on bakım ürünüdür. Uygulandığı bölgede ferahlık ve tazelenme hissi sunar.',
    aktifler: ['Lavanta Yağı', 'Bergamot Yağı', 'Ylang Ylang', 'Vetiver Yağı', 'Tatlı Badem Yağı', 'E Vitamini'],
    inci: null,
    kullanim: 'Şakaklara, alına, enseye, bileklere veya burun altına ince bir tabaka halinde uygulanır. Fototoksik bileşen içerdiğinden uygulama sonrası doğrudan güneş ışığından kaçınılır.',
    anahtarKelimeler: ['calmoris', 'calm oris', 'rahatlatici roll'],
    gunesUrunu: false
  }
};

// 🔴 GUNES KORUYUCU ZORUNLU IBARE SETI - 03_MEVZUAT §5
// Gunes koruyucu iceriklerinin TAMAMINDA gecer. Kisaltilamaz.
const GUNES_ZORUNLU =
  'Yeterli miktarda uygulanmaması korumayı önemli ölçüde düşürür. ' +
  'Aşırı güneş maruziyeti sağlık tehdididir. ' +
  'Bebek ve küçük çocuklar doğrudan güneşe maruz bırakılmamalıdır. ' +
  'Hiçbir ürün %100 koruma sağlamaz.';

// ---------------------------------------------------------------------
// UCLU RITUEL - capraz satis
// Sitede tanimli: LUCIDERM (temizle) -> HYDRAVIE (nemlendir) -> SUNACNEA (koru)
// Uc urunu tek adimda sepete hazirlayan Wix checkout template linki.
//
// 🔴 Bu cumlede SUNACNEA veya "SPF" BILEREK ANILMIYOR. Gunes urunu adi gecerse
// mevzuat zorunlu ibare setini de eklemek gerekir ve cevap okunamaz uzunluga
// cikar. Adim isimleri yeterli; urunler paketin sayfasinda zaten gorunuyor.
// ---------------------------------------------------------------------
const RITUEL_LINK = 'https://www.wixapis.com/ecom/v1/checkout-templates/' +
  'd0ace880-ac41-4cc1-ae31-1cd6a275fe0f/create-and-redirect-to-checkout' +
  '?siteId=20b24639-9d03-4307-8b5d-2a525af26151';

// CALMAROS paketin PARCASI DEGIL (sitede "esnek/ek bakim adimi" diye geciyor)
// ama onu soran musteriye de uclu paket teklif edilir - ust satis firsati.
const RITUEL_URUNLERI = ['LUCIDERM', 'HYDRAVIE', 'SUNACNEA', 'CALMAROS'];

const RITUEL_CUMLESI =
  ' Üç adımlı günlük bakım rutinimizi (temizle · nemlendir · koru) ' +
  'tek seferde almak için: ' + RITUEL_LINK;

// =====================================================================
// KATEGORILER - "ayak bakimi icin urun" gibi NIYET beyanlarini karsilar
//
// 13.09.2026 oncesi bu sorular ANLASILMADI'ya dusup genel site linki
// aliyordu. Musteri ihtiyacini SOYLEMIS olmasina ragmen urun gormuyordu -
// dogrudan satis kaybi. "sac bakimi icin ne var" ise BELIRTI_ANLATIMI
// sanilip INSANA AKTARILIYORDU.
//
// Sadece ajanin sattigi 30 urun listelenir; kanal disi ve onay bekleyen
// urunler burada YOKTUR.
// =====================================================================
const KATEGORILER = [
  { ad: 'ayak ve tırnak bakımı',
    anahtar: ['ayak', 'topuk', 'tirnak', 'ayak bakimi', 'nasir', 'sertlesmis'],
    urunler: ['DERMAGUARD', 'DERMACORN'] },

  { ad: 'bebek ve çocuk bakımı',
    anahtar: ['bebek', 'bebegim', 'cocuk', 'cocugum', 'bebe', 'yenidogan', 'bebek urun'],
    urunler: ['BABYSHOWER', 'BABYSOFT', 'MINISOOTH', 'BABYSOL', 'BABYDENT', 'EASYCOMB', 'BABYRESCUE'] },

  { ad: 'ağız ve diş bakımı',
    anahtar: ['agiz', 'dis', 'disler', 'agiz bakimi', 'dis bakimi', 'macun', 'nefes'],
    urunler: ['BRIGHTSMILE', 'ORAGARDE', 'BABYDENT'] },

  { ad: 'saç bakımı',
    anahtar: ['sac', 'sac bakimi', 'sac derisi', 'tarama'],
    urunler: ['HAIRNOURISHER', 'EASYCOMB'] },

  { ad: 'yüz bakımı',
    anahtar: ['yuz', 'yuz bakimi', 'cilt bakimi', 'gunluk bakim', 'rutin'],
    urunler: ['LUCIDERM', 'HYDRAVIE', 'SUNACNEA', 'CALMAROS'] },

  { ad: 'güneş koruma',
    anahtar: ['gunes', 'gunes kremi', 'spf', 'plaj', 'deniz'],
    urunler: ['SUNACNEA', 'BABYSOL'] },

  { ad: 'masaj ve spor sonrası bakım',
    anahtar: ['masaj', 'spor', 'antrenman', 'egzersiz', 'sporcu', 'bacak bakimi'],
    urunler: ['KINESIS', 'DORSIVIA', 'DERMAMOVERA', 'SERALIMBO', 'DERMARNICA'] },

  { ad: 'ferahlatıcı roll-on',
    anahtar: ['roll on', 'rollon', 'roll-on', 'ferahlik', 'ferahlatici'],
    urunler: ['MENTHALIS', 'CALMORIS', 'CALJAW'] },

  { ad: 'dudak bakımı',
    anahtar: ['dudak', 'balm', 'lip'],
    urunler: ['LIPVORA'] },

  { ad: 'göz çevresi bakımı',
    anahtar: ['goz cevresi', 'goz alti', 'ekran'],
    urunler: ['OPTYWAVE'] },

  { ad: 'iz ve bariyer bakımı',
    // 🔴 Tek basina 'iz' YAZILMAZ: eslesirMi kelime BASINDAN eslestigi icin
    // "IZIN verir misiniz" bu kategoriye dusuyordu (yanlis pozitif).
    anahtar: ['iz gorunumu', 'izlerim', 'iz icin', 'catlak izi', 'bariyer', 'yatalak'],
    urunler: ['DERMANOVA', 'DERMABED', 'DERMAVASC'] }
];

// En uygun fiyatli giris urunleri - fiyat itirazinda kullanilir.
// Indirim/kampanya UYDURULMAZ; sadece var olan en uygun secenek gosterilir.
const GIRIS_URUNLERI = ['LIPVORA', 'DERMACORN', 'ORAGARDE', 'BABYRESCUE', 'BRIGHTSMILE'];

// ---------------------------------------------------------------------
// Mesajda hangi kategori anildi?  (urun adi gecmiyorsa kullanilir)
// ---------------------------------------------------------------------
function kategoriTani(mesaj, asciiyeFn, eslesirFn) {
  const m = asciiyeFn(mesaj);
  let enIyi = null, enUzun = 0;
  for (const k of KATEGORILER) {
    for (const a of k.anahtar) {
      const t = asciiyeFn(a);
      const varMi = eslesirFn ? eslesirFn(m, a) : m.includes(t);
      // En UZUN eslesme kazanir: "goz cevresi" > "goz"
      if (varMi && t.length > enUzun) { enIyi = k; enUzun = t.length; }
    }
  }
  return enIyi;
}

// ---------------------------------------------------------------------
// Kategori cevabi: urunleri fiyatiyla ve kendi linkiyle sirala.
// Soru sormaz, CTA ile biter.
// ---------------------------------------------------------------------
function kategoriCevabi(kat, site) {
  if (!kat) return null;
  const satirlar = [];
  let gunesVar = false;
  for (const kod of kat.urunler) {
    const u = URUNLER[kod];
    if (!u) continue;
    if (u.gunesUrunu) gunesVar = true;
    const baslik = u.lockup || (u.ad + ' ' + u.altBaslik);
    const hacim = u.hacim ? ` (${u.hacim})` : '';
    satirlar.push(`• ${baslik}${hacim} · ${u.fiyat}\n  ${u.urunSayfasi || site}`);
  }
  if (!satirlar.length) return null;

  const gunesEk = gunesVar ? '\n' + GUNES_ZORUNLU : '';
  return `${basHarf(kat.ad)} için ürünlerimiz:\n${satirlar.join('\n')}${gunesEk}\n` +
         `Tüm ürünleri incelemek için: ${site}`;
}

// =====================================================================
// SATISTA AMA AJANIN ANLATMADIGI URUNLER
//
// 🔴 Bu urunler sitede SATISTA. Musteri iki tikla satin alabiliyor.
// Ajanin onlari ANLATMAMA karari duruyor (02_URUN_GERCEGI: WhatsApp/
// Instagram katalogu, "risk mavi tikli hesabin kendisi"), ama satista
// olan bir urun sorulunca "ekip arkadasimiz donecek" demek MUSTERI
// GOZUNDE SACMA - urun zaten sitede, tek tikla alinabiliyor.
//
// Cozum: urun ANLATILMAZ (aciklama, icerik, iddia YOK) ama kendi
// sayfasinin linki verilir. Musteri tikayabilsin diye. Ajan hicbir
// iddiada bulunmadigi icin anlatmama karari ihlal edilmiyor.
//
// AUROLIS / NOMORE / EARCLIA buraya GIRMEZ - onlar satista degil,
// bakanlik onayi bekliyor. Onlarda eskalasyon dogru davranis.
// =====================================================================
// 🔴 'tamYol' verilirse o kullanilir. VIREON'un ASIL satis sayfasi
//    /vireon; /product-page/vireon-for-men DEGIL. Reklamlar /vireon'a
//    yonleniyor ve o sayfa ozel kodlanmis (kademeli fiyat kartlari, SSS).
//    Musteriyi yanlis sayfaya gondermek satis kaybi olurdu.
const SATISTA_ANLATILMAYAN = {
  'softguard':  { ad: 'SOFTGUARD',  slug: 'softguard' },
  'buguard':    { ad: 'BUGUARD',    slug: 'buguard' },
  'bugguard':   { ad: 'BUGUARD',    slug: 'buguard' },
  'intimblanc': { ad: 'INTIMBLANC', slug: 'intimblanc' },
  'liftelle':   { ad: 'LIFTELLE',   slug: 'liftelle' },
  'vireon':     { ad: 'VIREON',     tamYol: 'https://www.lcarlie.shop/vireon' },
  'femisia':    { ad: 'FEMISIA',    slug: 'femisia-for-women' }
};

// Filtrenin yakaladigi ifadeye gore satistaki urunu bul
function satistaAnlatilmayan(ifadeler) {
  for (const i of (ifadeler || [])) {
    const k = String(i).toLocaleLowerCase('tr-TR');
    if (SATISTA_ANLATILMAYAN[k]) return SATISTA_ANLATILMAYAN[k];
  }
  return null;
}

// Urun ANLATILMAZ - sadece sayfasina yonlendirilir.
function satisLinkiCevabi(u, site) {
  if (!u) return null;
  const yol = u.tamYol || ('https://www.lcarlie.shop/product-page/' + u.slug);
  return `${u.ad} ürününün tüm bilgileri ve siparişi ürün sayfamızda yer alıyor: ` +
         `${yol}\n` +
         `Diğer sorularınız için ekip arkadaşımız da en kısa sürede dönüş yapacak.`;
}

// ---------------------------------------------------------------------
// KATEGORI LISTESI - "hangi kategoriler var", "ne satiyorsunuz"
//
// 🔴 "▸ " ile baslayan satirlar HIZLI CEVAP secenegidir.
// Web widget'i bunlari BUTON olarak cizer; WhatsApp gibi buton cizemeyen
// kanallarda duz metin olarak okunur ve yine anlasilir. Tek cevap,
// iki kanal. Ajanin metni kanala gore degismez.
// ---------------------------------------------------------------------
// Kategori adlari kucuk harfle tanimli (cumle icinde dogru duruyor);
// liste ve baslik olarak gosterilirken bas harfi buyutulur.
const basHarf = (s) => String(s).charAt(0).toLocaleUpperCase('tr-TR') + String(s).slice(1);

function kategoriListesi(site) {
  const satirlar = KATEGORILER.map(k => '▸ ' + basHarf(k.ad));
  return 'Hangi alanda yardımcı olabiliriz?\n' + satirlar.join('\n') +
         '\nTüm ürünleri incelemek için: ' + site;
}

// ---------------------------------------------------------------------
// FIYAT ITIRAZI CEVABI
//
// 🔴 SAHTE INDIRIM, SAHTE ACILIYET, "en uygun fiyat" IDDIASI YOK.
// Uydurulmus kampanya hem mevzuata hem musteriye karsi yanlis olur.
// Yapilan tek sey: katalogdaki GERCEKTEN en uygun secenekleri gostermek
// ve uc adimli paketi hatirlatmak. Bu durust ve ise yarar.
// ---------------------------------------------------------------------
function fiyatItiraziCevabi(site) {
  const secenekler = GIRIS_URUNLERI
    .map(k => URUNLER[k])
    .filter(Boolean)
    .map(u => `• ${u.ad} ${u.altBaslik} · ${u.fiyat}\n  ${u.urunSayfasi || site}`);

  if (!secenekler.length) return null;

  return 'Bütçenize uygun bir başlangıç arıyorsanız katalogdaki en uygun ' +
         'fiyatlı ürünlerimiz şunlar:\n' + secenekler.slice(0, 3).join('\n') +
         '\nGüncel fiyatların tamamı ürün sayfalarımızda yer alıyor: ' + site +
         RITUEL_CUMLESI;
}

// ---------------------------------------------------------------------
// CAPRAZ SATIS - "X aldim, yanina ne alayim"
// Ayni kategorideki DIGER urunleri onerir.
// ---------------------------------------------------------------------
function caprazSatis(kod, site) {
  if (!kod || !URUNLER[kod]) return null;
  const kat = KATEGORILER.find(k => k.urunler.includes(kod));
  if (!kat) return null;

  const digerleri = kat.urunler
    .filter(k => k !== kod)
    .map(k => URUNLER[k])
    .filter(Boolean)
    .slice(0, 3);

  if (!digerleri.length) return null;

  const u = URUNLER[kod];
  const baslik = u.lockup || (u.ad + ' ' + u.altBaslik);
  // 🔴 CIPA URUNUN KENDISI de sayilir. Once sadece onerilen urunlere
  // bakiyordum; "SUNACNEA ile birlikte..." diye baslayan cevapta zorunlu
  // gunes ibareleri EKSIK kaliyordu. Filtre yakaladi.
  const gunesVar = u.gunesUrunu || digerleri.some(d => d.gunesUrunu);
  const satirlar = digerleri.map(d => {
    const b = d.lockup || (d.ad + ' ' + d.altBaslik);
    return `• ${b} · ${d.fiyat}\n  ${d.urunSayfasi || site}`;
  });

  return `${baslik} ile birlikte ${kat.ad} rutinini tamamlayan ürünlerimiz:\n` +
         satirlar.join('\n') +
         (gunesVar ? '\n' + GUNES_ZORUNLU : '') +
         `\nTüm ürünler: ${site}`;
}

// ---------------------------------------------------------------------
// Mesajda hangi urun anildi?
// ---------------------------------------------------------------------
// 🔴 EN UZUN ESLESME KAZANIR - ilk eslesme DEGIL.
//
// Onceki hali `for ... return kod` ile ILK eslesmeyi donduruyordu ve
// nesne sirasi yuzunden YANLIS URUN + YANLIS FIYAT veriyordu:
//   "agiz spreyi kac para"  -> CALMAROS 1.850 TL   (dogrusu ORAGARDE 900 TL)
//   "cocuk sac spreyi"      -> CALMAROS            (dogrusu EASYCOMB 1.020 TL)
//   "dudak balmi ne kadar"  -> BABY RESCUE         (dogrusu LIPVORA)
// Sebebi 'sprey' ve 'balm' gibi TEK BASINA cok genel anahtarlardi.
// O anahtarlar kaldirildi; ayrica en uzun eslesme secilerek
// "agiz bakim spreyi" gibi ifadelerde dogru urun kazaniyor.
function urunTani(mesaj, asciiyeFn) {
  const m = asciiyeFn(mesaj);
  let enIyi = null, enUzun = 0;
  for (const [kod, u] of Object.entries(URUNLER)) {
    for (const k of u.anahtarKelimeler) {
      const t = asciiyeFn(k);
      if (t.length > enUzun && m.includes(t)) { enIyi = kod; enUzun = t.length; }
    }
  }
  return enIyi;
}

// ---------------------------------------------------------------------
// Urune ozel cevap uret. Bulamazsa null doner (genel sablon kullanilir).
// Her cevap CTA ile biter, soru sormaz.
// ---------------------------------------------------------------------
function urunCevabi(kod, sinif, site, tamListeIstendi) {
  const u = URUNLER[kod];
  if (!u) return null;
  const baslik = u.lockup || (u.ad + ' ' + u.altBaslik);
  // CTA dogrudan URUN SAYFASINA gider - ana sayfaya degil.
  // Musteri aradigi urunu tekrar bulmak zorunda kalmaz.
  const kuyruk = ` Hemen sipariş vermek için: ${u.urunSayfasi || site}`;
  const gunesEk = u.gunesUrunu ? ' ' + GUNES_ZORUNLU : '';

  // Satin alma niyeti olan siniflarda uclu rituel de teklif edilir.
  // Once sorulan urunun kendi linki (birincil), sonra paket (ust satis).
  const rituelEk = RITUEL_URUNLERI.includes(kod) ? RITUEL_CUMLESI : '';

  switch (sinif) {
    case 'FIYAT': {
      const hacim = u.hacim ? ` (${u.hacim})` : '';
      return `${baslik}${hacim} fiyatı ${u.fiyat}.${gunesEk}${kuyruk}${rituelEk}`;
    }
    case 'ICERIK': {
      // 🔴 TAM INCI LISTESI ARTIK VARSAYILAN DEGIL (27.09.2026 sahip karari).
      //    Liste 20-30 maddelik bir duvar; mesajda okunmaz ve karsidaki
      //    "bunu bir bot yazdi" der. Yasal metnin tamami zaten kutuda ve
      //    urun sayfasinda duruyor.
      //
      // 🔴 AMA TAMAMEN KALDIRILMADI. Onceki hali onu BILEREK koymustu:
      //    "eksik INCI listesi hassasiyeti olan musteri icin risk". Alerjisi
      //    olan musteri listeyi kanalda gormeli, sayfaya gitmek zorunda
      //    kalmamali. Bu yuzden iki kip var:
      //      - genel soru        -> one cikanlar + sayfaya yonlendirme
      //      - alerjen sorusu    -> TAM INCI (tamListeIstendi = true)
      //    Karari cagiran verir; bu fonksiyon mesaji gormez.
      //
      // 🔴 ONE CIKANLAR UYDURULMAZ: 'aktifler' urun tabaninda elle girilmis
      //    alandir. Yoksa one cikan SOYLENMEZ.
      const aktifler = Array.isArray(u.aktifler) ? u.aktifler.filter(Boolean) : [];
      if (tamListeIstendi && u.inci) {
        return `${baslik} tam içerik listesi (INCI): ${u.inci}${gunesEk}${kuyruk}`;
      }
      const onec = aktifler.length
        ? `${baslik} öne çıkan içerikleri: ${aktifler.join(', ')}.`
        : `${baslik} içerik bilgisi ürün sayfasında yer alıyor.`;
      // INCI'yi tasimayan urunde de ayni yonlendirme: liste kutuda ve
      // sayfada yasal olarak zaten var, uydurulmaz.
      return `${onec} Tam içerik listesini (INCI) ürün sayfasında bulabilirsiniz.` +
             `${gunesEk}${kuyruk}`;
    }
    case 'KULLANIM':
      return `${baslik} — ${u.kullanim}${gunesEk}${kuyruk}`;
    case 'SIPARIS':
      return `${baslik} için siparişinizi doğrudan sitemizden verebilirsiniz.${gunesEk}${kuyruk}${rituelEk}`;

    // 🔴 13.09.2026 - "X nedir", "X ne ise yarar", "X hakkinda bilgi" gibi
    // sorular ANLASILMADI/MARKA/ONERI siniflarina dusuyor ve musteri urunun
    // adini yazmis olmasina ragmen GENEL siteye yonlendirme aliyordu.
    // 30 urunlu katalogda bu dogrudan satis kaybi.
    // Urun tanindiysa taniticiyi ver: ne oldugu + fiyat + kendi sayfasi.
    case 'ANLASILMADI':
    case 'MARKA':
    case 'ONERI': {
      const hacim = u.hacim ? ` (${u.hacim})` : '';
      return `${baslik}${hacim} — ${u.aciklama} Fiyatı ${u.fiyat}.${gunesEk}${kuyruk}${rituelEk}`;
    }

    default:
      return null;
  }
}

// n8n'de bu dosya akis-motoru ile ayni Code node'una gomulur (require yok).
// Node testinde ayri modul olarak yuklenir.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { URUNLER, GUNES_ZORUNLU, RITUEL_LINK, RITUEL_CUMLESI,
                     KATEGORILER, GIRIS_URUNLERI, kategoriTani, kategoriCevabi,
                     fiyatItiraziCevabi, caprazSatis, kategoriListesi,
                     SATISTA_ANLATILMAYAN, satistaAnlatilmayan, satisLinkiCevabi,
                     urunTani, urunCevabi };
}
