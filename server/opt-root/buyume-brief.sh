#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - BUYUME BRIEF  (CR-014)
#
# 🔴 BU BETIK HICBIR AKSIYON ALMAZ.  Reklam butcesi degistirmez, kampanya
#    durdurmaz/yayinlamaz, fiyat degistirmez, sayfa yayinlamaz, mesaj
#    gondermez. Yalniz okur, kaniti dondurur ve brief yazar.
#
# 🔴 AI/LLM CAGRISI YOK.  Tum cikarimlar deterministik SQL kuralidir;
#    core.ai_calisma_log bos kalir ve bos olmasi kanittir.
#
# Kullanim:  /opt/lcarlie/buyume-brief.sh [--sessiz]
# Cikis: 0=SUCCESS, 1=FAILED, 2=NO_DATA
# =============================================================================
set -uo pipefail

KAP="${LCARLIE_KAP:-lcarlie-postgres}"
VT="${LCARLIE_VT:-n8n}"
SURUM="${LCARLIE_BRIEF_SURUM:-CR-014}"
CIKTI="${LCARLIE_BRIEF_DOSYA:-/opt/lcarlie/durum/buyume-brief.md}"
SESSIZ=0; [ "${1:-}" = "--sessiz" ] && SESSIZ=1

sorgu() { docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -F'|' -v ON_ERROR_STOP=1; }
yaz() { [ "$SESSIZ" -eq 0 ] && echo "$@"; return 0; }

# --- 1) Kaniti dondur, bulgulari yaz ----------------------------------------
ANLIK=$(sorgu <<SQL
SELECT core.brief_uret('$SURUM');
SQL
)
if ! [[ "$ANLIK" =~ ^[0-9]+$ ]]; then
  # 🔴 Kanit dondurulamadiysa BRIEF URETILMEZ. Kanitsiz yorum yasak.
  echo "HATA: kanit anlik goruntusu alinamadi - brief URETILMEDI." >&2
  exit 1
fi

