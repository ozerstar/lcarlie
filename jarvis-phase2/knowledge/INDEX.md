---
konu: bilgi dizini
anahtar: [index, dizin, ne biliyorsun, bilgi]
gizlilik: serbest
---

# L'CARLIÉ bilgi tabanı — dizin

`00-kimlik` **her turda** yüklenir. Diğer dosyalar `anahtar` alanındaki
kelimelerle eşleşerek getirilir; eşleşme yoksa yüklenmez.

Dosyalar küçük tutulur çünkü uzun bağlam pahalıdır: bu sunucuda her ~1500
karakter, operatörün beklediği süreye yaklaşık 30 saniye ekler. Bir konu tek
dosyaya sığmıyorsa **bölünür** — büyütülmez.

| Dosya | Ne var içinde | Gizlilik |
|---|---|---|
| `00-kimlik` | Şirket, kim kimdir, kanallar, temel sınır | serbest |
| `10-iddia-kurallari` | Tek kural, izinli/izinsiz nesne, yasak listeleri | serbest |
| `12-karsilik-tablosu` | Yasak ifade → uyumlu karşılığı | serbest |
| `13-kapanmis-kararlar` | Tekrar açılmayacak konular, mevzuat dayanağı | serbest |
| `11-marka-dili` | Müşteri yanıtı tonu, influencer tonu, Özer'in çıktı beklentisi, AI görsel yasağı, izinli kaynaklar | serbest |
| `20-urunler` | 36 ürün, slug, kategori, bilinen katalog hataları | serbest |
| `21-fiyat` | Fiyat listesi, VIREON 1.200/2.400 karışıklığı, kupon tuzağı, KDV/maliyet, pazar konumu | serbest |
| `30-urun-vireon` | VIREON: çerçeve, INCI, ticari bağlam, iç bilgi | **iç bilgi** |
| `30-urun-femisia` | FEMISIA: aynı yapı | **iç bilgi** |
| `30-urun-intimblanc` | INTIMBLANC: aynı yapı + strateji notları | **iç bilgi** |
| `30-urun-liftelle` | LIFTELLE: aynı yapı | **iç bilgi** |
| `30-urun-dermavasc` | DERMAVASC: aynı yapı + ad iddiası | **iç bilgi** |
| `40-eski-katalog-ic-bilgi` | Eski katalogun tam haritası, 3 satıştan kalkmış ürün, çelişkiler | **iç bilgi** |
| `50-olcum-gercekleri` | Hangi veri var/yok, sayı tuzakları, ölçülmüş gerçekler | serbest |

## `gizlilik` alanı ne demek
- **serbest** — içeriği müşteriye çıkan metinde de kullanabilirim (kurallara
  uyarak).
- **iç bilgi** — yalnız Özer'e karşı, kendi aramızda. Bu dosyalardaki
  `🔒 İÇ BİLGİ` bölümlerinden **hiçbir cümle** reklam metnine, caption'a, ürün
  sayfasına veya müşteri yanıtına taşınmaz.

## Bu dizinde olmayan ama sistemde olan
Canlı ticari veri (satış, reklam, CRM, operasyon) bu dosyalarda değil,
veritabanındadır ve izin listeli sorgularla okunur — bkz. `50-olcum-gercekleri`.
