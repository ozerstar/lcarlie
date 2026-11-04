#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - VERI KATMANI SEMASINI UYGULA  (CR-004)
#
# 🔴 Tum .sql dosyalari IDEMPOTENT yazilmistir; bu betik istendigi kadar
#    calistirilabilir. Yine de her calistirmada ONCE YEDEK alinir - sema
#    degisikligi geri alinamayan tek islem turudur.
#
# 🔴 SIRALAMA ONEMLI: core semasi ve fonksiyonlari raw cikarmasindan ONCE
#    kurulmali (raw, core.telefon_e164 gibi fonksiyonlara bagli degil ama
#    core.ayar raw-sema icinde yaratiliyor ve core semasi var olmali).
#
# Kullanim:  /opt/lcarlie/sql/raw-uygula.sh [--yedeksiz]
# =============================================================================
set -euo pipefail

KAP=lcarlie-postgres
SQL_DIZIN=/opt/lcarlie/sql
YEDEK_DIZIN=/opt/lcarlie/geri-donus

DOSYALAR=(core-sema.sql core-kimlik-fn.sql core-authority-seed.sql
          raw-sema.sql raw-cikarma.sql core-doldur.sql mart-sema.sql
          meta-harcama-sema.sql mart-harcama.sql
          # 🔴 meta-hesap-kayit.sql, mart-harcama.sql'den SONRA (raw.meta_hesap gerekir)
          #    ve mart-nakit/mart-gunluk-hazirlik/mart-ajans'tan ONCE: hepsi
          #    mart.meta_kapsama'yi okur. Kapsama paydasi artik sabit kodlu degil.
          meta-hesap-kayit.sql
          core-authority-guncelle.sql
          urun-maliyet-sema.sql mart-marj.sql
          mart-para.sql mart-hazirlik.sql
          # 🔴 mart-nakit.sql, mart-hazirlik.sql'den SONRA: mart.maliyet_kalite'ye bagimli.
          mart-nakit.sql
          mart-konusma.sql
          # COGS / UNIT ECONOMICS TRUTH LAYER
          # 🔴 cogs-truth-sema.sql: mart.siparis_kalem (mart-marj) + mart.gonderi
          #    (mart-sema) + core.maliyet_bul gerekir - ucu de yukarida kurulu.
          # 🔴 cogs-truth-agregat.sql ondan SONRA: mart.siparis_ekonomi'ye bagli.
          # 🔴 Ikisi de mart-gunluk-hazirlik.sql'den ONCE: 8. madde
          #    mart.ticari_yasayabilirlik'i okur.
          cogs-truth-sema.sql
          cogs-truth-agregat.sql
          # CR-017 GA4/Funnel Truth Layer
          # NOT: funnel-truth-sema.sql core.source_authority'yi guncelliyor ama
          #      operating-truth-yamasi.sql'den ONCE calisiyor. Cakisma YOK:
          #      o dosya 'behavior' alanina DOKUNMUYOR (ad_spend/payment_*).
          funnel-truth-sema.sql
          funnel-truth-mart.sql
          # CR-017 semantic audit yamasi: funnel-truth-*'tan SONRA (core.funnel_adim
          # ve mart.ga4_siparis_mutabakat'a bagimli). behavior satirini son o yazar.
          funnel-semantic-yamasi.sql
          # 🔴 mart-gunluk-hazirlik.sql, mart-konusma.sql'den SONRA:
          #    mart.konusma_cevapsiz'e bagimli. Ayrica mart.hazirlik (satir 1'i
          #    oradan okur), mart.maliyet_kalite ve mart.siparis_kalem gerekir -
          #    ucu de yukarida kurulmus olur.
          mart-gunluk-hazirlik.sql
          # 🔴 mart-acik-isler.sql EN SON VIEW: yukaridaki tum view'lara bagimli.
          mart-acik-isler.sql
          # 🔴 rapor-anlik-sema.sql en sonda: fonksiyonu butun view'lari okur.
          rapor-anlik-sema.sql
          # CR-014 ajans katmani: tablolar once, sinyal view'lari sonra.
          # 🔴 mart-ajans.sql, mart-nakit.sql'e (nakit_ozet) ve mart-hazirlik.sql'e
          #    (maliyet_kalite) bagimlidir; ikisi de yukarida uygulanmis olur.
          ajans-sema.sql
          mart-ajans.sql
          # CR-015 Decision Memory: karar-sema.sql, core.kanit_anlik ve
          # core.buyume_bulgu'ya FK ile bagli oldugu icin ajans-sema'dan SONRA;
          # mart-karar.sql de karar tablolarina bagli oldugu icin en sonda.
          karar-sema.sql
          mart-karar.sql
          # CR-016: eslestirme + oncelik + dedup duzeltmesi.
          # 🔴 karar-dedup-duzeltme.sql EN SON: core.karar_adaylari_uret'i
          #    yeniden tanimlar ve mart.karar_oncelik'e bagimlidir.
          mart-eslestirme.sql
          mart-oncelik.sql
          karar-dedup-duzeltme.sql
          # CR-016 kapanis yamasi (review): eslestirme metrigi, Meta ifadesi, pazar sinifi
          cr016-kapanis-yamasi.sql
          # CR-016 corrective: Meta ad-level + creative + jeton otoritesi
          meta-reklam-sema.sql
          mart-kreatif.sql
          cr016-meta-duzeltme.sql
          # 🔴 meta-kapsama-bulgusu.sql, cr016-meta-duzeltme.sql'den SONRA:
          #    ayni source_authority satirini ve ayni karar notunu guncelliyor,
          #    sonra yazan kazanir.
          #    (16.09.2026: bu satir bir sure listeden DUSMUSTU - yerel kaynak
          #     kopyasi eskiydi ve scp ile sunucudaki guncel liste ezildi.
          #     Etkisi veritabaninda zaten uygulanmisti, o yuzden fark
          #     edilmedi. Ders: uygulama listesi tek yonlu kopyalanmaz.)
          meta-kapsama-bulgusu.sql
          # 🔴 operating-truth-yamasi.sql EN SON: source_authority'yi ve karar
          #    hafizasini yeniden yazan tum yamalardan sonra calismali, yoksa
          #    duzeltmeleri onceki yamalar tarafindan EZILIR.
          operating-truth-yamasi.sql
          # Mimari dersler (Decision Memory learning katmani).
          # 🔴 core.karar'a bagimli DEGIL - ayri tablo, ayri semantik.
          #    En sonda cunku hicbir sey ona bagli degil.
          mimari-ders.sql
          # 🔴 CR-017 kapsam duzeltmesi: EN SON. mart.fiyat_gercegi ve kapsama
          #    matrisini URUN BAGIMSIZ hale getirir; operating-truth-yamasi.sql'in
          #    urune gomulu surumunu EZER (sonra yazan kazanir).
          urun-bagimsiz-yama.sql
          # 🔴 EN SON: uretim enstrumantasyon degisikliginin OLCULEN sonucu.
          #    core.sayfa_urun ve core.funnel_sayfa_kapsama'ya bagimli.
          ga4-instrumentation-yamasi.sql
          cr017-velo-durum.sql)

