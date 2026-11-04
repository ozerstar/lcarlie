// =====================================================================
// L'CARLIE - SATIS AJANI KONUSMA AKISI (kanal bagimsiz)
//
// Girdi : { mesaj, musteriId, kanal }
// Cikti : { sinif, taslakCevap, insanaAktar, gonder, ... }
//
// Kurallar:
//  - Cevaplarda SORU SORULMAZ (kapanis sorusu yok)
//  - Savunmaci/kuskulu dil yok
//  - Her cevap somut CTA ile biter (site linki)
//  - Saglik sorusunda urun onerilmez, hekime yonlendirilir
//  - Uretilen her taslak ayrica MEVZUAT FILTRESINDEN gecer
// =====================================================================

const SITE = 'https://lcarlie.shop';

// Urun bilgi tabani:
//  - n8n'de urunler.js ayni Code node'una ONCE gomulur, fonksiyonlar hazirdir.
//  - Node testinde ayri dosyadan yuklenir.
// Urun tabani hic yuklenmezse motor calismaya devam eder, sadece genel
// sablonlari kullanir (urune ozel cevap vermez).
if (typeof urunTani === 'undefined') {
  // 🔴 Yeni bir yardimci fonksiyon eklerken BURAYA DA yaz - yoksa sessizce
  //    undefined kalir, sinif dogru secilir ama YEDEK sablon gonderilir.
  //    (fiyatItiraziCevabi ve caprazSatis'ta tam bu oldu.)
  try { var { urunTani, urunCevabi, RITUEL_LINK,
               kategoriTani, kategoriCevabi, GIRIS_URUNLERI, URUNLER,
               fiyatItiraziCevabi, caprazSatis, kategoriListesi,
               satistaAnlatilmayan, satisLinkiCevabi } = require('./urunler.js'); } catch (e) { /* yok, sorun degil */ }
}

function asciiye(s) {
  let t = String(s || '').toLocaleLowerCase('tr-TR')
    .replace(/ı/g, 'i').replace(/İ/g, 'i').replace(/i̇/g, 'i')
    .replace(/ş/g, 's').replace(/ğ/g, 'g').replace(/ç/g, 'c')
    .replace(/ö/g, 'o').replace(/ü/g, 'u');

  // 🔴 KACINMA KARSITI NORMALIZASYON (kirmizi takim testinde bulundu).
  // "egz4ma", "e.g.z.a.m.a", "v i r e o n" gibi yazimlar filtreyi asiyordu.

  // 1) Rakam/sembol ile harf taklidi.
  //    🔴 SADECE harfe bitisik ve baska rakama bitisik OLMAYAN rakamlar cevrilir.
  //    Yoksa "SPF 30" -> "spf eo", "50 ml" -> "so ml" olur ve gercek kontroller kirilir.
  const LEET = { '4':'a', '0':'o', '1':'i', '3':'e', '5':'s', '@':'a', '$':'s' };
  t = t.replace(/[40135@$]/g, (ch, i, tam) => {
    const onceki = tam[i - 1] || '';
    const sonraki = tam[i + 1] || '';
    const harfeBitisik  = /[a-z]/.test(onceki) || /[a-z]/.test(sonraki);
    const rakamaBitisik = /[0-9]/.test(onceki) || /[0-9]/.test(sonraki);
    return (harfeBitisik && !rakamaBitisik) ? LEET[ch] : ch;
  });

  // 2) Tek harflerin ayriklastirilmasi: "e g z a m a" / "e.g.z.a.m.a" -> "egzama"
  //    Ard arda en az 3 tek harf varsa aralarindaki ayiraclar silinir.
  t = t.replace(/\b(?:[a-z][\s._\-*]+){2,}[a-z]\b/g, m => m.replace(/[\s._\-*]+/g, ''));

  return t;
}

// ---------------------------------------------------------------------
// 1. DURDURMA (opt-out) - 6563 sayili Kanun / IYS
//    Her seyden ONCE bakilir. Eslesirse baska hicbir sey yapilmaz.
// ---------------------------------------------------------------------
// 🔴 Tek basina "red" YAZMA - "nereden", "kredi", "adres" icinde yakalaniyor.
const DURDURMA = [
  'mesaj istemiyorum', 'mesaj gelmesin', 'mesaj atmayin', 'mesaj göndermeyin',
  'mesaj atma', 'rahatsiz etmeyin', 'rahatsiz etme', 'listeden cikar',
  'listenizden cikar', 'abonelikten cikar', 'iptal et', 'dur artik',
  'beni engelle', 'iletisim kurmayin', 'reddediyorum', 'istemiyorum artik',
  'artik istemiyorum', 'bir daha yazmayin', 'bir daha mesaj'
];

function durdurmaMi(mesaj) {
  const m = asciiye(mesaj);
  // Tek basina "dur" / "iptal" gibi kisa komutlar
  if (/^(dur|iptal|cik|stop|hayir)[.!]?$/.test(m.trim())) return true;
  return DURDURMA.some(k => m.includes(asciiye(k)));
}

