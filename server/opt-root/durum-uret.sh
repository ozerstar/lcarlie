#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - DURUM SAYFASI URETICISI  (v2 - CR-002)
#
# Cron ile 15 dakikada bir calisir.
#
# 🔴 NE DEGISTI (CR-002 madde 4):
#
# 1) HARD-CODED WORKFLOW ID KALDIRILDI.
#    Onceki hali eskalasyonlari "WHERE w.id='lcarlieSohbet01'" ile
#    sayiyordu. O workflow 15.09'da devre disi birakildi; sabit kaldi.
#    Sonuc: panel OLU workflow'un 14 test kaydini "bekleyen konusma"
#    diye gosterirken, YAYINDAKI WhatsApp'ta duran 1 GERCEK eskalasyonu
#    hic gostermiyordu. Iki yonde birden yanlis bilgi.
#    Artik liste /opt/lcarlie/uretim-workflowlari.conf'tan gelir.
#
# 2) "24 SAATTE HATA YOK" ARTIK YESIL DEGIL.
#    Hic calistirma yoksa hata da olmaz. Webhook rotasi bozulsa sistem
#    tamamen sagir olur ve eski panel "her sey yolunda" derdi.
#    Artik NO_TRAFFIC ayri bir durum ve HICBIR ZAMAN saglikli sayilmaz.
#
# 3) TEST KAYITLARI URETIM SAYILMAZ. Kimlik deseni yapilandirmada.
#
# 4) WhatsApp ve Instagram AYRI satirlarda; her biri icin son basarili
#    calistirma, son hatali calistirma ve son tetik zamani gosterilir.
#
# 5) SAYFANIN KENDI TAZELIGI tarayicida kontrol edilir. Toplayici olurse
#    sunucu tarafinda bunu fark edecek kimse yok; sayfayi acan kisi
#    yine de bayat veriye bakmamali. (madde 8: status collector failure)
#
# Olcum isi bu betikte DEGIL - saglik.sh'te. Burasi yalnizca gosterim.
# =============================================================================
set -uo pipefail

KOK=/opt/lcarlie
WEB="$KOK/durum"
CONF="$KOK/uretim-workflowlari.conf"
SAGLIK="$KOK/saglik.sh"
ALARM_LOG="$KOK/alarm.log"
mkdir -p "$WEB"

# shellcheck disable=SC1090
if [ -r "$CONF" ]; then . "$CONF"; else
  DURUM_BAYATLIK_DK=45
fi

# --- Olcumu al ---------------------------------------------------------------
if [ -x "$SAGLIK" ]; then
  KAYIT="$("$SAGLIK" 2>/dev/null)"
else
  KAYIT="GENEL|UNKNOWN|saglik.sh bulunamadi"
fi
[ -z "$KAYIT" ] && KAYIT="GENEL|UNKNOWN|saglik.sh cikti uretmedi"

al() { printf '%s\n' "$KAYIT" | awk -F'|' -v t="$1" '$1==t'; }
alan() { printf '%s' "$1" | cut -d'|' -f"$2"; }

kacis() { printf '%s' "${1:-}" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'; }

# --- Durum rozetleri ---------------------------------------------------------
# 🔴 BES DURUM BIRBIRINDEN AYRI RENKTE. NO_TRAFFIC bilerek YESIL DEGIL:
#    "veri gelmiyor" bir bilgi durumudur, saglik beyani degildir.
rozet() {
  case "$1" in
    HEALTHY)    echo '<span class="d ok">HEALTHY</span>' ;;
    SUCCESS)    echo '<span class="d ok">SUCCESS</span>' ;;
    NO_TRAFFIC) echo '<span class="d nt">NO_TRAFFIC</span>' ;;
    NO_DATA)    echo '<span class="d nt">NO_DATA</span>' ;;
    DEGRADED)   echo '<span class="d dg">DEGRADED</span>' ;;
    PARTIAL)    echo '<span class="d dg">PARTIAL</span>' ;;
    UYARI)      echo '<span class="d dg">UYARI</span>' ;;
    FAILED)     echo '<span class="d fl">FAILED</span>' ;;
    # Alarm gecmisi satirlarinda bu iki seviye de geciyor; taninmazsa
    # hepsi UNKNOWN gorunuyordu ve "cozuldu" bilgisi ariza gibi okunuyordu.
    COZULDU)    echo '<span class="d ok">COZULDU</span>' ;;
    BILGI)      echo '<span class="d nt">BILGI</span>' ;;
    *)          echo '<span class="d un">UNKNOWN</span>' ;;
  esac
}

