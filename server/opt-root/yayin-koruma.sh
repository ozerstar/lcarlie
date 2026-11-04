#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - YAYIN KORUMA
#
# NEDEN VAR
# yayinla.ps1 masaustundeki kaynagi sunucuya basar. Sunucuda elle yapilan
# bir duzeltme, bir sonraki yayinda SESSIZCE silinir. 20-22.09.2026'da bu
# iki kez olctu ve dort dosya kayboldu:
#   - sql/meta-harcama-yukle.py  (Meta hesap kayit defteri okumasi)
#   - ticari-kontrol.sh          (GA4 gunluk adimi)
# Kaybi fark etmenin tek yolu, gunler sonra "bu duzeltme neden yok?" demekti.
#
# 🔴 Ek tehlike: yayinla.ps1 dosyalari kurarken durmaz; "basarisiz" biten bir
#    yayin bile kurulmus dosyalari geride birakir.
#
# NE YAPAR
#   kontrol  : Yayindan ONCE. Sunucudaki yonetilen dosyalar en son yayinlanan
#              halinden FARKLIYSA durur ve hangilerinin degistigini yazar.
#              Yani "birisi sunucuda duzeltme yapmis, uzerine yazmak uzeresin".
#   kaydet   : Yayindan SONRA. Yeni hali geçmişe işler.
#   kaydet-tek <yol> : Tek bir dosya kurulur kurulmaz islenir. Yarim kalan
#              bir yayinin, kurdugu dosyalari bir sonraki kontrolde "elle
#              degistirilmis" gostermesini onler.
#   gecmis   : Son kayitlar.
#   fark     : Sunucudaki hali ile son kayit arasindaki farki gosterir.
#
# NEYI KORUMAZ
# Bu bir yedek degil, bir KAPI. Kayitlar yalniz yonetilen dosyalarin
# metnini tutar; veri, log ve state disaridadir.
# =============================================================================
set -uo pipefail

# 🔴 LCARLIE_KOK yalniz TEST icindir; uretimde ayarlanmaz ve varsayilan
#    /opt/lcarlie kullanilir. Sabit kodluyken bu betigin karari
#    ("yayini durdur / durdurma") ancak uretim agacinda sinanabilirdi.
KOK="${LCARLIE_KOK:-/opt/lcarlie}"
GITDIR="$KOK/.yayin-git"
LISTE="$KOK/yayin-dosyalari.conf"
GIT=(git --git-dir="$GITDIR" --work-tree="$KOK")

yaz() { printf '%s\n' "$*"; }
hata() { printf 'YAYIN KORUMA: %s\n' "$*" >&2; }

[ -f "$LISTE" ] || { hata "dosya listesi yok: $LISTE"; exit 2; }

# Listeyi /opt/lcarlie'ye GORECELI yollara cevir (git work-tree boyle ister).
goreceli() {
  grep -vE '^\s*(#|$)' "$LISTE" | sed "s#^$KOK/##"
}

ilk_kurulum() {
  "${GIT[@]}" init -q 2>/dev/null || true
  "${GIT[@]}" config user.email "yayin-koruma@lcarlie" 2>/dev/null || true
  "${GIT[@]}" config user.name  "Yayin Koruma"        2>/dev/null || true
  # Yalniz listedekiler izlenir; gerisi (log, state, yedek) disarida kalir.
  printf '/*\n' > "$GITDIR/info/exclude" 2>/dev/null || true
}

ekle() {
  local bulunan=0 eksik=0 y
  while IFS= read -r y; do
    [ -n "$y" ] || continue
    if [ -f "$KOK/$y" ]; then
      "${GIT[@]}" add -f -- "$y" 2>/dev/null && bulunan=$((bulunan+1))
    else
      eksik=$((eksik+1))
    fi
  done < <(goreceli)
  printf '%s %s' "$bulunan" "$eksik"
}

