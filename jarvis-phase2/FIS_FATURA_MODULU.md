# Fiş ve fatura arşivi

`/belgeler.html` mobil ve masaüstü Jarvis oturumunda çalışır. Fişler `ORTAK_FISLER`, faturalar inceleme sonrası `LEMOS_FATURALAR` veya `MOY_FATURALAR` klasörüne girer. Şirketi veya OCR bilgisi doğrulanmayan faturalar `INCELEME_GEREKEN_FATURALAR` klasöründe kalır. Belgelerin asılları PostgreSQL `core.jarvis_expense_document.content` alanında saklanır. Bu arşiv cari hesaba otomatik mali hareket yazmaz.

## Kurulum

1. `migrations/050_expense_documents.sql` ve `migrations/051_expense_review_retry.sql` test ve üretim veritabanına yedek alındıktan sonra uygulanır.
2. Kaynak depo temizken `tools/deploy.sh` çalıştırılır.
3. `tools/lcarlie-expense-{sync,monthly,retry}.{service,timer}` birimleri `/etc/systemd/system/` içine kopyalanır; `systemctl daemon-reload` ve timer `enable --now` uygulanır.
4. `/opt/lcarlie/jarvis-phase2/venv/bin/python /opt/lcarlie/jarvis-phase2/tools/expense_jobs.py dry-run YYYY-MM` yalnız paket sayımlarını gösterir. E-posta göndermez.

## Gmail

Gelen fatura eklerini sunucunun günlük taraması için Jarvis Google bağlantısında `gmail.readonly` izni gerekir. `/belgeler.html` bağlantı durumunu gösterir ve `/google/start` ile yenileme bağlantısı sunar. Bağlantı yokken kullanıcı yüklemesi ve ay sonu e-postası çalışır; e-posta taraması bekler. Tarama e-postaları okundu olarak işaretlemez ve belgeyi mali hesaba işlemez. Aynı dosya SHA-256 ile tekrar kaydedilmez. OCR alanları kullanıcı incelemesine düşer.

## İnceleme ve eşleştirme

İnceleme kuyruğu şirketten bağımsız olarak yeni veya incelenecek durumdaki tüm belgeleri gösterir. Bilgi düzenleme ekranı asıl belgeyi alanların yanında açar. Fişe aynı harcamanın faturasını bağlamak isteğe bağlıdır; her iki dosya korunur ve CSV listesinde bağlantı görünür. Bir fatura yalnız bir fişle eşleşebilir.

## Ay sonu

`lcarlie-expense-monthly.timer` her gün 23:55 Europe/Istanbul saatinde çalışır; komut yalnız ayın son gününde veya kaçırılmış ayın ilk üç gününde önceki ayı gönderir. `moy.ozeryildiz@gmail.com` adresine ZIP parçaları gider. Her parçada asıl dosyalar, `BELGE_LISTESI.csv` ve açıklama bulunur. Gönderim başlamadan önce veritabanına `sending` durumu yazılır. Belirsiz sonuçlar otomatik tekrar gönderilmez. Başarısız veya 30 dakikadır `sending` durumunda kalan bir paket için önce alıcı kutusu kontrol edilir; arayüzdeki yeniden gönderim düğmesi kullanıcının talebini kaydeder. `lcarlie-expense-retry.timer` bu talepleri 15 dakikada bir işler. `sent` paketleri yeniden gönderilemez. Gün sonundan sonra yüklenen belgeler yükleme ayının paketine girer.

Bu arşiv vergi indirimi veya muafiyeti kararı vermez. Belge türü, gider uygunluğu ve vergi tutarını muhasebeci doğrular.