GENEL_SATIR="$(al GENEL | head -n1)"
GENEL_DURUM="$(alan "$GENEL_SATIR" 2)"
GENEL_SEBEP="$(alan "$GENEL_SATIR" 3)"
[ -z "$GENEL_DURUM" ] && GENEL_DURUM="UNKNOWN"

case "$GENEL_DURUM" in
  HEALTHY)    RENK="#16a34a"; BASLIK="HEALTHY - tum kontroller normal" ;;
  NO_TRAFFIC) RENK="#0369a1"; BASLIK="NO_TRAFFIC - sistem ayakta, veri akmiyor" ;;
  DEGRADED|PARTIAL) RENK="#d97706"; BASLIK="DEGRADED - kismi ariza" ;;
  FAILED)     RENK="#dc2626"; BASLIK="FAILED - mudahale gerekiyor" ;;
  *)          RENK="#7c3aed"; BASLIK="UNKNOWN - durum olculemedi" ;;
esac

# --- Kanallar ----------------------------------------------------------------
esk_alan() { al ESK | awk -F'|' -v id="$1" -v n="$2" '$2==id{print $n}'; }
hata_alan() { al HATAKAYDI | awk -F'|' -v id="$1" -v n="$2" '$2==id{print $n}'; }
kon_alan() { al KONUSMA | awk -F'|' -v id="$1" -v n="$2" '$2==id{print $n}'; }

