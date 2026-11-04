#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - SAGLIK TOPLAYICI
#
# CR-002 maddeleri 3, 5, 7, 9 · 15.09.2026
#
# Sistemin gercek saglik durumunu OLCER ve makine okunur kayitlar uretir.
# durum-uret.sh bu ciktiyi HTML'e cevirir; alarm.sh ile bildirim gonderilir.
#
# 🔴 SENTETIK MUSTERI ISTEGI GONDERMEZ. (CR-002 madde 5)
#    CR-001 denetiminde /webhook/whatsapp'a atilan tek bir GET'in bile
#    gercek bir calistirma kaydi urettigi gorulду. Saglik olcumu musteri
#    uc noktalarini KIRLETMEMELI: sahte konusma, sahte mesaj, sahte
#    calistirma uretmek istatistikleri bozar ve gercek trafigi gizler.
#    Bu yuzden butun olcum n8n'in KENDI veritabanindan yapilir:
#    workflow aktiflik durumu, calistirma kayitlari, zaman damgalari.
#
# 🔴 "SON 24 SAATTE HATA YOK" = HEALTHY DEGILDIR. (CR-002 madde 3)
#    Onceki durum sayfasi yalnizca status='error' sayiyordu. Hic
#    calistirma olmadiginda hata da olmaz; webhook rotasi bozulsa,
#    kanal kapansa, Meta webhook'u kesse sistem TAMAMEN SAGIR olur ve
#    gosterge "24 saatte hata yok" diye YESIL yanardi.
#
# Durum degerleri:
#   HEALTHY    calisma var, hata yok
#   NO_TRAFFIC calisma HIC yok  (normal olabilir ama HEALTHY DEGILDIR)
#   DEGRADED   hem basari hem hata var / hata orani esigin uzerinde
#   FAILED     hepsi hata / beklenen aktiflik bozuk / beklenen veri hic gelmiyor
#   UNKNOWN    olculemedi (veritabanina erisilemedi vb.)
#
# Sistem kontrolleri icin (CR-002 madde 9):
#   SUCCESS | NO_DATA | PARTIAL | FAILED
#   🔴 "0 kayit kontrol edildi" SUCCESS degildir.
#   🔴 "Kaynaga ERISILEMEDI" NO_DATA degil FAILED'dir.
#   🔴 "Kaynaga erisildi ama yeni kayit yok" NO_DATA'dir.
#
# Kullanim:
#   saglik.sh              olc, kayitlari bas, gerekirse alarm uret
#   saglik.sh --sessiz     olc ve bas, alarm URETME (elle inceleme icin)
# =============================================================================
set -uo pipefail

# 🔴 TEST EDILEBILIRLIK: her yol bu koke baglidir (BK, WEB, CONF, ALARM,
#    ALARM_LOG, CIKTI_DOSYA). Koku degistirilebilir yapmak, saglik
#    kontrollerini GERCEK uretime dokunmadan fikstur uzerinde kosmayi
#    mumkun kilar - saglik-test.sh bunu kullanir. Varsayilan degismedi.
KOK="${LCARLIE_KOK:-/opt/lcarlie}"
BK="$KOK/backup"
WEB="$KOK/durum"
CONF="$KOK/uretim-workflowlari.conf"
ALARM="$KOK/alarm.sh"
ALARM_LOG="$KOK/alarm.log"      # alarm.sh'in birincil kaydi - buradan okunur
DB=lcarlie-postgres
KONTEYNERLER="lcarlie-n8n lcarlie-postgres lcarlie-caddy"
CIKTI_DOSYA="$WEB/saglik.txt"

SESSIZ=0
for a in "$@"; do [ "$a" = "--sessiz" ] && SESSIZ=1; done

mkdir -p "$WEB" 2>/dev/null || true

# -----------------------------------------------------------------------------
# Yapilandirma - 🔴 YOKSA DEVAM ETME.
# Varsayilanlarla sessizce devam etmek, tam da bu CR'nin kapatmaya calistigi
# "sessiz basari" hatasi olurdu: yanlis workflow listesiyle uretilen yesil bir
# sayfa, hic sayfa olmamasindan daha tehlikelidir.
# -----------------------------------------------------------------------------
if [ ! -r "$CONF" ]; then
  echo "GENEL|FAILED|Yapilandirma okunamadi: $CONF"
  [ "$SESSIZ" = "0" ] && [ -x "$ALARM" ] && "$ALARM" FAILED saglik.conf \
    "Saglik yapilandirmasi okunamadi" "Dosya: $CONF" >/dev/null 2>&1
  exit 1
fi
# shellcheck disable=SC1090
. "$CONF"

PENCERE="${SAGLIK_PENCERE_SAAT:-24}"
DEG_ORAN="${DEGRADED_HATA_ORANI:-5}"

# -----------------------------------------------------------------------------
# TRAFIK SINIFLANDIRMA (CR-002.5 madde A)
#
# 🔴 REGEX ARTIK ANA KARAR MEKANIZMASI DEGIL.
#    CR-002'de siniflandirma tek basina bir red listesine dayaniyordu ve
#    kacak verdigi kanitlandi (15.09 23:37, 'sinav-*' kimlikleri 12 test
#    kaydini URETIM sayiyordu). Red listeleri her zaman geriden gelir.
#
# Oncelik:
#   1) kaydin kendi 'traffic_class' alani   (kanal kodu giriste yaziyor)
#   2) zorunlu 'test-' oneki
#   3) kimliksiz / '-'                      -> unknown
#   4) KARANTINA dosyasi                    (tarihsel, elle siniflanan)
#   5) eski desen                           (YALNIZCA geriye donuk uyum)
#   6) digerleri                            -> production
#
# 🔴 'unknown' HICBIR ZAMAN otomatik production sayilmaz ve musteri
#    metrigine girmez - ama kaybolmaz, ayri raporlanir.
# -----------------------------------------------------------------------------
KARANTINA=()
# shellcheck disable=SC1090
[ -r "${KARANTINA_DOSYA:-}" ] && . "$KARANTINA_DOSYA"

karantina_values() {
  local out="" e wf zm sf
  for e in "${KARANTINA[@]}"; do
    IFS='|' read -r wf zm sf _guven _gerekce <<<"$e"
    [ -z "${wf:-}" ] && continue
    case "$sf" in production|test|unknown) : ;; *) continue ;; esac
    # Tek tirnak iceren bir deger SQL'i bozar - bu alanlar kimlik/zaman/sabit
    # oldugu icin olamaz, yine de savunma amacli temizleniyor.
    wf="${wf//\'/}"; zm="${zm//\'/}"; sf="${sf//\'/}"
    out="$out,('$wf','$zm','$sf')"
  done
  # Bos karantina da gecerli bir VALUES uretmeli
  [ -z "$out" ] && out=",('_yok_','_yok_','_yok_')"
  printf '%s' "${out#,}"
}
KAR_VALUES="$(karantina_values)"

