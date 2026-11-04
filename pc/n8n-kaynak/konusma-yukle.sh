#!/usr/bin/env bash
# L'CARLIE - konusma yukleyici
# Kullanim: ./konusma-yukle.sh <dosya.jsonl> [--kuru]
#
# Girdi: satir basina BIR konusma (JSONL):
# {"kanal":"instagram","harici_id":"t_1","musteri_ref":"igsid_9","musteri_ad":"Ad",
#  "notlar":{"reklam":"INTIMBLANC"},
#  "mesajlar":[{"harici_id":"m1","zaman":"2026-09-15T10:00:00+03:00",
#               "yon":"gelen","gonderen":"musteri","metin":"..."}]}
#
# gonderen: musteri | meta_ai | insan | ajan
# Tekrar calistirmak GUVENLIDIR: ayni harici_id kopyalanmaz, uzerine yazilir.
set -Eeuo pipefail

DOSYA="${1:-}"
KURU="${2:-}"
[ -z "$DOSYA" ] && { echo "HATA: dosya verilmedi. Kullanim: $0 <dosya.jsonl> [--kuru]"; exit 1; }
[ -f "$DOSYA" ] || { echo "HATA: dosya yok: $DOSYA"; exit 1; }
command -v jq >/dev/null || { echo "HATA: jq kurulu degil"; exit 1; }

PG=(docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1)

# ---------------------------------------------------------------
# 1) Girdi dogrulama - hicbir sey yazilmadan once
# ---------------------------------------------------------------
SATIR=0; HATA=0; TOPLAM_MESAJ=0
while IFS= read -r L || [ -n "$L" ]; do
  SATIR=$((SATIR+1))
  [ -z "${L//[[:space:]]/}" ] && continue
  if ! printf '%s' "$L" | jq -e . >/dev/null 2>&1; then
    echo "HATA satir $SATIR: gecersiz JSON"; HATA=1; continue
  fi
  EKSIK=$(printf '%s' "$L" | jq -r '[
      (if (.kanal//"")=="" then "kanal" else empty end),
      (if (.harici_id//"")=="" then "harici_id" else empty end),
      (if (.mesajlar|type)!="array" then "mesajlar-dizi-degil" else empty end)
    ] | join(",")')
  if [ -n "$EKSIK" ]; then echo "HATA satir $SATIR: eksik/hatali alan -> $EKSIK"; HATA=1; continue; fi
  BOZUK=$(printf '%s' "$L" | jq -r '[.mesajlar[]? | select(
      (.harici_id//"")=="" or (.zaman//"")=="" or
      ((.gonderen//"") as $g | ["musteri","meta_ai","insan","ajan"] | index($g) | . == null)
    )] | length')
  [ "$BOZUK" != "0" ] && { echo "HATA satir $SATIR: $BOZUK mesajda harici_id/zaman eksik ya da gonderen gecersiz"; HATA=1; }
  TOPLAM_MESAJ=$((TOPLAM_MESAJ + $(printf '%s' "$L" | jq -r '.mesajlar|length')))
done < "$DOSYA"

[ "$HATA" != "0" ] && { echo "== DOGRULAMA BASARISIZ - hicbir sey yazilmadi =="; exit 1; }
echo "Dogrulama tamam: $SATIR konusma, $TOPLAM_MESAJ mesaj."
[ "$KURU" = "--kuru" ] && { echo "(kuru calisma - yazilmadi)"; exit 0; }

ONCE=$("${PG[@]}" -tAc "SELECT (SELECT count(*) FROM lcarlie.konusma)||' konusma / '||(SELECT count(*) FROM lcarlie.mesaj)||' mesaj';")

# ---------------------------------------------------------------
# 2) Yukleme - temp tablo, COPY ve upsert TEK psql oturumunda
#    (temp tablo oturumluktur; ayri cagri olursa kaybolur)
#    COPY metin biciminde "\" kacis karakteridir -> JSON'daki her \ ikiye katlanir,
#    COPY okurken tekrar teke indirir.
# ---------------------------------------------------------------
{
  echo "BEGIN;"
  echo "CREATE TEMP TABLE gelen_json (v jsonb);"
  echo "COPY gelen_json (v) FROM STDIN;"
  jq -c . "$DOSYA" | sed 's/\\/\\\\/g'
  echo '\.'
  cat <<'SQL'

-- Konusmalari upsert et
INSERT INTO lcarlie.konusma (kanal, harici_id, musteri_ref, musteri_ad, notlar, sonuc, siparis_no, siparis_tutar)
SELECT v->>'kanal', v->>'harici_id', v->>'musteri_ref', v->>'musteri_ad',
       COALESCE(v->'notlar','{}'::jsonb),
       COALESCE(NULLIF(v->>'sonuc',''),'bilinmiyor'),
       NULLIF(v->>'siparis_no',''),
       NULLIF(v->>'siparis_tutar','')::numeric
FROM gelen_json
ON CONFLICT (kanal, harici_id) DO UPDATE SET
  musteri_ref   = COALESCE(EXCLUDED.musteri_ref, lcarlie.konusma.musteri_ref),
  musteri_ad    = COALESCE(EXCLUDED.musteri_ad,  lcarlie.konusma.musteri_ad),
  notlar        = lcarlie.konusma.notlar || EXCLUDED.notlar,
  sonuc         = CASE WHEN EXCLUDED.sonuc='bilinmiyor'
                       THEN lcarlie.konusma.sonuc ELSE EXCLUDED.sonuc END,
  siparis_no    = COALESCE(EXCLUDED.siparis_no, lcarlie.konusma.siparis_no),
  siparis_tutar = COALESCE(EXCLUDED.siparis_tutar, lcarlie.konusma.siparis_tutar),
  guncelleme    = now();

-- Mesajlari upsert et
INSERT INTO lcarlie.mesaj (konusma_id, harici_id, zaman, yon, gonderen, metin, ek)
SELECT k.id, m->>'harici_id', (m->>'zaman')::timestamptz,
       COALESCE(NULLIF(m->>'yon',''),
                CASE WHEN m->>'gonderen'='musteri' THEN 'gelen' ELSE 'giden' END),
       m->>'gonderen', COALESCE(m->>'metin',''), COALESCE(m->'ek','{}'::jsonb)
FROM gelen_json g
JOIN lcarlie.konusma k
  ON k.kanal = g.v->>'kanal' AND k.harici_id = g.v->>'harici_id'
CROSS JOIN LATERAL jsonb_array_elements(g.v->'mesajlar') AS m
ON CONFLICT (konusma_id, harici_id) DO UPDATE SET
  metin = EXCLUDED.metin,
  zaman = EXCLUDED.zaman,
  ek    = lcarlie.mesaj.ek || EXCLUDED.ek;

COMMIT;
SQL
} | "${PG[@]}"

SONRA=$("${PG[@]}" -tAc "SELECT (SELECT count(*) FROM lcarlie.konusma)||' konusma / '||(SELECT count(*) FROM lcarlie.mesaj)||' mesaj';")
echo
echo "ONCE : $ONCE"
echo "SONRA: $SONRA"
"${PG[@]}" -c "SELECT kanal, count(*) AS konusma, COALESCE(sum(mesaj_sayisi),0) AS mesaj FROM lcarlie.konusma GROUP BY kanal ORDER BY 1;"
