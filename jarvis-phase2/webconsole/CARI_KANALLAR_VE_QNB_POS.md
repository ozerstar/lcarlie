# Cari — e-ticaret, fatura, BasitKargo ve QNB POS

24 Ekim 2026 tarihli kapsam: Trendyol, n11, Amazon, Hepsiburada, Wix,
BasitKargo ve QNB fizikî POS kayıtlarının isimleriyle tek cari ekranında
izlenmesi; sipariş-müşteri-fatura-gönderi-tahsilat bağlantısı.

## Hazırlanan kod ve henüz bağlanmayan servisler

**Kodlandı:** yedi ayrı kaynak kartı, mağaza/hesap kimliği, müşteri adı,
sipariş/işlem kimliği, fatura numarası/UUID, fatura durumu, platforma aktarım
durumu, kontrol kuyruğu, açık sipariş-kargo/POS bağlantısı. Kaynak gözlemleri
PostgreSQL'de değiştirilmeyen olaylar olarak saklanır. Aynı kaynak olayı ikinci
kez yazılmaz; eski tarihli bir güncelleme daha yeni sipariş durumunu ezmez.

**Henüz kurulmadı:** gerçek pazaryeri API istemcileri ve sürekli veri çekimi,
mağaza kimlik/erişim yapılandırması, e-belge programı bağlantısı, QNB fizikî
POS rapor servisi veya cihaz entegrasyonu. Kartlar bu nedenle "canlı bağlantı
doğrulanmadı" gösterir. Birkaç kayıt alınması sürekli bağlantı kanıtı sayılmaz.
Kod bu oturumda canlı sunucuya dağıtılmadı.

Kaynak aktarımı cari bakiyeye otomatik satış yazmaz. Sipariş, fatura,
pazaryerinden alacak, müşterinin ödediği tutar ve bankaya yatan tutar için
doğrulanmış muhasebeleştirme eşleştirmesi ayrı geliştirilecektir.

## Kaynaklar nasıl birleştirilecek?

| Kaynak | Kendi kimliği | Cari/fatura ekranındaki görev |
|---|---|---|
| Trendyol | Satıcı/mağaza + sipariş/paket kimliği | Alıcı ve sipariş; fatura var mı, aktarılmış mı? |
| n11 | Mağaza + sipariş kimliği | Alıcı ve sipariş; fatura ve gönderim kontrolü |
| Amazon | Satıcı + ülke/pazaryeri + sipariş/sevkiyat kimliği | Sipariş, sevkiyata bağlı fatura ve ülke/program kapsamı |
| Hepsiburada | Merchant + sipariş/paket kimliği | Sipariş, paket ve fatura aktarım kontrolü |
| Wix | Site/mağaza + sipariş kimliği | Site alıcısı, sipariş ve e-belge eşleştirmesi |
| BasitKargo | Firma/hesap + gönderi kimliği | Hangi kaynak siparişin gönderisi olduğu; teslim/iade bilgisi |
| QNB POS | Üye işyeri/terminal hesabı + benzersiz işlem kimliği | Onaylanan/iptal/iade ödeme gözlemi ve bağlı satış |

Her mağaza kendi `store_id` ve görünen adına sahiptir. Aynı sipariş numarası
başka mağazada veya pazaryerinde tekrar edebilir; kaynak+mağaza+kimlik birlikte
anahtardır. Aynı müşteriyi farklı platformlarda yalnız isimle birleştirmek
doğru değildir. Müşteri adı kaynaktan gelmezse ekran bunu açıkça gösterir.

BasitKargo'dan gelen gönderi, Wix/Trendyol siparişine kimliğiyle bağlanır.
Bu ilişki ikinci satış, ikinci ciro veya ikinci müşteri borcu oluşturmaz.
QNB POS'ta görülen tahsilat da aynı şekilde ilişkilendirilir. Tutar ve isim
benzerliği otomatik eşleştirme için yeterli sayılmaz.

## Fatura takibi

Fatura bilgisi **doğrulanmadı / eksik / taslak / düzenlenmiş / iptal** olarak
tutulur. Fatura düzenlenmesi ile platforma aktarılması ayrı durumlardır.
Aktarım **doğrulanmadı / bekliyor / aktarılmış / reddedilmiş / uygulanmıyor**
olabilir. Faturanın nerede üretildiği ayrıca kaydedilebilir.

Kontrol listesi; doğrulanmamış veya eksik belgeyi, taslağı, aktarım sorunu
bildirilen belgeyi, farklı sipariş/fatura tutarını ve iptal/iade siparişine
bağlı düzenlenmiş faturayı işaretler. Tutar farkı, kısmi fatura veya farklı
paket kapsamından kaynaklanabileceği için doğrudan hata ilan edilmez.

