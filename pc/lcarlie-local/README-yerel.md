# lcarlie: yerel PostgreSQL (geliştirme)

Bu kurulum yalnızca bu makinede geliştirme ve test içindir. Üretim parolası ya da gerçek sağlayıcı API anahtarı içermez.

| Öğe | Değer |
|---|---|
| Container | `lcarlie-pg` (imaj `pgvector/pgvector:pg17`, üretim dump'ı ile aynı sürüm: PostgreSQL 17.11) |
| Port | `127.0.0.1:5432` (yalnızca localhost) |
| Volume | `lcarlie-pgdata` |
| Veritabanı | `lcarlie` |
| Parolalar | `.env.local` (bu klasörde) |

> Not: Aynı makinede başka bir oturumun kurduğu ayrı bir container daha var: `lcarlie-pg-local` (port 55432, volume `lcarlie-pg-local-data`). O container ile bu kurulum birbirinden bağımsızdır. Aşağıdaki komutlar yalnızca `lcarlie-pg`'ye dokunur.

## Başlat / durdur / durum

```powershell
docker start lcarlie-pg
docker stop lcarlie-pg
docker ps --filter name=lcarlie-pg
docker exec lcarlie-pg pg_isready -U lcarlie_admin -d lcarlie
```

Container `--restart unless-stopped` ile kuruldu. Docker Desktop açıldığında kendiliğinden başlar, ancak `docker stop` ile durdurduysan başlamaz. Docker motoru kapalıysa önce şunu çalıştır:

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

## Bağlan

```powershell
docker exec -it lcarlie-pg psql -U lcarlie_admin -d lcarlie
```

## Sıfırla (TÜM yerel veriyi siler)

```powershell
docker rm -f lcarlie-pg
docker volume rm lcarlie-pgdata
```

Sonra aşağıdaki "Sıfırdan kurulum" adımlarını uygula.

## Sıfırdan kurulum (Git Bash)

```bash
cd /c/Users/ozery/lcarlie-local
set -a; . ./.env.local; set +a
MSYS_NO_PATHCONV=1 docker run -d --name lcarlie-pg --restart unless-stopped \
  -e POSTGRES_USER=$POSTGRES_USER -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD -e POSTGRES_DB=$PGDATABASE \
  -p 127.0.0.1:5432:5432 -v lcarlie-pgdata:/var/lib/postgresql/data pgvector/pgvector:pg17
PSQL="docker exec -i lcarlie-pg psql -U $POSTGRES_USER -d $PGDATABASE -v ON_ERROR_STOP=1"
# 1) roller (dump --no-acl alındığı için roller dump'ta yok)
$PSQL -v worker_pw="$AI_WORKER_PGPASSWORD" -v approver_pw="$APPROVER_PGPASSWORD" < sql/00-roles.sql
# 2) şema: üretimden alınmış schema-only dump (f4/f5/f6 ve sonraki fazlar bunun içinde zaten var)
powershell -c "docker cp 'C:\Users\ozery\lcarlie-local\sql\01-schema-only-prod-2026-10-26.dump' lcarlie-pg:/tmp/schema.dump"
MSYS_NO_PATHCONV=1 docker exec lcarlie-pg pg_restore -U $POSTGRES_USER -d $PGDATABASE --exit-on-error /tmp/schema.dump
# 3) f4/f5/f6 referans satırları (action type'lar, kill-switch config)
$PSQL < sql/02-seed-from-f4-f6.sql
# 4) yetkiler (DB_CONTRACT + f4/f5/f6 GRANT'ları + zorunlu asgari çıkarımlar; dosyanın içindeki notlara bak)
$PSQL < sql/03-grants-from-contract.sql
# 5) yalnızca yerel test fixture'ları
$PSQL < sql/04-local-fixtures.sql
# 6) ÖNERİ (yalnızca yerel): ai_get_pending_actions risk_class sıralama düzeltmesi + doğrulama
$PSQL < sql/05-fix-pending-actions-order.sql
$PSQL < sql/05-verify-pending-actions-order.sql      # siralama_dogru = t olmalı (test satırları ROLLBACK edilir)
# geri almak için: $PSQL < sql/05-rollback-pending-actions-order.sql
```

Üretim yetkileriyle karşılaştırma için: `prod-acl-karsilastirma/README.md`.

Orijinal `lcarlie-f4/f5/f6` dosyaları **yeniden uygulanmaz**: dump'ta zaten var olan tabloları yeniden oluşturmaya çalıştıkları için hata verip ROLLBACK olurlar. `f4-two-person.sql` ise f5'in iki kişilik onay mantığını eski sürümle ezeceği için **uygulanmamalıdır**.

## Kill-switch

`core.ai_orchestrator_config.ai_worker_enabled` varsayılan olarak `false`. Bu değer false iken `core.ai_claim_task` hiçbir görev vermez. Sahte sağlayıcıyla yerel bir deneme için geçici olarak açıp iş bitince yeniden kapat:

```bash
docker exec lcarlie-pg psql -U lcarlie_admin -d lcarlie -c "update core.ai_orchestrator_config set config_value='true' where config_key='ai_worker_enabled'"
# ... PROVIDER_MODE=fake ile worker'ı çalıştır (PGUSER=ai_orchestrator_worker) ...
docker exec lcarlie-pg psql -U lcarlie_admin -d lcarlie -c "update core.ai_orchestrator_config set config_value='false' where config_key='ai_worker_enabled'"
```

Worker'ı yerelde **yalnızca** `PROVIDER_MODE=fake` ile çalıştır. Gerçek sağlayıcı anahtarı ekleme.