# <alan> yerine jsonb ogesi adi konur (e / r)
sinif_ifadesi() {
  local x="$1"
  cat <<IFADE
COALESCE(
  kar.sf,
  CASE
    WHEN COALESCE($x->>'traffic_class','') IN ('production','test','unknown')
      THEN $x->>'traffic_class'
    WHEN lower(left(COALESCE($x->>'musteri',''),5)) = '${TEST_ONEK:-test-}'
      THEN 'test'
    WHEN COALESCE($x->>'musteri','') IN ('','-')
      THEN 'unknown'
    WHEN COALESCE($x->>'musteri','') ~* '$TEST_KIMLIK_DESENI'
      THEN 'test'
    ELSE 'production'
  END)
IFADE
}

# -----------------------------------------------------------------------------
# TOPLAYICININ KENDI SAGLIGI  (CR-002 madde 8: status collector failure)
#
# 🔴 Cron olurse bunu fark edecek baska bir surec yok. Bir onceki olcum
#    dosyasinin yasina bakarak "toplayici bir sure calismamis" durumunu
#    yakalar ve alarm uretiriz. Bu, ariza SIRASINDA degil ARIZADAN SONRA
#    haber verir; gercek zamanli kapatmayi durum sayfasindaki tarayici
#    tarafli bayatlik kontrolu yapar (ikisi birlikte bosluk birakmaz).
# -----------------------------------------------------------------------------
ONCEKI_OLCUM_DK=-1
if [ -f "$CIKTI_DOSYA" ]; then
  ONCEKI_OLCUM_DK=$(( ( $(date +%s) - $(stat -c %Y "$CIKTI_DOSYA" 2>/dev/null || echo 0) ) / 60 ))
fi
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Yardimcilar
# -----------------------------------------------------------------------------
KAYITLAR=""
kayit() { KAYITLAR="${KAYITLAR}$*
"; }

# psql sarmalayici.
# 🔴 BOS SONUC ile HATA birbirinden AYRILIR: cikis kodu ayrica denetlenir.
#    Onceki durum-uret.sh '2>/dev/null' ile hatayi yutup bos string aliyordu;
#    bos string sayisal karsilastirmada beklenmedik davraniyordu.
SQL_HATA=""
sorgu() {
  local cikti rc
  cikti="$(docker exec "$DB" psql -U n8n -d n8n -tA -F'|' -v ON_ERROR_STOP=1 -c "$1" 2>&1)"
  rc=$?
  if [ $rc -ne 0 ]; then
    SQL_HATA="$(printf '%s' "$cikti" | tr '\n' ' ' | cut -c1-200)"
    return 1
  fi
  printf '%s' "$cikti"
  return 0
}

# Durum siralamasi - kotuden iyiye dogru agirlik
agirlik() {
  case "$1" in
    FAILED)     echo 5 ;;
    DEGRADED|PARTIAL) echo 4 ;;
    UNKNOWN|NO_DATA)  echo 3 ;;
    NO_TRAFFIC) echo 2 ;;
    *)          echo 1 ;;
  esac
}
GENEL_DURUM="HEALTHY"
GENEL_SEBEP=""
yukselt() {   # yukselt <durum> <sebep>
  local y_yeni y_mevcut
  y_yeni="$(agirlik "$1")"; y_mevcut="$(agirlik "$GENEL_DURUM")"
  if [ "$y_yeni" -gt "$y_mevcut" ]; then GENEL_DURUM="$1"; GENEL_SEBEP="$2"; fi
}

alarm() {     # alarm <seviye> <anahtar> <baslik> <detay>
  [ "$SESSIZ" = "1" ] && return 0
  [ -x "$ALARM" ] || return 0
  "$ALARM" "$1" "$2" "$3" "$4" >/dev/null 2>&1 || true
}

# =============================================================================
# 1) KONTEYNERLER
# =============================================================================
for c in $KONTEYNERLER; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]; then
    BASLANGIC="$(docker inspect -f '{{.State.StartedAt}}' "$c" 2>/dev/null | cut -dT -f1,2 | tr T ' ' | cut -d. -f1)"
    kayit "SYS|kapsayici.$c|SUCCESS|$BASLANGIC|calisiyor"
  else
    kayit "SYS|kapsayici.$c|FAILED|-|DURMUS"
    yukselt FAILED "$c durmus"
    alarm FAILED "sys.kapsayici.$c" "Kapsayici durdu: $c" "docker inspect: calismiyor"
  fi
done

# =============================================================================
# 2) POSTGRESQL ERISIMI  (diger tum sorgulardan ONCE)
# =============================================================================
if DB_TEST="$(sorgu 'SELECT 1;')" && [ "$DB_TEST" = "1" ]; then
  kayit "SYS|postgres.erisim|SUCCESS|1|sorgu calisiyor"
  DB_ERISIM=1
else
  kayit "SYS|postgres.erisim|FAILED|-|$SQL_HATA"
  yukselt FAILED "PostgreSQL erisilemiyor"
  alarm FAILED "sys.postgres" "PostgreSQL erisilemiyor" "$SQL_HATA"
  DB_ERISIM=0
fi

