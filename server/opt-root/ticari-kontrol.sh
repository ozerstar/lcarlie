#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - TICARI AYNA KONTROLU  (CR-004 Faz 4)
#
# Gunde bir kez: raw katmanini tazeler, ardindan insan karari bekleyen
# isleri sayar ve gerekiyorsa alarm uretir.
#
# 🔴 "0 acik is" ile "kontrol edilemedi" AYNI SEY DEGILDIR.
#    ETL basarisizsa acik is listesi de eski veriye bakar; bu durumda
#    "her sey yolunda" demek YANLIS olur. O yuzden once ETL durumu
#    degerlendirilir, alarm ondan sonra bakilir.
#
# 🔴 SESSIZ BASARI YOK: her calisma /opt/lcarlie/ticari-kontrol.log'a
#    tek satir yazar, durum ne olursa olsun.
#
# 🔴 Cikis kodu: 0 = kontrol yapildi (acik is olabilir), 1 = kontrol
#    YAPILAMADI. Cagiranin bu ikisini ayirt edebilmesi sart.
#
# Kullanim: /opt/lcarlie/ticari-kontrol.sh [--sessiz]
# =============================================================================
set -uo pipefail

KOK=/opt/lcarlie
KAP=lcarlie-postgres
LOG="$KOK/ticari-kontrol.log"
ALARM="$KOK/alarm.sh"
SESSIZ=0
[ "${1:-}" = "--sessiz" ] && SESSIZ=1

zaman() { date '+%d.%m.%Y %H:%M:%S'; }
yaz()   { [ "$SESSIZ" -eq 1 ] || echo "$*"; }
kaydet(){ echo "$(zaman) | $*" >> "$LOG"; }

# 🔴 HATA METNI YUTULMAZ (ikinci tur denetimi).  Onceki hali stderr'i
#    /dev/null'a atiyordu; sorgu basarisiz oldugunda alarm govdesi BOS
#    gidiyordu - "kimlik tazelenemedi" der ama NEDEN oldugunu soylemezdi.
#    Artik stderr ciktiya katilir: basarili sorguda zaten bos olur,
#    basarisizda cagiran hata metnini alarm govdesine koyabilir.
sorgu() {
  docker exec -i "$KAP" psql -U n8n -d n8n -tA -F'|' -v ON_ERROR_STOP=1 2>&1
}

# ---------------------------------------------------------------------------
# 1) raw katmanini tazele
# ---------------------------------------------------------------------------
yaz "=== TICARI AYNA KONTROLU $(zaman) ==="
ETL_CIKTI=$(python3 "$KOK/sql/raw-yukle.py" 2>&1)
ETL_KOD=$?
yaz "$ETL_CIKTI"

# 🔴 ORTAK CIKIS SOZLESMESI (CR-008):
#      0 = SUCCESS · 1 = FAILED · 2 = NO_DATA · 3 = PARTIAL
#    Onceki hali ciktida 'PARTIAL=[1-9]' METNI ariyordu - bicime bagimli ve
#    kirilgan. Ayrica NO_DATA da 1 donuyordu ve "ETL basarisiz" alarmina
#    donusuyordu; oysa "kaynak erisildi, kayit yok" ariza degildir.
if [ "$ETL_KOD" -eq 2 ]; then
  kaydet "ETL_VERI_YOK | kaynaklar erisildi, kayit yok"
  yaz "  (kaynak erisildi, kayit yok - ariza degil)"
elif [ "$ETL_KOD" -eq 3 ]; then
  printf '%s\n' "$ETL_CIKTI" | "$ALARM" DEGRADED ticari.etl.kismi \
    "Ticari ayna KISMI guncellendi" || true
  kaydet "ETL_KISMI"
elif [ "$ETL_KOD" -ne 0 ]; then
  OZET=$(echo "$ETL_CIKTI" | grep -E '^(SUCCESS=|  (HATA|veri) )' | tr '\n' ' ')
  kaydet "ETL_BASARISIZ | $OZET"
  printf '%s\n' "$ETL_CIKTI" | "$ALARM" FAILED ticari.etl \
    "Ticari ayna guncellenemedi" || true
  yaz "KONTROL YAPILAMADI - ETL basarisiz."
  exit 1
fi


