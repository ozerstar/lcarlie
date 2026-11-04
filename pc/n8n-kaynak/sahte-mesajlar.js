// Gercek musteri mesaji simulasyonu.
// Kucuk harf, noktalama yok, yazim hatasi, kisaltma - insanlar boyle yaziyor.
// [beklenenSinif, mesaj]  ·  beklenenSinif null ise "bilmiyorum, gorelim"

module.exports = [
  // ---------- SELAMLAMA ----------
  ['SELAMLAMA', 'merhaba'],
  ['SELAMLAMA', 'slm'],
  ['SELAMLAMA', 'selam kolay gelsin'],
  ['SELAMLAMA', 'iyi günler'],
  ['SELAMLAMA', 'gunaydin'],
  ['SELAMLAMA', 'merhabalar'],
  ['SELAMLAMA', 'iyi akşamlar'],

  // ---------- FIYAT ----------
  ['FIYAT', 'fiyat'],
  ['FIYAT', 'fiyati ne kadar'],
  ['FIYAT', 'bu kaç para'],
  ['FIYAT', 'kaç tl'],
  ['FIYAT', 'ne kadar acaba'],
  ['FIYAT', 'hydravie kac lira'],
  ['FIYAT', 'ücreti nedir'],
  ['FIYAT', 'indirim var mı'],
  ['FIYAT', 'kampanyanız var mı'],
  ['FIYAT', 'fiyat listesi alabilir miyim'],
  ['FIYAT', 'sunacnea fiyat'],
  ['FIYAT', 'luciderm ne kadar'],
  ['FIYAT', 'toptan fiyat verir misiniz'],

  // ---------- SIPARIS ----------
  ['SIPARIS', 'nasıl sipariş verebilirim'],
  ['SIPARIS', 'satın almak istiyorum'],
  ['SIPARIS', 'nereden alabilirim'],
  ['SIPARIS', 'sipariş vermek istiyorum'],
  ['SIPARIS', 'kapıda ödeme var mı'],
  ['SIPARIS', 'stok var mı'],
  ['SIPARIS', 'eczanelerde satılıyor mu'],
  ['SIPARIS', 'magazaniz var mi'],
  ['SIPARIS', 'bayilik veriyor musunuz'],
  ['SIPARIS', 'sepete ekledim ama ödeme yapamadım'],

  // ---------- KARGO ----------
  ['KARGO', 'kargo ne zaman gelir'],
  ['KARGO', 'kaç günde gelir'],
  ['KARGO', 'kargom nerede'],
  ['KARGO', 'takip numarası alabilir miyim'],
  ['KARGO', 'teslimat ne kadar sürüyor'],
  ['KARGO', 'kargo ücreti var mı'],
  ['KARGO', 'bugün kargoya verilir mi'],
  ['KARGO', 'ürünüm elime ulaşmadı'],

  // ---------- ICERIK ----------
  ['ICERIK', 'içeriği nedir'],
  ['ICERIK', 'içindekiler neler'],
  ['ICERIK', 'paraben var mı'],
  ['ICERIK', 'vegan mı'],
  ['ICERIK', 'hayvan deneyi yapıyor musunuz'],
  ['ICERIK', 'alkol var mi icinde'],
  ['ICERIK', 'inci listesi paylaşır mısınız'],
  ['ICERIK', 'hangi maddeler var'],
  ['ICERIK', 'kokusu var mı'],
  ['ICERIK', 'hydravie iceriginde ne var'],

  // ---------- KULLANIM ----------
  ['KULLANIM', 'nasıl kullanılır'],
  ['KULLANIM', 'günde kaç kere sürülür'],
  ['KULLANIM', 'sabah mı akşam mı'],
  ['KULLANIM', 'ne kadar sürülür'],
  ['KULLANIM', 'kullanımı nasıl'],
  ['KULLANIM', 'nasıl uygulanır'],
  ['KULLANIM', 'ne sıklıkla kullanmalıyım'],
  ['KULLANIM', 'buzdolabında saklanır mı'],

  // ---------- SAGLIK (insana + standart cevap) ----------
  ['SAGLIK', 'egzamam var işe yarar mı'],
  ['SAGLIK', 'sivilcelerime iyi gelir mi'],
  ['SAGLIK', 'hamileyim kullanabilir miyim'],
  ['SAGLIK', 'emziriyorum sakıncası var mı'],
  ['SAGLIK', 'bebeğime sürebilir miyim'],
  ['SAGLIK', 'alerjim var kullanabilir miyim'],
  ['SAGLIK', 'doktorum kullanmamı söyledi'],
  ['SAGLIK', 'cildimde kızarıklık var'],
  ['SAGLIK', 'kaşıntı yapar mı'],
  ['SAGLIK', 'sedef hastalığım var'],
  ['SAGLIK', 'mantar için kullanılır mı'],
  ['SAGLIK', 'yaram var sürebilir miyim'],
  ['SAGLIK', 'lekelerim için ne önerirsiniz'],

  // ---------- IADE ----------
  ['IADE', 'iade etmek istiyorum'],
  ['IADE', 'ürünü değiştirebilir miyim'],
  ['IADE', 'param ne zaman yatar'],
  ['IADE', 'cayma hakkımı kullanmak istiyorum'],
  ['IADE', 'yanlış ürün geldi'],
  ['IADE', 'memnun kalmadım iade'],

  // ---------- SIKAYET ----------
  ['SIKAYET', 'rezalet bir hizmet'],
  ['SIKAYET', 'kimse cevap vermiyor'],
  ['SIKAYET', 'şikayet etmek istiyorum'],
  ['SIKAYET', 'tüketici hakem heyetine gideceğim'],
  ['SIKAYET', 'ürün bozuk geldi berbat'],

  // ---------- DURDURMA ----------
  ['DURDURMA', 'mesaj istemiyorum'],
  ['DURDURMA', 'artık mesaj atmayın'],
  ['DURDURMA', 'beni listeden çıkarın'],
  ['DURDURMA', 'dur'],
  ['DURDURMA', 'rahatsız etmeyin'],
  ['DURDURMA', 'bir daha yazmayın lütfen'],

  // ---------- KANAL DISI / BLOKLU URUNLER ----------
  [null, 'vireon ne kadar'],
  [null, 'femisia hakkında bilgi'],
  [null, 'gece serisi ürünleriniz'],
  [null, 'intimblanc fiyatı'],
  [null, 'liftelle var mı'],
  [null, 'softguard spreyi'],
  [null, 'buguard kaç para'],
  [null, 'nomore roll on'],
  [null, 'earclia hakkında'],

  // ---------- ZOR / BELIRSIZ (siniflandirici sinavi) ----------
  [null, 'bilgi alabilir miyim'],
  [null, 'yardımcı olur musunuz'],
  [null, 'bu ürün hakkında'],
  [null, 'acaba'],
  [null, '?'],
  [null, 'ok'],
  [null, 'teşekkürler'],
  [null, 'sağolun'],
  [null, 'peki'],
  [null, 'tamam'],
  [null, 'anladım'],
  [null, 'bakacağım'],
  [null, 'düşüneyim'],
  [null, 'nerelisiniz'],
  [null, 'kimlersiniz'],
  [null, 'firma nerede'],
  [null, 'instagramdan gördüm'],
  [null, 'reklamınızı gördüm'],
  [null, 'arkadaşım önerdi'],
  [null, 'daha önce almıştım'],

  // ---------- KARISIK / COKLU NIYET ----------
  [null, 'merhaba hydravie ne kadar ve kargo kaç günde gelir'],
  [null, 'fiyat ve içerik bilgisi alabilir miyim'],
  [null, 'sipariş vermek istiyorum ama önce içeriğini öğrenmek istiyorum'],
  [null, 'egzamam var hangi ürünü önerirsiniz fiyatı da nedir'],

  // ---------- YAZIM HATALI ----------
  [null, 'fiyatii ne kdar'],
  [null, 'nasl kullanilir'],
  [null, 'kargoo ne zman gelir'],
  [null, 'icerigi nedr'],
  [null, 'hydravıe fıyat'],
  [null, 'sunacnea spf kac'],

  // ---------- SATIS FIRSATI ----------
  [null, 'hangi ürünü önerirsiniz'],
  [null, 'cildim kuru ne alayım'],
  [null, 'set halinde var mı'],
  [null, 'hepsini alsam indirim olur mu'],
  [null, 'hediye paketi yapıyor musunuz'],
  // =====================================================================
  // 13.09.2026 GENISLETME — 30 urunlu katalog donemi
  //
  // Eski havuz 4 urun donemindeydi; olculen %66 otomatik cevap orani
  // artik gercegi yansitmiyordu. Bu blok gercek musteri dilini taklit eder:
  // urun adini yanlis yazma, "nedir" sorulari, belirti anlatimi.
  // =====================================================================

  // ---------- URUN ADIYLA FIYAT (yeni 26 urun) ----------
  ['FIYAT', 'dermabed kac para'],
  ['FIYAT', 'lipvora fiyat'],
  ['FIYAT', 'menthalis ne kadar'],
  ['FIYAT', 'kinesis kac tl'],
  ['FIYAT', 'dorsivia fiyati'],
  ['FIYAT', 'oragarde kac para'],
  ['FIYAT', 'babysol ne kadar'],
  ['FIYAT', 'bright smile fiyati'],
  ['FIYAT', 'seralimbo kac lira'],
  ['FIYAT', 'optywave fiyat nedir'],
  ['FIYAT', 'dermaguard ucreti'],
  ['FIYAT', 'calmoris kac para'],

  // ---------- "NEDIR" / TANITIM (eskiden genel cevap aliyordu) ----------
  [null, 'dermabed nedir'],
  [null, 'lipvora ne ise yarar'],
  [null, 'oragarde hakkinda bilgi alabilir miyim'],
  [null, 'menthalis ne ise yarar'],
  [null, 'babydent nedir'],
  [null, 'dermanova ne ise yarar'],
  [null, 'kinesis hakkinda bilgi'],
  [null, 'easycomb nedir'],

  // ---------- ICERIK ----------
  ['ICERIK', 'dermabed icinde ne var'],
  ['ICERIK', 'optywave icerigi'],
  ['ICERIK', 'babysol hangi maddeler'],
  ['ICERIK', 'lipvora icerik listesi'],

  // ---------- KULLANIM ----------
  ['KULLANIM', 'dermaguard nasil kullanilir'],
  ['KULLANIM', 'seralimbo gunde kac kez'],
  ['KULLANIM', 'dorsivia nasil surulur'],
  ['KULLANIM', 'minisooth ne zaman kullanilir'],

  // ---------- URUN ADI YANLIS YAZIM ----------
  ['FIYAT', 'dermabet fiyat'],
  ['FIYAT', 'lip vora kac para'],
  [null, 'menthalis mi mentalis mi'],
  ['FIYAT', 'brightsmile kac para'],

  // ---------- BELIRTI ANLATIMI (eskale edilmeli) ----------
  [null, 'ayagimda catlak'],
  [null, 'topugumda kuruluk var'],
  [null, 'cildimde kizariklik oluyor'],
  [null, 'dirsegimde pullanma'],
  [null, 'sacim dokuluyor ne yapmaliyim'],
  [null, 'bacagimda odem var'],

  // ---------- URUN ARAMA (eskale EDILMEMELI - satis sorusu) ----------
  [null, 'catlak topuk icin krem var mi'],
  [null, 'kuruluk icin ne onerirsiniz'],
  [null, 'ayak bakimi icin urun'],
  [null, 'bebek icin guvenli urununuz var mi'],
  [null, 'hangi urunu almaliyim'],

  // ---------- COCUK / HASSAS GRUP (eskale edilmeli) ----------
  [null, 'kizima surebilir miyim'],
  [null, 'oglumun cildine uygun mu'],
  [null, 'hamileyim kullanabilir miyim'],

  // ---------- SIPARIS / TICARI ----------
  ['SIPARIS', 'dermabed siparis vermek istiyorum'],
  ['SIPARIS', 'uc urunu birden alabilir miyim'],
  ['SIPARIS', 'kapida odeme var mi'],
  ['KARGO', 'siparisim ne zaman gelir'],
  ['IADE', 'iade sarti nedir'],

  // ---------- KANAL DISI (eskale edilmeli) ----------
  [null, 'vireon nedir'],
  [null, 'femisia fiyat'],
  [null, 'softguard kac para'],
  [null, 'liftelle hakkinda'],
];
