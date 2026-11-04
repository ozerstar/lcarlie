#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - CEVAPSIZ MUSTERI MESAJLARI  (CR-012 eki)
#
# 🔴 NEDEN VAR: mart.konusma_cevapsiz PII TASIMAZ (takma kimlik) - panel de
#    yalnizca SAYI gosterir. Ama cevap yazabilmek icin musterinin ADI ve
#    NE SORDUGU gerekir. Bu betik o bilgiyi EKRANA basar; hicbir yere
#    yazmaz, mart'a tasimaz, panele koymaz.
#
# 🔴 MESAJ GONDERMEZ. Meta kanallarinda otomatik yanit sahip karariyla
#    KAPALI. Bu betik yalnizca "kime, ne cevaplanacak" listesini cikarir.
#
# Kullanim:  /opt/lcarlie/cevapsiz-liste.sh [saat]    (varsayilan 24)
# =============================================================================
set -uo pipefail

KAP="${LCARLIE_KAP:-lcarlie-postgres}"
VT="${LCARLIE_VT:-n8n}"
SAAT="${1:-24}"

case "$SAAT" in
  ''|*[!0-9]*) echo "Saat rakam olmali: $SAAT" >&2; exit 1 ;;
esac

CIKTI=$(docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -v ON_ERROR_STOP=1 -v saat="$SAAT" <<'SQL'
SELECT format(E'\n[%s gun] %s  ·  %s mesaj  ·  konusma #%s\n   son soru: %s',
              round(c.bekleme_saat/24.0, 1),
              coalesce(k.musteri_ad, '(ad yok)'),
              c.mesaj_sayisi,
              c.konusma_id,
              coalesce(nullif(replace(left((
                SELECT m.metin FROM lcarlie.mesaj m
                 WHERE m.konusma_id = c.konusma_id AND m.yon = 'gelen'
                 ORDER BY m.zaman DESC LIMIT 1), 160), E'\n', ' '), ''),
                '(bos/gorsel mesaj)'))
  FROM mart.konusma_cevapsiz c
  JOIN lcarlie.konusma k ON k.id = c.konusma_id
 WHERE c.bekleme_saat > (:saat)::numeric
 ORDER BY c.bekleme_saat DESC;
SQL
)
KOD=$?

# 🔴 Bos cikti ile HATA ayni sey degildir. Sorgu calismadiysa "cevapsiz
#    mesaj yok" demek, bu projede yasakladigimiz sessiz basaridir.
if [ "$KOD" -ne 0 ]; then
  echo "HATA: sorgu calismadi - liste CIKARILAMADI." >&2
  exit 1
fi

echo "==============================================================="
echo " CEVAPSIZ MUSTERI MESAJLARI  ($SAAT saatten eski)"
echo "==============================================================="
if [ -z "$CIKTI" ]; then
  echo
  echo "  Cevapsiz mesaj yok."
  echo
  exit 2   # 🔴 2 = NO_DATA (cikis kodu sozlesmesi). Basari ama veri yok.
fi

echo "$CIKTI"

# --- FIYAT KAPISI (16.09.2026) -------------------------------------------------
# 🔴 SOURCE AT SEND TIME - ama KAYNAK WIX DEGIL.
#    Musteriye soylenecek fiyat ISLETME FIYAT GERCEGINDEN gelir
#    (core.ayar: base_price · campaign_price · price_state). Wix vitrini
#    bir GOZLEMDIR, otorite degil.
#
# 🔴 BU AYRIM BIR DUZELTMEDIR (Chief Architect kilidi).  Bu blogun ilk
#    surumu hazir cevap dosyasini WIX'E GORE "eski" ilan ediyordu ve
#    sessizce sunu ogretiyordu: "Wix ne diyorsa dogrudur". Tehlike somut:
#    Wix'te kampanya fiyati yanlislikla KALICI kalirsa sistem isletmenin
#    2.400 TL'lik normal fiyatini sessizce KAYBEDERDI.
#    Artik iki katman karsilastiriliyor ve fark PRICE_TRUTH_MISMATCH uretiyor;
#    sistem hicbir tarafi otomatik duzeltmez, insana sorar.
FIYAT_DOSYA="${LCARLIE_YANIT_DOSYA:-/opt/lcarlie/durum/CEVAPSIZ-10-MUSTERI.md}"