# ---------------------------------------------------------------------------
# 1b) Reklam harcamasini tazele  (CR-005)
# ---------------------------------------------------------------------------
# 🔴 "Jeton yok" ile "jeton var ama calismiyor" AYRI SEYLERDIR.
#    Kaynak hic baglanmamissa bu bilinen bir durumdur - her gun alarm
#    uretmek gurultuden baska bir sey olmaz. Ama jeton VARKEN cekim
#    basarisizsa bu gercek bir arizadir ve alarm verir.
REK_CIKTI=$(python3 "$KOK/sql/meta-harcama-yukle.py" 2>&1)
REK_KOD=$?
yaz ""
yaz "$REK_CIKTI"

if echo "$REK_CIKTI" | grep -q 'META_ADS_TOKEN'; then
  kaydet "REKLAM_BAGLI_DEGIL | META_ADS_TOKEN tanimli degil"
  yaz "  (reklam kaynagi hic baglanmamis - alarm uretilmedi)"
elif [ "$REK_KOD" -eq 3 ]; then
  # 🔴 Erisilemeyen reklam hesabi = eksik harcama = ROAS oldugundan YUKSEK.
  #    Bu sessiz gecilmez; iyimser yanilmak en pahali yanilma turudur.
  printf '%s\n' "$REK_CIKTI" | "$ALARM" DEGRADED ticari.reklam.kismi \
    "Reklam harcamasi KISMI - bazi hesaplar okunamiyor" || true
  kaydet "REKLAM_KISMI"
elif [ "$REK_KOD" -ne 0 ]; then
  printf '%s\n' "$REK_CIKTI" | "$ALARM" FAILED ticari.reklam \
    "Reklam harcamasi cekilemedi" || true
  kaydet "REKLAM_BASARISIZ | kod=$REK_KOD"
else
  echo "Reklam harcamasi guncellendi." | "$ALARM" COZULDU ticari.reklam \
    "Reklam cekimi normale dondu" || true
fi


# ---------------------------------------------------------------------------
# 1b-2) Reklam/kreatif DUZEYINI tazele  (CR-018)
# ---------------------------------------------------------------------------
# NEDEN AYRI BIR ADIM: 1b kampanya duzeyini ceker (raw.meta_harcama).
# Kreatif analizi ise ad_id duzeyi ister -- hangi BASLIK, hangi CTA ne
# getirdi. O veri raw.meta_reklam + raw.meta_kreatif'te durur ve
# mart.kreatif_performans / mart.reklam_performans bunlarin uzerine kurulu.
#
# 🔴 BULUNDUGU HAL (20.09.2026): yukleyici vardi, gorunumler vardi, sohbet
#    baglanmisti -- ama betigi CAGIRAN HIC KIMSE YOKTU. Son cekim 16.09
#    22:25'ti, yani veri 4 gundur bayatliyor ve kimse fark etmiyordu.
#    "Calisan gorunum" ile "taze veri" ayri seylerdir.
#
# 🔴 KOD 3 (PARTIAL) BILEREK ALARM URETMEZ. Kismi kapsamanin kok nedeni
#    3 reklam hesabinin 2'sinde erisim izni olmamasi ve bu KALICI bir
#    durum (Graph: "Ad account owner has NOT granted access"). Ayni kok
#    neden 1b'de zaten her gun DEGRADED alarmi uretiyor. Ikinci bir alarm
#    yeni bilgi tasimaz, yalnizca gunluk gurultuyu ikiye katlar -- ve
#    gurultu, gercek alarmin gorulmemesinin sebebidir. Tek kok neden,
#    tek alarm.  Kapsama yine de loga yazilir, gizlenmez.
REKD_CIKTI=$(python3 "$KOK/sql/meta-reklam-yukle.py" 2>&1)
REKD_KOD=$?
yaz ""
yaz "$REKD_CIKTI"

if echo "$REKD_CIKTI" | grep -q 'META_ADS_TOKEN'; then
  kaydet "REKLAM_DUZEY_BAGLI_DEGIL | META_ADS_TOKEN tanimli degil"
  yaz "  (reklam kaynagi hic baglanmamis - alarm uretilmedi)"
elif [ "$REKD_KOD" -eq 2 ]; then
  kaydet "REKLAM_DUZEY_VERI_YOK | kaynak erisildi, reklam yok"
  yaz "  (kaynak erisildi, reklam yok - ariza degil)"
