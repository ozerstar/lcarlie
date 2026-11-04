# L’CARLIÉ Jarvis — Cari hesabın geliştirme ve entegrasyon planı

Amaç: bir kişi veya firma için **ürün, para, belge ve görüşme geçmişini aynı
yerden takip etmek**. Eczane, bayi, saha müşterisi, tedarikçi ve konsinye noktası
aynı yapıda izlenir. Finans hesabı ayrı hesap tablolarından elle birleştirilmez;
onaylı hareketlerin geçmişinden hesaplanır.

Bu belge hedef tasarımdır. Aşağıda geliştirildiği belirtilen kod da henüz canlı
sunucuya kurulmuş değildir. Entegrasyon adayı bulunan bölüm ile çalışan bağlantı
aynı şey değildir.

## 1. Şu anda hazırlanmış çekirdek

- Cari kartı; müşteri, tedarikçi veya iki rol birlikte.
- Ürün verdik/aldık, alış/satış iadesi, bedelsiz teslim.
- Tahsilat, ödeme, açılış bakiyesi; satır bazında fiyat/iskonto/KDV.
- Önizleme sonrası kayıt, teknik tekrarları engelleme, değiştirilmeyen tarihçe.
- Gerekçeli ters kayıtla düzeltme; ekstre ve ürün hareketlerinin birlikte görünümü.
- Yazdır/PDF ve CSV düğmeleri; masaüstü ve mobil menülerinden ortak ekran.
- **Yeni finans özeti:** rapor tarihine göre toplam alacak, toplam borç, girilmiş
  tahsilat ve ödemeler. Farklı carilerdeki borç ve alacak birbirini kapatmaz.
- KDV belirsizliği uyarısı; vadesi geçmiş tarihli belgeler için kontrol listesi.
  Ödeme-belge eşleştirmesi bulunmadığından bu liste "kesin ödenmemiş fatura"
  veya "kesin gelecek para" olarak sunulmaz.

## 2. Eklenecek modüller

| Modül | Kullanıcının yapacağı iş | Birleşeceği bölüm | Öncelik |
|---|---|---|---|
| Birleşik cari kartı | İletişim, firma/şube, ilgili kişi, cari türü, ödeme koşulu, ziyaret ve belgeleri aynı kartta görmek | Müşteri kartı, saha, satış | 1 |
| Ürün ve fiyat seçimi | Ürünü listeden seçmek; cariye özel fiyatı, iskontoyu ve geçerlilik tarihini görmek | Katalog, bayi fiyatı, fiyat matrisi | 1 |
| Teklif → sipariş → teslim | Teklif vermek, kabul edilen miktarı siparişe çevirmek, kısmi teslimi işlemek | Satış merkezi, kargo, cari | 1 |
| Ödeme-belge eşleştirme | Gelen paranın hangi satışları kapattığını seçmek; kısmi tahsilatı ve avansı ayırmak | Cari hareket, banka/kasa | 1 |
| Vade ve tahsilat planı | Gerçek açık tutarı; bugün, 7/30 gün içinde veya gecikmiş vadeleri görmek | Eşleştirme, görevler, finans özeti | 1 |
| Depo ve ürün hareketi | Depo/şube bazında giriş, çıkış, rezervasyon, kısmi teslim ve sayım farkını görmek | Sipariş, teslim, mevcut stok sayımı | 2 |
| Lot, SKT ve izlenebilirlik | Hangi parti ürünün kime gittiğini; yaklaşan SKT ve bloke iadeleri izlemek | Depo, ürün, müşteri/iade | 2 |
| İade ve değişim | İade talebi, fiziksel kabul, bedel düzeltmesi ve para iadesini ayrı izlemek | Müşteri, depo, cari, kargo | 2 |
| Konsinye | Noktaya emanet bırakılan, satılan, geri alınan ve hâlâ orada duran ürünleri görmek | Depo lokasyonu, bayi, cari | 2 |
| Banka/kasa ve dekont | Havale, kart, nakit ve POS hareketlerini içeri alıp cariye eşleştirmek | Tahsilat, ödeme, belge arşivi | 2 |
| Belge/dekont arşivi ve okuma | Fotoğraf/PDF'den taslak çıkarmak; belgeyi ilgili cariye ve harekete bağlamak | Cari, banka, fatura, özel dosya alanı | 2 |
| Tedarikçi ve satın alma | Teklif/sipariş, mal kabul, alış belgesi, tedarikçiye borç ve ödemeyi izlemek | Depo, cari, finans | 2 |
| E-ticaret ve kanal mutabakatı | Web/pazaryeri siparişini, ödemeyi, kesintiyi ve hesabımıza yatan tutarı karşılaştırmak | Wix kaynakları, satış, banka, iade | 3 |
| Fatura ve muhasebe aktarımı | Onaylı işlemi mevcut muhasebe/e-belge sistemine aktarmak; belge durumunu geri almak | Sipariş, cari, muhasebe yazılımı | 3 |
| Karlılık ve satış performansı | Net satıştan ürün maliyeti, iskonto, iade, komisyon ve kargoyu düşerek sonucu görmek | Maliyet, satış, banka, dağıtım | 3 |
| PR, numune ve etkinlik dağıtımı | Kime ne verildiğini, maliyetini ve etkinlik/iş birliği amacını izlemek | Dağıtım, pazarlama, depo, saha | 2 |
| Saha ekibi ve prim | Ziyaret, sipariş ve tahsilatı temsilciyle ilişkilendirmek; tanımlı kurala göre prim taslağı görmek | Saha, satış, tahsilat, iade | 3 |
| Jarvis finans asistanı | Cari sorgulamak; gecikmeyi, eksik dekontu, eşleşmeyen ödemeyi ve riskli yoğunlaşmayı özetlemek | Yetkili raporlar, görevler, hatırlatmalar | 3 |

