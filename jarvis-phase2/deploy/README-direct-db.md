# Jarvis web: root ve Docker soketi olmadan veritabanı erişimi

Web servisi `jarvis-web` sistem kullanıcısıyla çalışır. `jarvis_web` PostgreSQL
hesabı yalnız gereken tablo izinlerini ve `ai_reader` ile `human_approver`
rollerine geçiş yetkisini taşır. Parola `/etc/lcarlie/jarvis-web-db.pass`
dosyasındadır; kaynak depoya konmaz.

## Sunucu yapılandırması

- PostgreSQL Compose hizmeti hem `dahili` hem `dbhost` köprü ağındadır.
  `127.0.0.1:5433:5432` port eşlemesi yalnız sunucu içinden erişilir.
- `python3 deploy/provision-web-db.py` ilk kurulumda hesabı ve parolayı
  oluşturur. Mevcut parola dosyası varsa betik yeniden çalışmayı reddeder.
- `/etc/systemd/system/jarvis-web.service` içinde `User=jarvis-web`,
  `Group=jarvis-web`, `JARVIS_MEMORY_TRANSPORT=direct-pg`,
  `JARVIS_DB_HOST=127.0.0.1`, `JARVIS_DB_PORT=5433`,
  `JARVIS_DB_PASSWORD_FILE=/etc/lcarlie/jarvis-web-db.pass` ve
  `InaccessiblePaths=/var/run/docker.sock` ayarları bulunur.
- `/opt/lcarlie/jarvis-phase2/state`, `/opt/lcarlie/saha-foto` ve
  `/opt/lcarlie/saha-karo` web kullanıcısının yazmasına izin verir.
  Katalog ve gönderi görselleri yalnız okunur.

## Doğrulama

`deploy/smoke-web-db.py` dosyasını web kullanıcısıyla çalıştırın. Ardından
şirket belleği, onay listesi, satış, katalog, saha, gelen kutusu ve üretilenler
okumalarını aynı kullanıcıyla kontrol edin. `systemctl show jarvis-web.service
-p User -p Group -p ActiveState` çıktısında `jarvis-web` ve `active` görülmeli.
`docker ps` komutu bu kullanıcı altında izin hatası vermelidir. 5433 yalnız
`127.0.0.1` üzerinde dinlemelidir.

## Geri dönüş

Canlı sunucudaki önceki servis birimi
`/etc/systemd/system/jarvis-web.service.pre-direct-db` ve önceki kod kopyaları
`/opt/lcarlie/backups/jarvis-web-direct-*` altında tutulur. Önce servisi
durdurun; birimi ve kodu geri yükleyip `systemctl daemon-reload` ve
`systemctl start jarvis-web.service` çalıştırın. PostgreSQL hesabını veya
parolayı geri dönüş sırasında silmeyin; kullanımdan çıktığı doğrulandıktan
sonra ayrı bakım işleminde kaldırın.