// ---------------------------------------------------------------------
// 2. SINIFLANDIRMA - kural tabanli, deterministik, test edilebilir
//    Sira ONEMLI: yukarıdaki kazanir (saglik her zaman once gelir)
// ---------------------------------------------------------------------
const SINIFLAR = [
  {
    // Gercek saglik sinyalleri. "odem", "eczane" gibi yanlis pozitif
    // ureten kelimeler BILEREK yok (eczane -> SIPARIS'e tasindi).
    ad: 'SAGLIK',
    anahtar: [
      'egzama','sedef','akne','sivilce','mantar','iltihap','dermatit','hemoroid',
      'varis','kanser','roza','alerji','hastalik','rahatsizlik','tedavi','recete',
      'doktor','hekim','iyi gelir mi','gecer mi','ise yarar mi','faydasi var',
      'derdim var','sorunum var','kasinti','kizariklik','tahris','yara','yaram',
      'agri','agriyor','sisme','hamile','gebe','emzir','bebegime','bebege',
      'cocuguma','cocuguma','kucugume','kucuguma','torunuma',
      'leke','lekelerim','sakincasi var','zarari var','kullanabilir miyim',
      // 13.09.2026 - 'odem' ARTIK GUVENLE eklenebiliyor: SINIF_ISTISNA
      // 'odeme' onekini disliyor, yani "odemem gecti mi" SAGLIK sayilmiyor.
      'odem',
      // Cocuk icin sorma bicimleri eksikti - "kizima surebilir miyim"
      // eskale EDILMIYORDU.
      'kizima','kizim','oglum','ogluma','yegenime','kardesime'
    ]
  },
  { ad: 'IADE',    anahtar: ['iade','iptal etmek','geri gonder','degisim','degistir','cayma',
                             'memnun kalmadim','para iadesi','param ne zaman','parami',
                             'yanlis urun','eksik urun','hasarli geldi'] },
  { ad: 'SIKAYET', anahtar: ['sikayet','rezalet','berbat','kandirdiniz','dolandir','mahkeme',
                             'tuketici hakem','sikayetvar','cevap yok','cevap vermiyor',
                             'ilgilenen yok','ulasamiyorum','kimse bakmiyor'] },
  { ad: 'KARGO',   anahtar: ['kargo','teslimat','ne zaman gelir','gonderim','takip numarasi',
                             'kac gunde gelir','elime gecer','ulasir mi','ulasmadi','gelmedi',
                             'nerede kaldi'] },
  // 🔴 SIRA ONEMLI: KULLANIM, FIYAT'tan ONCE gelmeli.
  // FIYAT'ta "ne kadar" var; "ne kadar surulur" sorusu yoksa fiyat sanilir.
  { ad: 'KULLANIM',anahtar: ['nasil kullan','kullanim','kullanil','surul','gunde kac','sabah mi',
                             'aksam mi','ne siklikla','saklama','nasil uygulan','uygulama sekli'] },
  // NOT: Turkcede k -> g yumusamasi var ("icerik" ama "icerigi").
  // Bu yuzden hem 'icerik' hem 'icerig' kokleri yazili.
  // 'inci' tek basina yazilmaz - "ikinci" kelimesinin icinde de gecer.
  // 🔴 'icinde ne' 20.09.2026'da eklendi. Olculdu: "Icinde ne var?" mesaji
  // ANLASILMADI'ya dusuyordu, oysa growth005-okuma.sql AYNI mesaji 'icinde ne'
  // kalibiyla ICERIK sayiyor. Ayni soru iki kod yolunda iki farkli sinif
  // aliyordu; analiz sorgusu uretim siniflandiricisindan genisti.
  { ad: 'ICERIK',  anahtar: ['icerik','icerig','icindekiler','inci listesi','bilesen','formul',
                             'vegan','hayvan','paraben','alkol var mi','koku','ne var icinde',
                             'icinde ne','hangi maddeler'] },
  // IDDIA SORUSU - musteri bizden sonuc/sure/ustunluk TAAHHUDU istiyor.
  // Kirmizi takim testinde "kac gunde sonuc alirim" ve "sizinki daha mi iyi"
  // fark edilmeden geciyordu. Bunlara asla taahhut verilmez.
  // 🔴 ETKI TAAHHUDU SORULARI 20.09.2026'da eklendi - MEVZUAT DUZELTMESI.
  // 540 gercek musteri mesaji siniflandirilinca goruldu: "Cinsel. Guc.
  // Artiricimi", "Sertlesme. Yaparsa. Iyi", "uzamaya yardimci oluyor mu"
  // gibi mesajlar ANLASILMADI'ya dusuyordu. ANLASILMADI genel site linki
  // gonderir ve insanaAktar = FALSE'tur -- yani fizyolojik etki taahhudu
  // isteyen soru, insan gormeden otomatik cevap aliyordu. IDDIA_SORUSU dali
  // "sonuc veya sure taahhudunde bulunmuyoruz" der ve insana aktarir.
  //
  // Bilerek EKLENMEYENLER: cilginca genis olurlardi.
  //   'etkisi'      -> "yan etkisi var mi" SAGLIK sorusudur, iddia degil.
  //   'ne ise yarar'-> urunun ne oldugunu sormak iddia sorusu DEGIL; ayrica
  //                    SINIF_ISTISNA yorumu bunu bilerek SAGLIK'tan cikarmis.
  { ad: 'IDDIA_SORUSU', anahtar: ['kac gunde','kac haftada','kac ayda','ne kadar surede',
                                  'ne zaman sonuc','sonuc alirim','sonuc verir',
                                  'daha mi iyi','digerlerinden','rakip','karsilastir',
                                  'garanti','kesin sonuc','ise yarar mi gercekten',
                                  'cinsel','sertlesme','sertlest','sertlik yap',
                                  'uzamaya','uzatir mi','uzuyor mu','uzar mi',
                                  'artirici mi','artirir mi','artiriyor mu',
                                  'yardimci olur mu','yardimci oluyor mu','etkili mi'] },

  // KATEGORI LISTESI - "hangi kategoriler var", "ne satiyorsunuz"
  // Acilis ekranindaki "Ihtiyacima gore urun oner" butonu da buraya duser.
  // ONERI'den ONCE gelmeli: "hangi urunler var" katalog sorusudur,
  // uclu rutin onerisi degil.
  { ad: 'KATEGORI_LISTESI',
    anahtar: ['hangi kategori','kategoriler','ne satiyorsunuz','neler satiyorsunuz',
              'urunleriniz neler','hangi urunler var','urun gamiz','urun yelpazesi',
              'tum kategoriler','bakim kategorileri','ihtiyacima gore','ne tur urun'] },

  // ONERI - SATIS FIRSATI. Musteri ne alacagini soruyor.
  // Uclu rituele yonlendirilir; cilt TIPI/SORUNU iddiasinda bulunulmaz.
  { ad: 'ONERI',   anahtar: ['ne onerirsiniz','hangi urun','ne alayim','ne kullanmaliyim',
                             'tavsiye eder misiniz','ne tavsiye','set halinde','set var mi',
                             'paket var mi','rutin onerisi','hangisini almaliyim',
                             // Acilis ekranindaki "Gunluk bakim rutini" butonu
                             'gunluk bakim rutini','bakim rutini','rutin',
                             'cildim kuru','cildim yagli','cildim hassas'] },

  { ad: 'SIPARIS', anahtar: ['siparis','satin al','nasil alabilirim','nereden alabilirim',
                             'nereden alinir','sepet','kapida odeme','havale','kredi karti',
                             'satis noktasi','magaza','eczane','bayi','bayilik','toptan',
                             'stok var mi','stokta var mi'] },
  // 🔴 FIYAT'TAN ONCE gelmeli - "pahali" iceren mesaj duz fiyat sorusu degil,
  // ITIRAZDIR ve farkli cevap ister. Once ANLASILMADI'ya dusup genel site
  // linki aliyordu; satisin en kritik anini bos geciyorduk.
  { ad: 'FIYAT_ITIRAZI',
    anahtar: ['pahali','pahalimi','cok tutuyor','butcem','butce','ucuz',
              'daha uygun','uygun fiyatli','fiyatlar yuksek','yuksek fiyat',
              'ekonomik','indirimli olani','ucuz olan','bu kadar para'] },

  { ad: 'FIYAT',   anahtar: ['fiyat','ne kadar','kac para','kac tl','kac lira','kaca',
                             'ucret','indirim','kampanya','tl mi','hediye paketi'] },

  { ad: 'MARKA',   anahtar: ['nerelisiniz','kimlersiniz','firma nerede','neredesiniz',
                             'hakkinizda','markaniz','uretici','nerede uretiliyor',
                             'instagramdan','reklaminizi','arkadasim onerdi','daha once almistim'] },

  { ad: 'TESEKKUR',anahtar: ['tesekkur','sagol','sag ol','eyvallah','anladim','tamamdir',
                             'bakacagim','dusuneyim','peki','olur','tamam','ok','okey'] },

  { ad: 'SELAMLAMA', anahtar: ['merhaba','selam','iyi gunler','iyi aksamlar','gunaydin','kolay gelsin','slm'] },
];

