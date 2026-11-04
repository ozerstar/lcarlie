# Cari hesap modülü

Müşteri veya tedarikçi kartı açılır; verilen/alınan ürün, alış-satış iadesi,
tahsilat, ödeme ve açılış bakiyesi ayrı hareketler halinde girilir. Cari adı,
ürün fiyatı ve miktarlar kullanıcı tarafından girilir; örnek veya gerçek müşteri
verisi kaynak koduna eklenmez. Mevcut Jarvis oturumu kullanılır. Veri yalnız
mevcut PostgreSQL içinde tutulur. Fatura okuma yerel Ollama modelleri ve
Tesseract OCR kullanır; dış OCR servisine belge gönderilmez.

## Kullanım

- Masaüstü menüsü **CARİ EKSTRELER** ve mobil şirket bölümleri `/cari.html`
  sayfasını açar; aynı ekran küçük ekrana uyarlanır.
- **Yeni cari** ile kişi/firma açılır. **Hareket ekle** ile ürünler, adet,
  KDV hariç birim fiyat, iskonto, KDV oranı, işlem tarihi, vade ve belge
  numarası girilir. Tahsilat/ödeme için doğrudan tutar girilir.
- Cari özeti, beyaz zemin üzerinde mavi borç, yeşil alacak, turuncu bakiye
  ve mor durum kartlarını gösterir. Borç ve alacak bu cariye karşı kalan
  net bakiyenin yönüdür; toplam hareket hacmi hesap ekstresinde izlenir.
- Ürün tablosunda adet, iskontolu KDV hariç birim fiyat, isteğe bağlı tavsiye
  satış fiyatı ve KDV hariç satır toplamı bulunur. Tavsiye fiyatı belgeye
  sabitlenir, alacak/KDV hesabına katılmaz; eski belgelerde yoksa boş görünür.
  Satış, alış ve bedelsiz ürünler ayrı seçilir; iadeler ilgili türün toplamından
  düşülür. Ürün toplamı ile tahsilatlar sonrası hesap bakiyesi farklıdır.
- Ürün tablosunun altındaki **Teslim ve iade geçmişi**, geçerli ürün
  hareketlerini tarih, ürün, adet, yön, belge ve açıklamayla gösterir.
  Mutabakat notu açıklamaya yazılabilir; bu not imzalı mutabakat belgesi
  sayılmaz. Ters çevrilen hareketler tam hesap ekstresinde korunur.
  Tarih zorunludur; tarihi bilinmeyen bir teslim/iade için tarih uydurulmaz.
- **Hesapla ve kontrol et** kayıt yapmaz. Hesap özeti görüldükten sonra
  **Hareketi kaydet** kalıcı kayıt oluşturur. Yanıt kaybolursa aynı istekle
  tekrar denemek ikinci bir kayıt oluşturmaz.
- **Düzelt**, gerekçesi ve tarihi belirtilen ters kayıt ekler. Asıl hareket
  değişmez. Ardından doğru hareket yeniden girilebilir. Bir hareket yalnız
  bir kez ters çevrilebilir; ters kayıt tekrar ters çevrilemez.
- **Yazdır / PDF** tarayıcının yazdırma ekranını açar. Cari özeti ve ürün
  satırlarından sonra teslim/iade geçmişi yeni sayfadan devam eder.
  **CSV indir** ekstre ve satır ayrıntılarını dışa aktarır;
  metin hücrelerinde tablo formülü çalıştırılmasına karşı önlem vardır.
- **Genel cari durumu**, seçilen tarihe kadar girilmiş hareketlerden toplam
  alacak, borç, tahsilat ve ödemeyi hesaplar. Farklı cariler birbirini kapatmaz.
  Bu rakamlar banka bakiyesi veya gerçekleşeceği kesin nakit akışı değildir.
- **Yaklaşan ve geciken vadeler**, belgeye bağlanmış ödemeleri düşerek açık
  tutarı gösterir. Eşleşmemiş ödemeler ile iadeler ayrıca mutabakat gerektirir.

## Fatura ve ödeme akışı

- **Fatura aktar** JPG, PNG, WebP ve en çok 5 sayfalık PDF kabul eder (8 MB).
  Dosya PostgreSQL'de sahipliğe bağlı saklanır; aynı dosyanın tekrar faturaya
  işlenmesi engellenir. Okuma arka planda yapılır, liste 5 saniyede bir yenilenir.
- Metni olan PDF doğrudan okunur; görüntü ve taranmış PDF için `tesseract`
  (`tur+eng`) uygulanır. Yerel Ollama `qwen3:1.7b` metni, `qwen3-vl:2b`
  görselleri yapılandırılmış alanlara ayırır. Model yanıtı finansal kayıt olarak
  doğrudan kullanılmaz: taraf adları, fatura numarası, ürün adları, birim fiyat
  ve toplam belge metninde aranır; satır hesabı ile KDV ve genel toplam
  kuruş düzeyinde uyuşmalıdır. Belirsiz fatura **İnceleme** durumuna düşer.