# --- 2) Brief'i uret --------------------------------------------------------
TMP=$(mktemp)
{
docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -v ON_ERROR_STOP=1 -v anlik="$ANLIK" <<'SQL'
\pset footer off
SELECT E'# L\'CARLIÉ BÜYÜME BRIEF\n';
SELECT format(E'**Kanıt anlık görüntüsü:** #%s · %s\n**Kanıt kalitesi:** **%s** (%s/12)\n\n> 🔴 Bu brief **karar vermez**. Hiçbir bütçe, kampanya, fiyat veya sayfa değiştirilmedi.\n> Tüm çıkarımlar **deterministik SQL kuralıdır** — AI/LLM çağrısı yapılmadı.\n',
              a.anlik_id, to_char(a.alindi AT TIME ZONE 'Europe/Istanbul','DD.MM.YYYY HH24:MI'),
              a.kanit_sinifi, a.kanit_puani)
  FROM core.kanit_anlik a WHERE a.anlik_id = :anlik;

SELECT E'\n## 1. COMMERCIAL SNAPSHOT\n';
SELECT format('| | Son 7 gün | Son 30 gün |%s|---|---:|---:|%s| Sipariş (iptal hariç) | %s | %s |%s| Net ciro (KDV hariç) | ₺%s | ₺%s |%s| Tahsil edilmemiş | ₺%s | ₺%s |%s| Bilinen ürün maliyeti | ₺%s | ₺%s |%s| Ölçülmüş maliyet oranı | %%%s | %%%s |%s| Reklam öncesi katkı | ₺%s | ₺%s |%s| Meta harcaması (kapsama %s) | ₺%s | ₺%s |%s| **Reklam sonrası** | **₺%s** | **₺%s** |%s| Harcama var, sipariş yok | %s gün | %s gün |%s| **Durum** | **%s** | **%s** |',
  E'\n', E'\n',
  d7.siparis, d30.siparis, E'\n',
  to_char(d7.net_ciro,'FM999990.00'), to_char(d30.net_ciro,'FM999990.00'), E'\n',
  to_char(d7.tahsil_edilmemis,'FM999990.00'), to_char(d30.tahsil_edilmemis,'FM999990.00'), E'\n',
  to_char(d7.bilinen_cogs,'FM999990.00'), to_char(d30.bilinen_cogs,'FM999990.00'), E'\n',
  coalesce(d7.cogs_olculmus_yuzde,0), coalesce(d30.cogs_olculmus_yuzde,0), E'\n',
  to_char(d7.reklam_oncesi,'FM999990.00'), to_char(d30.reklam_oncesi,'FM999990.00'), E'\n',
  d30.meta_kapsama, to_char(d7.meta_harcama,'FM999990.00'), to_char(d30.meta_harcama,'FM999990.00'), E'\n',
  to_char(d7.reklam_sonrasi,'FM999990.00'), to_char(d30.reklam_sonrasi,'FM999990.00'), E'\n',
  d7.harcamali_satissiz_gun, d30.harcamali_satissiz_gun, E'\n',
  d7.nakit_durum, d30.nakit_durum)
  FROM mart.nakit_ozet(7) d7, mart.nakit_ozet(30) d30;

SELECT E'\n## 2. WHAT CHANGED\n';
SELECT format('- %s: sipariş **%s**, harcama **₺%s**, durum **%s**',
              to_char(gun,'DD.MM'), siparis, to_char(meta_harcama_gozlenen,'FM999990'), nakit_durum)
  FROM mart.nakit_gunluk WHERE gun > current_date - 7 ORDER BY gun DESC;

SELECT E'\n## 3. PRODUCT / OFFER SIGNALS\n';
SELECT format('- **%s** — `%s` · %s adet · net ₺%s · brüt katkı ₺%s (%%%s) · maliyet: %s%s  _%s_',
              left(urun_adi,42), sinif, adet, to_char(ciro_net,'FM999990'),
              to_char(brut_marj,'FM999990'), brut_marj_yuzde, maliyet_kalitesi, E'\n', gerekce)
  FROM mart.urun_sinyal;

SELECT E'\n## 3b. UNIT ECONOMICS\n';
-- 🔴 TEK "kar" SAYISI URETILMEZ ve "alt sinir" DENMEZ (17.09.2026 semantic
--    audit): cozulmemis COGS KDV tabani katkiyi YUKARI da tasiyabilir, yani
--    tek yonlu sinir yoktur. Kanitlanabilir UST SINIR ayri kolonda basilir.
SELECT format(E'| | Son 7 gün | Son 30 gün |%s|---|---:|---:|%s| Sipariş | %s | %s |%s| — gerçekleşmiş (tahsil) | %s | %s |%s| Net ciro (KDV hariç) | ₺%s | ₺%s |%s| **Bilinen bileşen katkısı** | **₺%s** | **₺%s** |%s| Ekonomisi doğrulanmış katkı | ₺%s | ₺%s |%s| Reklam harcaması | ₺%s | ₺%s |%s| **Reklam sonrası** | **₺%s** | **₺%s** |%s| Ekonomi tamlığı | %s / %s tam | %s / %s tam |%s| **Durum** | **%s** | **%s** |',
  E'\n', E'\n',
  e7.siparis, e30.siparis, E'\n',
  e7.gerceklesmis, e30.gerceklesmis, E'\n',
  to_char(e7.net_ciro,'FM999999990.00'), to_char(e30.net_ciro,'FM999999990.00'), E'\n',
  to_char(e7.bilinen_bilesen_katkisi,'FM999999990.00'), to_char(e30.bilinen_bilesen_katkisi,'FM999999990.00'), E'\n',
  to_char(e7.dogrulanmis_katki,'FM999999990.00'), to_char(e30.dogrulanmis_katki,'FM999999990.00'), E'\n',
  to_char(e7.reklam_harcamasi,'FM999999990.00'), to_char(e30.reklam_harcamasi,'FM999999990.00'), E'\n',
  to_char(e7.reklam_sonrasi_katki,'FM999999990.00'), to_char(e30.reklam_sonrasi_katki,'FM999999990.00'), E'\n',
  e7.ekonomi_tam, e7.siparis, e30.ekonomi_tam, e30.siparis, E'\n',
  e7.ekonomi_durumu, e30.ekonomi_durumu)
  FROM mart.ekonomi_ozet(7) e7, mart.ekonomi_ozet(30) e30;

SELECT E'\n> 🔴 **"Bilinen bileşen katkısı" kâr DEĞİLDİR ve SINIR İDDİASI DEĞİLDİR.** Bilinmeyen maliyetler'
    || E' **sıfır sayılmadığı** için düşülmemiştir; gerçek katkı bundan **DÜŞÜKTÜR**.'
    || E'\n> Eksik bileşenler: **' || (SELECT eksik_bilesenler FROM mart.ekonomi_ozet(30)) || E'**'
    || E'\n> Reklam maliyeti **siparişe dağıtılmaz** — order-level atıf kurulamadı (CR-011, eşleşme 0/259).'
    || E' "Reklam sonrası" yalnız **gün grain''inde** bir karşılaştırmadır, atıflı ROAS değildir.\n';

SELECT E'\n### Ticari yaşayabilirlik\n';
SELECT format(E'- **Ekonomik tamlık:** `%s` · ekonomik doğrulanmış: **%s**%s- **Ticari yön:** `%s`%s- Scale konuşulabilir: **%s**%s%s%s  %s',
              ekonomik_tamlik, ekonomik_dogrulanmis, E'\n',
              ticari_yon, E'\n', scale_konusulabilir, E'\n', E'\n', E'\n', ifade)
  FROM mart.ticari_yasayabilirlik;
SELECT E'\n> 🔴 **Ekonomik tamlık** ile **ticari yön** ayrı kavramlardır: veri eksikken bile'
    || E' çözülmemiş bileşenlerin yönü biliniyorsa **yön kanıtlanabilir**.'
    || E'\n> `NEGATIVE_PROVEN_BY_BOUND` ≠ `ECONOMICALLY_VALIDATED` — yön kanıtlı, **tutar hâlâ bilinmiyor**.'
    || E'\n> ' || (SELECT atif_uyarisi FROM mart.ticari_yasayabilirlik) || E'\n';

SELECT E'\n### Ekonomi veri kalitesi\n';
SELECT format('- `%s` **%s** — %s _(%s)_', durum, kalem, aciklama, etki)
  FROM mart.ekonomi_veri_kalitesi;

SELECT E'\n## 4. PAID MEDIA SIGNALS\n';
-- 🔴 IKI AYRI KAPSAMA GOSTERILIR (16.09.2026 duzeltmesi). Onceki brief
--    yalniz "1/3" yaziyordu ve bu bir VERI ACIGI gibi okunuyordu. Uc hesap
--    biliniyor ama yalnizca biri reklam yayinliyor; digerleri kapsam disi.
--    Karar metrigi AKTIF kapsamadir.
-- 🔴 TERMINOLOJI KILIDI: yuzde ASLA tek basina yazilmaz. mart.meta_kapsama.etiket
--    zaten "Operational Meta Coverage: 100% (1/1 active known accounts)" uretir;
--    brief o etiketi AYNEN basar, kendi cumlesini kurmaz.
SELECT format(E'**%s**%s- Aktif operasyonel: **%s** → %s%s- Bilinen hesap (envanter): **%s** · kapsam dışı: **%s** (`INACTIVE_EXCLUDED` — reklam yayınlamıyor)%s%s',
              etiket, E'\n', aktif_kapsama, aktif_durum, E'\n',
              bilinen_kapsama, kapsam_disi, E'\n',
              CASE WHEN aktif_tam
                THEN E'\n> Bu **“Meta Business’teki tüm hesapları otomatik keşfediyoruz” demek değildir.**'
                  || E' Söylenen şey: *registry’de bilinen ve aktif sınıflandırılmış operasyonel'
                  || E' hesapların %100’ü kapsanıyor.*'
                  || E'\n> Erişilemeyen 2 hesap bir **veri kalitesi açığı değildir** — okunacak harcama yok.'
                  || E'\n> `' || kesif_riski || E'` — ' || kesif_riski_aciklama
                ELSE E'\n> 🔴 **AKTİF** hesapların tamamı okunamıyor — harcama eksik ölçülüyor olabilir.'
              END)
  FROM mart.meta_kapsama;
SELECT format('- **Son %s gün** — harcama ₺%s · gösterim %s · link tıklama %s · %s kampanya%s  Kreatif seviyesi veri: **%s** → kreatif sıralaması **yapılamaz**',
              pencere, to_char(harcama,'FM999990'), gosterim, link_tiklama, kampanya, E'\n',
              kreatif_seviyesi_veri)
  FROM mart.meta_sinyal ORDER BY pencere;
SELECT format('- Meta''nın kendi dönüşüm iddiası: ₺%s — **bizim cirumuzla toplanmaz**, atıf kurulamadığı için doğrulanamaz',
              to_char(meta_iddia_gelir,'FM999990'))
  FROM mart.meta_sinyal WHERE pencere = 30;

SELECT E'\n## 4b. ÖDEME OTORİTESİ\n';
-- 🔴 Bu bölüm 16.09.2026'da eklendi cunku brief'i okuyan, "PayTR bagli degil"
--    ifadesini "online satis bilinmiyor" diye okuyordu. Uc ayri sey var ve
--    ucu de ayri yazilir: siparis otoritesi · odeme operasyonel durumu ·
--    settlement mutabakati.
SELECT format('- **%s** → `%s`%s  %s',
              CASE alan
                WHEN 'order'                     THEN 'Sipariş otoritesi'
                WHEN 'payment_online'            THEN 'Online ödeme (operasyonel durum)'
                WHEN 'payment_offline'           THEN 'Offline/elle ödeme'
                WHEN 'settlement_reconciliation' THEN 'Settlement mutabakatı'
                ELSE alan END,
              current_connection, E'\n', left(gap, 300))
  FROM core.source_authority
 WHERE alan IN ('order','payment_online','payment_offline','settlement_reconciliation')
 ORDER BY array_position(ARRAY['order','payment_online','payment_offline','settlement_reconciliation'], alan);
SELECT E'\n> **PayTR ayrı bir satış kanalı değildir** — Wix checkout''unun ödeme sağlayıcısıdır.'
    || E'\n> Bağlı olmaması siparişi veya ciroyu `UNKNOWN` yapmaz; yalnızca **settlement mutabakatı** açığıdır.'
    || E'\n> Offline ödeme bir entegrasyon hatası değil, **tasarlanmış insan girişi** sürecidir'
    || E' (`MANUAL_CONTROLLED_INPUT`). Kayıt girilmemişse doğru ifade `MISSING_MANUAL_ENTRY`''dir.\n';

SELECT E'\n## 4c. FİYAT DURUMU (ürün bağımsız)\n';
-- 🔴 URUNE GOMULU DEGIL: core.urun_fiyat_gercegi tablosundan turer.
--    Yeni urun eklendiginde bu bolum KOD DEGISMEDEN buyur.
SELECT E'| Ürün | Base | Güncel | Durum | Wix vitrini | Karşılaştırma |\n|---|---:|---:|---|---|---|';
SELECT format('| %s | %s | %s | `%s` | `%s` | %s |',
              left(urun_adi,34),
              coalesce(base_price::text,'—'), coalesce(kampanya_fiyati::text,'—'),
              fiyat_durumu, durum, karsilastirma_izni)
  FROM mart.fiyat_gercegi WHERE fiyat_durumu <> 'UNKNOWN' ORDER BY urun_adi;
SELECT format(E'\n> 🔴 **%s/%s ürünün işletme fiyat gerçeği BEYAN EDİLMEMİŞ** (`UNKNOWN`).'
           || E' Wix vitrini bir **gözlemdir**, otorite değildir — beyan olmadan müşteriye fiyat söylenmez.'
           || E'\n> Kampanya bitişi `%s` olan ürün(ler) için fiyat **kalıcı değildir**; gönderim anında'
           || E' `mart.fiyat_gercegi` okunur, sabit kodlanmaz.',
              (SELECT count(*) FROM core.urun_fiyat_gercegi WHERE fiyat_durumu='UNKNOWN'),
              (SELECT count(*) FROM core.urun_fiyat_gercegi),
              coalesce((SELECT string_agg(DISTINCT kampanya_bitisi,', ')
                          FROM core.urun_fiyat_gercegi WHERE fiyat_durumu='CAMPAIGN'),'—'));
SELECT E'\n## 4d. FUNNEL HEALTH (CR-017)\n';
-- 🔴 EKSIK VERI SIFIR GIBI GOSTERILMEZ. "0 ATC" ancak enstrumantasyon
--    saglikliyken ve gercekten sifir gozlendiginde yazilabilir.
SELECT E'| Adım | Enstrümantasyon | Veri akışı | Gözlem | Sayı |\n|---|---|---|---|---:|';
SELECT format('| %s | `%s` | `%s` | `%s` | %s |',
              ad, enstrumantasyon, veri_akisi, gozlem_durumu,
              CASE WHEN gozlem_durumu='OBSERVED' THEN event_satiri::text
                   ELSE 'NOT_MEASURED' END)
  FROM mart.funnel_saglik ORDER BY sira;

SELECT E'\n**Geçiş oranları**\n';
SELECT format('- %s → %s: **%s**',
              ust_ad, alt_ad,
              CASE WHEN oran_durumu='HESAPLANDI' THEN '%'||oran_yuzde::text
                   ELSE 'NOT_MEASURABLE' END)
  FROM mart.funnel_orani ORDER BY ust_kod;

SELECT E'\n> 🔴 `NOT_MEASURED` **sıfır değildir.** Enstrümantasyon yoksa olay gerçekleşse bile'
    || E' ölçülmez; oran da **NOT_MEASURABLE** kalır — %0 yazmak uydurmaktır.'
    || E'\n> ' || (SELECT ifade FROM mart.ga4_siparis_mutabakat) || E'\n';

SELECT E'\n**GA4 ↔ Wix purchase mutabakatı**\n';
SELECT format('- GA4 purchase: **%s** · Wix sipariş: **%s** · eşleşen: **%s** · GA4_ONLY: **%s** · WIX_ONLY: **%s** · duplicate: **%s** → `%s`',
              ga4_purchase_sayisi, wix_siparis_sayisi, eslesen, ga4_only, wix_only, duplicate_islem, durum)
  FROM mart.ga4_siparis_mutabakat;
SELECT E'\n> GA4 **ciro otoritesi değildir.** Ticari gerçek Wix/core''dadır; GA4 yalnız davranış gözlemidir.\n';

SELECT E'\n## 5. CRO SIGNALS\n';
SELECT format('- `%s` **%s** — %s', seviye, kod, bulgu) FROM mart.cro_sinyal;

SELECT E'\n## 6. CREATIVE HYPOTHESES\n';
SELECT E'> Kreatif performans verisi **YOK**. Aşağıdakiler kazanan kreatif değil, **test edilecek varsayım**.\n> Hiçbiri mevzuat kapısından geçmeden yayına hazır sayılmaz.\n';
SELECT format('- **%s**%s  - kanıt: %s%s  - beklenen etki: %s%s  - risk: %s%s  - **yanlışlama:** %s',
              replace(baslik,' — ',E' — '), E'\n', kanit, E'\n', beklenen_etki, E'\n', risk, E'\n', yanlislama)
  FROM core.buyume_bulgu WHERE anlik_id = :anlik AND modul='KREATIF';

SELECT E'\n### Müşteri soru konuları (ölçüm: `core.tr_norm` + LIKE, her iki taraf normalize)\n';
-- 🔴 Bu DUZ string; format() degil. `%%` kacisi burada gecersiz, oldugu
--    gibi basilir. Yalnizca format() icinde `%%` yazilir.
SELECT E'| Konu | Tekil konuşma | Eşleşen mesaj | Konuşma % | Örnek (PII maskeli) |\n|---|---:|---:|---:|---|';
SELECT format('| %s | %s | %s | %%%s | %s |', konu, distinct_konusma, eslesen_mesaj,
              konusma_yuzde, replace(array_to_string(ornekler,' · '),'|','/'))
  FROM mart.soru_konu ORDER BY distinct_konusma DESC;
SELECT E'\n> Konular **örtüşür** (bir konuşma hem fiyat hem içerik sorabilir); yüzdeler toplanıp 100 etmez.\n> Veride **hiç bulunmadığı için kategori açılmayanlar:** kargo · teslimat · iade · ödeme · kapıda ödeme · gizlilik/paket (her biri 0 konuşma).\n';

SELECT E'\n## 7. MARKET / AUDIENCE / COMPETITOR SIGNALS\n';
SELECT format('- `%s` **%s** — %s _(%s)_', seviye, kod, bulgu, durum) FROM mart.pazar_sinyal;

SELECT E'\n## 8. RED TEAM CHALLENGES\n';
SELECT format('- **%s · %s** — %s', hukum, baslik, gerekce) FROM mart.red_team;

SELECT E'\n## 9. DATA GAPS\n';
SELECT format('- **%s** `%s` — %s', kalem, durum, etki)
  FROM mart.nakit_veri_kalitesi WHERE durum IN ('MISSING','TAHMIN','PARTIAL')
 ORDER BY CASE durum WHEN 'MISSING' THEN 1 WHEN 'TAHMIN' THEN 2 ELSE 3 END, kalem;

SELECT E'\n## 10. DECISIONS REQUIRING HUMAN APPROVAL\n';
SELECT E'| # | Karar | Kanıt | Beklenen etki | Risk | Kanıt kalitesi | Yanlışlama |\n|---|---|---|---|---|---|---|';
SELECT format('| %s | %s | %s | %s | %s | %s | %s |',
              row_number() OVER (ORDER BY b.bulgu_id),
              replace(b.baslik,'|','/'), replace(left(b.kanit,110),'|','/'),
              coalesce(replace(b.beklenen_etki,'|','/'),'—'),
              coalesce(replace(b.risk,'|','/'),'—'),
              coalesce(b.kanit_sinifi,'—'),
              coalesce(replace(b.yanlislama,'|','/'),'—'))
  FROM core.buyume_bulgu b
 WHERE b.anlik_id = :anlik AND b.modul IN ('URUN','META','KREATIF')
   AND coalesce(b.sinif,'') <> 'INSUFFICIENT_DATA'
 ORDER BY b.bulgu_id;

SELECT E'\n---\n';
SELECT format('**AI kullanımı:** %s çağrı · maliyet $%s — bu brief tamamen deterministik SQL ile üretildi.',
              (SELECT count(*) FROM core.ai_calisma_log),
              (SELECT coalesce(sum(maliyet_usd),0) FROM core.ai_calisma_log));
SELECT E'**Hiçbir bütçe, kampanya, fiyat, sayfa veya mesaj değiştirilmedi.**';
SQL
} > "$TMP" 2>/dev/null

if [ ! -s "$TMP" ]; then
  rm -f "$TMP"
  echo "HATA: brief bos uretildi." >&2
  exit 1
fi

mkdir -p "$(dirname "$CIKTI")"
mv "$TMP" "$CIKTI"
chmod 644 "$CIKTI"

BULGU=$(sorgu <<SQL
SELECT count(*) FROM core.buyume_bulgu WHERE anlik_id = $ANLIK;
SQL
)
MEYDAN=$(sorgu <<SQL
SELECT count(*) FROM core.buyume_bulgu WHERE anlik_id = $ANLIK AND modul='RED_TEAM' AND sinif='CHALLENGE';
SQL
)

yaz "Buyume brief yazildi: $CIKTI ($(stat -c%s "$CIKTI") bayt)"
yaz "  kanit anlik goruntusu: #$ANLIK"
yaz "  bulgu: $BULGU · red team itirazi: $MEYDAN"
exit 0