Bölünmüş teslimlerde, sağlayıcının fatura birimi sipariş mi paket/sevkiyat mı
önce doğrulanmalıdır. Gözlem kimliği o birimi temsil etmelidir. Birden çok
paketin faturası tek belge varmış gibi kapatılmamalıdır. Kargo hizmetinin
gider faturası da müşteri satış faturasından ayrı tedarikçi belgesidir.

Platformda fatura bağlantısı paylaşabilmek, faturanın o platform tarafından
üretildiği anlamına gelmez. Gerçek belge programı/özel entegratör ve bu
programın belge kimliği bağlanmalıdır. Kullanıcı 24 Ekim 2026 tarihinde
**Mikro Yazılım** kullandığını bildirdi. Ürün, sürüm ve kurulum türü henüz
bilinmiyor; Mikro bağlantısı kodlanmış veya etkin kabul edilmez.

### Mikro Yazılım bağlantısı — planlanan kapsam

Mikro, muhasebe/e-belge kaynağı olarak bağlanacak; sekizinci satış kanalı
sayılmayacak. İlk aşamada mevcut faturanın numarası, belge kimliği, durumu
ve erişilebilen PDF'si ilgili pazaryeri/Wix siparişine bağlanacak. Fatura
varlığı, GİB belge durumu, platforma yükleme ve ödeme birbirinden ayrı
izlenecek. Siparişin yeniden gelmesi ikinci fatura veya ikinci cari hareket
oluşturmayacak. Mikro cari kodu ile Jarvis cari kimliği açıkça eşlenecek.

Resmî Mikro API portalında cari, fatura, tahsilat/tediye, fatura PDF ve
e-belge durum sorgulama metotları bulunuyor. Portal V16, V17 ve JumpBulut
için ayrı kaynaklar sunuyor. Bu, kullanıcının lisansında ilgili metotların
açık olduğu veya tüm sürümlerde aynı çalıştığı anlamına gelmez.

Bağlantı öncesinde Mikro ürün adı (Run/Jump/Fly veya kullanılan diğer ürün),
tam sürüm, bulut/yerel kurulum ve API erişim kapsamı doğrulanacak. İlk adım
belge okuma ve eşleştirme olacak. Yeni fatura üretimi/GİB'e gönderim ayrı
işlem akışıdır; salt takip bağlantısı bu yetkileri kendiliğinden açmaz.
QNB fizikî POS hareketlerine erişim, Mikro kullanımıyla doğrulanmış olmaz;
cihaz modeli ve banka/üretici erişimi ayrıca belirlenir.

## Mevcut kaynakta görülen altyapı

İncelenen Jarvis sürümünde Wix sipariş aynası ve BasitKargo istemcisi var.
Satış merkezi, Trendyol ürün verisi bulunmasına rağmen Trendyol sipariş
aktarımı bulunmadığını açıkça belirtiyor. n11/Amazon/Hepsiburada sipariş
istemcileri bu incelemede görülmedi. Bu, canlı hesaplarda veri olmadığı
anlamına gelmez; mevcut kod ve canlı bağlantı ayrı doğrulanmalıdır.

Mevcut entegratörün güncel mağaza bağlantıları varsa tekrar kullanılabilir;
önce kapsam ve erişim kontrol edilir. Panel şifresi veya API anahtarı bu
belgeye, koda ya da sohbet mesajına eklenmez.

## QNB fizikî POS: araştırma sonucu

QNB, Mobil Üye İşyeri İşlemleri üzerinden ciro; İnternet Şubesi üzerinden
işyeri bilgisi, ekstre ve çalışma koşullarına erişim sunduğunu belirtiyor.
Bu bilgi, cihazdan Jarvis'e anlık olay akışı bulunduğunu tek başına doğrulamaz.

QNB'nin yazarkasa POS sayfasında farklı marka ve modeller listeleniyor.
Mevcut cihazın marka/modeli ve fizikî POS mu, yazarkasa POS mu olduğu
netleşmeden cihaz entegrasyonu seçilemez. QNBpay veya Sanal POS kullanımı da
ayrı ürün olarak belirlenmelidir; yalnız QNB markasına bakarak servis seçilmez.

Kamuya açık resmî sayfalarda, bu işyerinin fizikî terminal satışlarını
saniyesinde Jarvis'e iletecek genel bir webhook/API erişimi doğrulanamadı.
Doğrudan veri aktarımının ve gecikmesinin banka/cihaz sağlayıcısıyla
doğrulanması gerekir. Sanal POS için yayımlanan entegrasyon belgesi,
fizikî terminale uygulanacak erişim sözleşmesini tanımlamıyor.