- Doğrulanan faturada cari adıyla yeni hesap açılır veya var olan hesap bulunur.
  Ürün satırları değişmez cari hareketine yazılır. OCR'nin önerdiği vergi no,
  adres, e-posta ve telefon otomatik hesaba aktarılmaz; inceleme ekranında
  kullanıcı bunları gözden geçirerek kaydedebilir. Çağrı adına hareket otomatik
  oluşturulmaz. Fatura numarası ve dosya özeti mükerrer kaydı engeller.
- Satış/alış satırındaki **Ödeme alındı / yapıldı** düğmesi POS, havale/EFT,
  elden veya diğer yöntem ve açıklamayla tahsilat/ödeme ekler. Ödeme belirli
  belgeye bağlanır; ödenmedi, kısmi ve ödendi durumları buradan hesaplanır.
  Fazla eşleştirme reddedilir. Bağlı ödeme varken asıl belge terslenemez.
- **Taslak olarak kaydet** ürün ve ödeme hareketini bakiyeye etki etmeden
  saklar. Taslak satırları tek tek veya **Toplu iskonto** ile düzenlenir;
  **Onayla ve cari hareketine işle** tek seferlik, denetlenebilir kayıt açar.
  Onay işlemi tekrar edilirse aynı hareket döner. Taslaklar cari seçildiğinde
  hesap başlığının altında görünür.
- Ürün hareketine belge eki eklenebilir. Cari kartında vergi/kimlik numarası,
  adres, e-posta ve telefon düzenlenebilir. Ekstre tarih, ürün ve hareket türüne
  göre filtrelenebilir; CSV ve yazdır/PDF filtrelenmiş satırları kullanır.
  Genel durum eksik KDV ve fatura numaralarını listeler.

İleriki modüller ve mevcut satış, müşteri, bayi fiyatı, kargo, saha ve stok
sayımıyla entegrasyon planı `CARI_GELISTIRME_PLANI.md` içindedir.

**Kanallar ve faturalar** bölümünde Trendyol, n11, Amazon, Hepsiburada, Wix,
BasitKargo ve QNB POS ayrı kaynaklar olarak tanımlıdır. Mağaza, müşteri,
sipariş/işlem ve fatura kimliğiyle takip yapılır. Kaynak bağlantıları bu
oturumda açılmamıştır. Yeni kaynak tablosu için `045_cari_source_events.sql`
migration'ı gerekir. Teknik kapsam ve QNB araştırması
`CARI_KANALLAR_VE_QNB_POS.md` içindedir.

## Hesap kuralları

Şirket açısından pozitif bakiye alacağımız, negatif bakiye borcumuzdur.

| Hareket | Alacak etkisi | Ürün etkisi |
|---|---:|---|
| Satış | + | Verdik |
| Alış | − | Aldık |
| Müşteriden iade | − | Aldık |
| Tedarikçiye iade | + | Verdik |
| Tahsilat | − | Yok |
| Ödeme | + | Yok |
| Açılış alacağımız / borcumuz | + / − | Yok |
| Bedelsiz verdik / aldık | 0 | Verdik / aldık |

Tutarlar Python `Decimal` ile hesaplanıp PostgreSQL'e tam sayı kuruş olarak
yazılır. İskonto sonrası satır tutarı ve satır KDV'si ayrı ayrı `ROUND_HALF_UP`
ile kuruşa yuvarlanır. İstemciden gelen toplamlar kullanılmaz. Kaydedilmiş
fiyatlar belge üzerinde sabittir; başka ürün fiyatı değişiklikleri eski
hareketleri etkilemez. TRY ve tam adet ürünler desteklenir.

**KDV boş bırakılabilir fakat sıfır sayılmaz.** Böyle belgeler için bakiye
"+ belirlenecek KDV" olarak gösterilir ve uyarı çıkar. Belirsiz KDV bulunan
hesap, sayısal bakiye sıfır olsa bile "hesap kapalı" gösterilmez. KDV kesinleşince
belge ters kayıtla düzeltilip doğru oranla yeniden girilir. Bedelsiz girişler
yalnız sıfır fiyat/iskonto/KDV kabul eder; bu seçim vergisel değerlendirme yapmaz.

Ürün tablosu bu cariye ait hareketleri gösterir; toplam depo stoku veya muhasebe
fişi üretmez. İade, eski belgeyi otomatik bulup fiyatlamaz; hangi alış/satışa
dayandığı belge numarası ve açıklamada belirtilmeli, ilgili fiyatla girilmelidir.
Mükerrer kaydı önleyen anahtar teknik tekrarları önler; fatura yükleme ayrıca
dosya özeti ve cari içindeki fatura numarasını denetler. Elle hareket girişi
aynı fatura numarasını tek başına engellemez. Kayıt sahipliği mevcut oturum kullanıcısına
bağlıdır; farklı operatörlerin hesapları birbirine açılmaz.