# 🔴 URUNE GOMULU DEGIL. Isletme fiyat gercegi BEYAN EDILMIS her urun
#    listelenir. Yeni urun eklendiginde betik DEGISMEZ.
#    LCARLIE_URUN ile tek bir urune daraltilabilir (urun_id).
FIYAT=$(docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -F'|' 2>/dev/null <<SQL
SELECT left(urun_adi,30),
       to_char(musteriye_soylenecek_fiyat,'FM999990'),
       to_char(base_price,'FM999990'),
       to_char(coalesce(wix_satis,-1),'FM999990'),
       fiyat_durumu, kampanya_bitisi, karsilastirma_izni, durum
  FROM mart.fiyat_gercegi
 WHERE fiyat_durumu <> 'UNKNOWN'
   AND ('${LCARLIE_URUN:-}' = '' OR urun_id = '${LCARLIE_URUN:-}')
 ORDER BY urun_adi;
SQL
)

echo
echo "---------------------------------------------------------------"
if [ -z "${FIYAT:-}" ]; then
  # 🔴 Beyan edilmis fiyat gercegi YOKSA fiyat SOYLENMEZ.
  echo " 🔴 ISLETME FIYAT GERCEGI BEYAN EDILMEMIS - musteriye fiyat YAZMA."
  echo "    Wix vitrini bir GOZLEMDIR, otorite degildir."
  echo "    core.urun_fiyat_gercegi'ne base_price ve kampanya durumu girilmeli."
else
  echo " MUSTERIYE SOYLENECEK FIYAT (isletme gercegi - Wix DEGIL)"
  while IFS='|' read -r ad soyle base wix durum bitis karsilastirma uyum; do
    [ -z "${ad:-}" ] && continue
    echo
    echo "   $ad"
    echo "     soylenecek : ${soyle} TL     base: ${base} TL   durum: ${durum}"
    echo "     Wix vitrini: ${wix} TL  (gozlem)   kampanya bitisi: ${bitis}"
    if [ "${durum}" = "CAMPAIGN" ]; then
      echo "     🔴 GECICI KAMPANYA FIYATI - bitince ${base} TL'ye doner."
    fi
    if [ "${karsilastirma}" != "EVET" ]; then
      echo "     🔴 KARSILASTIRMALI FIYAT YASAK: \"${base} yerine ${soyle}\" YAZMA."
    fi
    if [ "${uyum}" = "PRICE_TRUTH_MISMATCH" ]; then
      echo "     🔴🔴 PRICE_TRUTH_MISMATCH - isletme gercegi ${soyle}, vitrin ${wix}."
      echo "          SISTEM WIX'I DOGRU KABUL ETMEZ. Insan karari gerekir."
    fi
    # Hazir cevap dosyasi ISLETME gercegiyle karsilastirilir
    if [ -f "$FIYAT_DOSYA" ]; then
      DOSYA_FIYAT=$(grep -oE '[0-9]\.?[0-9]{3} TL' "$FIYAT_DOSYA" 2>/dev/null \
                    | sed 's/\.//; s/ TL//' | sort -u | tr '\n' ' ')
      if [ -n "$DOSYA_FIYAT" ] && ! grep -qw "$soyle" <<< "$DOSYA_FIYAT"; then
        echo "     🔴 HAZIR CEVAP DOSYASI ORTUSMUYOR: dosyada [${DOSYA_FIYAT}] var,"
        echo "        soylenecek ${soyle}. $FIYAT_DOSYA guncellenmeden GONDERME."
      fi
    fi
  done <<< "$FIYAT"
fi
echo
echo "---------------------------------------------------------------"
echo "Meta Business Suite > Gelen Kutusu > FILTRESIZ 'Tum mesajlar'"
echo "(okunmamis filtresi bu konusmalari GIZLIYOR)"
echo
echo "Yanit yazarken: soru sorarak bitirme, savunmaci dil kullanma,"
echo "her cevabi somut siparis baglantisiyla kapat."
echo "---------------------------------------------------------------"
exit 0