Modüller, tüm ekranlar bir kerede büyütülerek değil, doğru hareket ve kimlik
bağlantıları kurularak eklenir. İlk hedef **cari + ürün/fiyat + satış + tahsilat
eşleştirmesi** olmalıdır. Sağlam açık-tutar verisi olmadan vade alarmı veya nakit
akışı tahmini açılmaz.

## 3. En önemli iş kuralları

### Ürün çıkışı ve alacak aynı olay değildir

Teklif para alacağı yaratmaz. Sipariş, stok rezervasyonu yaratabilir; rezervasyon
fiziksel ürün çıkışı değildir. Teslim edilen ürünün satış, numune, hediye veya
konsinye olmasına göre finans etkisi değişir. Faturalama/alacak doğurma anı
işletmenin seçtiği belge akışına bağlanmalı; her durum değişikliğinde tekrar
satış yazılmamalıdır.

Konsinye ürünü müşteriye emanet bırakmaktır: normal satış veya bedelsiz hediye
olarak kaydedilmez. Ürün şirket mülkiyetinde, farklı lokasyonda izlenir. Satış
bildirimi ve mutabakat sonrası ilgili miktarın cariye yansıması oluşturulur.

### İade tek düğmeyle üç ayrı gerçeği varsaymamalı

Ürünün geri gelmesi, fiyat düzeltmesi ve paranın müşteriye dönmesi farklı
durumlardır. Gelen ürün karantinaya alınabilir; satılabilir stoka otomatik
konulmaz. Para iadesi varsa ayrıca ödeme hareketi kaydedilir. Sadece kargo
durumu değiştiği için finans hesabı kapatılmaz.

### Tahsilatın nereye mahsup edildiği belli olmalı

Bir tahsilat birden fazla belgeye bölünebilir; bir belge de birden fazla
tahsilatla kapanabilir. Avans ve henüz eşleşmeyen tutar ayrıca tutulur.
Eşleşen toplam tutar ödeme veya belge tutarını aşamaz. Yanlış eşleştirme
geri alınabilir olmalı; geri alma finansal hareketi silmemelidir.