// 🔴 Duz includes() KULLANMA. "odeme" icinde "odem", "nereden" icinde "red"
// yakalaniyordu. Tek kelimeler icin kelime basindan eslesme + ek kabulu,
// cok kelimeli ifadeler icin dogrudan arama.
// 🔴 ISTISNA: mevzuat filtresindeki liste ile AYNI mantik.
// Buraya eklenmedigi icin "ne ise YARAR" SAGLIK sanilip hekime yonlendiriliyordu -
// oysa Turkcede bir urunun ne yaptigini sormanin en dogal yolu bu.
const SINIF_ISTISNA = {
  // 'yaras' EKLENMEZ: "yarasir" nadir ama "YARASI" (yatak yarasi, yarasi var)
  // cok yaygin ve gercek bir saglik ifadesi - onu kacirmak kabul edilemez.
  'yara' : ['yarar', 'yarat', 'yarasa'],            // yararli, yaratici, yarasa
  'kas'  : ['kasim', 'kasa', 'kastet', 'kasiyer'],
  'odem' : ['odeme'],
  'agri' : ['agrikultur'],
  'aft'  : ['after', 'aftershave']
};

function eslesirMi(metin, terim) {
  const t = asciiye(terim);
  if (/\s/.test(t)) return metin.includes(t);

  // 🔴 TURKCE UNSUZ YUMUSAMASI:  k->g, t->d, p->b, c->c
  // "bacak"+ek = "bacagimda", "cilt"+ek = "cildimde", "kitap" -> "kitabim".
  // Sadece k->g yazmistim; "cildimde kuruluk var" bu yuzden kaciyordu.
  const YUMUSAMA = { k: 'g', t: 'd', p: 'b' };
  const govdeler = [t];
  const son = t.slice(-1);
  if (YUMUSAMA[son]) govdeler.push(t.slice(0, -1) + YUMUSAMA[son]);

  const haric = SINIF_ISTISNA[t];
  for (const g of govdeler) {
    const re = new RegExp('(^|[^a-z0-9])(' + g.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[a-z]*)', 'g');
    let mm;
    while ((mm = re.exec(metin)) !== null) {
      const tamKelime = mm[2];
      if (haric && haric.some(onek => tamKelime.startsWith(onek))) continue;
      return true;
    }
  }
  return false;
}

function siniflandir(mesaj) {
  const m = asciiye(mesaj);
  for (const s of SINIFLAR) {
    if (s.anahtar.some(k => eslesirMi(m, k))) return s.ad;
  }
  return 'ANLASILMADI';
}