elif [ "$REKD_KOD" -eq 3 ]; then
  # Kalici kismi kapsama. Alarm 1b'de veriliyor; burada yalniz kayit.
  kaydet "REKLAM_DUZEY_KISMI | $(echo "$REKD_CIKTI" | grep -o 'kapsama=[^ ]*' | tail -1)"
  yaz "  (kismi kapsama - alarm 1b'de veriliyor, tekrarlanmadi)"
elif [ "$REKD_KOD" -ne 0 ]; then
  printf '%s\n' "$REKD_CIKTI" | "$ALARM" FAILED ticari.reklam.duzey \
    "Reklam/kreatif duzeyi cekilemedi" || true
  kaydet "REKLAM_DUZEY_BASARISIZ | kod=$REKD_KOD"
else
  echo "Reklam/kreatif duzeyi guncellendi." | "$ALARM" COZULDU ticari.reklam.duzey \
    "Reklam/kreatif duzey cekimi normale dondu" || true
  kaydet "REKLAM_DUZEY_OK"
fi


# ---------------------------------------------------------------------------
# 1b-3) Instagram ORGANIK icerigini tazele  (20.09.2026)
# ---------------------------------------------------------------------------
# NEDEN: CONTENT, SOCIAL, INSTAGRAM ve ART departmanlarinin veri kaynagi YOKTU.
# Reklam tarafi olculuyordu, organik taraf hic okunmuyordu -- oysa hesapta
# 123 gonderi duruyor (26.11.2025'ten beri). Bu cekim onlari besliyor.
#
# 🔴 JETON: IG_ACCESS_TOKEN OLU (olculdu: "Cannot parse access token", kod 190).
#    Yukleyici once FB_PAGE_TOKEN'i dener -- o suresiz ve IG is hesabi sayfaya
#    bagli oldugu icin calisiyor. Jeton adini yazar, jetonu yazmaz.
#
# 🔴 SADECE OKUR: gonderi paylasma/silme/yorum kod yolu yok.
IGO_CIKTI=$(python3 "$KOK/sql/ig-medya-yukle.py" 2>&1)
IGO_KOD=$?
yaz ""
yaz "$IGO_CIKTI"

if echo "$IGO_CIKTI" | grep -q 'hicbir jeton'; then
  # Jeton hic calismiyorsa bu GERCEK bir ariza: organik veri sessizce bayatlar.
  printf '%s\n' "$IGO_CIKTI" | "$ALARM" FAILED ticari.instagram \
    "Instagram organik cekimi: hicbir jeton okuyamiyor" || true
  kaydet "IG_ORGANIK_JETON_YOK"
elif [ "$IGO_KOD" -eq 2 ]; then
  kaydet "IG_ORGANIK_VERI_YOK | kaynak erisildi, gonderi yok"
  yaz "  (kaynak erisildi, gonderi yok - ariza degil)"
elif [ "$IGO_KOD" -eq 3 ]; then
  # Sayfalamanin ortasinda kesilme: elde olan yazildi, eksik oldugu SOYLENIR.
  kaydet "IG_ORGANIK_KISMI | bazi sayfalar okunamadi"
  yaz "  (kismi cekim - bazi sayfalar okunamadi)"
elif [ "$IGO_KOD" -ne 0 ]; then
  printf '%s\n' "$IGO_CIKTI" | "$ALARM" FAILED ticari.instagram \
    "Instagram organik icerigi cekilemedi" || true
  kaydet "IG_ORGANIK_BASARISIZ | kod=$IGO_KOD"
else
  echo "Instagram organik icerigi guncellendi." | "$ALARM" COZULDU ticari.instagram \
    "Instagram organik cekimi normale dondu" || true
  kaydet "IG_ORGANIK_OK"
fi

# ---------------------------------------------------------------------------
# 1b-4) GA4 davranis + atif verisi  (20.09.2026)
# ---------------------------------------------------------------------------
# NEDEN: donusum olcumu GA4 olmadan kurulamiyordu. Erisim bugun acildi
# (mulk 524826904, servis hesabi ga4-reader, anahtar /etc/lcarlie/ga4.json).
#
# 🔴 YUKLEYICI VARDI AMA CAGIRAN YOKTU -- 1b-2'de yasanan hatanin AYNISI.
#    Tek seferlik calisan bir yukleyici, veri bayatladiginda kimseye haber
#    vermez. "Calisan gorunum" ile "taze veri" ayri seylerdir.
#
# DEGERI: satin alma satirlari ATIF tasiyor (transactionId + source /
# medium / campaign) ve transactionId Wix siparis kimligiyle eslesiyor --
# OLCULDU: 10 islemin 10'u. "Hangi reklam hangi siparisi getirdi" sorusu
# bu yoldan cevaplanir; Wix siparisinde utm/gclid/fbclid YOK.
GA4_CIKTI=$(python3 "$KOK/sql/ga4-yukle.py" 2>&1)
GA4_KOD=$?
yaz ""
yaz "$GA4_CIKTI"

