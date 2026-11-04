# 🔴 KURULUM BETİKLERİNİ YENİDEN ÇALIŞTIRMADAN ÖNCE OKU

Son güncelleme: 14.09.2026

## Tehlike

`02-kurulum.sh` şunları **koşulsuz üzerine yazar**:

- `/opt/lcarlie/n8n/Caddyfile`
- `/opt/lcarlie/n8n/docker-compose.yml`

Betiğin başında "idempotent, tekrar çalıştırılabilir" yazıyor. **Doğru değil.**

Yeniden çalıştırılırsa sonradan elle eklenen şunlar **silinir**:

| Kaybolan | Sonuç |
|---|---|
| `handle /lc-sohbet.js` rotası | **Sitedeki canlı sohbet widget'ı 404 olur** |
| `handle_path /durum-<token>` rotası | Sunucu durum sayfası kaybolur |
| `/opt/lcarlie/widget:/widget:ro` bağlaması | Widget dosyası servis edilemez |
| `/opt/lcarlie/durum:/durum:ro` bağlaması | Durum sayfası servis edilemez |
| `header_up X-Gercek-IP {client_ip}` | **Hız sınırı taklit edilebilir hâle gelir** — müşteri kendi `X-Forwarded-For` başlığını yazarak sınırı sonsuza kadar aşar |
| `request_body @herkeseAcik { max_size 64KB }` | Herkese açık webhook'a sınırsız boyutta gövde gönderilebilir |
| `format filter { … request>uri regexp … }` | **Panel ve durum sayfası anahtarları erişim kaydına düz metin düşer** |

## Çalıştırmak zorundaysanız

**Önce yedekleyin:**

```bash
ssh lcarlie
cp /opt/lcarlie/n8n/Caddyfile          /root/Caddyfile.oncesi
cp /opt/lcarlie/n8n/docker-compose.yml /root/compose.oncesi
```

**Sonra geri koyun** — bu klasördeki canlı kopyalar referanstır:

- `Caddyfile.canli`
- `docker-compose.canli.yml`

```bash
# Kurulumdan sonra:
scp Caddyfile.canli lcarlie:/opt/lcarlie/n8n/Caddyfile
scp docker-compose.canli.yml lcarlie:/opt/lcarlie/n8n/docker-compose.yml
ssh lcarlie "cd /opt/lcarlie/n8n && docker compose up -d caddy"
```

**Doğrulayın:**

```bash
ssh lcarlie 'curl -s -o /dev/null -w "widget %{http_code}\n" https://n8n.lcarlie.shop/lc-sohbet.js'
```

`200` dönmeli. `404` dönüyorsa rota silinmiştir.

---

## Kaynak ↔ sunucu senkronu

Bu klasördeki şu dosyalar **sunucudaki canlı hâlin kopyasıdır**, kurulum
betiklerinin ürettiği ilk hâl değil:

| Dosya | İçerdiği canlı değişiklik |
|---|---|
| `durum-uret.sh` | Bekleyen eskalasyon satırı · `DOCKER_API_VERSION` |
| `backup.sh` | `--yerel` bayrağı · rclone `timeout` sarmalı |
| `Caddyfile.canli` | Widget ve durum sayfası rotaları · **`header_up X-Gercek-IP`** |
| `docker-compose.canli.yml` | `/widget` ve `/durum` bağlamaları |
| `hiz-sifirla.sh` | Hız sınırı sayaçlarını temizleme aracı |
| `geri-yukle.sh` | **Doğrula → güvenlik dökümü → yükle** sırası; `--dogrula` / `--onayla` / `--dokumden` bayrakları |

> 🔴 `03-yedekleme.sh` yeniden çalıştırılırsa `/opt/lcarlie/backup/geri-yukle.sh`
> dosyasını **eski, tehlikeli hâliyle üzerine yazar** (önce DROP DATABASE, güvenlik
> dökümü yok). Sonra bu klasördeki kopyayı geri koyun:
> `scp geri-yukle.sh lcarlie:/root/ && ssh lcarlie "install -m 700 /root/geri-yukle.sh /opt/lcarlie/backup/geri-yukle.sh"`

`n8n-yayinla.sh`, `n8n-geri-don.sh` ve `hiz-sifirla.sh` `.\yayinla.ps1` ile
otomatik gönderiliyor — onları elle kopyalamaya gerek yok.

Sunucuda bir bakım betiğini elle değiştirirseniz, **kopyasını buraya alın**.
Aksi halde kaynak yalan söyler ve bir sonraki kurulumda değişiklik kaybolur.

> Bu uyarı 14.09.2026 sistem denetiminde ortaya çıktı: widget rotası
> hiçbir kaynak dosyada kayıtlı değildi, yalnızca sunucuda elle eklenmişti.