// ---------------------------------------------------------------------
// 3. CEVAP SABLONLARI
//    Hepsi: soru sormaz · savunmaci degil · CTA ile biter
//    Hepsi ayrica mevzuat filtresinden gecirilir (test ediliyor)
// ---------------------------------------------------------------------
const SABLON = {
  // 🔴 ILK TEMAS MESAJI - musteriye ilk giden metin budur, satis yapmali.
  // Icinde: marka ne, rutin nedir, hangi urunler, FIYAT, nereden alinir.
  // NOT: Gunes koruyucunun ADI bilerek anilmiyor - anilirsa mevzuat 4 zorunlu
  // ibarenin de eklenmesini sart kosuyor ve mesaj okunamaz uzunluga cikiyor.
  // Ucuncu adim "koruma" olarak geciyor, urun rituel sayfasinda gorunuyor.
  SELAMLAMA: {
    cevap:
      `Merhaba, L'CARLIÉ'ye hoş geldiniz. ` +
      `Günlük bakım rutinimiz üç adımdan oluşuyor:\n` +
      `1) Temizle — LUCIDERM Yüz Temizleme Köpüğü · 1.200 TL\n` +
      `2) Nemlendir — HYDRAVIE El & Yüz Nemlendirici Krem, 50 ml · 1.200 TL\n` +
      `3) Koru — güneş koruma adımı\n` +
      `Üç adımı tek seferde almak için: ${RITUEL_LINK}\n` +
      `Tüm ürünleri incelemek için: ${SITE}`,
    insanaAktar: false
  },

  FIYAT: {
    cevap: `Tüm ürünlerimizin güncel fiyatları ürün sayfalarımızda yer alıyor. Hemen sipariş vermek için: ${SITE}`,
    insanaAktar: false
  },

  SIPARIS: {
    cevap: `Siparişinizi doğrudan sitemizden verebilirsiniz. Hemen sipariş vermek için: ${SITE}`,
    insanaAktar: false
  },

  KULLANIM: {
    cevap: `Ürünün kullanım şekli ve önerilen sıklık, ürün sayfasındaki açıklamada ve ambalaj üzerinde yer alıyor. Ürün sayfasına buradan ulaşabilirsiniz: ${SITE}`,
    insanaAktar: false
  },

  ICERIK: {
    cevap: `Ürünlerimizin tam içerik listesi (INCI) ilgili ürün sayfasında yer alıyor. Ürün sayfasına buradan ulaşabilirsiniz: ${SITE}`,
    insanaAktar: false
  },

  // --- Insan mudahalesi gerekenler ---
  SAGLIK: {
    cevap: `L'CARLIÉ ürünleri kozmetik bakım ürünleridir. Cildinizle ilgili bir durum için hekiminize danışmanızı öneririz. Ürünlerimizin tam içerik listesini ürün sayfalarımızda bulabilirsiniz: ${SITE}`,
    insanaAktar: true,
    not: 'Saglik sorusu - urun onerilmez, onay verilmez. Insan kontrolu sart.'
  },

  IADE: {
    cevap: null,
    insanaAktar: true,
    not: 'Iade/cayma hakki - hukuki ve parasal konu. Otomatik cevap verilmez.'
  },

  SIKAYET: {
    cevap: null,
    insanaAktar: true,
    not: 'Sikayet - insan tarafindan ele alinmali.'
  },

  KARGO: {
    cevap: null,
    insanaAktar: true,
    not: 'Kargo suresi konusunda sitede ve sozlesmede celiski var (bkz. 03_MEVZUAT §14). Teyit edilene kadar otomatik sure vaadi verilmez.'
  },

  // Musteri bir sikayet/belirti anlatiyor ama hastalik adi gecmiyor.
  // Urun onerilmez - SAGLIK ile ayni guvenli cevap, insana aktarilir.
  BELIRTI_ANLATIMI: {
    cevap: `L'CARLIÉ ürünleri kozmetik bakım ürünleridir. Cildinizle ilgili bir durum için ` +
           `hekiminize danışmanızı öneririz. Ürünlerimizin tam içerik listesini ürün ` +
           `sayfalarımızda bulabilirsiniz: ${SITE}`,
    insanaAktar: true,
    not: 'Belirti anlatimi sezildi (vucut bolgesi + sikayet) - urun onerilmez.'
  },

  IDDIA_SORUSU: {
    cevap: `Ürünlerimiz kozmetik bakım ürünleridir; sonuç veya süre taahhüdünde bulunmuyoruz. ` +
           `İçerik ve kullanım bilgilerini ürün sayfalarımızda bulabilirsiniz: ${SITE}`,
    insanaAktar: true,
    not: 'Musteri sonuc/sure/ustunluk taahhudu istedi - taahhut verilmez, insan bilgilendirilir.'
  },

  // SATIS FIRSATI - musteri ne alacagini soruyor.
  // Cilt tipi/sorunu iddiasi YOK; sadece rutin adimlari ve link.
  ONERI: {
    cevap: `Günlük bakım rutinimiz üç adımdan oluşuyor: temizleme, nemlendirme ve koruma. ` +
           `Ürünlerimizi inceleyip size uygun olanı seçebilirsiniz: ${SITE}`,
    insanaAktar: false
  },

  // Fiyat itirazi - gercek cevap fiyatItiraziCevabi() tarafindan uretilir.
  // 🔴 SAHTE INDIRIM/ACILIYET UYDURULMAZ. Sadece katalogdaki gercekten
  //    en uygun secenekler gosterilir.
  FIYAT_ITIRAZI: {
    cevap: `Güncel fiyatlarımızın tamamı ürün sayfalarımızda yer alıyor: ${SITE}`,
    insanaAktar: false
  },

  // Kategori listesi - gercek cevap kategoriListesi() tarafindan uretilir.
  KATEGORI_LISTESI: {
    cevap: `Ürünlerimizi sitemizden inceleyebilirsiniz: ${SITE}`,
    insanaAktar: false
  },

  // Musteri bir bakim ihtiyaci soyledi - o kategorideki urunler listelenir.
  // Gercek cevap kategoriCevabi() tarafindan uretilir; bu yalnizca yedek.
  KATEGORI: {
    cevap: `Ürünlerimizi ihtiyacınıza göre inceleyebilirsiniz: ${SITE}`,
    insanaAktar: false
  },

  MARKA: {
    cevap: `L'CARLIÉ ürünleri ve marka bilgilerimiz sitemizde yer alıyor: ${SITE}`,
    insanaAktar: false
  },

  TESEKKUR: {
    cevap: `Rica ederiz. Tüm ürünlerimizi incelemek ve sipariş vermek için: ${SITE}`,
    insanaAktar: false
  },

  // 🔴 GEVSEK DAVRAN: siniflandiramadigimiz mesaji insana atmak yerine
  // yardimci bir cevap verip siteye yonlendiriyoruz. Mesajda riskli icerik
  // varsa mevzuat filtresi zaten yakalayip insani haberdar ediyor.
  ANLASILMADI: {
    cevap: `Ürünlerimizi, içerik ve kullanım bilgilerini sitemizden inceleyebilirsiniz: ${SITE}`,
    insanaAktar: false,
    not: 'Siniflandirilamadi - genel cevap gonderildi.'
  },

  DURDURMA: {
    cevap: `Talebiniz alınmıştır. Bundan sonra tarafınıza mesaj gönderilmeyecektir.`,
    insanaAktar: false,
    not: 'Opt-out kaydi olusturulmali (6563 sayili Kanun / IYS).'
  }
};