case "${1:-}" in
  kontrol)
    if [ ! -d "$GITDIR" ]; then
      # Ilk calisma: bugunku hal TABAN olarak alinir. Gecmisi olmayan bir
      # kapiyi "her sey degismis" diye kapatmak, kapiyi ise yaramaz kilardi.
      ilk_kurulum
      okunan=$(ekle); "${GIT[@]}" commit -q -m "taban: ilk kurulum" 2>/dev/null || true
      yaz "YAYIN KORUMA: ilk kurulum yapildi, bugunku hal taban alindi (${okunan% *} dosya)."
      exit 0
    fi
    ekle >/dev/null
    degisen=$("${GIT[@]}" diff --cached --name-only 2>/dev/null)
    if [ -z "$degisen" ]; then
      yaz "YAYIN KORUMA: sunucudaki yonetilen dosyalar son yayinla ayni. Devam."
      exit 0
    fi
    hata "SUNUCUDA ELLE DEGISTIRILMIS DOSYA VAR - yayin bunlari SILECEK:"
    printf '%s\n' "$degisen" | sed 's/^/  - /' >&2
    hata ""
    hata "Once karar ver:"
    hata "  a) Degisiklik kaynaga tasinacaksa: /opt/lcarlie/yayin-koruma.sh fark <dosya>"
    hata "     ciktisini masaustundeki kaynaga uygula, sonra yayinla."
    hata "  b) Degisiklik atilacaksa: /opt/lcarlie/yayin-koruma.sh kaydet 'elle degisiklik kabul edildi'"
    hata "     sonra yayinla."
    exit 1
    ;;

  kaydet)
    [ -d "$GITDIR" ] || ilk_kurulum
    okunan=$(ekle)
    mesaj="${2:-yayin $(date '+%F %T')}"
    if "${GIT[@]}" diff --cached --quiet 2>/dev/null; then
      yaz "YAYIN KORUMA: degisiklik yok, kayit gerekmedi."
    else
      "${GIT[@]}" commit -q -m "$mesaj"
      yaz "YAYIN KORUMA: kaydedildi - $mesaj (${okunan% *} dosya izleniyor, ${okunan#* } eksik)"
    fi
    exit 0
    ;;

  kaydet-tek)
    # 🔴 YARIM YAYIN, BIR SONRAKI YAYINI KILITLEMESIN.
    #    yayinla.ps1 dosyalari tek tek kurar ve ortada durabilir (test
    #    kapisi, sozdizimi hatasi, kesilen baglanti). Kayit yalnizca en
    #    sonda alindigi icin, kurulmus dosyalar bir sonraki calistirmada
    #    "sunucuda elle degistirilmis" gorunur ve kapi kapanir - oysa o
    #    dosyalari kuran yayinin ta kendisidir.
    #
    #    Bu, "hepsini kaydet"ten farkli: YALNIZ adi verilen dosya islenir.
    #    Baska bir dosyadaki gercek elle degisiklik kayit disinda kalir ve
    #    bir sonraki kontrolde yakalanmaya devam eder.
    [ -n "${2:-}" ] || { hata "kaydet-tek: dosya yolu gerekli"; exit 2; }
    [ -d "$GITDIR" ] || ilk_kurulum
    hedef="${2#"$KOK/"}"
    [ -f "$KOK/$hedef" ] || { hata "kaydet-tek: dosya yok: $2"; exit 2; }
    "${GIT[@]}" add -f -- "$hedef" 2>/dev/null || { hata "kaydet-tek: eklenemedi: $hedef"; exit 1; }
    if "${GIT[@]}" diff --cached --quiet -- "$hedef" 2>/dev/null; then
      exit 0   # degismemis: sessiz
    fi
    "${GIT[@]}" commit -q -m "kuruldu: $hedef" -- "$hedef" 2>/dev/null || true
    exit 0
    ;;

  fark)
    [ -d "$GITDIR" ] || { hata "henuz kayit yok"; exit 2; }
    ekle >/dev/null
    "${GIT[@]}" diff --cached ${2:+-- "${2#"$KOK/"}"}
    exit 0
    ;;

  gecmis)
    [ -d "$GITDIR" ] || { hata "henuz kayit yok"; exit 2; }
    "${GIT[@]}" log --oneline -"${2:-15}" --date=short --pretty='%h %ad %s'
    exit 0
    ;;

  *)
    yaz "kullanim: yayin-koruma.sh {kontrol|kaydet [mesaj]|fark [dosya]|gecmis [n]}"
    exit 2
    ;;
esac