if echo "$GA4_CIKTI" | grep -qE 'GA4_PROPERTY_ID (yok|bos)|servis hesabi okunamadi'; then
  # Kaynak hic baglanmamis: BILINEN durum, her gun alarm uretmek gurultudur.
  # (Ayni ayrim 1b'de de yapiliyor: "jeton yok" ile "jeton var ama
  #  calismiyor" farkli seylerdir.)
  kaydet "GA4_BAGLI_DEGIL"
  yaz "  (GA4 kaynagi baglanmamis - alarm uretilmedi)"
elif [ "$GA4_KOD" -eq 3 ]; then
  printf '%s\n' "$GA4_CIKTI" | "$ALARM" DEGRADED ticari.ga4 \
    "GA4 cekimi KISMI - bazi sorgular basarisiz" || true
  kaydet "GA4_KISMI"
elif [ "$GA4_KOD" -ne 0 ]; then
  printf '%s\n' "$GA4_CIKTI" | "$ALARM" FAILED ticari.ga4 \
    "GA4 verisi cekilemedi" || true
  kaydet "GA4_BASARISIZ | kod=$GA4_KOD"
else
  echo "GA4 verisi guncellendi." | "$ALARM" COZULDU ticari.ga4 \
    "GA4 cekimi normale dondu" || true
  kaydet "GA4_OK"
fi

# ---------------------------------------------------------------------------
# 1c) Urun katalogu + maliyet versiyonlama  (CR-006)
# ---------------------------------------------------------------------------
# 🔴 GUNLUK CALISMASI IHMAL EDILEMEZ: Wix bir urun icin TEK maliyet degeri
#    tutar. Sahip alis fiyatini guncelledigi an eski deger Wix'te kaybolur.
#    Bu cekim degisimi yakalayip tarihleyerek versiyonlar; kacirilirsa o
#    degisim tarihsiz kalir ve gecmis marj hesabi bozulur.
URUN_CIKTI=$(python3 "$KOK/sql/urun-yukle.py" 2>&1)
URUN_KOD=$?
yaz ""
yaz "$URUN_CIKTI"
# 🔴 Diger iki ETL icin ozenle yapilan kod ayrimi burada YAPILMAMISTI
#    (ikinci tur denetimi): PARTIAL ve NO_DATA da "cekilemedi" alarmi
#    uretiyordu. Sozlesme 3/3 uyumlu olmali, 2/3 degil.
if [ "$URUN_KOD" -eq 2 ]; then
  kaydet "URUN_VERI_YOK | kaynak erisildi, urun yok"
  yaz "  (kaynak erisildi, urun yok - ariza degil)"
elif [ "$URUN_KOD" -eq 3 ]; then
  printf '%s\n' "$URUN_CIKTI" | "$ALARM" DEGRADED ticari.urun.kismi \
    "Urun katalogu KISMI cekildi" || true
  kaydet "URUN_KISMI"
elif [ "$URUN_KOD" -ne 0 ]; then
  printf '%s\n' "$URUN_CIKTI" | "$ALARM" FAILED ticari.urun \
    "Urun katalogu cekilemedi" || true
  kaydet "URUN_BASARISIZ | kod=$URUN_KOD"
else
  echo "Urun katalogu guncellendi." | "$ALARM" COZULDU ticari.urun \
    "Urun cekimi normale dondu" || true
fi