// ---------------------------------------------------------------------
// 4. ANA FONKSIYON
// ---------------------------------------------------------------------
function akisMotoru(girdi) {
  const mesaj = String(girdi.mesaj || girdi.metin || girdi.text || '').trim();
  const musteriId = girdi.musteriId || null;
  const kanal = girdi.kanal || 'bilinmiyor';
  const zaman = new Date().toISOString();

  // Bos mesaj
  if (!mesaj) {
    return {
      sinif: 'ANLASILMADI', taslakCevap: null, insanaAktar: true,
      durduruldu: false, not: 'Bos mesaj',
      mesaj, musteriId, kanal, zaman
    };
  }

  // 1) Durdurma her seyden once
  if (durdurmaMi(mesaj)) {
    const s = SABLON.DURDURMA;
    return {
      sinif: 'DURDURMA', taslakCevap: s.cevap, insanaAktar: false,
      durduruldu: true, optOut: true, not: s.not,
      mesaj, musteriId, kanal, zaman
    };
  }

  // 2) Siniflandir
  let sinif = siniflandir(mesaj);

  // 🔴 BELIRTI ANLATIMI SEZGISI (kirmizi takim testinde bulundu).
  // "bacaklarimda ince ince izler var", "yuzumde kabarcikliklar cikiyor",
  // "sacim eskisi kadar gur degil" - yasak kelime YOK ama musteri bir
  // sikayet anlatiyor. Boyle bir mesaja urun rutini onermek, urunun o
  // duruma iyi geldigini IMA etmek olur. Insana aktarilir.
  if (sinif === 'ONERI' || sinif === 'ANLASILMADI') {
    const m = asciiye(mesaj);
    const bolge = ['yuz','cilt','bacak','ayak','kol','sac','goz','diz','sirt',
                   'bel','karin','dudak','tirnak','koltuk alti','gogus','boyun',
                   'bebek','cocuk','kucugum','torun','esim',
                   // 13.09.2026 - eksik kalan bolgeler. "topugumda kuruluk"
                   // eskale EDILMIYORDU. (k->g yumusamasi eslesirMi'de cozuldu,
                   // yani 'topuk' yazmak "topugumda" icin de yeterli.)
                   'topuk','dirsek','omuz','bilek','ense','alin','yanak','cene',
                   'kulak','burun','kasik','kalca','baldir','parmak','avuc',
                   'sac derisi','kafa derisi','agiz','dis eti','oglum','kizim'];
    const sikayet = ['var','cikiyor','cikti','oluyor','olustu','degil','sorun',
                     'rahatsiz','gecmiyor','kotu','dokuluyor','kasiniyor','yaniyor',
                     // 13.09.2026 - BELIRTI ISIMLERI. Musteri her zaman "var"
                     // demiyor: "ayagimda catlak" gibi tek basina belirti adi da
                     // yaziyor ve bu eskale EDILMIYORDU.
                     'catlak','kizarik','sislik','dokuntu','kabarcik','yanma',
                     'kuruluk','pullanma','morluk','sertlesme','sisiyor'];
    const bolgeVar   = bolge.some(k => eslesirMi(m, k));
    const sikayetVar = sikayet.some(k => eslesirMi(m, k));

    // 🔴 AYRIM: "urun kelimesi geciyor mu" DEGIL, "KENDI durumunu anlatiyor mu".
    //
    // Ilk denemede sadece urun kelimesine baktim ve kirmizi takim 23/23'ten
    // 21/23'e dustu - su iki saldiri kacti:
    //   "sacim eskisi kadar gur degil ne ONERIRSINIZ"   (onerir -> muaf sandi)
    //   "esimle aramizdaki seyler icin bir URUNUNUZ VAR MI"
    // Ikisi de urun soruyor AMA kendi durumunu anlatiyor. Eskale edilmeli.
    //
    // Dogru ayrim BIRINCI TEKIL SAHIS: "sacim", "topugumda", "cildim", "esim".
    // Bolge kokunun iyelik ekli hali aranir (kok + [iıuü]m), ayrica acik
    // benlik kelimeleri listelenir.
    const benlik = ['benim','bende','bana','kendim','kendime','esim','esime','esimle'];
    const kendiDurumu =
      benlik.some(k => eslesirMi(m, k)) ||
      bolge.some(k => {
        const t = asciiye(k);
        if (/\s/.test(t)) return false;
        const YUM = { k: 'g', t: 'd', p: 'b' };
        const govdeler = [t];
        const son = t.slice(-1);
        if (YUM[son]) govdeler.push(t.slice(0, -1) + YUM[son]); // topuk->topug, cilt->cild
        return govdeler.some(g =>
          new RegExp('(^|[^a-z0-9])' + g + '[iuea]?m').test(m)); // sac+im, cild+im
      });

    // Kendi durumunu ANLATMIYORSA ve urun soruyorsa: bu bir SATIS sorusudur.
    // "catlak topuk kremi var mi" eskale edilmez - en degerli musteri sorusu.
    const urunSorusu = ['krem','urun','sprey','losyon','balm','serum','kopuk',
                        'roll','macun','jel','sampuan','var mi','varmi','fiyat',
                        'kac para','satiyor','alabilir','siparis','onerir',
                        'hangi urun','tavsiye eder',
                        // 13.09.2026 - KATEGORI sorusu kaliplari.
                        // "sac bakimi icin ne var" belirti anlatimi DEGIL,
                        // katalog sorusudur. Bunlar burada olmayinca BELIRTI
                        // tetikleniyor ve satis sorusu insana gidiyordu.
                        'bakimi','bakim icin','ne var','neler var','cesit','seri']
                       .some(k => eslesirMi(m, k) || m.includes(k));

    const muaf = urunSorusu && !kendiDurumu;

    if (!muaf && bolgeVar && sikayetVar) sinif = 'BELIRTI_ANLATIMI';
  }

  // -------------------------------------------------------------------
  // 🔴 KATEGORI NIYETI - satis firsatinin en net hali
  //
  // "ayak bakimi icin urun", "bebegim icin ne onerirsiniz",
  // "agiz bakimi urunleriniz" -> musteri ihtiyacini SOYLEMIS.
  // Once bunlar genel site linkine dusuyordu; "sac bakimi icin ne var"
  // ise BELIRTI_ANLATIMI sanilip INSANA AKTARILIYORDU. Ikisi de satis kaybi.
  //
  // Kategori BELIRTI_ANLATIMI'nin UZERINE yazar - ama sadece musteri
  // kendi durumunu anlatmiyorsa. "sacim dokuluyor" hala eskale edilir,
  // "sac bakimi icin ne var" satisa gider.
  // -------------------------------------------------------------------
  const BAKIM_NIYETI = ['bakimi', 'bakim icin', 'urun', 'urunleriniz', 'ne var',
                        'ne onerirsiniz', 'neler var', 'seriniz', 'seri',
                        'gamma', 'cesitleri', 'ne alabilirim'];
  if (typeof kategoriTani === 'function' &&
      ['ANLASILMADI', 'ONERI', 'BELIRTI_ANLATIMI', 'MARKA'].includes(sinif)) {
    const mk = asciiye(mesaj);
    const niyetVar = BAKIM_NIYETI.some(k => mk.includes(asciiye(k)));
    // Kendi durumunu anlatan musteri kategoriye kaydirilmaz - saglik onceliklidir
    const kendiDurumuVar = sinif === 'BELIRTI_ANLATIMI';
    // 🔴 BELIRTI_ANLATIMI EZILMEZ.
    // Once "niyet kelimesi varsa kategoriye cevir" diye ikinci bir dal
    // yazmistim ve kirmizi takim 23/23'ten 22/23'e dustu:
    //   "sacim eskisi kadar gur degil ne ONERIRSINIZ"  -> KATEGORI olmustu.
    // Musteri kendi durumunu anlatiyorsa urun listesi verilmez, insana gider.
    // Ayrim yukaridaki urunSorusu/kendiDurumu mantiginda yapiliyor:
    // "sac bakimi icin ne var" zaten BELIRTI'ye hic dusmuyor.
    if (niyetVar && !kendiDurumuVar && kategoriTani(mesaj, asciiye, eslesirMi)) {
      sinif = 'KATEGORI';
    }
  }

  const s = SABLON[sinif] || SABLON.ANLASILMADI;

  // 3) Urun tanindiysa genel sablon yerine urune ozel cevap kullan.
  //    Not: SAGLIK sinifi buraya HIC girmez - saglik sorusunda urun anlatilmaz.
  let taslakCevap = s.cevap;
  let urun = null;
  let insanaAktar = s.insanaAktar;

  // Kategori cevabi: urun adi gecmese bile ihtiyaca gore urun listesi ver.
  // Urun adi GECIYORSA asagidaki urun bloğu bunu zaten ezer - dogru olan da bu
  // ("dermaguard fiyat" kategori listesi degil, o urunun fiyatini almali).
  // Kategori listesi - "▸ " satirlari web'de BUTON olarak cizilir
  if (sinif === 'KATEGORI_LISTESI' && typeof kategoriListesi === 'function') {
    const kl = kategoriListesi(SITE);
    if (kl) taslakCevap = kl;
  }

  if (sinif === 'KATEGORI' && typeof kategoriTani === 'function') {
    const kat = kategoriTani(mesaj, asciiye, eslesirMi);
    const kc = kategoriCevabi(kat, SITE);
    if (kc) taslakCevap = kc;
  }

  // Fiyat itirazi: katalogdaki en uygun secenekler + uclu paket.
  if (sinif === 'FIYAT_ITIRAZI' && typeof fiyatItiraziCevabi === 'function') {
    const fc = fiyatItiraziCevabi(SITE);
    if (fc) taslakCevap = fc;
  }

  // 🔴 CAPRAZ SATIS - "luciderm aldim yanina ne alayim"
  // Once sorulan urunun kendi tanitimi tekrar veriliyordu; musteri zaten
  // o urunu ALMIS. Ayni kategorideki tamamlayici urunler gosterilir.
  //
  // 🔴🔴 KAPI SART (14.09.2026'da canlida yakalandi):
  // Bu blok ONCE hicbir sinif kontrolu yapmiyor, USTELIK 'insanaAktar = false'
  // diyerek BELIRTI_ANLATIMI'nin verdigi eskalasyon kararini EZIYORDU.
  // Sonuc canli sistemde dogrulandi:
  //   "sacim dokuluyor"                                -> insana aktariliyor (DOGRU)
  //   "luciderm aldim yanina ne alayim sacim dokuluyor" -> OTOMATIK fiyatli
  //                                                        urun listesi gidiyor (YANLIS)
  // Yani dort siradan kelime eklemek, sikayet anlatan musteriye urun
  // satmaya cevriliyordu - BELIRTI_ANLATIMI tam da bunu onlemek icin vardi.
  //
  // Iki kural: (1) riskli siniflarda capraz satis HIC calismaz,
  //            (2) bu blok insanaAktar'i ASLA dusuremez, yalniz yukseltebilir.
  const CAPRAZ_YASAK = ['SAGLIK', 'BELIRTI_ANLATIMI', 'IDDIA_SORUSU',
                        'IADE', 'SIKAYET', 'KARGO', 'DURDURMA'];
  if (typeof caprazSatis === 'function' && typeof urunTani === 'function'
      && CAPRAZ_YASAK.indexOf(sinif) === -1 && !insanaAktar) {
    const mc = asciiye(mesaj);
    const tamamlayiciNiyet = ['yanina', 'birlikte', 'beraber', 'tamamlay',
                              'baska ne', 'ne alayim', 'ek olarak', 'ilave',
                              'yaninda ne', 'bununla']
                             .some(k => mc.includes(asciiye(k)));
    if (tamamlayiciNiyet) {
      const u2 = urunTani(mesaj, asciiye);
      const cs = u2 ? caprazSatis(u2, SITE) : null;
      // insanaAktar'a DOKUNULMAZ - yukarida zaten false oldugu dogrulandi.
      if (cs) { taslakCevap = cs; urun = u2; sinif = 'CAPRAZ_SATIS'; }
    }
  }

  // 🔴 ALERJEN SORUSU TAM LISTEYI HAK EDER.
  // "Icindekiler nelerdir?" genel meraktir; "paraben var mi" bir SAGLIK
  // tedbiridir. Ikincisinde musteriyi urun sayfasina yollamak, ihtiyaci
  // olan bilgiyi bir tik arkasina saklamak olur.
  // Liste UYDURULMAZ; yalnizca urun tabanindaki INCI aynen verilir.
  const ALERJEN_IZLERI = ['paraben', 'sulfat', 'sls', 'sles', 'alkol', 'koku', 'parfum',
                          'esans', 'gluten', 'alerj', 'alarj', 'hassasiyet', 'duyarli',
                          'iceriyor mu', 'var mi', 'bulunuyor mu', 'katki', 'silikon',
                          'hayvansal', 'vegan', 'nikel', 'lateks'];
  const mesajAscii = asciiye(mesaj);
  const tamListeIstendi = ALERJEN_IZLERI.some(iz => mesajAscii.includes(iz));

  if (typeof urunTani === 'function' && sinif !== 'SAGLIK') {
    urun = urunTani(mesaj, asciiye);
    if (urun) {
      const ozel = urunCevabi(urun, sinif, SITE, tamListeIstendi);
      if (ozel) {
        taslakCevap = ozel;
        // Musteri urunun adini yazdi ve gercek bir cevap uretildi -
        // ANLASILMADI'yi insana aktarmanin anlami kalmiyor.
        if (sinif === 'ANLASILMADI') insanaAktar = false;
      }
    }
  }

  // 🔴 KARMA NIYET: "hydravie ne kadar VE kargo kac gunde gelir"
  // Tek sinif secilir (KARGO) ve fiyat sorusu tamamen kaybolur - musteri
  // urun adini yazmis olmasina ragmen FIYAT CEVABI ALAMAZ. Satis kaybi.
  //
  // Cozum: satilabilir yarisini cevapla, lojistik yarisi icin yine insana aktar.
  // KARGO/IADE'nin insanaAktar'i BOZULMAZ - sadece sessiz kalmayi biraktik.
  if ((sinif === 'KARGO' || sinif === 'IADE') && typeof urunTani === 'function') {
    const u2 = urunTani(mesaj, asciiye);
    const mn = asciiye(mesaj);   // 'm' bu kapsamda yok - yerinde normalize edilir
    const satisNiyeti = ['fiyat', 'kac para', 'kac tl', 'kac lira', 'ne kadar',
                         'ucret', 'icerik', 'nasil kullan', 'siparis']
                        .some(k => eslesirMi(mn, k) || mn.includes(k));
    if (u2 && satisNiyeti) {
      const ozel = urunCevabi(u2, 'FIYAT', SITE);
      if (ozel) {
        urun = u2;
        taslakCevap = ozel + (sinif === 'KARGO'
          ? ' Kargo ve teslimat sorunuz için ekip arkadaşımız en kısa sürede dönüş yapacak.'
          : ' İade ve değişim sorunuz için ekip arkadaşımız en kısa sürede dönüş yapacak.');
        insanaAktar = true;   // lojistik kismi icin insan yine devrede
      }
    }
  }

  return {
    sinif,
    urun,
    taslakCevap,
    insanaAktar,
    durduruldu: false,
    optOut: false,
    not: s.not || null,
    mesaj, musteriId, kanal, zaman
  };
}

