#!/bin/sh
set -eu
exec docker exec lcarlie-postgres psql -U n8n -d n8n -P pager=off -c "select karar_id,karar_tipi,urun,kanit_kalitesi,red_team_sonucu,onay_hazirligi,left(oneri,100) oneri from mart.ai_human_approval_dashboard where durum='PROPOSED' order by karar_id;" -c "select * from mart.ai_operations_dashboard;" -c "select * from mart.ai_alert_candidates;"
