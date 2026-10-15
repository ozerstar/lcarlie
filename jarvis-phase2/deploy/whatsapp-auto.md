# WhatsApp otomatik yanıt

`lcarlie-whatsapp-oto-yanit.timer` her dakika yalnız yeni, son gelen WhatsApp webhook mesajlarını inceler. `JARVIS_WHATSAPP_AUTO_SINCE` öncesine dönmez ve 23 saatten eski bir mesaja serbest metin göndermez. Her mesaj `lcarlie.mesaj.ek.auto_reply` alanında gönderimden önce sahiplenilir; belirsiz ağ hatası veya çökme sonrasında otomatik yeniden denenmez.

`JARVIS_WHATSAPP_AUTO_REPLY=1` yalnız Meta Business Agent'ın WhatsApp'ta yanıt vermediği doğrulandıktan sonra açılır. `JARVIS_WHATSAPP_GONDER=1` ve geçerli WhatsApp token/telefon kimliği ayrıca gerekir. Kapatmak için `/etc/lcarlie/whatsapp-auto.env` içindeki otomatik yanıt anahtarını `0` yapıp timer'ı durdurun. Manuel panel gönderimi bundan etkilenmez.

Sağlık, şikâyet ve belirsiz mesajlara kısa yanıtın ardından konuşma `INSANDA` olur. İletişimi durdurma isteğine yanıt gönderilmez. Doğrulanmamış ürün bağlantısı, mevzuat engeli ve model hatası müşteriye gönderilmez; ilgili konuşma insana devredilir. Ödeme sorusunda ürün bilinmiyorsa ürün adı sorulur. İddia, iade ve mevcut sipariş işlemleri otomatik yanıtlanmaz.
