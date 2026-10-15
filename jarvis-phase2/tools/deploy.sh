#!/bin/sh
# Jarvis Phase 2 dağıtımı: depodan üretime, eksiksiz ve doğrulanarak.
#
# NEDEN VAR
# Dağıtım bugüne kadar elle `cp` komutlarıyla yapılıyordu ve hiçbir şey
# eksiksizliği garanti etmiyordu. 20.09.2026'da jarvis/knowledge.py'nin
# üretimde HİÇ olmadığı TESADÜFEN görüldü -- modül yazılmış, commit edilmiş,
# ama kopyalanmamıştı. Hiçbir hata vermedi; ilgili yetenek sessizce yoktu.
#
# NE YAPAR
#   1. Depodaki değişiklikleri kontrol eder (kirli ağaçla dağıtım yapılmaz)
#   2. Testleri KAYNAKTA çalıştırır -- geçmezse dağıtım YOK
#   3. Yedek alır
#   4. Git'in bildiği TÜM dosyaları kopyalar (tek tek seçmez)
#   5. Sonra tekrar karşılaştırır: eksik kalan varsa söyler
#   6. Servisi yeniden başlatır ve ayakta olduğunu doğrular
#
# NE YAPMAZ
# venv'e dokunmaz, veritabanına dokunmaz, migration çalıştırmaz. Onlar ayrı
# ve bilinçli adımlardır.
set -eu

# 🔴 BETIK KENDINI UZERINE YAZIYOR — OLCULDU 15.10.2026.
# 4. adim git'in bildigi TUM dosyalari kopyaliyor; bu betik de onlardan
# biri. Kabuk betigi artimli okudugu icin, dosya calisma sirasinda
# degisince eski bayt konumundan YENI icerige dusuyor ve rastgele bir
# satiri komut sanip calistiriyor. Olculen cikti:
#   tools/deploy.sh: 142: ün: not found
# O sefer zararsiz bir satira dustu. Dusmeyebilirdi.
#
# Cozum: ilk is olarak kendini /tmp'ye kopyalayip oradan devam et.
# Kopya calisma boyunca degismez, hedefteki dosya serbestce guncellenir.
if [ "${DEPLOY_SABIT_KOPYA:-}" != "1" ]; then
  _kopya=$(mktemp "${TMPDIR:-/tmp}/deploy-XXXXXX.sh")
  cat "$0" > "$_kopya"
  DEPLOY_SABIT_KOPYA=1 _KOPYA_SIL="$_kopya" export DEPLOY_SABIT_KOPYA _KOPYA_SIL
  sh "$_kopya" "$@"
  _durum=$?
  rm -f "$_kopya"
  exit $_durum
fi

KAYNAK=${JARVIS_SOURCE:-/opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2}
HEDEF=${JARVIS_TARGET:-/opt/lcarlie/jarvis-phase2}
SERVIS=${JARVIS_SERVICE:-jarvis-web}
PY="$HEDEF/venv/bin/python"
[ -x "$PY" ] || PY=python3

say() { printf '%s\n' "$*"; }
die() { printf 'DURDURULDU: %s\n' "$*" >&2; exit 1; }

say "kaynak : $KAYNAK"
say "hedef  : $HEDEF"
say "servis : $SERVIS"
say

# --- 1. kirli agacla dagitim yapilmaz -------------------------------------
cd "$KAYNAK/.." || die "kaynak dizin yok"
kirli=$(git status --porcelain 2>/dev/null | head -5)
if [ -n "$kirli" ]; then
  say "=== 1. DEPO KIRLİ -- commit edilmemiş değişiklik var:"
  printf '%s\n' "$kirli" | sed 's/^/     /'
  die "önce commit et; kaydedilmemiş kod dağıtılmaz"
fi
say "=== 1. depo temiz  ($(git log --oneline -1))"

# --- 2. testler KAYNAKTA gecmeden dagitim yok -----------------------------
# Bu kapi 20.09.2026'da OLCULDU ve KAPANMIYORDU: bir test basarisizken
# dagitim sorunsuz gecti. Iki ayri kusur vardi, ikisi de asagida kapali.
#
# 1) `cmd | tail` borusunun cikis kodu TAIL'in kodudur ve tail hep 0
#    doner. `if ! sonuc=$(... | tail -3)` bu yuzden hicbir zaman dogru
#    olmuyordu. Cikis kodu artik boruya verilmeden okunuyor.
# 2) Testler `python3` ile kosuyordu, oysa uretim venv'de calisiyor.
#    Sistem python'unda mem0 yok; test gercekte olmayan bir sebeple
#    kirmizi yandi. Uretimde ne calisiyorsa test de onunla kosmali.
#
# Ayrica webconsole/tests hic kosmuyordu -- paneli koruyan sozlesme
# testleri (CSP, uydurma sayi, olmayan uc nokta) tam oradadir.
say "=== 2. testler çalışıyor..."
cd "$KAYNAK" || die "kaynak yok"
gunluk=$(mktemp)
gecti=1