Belirsiz KDV, belgenin kesin kapanışını doğrulamayı engeller. Farklı para
birimleri eklenirse kur, tarih ve kur farkı ayrı kaydedilir; farklı dövizler
doğrudan tek tutarda toplanmaz. Mevcut çekirdek yalnız TRY destekler.

### Bir işlemin tüm sistemde tek kimliği olmalı

Sipariş, banka tahsilatı, kargo teslimi ve cari belgesi ayrı kaynak olaylarıdır.
Aynı kaynak olayı yeniden gelirse ikinci hareket oluşmaz. İsim veya tutar
benzerliği tek başına otomatik birleştirme nedeni değildir.

Örneğin zaten ödenmiş bir Wix siparişi içeri alınırken satışla birlikte gerçek
ödeme bilgisi de ele alınır. Aynı siparişi hem elle hem platform kaynağından
tekrar işlemek alacağı ve ciroyu iki katına çıkarmamalıdır. Kargo kapıda ödeme
bedeli de banka tahsilatıyla mükerrer yazılmamalıdır.

## 4. Çağrı üzerinden örnek kullanım

1. Çağrı cari kartı açılır. İlgili kişi, varsa firma/şube ve fiyat koşulu seçilir.
2. Ürünler katalogdan seçilir. Ekran adet, fiyat, iskonto ve KDV durumunu gösterir.
3. Onaylanan ürün tesliminin belgesi kaydedilir; cari hareket aynı belgeye bağlanır.
4. Para geldiğinde dekont/tahsilat eklenir ve hangi belgelere ait olduğu seçilir.
5. İade varsa asıl satışa bağlanır; fiyat ve toplam iade miktarı o satıştan doğrulanır.
6. Cari kartta verilen/alınan ürünler, açık belgeler, ödeme geçmişi ve vade görünür.
7. Ekstre paylaşımı için çıktı hazırlanır. Mesajın gönderilmesi ayrıca kullanıcı
   talebine bağlıdır; otomatik WhatsApp/e-posta gönderimi bu planla açılmaz.

## 5. Kaynakta doğrulanan entegrasyon adayları

Bu kayıtlar incelenen kaynak sürümüne aittir; canlı sunucuda mevcut oldukları
veya güncel veri döndürdükleri bu oturumda doğrulanmamıştır.

| Mevcut kaynak | Sağladığı dayanak | Cariyle birleşme şekli |
|---|---|---|
| `webconsole/app.py`, `/api/musteri`, `/api/musteri/kart` | Wix müşteri kartı ve sipariş geçmişi | Cari ile alıcı kimliği arasında açık eşleştirme |
| `raw.wix_order`, `mart.siparis`, `mart.siparis_kalem` | Sipariş, ürün ve ödeme durumları | Sipariş kimliğiyle aktarım taslağı; mükerrer kaynak kontrolü |
| `mart.gonderi`, `raw.bk_shipment` | Kargo ve gelen gönderi kayıtları | Teslim/iade kanıtı; finansal olayı tek başına onaylamaz |
| `core.urun_bayi_fiyat`, `mart.bayi_fiyat_gecerli` | Bayi fiyat kademeleri ve fiyat çelişkisi | Doğrulanmış fiyatı önizlemeye getir; belgedeki fiyatı sabitle |
| `core.stok_sayim`, `mart.stok_guncel` | Fiziksel stok sayımı | Tarihli açılış/sayım dayanağı; üzerine ayrı hareket defteri |
| `core.gonderi_notu`, `mart.urun_dagitim` | Satış/numune/UGC/hediye ayrımı | Dağıtımı doğru türe bağlama; ciro ile bedelsizi karıştırmama |
| Saha ve katalog bölümleri | Ziyaret, sunum, ürün ilgisi | İlgili firma/ziyaretten teklif veya cari kartına geçiş |