# ---------------------------------------------------------------------------
# 1d) Kimlik omurgasini tazele  (CR-008 · denetim bulgusu)
# ---------------------------------------------------------------------------
# 🔴 BU ADIM GUNLUK HATTA HIC YOKTU.  core.kimlik_doldur() yalnizca elle
#    calistirilmisti. raw her gun tazeleniyor ama core.customer tazelenmiyordu;
#    1 Ekim'den sonra gelen her yeni alici icin mart.siparis.customer_id NULL
#    kalirdi. Sonuclari: yeni musteri sayimi (dolayisiyla karma CAC) yanlis,
#    mart.musteri eksik, ve en onemlisi YENI KIMLIK CAKISMALARI HIC TESPIT
#    EDILMEZDI - yani "otomatik birlestirme yok, insan karar verir" kuralinin
#    bedeli, insanin onune hicbir cakismanin gelmemesi olurdu.
KIMLIK=$(sorgu <<'SQL'
SELECT adim || ' -> ' || sonuc FROM core.kimlik_doldur();
SQL
)
KIMLIK_KOD=$?
yaz ""
yaz "=== KIMLIK OMURGASI ==="
if [ "$KIMLIK_KOD" -ne 0 ]; then
  printf '%s\n' "$KIMLIK" | "$ALARM" FAILED ticari.kimlik \
    "Musteri kimligi tazelenemedi" || true
  kaydet "KIMLIK_BASARISIZ | kod=$KIMLIK_KOD"
  yaz "  HATA: kimlik doldurma calismadi"
else
  printf '%s\n' "$KIMLIK" | sed 's/^/  /' | while IFS= read -r s; do yaz "$s"; done
  echo "Kimlik omurgasi tazelendi." | "$ALARM" COZULDU ticari.kimlik \
    "Kimlik tazeleme normale dondu" || true
fi

# ---------------------------------------------------------------------------
# 1e) Mutabakat - birbirinden turemis sayilar tutuyor mu
# ---------------------------------------------------------------------------
# 🔴 Ciro kaleminin %18,8 sisik olmasi AYLARCA gorunmedi cunku kimse iki
#    rakami yan yana koymadi. Bu kontrol tam olarak onu yapar.
if [ -f "$KOK/sql/mutabakat.sql" ]; then
  # 🔴 ON_ERROR_STOP=1 SART (16.09 ikinci tur denetimi).
  #    Olmadan psql, SQL hatasi olsa bile 0 ile cikar. Sonuc: bir tablo
  #    kaybolsa, core.ayar silinse, mart.* bozulsa -> cikti 'ERROR:' satirlari
  #    dolu olur ama 'FAILED' KELIMESI hic gecmez, betik "tum kontroller
  #    gecti" yazip COZULDU alarmi gonderirdi. Yani DENETIMIN DENETIMI KOR.
  #    Bu, projenin yasakladigi sessiz basarinin en pahali hali.
  MUTABAKAT=$(docker exec -i "$KAP" psql -U n8n -d n8n -v ON_ERROR_STOP=1 \
                -f - < "$KOK/sql/mutabakat.sql" 2>&1)
  MUT_KOD=$?
  BOZUK=$(printf '%s\n' "$MUTABAKAT" | grep -cE 'FAILED|UYARI' || true)
  # 🔴 Beklenen kontrol sayisi da dogrulanir: sorgu yarida kesilirse satir
  #    sayisi duser ve "hepsi gecti" denmesi yine mumkun olurdu.
  GECEN=$(printf '%s\n' "$MUTABAKAT" | grep -c 'SUCCESS' || true)
  yaz ""
  yaz "=== MUTABAKAT ==="
  if [ "$MUT_KOD" -ne 0 ]; then
    printf '%s\n' "$MUTABAKAT" | tail -20 | "$ALARM" FAILED ticari.mutabakat \
      "Mutabakat sorgusu calismadi" || true
    kaydet "MUTABAKAT_CALISMADI"
    yaz "  HATA: mutabakat sorgusu calismadi"
  elif [ "$BOZUK" -gt 0 ]; then
    # UYARI da sayilir: 'BILINMIYOR' siniflari FAILED degil UYARI doner ve
    # onceki halinde hicbir yere ULASMIYORDU.
    printf '%s\n' "$MUTABAKAT" | grep -E 'FAILED|UYARI' | head -40 | "$ALARM" FAILED ticari.mutabakat \
      "$BOZUK mutabakat kontrolu BASARISIZ/UYARI" || true
    kaydet "MUTABAKAT_BOZUK | $BOZUK kontrol"
    yaz "  🔴 $BOZUK kontrol BASARISIZ/UYARI:"
    printf '%s\n' "$MUTABAKAT" | grep -E 'FAILED|UYARI' | sed 's/^/     /' | while IFS= read -r s; do yaz "$s"; done
  elif [ "$GECEN" -lt "${MUTABAKAT_ASGARI:-20}" ]; then
    # 🔴 Hic FAILED yok AMA kontrol sayisi beklenenin altinda: sorgu yarida
    #    kesilmis olabilir. "Az kontrol calisti" da bir arizadir.
    printf '%s\n' "$MUTABAKAT" | tail -20 | "$ALARM" FAILED ticari.mutabakat \
      "Mutabakat eksik calisti ($GECEN kontrol, asgari ${MUTABAKAT_ASGARI:-20})" || true
    kaydet "MUTABAKAT_EKSIK | gecen=$GECEN"
    yaz "  🔴 yalnizca $GECEN kontrol calisti (asgari ${MUTABAKAT_ASGARI:-20}) - sorgu yarida kesilmis olabilir"
  else
    yaz "  $GECEN kontrolun tamami gecti"
    kaydet "MUTABAKAT_TAMAM | $GECEN kontrol gecti"
    echo "Mutabakat kontrolleri gecti ($GECEN kontrol)." | "$ALARM" COZULDU ticari.mutabakat \
      "Mutabakat normale dondu" || true
  fi