Uygulanabilecek yollar, **doğrulama bekleyen seçeneklerdir**:

1. Bankanın üye işyeri POS hareket/raporlama servisi varsa, bu işyerine
   açtırıp kendi sunucumuzdan okumak. Veri gecikmesi ve sorgulama sınırı
   sözleşmeden/servis dokümanından belirlenir.
2. Cihaz üreticisi onaylı kasa/ECR bağlantısı sunuyorsa, yerel satış
   ekranını ödeme onayıyla bağlamak. Cihaz modeli ve üretici desteği gerekir.
3. Resmî veri erişimi sağlanana kadar doğrulanmış raporu sisteme aktarmak.
   Rapor aktarımı anlık entegrasyon diye gösterilmez.

POS onayı, para bankaya geçti demek değildir. Sonraki mutabakat aşamasında
brüt işlem, iptal/iade, komisyon, bloke ve net hesaba geçiş ayrı izlenmelidir.
Hangi ürünün kime satıldığı satış kaydından gelir; terminal ödemesi bu kayda
bağlanır. Uygulama kart numarası/CVV saklamaz.

### Banka/cihaz sağlayıcısıyla doğrulanacaklar

- Üye işyeri için fizikî POS hareket API'si, web servisi veya rapor aktarımı var mı?
- Gün içi işlemler hangi gecikmeyle geliyor; callback/webhook var mı?
- Terminal/işlem/iptal/iade kimlikleri ve benzersizlik kuralları nedir?
- Komisyon, bloke, taksit ve net ödeme ayrı alanlar olarak dönüyor mu?
- Test ortamı, erişim yetkisi ve mevcut cihaz modeli için üretici bağlantısı var mı?

Bu belgede bankaya ileti gönderilmedi; cihaz ayarı veya bankacılık izni değiştirilmedi.

## Birincil teknik kaynaklar

24 Ekim 2026 tarihinde incelenen kaynaklar:

- Mikro resmî API portalı (V16/V17/JumpBulut kaynakları):
  https://apidocs.mikro.com.tr/
- Mikro metot kataloğu (cari, fatura, tahsilat/tediye, e-belge):
  https://apidocs.mikro.com.tr/apis
- Mikro e-belge durum sorgulama:
  https://apidocs.mikro.com.tr/apis/e-fatura-islemleri/paths/~1api~1apimethods~1ebelgedurumsorgulamav2/post
- QNB POS ve üye işyeri hizmetleri:
  https://www.qnb.com.tr/isim-icin/kobi/kobi-pos-cozumleri/pos
- QNB yazarkasa POS marka/model bilgileri:
  https://www.qnb.com.tr/isim-icin/kobi/kobi-pos-cozumleri/yazar-kasa-pos
- QNB Sanal POS entegrasyon belgesi sayfası:
  https://vpos.qnbfinansbank.com/Help/apiIntegrationDocument
- n11 satıcı faturası bağlantısı dokümanı:
  https://developer.n11.com/documentation/n11-siparis-entegrasyonu/fatura-linki-gonderme/
- Hepsiburada resmî entegrasyon portalı:
  https://developers.hepsiburada.com/tr/companies/hepsiburada
- Amazon SP-API fatura programları (ülke ve program uygunluğu ayrıca kontrol edilmeli):
  https://developer-docs.amazon/sp-api/lang-en_us/docs/create-and-upload-invoices

## Geliştirici notu

`045_cari_source_events.sql`, mevcut `044_cari_ledger.sql` sonrasında uygulanır.
`cari_channels.py` sağlayıcıdan bağımsız gözlem katmanıdır; sağlayıcı API
istemcisinin yerini almaz. GET `/api/cari/channels` panel verisini döndürür.
POST `/api/cari/channels/observe` mevcut oturum/CSRF sınırında tek kanonik
gözlem kabul eder. Gerçek bağlayıcı bu alanları resmî API/rapordan eşlemelidir.

Zorunlu alanlar: `source`, `store_id`, `object_id`, `event_key`, `currency`,
`source_updated_at` (saat dilimiyle). `gross_amount` varsa ondalık metindir;
eksik tutar sıfır kabul edilmez. `invoice.status` düzenlenmişse numara veya
belge kimliği gerekir. Finansal kayıt veya dış fatura üretimi burada yapılmaz.

QNB POS ve BasitKargo gözlemleri `order_link` içinde siparişin kaynak,
mağaza ve kimliğini açıkça taşır. Cari eşleştirmesinde `account_id` verilirse
aynı kullanıcıya ait bir cari olmalıdır. Gizli erişim bilgileri, tam kart
verileri ve serbest ham sağlayıcı yanıtı bu kanonik kayda alınmaz.