Not: `jarvis/stok.py` adlı dosya depo stok modülü değil, stok fotoğrafı/arka
plan modülüdür. Depo bağlantısı için bu dosya kullanılmayacaktır.

## 6. Teknik genişleme sınırları

Kullanıcının 24 Ekim 2026 bildirimiyle muhasebe/e-belge sistemi **Mikro
Yazılım** olarak belirlendi. Ürün/sürüm/kurulum ve API erişimi doğrulanınca
önce mevcut faturaların okunması ve siparişlerle eşleştirilmesi geliştirilecek.
Mikro ayrı satış kanalı sayılmayacak; aynı satış sipariş, fatura ve tahsilat
kaynaklarından tekrar tekrar cari bakiyeye yazılmayacak. Ayrıntılı kapsam
`CARI_KANALLAR_VE_QNB_POS.md` içindeki Mikro bölümündedir. Canlı Mikro
bağlantısı ve yeni fatura üretimi henüz uygulanmadı.

Yeni modüller için tasarlanacak kayıtlar: kişi/firma ve dış kimlik eşleştirmesi;
ürün/SKU ve lot; satış/alış belgesi; fiziksel teslim; stok hareketi; tahsilat/ödeme;
belge-ödeme dağıtımı; kaynak olay bağlantısı; mutabakat; denetim olayı.

- Ürünler görünen ad yerine kalıcı ürün kimliğiyle birleşmeli; ambalaj/hacim
  farklılıkları ayrı SKU olmalıdır. Mevcut isimle girişler kontrollü eşlenir.
- Kaynak bağlantısında `(owner, sistem, kaynak_olay_id)` benzersizliği olmalı;
  aynı olay başka cariye ikinci kez bağlanamamalı.
- Mevcut hesap sahibi sınırı korunmalı. Ekip kullanımı açılacaksa ayrı şirket,
  rol ve yetki tasarımı yapılmalı; cari verileri kendiliğinden tüm operatörlere
  veya modelin genel şirket hafızasına açılmamalı.
- Para, stok adedi ve karlılık hesabı deterministik kodla yapılmalı. Jarvis
  sorgular ve açıklar; tutar veya kayıp belge uydurmaz.
- Banka ve muhasebe entegrasyonları kullanılacak sistemin gerçek belgeleri ve
  mevcut izinleri incelenmeden kodlanmış sayılmamalı.
- Tarihli rapor, kayıt anı ve kaynak olay zamanı ayrı saklanmalı. İleride
  geriye dönük mutabakat raporu üretilebilir olmalı.

## 7. Uygulama sırası ve kabul ölçütleri

**A — Operasyon çekirdeği:** cari kartı, ürün/fiyat seçimi, satış belgesi ve
ödeme dağıtımı. Kabul: kısmi ödeme, avans, iade ve yanlış eşleştirme örneklerinde
açık tutar belgeden tekrar hesaplanıyor; aynı sipariş ikinci kez yazılamıyor.

**B — Fiziksel ürün takibi:** depo hareketi, lot/SKT, konsinye ve bedelsiz
dağıtım. Kabul: şirketin deposu ve konsinye noktaları ayrı; teslim, sayım ve
iade karantinası stokta birbiriyle karışmıyor.

**C — Finans ve kanallar:** banka mutabakatı, doğrulanmış vade yaşlandırması,
e-ticaret kesintileri, muhasebe bağlantısı ve maliyet/karlılık. Kabul: sipariş
cirosu, alacak, bankaya yatan net para ve ürün maliyeti ayrı gösteriliyor.

**D — Jarvis açıklama katmanı:** "Hangi caride açık tutar var?", "Bu haftaki
vadeler neler?", "Hangi ödeme eşleşmemiş?" sorguları. Kabul: her cevap
yetkili kayıt kimliğine ve rapor tarihine dayanıyor; kullanıcı istemeden dışarı
mesaj gönderilmiyor veya finansal kayıt değiştirilmiyor.
