---
konu: Instagram ve Facebook organik kaydırmalı gönderi yayınlama repoları
anahtar: [instagram yayınlama, facebook yayınlama, carousel, kaydırmalı gönderi, sosyal medya planlama, postiz, meta business sdk, dosya yükleme]
gizlilik: ic-bilgi
kaynak: GitHub resmi depoları ve Jarvis sunucusunda doğrulanmış kaynak kopyaları; 19.10.2026
uretim: 19.10.2026
---

# Organik sosyal medya yayınlama kaynakları

19 Ekim 2026'da iki açık kaynak depo, çalışan Jarvis uygulamasından ayrı olarak
/opt/lcarlie/research-repos/social-publishing/ altına indirildi. Kaynak kodu
okumak için hazırdır; uygulama kurulumu, Meta yetkilendirmesi ve yayınlama
bağlantısı yapılmış değildir. Bu ayrımı yanıtlarda açıkça koru.

1. Meta Business SDK for Python — resmi Meta istemcisi.
   facebook-python-business-sdk/, commit
   efd8423a2e595ea8d4c04eb824ce113f2f1d68cd.
   https://github.com/facebook/facebook-python-business-sdk
   Jarvis'in mevcut Python mimarisine en küçük eklemlenme adayı. SDK tek
   başına gönderi planlayıcısı veya yetki değildir. Meta uygulaması, gerekli
   Instagram içerik yayınlama ve Facebook Sayfa izinleri, bağlı profesyonel
   Instagram hesabı ve erişim anahtarları doğrulanmalıdır.

2. Postiz — açık kaynak sosyal medya planlama sistemi.
   postiz-app/, commit e7ceab7b661bb69d7479313b81935028c514d741.
   https://github.com/gitroomhq/postiz-app
   Instagram ve Facebook kanalları, çoklu görsel, takvim ve API içerir.
   AGPL-3.0 lisanslı ayrı bir servis olarak değerlendirilir; Jarvis'e kod
   kopyalanmaz. Veritabanı, arka plan işleyicileri, Meta geliştirici
   uygulaması/OAuth ve bakım yükü vardır. Bu sunucuda çalıştırılmadı.

Önerilen sıra: Mevcut 39 ürün seti için önce Meta yetkilerini salt okunur
biçimde doğrula. Ardından kamuya açık HTTPS görsel adresleri ve görsel sırası
(01-INSAN-KULLANIM, 02-URUN, 03-ICERIK) ile tek gönderilik taslak/deneme
akışı kur. Instagram carousel oluşturma, Facebook çoklu görsel gönderisi,
Türkiye saat dilimi, tekrar denemede çift yayınlamama, sonuç kimliği ve hata
kaydı ayrı ayrı sınanmalı. 39 gönderinin platformda gerçekten planlandığı
kanıtlanmadan “planlandı” deme. Reklam oluşturma.

Mevcut engel: Chrome/ChatGPT eklentisi yerel JPG yüklemeyi “Allow access to
file URLs” açık görünmesine rağmen reddediyor. Bu depolar eklenti iznini
düzeltmez. Resmi API akışı bu tarayıcı dosya seçicisine bağımlı olmayan bir
yol sağlayabilir, ama erişim yetkisi ve güvenli görsel barındırma kurulmalıdır.
Meta Business Suite'de bu hesap için mağazanın Türkiye'de kullanılamadığı
görüldü; organik mavi “Satın al” düğmesi vaat edilmemeli.