KANAL_KART=""
ALTAKIS_SATIR=""
ESK_URETIM_TOPLAM=0
ESK_BILINMEYEN_TOPLAM=0
while IFS= read -r satir; do
  [ -z "$satir" ] && continue
  WID="$(alan "$satir" 2)";    WAD="$(alan "$satir" 3)"
  WKANAL="$(alan "$satir" 4)"; WROL="$(alan "$satir" 5)"
  WDURUM="$(alan "$satir" 6)"; WAKTIF="$(alan "$satir" 7)"
  WOLMALI="$(alan "$satir" 8)"
  WCAL="$(alan "$satir" 9)";   WHATA="$(alan "$satir" 10)"
  WSB="$(alan "$satir" 11)";   WSH="$(alan "$satir" 12)"
  WST="$(alan "$satir" 13)";   WACIK="$(alan "$satir" 15)"

  if [ "$WROL" = "altakis" ]; then
    ALTAKIS_SATIR="$ALTAKIS_SATIR<tr><td>$(kacis "$WAD")</td><td>$(rozet "$WDURUM")</td>"
    ALTAKIS_SATIR="$ALTAKIS_SATIR<td class=s>$(kacis "$WCAL") calisma · $(kacis "$WHATA") hata</td>"
    ALTAKIS_SATIR="$ALTAKIS_SATIR<td class=s>$(kacis "$WSB")</td></tr>"
    continue
  fi

  # --- kanal karti ---
  # 🔴 ALAN NUMARALARI (CR-002.5 ile 'unknown' eklendi):
  #    ESK|<id>|<kanal>|<acik_production>|<acik_test>|<acik_unknown>|<kapali>|<toplam>
  #        1     2       3                 4           5              6        7      8
  #    Ilk surumde 3/4/5 yazilmisti - 'acik_uretim' yerine KANAL ADI okunuyor,
  #    panel "Donus bekleyen whatsapp uretim" gibi anlamsiz bir satir basiyordu.
  #    Alan eklerken indeksler KAYAR - her degisiklikte buraya bakilmali.
  EU="$(esk_alan "$WID" 4)"; ET="$(esk_alan "$WID" 5)"
  EB="$(esk_alan "$WID" 6)"; EK="$(esk_alan "$WID" 7)"
  [ -z "$EU" ] && EU="?"; [ -z "$ET" ] && ET="?"
  [ -z "$EB" ] && EB="?"; [ -z "$EK" ] && EK="?"
  case "$EU" in ([0-9]*) ESK_URETIM_TOPLAM=$(( ESK_URETIM_TOPLAM + EU )) ;; esac
  case "$EB" in ([0-9]*) ESK_BILINMEYEN_TOPLAM=$(( ESK_BILINMEYEN_TOPLAM + EB )) ;; esac

  HK="$(hata_alan "$WID" 4)"; HKS="$(hata_alan "$WID" 5)"
  [ -z "$HK" ] && HK="0"
  KU="$(kon_alan "$WID" 4)"; KT="$(kon_alan "$WID" 5)"; KB="$(kon_alan "$WID" 6)"
  [ -z "$KU" ] && KU="?"; [ -z "$KT" ] && KT="?"; [ -z "$KB" ] && KB="0"

  # Beklenen aktiflik uyusmazligi acikca yazilir
  if [ "$WOLMALI" = "evet" ]; then BEKL="yayinda olmali"; else BEKL="bilerek kapali"; fi
  if { [ "$WOLMALI" = "evet" ] && [ "$WAKTIF" != "evet" ]; } || { [ "$WOLMALI" = "hayir" ] && [ "$WAKTIF" = "evet" ]; }; then
    AKT_TXT="<span class=fl2>$(kacis "$WAKTIF") (beklenen: $BEKL)</span>"
  else
    AKT_TXT="$(kacis "$WAKTIF") <span class=s>($BEKL)</span>"
  fi

  ESK_TXT="<b>$EU</b> production"
  [ "$ET" != "0" ] && [ "$ET" != "?" ] && ESK_TXT="$ESK_TXT <span class=s>· $ET test</span>"
  # 🔴 UNKNOWN AYRI GOSTERILIR - metrige girmez ama KAYBOLMAZ (CR-002.5 madde A).
  [ "$EB" != "0" ] && [ "$EB" != "?" ] && ESK_TXT="$ESK_TXT <span class=un2>· $EB unknown</span>"
  [ "$EK" != "0" ] && [ "$EK" != "?" ] && ESK_TXT="$ESK_TXT <span class=s>· $EK kapatildi</span>"

  HATA_TXT="$HK"
  [ "$HK" != "0" ] && HATA_TXT="<span class=fl2>$HK</span> <span class=s>· son: $(kacis "$HKS")</span>"

  KON_TXT="<b>$KU</b> production <span class=s>· $KT test</span>"
  [ "$KB" != "0" ] && [ "$KB" != "?" ] && KON_TXT="$KON_TXT <span class=un2>· $KB unknown</span>"

  KANAL_KART="$KANAL_KART<div class=kanal>"
  KANAL_KART="$KANAL_KART<div class=kh><span>$(kacis "$WAD") <span class=s>· $(kacis "$WKANAL")</span></span>$(rozet "$WDURUM")</div>"
  KANAL_KART="$KANAL_KART<div class=s style=\"margin:.15rem 0 .5rem\">$(kacis "$WACIK")</div><table>"
  KANAL_KART="$KANAL_KART<tr><td>Yayin durumu</td><td>$AKT_TXT</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Calistirma (24sa)</td><td>$(kacis "$WCAL") · hata $(kacis "$WHATA")</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Son BASARILI calistirma</td><td>$(kacis "$WSB")</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Son HATALI calistirma</td><td>$(kacis "$WSH")</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Son tetik / veri</td><td>$(kacis "$WST")</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Donus bekleyen</td><td>$ESK_TXT</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Kayitli konusma</td><td>$KON_TXT</td></tr>"
  KANAL_KART="$KANAL_KART<tr><td>Kanal hata kaydi</td><td>$HATA_TXT</td></tr>"
  KANAL_KART="$KANAL_KART</table></div>"
done <<<"$(al WF)"

# --- Gecikme -----------------------------------------------------------------
LAT_SATIR=""
while IFS= read -r satir; do
  [ -z "$satir" ] && continue
  K="$(alan "$satir" 2)"; A="$(alan "$satir" 3)"
  P50="$(alan "$satir" 4)"; P95="$(alan "$satir" 5)"
  P99="$(alan "$satir" 6)"; MX="$(alan "$satir" 7)"
  AD="son 24 saat"; [ "$K" = "tum" ] && AD="tum zamanlar"
  LAT_SATIR="$LAT_SATIR<tr><td>$AD</td><td class=s>$(kacis "$A") calisma</td>"
  LAT_SATIR="$LAT_SATIR<td>p50 <b>$(kacis "$P50")</b></td><td>p95 <b>$(kacis "$P95")</b></td>"
  LAT_SATIR="$LAT_SATIR<td>p99 <b>$(kacis "$P99")</b></td><td>max <b>$(kacis "$MX")</b></td></tr>"
done <<<"$(al LAT)"