# =============================================================================
# 3) WORKFLOW SAGLIGI   (n8n API/execution bilgisi uzerinden - madde 5)
# =============================================================================
WF_SATIRLARI=""
if [ "$DB_ERISIM" = "1" ]; then
  WF_SATIRLARI="$(sorgu "
    SELECT w.id,
           CASE WHEN w.active THEN 'evet' ELSE 'hayir' END,
           COALESCE(s.calisma,0),
           COALESCE(s.hata,0),
           COALESCE(to_char(l.son_basarili,'YYYY-MM-DD HH24:MI'),''),
           COALESCE(to_char(l.son_hatali,'YYYY-MM-DD HH24:MI'),''),
           COALESCE(to_char(l.son_tetik,'YYYY-MM-DD HH24:MI'),''),
           COALESCE(ROUND(EXTRACT(EPOCH FROM (now()-l.son_tetik))/3600)::bigint, -1)
    FROM workflow_entity w
    LEFT JOIN LATERAL (
      SELECT count(*) AS calisma,
             count(*) FILTER (WHERE e.status='error') AS hata
      FROM execution_entity e
      WHERE e.\"workflowId\" = w.id
        AND e.\"startedAt\" > now() - interval '$PENCERE hours'
    ) s ON true
    LEFT JOIN LATERAL (
      SELECT max(e.\"startedAt\") FILTER (WHERE e.status='success') AS son_basarili,
             max(e.\"startedAt\") FILTER (WHERE e.status='error')   AS son_hatali,
             max(e.\"startedAt\")                                    AS son_tetik
      FROM execution_entity e WHERE e.\"workflowId\" = w.id
    ) l ON true
    ORDER BY w.id;")" || WF_SATIRLARI=""
fi

wf_alan() {   # wf_alan <id> <alan_no>
  printf '%s\n' "$WF_SATIRLARI" | awk -F'|' -v id="$1" -v n="$2" '$1==id{print $n; bulundu=1} END{if(!bulundu) print "__YOK__"}'
}

for tanim in "${WORKFLOWLAR_TANIM[@]}"; do
  IFS='|' read -r WID WAD WKANAL WROL _WBUILD _WJSON WAKTIF_OLMALI WTRAFIK WSESSIZLIK <<<"$tanim"

  if [ "$DB_ERISIM" != "1" ] || [ -z "$WF_SATIRLARI" ]; then
    kayit "WF|$WID|$WAD|$WKANAL|$WROL|UNKNOWN|?|$WAKTIF_OLMALI|-|-|-|-|-|-|veritabanina erisilemedi"
    yukselt UNKNOWN "$WAD olculemedi"
    continue
  fi

  AKTIF="$(wf_alan "$WID" 2)"
  if [ "$AKTIF" = "__YOK__" ]; then
    kayit "WF|$WID|$WAD|$WKANAL|$WROL|FAILED|yok|$WAKTIF_OLMALI|-|-|-|-|-|-|workflow veritabaninda BULUNAMADI"
    yukselt FAILED "$WAD bulunamadi"
    alarm FAILED "wf.$WID.eksik" "Workflow bulunamadi: $WAD" "ID $WID veritabaninda yok"
    continue
  fi

  CALISMA="$(wf_alan "$WID" 3)";   HATA="$(wf_alan "$WID" 4)"
  SON_BAS="$(wf_alan "$WID" 5)";   SON_HAT="$(wf_alan "$WID" 6)"
  SON_TET="$(wf_alan "$WID" 7)";   SESSIZ_SAAT="$(wf_alan "$WID" 8)"
  case "$CALISMA" in (''|*[!0-9]*) CALISMA=0 ;; esac
  case "$HATA"    in (''|*[!0-9]*) HATA=0 ;; esac
  case "$SESSIZ_SAAT" in (''|*[!0-9-]*) SESSIZ_SAAT=-1 ;; esac
  [ -z "$SON_BAS" ] && SON_BAS="-"
  [ -z "$SON_HAT" ] && SON_HAT="-"
  [ -z "$SON_TET" ] && SON_TET="-"

  DURUM="HEALTHY"; ACIKLAMA=""

  # --- 3a) Beklenen aktiflik durumu -----------------------------------------
  # 🔴 Iki yonlu kontrol. "Beklenmedik sekilde PASIF" kadar "beklenmedik
  #    sekilde AKTIF" de arizadir: yayinlama hatti 15.09'da bilerek
  #    kapatilan web sohbetini sessizce geri acabiliyordu.
  if [ "$WAKTIF_OLMALI" = "evet" ] && [ "$AKTIF" != "evet" ]; then
    DURUM="FAILED"; ACIKLAMA="YAYINDA OLMASI gerekirken pasif"
    alarm FAILED "wf.$WID.pasif" "Workflow beklenmedik sekilde pasif: $WAD" \
      "ID $WID · yapilandirmada aktif_olmali=evet · gercek durum pasif"
  elif [ "$WAKTIF_OLMALI" = "hayir" ] && [ "$AKTIF" = "evet" ]; then
    DURUM="FAILED"; ACIKLAMA="PASIF OLMASI gerekirken yayinda"
    alarm FAILED "wf.$WID.beklenmedik-aktif" "Workflow beklenmedik sekilde yayinda: $WAD" \
      "ID $WID · yapilandirmada aktif_olmali=hayir · gercek durum aktif"
  fi

  # --- 3b) BILEREK DEVRE DISI BIRAKILMIS WORKFLOW ---------------------------
  # 🔴 Bilerek kapatilmis bir workflow HEALTHY DEGILDIR (hizmet vermiyor) ama
  #    ARIZA DA DEGILDIR (istenen durum). Ilk surumde lcarlieSohbet01,
  #    devre disi olmasina ragmen "HEALTHY / 239 calistirma" gorunuyordu -
  #    cunku sayaclar kapatilmadan onceki trafigi okuyordu. Yaniltici.
  #    Bu yuzden ayri ele alinir ve GENEL durumu etkilemez.
  BEKLENEN_KAPALI=0
  if [ "$WAKTIF_OLMALI" = "hayir" ] && [ "$AKTIF" = "hayir" ]; then
    BEKLENEN_KAPALI=1
    DURUM="NO_TRAFFIC"
    ACIKLAMA="bilerek devre disi (yapilandirma: aktif_olmali=hayir)"
    kayit "WF|$WID|$WAD|$WKANAL|$WROL|$DURUM|$AKTIF|$WAKTIF_OLMALI|$CALISMA|$HATA|$SON_BAS|$SON_HAT|$SON_TET|$SESSIZ_SAAT|$ACIKLAMA"
    continue
  fi

  # --- 3c) Calistirma saglagi -----------------------------------------------
  if [ "$DURUM" != "FAILED" ]; then
    if [ "$CALISMA" -eq 0 ]; then
      # 🔴 BURASI CR-002'NIN KALBI: hic calisma yok = HEALTHY DEGIL.
      DURUM="NO_TRAFFIC"
      ACIKLAMA="son $PENCERE saatte hic calistirma yok"
      if [ "$WTRAFIK" = "evet" ] && [ "${WSESSIZLIK:-0}" -gt 0 ] 2>/dev/null; then
        if [ "$SESSIZ_SAAT" -lt 0 ] || [ "$SESSIZ_SAAT" -gt "$WSESSIZLIK" ]; then
          DURUM="FAILED"
          ACIKLAMA="trafik BEKLENIYOR ama ${SESSIZ_SAAT} saattir veri yok (esik ${WSESSIZLIK}sa)"
          alarm FAILED "wf.$WID.sessizlik" "Beklenen veri gelmiyor: $WAD" \
            "ID $WID · kanal $WKANAL · son tetik $SON_TET · esik ${WSESSIZLIK} saat"
        fi
      fi
    elif [ "$HATA" -ge "$CALISMA" ]; then
      DURUM="FAILED"
      ACIKLAMA="$CALISMA calistirmanin TAMAMI hatali"
      alarm FAILED "wf.$WID.hata" "Workflow tamamen hatali: $WAD" \
        "ID $WID · kanal $WKANAL · $HATA/$CALISMA hata · son hata $SON_HAT"
    elif [ "$HATA" -gt 0 ]; then
      ORAN=$(( HATA * 100 / CALISMA ))
      if [ "$ORAN" -ge "$DEG_ORAN" ]; then
        DURUM="DEGRADED"
        ACIKLAMA="$HATA/$CALISMA hata (%$ORAN)"
        alarm DEGRADED "wf.$WID.hata" "Workflow hata veriyor: $WAD" \
          "ID $WID · kanal $WKANAL · $HATA/$CALISMA hata (%$ORAN) · son hata $SON_HAT"
      else
        DURUM="DEGRADED"
        ACIKLAMA="$HATA/$CALISMA hata (%$ORAN, esik altinda)"
      fi
    else
      DURUM="HEALTHY"
      ACIKLAMA="$CALISMA calistirma, hata yok"
    fi
  fi

  kayit "WF|$WID|$WAD|$WKANAL|$WROL|$DURUM|$AKTIF|$WAKTIF_OLMALI|$CALISMA|$HATA|$SON_BAS|$SON_HAT|$SON_TET|$SESSIZ_SAAT|$ACIKLAMA"
  yukselt "$DURUM" "$WAD: $ACIKLAMA"
done

# =============================================================================
# 4) GECIKME DAGILIMI  (CR-002 madde 7: p50 / p95 / p99 / max)
# =============================================================================
# 🔴 Yalnizca ortalamaya bakmak yaniltiyordu: CR-001'de ortalama 3,03 sn
#    gorunurken medyan 0,44 sn, p95 ise 17,4 sn cikti. Esmanlilik=1 oldugu
#    icin p95 buyuk olcude KUYRUK BEKLEMESIDIR.
if [ "$DB_ERISIM" = "1" ]; then
  for kapsam in "pencere:AND e.\"startedAt\" > now() - interval '$PENCERE hours'" "tum:"; do
    AD="${kapsam%%:*}"; KOSUL="${kapsam#*:}"
    SATIR="$(sorgu "
      SELECT count(*),
             COALESCE(ROUND((percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (e.\"stoppedAt\"-e.\"startedAt\"))))::numeric,3),0),
             COALESCE(ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (e.\"stoppedAt\"-e.\"startedAt\"))))::numeric,3),0),
             COALESCE(ROUND((percentile_cont(0.99) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (e.\"stoppedAt\"-e.\"startedAt\"))))::numeric,3),0),
             COALESCE(ROUND(MAX(EXTRACT(EPOCH FROM (e.\"stoppedAt\"-e.\"startedAt\")))::numeric,3),0)
      FROM execution_entity e
      WHERE e.mode='webhook' AND e.\"stoppedAt\" IS NOT NULL $KOSUL;")"
    if [ $? -eq 0 ] && [ -n "$SATIR" ]; then
      ADET="$(printf '%s' "$SATIR" | cut -d'|' -f1)"
      if [ "$ADET" = "0" ]; then
        kayit "LAT|$AD|0|-|-|-|-"
      else
        kayit "LAT|$AD|$SATIR"
      fi
    else
      kayit "LAT|$AD|?|?|?|?|?"
    fi
  done
else
  kayit "LAT|pencere|?|?|?|?|?"
  kayit "LAT|tum|?|?|?|?|?"
fi

# =============================================================================
# 5) ESKALASYONLAR - URETIM ve TEST AYRI  (CR-002 madde 4)
# =============================================================================
# 🔴 HARD-CODED WORKFLOW ID YOK. Liste yapilandirmadan gelir.
# 🔴 TEST KIMLIKLERI URETIM SAYILMAZ: CR-001'de panel "14 konusma bekliyor"
#    diyordu ve 14'u de testti; ayni anda yayindaki WhatsApp'ta duran
#    1 gercek eskalasyon HIC gorunmuyordu.
ESK_URETIM_TOPLAM=0
if [ "$DB_ERISIM" = "1" ]; then
  for tanim in "${WORKFLOWLAR_TANIM[@]}"; do
    IFS='|' read -r WID WAD WKANAL WROL _a _b WAKTIF_OLMALI _c _d <<<"$tanim"
    [ "$WROL" = "kanal" ] || continue

    # 🔴 'count(*)' DEGIL 'count(e)'.
    # LEFT JOIN LATERAL bos bir diziyle eslesince TEK BIR NULL SATIR uretir;
    # count(*) onu da sayar. Ilk surumde Instagram'in hic eskalasyonu yokken
    # panel "1 donus bekleyen konusma" gosterdi. count(e) NULL saymaz.
    SINIF="$(sinif_ifadesi e)"
    SATIR="$(sorgu "
      WITH kar(wf,zm,sf) AS (VALUES $KAR_VALUES)
      SELECT
        count(e) FILTER (WHERE e IS NOT NULL AND NOT COALESCE((e->>'kapatildi')::boolean,false)
                           AND $SINIF = 'production'),
        count(e) FILTER (WHERE e IS NOT NULL AND NOT COALESCE((e->>'kapatildi')::boolean,false)
                           AND $SINIF = 'test'),
        count(e) FILTER (WHERE e IS NOT NULL AND NOT COALESCE((e->>'kapatildi')::boolean,false)
                           AND $SINIF = 'unknown'),
        count(e) FILTER (WHERE e IS NOT NULL AND COALESCE((e->>'kapatildi')::boolean,false)),
        count(e)
      FROM workflow_entity w
      LEFT JOIN LATERAL jsonb_array_elements(
             COALESCE((w.\"staticData\"::jsonb)->'global'->'eskalasyonlar','[]'::jsonb)) e ON true
      LEFT JOIN kar ON kar.wf = w.id AND kar.zm = e->>'zaman'
      WHERE w.id='$WID';")"
    if [ $? -eq 0 ] && [ -n "$SATIR" ]; then
      A_URETIM="$(printf '%s' "$SATIR" | cut -d'|' -f1)"
      case "$A_URETIM" in (''|*[!0-9]*) A_URETIM=0 ;; esac
      ESK_URETIM_TOPLAM=$(( ESK_URETIM_TOPLAM + A_URETIM ))
      kayit "ESK|$WID|$WKANAL|$SATIR"
    else
      kayit "ESK|$WID|$WKANAL|?|?|?|?"
      yukselt UNKNOWN "$WAD eskalasyonlari okunamadi"
    fi
  done
fi
if [ "$ESK_URETIM_TOPLAM" -gt 20 ]; then
  alarm DEGRADED "esk.birikme" "Donus bekleyen konusma birikti" \
    "Uretim eskalasyonu: $ESK_URETIM_TOPLAM (test kayitlari haric)"
fi

# =============================================================================
# 6) WORKFLOW HATA KAYITLARI  (CR-002 madde 2 - kanal kodlarinin yazdigi)
# =============================================================================
if [ "$DB_ERISIM" = "1" ]; then
  for tanim in "${WORKFLOWLAR_TANIM[@]}"; do
    IFS='|' read -r WID WAD WKANAL WROL _a _b _c _d _e <<<"$tanim"
    [ "$WROL" = "kanal" ] || continue
    # 🔴 count(h) - bos dizinin urettigi NULL satir sayilmamali (bkz. yukarisi).
    SATIR="$(sorgu "
      SELECT count(h),
             COALESCE(max(h->>'ts'),'-'),
             COALESCE(replace(substr(
               (array_agg(h->>'error_class' ORDER BY h->>'ts' DESC)
                  FILTER (WHERE h IS NOT NULL))[1],1,60),'|','/'),'-')
      FROM workflow_entity w
      LEFT JOIN LATERAL jsonb_array_elements(
             COALESCE((w.\"staticData\"::jsonb)->'global'->'hatalar','[]'::jsonb)) h ON true
      WHERE w.id='$WID';")"
    if [ $? -eq 0 ] && [ -n "$SATIR" ]; then
      HADET="$(printf '%s' "$SATIR" | cut -d'|' -f1)"
      case "$HADET" in (''|*[!0-9]*) HADET=0 ;; esac
      kayit "HATAKAYDI|$WID|$WKANAL|$SATIR"
      if [ "$HADET" -gt 0 ]; then
        SON_TS="$(printf '%s' "$SATIR" | cut -d'|' -f2)"
        SON_SINIF="$(printf '%s' "$SATIR" | cut -d'|' -f3)"
        alarm DEGRADED "wf.$WID.hatakaydi" "Kanal hata kaydi var: $WAD" \
          "ID $WID · kanal $WKANAL · toplam $HADET kayit · son $SON_TS · sinif $SON_SINIF"
      fi
    else
      kayit "HATAKAYDI|$WID|$WKANAL|?|-|-"
    fi
  done
fi

# =============================================================================
# 7) URETIM KONUSMA SAYIMI (test kayitlari haric)
# =============================================================================
if [ "$DB_ERISIM" = "1" ]; then
  for tanim in "${WORKFLOWLAR_TANIM[@]}"; do
    IFS='|' read -r WID WAD WKANAL WROL _a _b _c _d _e <<<"$tanim"
    [ "$WROL" = "kanal" ] || continue
    # 🔴 count(r) + 'r IS NOT NULL': aksi halde hic kaydi olmayan bir kanal
    #    "1 uretim konusmasi" gosterirdi (COALESCE(NULL,'') test desenine
    #    UYMADIGI icin uretim sayilirdi). Panelin yalan soylemesinin en
    #    sinsi yolu tam olarak budur.
    SINIF="$(sinif_ifadesi r)"
    SATIR="$(sorgu "
      WITH kar(wf,zm,sf) AS (VALUES $KAR_VALUES)
      SELECT
        count(r) FILTER (WHERE r IS NOT NULL AND $SINIF = 'production'),
        count(r) FILTER (WHERE r IS NOT NULL AND $SINIF = 'test'),
        count(r) FILTER (WHERE r IS NOT NULL AND $SINIF = 'unknown')
      FROM workflow_entity w
      LEFT JOIN LATERAL jsonb_array_elements(
             COALESCE((w.\"staticData\"::jsonb)->'global'->'kayitlar','[]'::jsonb)
          || COALESCE((w.\"staticData\"::jsonb)->'global'->'pilot','[]'::jsonb)) r ON true
      LEFT JOIN kar ON kar.wf = w.id AND kar.zm = r->>'zaman'
      WHERE w.id='$WID';")"
    [ $? -eq 0 ] && [ -n "$SATIR" ] && kayit "KONUSMA|$WID|$WKANAL|$SATIR" || kayit "KONUSMA|$WID|$WKANAL|?|?|?"
  done
fi

# =============================================================================
# 8) YEDEKLEME
# =============================================================================
SON_LOG="$(ls -1t "$BK"/log/backup-*.log 2>/dev/null | head -n1 || true)"
if [ -n "${SON_LOG:-}" ] && [ -f "$SON_LOG" ]; then
  # 🔴 YALNIZCA 'tam' CALISMA GECERLIDIR.
  #    Her yayinlamada calisan 'backup.sh --yerel' Drive'a bilerek yuklemez
  #    ve neredeyse her zaman BASARILI biter. Log'un SON satirina bakmak,
  #    gece yedegi basarisiz olsa bile gun icindeki ilk yayinlamadan sonra
  #    gostergeyi yesile cevirirdi - arizanin uzerini orterdi.
  #    Bu yuzden 'tam' etiketli son satir esas alinir.
  SON_SATIR="$(grep -E 'Yedekleme bitti: .*\(tam\)' "$SON_LOG" | tail -n1 || echo '')"
  if [ -z "$SON_SATIR" ]; then
    # Geriye donuk uyum: etiketsiz eski satirlar (CR-002 oncesi).
    SON_SATIR="$(grep 'Yedekleme bitti' "$SON_LOG" | grep -v '(yerel)' | tail -n1 || echo '')"
  fi
  SON_ZAMAN="$(printf '%s' "$SON_SATIR" | grep -oE '\[[^]]+\]' | tr -d '[]' || echo '?')"
  if printf '%s' "$SON_SATIR" | grep -q 'BASARILI'; then
    kayit "SYS|yedek.sonuc|SUCCESS|$SON_ZAMAN|son calisma basarili"
    alarm COZULDU "backup.sonuc" "Yedekleme tekrar basarili" "Son calisma: $SON_ZAMAN"
  elif [ -z "$SON_SATIR" ]; then
    # Log var ama 'bitti' satiri yok -> yarida kalmis olabilir. NO_DATA DEGIL.
    kayit "SYS|yedek.sonuc|FAILED|-|log var ama sonuc satiri yok (yarida kalmis olabilir)"
    yukselt FAILED "Yedekleme sonucu belirsiz"
    alarm FAILED "backup.sonuc" "Yedekleme sonucu belirsiz" "Log: $SON_LOG - 'Yedekleme bitti' satiri yok"
  else
    kayit "SYS|yedek.sonuc|FAILED|$SON_ZAMAN|son calisma BASARISIZ"
    yukselt FAILED "Yedekleme basarisiz"
    alarm FAILED "backup.sonuc" "Yedekleme BASARISIZ" "Son calisma: $SON_ZAMAN · Log: $SON_LOG"
  fi

  # OLCUM DUZELTILDI: aktarim IKI ayri cumleyle loglanir.
  #   asil tur  : "Harici depolamaya aktarildi ve DOGRULANDI"
  #   telafi turu: "Telafi sirasinda bu gecenin yedegi de aktarildi"
  # Yalniz birincisi araninca, telafiyle kurtarilan geceler "aktarim yok"
  # sayiliyor ve dosya Drive'da dururken saat basi FAILED alarmi gidiyordu.
  SON_DRIVE="$(grep -hE 'Harici depolamaya aktarildi|Telafi sirasinda bu gecenin yedegi de aktarildi' "$BK"/log/backup-*.log 2>/dev/null \
               | tail -n1 | grep -oE '\[[^]]+\]' | tr -d '[]' || true)"
  if [ -n "${SON_DRIVE:-}" ]; then
    DRIVE_YAS=$(( ( $(date +%s) - $(date -d "$SON_DRIVE" +%s 2>/dev/null || echo 0) ) / 3600 ))
    if [ "$DRIVE_YAS" -gt "${DRIVE_ESIK_SAAT:-26}" ]; then
      kayit "SYS|yedek.drive|FAILED|${DRIVE_YAS}sa|off-site aktarim ${DRIVE_YAS} saattir yok"
      yukselt FAILED "Drive aktarimi ${DRIVE_YAS} saattir yok"
      alarm FAILED "backup.drive" "Off-site yedek aktarilmiyor" \
        "Drive'a son aktarim: $SON_DRIVE (${DRIVE_YAS} saat once) · esik ${DRIVE_ESIK_SAAT:-26} saat"
    else
      kayit "SYS|yedek.drive|SUCCESS|${DRIVE_YAS}sa|$SON_DRIVE"
      alarm COZULDU "backup.drive" "Off-site yedek tekrar calisiyor" "Son aktarim: $SON_DRIVE"
    fi
  else
    kayit "SYS|yedek.drive|FAILED|-|Drive'a HIC aktarilmadi"
    yukselt FAILED "Drive'a hic aktarilmadi"
    alarm FAILED "backup.drive" "Off-site yedek hic alinmamis" "backup loglarinda aktarim kaydi yok"
  fi
else
  # 🔴 Log YOK = "yedek alindi mi bilinmiyor" = FAILED. NO_DATA degil.
  kayit "SYS|yedek.sonuc|FAILED|-|yedekleme logu bulunamadi"
  kayit "SYS|yedek.drive|FAILED|-|yedekleme logu bulunamadi"
  yukselt FAILED "Yedekleme logu yok"
  alarm FAILED "backup.log" "Yedekleme logu bulunamadi" "Dizin: $BK/log"
fi

SON_DOSYA="$(ls -1t "$BK"/archive/*.tgz.enc 2>/dev/null | head -n1 || true)"
if [ -n "${SON_DOSYA:-}" ]; then
  YAS_SAAT=$(( ( $(date +%s) - $(stat -c %Y "$SON_DOSYA") ) / 3600 ))
  ADET="$(ls -1 "$BK"/archive/*.tgz.enc 2>/dev/null | wc -l)"
  BOYUT="$(du -h "$SON_DOSYA" 2>/dev/null | cut -f1)"
  if [ "$YAS_SAAT" -gt "${YEDEK_ESIK_SAAT:-26}" ]; then
    kayit "SYS|yedek.yas|FAILED|${YAS_SAAT}sa|$ADET adet, son $BOYUT"
    yukselt FAILED "Son yedek ${YAS_SAAT} saatlik"
    alarm FAILED "backup.yas" "Yedek eskidi" "Son yedek ${YAS_SAAT} saat once alindi"
  else
    kayit "SYS|yedek.yas|SUCCESS|${YAS_SAAT}sa|$ADET adet, son $BOYUT"
  fi
else
  kayit "SYS|yedek.yas|FAILED|-|arsivde yedek dosyasi yok"
  yukselt FAILED "Yedek dosyasi yok"
fi

if [ -f "$BK/son-test.txt" ]; then
  T_SATIR="$(cat "$BK/son-test.txt" 2>/dev/null)"
  # OLCUM DUZELTILDI: son-test.txt UC alanli (zaman|SONUC|mod).
  # "##*|" SON alani alir, yani calisma MODUNU ("izole") sonuc sanar.
  # Dosyada BASARILI yazarken alarm "Sonuc: izole" deyip FAILED
  # uretiyordu. cut -f2 iki alanli eski satirlarda da dogrudur.
  T_ZAMAN="${T_SATIR%%|*}"
  T_SONUC="$(printf '%s' "$T_SATIR" | cut -d"|" -f2)"
  T_GUN=$(( ( $(date +%s) - $(date -d "$T_ZAMAN" +%s 2>/dev/null || echo 0) ) / 86400 ))
  if [ "$T_SONUC" != "BASARILI" ]; then
    kayit "SYS|yedek.geritest|FAILED|${T_GUN}g|son test BASARISIZ"
    yukselt FAILED "Geri yukleme testi basarisiz"
    alarm FAILED "backup.geritest" "Geri yukleme testi BASARISIZ" "Zaman: $T_ZAMAN · Sonuc: $T_SONUC"
  elif [ "$T_GUN" -gt "${GERI_TEST_ESIK_GUN:-40}" ]; then
    kayit "SYS|yedek.geritest|FAILED|${T_GUN}g|${T_GUN} gundur calismadi"
    yukselt FAILED "Geri yukleme testi ${T_GUN} gundur yok"
    alarm FAILED "backup.geritest" "Geri yukleme testi calismiyor" "Son basarili test ${T_GUN} gun once"
  else
    kayit "SYS|yedek.geritest|SUCCESS|${T_GUN}g|$T_ZAMAN"
  fi
else
  # 🔴 Hic calismamis bir dogrulama testi "sari uyari" degil ARIZADIR:
  #    yedeklerin geri yuklenebildigi HIC kanitlanmamis demektir.
  kayit "SYS|yedek.geritest|FAILED|-|hic calismamis - yedekler dogrulanmamis"
  yukselt FAILED "Geri yukleme testi hic calismamis"
fi

# =============================================================================
# 9) DISK / SERTIFIKA / DURUM TAZELIGI
# =============================================================================
DISK_YUZDE="$(df / | awk 'NR==2{print $5}' | tr -d '%')"
DISK_TXT="$(df -h / | awk 'NR==2{print $3" / "$2" ("$5")"}')"
case "$DISK_YUZDE" in (''|*[!0-9]*) DISK_YUZDE=0 ;; esac
if [ "$DISK_YUZDE" -gt "${DISK_KRITIK_YUZDE:-85}" ]; then
  kayit "SYS|disk|FAILED|$DISK_TXT|kritik seviye"
  yukselt FAILED "Disk %$DISK_YUZDE"
  alarm FAILED "sys.disk" "Disk kritik seviyede" "Kullanim: $DISK_TXT"
elif [ "$DISK_YUZDE" -gt "${DISK_UYARI_YUZDE:-70}" ]; then
  kayit "SYS|disk|PARTIAL|$DISK_TXT|uyari seviyesi"
  yukselt PARTIAL "Disk %$DISK_YUZDE"
  alarm UYARI "sys.disk" "Disk uyari seviyesinde" "Kullanim: $DISK_TXT"
else
  kayit "SYS|disk|SUCCESS|$DISK_TXT|"
  alarm COZULDU "sys.disk" "Disk normale dondu" "Kullanim: $DISK_TXT"
fi

# Bellek: VMware balloon nedeniyle 'used' yaniltici - balloon ayrica raporlanir
BELLEK="$(free -h | awk 'NR==2{print $3" / "$2}')"
BALON="$(vmware-toolbox-cmd stat balloon 2>/dev/null || echo '-')"
kayit "SYS|bellek|SUCCESS|$BELLEK|balloon=$BALON"

SON_GUN="$(echo | openssl s_client -connect n8n.lcarlie.shop:443 -servername n8n.lcarlie.shop 2>/dev/null \
  | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo '')"
if [ -n "$SON_GUN" ]; then
  KALAN=$(( ( $(date -d "$SON_GUN" +%s) - $(date +%s) ) / 86400 ))
  if [ "$KALAN" -lt "${SERTIFIKA_KRITIK_GUN:-10}" ]; then
    kayit "SYS|sertifika|FAILED|${KALAN}g|yenilenmeli"
    yukselt FAILED "Sertifika $KALAN gun"
    alarm FAILED "sys.sertifika" "TLS sertifikasi bitmek uzere" "$KALAN gun kaldi"
  elif [ "$KALAN" -lt "${SERTIFIKA_UYARI_GUN:-25}" ]; then
    kayit "SYS|sertifika|PARTIAL|${KALAN}g|yakinda yenilenecek"
  else
    kayit "SYS|sertifika|SUCCESS|${KALAN}g|"
  fi
else
  # 🔴 Okunamadi = FAILED. "Bilinmiyor"u yesil gostermek riski gizler.
  kayit "SYS|sertifika|FAILED|-|okunamadi"
  yukselt FAILED "Sertifika okunamadi"
fi

# =============================================================================
# 10) ALARM HATTININ KENDISI  (madde 8: alarm basarisiz olursa gorunur olsun)
# =============================================================================
GONDERILEMEDI="$KOK/alarm-gonderilemedi.log"
# 🔴 GECMISTEKI BASARISIZLIK KALICI ARIZA DEGILDIR.
#
# Ilk surum yalnizca "gonderilemedi dosyasi bos mu" diye bakiyordu. Dosya
# hicbir zaman temizlenmedigi icin, e-posta duzeldikten SONRA bile panel
# sonsuza kadar "Alarm e-postasi gonderilemiyor / FAILED" diyecekti.
# 15.09.2026'da tam bu oldu: kurulum tamamlandi, mail 250 OK ile teslim
# edildi, panel yine de PARTIAL gosterdi.
#
# Bu, bu CR'nin duzeltmeye calistigi hatanin AYNA GORUNTUSU: once panel
# ariza varken yesil gosteriyordu, simdi ariza yokken kirmizi gosteriyor.
# Ikisi de gostergeye olan guveni yok eder - ikincisi uyari korlugu yaratir.
#
# Dogru olcu: SON BASARISIZ gonderim mi daha yeni, SON BASARILI gonderim mi?
SON_BASARISIZ=""
SON_BASARILI=""
[ -f "$GONDERILEMEDI" ] && [ -s "$GONDERILEMEDI" ] && \
  SON_BASARISIZ="$(tail -n1 "$GONDERILEMEDI" 2>/dev/null | cut -d'|' -f1)"
[ -f "$ALARM_LOG" ] && \
  SON_BASARILI="$(grep 'posta=gonderildi' "$ALARM_LOG" 2>/dev/null | tail -n1 | cut -d'|' -f1)"

zaman_sn() { [ -n "${1:-}" ] && date -d "$1" +%s 2>/dev/null || echo 0; }

# 🔴 KOR NOKTA KAPATILIYOR: yukaridaki olcu yalnizca GERCEK gonderimleri
#    gorebiliyordu. Sistem saglikliysa yeni gonderim olmaz; son olay bir
#    basarisizlik olarak kalir ve gosterge sonsuza kadar kirmizi durur.
#    21.09.2026'da iki gonderim zaman asimina ugradi, ertesi sabah SMTP
#    2 saniyede 250 OK veriyordu, panel yine de FAILED diyordu.
#
#    posta-yoklama.sh baglanip kimlik dogrular ve QUIT der - MAIL ATMAZ.
#    Boylece "calisiyor" bilgisi gercek bir ariza beklemeden olculur.
#    Kendi icinde saatlik kisitlamasi var, her 15 dakikada bir Yandex'e
#    giris yapilmaz.
YOKLAMA_LOG="$KOK/alarm-yoklama.log"
[ -x "$KOK/posta-yoklama.sh" ] && "$KOK/posta-yoklama.sh" >/dev/null 2>&1
SON_YOKLAMA=""
[ -f "$YOKLAMA_LOG" ] && \
  SON_YOKLAMA="$(grep '|OK|' "$YOKLAMA_LOG" 2>/dev/null | tail -n1 | cut -d'|' -f1)"

BZ="$(zaman_sn "$SON_BASARISIZ")"
IZ="$(zaman_sn "$SON_BASARILI")"
YZ="$(zaman_sn "$SON_YOKLAMA")"
# Basarili yoklama, basarili gonderim kadar gecerli bir kanittir: ikisi de
# "SMTP su anda kimligimizi kabul ediyor" demektir.
if [ "$YZ" -gt "$IZ" ] 2>/dev/null; then
  IZ="$YZ"
  SON_BASARILI="$SON_YOKLAMA (yoklama)"
fi

if [ -z "$SON_BASARISIZ" ]; then
  if [ -n "$SON_BASARILI" ]; then
    kayit "ALARMPOSTA|SUCCESS|0|son basarili gonderim $SON_BASARILI"
  else
    # 🔴 Hic gonderim denemesi olmamis: bu SUCCESS degil NO_DATA'dir.
    #    "Hic denenmedi" ile "denendi ve calisti" ayni sey degil.
    kayit "ALARMPOSTA|NO_DATA|0|henuz hic alarm e-postasi gonderilmedi"
  fi
elif [ "$IZ" -gt "$BZ" ]; then
  GADET="$(wc -l <"$GONDERILEMEDI" 2>/dev/null || echo 0)"
  kayit "ALARMPOSTA|SUCCESS|$GADET|duzeldi - son basarili $SON_BASARILI (gecmiste $GADET basarisiz)"
else
  GADET="$(wc -l <"$GONDERILEMEDI" 2>/dev/null || echo 0)"
  GSON="$(tail -n1 "$GONDERILEMEDI" 2>/dev/null | cut -d'|' -f1,5 | tr '|' ' ')"
  # Alarm e-postasi gitmiyorsa sistem "haber veriyorum" sanirken kimse
  # haber almiyor - sessiz ariza sinifi, panelde acikca gorunmeli.
  kayit "ALARMPOSTA|FAILED|$GADET|$GSON"
  yukselt PARTIAL "Alarm e-postasi gonderilemiyor"
fi

# --- Ticari olcum hattinin tazeligi  (CR-008 · denetim bulgusu) --------------
#
# 🔴 "HIC CALISMAMA" DURUMUNU SUNUCU TARAFINDA GOREN KIMSE YOKTU.
#    Tum alarmlar "bir sey oldu" uzerine kuruluydu. 08:30 cron'u hic
#    calismazsa (flock takili kalir, konteyner duser, betik silinir) ne yeni
#    yukleme kaydi olusur ne alarm; ticari panel dunku haliyle durur ve kimse
#    sayfayi ACMADIKCA "bayat" bile demez. Yani olcum hatti SESSIZCE olebilir.
#    Panel bunu kaynak bazinda gosteriyordu ama yalniz TARAYICIDA; ayni soru
#    sunucu tarafinda da sorulmali.
TICARI_YAS="$(docker exec "$DB" psql -U n8n -d n8n -tAc \
  "SELECT coalesce(round(extract(epoch FROM now()-max(bitis))/3600.0)::int, -1) FROM raw.yukleme_log" \
  2>/dev/null | tr -d '[:space:]')"
if ! printf '%s' "$TICARI_YAS" | grep -qE '^-?[0-9]+$'; then
  kayit "SYS|ticari.tazelik|NO_DATA|-|raw.yukleme_log okunamadi"
elif [ "$TICARI_YAS" -lt 0 ]; then
  kayit "SYS|ticari.tazelik|NO_DATA|-|hic yukleme kaydi yok"
elif [ "$TICARI_YAS" -gt 30 ]; then
  kayit "SYS|ticari.tazelik|FAILED|${TICARI_YAS}sa|ticari olcum hatti durmus olabilir"
  yukselt PARTIAL "Ticari olcum ${TICARI_YAS} saattir tazelenmedi"
  alarm FAILED "ticari.tazelik" "Ticari olcum hatti durmus olabilir" \
    "Son yukleme ${TICARI_YAS} saat once · esik 30 saat · cron: 30 8 * * * ticari-kontrol.sh"
else
  kayit "SYS|ticari.tazelik|SUCCESS|${TICARI_YAS}sa|ticari olcum guncel"
fi

# --- Toplayicinin kendi calisma surekliligi ----------------------------------
if [ "$ONCEKI_OLCUM_DK" -lt 0 ]; then
  kayit "SYS|toplayici|NO_DATA|-|ilk olcum (onceki kayit yok)"
elif [ "$ONCEKI_OLCUM_DK" -gt "${DURUM_BAYATLIK_DK:-45}" ]; then
  kayit "SYS|toplayici|FAILED|${ONCEKI_OLCUM_DK}dk|onceki olcumden bu yana bosluk var"
  yukselt PARTIAL "Durum toplayici ${ONCEKI_OLCUM_DK} dk calismamis"
  alarm DEGRADED "sys.toplayici" "Durum toplayici bir sure calismadi" \
    "Onceki olcum ${ONCEKI_OLCUM_DK} dakika once · esik ${DURUM_BAYATLIK_DK:-45} dk · cron: /etc/cron.d/lcarlie-durum"
else
  kayit "SYS|toplayici|SUCCESS|${ONCEKI_OLCUM_DK}dk|duzenli calisiyor"
fi

# =============================================================================
# 10c) KIRMIZI TAKIM KURULU  (22.09.2026 · konsey yeter sayisi)
# =============================================================================
# 🔴 KAYIT TUTMAK OGRENMEK DEGILDIR.
#    Kurul her karar icin en az iki bagimsiz gorus ister. 22.09'da
#    olculdu: dort saglayicidan yalnizca biri donuyordu ve her karar
#    "INSUFFICIENT_EVIDENCE" ile geciyordu. Sebep kayitliydi
#    (ai_red_team_attempt.failover_reason) ama hicbir ekranda yoktu;
#    gemini ALTI GUNDUR 'not configured' duserken kimse gormedi.
#
# 🔴 BU KONTROL ALARM/E-POSTA URETMEZ (alarm cagrisi YOK). Sahip zaten
#    posta selinden sikayetciydi. Karar incelenmeden gecmis olmasi
#    onemlidir ama gosterge olarak onemlidir; gelen kutusu olarak degil.
if [ -x "$KOK/ai-saglayici-tani.sh" ]; then
  KONSEY_SATIR="$("$KOK/ai-saglayici-tani.sh" --satir 2>/dev/null)"
  if [ -n "$KONSEY_SATIR" ]; then
    kayit "$KONSEY_SATIR"
    case "$KONSEY_SATIR" in
      KONSEY\|DEGRADED*)
        yukselt PARTIAL "Kirmizi takim kurulu yeter sayiya ulasamiyor" ;;
    esac
  fi
fi

# =============================================================================
# 10b) SYSTEMD BIRIMLERI  (03.11.2026)
# =============================================================================
# 🔴 NEDEN: lcarlie-meta-kuyruk-yukle 26.10-03.11 arasinda DAKIKADA BIR
#    coktu (8 gunde ~11.000 kez) ve gelen WhatsApp mesajlari ambara hic
#    girmedi. Bu betik konteynerlere, workflow'lara ve yedege bakiyordu
#    ama systemd birimlerine bakmiyordu; ariza hicbir ekrana dusmedi.
#    Artik "failed" durumdaki her lcarlie-/jarvis-/icaz- birimi alarm
#    uretir (dedup alarm.sh'ta), duzelen birim COZULDU ile kapanir.
# 🔸 dagitim-ayrisma bilerek haric: o birim cokmez, fark RAPORLAR (exit 2).
BIRIM_DURUM="$KOK/saglik-birim.durum"
BIRIM_ONCE="$(cat "$BIRIM_DURUM" 2>/dev/null || true)"
BIRIM_SIMDI="$(systemctl list-units --state=failed --no-legend --plain 2>/dev/null \
  | awk '{print $1}' | grep -E '^(lcarlie|jarvis|icaz)-' \
  | grep -v '^lcarlie-dagitim-ayrisma' | sort -u)"
BIRIM_SAYI=0
for b in $BIRIM_SIMDI; do
  BIRIM_SAYI=$((BIRIM_SAYI + 1))
  SON_HATA="$(journalctl -u "$b" -n 30 --no-pager -o cat 2>/dev/null \
    | grep -iE 'error|hata|traceback|exception|failed|timeout' | grep -vE '^Failed to start|Failed with result|Main process exited' \
    | tail -1 | cut -c1-200)"
  kayit "SYS|birim|FAILED|$b|${SON_HATA:-sebep okunamadi}"
  alarm FAILED "sys.birim.$b" "Zamanlanmis is cokuyor: $b" "${SON_HATA:-journalctl -u $b}"
done
for b in $BIRIM_ONCE; do
  printf '%s\n' "$BIRIM_SIMDI" | grep -qx "$b" || \
    alarm COZULDU "sys.birim.$b" "Zamanlanmis is duzeldi: $b" "artik failed degil"
done
printf '%s\n' "$BIRIM_SIMDI" > "$BIRIM_DURUM" 2>/dev/null || true
if [ "$BIRIM_SAYI" -gt 0 ]; then
  yukselt DEGRADED "$BIRIM_SAYI zamanlanmis is cokmus durumda"
else
  kayit "SYS|birim|OK|failed birim yok"
fi

# =============================================================================
# 11) GENEL DURUM
# =============================================================================
[ -z "$GENEL_SEBEP" ] && GENEL_SEBEP="tum kontroller normal"
KAYITLAR="GENEL|$GENEL_DURUM|$GENEL_SEBEP
${KAYITLAR}OLCUM|$(date -Is)|pencere=${PENCERE}sa
"

printf '%s' "$KAYITLAR" | tee "$CIKTI_DOSYA" 2>/dev/null || printf '%s' "$KAYITLAR"
exit 0