## Kurulum

1. Mevcut kaynağı yedekleyip `migrations/044_cari_ledger.sql` ve ardından
   `migrations/045_cari_source_events.sql`, `046_cari_account_edit.sql` ve
   `047_cari_invoice_documents.sql` ve `048_cari_drafts.sql` dosyalarını var olan
   veritabanında yetkili rol ile uygulayın. Migration'lar yeni cari tabloları,
   hesap kimliği alanları ve indeksler ekler; mevcut finans verilerini değiştirmez. Uygulama migration'ı
   kendi kendine çalıştırmaz.
2. `webconsole/cari.py`, güncel `app.py` ve statik dosyaları mevcut Jarvis
   dağıtım süreciyle dağıtın; mevcut web servisini yeniden başlatın.
3. `/api/cari/accounts` isteğini girişten sonra kontrol edin. Migration veya
   PostgreSQL bağlantısı yoksa ekran `503` hatasını gösterir; sahte bakiye üretmez.

Bağlantı, zaten kullanılan `personal_action_store._connect` üzerinden mevcut
`jarvis_web` rolüyle kurulur. Sunucuda `tesseract-ocr`, `tesseract-ocr-tur`
paketleri ve belirtilen yerel Ollama modelleri gerekir. Finans hareketi
tablolarında `UPDATE`, `DELETE` ve `TRUNCATE` yetkisi yoktur; cari kimliği ve
belge durumunda sınırlı alan güncellemesi vardır. API oturum sahipliğini
sunucudan alır; POST istekleri mevcut
CSRF kapısından geçer. Kullanıcıya başka kullanıcının hesap kimliği verilse bile
okuma/yazma ve ters kayıt sorguları sahiplikle sınırlıdır.

## Doğrulama

Kaynak kökünün `jarvis-phase2` dizininde:

```bash
test_state_dir=$(mktemp -d)
JARVIS_STATE_DIR="$test_state_dir" python3 -m unittest discover -s webconsole/tests -p 'test_cari*.py' -v
JARVIS_STATE_DIR="$test_state_dir" python3 -m unittest discover -s webconsole/tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
node --check webconsole/static/cari.js
```

Gerçek PostgreSQL testleri ancak `CARI_TEST_DSN` ayarlıysa çalışır. Bu bağlantı
**yalnız disposable `jarvis_cari_test` veritabanı** olmalıdır. Test kurulumu cari
tablolarını temizler ve `jarvis_web` rolüne geçer. Üretim DSN'i asla verilmemeli;
test farklı veritabanı adında temizleme yapmayı reddeder. Migration'ın önce
bu izole veritabanında uygulanmış olması gerekir.

Kapsam: kuruş yuvarlama, KDV belirsizliği, kısmi tahsilat, iade, borç yönü,
bedelsiz ürün, ters kayıt, giriş doğrulaması, kullanıcı/CSRF sınırı; PostgreSQL
testleri ayrıca eşzamanlı tekrar, kalıcılık, sahiplik ve veritabanı yetkileri.

24 Ekim 2026 arayüz doğrulaması:

- `python3 -m unittest discover -s webconsole/tests -p 'test_*.py'`:
  386 test, OK (11 veritabanı testi standart koşuda atlandı).
- `test_cari*.py` izole PostgreSQL uyumlu PGlite/WASM üzerinde:
  59 test, OK; standart koşuda atlanan 11 test burada ayrıca geçti.
- Gerçek yerel web sunucusu ve Chromium üzerinden giriş/CSRF, cari oluşturma,
  fiyat önizlemesi, kalıcı kayıt, yenileme, kısmi tahsilat, iade/ters kayıt,
  tedarikçi borcu, yedi kaynak sekmesi, teslim/iade geçmişi, CSV ve PDF
  akışları geçti. 320, 390 ve 768 px genişliklerde sayfa taşması görülmedi;
  geniş ürün tablosu kendi alanında yatay kaydırılır. Masaüstü/mobil ve
  PDF görselleri yerel olarak incelendi. Bu kontrol gerçek iOS cihaz testi değildir.
- İsteğe bağlı tavsiye fiyatı için yeni migration gerekmez; mevcut JSON
  belgeye eklenir. Eksik alan eski isteklerin normalleştirilmiş içeriğini
  değiştirmez. Değişmiş finansal beklentiye uydurulmuş eski test yoktur.

Canlı sunucuya erişim ve migration uygulanması ayrı doğrulanmalıdır; yerel
testin geçmesi tek başına canlıya dağıtım kanıtı değildir.
