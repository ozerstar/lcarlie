# L’CARLIÉ AI arama görünürlüğü

## Canlı temel

- Resmî site: <https://www.lcarlie.shop/>
- Bakım ürünleri rehberi: <https://www.lcarlie.shop/post/l-carlié-ürün-rehberi-bakım-alanına-göre-ürünler>
- Rehber, 28 Ekim 2026'da Wix Blog üzerinden yayımlandı. Resmî mağazadaki 36 bakım ürününün güncel ürün URL'si kullanıldı; aksesuar seçkisi bu rehbere katılmadı.
- Canlı HTTP yanıtı 200, canonical kendisi ve HTML içinde 36 ürün bağlantısı doğrulandı.
- Aynı gün Wix bağlantılı Google Search Console'a sayfa indeksleme isteği gönderildi; API yanıtı 200. Bu, indekslenme garantisi değildir.
- `robots.txt` bütün botlara kök yolu açıyor ve sitemap'e işaret ediyor. `store-products-sitemap.xml` 100 URL içeriyor. Google Search Console bağlantısı `VALID`, site hazırlığı `READY`; sitemap 25 Ekim 2026'da gönderilmiş.

## Yerel denetim

```powershell
cd C:\Users\ozery\lcarlie-local
python visibility/audit.py
```

Komut yalnızca herkese açık siteyi okur; API anahtarı veya özel veri kullanmaz. Rehberden ürün URL'lerini çıkarır; her sayfanın HTTP durumu, canonical etiketi, sitemap üyeliği, `Product` JSON-LD adı, görseli ve teklifi ile rehber bağlantı sayısını kontrol eder. Sonuçları `report.json` ve `products.csv` dosyalarına yazar. Hata kodları sayfa düzeyinde incelenebilir.

`gtin13_candidate_unverified` yalnızca SKU'nun 13 rakamlı olmasına bakar. Bu SKU'nun gerçek, tahsis edilmiş GTIN olduğu ürün kayıtları veya ambalajlardan doğrulanmadan `gtin13` işaretlemesi eklenmemelidir.

## İlk ölçüm ve sonraki işler

- 28 Eylül–25 Ekim 2026 Search Console sorgularında trafik büyük ölçüde marka ve ürün adlarından geldi. Genel ihtiyaç sorguları için görünürlük henüz sınırlı.
- `/tumurunler` arama aracında görünür metin döndürmedi. İçeriği Wix Editor içinde gerçek metin ve bağlantı bileşenlerine taşıma, kalıcı kategori keşfi için en önemli sonraki site değişikliği. Rehber, bugünden taranabilir bir giriş sağlar.
- Ürün başlıkları, içerik/INCI, uyarılar ve fiyatlar ürün sayfalarında tutulmalı; rehberde kopyalanan geçici fiyat iddiası yok.
- Google Merchant Center ürün feed'i ve Bing Webmaster/IndexNow entegrasyonu ayrıca kurulmalı. `robots.txt` erişimi ve yapılandırılmış veri, herhangi bir yapay zekâ platformunda önerilme garantisi vermez.
- İzleme için tarafsız, markasız sorguların ve ürün kategorilerinin mevcut GEO gözlem sistemine eklenmesi gerekir. Mevcut F2 seti yalnız SUNACNEA odaklıdır.
