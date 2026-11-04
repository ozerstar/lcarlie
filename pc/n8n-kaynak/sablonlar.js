// =====================================================================
// L'CARLIE - META ONAYLI MESAJ SABLONLARI (taslak)
//
// 24 saatlik musteri hizmeti penceresi DISINDA gonderilecek her mesaj
// Meta tarafindan onaylanmis sablonla gonderilir.
//
// Kategoriler:
//   UTILITY   - islem bildirimi (siparis, kargo, iade). Genelde hizli onaylanir.
//   MARKETING - tanitim/hatirlatma. 🔴 IYS/6563 hukuk onayi olmadan ACILMAZ.
//
// {{1}}, {{2}} ... Meta'nin degisken yer tutuculari.
// =====================================================================

module.exports = [
  // ------------------------------------------------------------------
  // UTILITY - islem bildirimleri
  // ------------------------------------------------------------------
  {
    ad: 'siparis_alindi',
    kategori: 'UTILITY',
    dil: 'tr',
    govde:
      'Merhaba {{1}}, siparişiniz tarafımıza ulaştı. ' +
      'Sipariş numaranız: {{2}}. ' +
      'Hazırlanır hazırlanmaz kargo bilgilerinizi paylaşacağız. ' +
      'Siparişinizi buradan takip edebilirsiniz: {{3}}',
    degiskenler: ['Müşteri adı', 'Sipariş numarası', 'Sipariş takip linki'],
    ornek: ['Ayşe', 'LC-10234', 'https://www.lcarlie.shop/account/my-orders']
  },

  {
    ad: 'kargoya_verildi',
    kategori: 'UTILITY',
    dil: 'tr',
    // 🔴 SURE VAADI YOK: sitede "16:00 aynı gün", sozlesmede "1-7 is gunu"
    // yaziyor ve bu celiski cozulmedi. Teslim suresi TAAHHUT EDILMIYOR.
    govde:
      'Merhaba {{1}}, {{2}} numaralı siparişiniz kargoya verildi. ' +
      'Kargo takip numaranız: {{3}}. ' +
      'Takip için: {{4}}',
    degiskenler: ['Müşteri adı', 'Sipariş numarası', 'Kargo takip numarası', 'Kargo takip linki'],
    ornek: ['Ayşe', 'LC-10234', '1234567890', 'https://kargo.example/1234567890']
  },

  {
    ad: 'iade_talebi_alindi',
    kategori: 'UTILITY',
    dil: 'tr',
    govde:
      'Merhaba {{1}}, {{2}} numaralı siparişiniz için iade talebiniz alınmıştır. ' +
      'Talebiniz incelendikten sonra size dönüş yapılacaktır.',
    degiskenler: ['Müşteri adı', 'Sipariş numarası'],
    ornek: ['Ayşe', 'LC-10234']
  },

  {
    ad: 'insan_destegi_donus',
    kategori: 'UTILITY',
    dil: 'tr',
    // Ajan insana aktardiginda, 24 saat gecmisse temsilci bununla geri doner
    govde:
      'Merhaba {{1}}, mesajınızla ilgili size dönüş yapmak istedik. ' +
      'Yanıtlamanız halinde konuşmaya buradan devam edebiliriz.',
    degiskenler: ['Müşteri adı'],
    ornek: ['Ayşe']
  },

  // ------------------------------------------------------------------
  // MARKETING - 🔴 IYS / 6563 HUKUK ONAYI OLMADAN KULLANILMAZ
  // Hepsinde opt-out cumlesi var; "DUR" ajanin durdurma siniflandiricisiyla
  // birebir eslesiyor, yazan kisi aninda listeden cikar.
  // ------------------------------------------------------------------
  {
    ad: 'sepette_urun_kaldi',
    kategori: 'MARKETING',
    dil: 'tr',
    govde:
      'Merhaba {{1}}, sepetinizde tamamlanmamış bir siparişiniz görünüyor. ' +
      'Dilerseniz buradan tamamlayabilirsiniz: {{2}} ' +
      'Mesaj almak istemiyorsanız DUR yazabilirsiniz.',
    degiskenler: ['Müşteri adı', 'Sepet linki'],
    ornek: ['Ayşe', 'https://www.lcarlie.shop/cart-page']
  },

  {
    ad: 'rutin_hatirlatma',
    kategori: 'MARKETING',
    dil: 'tr',
    // Urun ADI degisken; hangi urun gonderilecegi sistemden gelir.
    // Hicbir fayda/etki iddiasi YOK - sadece hatirlatma.
    govde:
      'Merhaba {{1}}, {{2}} ürününüzü {{3}} tarihinde almıştınız. ' +
      'Yenilemek isterseniz: {{4}} ' +
      'Mesaj almak istemiyorsanız DUR yazabilirsiniz.',
    degiskenler: ['Müşteri adı', 'Ürün adı', 'Sipariş tarihi', 'Ürün sayfası linki'],
    ornek: ['Ayşe', 'HYDRAVIE El & Yüz Nemlendirici Krem',
            '12.06.2026', 'https://www.lcarlie.shop/product-page/hydravie']
  },

  {
    ad: 'uclu_rutin_tanitim',
    kategori: 'MARKETING',
    dil: 'tr',
    // 🔴 Gunes koruyucunun ADI ve SPF degeri BILEREK YOK.
    // Anilirsa mevzuat 4 zorunlu gunes ibaresinin de eklenmesini sart kosuyor
    // ve sablon okunamaz uzunluga cikiyor.
    govde:
      'Merhaba {{1}}, günlük bakım rutinimiz üç adımdan oluşuyor: ' +
      'temizleme, nemlendirme ve koruma. ' +
      'Üç adımı tek seferde almak için: {{2}} ' +
      'Mesaj almak istemiyorsanız DUR yazabilirsiniz.',
    degiskenler: ['Müşteri adı', 'Üçlü ritüel linki'],
    ornek: ['Ayşe', 'https://www.lcarlie.shop']
  }
];