else
  kaydet "MUTABAKAT_YOK | mutabakat.sql kurulu degil"
fi

# ---------------------------------------------------------------------------
# 2) Acik isler
# ---------------------------------------------------------------------------
ACIK=$(sorgu <<'SQL'
SELECT tur, count(*) FROM mart.acik_isler GROUP BY 1 ORDER BY 1;
SQL
)
ACIK_KOD=$?
if [ "$ACIK_KOD" -ne 0 ]; then
  kaydet "SORGU_BASARISIZ | mart.acik_isler okunamadi"
  echo "mart.acik_isler sorgusu calismadi." | "$ALARM" FAILED ticari.sorgu \
    "Acik is listesi okunamadi" || true
  exit 1
fi

TOPLAM=0
[ -n "$ACIK" ] && TOPLAM=$(echo "$ACIK" | awk -F'|' '{s+=$2} END{print s+0}')

yaz ""
yaz "=== ACIK ISLER ==="
if [ "$TOPLAM" -eq 0 ]; then
  yaz "  yok"
else
  echo "$ACIK" | awk -F'|' '{printf "  %-28s %s\n", $1, $2}'
fi

# ---------------------------------------------------------------------------
# 3) Alarm kurali (sahip karari): siniflandirilamayan gonderi
# ---------------------------------------------------------------------------
SINIFSIZ=$(sorgu <<'SQL'
SELECT count(*) FROM mart.gonderi WHERE alarm AND olcumde;
SQL
)
SORGU_KOD=$?
# 🔴 Bos cikti 0'a CEVRILMEZ. Sorgu calismadiysa "0 siniflandirilmamis
#    gonderi var" demek, tam da bu projede yasakladigimiz sessiz basaridir.
if [ "$SORGU_KOD" -ne 0 ] || ! [[ "$SINIFSIZ" =~ ^[0-9]+$ ]]; then
  kaydet "SORGU_BASARISIZ | siniflandirma sayisi okunamadi (kod=$SORGU_KOD cikti='$SINIFSIZ')"
  echo "mart.gonderi siniflandirma sorgusu sonuc dondurmedi." | "$ALARM" FAILED ticari.sorgu \
    "Gonderi siniflandirmasi kontrol edilemedi" || true
  exit 1
fi

if [ "$SINIFSIZ" -gt 0 ]; then
  AYRINTI=$(sorgu <<'SQL'
SELECT format('%s | %s | %s', coalesce(barkod,'-'), coalesce(sehir,'-'),
              coalesce(array_to_string(urun_adlari,', '),'-'))
  FROM mart.gonderi WHERE alarm AND olcumde ORDER BY olusturma DESC LIMIT 20;
SQL
)
  printf 'Siniflandirilamayan gonderi: %s\n\nBunlarin Wix siparisi de yok, EK BILGI alani da bos.\nYa Wix siparisiyle eslesmeli ya da EK BILGI alanina NUMUNE-<tarih> yazilmali.\n\n%s\n' \
    "$SINIFSIZ" "$AYRINTI" | "$ALARM" UYARI ticari.siniflandirilmamis \
    "$SINIFSIZ gonderi siniflandirilamadi" || true
else
  # Daha once alarm verilmis ve duzelmisse dedup durumu temizlenir.
  echo "Siniflandirilamayan gonderi kalmadi." | "$ALARM" COZULDU ticari.siniflandirilmamis \
    "Gonderi siniflandirmasi tamam" || true
fi