// ---------------------------------------------------------------------
// 5. KARAR - motor ciktisi + iki filtre sonucu birlestirilir
//    gelenFiltre  : musterinin mesajina uygulanan mevzuat filtresi
//    taslakFiltre : bizim uretecegimiz cevaba uygulanan mevzuat filtresi
//
//    Bu fonksiyon n8n'deki son Code node'unda da AYNEN kullanilir.
// ---------------------------------------------------------------------
function kararVer(motor, gelenFiltre, taslakFiltre) {
  const gerekceler = [];
  let gonder = false;
  let cevap = motor.taslakCevap;
  let insanaAktar = motor.insanaAktar;

  // 1) Opt-out her seyin onunde
  if (motor.durduruldu) {
    return {
      ...motor,
      gonder: true,
      cevap: motor.taslakCevap,
      insanaAktar: false,
      gerekceler: ['Durdurma talebi - onay beklenmeden gonderilir, kayit acilir'],
      satisKaybi: false,
      optOutKaydi: true
    };
  }

  // 2) Konusulmayacak urun anildiysa ASLA cevap verme.
  //    Uc kaynak: kanal disi (WhatsApp/Instagram katalogu),
    //    Master Matrix EXCLUDED, Master Matrix PENDING APPROVAL.
  // 🔴 Yeni bir "konusulmaz" kategorisi eklerken BU LISTEYE DE yaz.
  //    Filtre BLOKLU dese bile bu listede degilse ajan cevap gondermeye
  //    devam eder - 13.09.2026'da 'katalog-disi-urun' eklenince tam bu oldu
  //    (kritik kontrol 91/91'den 90/91'e dustu, test yakaladi).
  const KONUSULMAZ = ['kanal-disi-urun', 'motor-disi-urun', 'onay-bekleyen-urun',
                      'katalog-disi-urun'];
  // 🔴 HASTALIK ADI GECEN MESAJ - SAHIP KARARI (Ozer Yildiz, 14.09.2026):
  //
  //   "nasir, catlak izi, egzama hastalik; musteri SORABILIR.
  //    Ama 'tedavi eder' demen YASAK. Sadece URUN ONEREBILIRSIN,
  //    'bakim yapar' diyebilirsin."
  //
  // Yani yasak olan URUN ONERMEK DEGIL, TEDAVI IDDIASI kurmak.
  // Once bu dal urun onerisini tamamen kesiyordu - fazla sikiydi ve
  // musteri ihtiyacini soylemisken satis kaybediliyordu.
  //
  // Yeni davranis:
  //   · Urun + fiyat + link NORMAL sekilde gider
  //   · Cevaba "kozmetik bakim urunu" notu ZORUNLU eklenir
  //   · Insana yine aktarilir (hassas konu, insan gozu gecsin)
  //   · Tedavi fiili ("tedavi eder", "iyilestirir", "gecirir") zaten
  //     mevzuat filtresinde BLOKLU - o taraf degismedi.
  const BAKIM_NOTU = ' L\'CARLIÉ ürünleri kozmetik bakım ürünleridir; ' +
    'cildinizle ilgili bir durum için hekiminize danışmanızı öneririz.';

  const hastalikAdi = (gelenFiltre?.bulgular || [])
    .filter(b => b.tur === 'hastalik-adi' && b.sonuc === 'BLOKLU');

  const kanalDisi = (gelenFiltre?.bulgular || []).filter(b => KONUSULMAZ.includes(b.tur));
  if (kanalDisi.length) {
    // 🔴 SATISTAKI URUNE SESSIZ KALMA.
    // Bu urunlerin ANLATILMAMA karari duruyor, ama sitede satistalar ve
    // musteri iki tikla alabiliyor. "Ekip arkadasimiz donecek" demek
    // musteri gozunde sacma. Urun ANLATILMADAN sayfa linki verilir;
    // hicbir iddia kurulmadigi icin anlatmama karari ihlal edilmez.
    // (Satista OLMAYAN AUROLIS/NOMORE/EARCLIA bu listede yok - onlarda
    //  eskalasyon dogru davranis.)
    if (typeof satistaAnlatilmayan === 'function') {
      const su = satistaAnlatilmayan(kanalDisi.map(b => b.ifade));
      let sc = su ? satisLinkiCevabi(su, SITE) : null;

      // 🔴 BU CEVAP DA FILTREDEN GECMELI.
      // Bu dal 'gonder: true' ile erken return ettigi icin asagidaki
      // taslak filtresine HIC ugramiyordu - denetimde bulundu.
      // Urun ADININ gecmesi burada BILEREK serbest (musteri zaten o urunu
      // adiyla sordu, biz sadece kendi sayfasina yonlendiriyoruz), o yuzden
      // yalnizca kanal/katalog kurallari muaf tutulur; diger her kural gecerli.
      // 🔴🔴 BU KONTROL OLU KOD - 15.09.2026'da denetimde bulundu.
      //
      // 'mevzuatFiltresi' bu dosyada NE tanimli NE require ediliyor
      // (tek require: ./urunler.js). Filtre AYRI bir workflow'da calisiyor.
      // Yani 'typeof mevzuatFiltresi === "function"' HER ZAMAN false:
      // bu blok hic calismiyor, ve alttaki 'return' taslak filtresi
      // dugumune ugramadan erken cikis yaptigi icin bu cevap CANLIDA
      // denetlenmeden gidiyor.
      //
      // 🔴 NEDEN OLDUGU GIBI BIRAKILDI:
      // Once "taslaga birak, filtre dugumu baksin" diye degistirildi -
      // ama o yol 'gonder' uretmedigi icin VIREON/FEMISIA/SOFTGUARD
      // sorulari satis sayfasi linki yerine genel "ekip donus yapacak"
      // cevabina dustu. Yani musteri kaybi. Canli testte goruldu ve
      // geri alindi.
      //
      // Risk bunun yerine YAYINLAMA ANINDA kapatildi: 'test-sablon.js'
      // artik tum SATISTA_ANLATILMAYAN metinlerini mevzuat filtresinden
      // geciriyor. Metin, slug veya urun adi degisirse test kirmizi olur
      // ve YAYIN DURUR - yani denetlenmemis metin canliya hic cikamaz.
      // Calisma anindaki acik kapi, yayin anindaki kapali kapiya cevrildi.
      // Filtre bu dosyada yok (ayri workflow'da). Burada calistirmaya
      // calismak yerine risk YAYINLAMA ANINDA kapatiliyor - asagiya bak.
      if (sc && typeof mevzuatFiltresi === 'function') {
        const MUAF = ['kanal-disi-urun', 'motor-disi-urun', 'onay-bekleyen-urun',
                      'katalog-disi-urun', 'ilac-karinesi-bileseni'];
        const kontrol = mevzuatFiltresi(sc, { kaynak: 'taslak' });
        const kalan = (kontrol.bulgular || [])
          .filter(b => b.sonuc === 'BLOKLU' && !MUAF.includes(b.tur));
        if (kalan.length) {
          gerekceler.push('Satista-anlatilmayan cevabi filtreye takildi (' +
            kalan.map(b => b.ifade).join(', ') + ') - gonderilmedi');
          sc = null;
        }
      }

      if (sc) {
        gerekceler.push('Satista olan ancak anlatilmayan urun soruldu (' +
          su.ad + ') - urun anlatilmadan sayfa linki verildi, insana da aktarildi');
        // 🔴 'gerekce' (tekil, metin) DEGIL 'gerekceler' (dizi).
        // Tuketiciler dizi bekliyor (build-akis-workflow.js:46,
        // build-whatsapp-workflow.js:91); tekil yazilinca panel satirinda
        // eskalasyonun GEREKCESI BOS kaliyordu - hem de tam olarak
        // "asla anlatilmaz" kurali olan urunlerde, yani ispat kaydinin
        // en cok gerektigi yerde.
        return {
          ...motor, gonder: true, cevap: sc, insanaAktar: true,
          gerekceler, satisKaybi: false, optOutKaydi: false
        };
      }
    }

    gerekceler.push('Musteri konusulmayacak urun sordu (' +
      kanalDisi.map(b => b.tur + ':' + b.ifade).join(', ') +
      ') - otomatik cevap verilmez, urun adi tekrarlanmaz');
    return {
      ...motor, gonder: false, cevap: null, insanaAktar: true,
      gerekceler, satisKaybi: true, optOutKaydi: false
    };
  }

  // 3) Gelen mesajda saglik/iddia icerigi varsa insan kontrolu
  if (gelenFiltre && gelenFiltre.sonuc === 'BLOKLU') {
    insanaAktar = true;
    gerekceler.push('Gelen mesajda riskli icerik: ' +
      (gelenFiltre.bulgular || []).map(b => b.tur).join(', '));
  }

  // 4) Taslak cevap yoksa zaten insana gidiyor
  if (!cevap) {
    gerekceler.push(motor.not || 'Otomatik cevap sablonu yok');
    return {
      ...motor, gonder: false, cevap: null, insanaAktar: true,
      gerekceler, satisKaybi: true, optOutKaydi: false
    };
  }

  // 5) Taslak cevap mevzuat filtresinden gecmeli
  //
  // 🔴 FAIL-CLOSED: filtre YOKSA da gonderilmez.
  // Onceki hali `if (taslakFiltre && ...)` idi: filtre null/undefined
  // gelirse kontrol TAMAMEN atlaniyor ve cevap denetlenmeden gidiyordu
  // (fail-open). n8n'de taslak filtresi node'u bos donerse ayni sonuc.
  // Denetlenmemis cevap, denetimden kalmis cevaptan daha tehlikelidir.
  if (motor && motor.taslakCevap && !taslakFiltre) {
    gerekceler.push('TASLAK FILTRESI CALISMADI - denetlenmemis cevap gonderilmez');
    return {
      ...motor, gonder: false, cevap: null, insanaAktar: true,
      gerekceler, satisKaybi: true, optOutKaydi: false
    };
  }
  if (taslakFiltre && taslakFiltre.sonuc !== 'TEMIZ') {
    gerekceler.push('URETILEN CEVAP FILTREDEN GECMEDI (' + taslakFiltre.sonuc + '): ' +
      (taslakFiltre.bulgular || []).map(b => b.tur + ':' + b.ifade).join(', '));
    return {
      ...motor, gonder: false, cevap: null, insanaAktar: true,
      gerekceler, satisKaybi: true, optOutKaydi: false
    };
  }

  // 6) Saglik sinifinda cevap gonderilir AMA insan da bilgilendirilir
  if (motor.sinif === 'SAGLIK') {
    gerekceler.push('Saglik sorusu - standart cevap gonderildi, insan bilgilendirildi');
    return {
      ...motor, gonder: true, cevap, insanaAktar: true,
      gerekceler, satisKaybi: false, optOutKaydi: false
    };
  }

  // 7) Temiz akis
  gonder = true;
  gerekceler.push('Temiz - otomatik gonderilebilir');

  // 🔴 Musteri hastalik/durum adi yazdiysa urun onerisi GIDER ama yanina
  // "kozmetik bakim urunu + hekime danisin" notu ZORUNLU eklenir ve insan
  // da devreye alinir. Tedavi iddiasi kurulmaz - o zaten filtrede bloklu.
  if (hastalikAdi.length && cevap && cevap.indexOf('kozmetik bakım ürünleridir') === -1) {
    cevap = cevap + '\n' + BAKIM_NOTU.trim();
    insanaAktar = true;
    gerekceler.push('Hastalik/durum adi gecti (' +
      [...new Set(hastalikAdi.map(b => b.ifade))].join(', ') +
      ') - urun onerildi, bakim notu eklendi, insana da aktarildi');
  }

  return {
    ...motor, gonder, cevap, insanaAktar,
    gerekceler, satisKaybi: false, optOutKaydi: false
  };
}

module.exports = { akisMotoru, kararVer, SABLON, siniflandir, durdurmaMi, SITE };
