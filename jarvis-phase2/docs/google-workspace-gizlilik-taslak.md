# L’CARLIÉ Jarvis — Google bağlantısı gizlilik bildirimi

**YAYIMLANMAMIŞ TASLAK. Hukuki ve operasyonel onay alınmadan kamuya açılmamalı.**

## Kim işletiyor?

Veri sorumlusu: **Lemos Medikal Sağlık İş Güvenliği İnşaat Gıda Turizm Sanayi ve Ticaret A.Ş.**  
Adres: **Mehmet Akif Ersoy Mah. 325. Sk. No: 3/117 Yenimahalle / Ankara**  
İletişim ve silme talepleri: **info@lcarlie.com.tr**  
Son güncelleme: **[Yayın tarihi]**

## Hangi Google verilerine erişiyoruz?

Google hesabınızı isteğe bağlı olarak bağladığınızda Jarvis şu izinleri ister:

- **Takvim etkinlikleri:** Yaklaşan etkinlikleri göstermek ve yalnızca ayrıca onayladığınız etkinliği oluşturmak.
- **Gmail gönderme:** Yalnızca alıcısını, konusunu ve metnini hazırlayıp ayrıca onayladığınız e-postayı göndermek. Gelen kutunuzu okumak için izin istemiyoruz.
- **Drive okuma:** Dosya adlarını ve bağlantılarını listelemek; yalnızca “Jarvis’e ekle” dediğiniz desteklenen dosyanın içeriğini indirmek. Okuma izni Google hesabınızdaki okunabilir Drive dosyalarını kapsar; belirli bir klasörle sınırlı değildir.
- **Drive'a kaydetme:** Ayrı dosya izni ve Jarvis onayıyla telefonunuzdan seçtiğiniz dosyanın veya Jarvis sunucusundaki kreatif ekip görselinin yeni bir kopyasını Drive ana dizinine ya da belirttiğiniz klasöre yüklemek. Mevcut Drive dosyasının üzerine yazılmaz ve Drive dosyaları silinmez.

Google hesabını bağlamak kişisel asistanın diğer özelliklerini kullanmak için zorunlu değildir.

## Verileri nasıl kullanıyoruz?

Takvim ve Drive sonuçları istediğiniz anda Google API üzerinden alınır. Seçtiğiniz Drive dosyasının bir kopyası Jarvis sunucusundaki kişisel ekler alanına kaydedilir; en fazla 5 MB kabul edilir. Kişisel sohbette soru sorduğunuzda desteklenen metnin ilgili bölümü sunucudaki yerel modele verilebilir. Görsel analizi yalnızca ayrı düğmeye bastığınızda sunucudaki yerel modele gönderilir. Google verileri reklam, satış veya kullanıcı profillemesi için kullanılmaz.

Takvim etkinliği oluşturma, Gmail gönderme ve Drive'a yeni dosya yükleme, işlemin içeriğini gösteren ayrı bir Jarvis onayı gerektirir. Google verilerini eğitim amacıyla üçüncü taraf yapay zekâ modellerine aktarmıyoruz. **Bu ifadeler, kişisel asistanın mevcut yerel model yapılandırması değişirse yayımlanmadan önce yeniden gözden geçirilmelidir.**

## Saklama ve silme

Google erişim ve yenileme belirteçleri erişimi sürdürmek için sunucuda saklanır. “Bağlantıyı kaldır” işlemi yerel belirteci siler ve Google nezdinde iptal etmeyi dener. Ayrıca Google Hesabınızın üçüncü taraf erişim ayarlarından izni kaldırabilirsiniz.

Jarvis’e eklenmiş dosya kopyaları, kişisel sohbet kayıtları ve hazırlanmış işlem/onay kayıtları bağlantı kaldırıldığında **otomatik olarak silinmez**. Sohbet geçmişi en son 400 turla sınırlıdır; işlem kayıtları en son 100 kayıtla sınırlıdır. Ek dosyalar için otomatik süreli silme henüz uygulanmamıştır. **[Yayın öncesi saklama süreleri, silme yöntemi ve talep kanalı belirlenip uygulanacak.]**

## Koruma ve paylaşım

Google bağlantısı HTTPS üzerinden kurulur. OAuth istemci gizli anahtarı kaynak koddan ayrı tutulur; kullanıcı belirteçlerine sunucuda kısıtlı dosya izni uygulanır. Google verileri, istenen işlemi gerçekleştirmek için Google API'leriyle ve hesabınızdan onayladığınız e-postanın alıcısıyla paylaşılır. **[Barındırma sağlayıcısı, yedekler, destek erişimleri ve olası alt işleyenler doğrulanıp açıklanacak.]**

Verilerinizle ilgili erişim, düzeltme veya silme talebini yukarıdaki iletişim adresine iletebilirsiniz. **[Talep işleme süresi ve hukuki dayanak hukuk incelemesinde doldurulacak.]**

## Yayın öncesi zorunlu kontrol

- Gerçek saklama/silme uygulaması doğrulanmalı.
- Bu metin kamuya açık, giriş gerektirmeyen bir sayfada yayımlanmalı; Jarvis ana sayfasından bağlanmalı.
- Google OAuth marka alanındaki ana sayfa ve gizlilik bağlantıları gerçek sayfalarla doldurulmalı.
- Drive `drive.readonly` kapsamı için Google doğrulama ve olası güvenlik incelemesi değerlendirilmeli.
- Google'ın [API Kullanıcı Verisi Politikası](https://developers.google.com/terms/api-services-user-data-policy) ile son metin karşılaştırılmalı.