# ---------------------------------------------------------------------------
# 3b) Gunun anlik goruntusunu yaz  (CR-012)
# ---------------------------------------------------------------------------
# 🔴 NEDEN PANELDEN ONCE: panel bugunku view mantigini gosterir ve yarin
#    mantik degisirse o gorunti KAYBOLUR. Anlik goruntu, "o gun ekranda ne
#    yaziyordu" sorusunun tek kalici cevabi - ve geriye donuk telafisi YOK.
#    Bu yuzden panel uretilemese bile yazilmis olmali.
#
# 🔴 METRIK SURUMU hesap mantigi degistiginde ELLE artirilir. Ayni surumde
#    olmayan iki gunun rakamlari yan yana konmaz.
METRIK_SURUMU="${LCARLIE_METRIK_SURUMU:-CR-012}"
yaz ""
yaz "=== ANLIK GORUNTU ==="
if ANLIK=$(sorgu <<SQL
SELECT format('%s #%s | karar_hazir=%s', gun, no, hazir)
  FROM core.anlik_yaz('$METRIK_SURUMU');
SQL
) && [ -n "$ANLIK" ]; then
  yaz "  $ANLIK  (metrik surumu: $METRIK_SURUMU)"
  kaydet "ANLIK_YAZILDI | $ANLIK"
else
  # 🔴 Yazilamamasi SESSIZ GECILMEZ: o gunun karar baglami kalici olarak kaybolur.
  yaz "  🔴 anlik goruntu YAZILAMADI - o gunun karar baglami kaybolur"
  echo "core.anlik_yaz() calismadi." | "$ALARM" DEGRADED ticari.anlik \
    "Gunun anlik goruntusu yazilamadi" || true
  kaydet "ANLIK_YAZILAMADI"
fi

# ---------------------------------------------------------------------------
# 4) Paneli uret  (CR-007)
# ---------------------------------------------------------------------------
# 🔴 SIRA ONEMLI: panel kaynaklar tazelendikten SONRA uretilir. Ters sirada
#    uretilirse panel bir gun eski veriyi gosterir ve ustunde "bugun
#    uretildi" yazar - en kotu tur yanlislik.
if [ -x "$KOK/ticari-panel.sh" ]; then
  if PANEL=$("$KOK/ticari-panel.sh" 2>&1); then
    yaz ""
    yaz "$PANEL"
  else
    # Panel uretilemezse sayfa ESKI haliyle durur (betik gecici dosyaya
    # yazip tasiyor). Bayat panel sessiz kalmaz: alarm uretilir.
    printf '%s\n' "$PANEL" | "$ALARM" DEGRADED ticari.panel \
      "Ticari panel uretilemedi" || true
    kaydet "PANEL_BASARISIZ"
  fi
else
  kaydet "PANEL_YOK | ticari-panel.sh kurulu degil"
fi

# ---------------------------------------------------------------------------
# 3d) SIPARIS SESSIZLIGI  (25.09.2026)
# ---------------------------------------------------------------------------
# NEDEN VAR. Disk, yedek, mutabakat ve panel izleniyordu ama "siparis akisi
# durdu" diye bir kontrol YOKTU. 25.09.2026'da elle bakilinca Wix'te 13
# gundur siparis olmadigi gorildu; hicbir yerde bunu soyleyen bir satir
# yoktu.
#
# 🔴 ESIK UYDURULMADI, OLCULDU. mart.siparis'teki 30 siparisli gunun
#    araliklari (06.02.2026 - 12.09.2026):
#      medyan 4 gun · ortalama 7,5 · 90. yuzdelik 18,4 · EN UZUN 32 gun
#    Yani bu iste seyrek ve duzensiz siparis NORMALDIR. 13 gunluk sessizlik
#    tek basina anormal DEGIL. Esigi medyana koymak her ay oten, dolayisiyla
#    kimsenin bakmadigi bir alarm uretirdi -- gercek alarmi gorunmez kilan
#    sey tam olarak budur.
#      UYARI  >= 18 gun  (olculen 90. yuzdelik: gecmisin %10'u bunun ustunde)
#      FAILED >  32 gun  (gecmiste HIC gorulmemis: gercekten yeni bir durum)
#
# 🔴 KAPSAM SINIRI ALARMIN ICINE YAZILIR. mart.siparis YALNIZ Wix'tir.
#    Trendyol siparisleri bu ambara hic girmiyor, kapida odeme ve
#    WhatsApp/telefon satislari da burada yok. Bu yuzden alarm "satis yok"
#    DEMEZ, "Wix'te siparis yok" der. Ikisini karistirmak, ciro dururken
#    "is bitti" ya da is surerken "alarm yanlis" sonucuna goturur.
#
# Reklam harcamasi ayni pencerede RAPORLANIR: asil karar verdiren sey
# sessizligin kendisi degil, sessizlik SURERKEN para harcaniyor olmasidir.
yaz ""
yaz "=== SIPARIS SESSIZLIGI ==="
if SESSIZLIK=$(sorgu <<'SQL'
WITH son AS (SELECT max(gun) AS g FROM mart.siparis),
     h   AS (SELECT COALESCE(sum(harcama),0) AS tl FROM raw.meta_harcama, son
              WHERE gun > son.g)
SELECT (current_date - son.g)::text || '|' || son.g::text || '|' || round(h.tl)::text
  FROM son, h WHERE son.g IS NOT NULL;
SQL
) && [ -n "$SESSIZLIK" ]; then
  GUN="${SESSIZLIK%%|*}"
  KALAN="${SESSIZLIK#*|}"
  SON_GUN="${KALAN%%|*}"
  HARCAMA="${KALAN##*|}"
  UYARI_ESIK="${SIPARIS_SESSIZLIK_UYARI:-18}"
  FAIL_ESIK="${SIPARIS_SESSIZLIK_FAIL:-32}"

  yaz "  son Wix siparisi: $SON_GUN  ($GUN gun once)"
  yaz "  o tarihten beri Meta harcamasi: $HARCAMA TL"

  GOVDE="Son Wix siparisi: $SON_GUN ($GUN gun once).