if [ "${1:-}" != "--yedeksiz" ]; then
  mkdir -p "$YEDEK_DIZIN"
  YEDEK="$YEDEK_DIZIN/sema-oncesi-$(date +%Y%m%d-%H%M%S).sql"
  if ! docker exec "$KAP" pg_dump -U n8n -d n8n --schema=core --schema=raw --schema=mart \
        > "$YEDEK" 2>/dev/null; then
    echo "HATA: yedek alinamadi, sema uygulanmadi." >&2
    exit 1
  fi
  echo "Yedek: $YEDEK ($(du -h "$YEDEK" | cut -f1))"
fi

# Semalar (dosyalar bunlarin var oldugunu varsayar)
docker exec -i "$KAP" psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q <<'SQL'
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS mart;
SQL

HATA=0
for d in "${DOSYALAR[@]}"; do
  yol="$SQL_DIZIN/$d"
  if [ ! -f "$yol" ]; then
    # 🔴 Eksik dosya SESSIZ GECILMEZ. "0 dosya uygulandi" basari degildir.
    echo "  EKSIK  $d  (kurulmamis - yayinla.ps1 listesini kontrol et)"
    HATA=1
    continue
  fi
  if docker exec -i "$KAP" psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q -f - < "$yol" 2>/tmp/uygula-hata; then
    echo "  ok     $d"
  else
    echo "  HATA   $d -> $(head -3 /tmp/uygula-hata | tr '\n' ' ')"
    HATA=1
  fi
done

echo
echo "=== KURULU NESNELER ==="
# 🔴 'docker exec' -i OLMADAN stdin'i konteynere GECIRMEZ: heredoc bos gider,
#    psql hicbir sey calistirmaz ve HATA DA VERMEZ. Sonuc: bos cikti + exit 0,
#    yani "dogrulama yapildi" yanilsamasi. Bu betigin ilk surumunde oldu.
NESNE=$(docker exec -i "$KAP" psql -U n8n -d n8n -tA -F'|' -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'tablo', table_schema, count(*) FROM information_schema.tables
 WHERE table_schema IN ('raw','core','mart') AND table_type='BASE TABLE'
 GROUP BY 1,2
UNION ALL
SELECT 'fonksiyon', n.nspname, count(*) FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname IN ('raw','core','mart') GROUP BY 1,2
 ORDER BY 1,2;
SQL
) || { echo "HATA: nesne sorgusu calismadi."; exit 1; }

if [ -z "$NESNE" ]; then
  echo "HATA: hicbir nesne bulunamadi - sema uygulanmamis olabilir." >&2
  exit 1
fi
echo "$NESNE" | awk -F'|' '{printf "  %-10s %-6s %s\n", $1, $2, $3}'

[ "$HATA" -eq 0 ] || { echo; echo "EN AZ BIR DOSYA UYGULANAMADI."; exit 1; }
echo
echo "Sema guncel."
