# Jarvis Google bağlantısı

Bu bağlantı **isteğe bağlıdır**. Kişisel sohbet, hafıza ve görsel analizi Google
hesabı olmadan çalışır. Google Takvim, Gmail ve Drive hizmetleri açık kaynak
değildir; aşağıdaki kurulum yalnızca bu hizmetleri kullanmak isteyenler içindir.

Google Cloud Console'da bu Jarvis için bir **OAuth 2.0 Web application** istemcisi oluşturun.

1. Google Calendar API, Gmail API ve Google Drive API'yi açın.
2. OAuth izin ekranında kullanılacak Google hesabını test kullanıcısı olarak ekleyin.
3. Authorized JavaScript origin: `https://jarvis.lcarlie.shop`
4. Authorized redirect URI: `https://jarvis.lcarlie.shop/google/callback`
5. İstemci kimliğini ve gizli anahtarını sunucuda yalnızca root'un okuyabildiği `/etc/lcarlie/google-oauth.env` dosyasına yazın:

   ```text
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   ```

6. Dosya izinlerini `0600` yapıp `jarvis-web.service` hizmetini yeniden başlatın.
7. Telefonda **Asistan → Kişisel → Google hesabını bağla** yoluyla kendi Google hesabınıza giriş yapın.

İzinler: takvim etkinliklerini okuma/ekleme, e-posta gönderme ve Drive dosya adlarını okuma. Jarvis e-posta veya takvim yazma işlemini önce taslak olarak gösterir; ayrıca onay verilmedikçe uygulamaz. Drive dosya içeriği okunmaz.

Gmail ve Drive izinleri, Google'ın uygulama doğrulaması veya test kullanıcısı sınırlamalarına tabi olabilir. İzinleri yalnızca gerekli hesaplara verin.
