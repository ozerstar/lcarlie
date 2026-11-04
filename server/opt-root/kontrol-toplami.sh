#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - HARICI KONTROL TOPLAMI  (CR-012)
#
# 🔴 NEDEN VAR - bagimsiz denetimin dordüncü bulgusu (16.09.2026):
#
#    33 mutabakat kontrolumuz ILISKISEL: birbirinden turemis iki sayi
#    birbirini tutmak zorunda. Iyi, ama YETMEZ:
#
#        A yanlis · B, A'dan turetildi · test "A = B" der ve GECER.
#
#    Bunu zaten yasadik: kalem indirimi okunmayinca hem kalem toplami hem
#    siparis toplami AYNI yanlis kaynaktan geliyordu.
#
#    Eksik olan ucuncu katman: DISARIDAN kontrol toplami. Wix panelinde
#    kac siparis goruluyor, Meta Ads Manager kac TL harcama diyor,
#    BasitKargo kac gonderi listeliyor - ve bizim veritabanimiz ne diyor.
#
# 🔴 BU BETIK OTOMATIK KARSILASTIRMA YAPMAZ, YAPAMAZ.
#    Panellerin sayfa sayfa okunmasi gerekir; API zaten bizim kaynagimiz,
#    onu kendisiyle karsilastirmak kontrol degil dongudur.
#    Betik BIZIM tarafin sayilarini basar; sen panellerden bakip yanina
#    yazarsin. Denetimin kendi cumlesi:
#      "Ayda 37 siparişte bunu otomatiklestirmek zorunda bile degilsin.
#       Haftada bir elle yapilan kontrol cogu sofistike testten degerlidir."
#
# Kullanim:  /opt/lcarlie/kontrol-toplami.sh [gun_sayisi]   (varsayilan 7)
# =============================================================================
set -uo pipefail

KAP="${LCARLIE_KAP:-lcarlie-postgres}"
VT="${LCARLIE_VT:-n8n}"
GUN="${1:-7}"

# 🔴 Sayi dogrulamasi: "7; DROP" gibi bir arguman SQL'e girmesin.
case "$GUN" in
  ''|*[!0-9]*) echo "Gun sayisi rakam olmali: $GUN" >&2; exit 1 ;;
esac

sorgu() { docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -F'|' -v ON_ERROR_STOP=1 -v gun="$GUN"; }

echo "==============================================================="
echo " HARICI KONTROL TOPLAMI - son $GUN gun"
echo " $(date '+%d.%m.%Y %H:%M')"
echo "==============================================================="
echo
echo "Asagidaki rakamlar BIZIM VERITABANIMIZIN dedikleridir."
echo "Her satirin yanina KAYNAK PANELDEN okudugun rakami yaz."
echo "Tutmuyorsa: once ham veriye bak, koda degil."
echo

CIKTI=$(sorgu <<'SQL'
\set baslangic (current_date - (:gun)::int)

SELECT 'WIX · siparis adedi',
       count(*)::text,
       'Wix > Satislar > Siparisler, tarih filtresi'
  FROM raw.wix_order
 WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic
UNION ALL
SELECT 'WIX · toplam ciro (KDV DAHIL)',
       to_char(coalesce(sum(toplam),0),'FM999999990.00'),
       'Wix siparis listesi toplami - KDV DAHIL tutar'
  FROM raw.wix_order
 WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic
UNION ALL
SELECT 'WIX · KDV',
       to_char(coalesce(sum(kdv),0),'FM999999990.00'),
       'Muhasebe/e-Arsiv ile karsilastir'
  FROM raw.wix_order
 WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic
UNION ALL
SELECT 'META · harcama (bagli hesap)',
       to_char(coalesce(sum(harcama),0),'FM999999990.00'),
       'Ads Manager > secili tarih > Harcanan tutar'
  FROM raw.meta_harcama
 WHERE kampanya_id <> '_HESAP' AND gun >= :baslangic
UNION ALL
-- 🔴 Bu satir DIGERLERINDEN farkli: bizim rakamimizin EKSIK oldugunu
--    bildigimiz yer. Ads Manager TUM hesaplari gosterir, biz 1 hesap
--    okuyoruz. Tutmamasi BEKLENEN durumdur - ne kadar tutmadigi onemli.
SELECT 'META · okunan hesap sayisi',
       count(DISTINCT hesap_id)::text,
       'Ads Manager''da kac reklam hesabi var? (fark BEKLENEN)'
  FROM raw.meta_harcama
 WHERE gun >= :baslangic
UNION ALL
SELECT 'BASITKARGO · gonderi adedi',
       count(*)::text,
       'BasitKargo > Kargolar, ayni tarih araligi'
  FROM raw.bk_shipment
 WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic
UNION ALL
SELECT 'BASITKARGO · kargo bedeli',
       to_char(coalesce(sum(kargo_ucreti),0),'FM999999990.00'),
       'BasitKargo fatura/ozet'
  FROM raw.bk_shipment
 WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic
UNION ALL
SELECT 'BASITKARGO · kapida odeme tahsilati',
       to_char(coalesce(sum(cod_tutar) FILTER (WHERE cod_durum='TRANSFERRED'),0),'FM999999990.00'),
       'Banka hesabina gecen tutar ile karsilastir'
  FROM raw.bk_shipment
 WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic
UNION ALL
SELECT 'MESSENGER · yeni konusma',
       count(*)::text,
       'Meta Business Suite > Gelen Kutusu'
  FROM lcarlie.konusma
 WHERE (ilk_mesaj AT TIME ZONE 'Europe/Istanbul')::date >= :baslangic;
SQL
)

if [ -z "$CIKTI" ]; then
  # 🔴 Bos cikti BASARI DEGILDIR. Sorgu calismadiysa "kontrol yapildi" denemez.
  echo "HATA: sorgu sonuc dondurmedi - kontrol YAPILMADI." >&2
  exit 1
fi

printf '%-36s %16s   %s\n' "BIZIM RAKAMIMIZ" "DEGER" "KAYNAKTA NEREYE BAKILIR"
printf '%-36s %16s   %s\n' "------------------------------------" "----------------" "-----------------------"
while IFS='|' read -r ad deger nere; do
  [ -z "$ad" ] && continue
  printf '%-36s %16s   %s\n' "$ad" "$deger" "$nere"
done <<< "$CIKTI"

echo
echo "---------------------------------------------------------------"
echo "Tutmayan satir varsa:"
echo "  1) Once ham veriye bak (raw.* tablolari), koda DEGIL."
echo "  2) Fark tek yonlu mu? (bizde eksik / kaynakta eksik)"
echo "  3) Tarih dilimi ayni mi? Bizim gun siniri Europe/Istanbul."
echo "  4) Duzeltme gerekiyorsa CR ac - panelde elle duzeltme YAPMA."
echo "---------------------------------------------------------------"
exit 0