# --- Sistem ------------------------------------------------------------------
SYS_SATIR=""
while IFS= read -r satir; do
  [ -z "$satir" ] && continue
  A="$(alan "$satir" 2)"; D="$(alan "$satir" 3)"
  V="$(alan "$satir" 4)"; C="$(alan "$satir" 5)"
  SYS_SATIR="$SYS_SATIR<tr><td>$(kacis "$A")</td><td>$(rozet "$D")</td><td>$(kacis "$V")</td><td class=s>$(kacis "$C")</td></tr>"
done <<<"$(al SYS)"

# --- Alarm hatti -------------------------------------------------------------
AP_SATIR="$(al ALARMPOSTA | head -n1)"
AP_DURUM="$(alan "$AP_SATIR" 2)"; AP_ADET="$(alan "$AP_SATIR" 3)"; AP_SON="$(alan "$AP_SATIR" 4)"
[ -z "$AP_DURUM" ] && AP_DURUM="UNKNOWN"

# --- Kirmizi takim kurulu ----------------------------------------------------
# 🔴 Kurul her karar icin iki bagimsiz gorus ister. 22.09.2026'da dort
#    saglayicidan biri donuyordu ve her karar incelenmeden geciyordu.
#    Sebep veritabaninda kayitliydi ama hicbir EKRANDA yoktu; gemini
#    ALTI GUN 'not configured' duserken kimse gormedi. Panelde durmasinin
#    sebebi bu: kayit tutmak ogrenmek degildir.
KS_SATIR="$(al KONSEY | head -n1)"
KS_DURUM="$(alan "$KS_SATIR" 2)"; KS_ORAN="$(alan "$KS_SATIR" 3)"; KS_NOT="$(alan "$KS_SATIR" 4)"
[ -z "$KS_DURUM" ] && KS_DURUM="UNKNOWN"

ALARM_SON=""
if [ -f "$ALARM_LOG" ]; then
  while IFS='|' read -r az asev aanah abas adet apost; do
    [ -z "$az" ] && continue
    ALARM_SON="<tr><td class=s>$(kacis "$az")</td><td>$(rozet "$asev")</td><td>$(kacis "$abas")</td><td class=s>$(kacis "$apost")</td></tr>$ALARM_SON"
  done <<<"$(tail -n 12 "$ALARM_LOG" 2>/dev/null)"
fi
[ -z "$ALARM_SON" ] && ALARM_SON='<tr><td colspan=4 class=s>Henuz alarm kaydi yok.</td></tr>'

URETIM_ZAMAN="$(date '+%d.%m.%Y %H:%M')"
URETIM_EPOCH="$(date +%s)"
BAYAT_DK="${DURUM_BAYATLIK_DK:-45}"

