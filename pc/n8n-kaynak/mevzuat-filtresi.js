// =====================================================================
// L'CARLIE - MEVZUAT FILTRESI
// Kaynak: 03_MEVZUAT_KURALLARI.md + 02_URUN_GERCEGI.md (06.09.2026)
//
// Musteriye gonderilecek HER metin once buradan gecer.
// Cikti: TEMIZ / INCELE / BLOKLU  + etiket (A/B/C/D) + bulgular
// =====================================================================

function mevzuatFiltresi(metin, baglam) {
  baglam = baglam || {};
  const bulgular = [];

  // --- Turkce duyarli normalizasyon ---
  // Hem Turkce karakterli hem ASCII yazimi yakalar ("dolasim" = "dolaşım")
  const küçült = (s) => s.toLocaleLowerCase('tr-TR');
  const asciiye = (s) => {
    let t = küçült(s)
      .replace(/ı/g, 'i').replace(/İ/g, 'i').replace(/i̇/g, 'i')
      .replace(/ş/g, 's').replace(/ğ/g, 'g').replace(/ç/g, 'c')
      .replace(/ö/g, 'o').replace(/ü/g, 'u');
    // 🔴 Kacinma karsiti normalizasyon - kirmizi takim testinde bulundu.
    // "egz4ma", "e.g.z.a.m.a", "v i r e o n" filtreyi asiyordu.
    // 🔴 SADECE harfe bitisik ve rakama bitisik OLMAYAN rakamlar cevrilir.
    // Yoksa "SPF 30" -> "spf eo" olur, lockup ve SPF kontrolleri kirilir.
    const LEET = { '4':'a', '0':'o', '1':'i', '3':'e', '5':'s', '@':'a', '$':'s' };
    t = t.replace(/[40135@$]/g, (ch, i, tam) => {
      const o = tam[i - 1] || '', sn = tam[i + 1] || '';
      return (/[a-z]/.test(o) || /[a-z]/.test(sn)) && !(/[0-9]/.test(o) || /[0-9]/.test(sn))
        ? LEET[ch] : ch;
    });
    t = t.replace(/\b(?:[a-z][\s._\-*]+){2,}[a-z]\b/g, m => m.replace(/[\s._\-*]+/g, ''));
    return t;
  };

  const ham = String(metin || '');
  const n1 = küçült(ham);
  const n2 = asciiye(ham);

  // --- Eslesme kurali ---
  // Cok kelimeli ifadeler: dogrudan icerik aramasi.
  // Tek kelimeler: KELIME BASINDAN eslesir, Turkce ekleri kabul eder
  //   ("akne" -> "akneli" yakalanir), ama kelime ICINDE eslesmez
  //   ("odem" -> "odeme" YAKALANMAZ; asagidaki istisna listesi bunu garanti eder).
  // Bu ONEKLERLE baslayan kelimeler eslesme sayilmaz (yanlis pozitif onleme).
  // Ornek: "odem" kokü, "odeme..." ile baslayan her kelimede (odeme, odemeniz,
  // odemenizi, odemesi) yok sayilir - cunku o kelime "odeme" (para), "odem" degildir.
  const İSTİSNA = {
    'odem'  : ['odeme'],                                  // odeme/odemeniz/odemenizi...
    // 'yaras' EKLENMEZ: "YARASI" (yatak yarasi) gercek bir lezyon ifadesi.
  // 'yaray' EKLENIR: "ise YARAYAN urun", "size YARAYACAK" bloklaniyordu.
  'yara'  : ['yarar', 'yarat', 'yarasa', 'yaray'],      // yararli, yaratici, yarayan
    'kas'   : ['kasim', 'kasa', 'kastet', 'kasiyer', 'kasik', 'kase'],     // kaslar HARIC TUTULMAZ (gercek eslesme)
    'sinir' : ['sinirli', 'sinirsiz', 'sinirlam', 'sinirlandir'], // "sinir" = limit
    'maca'  : ['macar'],
    'agri'  : ['agrikultur'],
    // "aft" agiz yarasi demek; ama Ingilizce metinde "after" gecince yakalaniyordu
    'aft'   : ['after', 'aftershave'],
  };

  const gecer = (terim) => {
    const t2 = asciiye(terim);
    // Cok kelimeli ifade -> dogrudan arama
    if (/\s/.test(t2)) return n1.includes(küçült(terim)) || n2.includes(t2);

    // Tek kelime -> kelime basindan eslesme + ek kabulu
    const re = new RegExp('(^|[^a-z0-9])(' + t2.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[a-z]*)', 'g');
    let m;
    while ((m = re.exec(n2)) !== null) {
      const tamKelime = m[2];
      const haric = İSTİSNA[t2];
      if (haric && haric.some(onek => tamKelime.startsWith(onek))) continue; // yanlis pozitif, atla
      return true;
    }
    return false;
  };

  // --- KONTRENDIKASYON / UYARI CUMLESI TESPITI ---
  // "Acik yaralara uygulanmaz" bir IDDIA DEGILDIR - zorunlu guvenlik uyarisidir.
  // Bunu bloklamak ureticiye yasal uyarisini sildirmek olur; tam tersi zarar.
  // Bu yuzden hastalik/lezyon adi SADECE olumsuz kullanim kalibi icinde geciyorsa
  // bulgu uretilmez. Kalip yoksa (ornegin "yara kapatma") normal sekilde bloklanir.
  // NOT: Turkcede uyari hem "-maz/-may" hem "-mamali/-memeli" bicimiyle kurulur.
  // Ikisini de kapsamazsan "uygulanmamalidir" kacar ve zorunlu uyari silinmeye gider.
  const UYARI_KALIBI = new RegExp(
    'uygulanmaz|uygulamay|uygulanmamali|kullanilmaz|kullanmay|kullanilmamali|' +
    'surulmez|surmey|surulmemeli|temas ettirmey|temas etmemeli|dokundurmay|' +
    'maruz birakmay|birakilmamali|uzak tutun|kacinin|kacinilmali|' +
    'tavsiye edilmez|onerilmez|yutulmaz|yutmay|verilmemeli|verilmez'
  );
  const uyariCumlesi = UYARI_KALIBI.test(n2);

  const tara = (liste, tur, sonuc, gerekce, dayanak) => {
    for (const terim of liste) {
      if (gecer(terim)) {
        // Uyari cumlesindeki hastalik/lezyon adi iddia sayilmaz
        if (uyariCumlesi && tur === 'hastalik-adi') {
          bulgular.push({
            tur: 'uyari-cumlesi', ifade: terim, sonuc: 'TEMIZ',
            gerekce: 'Kontrendikasyon/uyari cumlesi - iddia degil, silinmemeli',
            dayanak: 'Kozmetik Urunler Yonetmeligi (zorunlu uyari)'
          });
          continue;
        }
        bulgular.push({ tur, ifade: terim, sonuc, gerekce, dayanak });
      }
    }
  };

  // ------------------------------------------------------------------
  // 1. HASTALIK / SEMPTOM ADLARI  -> BLOKLU
  //    03_MEVZUAT §7 sert liste + §2 genel yasak
  // ------------------------------------------------------------------
  tara([
    'egzama', 'sedef', 'akne', 'sivilce', 'mantar', 'iltihap', 'dermatit',
    'hemoroid', 'varis', 'kanser', 'roza', 'rosacea', 'bruksizm', 'vertigo',
    'migren', 'panik atak', 'anksiyete', 'basi ulseri', 'yatak yarasi',
    'huzursuz bacak', 'kireclenme', 'aft', 'dis curugu', 'dis eti cekilmesi',
    'nasir', 'catlak izi', 'bagimlilik', 'sinuzit', 'horlama', 'iktidar',
    'sertlesme', 'kramp', 'odem', 'morarma', 'kepek', 'dokulme', 'sac dokulmesi',
    // 13.09.2026 - kutu metni taramasinda kacirildigi gorulen hastalik/lezyon adlari
    'yara', 'enfeksiyon', 'apse', 'ulser', 'kasinti', 'yanik', 'uyuz', 'sigil',
    // 🔴 14.09.2026 - 'egzema' YAZIMI HIC YAKALANMIYORDU (sadece 'egzama' vardi).
    // Musteriler iki yazimi da kullaniyor.
    'egzema', 'ucuk', 'urtiker', 'kurdesen', 'atopik', 'pamukcuk',
    'alopesi', 'vitiligo', 'selulit', 'pisik'
  ], 'hastalik-adi', 'BLOKLU',
     'Hastalik veya semptom adi kozmetik urune tedavi rolu yukler',
     'Saglik Beyani Yonetmeligi m.9/(3)');

  // ------------------------------------------------------------------
  // 2. TEDAVI / SONUC FIILLERI  -> BLOKLU
  // ------------------------------------------------------------------
  tara([
    'tedavi eder', 'tedavi edici', 'iyilestirir', 'iyilesme', 'gecirir',
    'yok eder', 'kesin sonuc', 'mucize', 'kalici cozum', 'sifa',
    'agriyi keser', 'agri keser', 'analjezik', 'antifungal', 'antibakteriyel',
    // 'onari' koku: onarir / onarim / onarici hepsini kapsar.
    // Ayri ayri yazilinca "Onarici Bakim Kremi" URUN ADI kaciyordu.
    'onari', 'hizlandirir',
    // 13.09.2026 - ilac karinesi yaratan, filtrede eksik kalan terimler
    'antiviral', 'antiseptik', 'antienflamatuar', 'antiinflamatuar',
    'mikrop', 'dezenfekte', 'steril eder', 'bakteri oldur', 'bakteri kirici',
    'antimikrobiyal', 'mikrobiyal', 'antipatojen', 'patojen'
  ], 'tedavi-fiili', 'BLOKLU',
     'Tedavi/iyilestirme cagrisimi',
     'Saglik Beyani Yonetmeligi m.9/(3)');

  // ------------------------------------------------------------------
  // 3. YASAK NESNELER (fizyolojik fonksiyon / yapisal degisim) -> BLOKLU
  //    03_MEVZUAT §1: fiil degil, cumlenin NESNESI denetlenir
  // ------------------------------------------------------------------
  tara([
    'dolasim', 'kan akisi', 'kan gider', 'mikrosirkulasyon', 'damar',
    'hormon', 'kas', 'refleks', 'metabolizma', 'bagisiklik',
    'kolajen', 'elastikiyet', 'hucre yenilenmesi', 'hucresel', 'doku onarimi',
    'melanin uretimi', 'folikul', 'dopamin', 'serotonin', 'odul merkezi',
    'sinapx', 'noron', 'vazodilatasyon',
    // 13.09.2026 - fizyolojik fonksiyon iddiasi, filtrede eksik kalanlar.
    // DIKKAT: 'doku' ve 'hucre' TEK BASINA eklenmez - "cildin dokusu",
    // "kremin dokusu" mesru kozmetik ifadeleri; nesneyle birlikte yazilir.
    'lenf', 'detoks', 'oksijenlen', 'doku yenile', 'doku canlan', 'doku onar',
    'hucre yenile', 'hucre canlan', 'hucre onar', 'hucre yapisi',
    'savunma sistemi', 'sindirim',
    'kan basinci', 'tansiyon', 'kalp ritmi', 'sinir sistemi',
    // Cinsel islev iddialari - VIREON/FEMISIA kutu metninde gecti
    'afrodizyak', 'libido', 'cinsel istek', 'cinsel performans',
    'ereksiyon', 'orgazm', 'dogurganlik', 'sperm'
  ], 'yasak-nesne', 'BLOKLU',
     'Fizyolojik fonksiyon veya yapisal degisim iddiasi - izinli nesne degil',
     'Kozmetik Urunler Yonetmeligi + TITCK Sinir Urunler Kilavuzu m.9/(4)/(c)');

  // ------------------------------------------------------------------
  // 4. VIREON / FEMISIA - ASLA ANLATILMAYACAK BILESENLER -> BLOKLU
  //    02_URUN_GERCEGI: ilac karinesi
  // ------------------------------------------------------------------
  tara(['epimedium', 'tribulus', 'damiana', 'maca', 'arginine', 'arjinin'],
     'ilac-karinesi-bileseni', 'BLOKLU',
     'Ilac etken maddesi olarak kullanilan bilesen one cikarilamaz (INCI listesinde kalir)',
     'TITCK Sinir Urunler Kilavuzu m.9/(4)/(c)-1');

  // ------------------------------------------------------------------
  // 5. KATALOG/KANAL DISI URUNLER -> BLOKLU
  //    02_URUN_GERCEGI s.188: WhatsApp katalogu filtrelenmeden acilmaz
  // ------------------------------------------------------------------
  tara(['vireon', 'femisia', 'intimblanc', 'liftelle', 'gece serisi', 'geceserisi'],
     'kanal-disi-urun', 'BLOKLU',
     'Bu urun WhatsApp/Instagram katalogu disinda - risk mavi tikli hesabin kendisi',
     '02_URUN_GERCEGI.md (06.09.2026)');

  // Master Ritual Matrix v12.1.1 (26.08.2026) - Engine Class = EXCLUDED
  // Siniflandirma sorunu var (biyosidal/kozmetik). Konusulmaz.
  tara(['softguard', 'buguard', 'bugguard', 'bebepur'],
     'motor-disi-urun', 'BLOKLU',
     'Master Matrix Engine Class = EXCLUDED - siniflandirma cozulmeden konusulmaz',
     'LCARLIE_Master_Ritual_Matrix_v12_1_1.xlsx');

  // Master Ritual Matrix - Engine Class = PENDING APPROVAL
  // "Products with unresolved formula/classification issues cannot become
  //  primary recommendations" (Decision Engine, Layer 8 Evidence Gate)
  // 🔴 SATIS DISI - BAKANLIK ONAYI BEKLIYOR
  //    Sahip beyani (Ozer Yildiz, 13.09.2026):
  //    "earclia aurolis ve nomore su an satis disi, bakanlik onayi bekliyor"
  //
  // Bu GECICI bir durumdur - onay gelince uculu de satisa acilabilir.
  // (Kalici kaldirma DEGIL; kaldirilirlarsa gerekce guncellenmeli.)
  //
  // Not: AUROLIS 13.09.2026'ya kadar HICBIR engel listesinde degildi -
  // sorulsa ajan fiyat verebilirdi. Ayrica AUROLIS'in KUTU metni
  // "MIGREN Rahatlatici Roll-On" diyor; site metni temiz ama urun satista degil.
  tara(['earclia', 'earchia', 'nomore', 'no more', 'aurolis', 'aurolıs', 'auroli'],
     'onay-bekleyen-urun', 'BLOKLU',
     'Bakanlik onayi bekliyor - su an satis disi, onerilmez',
     'Sahip beyani 13.09.2026 + Master Matrix PENDING APPROVAL');

  // 🔴 13.09.2026 - LISTE BOSALTILDI (mekanizma duruyor).
  //
  // Eski hali: tara(['kinesis'], ...) - iki gerekce vardi:
  //   1) "KINESIS+ Ay 1 takviminden cikarildi"  -> PAZARLAMA TAKVIMI karari.
  //      Bu bir mevzuat sorunu degil; mevzuat filtresine ait degil.
  //   2) "katalog metni kirli"                  -> ARTIK GECERSIZ.
  //      KINESIS'in site metni tarandi (temiz) ve ajanin kullandigi metin
  //      KATALOG-YAZIM-KILAVUZU'na gore yeniden yazildi, filtreden temiz gecti.
  //
  // Urun bilgi tabani 4'ten 30'a cikarilinca bu kapi satisi engelliyordu:
  // "kinesis fiyat" -> INCELE -> insana aktar. Satis kaybi.
  //
  // Takvim kapisi geri istenirse urun adini bu listeye yazmak yeterli:
  const TAKVIM_DISI = [];   // ornek: ['kinesis']
  if (TAKVIM_DISI.length) {
    tara(TAKVIM_DISI, 'takvim-disi-urun', 'INCELE',
       'Kampanya takvimi disinda - satis ekibi teyidi istenir',
       '00_BASLA_BURADAN.md');
  }

  // ------------------------------------------------------------------
  // 6. "ICERMEZ" KALIBI -> BLOKLU (adillik kriteri, belge kurtarmaz)
  // ------------------------------------------------------------------
  if (/icermez|icermeyen|arindirilmis|free from|\bicermiyor\b/.test(n2)) {
    bulgular.push({
      tur: 'icermez-kalibi', ifade: 'icermez/icermeyen', sonuc: 'BLOKLU',
      gerekce: 'Yasal olarak kullanilabilen bilesenler icin hicbir kosulda kullanilmaz - sorun ispat degil ADILLIK',
      dayanak: 'Ticari Reklam Yonetmeligi (adillik) - 03_MEVZUAT §2'
    });
  }

  // ------------------------------------------------------------------
  // 7. USTUNLUK IDDIALARI -> BLOKLU
  // ------------------------------------------------------------------
  tara(['en iyi', 'en etkili', 'lider', 'turkiyenin ilk', 'turkiye nin ilk',
        'bir numara', '1 numara', 'rakipsiz', 'essiz',
        // 14.09.2026 eklenenler
        'kat kat', 'muadil', 'daha etkili', 'birebir'],
     'ustunluk-iddiasi', 'BLOKLU',
     'Ustunluk iddiasi - ispat kulfeti reklamverende',
     'Ticari Reklam Yonetmeligi m.8');

  // 🔴 14.09.2026 - YASLANMA / ESTETIK IDDIALARI
  // Kozmetik urun yapisal degisim vaat edemez.
  tara([
    'kirisiklik', 'kirisik', 'ince cizgi', 'anti aging', 'antiaging',
    'anti-aging', 'yaslanma karsiti', 'genclestir', 'sikilastir',
    'dolgunlastir', 'botoks', 'lifting etkisi', 'beyazlatir', 'agartir',
    'gozenek', 'kucultur'
  ], 'yaslanma-iddiasi', 'BLOKLU',
     'Yapisal degisim / yaslanma karsiti iddia kozmetik urunde kullanilamaz',
     'Kozmetik Urunler Yonetmeligi + Ticari Reklam Yonetmeligi m.8');

  // 🔴 OTORITE / ONAY ALGISI
  // Kozmetik urun "onayli/ruhsatli" izlenimi veremez; bildirimle piyasaya sunulur.
  tara([
    'bakanlik onayli', 'saglik bakanligi onayli', 'ruhsatli', 'fda onayli',
    'dermatolog onayli', 'dermatolog testli', 'eczane urunu', 'recetesiz',
    'terapotik'
  ], 'otorite-algisi', 'BLOKLU',
     'Resmi onay/ruhsat algisi yaratan ifade - kozmetik urun bildirimle sunulur',
     'Kozmetik Urunler Yonetmeligi + TITCK Sinir Urunler Kilavuzu');

  // 🔴 MUTLAKLIK / GUVENLIK VAADI
  tara([
    'yan etkisi yok', 'yan etkisiz', 'zararsiz', 'tamamen guvenli',
    'bagimlilik yapmaz', 'hicbir riski yok', 'her cilt tipine uygun',
    'non komedojenik'
  ], 'mutlaklik-iddiasi', 'BLOKLU',
     'Mutlak guvenlik/uygunluk vaadi belgelenemez',
     'Ticari Reklam Yonetmeligi m.8');

  // ------------------------------------------------------------------
  // 8. SURE / ORAN IDDIALARI -> BLOKLU (belge yoksa)
  // ------------------------------------------------------------------
  // Raf omru, son kullanma ve saklama suresi YASAL ZORUNLULUKTUR, iddia degil.
  // Ayrica "15 dakika once uygula" gibi KULLANIM talimatlari da iddia degil.
  // Raf omru, saklama kosulu, kullanim talimati ve GUVENLIK UYARISI iddia degildir.
  // Ornek: "uygulama sonrasi en az 12 saat direkt gunes isigindan kacinin" -> uyari.
  const sureMuafiyeti = new RegExp(
    'raf omru|shelf life|son kullanma|saklay|saklama|storage|store in|expiry|expiration|pao|' +
    'acildiktan sonra|after opening|dakika once|minutes before|gunese cikmadan|once uygulay|' +
    'kacinin|kacininiz|avoid|gunes isigindan|sunlight|uygulama sonras|maruz birak'
  ).test(n2);
  if (!sureMuafiyeti && /\b\d+\s*(gun|gunde|hafta|haftada|saat|saatte|ay|ayda)\b/.test(n2)) {
    bulgular.push({
      tur: 'sure-iddiasi', ifade: 'sure belirten ifade', sonuc: 'BLOKLU',
      gerekce: 'Klinik veri olmadan sure sonucu verilemez ("14 gunde", "96 saat")',
      dayanak: 'Ticari Reklam Yonetmeligi m.8'
    });
  }
  // 🔴 URL'leri ve yuzde-kodlamayi oran kontrolunden CIKAR.
  // "minisooth-bebek-pi%C5%9Fik-kremi" gibi bir adres %C5 yuzunden
  // "yuzde iddiasi" sayiliyor ve GECERLI urun cevabi bloklaniyordu.
  // (14.09.2026'da tam bu oldu: MINISOOTH cevabi hic gonderilemedi.)
  // ⚠️ SADECE adresler cikarilir. "%XX yuzde-kodlamasini da temizle" demek
  // CAZIP ama YANLIS: "%95" de gecerli onaltilik sayidir ve GERCEK bir
  // yuzde iddiasi silinir. (Bu tuzaga dustum, test yakaladi.)
  // Adres zaten butunuyle cikarildigi icin icindeki %C5 de gitmis olur.
  const oranMetni = n2.replace(/https?:\/\/\S+/g, ' ');

  if (/%\s*\d+|\b\d+\s*%/.test(oranMetni) && !/spf/.test(oranMetni)) {
    bulgular.push({
      tur: 'oran-iddiasi', ifade: 'yuzde ifadesi', sonuc: 'INCELE',
      gerekce: 'Rakam/oran varsa belgesi gosterilmeli',
      dayanak: 'Ticari Reklam Yonetmeligi m.8'
    });
  }

  // ------------------------------------------------------------------
  // 9. BELGESIZ KULLANILAMAYAN IFADELER -> BLOKLU
  // ------------------------------------------------------------------
  tara(['%100 dogal', '100 dogal', 'tamamen dogal', 'kimyasallardan arindir',
        'klinik etkinligi kanitlanmis', 'klinik olarak test', 'klinik olarak kanitlanmis',
        'dermatolojik olarak test', 'dermatolojik olarak onaylanmis', 'hipoalerjenik',
        'doktor formulu', 'doktor tavsiyesi'],
     'belgesiz-ifade', 'BLOKLU',
     'Belge olmadan kullanilamaz',
     'Ticari Reklam Yonetmeligi m.8');

  // GMP / ISO ustunluk kurgusu
  if (/(gmp|iso\s*22716)/.test(n2)) {
    bulgular.push({
      tur: 'gmp-iso-ustunluk', ifade: 'GMP / ISO 22716', sonuc: 'INCELE',
      gerekce: 'Yasal gerekliliktir, urune ozgu fayda olarak sunulamaz',
      dayanak: '03_MEVZUAT §2/5'
    });
  }

  // ------------------------------------------------------------------
  // 10. TIBBI TAVSIYE / ONAY CUMLELERI -> BLOKLU
  //     03_MEVZUAT §8: "Evet iyi gelir" ve "denemenizi oneririm" yasak
  // ------------------------------------------------------------------
  tara(['iyi gelir', 'iyi geliyor', 'denemenizi oneririm', 'tavsiye ederim',
        'kullanabilirsiniz sorun olmaz', 'gecer merak etmeyin'],
     'tibbi-onay', 'BLOKLU',
     'Sikayete karsi urun onerme / onaylama yasak - hekime yonlendirilir',
     '03_MEVZUAT §8');

  // ------------------------------------------------------------------
  // 11. YUMUSAK LISTE -> INCELE (insan gozden gecirir)
  // ------------------------------------------------------------------
  tara(['leke', 'gecti', 'agri', 'alerji', 'doktor', 'eczaci', 'yara', 'sisme'],
     'yumusak-liste', 'INCELE',
     'Baglama gore riskli - insan kontrolu gerekir',
     '03_MEVZUAT §7 yumusak liste');

  // ------------------------------------------------------------------
  // 12. GUNES KORUYUCU - ZORUNLU IBARE SETI
  // ------------------------------------------------------------------
  // 🔴 ONEMLI: Zorunlu ibare seti ve lockup, BIZIM yazdigimiz metnin yukumlulugu.
  // Musterinin kendi mesajinda bunlari aramak yanlis - "Sunacnea ne kadar" diyen
  // musteri yasal ibareleri yazmaz. Bu kontroller sadece giden metne uygulanir.
  const bizimMetin = (baglam.kaynak || '') !== 'gelen';
  const gunesUrunu = bizimMetin && /sunacnea|babysol|spf|gunes koruyucu|gunes kremi/.test(n2);
  if (gunesUrunu) {
    const zorunlu = [
      { anahtar: /yeterli miktarda/, ad: 'Yeterli miktarda uygulanmamasi korumayi dusurur' },
      { anahtar: /asiri gunes|guneş maruziyeti|maruziyet/, ad: 'Asiri gunes maruziyeti saglik tehdididir' },
      { anahtar: /bebek|kucuk cocuk/, ad: 'Bebek ve kucuk cocuklar dogrudan gunese maruz birakilmamali' },
      { anahtar: /%100 koruma|tam koruma|hicbir urun/, ad: 'Hicbir urun %100 koruma saglamaz' }
    ];
    const eksik = zorunlu.filter(z => !z.anahtar.test(n2)).map(z => z.ad);
    if (eksik.length) {
      bulgular.push({
        tur: 'gunes-zorunlu-ibare', ifade: eksik.join(' | '), sonuc: 'INCELE',
        gerekce: 'Gunes koruyucu iceriklerinin TAMAMINDA zorunlu ibare seti gecer',
        dayanak: '03_MEVZUAT §5'
      });
    }
    // SUNACNEA kilitli lockup
    if (/sunacnea/.test(n2) && !/spf\s*30/.test(n2)) {
      bulgular.push({
        tur: 'sunacnea-lockup', ifade: 'SUNACNEA · SPF 30 Gunluk Gunes Koruyucu', sonuc: 'BLOKLU',
        gerekce: 'Urun adi tek basina iddiadir - kilitli lockup her yerde tam yazilir',
        dayanak: '03_MEVZUAT §4'
      });
    }
  }

  // ------------------------------------------------------------------
  // 13. HYDRAVIE SERAMID TUTARSIZLIGI
  // ------------------------------------------------------------------
  if (/hydravie/.test(n2) && /seramid|ceramide/.test(n2)) {
    bulgular.push({
      tur: 'hydravie-seramid', ifade: 'seramid / ceramide', sonuc: 'BLOKLU',
      gerekce: 'Aciklamada var ama gorunur INCI\'de seramid YOK - resmi dosyayla cozulene kadar iddia kullanilmaz',
      dayanak: '02_URUN_GERCEGI.md - Ay 1 ana urunu, oncelikli'
    });
  }

  // ------------------------------------------------------------------
  // 14. SAGLIK CALISANI ALGISI
  // ------------------------------------------------------------------
  tara(['beyaz onluk', 'onluk', 'klinik ortam', 'laboratuvar', 'hekim onerisi'],
     'saglik-calisani-algisi', 'INCELE',
     'Saglik calisani algisi yaratan sunum',
     'Ticari Reklam Yonetmeligi m.16/(3)');

  // ------------------------------------------------------------------
  // 15. ONCESI / SONRASI
  // ------------------------------------------------------------------
  if (/oncesi.*sonrasi|once.*sonra gorsel|before.*after/.test(n2)) {
    bulgular.push({
      tur: 'oncesi-sonrasi', ifade: 'oncesi/sonrasi', sonuc: 'INCELE',
      gerekce: 'Ayni isik/aci/kamera/kosul, gercek sure, retouch yok, tipik sonuc aciklamasi gerekir',
      dayanak: '03_MEVZUAT §12'
    });
  }

  // ------------------------------------------------------------------
  // SONUC
  // ------------------------------------------------------------------
  const bloklu = bulgular.filter(b => b.sonuc === 'BLOKLU');
  const incele = bulgular.filter(b => b.sonuc === 'INCELE');

  let sonuc, etiket, insanaAktar, mesaj;
  if (bloklu.length) {
    sonuc = 'BLOKLU';
    etiket = 'C';   // saglik/tedavi cagrisimi nedeniyle bloklu
    insanaAktar = true;
    mesaj = 'Bu metin musteriye GONDERILMEZ. Insana aktarilmali.';
  } else if (incele.length) {
    sonuc = 'INCELE';
    etiket = 'B';   // dogrulama gerekli
    insanaAktar = true;
    mesaj = 'Otomatik gonderilmez. Insan onayindan sonra gonderilebilir.';
  } else {
    sonuc = 'TEMIZ';
    etiket = 'D';   // yalniz duyusal/kullanim deneyimi ifadesi
    insanaAktar = false;
    mesaj = 'Gonderilebilir.';
  }

  return {
    sonuc,
    etiket,
    insanaAktar,
    mesaj,
    bulguSayisi: bulgular.length,
    bloklu: bloklu.length,
    incele: incele.length,
    bulgular,
    // Ispat kulfeti kaydi icin
    kayit: {
      tarih: new Date().toISOString(),
      metin: ham,
      sonuc,
      etiket,
      kaynak: baglam.kaynak || 'bilinmiyor',
      musteriId: baglam.musteriId || null
    }
  };
}

module.exports = { mevzuatFiltresi };
