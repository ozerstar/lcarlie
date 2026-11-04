#!/usr/bin/env bash
# lcarlie: YEREL taraf + otomatik fark. Hicbir uzak sunucuya baglanmaz.
# Yerel veritabani yalnizca docker container uzerinden okunur (varsayilan: lcarlie-pg).
#
# Kullanim (Git Bash):
#   bash karsilastir.sh --yalniz-yerel              # yalnizca yerel ciktiyi uret + oz-kontrol
#   bash karsilastir.sh <uretim-cikti-klasoru>      # uretimde-topla.sh ciktisiyla karsilastir
# Ortam:
#   CONTAINER (varsayilan lcarlie-pg), YEREL_DB (lcarlie), YEREL_USER (lcarlie_admin)
set -euo pipefail
export LC_ALL=C
export MSYS_NO_PATHCONV=1

BURASI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="${CONTAINER:-lcarlie-pg}"
YEREL_DB="${YEREL_DB:-lcarlie}"
YEREL_USER="${YEREL_USER:-lcarlie_admin}"

if [ "$CONTAINER" = "lcarlie-pg-local" ]; then
  echo "HATA: lcarlie-pg-local baska bir oturuma ait; bu betik ona dokunmaz." >&2; exit 2
fi
[ $# -ge 1 ] || { sed -n '2,10p' "$0"; exit 2; }

YEREL="$BURASI/yerel-cikti"
mkdir -p "$YEREL"
PSQL=(docker exec -i -e PGOPTIONS="-c default_transaction_read_only=on" "$CONTAINER" psql -X -U "$YEREL_USER" -d "$YEREL_DB" -v ON_ERROR_STOP=1)

echo "[yerel] acl-envanter.sql -> yerel-cikti/acl-envanter.txt ($CONTAINER/$YEREL_DB)"
"${PSQL[@]}" -At -F '|' < "$BURASI/acl-envanter.sql" > "$YEREL/acl-envanter.txt"
echo "[yerel] pg_dumpall --roles-only --no-role-passwords -> yerel-cikti/roles.sql"
docker exec -e PGOPTIONS="-c default_transaction_read_only=on" "$CONTAINER" \
  pg_dumpall -U "$YEREL_USER" -l "$YEREL_DB" --roles-only --no-role-passwords > "$YEREL/roles.sql"
echo "[yerel] pg_dump --schema-only -> yerel-cikti/schema-acl.sql"
docker exec -e PGOPTIONS="-c default_transaction_read_only=on" "$CONTAINER" \
  pg_dump -U "$YEREL_USER" -d "$YEREL_DB" --schema-only --no-comments > "$YEREL/schema-acl.sql"

# ---------- normalizasyon ----------
meta() { grep -E "^meta\|$2\|" "$1" | head -1 | cut -d'|' -f3; }

norm_envanter() {   # $1 dosya -> stdout (meta haric, CRLF/bosluk temiz, sirali, tekil)
  tr -d '\r' < "$1" | sed -E 's/[[:space:]]+$//' | grep -v '^$' | grep -v '^meta|' | sort -u
}

# pg_dump / pg_dumpall: yalnizca yetki/sahiplik/rol satirlari; bootstrap superuser adi normalize edilir.
norm_dump() {       # $1 dosya, $2 bootstrap adi -> stdout
  local bs="$2"
  tr -d '\r' < "$1" \
  | grep -E '^(GRANT|REVOKE|ALTER DEFAULT PRIVILEGES|ALTER [A-Z ]+ .* OWNER TO|CREATE ROLE|ALTER ROLE)' \
  | sed -E "s/(^|[^A-Za-z0-9_\"])\"?${bs}\"?([^A-Za-z0-9_\"]|$)/\1<bootstrap_superuser>\2/g" \
  | sed -E 's/ GRANTED BY [^;]+;/;/' \
  | sed -E 's/[[:space:]]+$//' | sort -u
}

ozet() {            # $1 fark klasoru: bolum bazli sayim
  local d="$1"
  printf '%-18s %10s %10s\n' "bolum" "yalniz-ur" "yalniz-yer"
  cut -d'|' -f1 "$d/yalniz-uretimde.txt" "$d/yalniz-yerelde.txt" 2>/dev/null | sort -u | while read -r b; do
    [ -n "$b" ] || continue
    u=$(grep -c "^$b|" "$d/yalniz-uretimde.txt" || true)
    y=$(grep -c "^$b|" "$d/yalniz-yerelde.txt" || true)
    printf '%-18s %10s %10s\n' "$b" "$u" "$y"
  done
}

if [ "$1" = "--yalniz-yerel" ]; then
  echo
  echo "== yerel envanter ozeti =="
  norm_envanter "$YEREL/acl-envanter.txt" | cut -d'|' -f1 | uniq -c
  echo
  grep -E '^(meta|ayar|ayar_kontrol|uyelik)\|' "$YEREL/acl-envanter.txt"
  # oz-kontrol: ayni girdi -> bos fark olmali
  if diff -q <(norm_envanter "$YEREL/acl-envanter.txt") <(norm_envanter "$YEREL/acl-envanter.txt") >/dev/null; then
    echo "oz-kontrol: normalizasyon deterministik (fark yok)."
  fi
  bs=$(meta "$YEREL/acl-envanter.txt" bootstrap_superuser)
  echo "yerel dump yetki satirlari: $(norm_dump "$YEREL/schema-acl.sql" "$bs" | wc -l), rol satirlari: $(norm_dump "$YEREL/roles.sql" "$bs" | wc -l)"
  exit 0
fi

UR="$1"
for f in acl-envanter.txt roles.sql schema-acl.sql; do
  [ -f "$UR/$f" ] || { echo "HATA: $UR/$f yok." >&2; exit 2; }
done
if [ -f "$UR/SHA256SUMS" ]; then
  ( cd "$UR" && tr -d '\r' < SHA256SUMS | sha256sum -c --quiet - ) || { echo "UYARI: SHA256SUMS dogrulanamadi (dosyalar degismis olabilir)." >&2; }
fi

FARK="$BURASI/fark-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$FARK"
norm_envanter "$UR/acl-envanter.txt"    > "$FARK/uretim.norm.txt"
norm_envanter "$YEREL/acl-envanter.txt" > "$FARK/yerel.norm.txt"
comm -23 "$FARK/uretim.norm.txt" "$FARK/yerel.norm.txt" > "$FARK/yalniz-uretimde.txt"
comm -13 "$FARK/uretim.norm.txt" "$FARK/yerel.norm.txt" > "$FARK/yalniz-yerelde.txt"
diff -u --label uretim --label yerel "$FARK/uretim.norm.txt" "$FARK/yerel.norm.txt" > "$FARK/acl-envanter.diff" || true

BS_UR=$(meta "$UR/acl-envanter.txt" bootstrap_superuser)
BS_YER=$(meta "$YEREL/acl-envanter.txt" bootstrap_superuser)
norm_dump "$UR/schema-acl.sql"    "$BS_UR"  > "$FARK/uretim.dump-yetki.txt"
norm_dump "$YEREL/schema-acl.sql" "$BS_YER" > "$FARK/yerel.dump-yetki.txt"
diff -u --label uretim --label yerel "$FARK/uretim.dump-yetki.txt" "$FARK/yerel.dump-yetki.txt" > "$FARK/schema-acl.diff" || true
norm_dump "$UR/roles.sql"    "$BS_UR"  > "$FARK/uretim.roller.txt"
norm_dump "$YEREL/roles.sql" "$BS_YER" > "$FARK/yerel.roller.txt"
diff -u --label uretim --label yerel "$FARK/uretim.roller.txt" "$FARK/yerel.roller.txt" > "$FARK/roles.diff" || true

{
  echo "# lcarlie yetki farki  ($(date '+%Y-%m-%d %H:%M'))"
  echo "uretim: $UR  (surum $(meta "$UR/acl-envanter.txt" server_version_num), bootstrap=$BS_UR, user=$(meta "$UR/acl-envanter.txt" current_user))"
  echo "yerel : $CONTAINER/$YEREL_DB  (surum $(meta "$YEREL/acl-envanter.txt" server_version_num), bootstrap=$BS_YER)"
  echo
  echo "## orchestrator_enabled_after"
  echo "uretim: $(grep -E '^ayar_kontrol\|orchestrator_enabled_after\|' "$UR/acl-envanter.txt" | cut -d'|' -f3)"
  echo "yerel : $(grep -E '^ayar_kontrol\|orchestrator_enabled_after\|' "$YEREL/acl-envanter.txt" | cut -d'|' -f3)"
  echo
  echo "## bolum bazli fark (satir sayisi)"
  ozet "$FARK"
  echo
  echo "## 03-grants-from-contract.sql CIKARIMLARININ uretimdeki karsiligi"
  for k in 'sema_acl|core|function_owner|USAGE|' \
           'iliski_acl|core.karar|function_owner|SELECT|' \
           'iliski_acl|core.karar|function_owner|INSERT|' \
           'iliski_acl|core.ai_calisma_log|function_owner|INSERT|' \
           'iliski_acl|core.ayar|ai_reader|SELECT|' \
           'iliski_acl|core.urun_maliyet|ai_reader|SELECT|'; do
    if grep -qF "$k" "$FARK/uretim.norm.txt"; then d="URETIMDE VAR"; else d="URETIMDE YOK"; fi
    printf '  %-55s %s\n' "$k" "$d"
  done
  echo
  echo "## kill-switch / ayar / action_type farklari"
  grep -hE '^(ayar|ayar_kontrol|action_type)\|' "$FARK/yalniz-uretimde.txt" | sed 's/^/  - uretim: /' || true
  grep -hE '^(ayar|ayar_kontrol|action_type)\|' "$FARK/yalniz-yerelde.txt"  | sed 's/^/  + yerel : /' || true
  echo
  echo "## rol / uyelik farklari"
  grep -hE '^(rol|rol_ayar|uyelik)\|' "$FARK/yalniz-uretimde.txt" | sed 's/^/  - uretim: /' || true
  grep -hE '^(rol|rol_ayar|uyelik)\|' "$FARK/yalniz-yerelde.txt"  | sed 's/^/  + yerel : /' || true
  echo
  echo "Ayrintilar: acl-envanter.diff, schema-acl.diff, roles.diff, yalniz-uretimde.txt, yalniz-yerelde.txt"
  echo "Beklenen yerel-only farklar: local_approver_1 rolu/uyeligi, yerel fixture'lar, (uygulandiysa) 05 risk_class duzeltmesinin fonksiyon_govde md5'i."
} > "$FARK/OZET.txt"

cat "$FARK/OZET.txt"
echo
echo "Fark klasoru: $FARK"