kos() {
  ad=$1
  shift
  if PYTHONPATH="$KAYNAK:$KAYNAK/webconsole" "$PY" -m unittest discover "$@" -p "test_*.py" >"$gunluk" 2>&1; then
    printf '     %-12s %s\n' "$ad" "$(tail -3 "$gunluk" | tr '\n' ' ')"
  else
    gecti=0
    say "     $ad BAŞARISIZ:"
    grep -E '^(FAIL|ERROR):' "$gunluk" | head -10 | sed 's/^/       /'
    tail -3 "$gunluk" | sed 's/^/       /'
  fi
}

kos "tests"      -s tests
kos "webconsole" -s webconsole/tests -t webconsole/tests
rm -f "$gunluk"
[ "$gecti" -eq 1 ] || die "testler geçmedi; dağıtım yapılmadı"

# --- 3. yedek --------------------------------------------------------------
damga=$(date +%Y%m%d-%H%M%S)
yedek="$HEDEF/.backup-$damga"
say "=== 3. yedek: $yedek"
mkdir -p "$yedek"
for d in jarvis webconsole bin tools; do
  [ -d "$HEDEF/$d" ] && cp -a "$HEDEF/$d" "$yedek/" 2>/dev/null || true
done

# --- 4. git'in bildigi TUM dosyalari kopyala ------------------------------
# Tek tek secmek, bugun yasanan hatanin ta kendisiydi.
say "=== 4. kopyalanıyor (git'in bildiği tüm dosyalar)"
kopyalanan=0
cd "$KAYNAK/.." || die
for rel in $(git ls-files | grep "^jarvis-phase2/" | sed 's|^jarvis-phase2/||'); do
  kaynak_dosya="$KAYNAK/$rel"
  [ -f "$kaynak_dosya" ] || continue
  case "$rel" in
    .*|*/.*) continue ;;
  esac
  hedef_dosya="$HEDEF/$rel"
  mkdir -p "$(dirname "$hedef_dosya")"
  if ! cmp -s "$kaynak_dosya" "$hedef_dosya" 2>/dev/null; then
    cp -p "$kaynak_dosya" "$hedef_dosya"
    kopyalanan=$((kopyalanan + 1))
  fi
done
say "     $kopyalanan dosya güncellendi"

# --- 5. DOGRULA: eksik kalan var mi --------------------------------------
say "=== 5. doğrulama"
eksik=0
for rel in $(git ls-files | grep "^jarvis-phase2/" | sed 's|^jarvis-phase2/||'); do
  [ -f "$KAYNAK/$rel" ] || continue
  case "$rel" in .*|*/.*) continue ;; esac
  if [ ! -f "$HEDEF/$rel" ]; then
    say "     EKSİK: $rel"
    eksik=$((eksik + 1))
  fi
done
[ "$eksik" -eq 0 ] || die "$eksik dosya kopyalanamadı"
say "     eksik dosya yok"

# --- 6. servis --------------------------------------------------------------
say "=== 6. servis yeniden başlatılıyor"
systemctl restart "$SERVIS"
sleep 5
durum=$(systemctl is-active "$SERVIS" || true)
[ "$durum" = "active" ] || die "servis ayağa kalkmadı: $durum"

# 🔴 BEKLE, TEK ATIŞ YAPMA — 15.10.2026'da ölçüldü.
# Önceki hâli `sleep 5` sonrası TEK curl atıyordu. Servis 12:36:20'de
# başlayıp 12:36:25'te dinlemeye geçiyor; kontrol arada koşunca
# "panel 200 dönmedi" diye YANLIŞ ALARM veriyordu -- panel çalışıyordu.
# Yanlış alarm üreten bir kapı, kapıya olan güveni aşındırır.
#
# Ayrıca `|| echo "000"` curl'ün kendi "000" çıktısıyla birleşip
# "HTTP 000000" gibi anlamsız bir kod basıyordu; curl artık `-f` ile
# değil, çıktısı doğrudan okunuyor.
kod="000"
bekleme=0
for deneme in $(seq 1 20); do
  kod=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8091/ 2>/dev/null)
  [ -n "$kod" ] || kod="000"
  [ "$kod" = "200" ] && break
  sleep 1
  bekleme=$((bekleme + 1))
done
say "     servis: $durum, panel HTTP $kod (${bekleme}s beklendi)"
[ "$kod" = "200" ] || say "     UYARI: panel 20 saniyede 200 dönmedi"

hata=$(journalctl -u "$SERVIS" -n 30 --no-pager 2>/dev/null | grep -ciE "traceback|importerror" || true)
say "     son 30 satırda hata: $hata"

say
say "TAMAM. Geri almak için: $yedek"
