#!/usr/bin/env bash
# lcarlie: URETIM yetki envanteri toplama betigi. SALT OKUNUR.
#
# Bu betik URETIM SUNUCUSUNDA (ya da uretim veritabanina erisebilen bir yonetim makinesinde)
# kullanicinin kendisi tarafindan calistirilir. Hicbir sunucu adresi, kullanici adi ya da parola
# icermez: baglanti bilgisi standart libpq ortam degiskenlerinden (PGHOST, PGPORT, PGUSER,
# PGDATABASE) ve ~/.pgpass / PGPASSFILE'dan okunur.
#
# Uretir (yeni bir klasore):
#   roles.sql          pg_dumpall --roles-only --no-role-passwords   (parola hash'i YOK)
#   schema-acl.sql     pg_dump --schema-only (sahiplik + GRANT/REVOKE dahil, veri YOK)
#   acl-envanter.txt   acl-envanter.sql ciktisi (normalize, satir bazli)
#   bilgi.txt          istemci surumleri ve zaman damgasi (adres/parola yazilmaz)
#   SHA256SUMS
#
# Hicbir sey YAZMAZ: tum oturumlar default_transaction_read_only=on ile acilir.
#
# Kullanim:
#   export PGDATABASE=<uretim veritabani adi>   # zorunlu
#   export PGUSER=<rol>                         # GRANT'lari gorebilen ve core.ai_orchestrator_config'i okuyabilen rol
#   export PGHOST=... PGPORT=...                # gerekiyorsa (sunucuda unix socket ise bos birakilabilir)
#   bash uretimde-topla.sh [cikti-klasoru]
set -euo pipefail
umask 077

BURASI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVANTER_SQL="$BURASI/acl-envanter.sql"
[ -f "$ENVANTER_SQL" ] || { echo "HATA: $ENVANTER_SQL bulunamadi (betikle ayni klasorde olmali)." >&2; exit 2; }

if [ -z "${PGDATABASE:-}" ]; then
  echo "HATA: PGDATABASE ayarli degil. Ornek: export PGDATABASE=<uretim veritabani adi>" >&2
  exit 2
fi

for t in psql pg_dump pg_dumpall; do
  command -v "$t" >/dev/null 2>&1 || { echo "HATA: '$t' bulunamadi (PostgreSQL istemcisi gerekli)." >&2; exit 2; }
done

CIKTI="${1:-uretim-cikti-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$CIKTI"

# Tum baglantilar salt okunur; uzun kilit beklemesi yok.
export PGOPTIONS="${PGOPTIONS:-} -c default_transaction_read_only=on -c lock_timeout=10s -c statement_timeout=300s"
export PGAPPNAME="lcarlie-acl-envanter"

echo "[1/5] Sunucu surumu ve salt-okunur kontrolu"
SUNUCU_SURUM="$(psql -X -At -v ON_ERROR_STOP=1 -c "select current_setting('server_version_num')")"
RO="$(psql -X -At -v ON_ERROR_STOP=1 -c "show default_transaction_read_only")"
[ "$RO" = "on" ] || { echo "HATA: oturum salt okunur acilmadi (default_transaction_read_only=$RO). Durduruldu." >&2; exit 3; }
ISTEMCI_SURUM="$(pg_dump --version | sed -E 's/.*\(PostgreSQL\) ([0-9]+(\.[0-9]+)?).*/\1/')"
ISTEMCI_ANA="${ISTEMCI_SURUM%%.*}"
SUNUCU_ANA="$((SUNUCU_SURUM / 10000))"
if [ "$ISTEMCI_ANA" -lt "$SUNUCU_ANA" ]; then
  echo "HATA: pg_dump $ISTEMCI_SURUM, sunucu ana surumu $SUNUCU_ANA'dan eski. Ayni ya da daha yeni pg_dump kullan." >&2
  exit 3
fi

echo "[2/5] acl-envanter.sql -> $CIKTI/acl-envanter.txt"
psql -X -At -F '|' -v ON_ERROR_STOP=1 -f "$ENVANTER_SQL" > "$CIKTI/acl-envanter.txt"

echo "[3/5] pg_dumpall --roles-only --no-role-passwords -> $CIKTI/roles.sql"
pg_dumpall --roles-only --no-role-passwords -l "$PGDATABASE" -f "$CIKTI/roles.sql"
# Emniyet: parola ya da hash sizmadigini dogrula.
if grep -Eiq "PASSWORD '|SCRAM-SHA-256\\\$|md5[0-9a-f]{32}" "$CIKTI/roles.sql"; then
  echo "HATA: roles.sql icinde parola/hash izi bulundu. Dosya silindi, paylasma." >&2
  rm -f "$CIKTI/roles.sql"; exit 4
fi

echo "[4/5] pg_dump --schema-only (sahiplik + ACL dahil) -> $CIKTI/schema-acl.sql"
pg_dump --schema-only --no-comments -f "$CIKTI/schema-acl.sql"

echo "[5/5] bilgi.txt + SHA256SUMS"
{
  echo "olusturma_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "pg_dump=$ISTEMCI_SURUM"
  echo "server_version_num=$SUNUCU_SURUM"
  echo "database=$PGDATABASE"
  echo "user=$(psql -X -At -c 'select current_user')"
} > "$CIKTI/bilgi.txt"
( cd "$CIKTI" && { command -v sha256sum >/dev/null && sha256sum acl-envanter.txt roles.sql schema-acl.sql bilgi.txt || shasum -a 256 acl-envanter.txt roles.sql schema-acl.sql bilgi.txt; } > SHA256SUMS )

echo
echo "Tamam. Klasor: $CIKTI"
grep -E '^ayar_kontrol\|' "$CIKTI/acl-envanter.txt" || true
echo "Bu klasoru yerel makinede lcarlie-local/prod-acl-karsilastirma/ altina kopyala ve karsilastir.sh calistir."
echo "Paylasmadan once roles.sql icindeki 'ALTER ROLE ... SET' satirlarini gozden gecir."