cat > "$WEB/index.html" <<HTML
<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>L'CARLIÉ · Sunucu Durumu</title>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:1rem;font-size:15px}
 .ust{background:$RENK;color:#fff;padding:.9rem 1rem;border-radius:10px;margin-bottom:1rem}
 .kart{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem;margin-bottom:.9rem}
 .kart h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:#64748b;margin:0 0 .6rem}
 table{width:100%;border-collapse:collapse;font-size:.88rem}
 td{padding:.32rem .3rem .32rem 0;border-bottom:1px solid #f1f5f9;vertical-align:top}
 td:first-child{color:#475569;white-space:nowrap}
 .s{color:#94a3b8;font-size:.8rem;font-weight:400}
 .fl2{color:#dc2626;font-weight:700}
 .un2{color:#7c3aed;font-weight:700}
 .d{display:inline-block;padding:.1rem .45rem;border-radius:5px;font-size:.7rem;font-weight:700;letter-spacing:.03em}
 .ok{background:#dcfce7;color:#166534}
 .nt{background:#e0f2fe;color:#075985}
 .dg{background:#fef3c7;color:#92400e}
 .fl{background:#fee2e2;color:#991b1b}
 .un{background:#ede9fe;color:#5b21b6}
 .kanal{border:1px solid #e2e8f0;border-radius:9px;padding:.7rem .8rem;margin-bottom:.7rem;background:#fcfdff}
 .kh{display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:.95rem;gap:.5rem}
 .bayat{background:#dc2626;color:#fff;padding:.7rem 1rem;border-radius:10px;margin-bottom:1rem;font-weight:700;display:none}
 .alt{font-size:.75rem;color:#94a3b8;text-align:center;margin-top:1rem;line-height:1.6}
 .not{font-size:.76rem;color:#64748b;background:#f1f5f9;border-radius:7px;padding:.5rem .7rem;margin-top:.5rem}
</style></head><body>

<div id="bayat" class="bayat"></div>

<div class="ust">
  <div style="font-size:.72rem;opacity:.9">L'CARLIÉ SUNUCU · CR-002</div>
  <div style="font-size:1.12rem;font-weight:700">$BASLIK</div>
  <div style="font-size:.8rem;opacity:.92;margin-top:.2rem">$(kacis "$GENEL_SEBEP")</div>
</div>

<div class="kart"><h2>Kanallar</h2>
$KANAL_KART
<div class="not">NO_TRAFFIC = sistem ayakta ama veri gelmiyor. <b>Bu bir saglik beyani degildir.</b>
Test kimlikleri uretim konusmasi sayilmaz.</div>
</div>

<div class="kart"><h2>Alt akislar</h2><table>$ALTAKIS_SATIR</table></div>

<div class="kart"><h2>Gecikme (webhook calistirmalari)</h2><table>$LAT_SATIR</table>
<div class="not">Eszamanlilik 1 oldugu icin p95/p99 buyuk olcude <b>kuyruk beklemesidir</b>, islem suresi degil.
Ortalamaya bakarak kapasite yorumu yapilmaz.</div>
</div>

<div class="kart"><h2>Sistem ve yedekleme</h2><table>$SYS_SATIR</table></div>

<div class="kart"><h2>Alarm hatti</h2><table>
<tr><td>E-posta gonderimi</td><td>$(rozet "$AP_DURUM")</td><td class=s>$(kacis "$AP_ADET") gonderilemeyen · $(kacis "$AP_SON")</td></tr>
</table>
<table style="margin-top:.5rem">$ALARM_SON</table>
<div class="not">Alarm once <b>diske</b> yazilir, sonra e-posta denenir. E-posta gitmese bile olay kaybolmaz.</div>
</div>

<div class="kart"><h2>AI karar denetimi (kirmizi takim)</h2><table>
<tr><td>Kurul yeter sayisi</td><td>$(rozet "$KS_DURUM")</td><td class=s>$(kacis "$KS_ORAN") · $(kacis "$KS_NOT")</td></tr>
</table>
<div class="not">Her AI karari en az <b>iki bagimsiz gorus</b> almalidir. Yeter sayiya ulasilmazsa karar
<b>incelenmeden</b> gecmis demektir. Hangi saglayicinin neden dustugu ve ne yapilmasi gerektigi icin:
<code>/opt/lcarlie/ai-saglayici-tani.sh</code></div>
</div>

<div class="alt">
  Uretim: $URETIM_ZAMAN · 15 dakikada bir tazelenir<br>
  Bekleyen <b>production</b> eskalasyonu: <b>$ESK_URETIM_TOPLAM</b> · sınıflandırılamayan (unknown): <b>$ESK_BILINMEYEN_TOPLAM</b>
</div>

<script>
// 🔴 SAYFANIN KENDI TAZELIGI.
// Toplayici (cron) olurse sunucuda bunu fark edecek kimse yok; sayfa
// sessizce BAYAT veri gostermeye devam ederdi. Tarayicinin saati canli
// oldugu icin bayatligi burada tespit edip acikca uyariyoruz.
(function () {
  var uretim = $URETIM_EPOCH * 1000;
  var esikDk = $BAYAT_DK;
  var gecenDk = Math.floor((Date.now() - uretim) / 60000);
  if (gecenDk > esikDk) {
    var k = document.getElementById('bayat');
    k.textContent = 'DIKKAT: Bu sayfa ' + gecenDk + ' dakikadir tazelenmedi (esik ' +
                    esikDk + ' dk). Durum toplayici calismiyor olabilir - ' +
                    'asagidaki bilgiler GUNCEL DEGIL.';
    k.style.display = 'block';
  }
})();
</script>
<!-- 🔴 CR-007: ticari panele kopru. Ayni dizinde servis edildigi icin
     goreli bag yeterli - token adres yolunda zaten var, tekrar yazilmaz
     (yazilsaydi kaynak kodunda duz metin gorunurdu). -->
<p style="text-align:center;margin:26px 0 8px">
  <a href="./ticari.html" style="color:#6b93c9;font-size:14px">Ticari durum &rarr;</a>
</p>
</body></html>
HTML