O tarihten beri Meta reklam harcamasi: $HARCAMA TL.

KAPSAM: bu sayi YALNIZ Wix siparisleridir. Trendyol siparisleri bu ambara
girmiyor; kapida odeme ve WhatsApp/telefon satislari da burada gorunmez.
Yani bu alarm 'hic satis yok' DEMEZ - 'Wix'te siparis yok' der.

OLCULEN NORMAL: medyan aralik 4 gun, 90. yuzdelik 18 gun, gecmisteki en
uzun sessizlik 32 gun (30 siparisli gun, 06.02.2026 - 12.09.2026)."

  if [ "$GUN" -gt "$FAIL_ESIK" ]; then
    printf '%s\n' "$GOVDE" | "$ALARM" FAILED ticari.siparis_sessizlik \
      "Wix'te $GUN gundur siparis yok - gecmiste hic gorulmemis sure" || true
    kaydet "SIPARIS_SESSIZLIK_FAILED | $GUN gun | harcama=$HARCAMA"
    yaz "  🔴 $GUN gun: gecmisteki en uzun sessizligi ($FAIL_ESIK gun) asti"
  elif [ "$GUN" -ge "$UYARI_ESIK" ]; then
    printf '%s\n' "$GOVDE" | "$ALARM" DEGRADED ticari.siparis_sessizlik \
      "Wix'te $GUN gundur siparis yok" || true
    kaydet "SIPARIS_SESSIZLIK_UYARI | $GUN gun | harcama=$HARCAMA"
    yaz "  🟡 $GUN gun: olculen 90. yuzdeligin ($UYARI_ESIK gun) ustunde"
  else
    kaydet "SIPARIS_SESSIZLIK_NORMAL | $GUN gun | harcama=$HARCAMA"
    yaz "  olculen normal aralikta (uyari esigi $UYARI_ESIK gun)"
  fi
else
  # 🔴 Sorgu calismadiysa "siparis yok" DENMEZ - bilinmiyor denir.
  #    Yoklugu sebebini bilmeden cumleye cevirmek bu projede tekrar eden
  #    kok hatadir; bos sonuc ile okunamayan sonuc ayri seylerdir.
  yaz "  🔴 siparis sessizligi OLCULEMEDI (sorgu calismadi)"
  printf '%s\n' "$SESSIZLIK" | "$ALARM" DEGRADED ticari.siparis_sessizlik \
    "Siparis sessizligi sorgusu calismadi - durum BILINMIYOR" || true
  kaydet "SIPARIS_SESSIZLIK_SORULAMADI"
fi

kaydet "TAMAM | acik_is=$TOPLAM siniflandirilmamis=$SINIFSIZ"
yaz ""
yaz "Kontrol tamamlandi. Acik is: $TOPLAM"
exit 0
