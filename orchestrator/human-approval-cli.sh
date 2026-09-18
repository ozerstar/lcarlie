#!/bin/sh
set -eu
usage(){ echo "usage: $0 status | list [limit] | duplicates | supersede <old_id> <canonical_id> <approver> <reason> | conclude <id> <metric> <baseline> <observed> <actor> | show <karar_id> | decide <karar_id> <APPROVE|REJECT|DEFER|MODIFY> <approver> <note>" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "root required" >&2; exit 1; }
cmd=${1:-}; shift || true
case "$cmd" in
 status)
  docker exec lcarlie-postgres psql -U n8n -d n8n -x -c "SET ROLE human_approver; SELECT * FROM mart.ai_company_intelligence_dashboard;"
 ;;
 conclude)
  [ "$#" -eq 5 ] || usage
  id=$1; metric=$2; baseline=$3; observed=$4; actor=$5
  case "$id" in ''|*[!0-9]*) usage;; esac
  docker exec -i lcarlie-postgres psql -v ON_ERROR_STOP=1 -U n8n -d n8n -v id="$id" -v metric="$metric" -v baseline="$baseline" -v observed="$observed" -v actor="$actor" <<'SQL'
BEGIN;
SET ROLE human_approver;
SELECT core.human_conclude_decision(:'id'::bigint,:'metric',:'baseline'::numeric,:'observed'::numeric,:'actor');
COMMIT;
SQL
 ;;
 list)
  limit=${1:-20}; case "$limit" in ''|*[!0-9]*) usage;; esac
  [ "$limit" -ge 1 ] && [ "$limit" -le 100 ] || usage
  docker exec lcarlie-postgres psql -U n8n -d n8n -P pager=off -c "SET ROLE human_approver; SELECT karar_id,karar_tipi,urun,kanal,kanit_kalitesi,red_team_result,review_priority_score,review_disposition FROM mart.ai_approval_priority LIMIT $limit;"
 ;;
 duplicates)
  docker exec lcarlie-postgres psql -U n8n -d n8n -P pager=off -c "SET ROLE human_approver; SELECT duplicate_count,karar_ids,karar_tipi,urun,kanal,anlik_id,red_team_results,min_review_score,max_review_score FROM mart.ai_decision_duplicate_groups;"
 ;;
 supersede)
  [ "$#" -eq 4 ] || usage
  old=$1; canonical=$2; approver=$3; reason=$4
  case "$old:$canonical" in *[!0-9:]*|:*) usage;; esac
  docker exec -i lcarlie-postgres psql -v ON_ERROR_STOP=1 -U n8n -d n8n -v old="$old" -v canonical="$canonical" -v approver="$approver" -v reason="$reason" <<'SQL'
BEGIN;
SET ROLE human_approver;
SELECT core.human_supersede_decision(:'old'::bigint,:'canonical'::bigint,:'approver',:'reason');
COMMIT;
SQL
 ;;
 show)
  id=${1:-}; case "$id" in ''|*[!0-9]*) usage;; esac
  docker exec lcarlie-postgres psql -U n8n -d n8n -P pager=off -c "SET ROLE human_approver; SELECT karar_id,olusturma,karar_tipi,urun,kanal,oneri,kanit_kalitesi,beklenen_etki,risk,yanlislama_kosulu,red_team_result,itiraz_tipi,red_team_reason,kanit_referansi,eligible_for_human_decision FROM mart.ai_approval_inbox WHERE karar_id=$id;"
 ;;
 decide)
  [ "$#" -eq 4 ] || usage
  id=$1; decision=$2; approver=$3; note=$4
  case "$id" in ''|*[!0-9]*) usage;; esac
  case "$decision" in APPROVE|REJECT|DEFER|MODIFY);;*) usage;; esac
  [ "${#approver}" -ge 3 ] && [ "${#approver}" -le 200 ] || usage
  [ "${#note}" -ge 1 ] && [ "${#note}" -le 4000 ] || usage
  docker exec -i lcarlie-postgres psql -v ON_ERROR_STOP=1 -U n8n -d n8n -P pager=off -v id="$id" -v decision="$decision" -v approver="$approver" -v note="$note" <<'SQL'
BEGIN;
SET ROLE human_approver;
SELECT core.human_decide_karar(:'id'::bigint,:'decision',:'note',:'approver') AS new_status;
COMMIT;
SQL
 ;;
 *) usage;;
esac
