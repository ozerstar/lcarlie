#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - n8n WORKFLOW SURUM TAKIBI
#
# NEDEN VAR. 25.09.2026'da olculdu: kod 24.09'da GitHub'a tasindi ama
# workflow'lar tasinmadi. Is mantiginin bir kismi workflow JSON'larinda
# duruyor ve tek kopyasi Postgres'ti. Gecelik sifreli yedek workflows.json
# iceriyor -- yani GERI YUKLENEBILIR, ama "kim neyi ne zaman degistirdi"
# sorusunun cevabi hicbir yerde yoktu. Bu betik o boslugu kapatir.
#
# 🔴 YETIM (orphan) DAL KULLANILIR. Depoda es zamanli calisan kod dallari
# var; workflow JSON'larini onlarin gecmisine karistirmak her birlestirmede
# gereksiz catisma uretirdi. n8n-workflows dali kodla hicbir ortak ata
# paylasmaz.
#
# 🔴 EXPORT YAYINDAN DUSURMEZ. n8n-yayinla.sh basliginda yazili tuzak
# `import:workflow` icindir; `export:workflow` salt okunurdur ve
# workflow'larin aktifligine dokunmaz. Yine de bu betik yayina HIC
# dokunmaz: yalniz disa aktarir ve commit'ler.
#
# Kullanim: n8n-wf-yedek.sh [--push]
# =============================================================================
set -uo pipefail

KAP=lcarlie-n8n
DEPO=/opt/lcarlie/n8n-wf-git
GECICI=/tmp/n8n-wf-disa
PUSH=0
for a in "$@"; do [ "$a" = "--push" ] && PUSH=1; done

alarm() {
  # Alarm merkezi TEK bildirim kapisidir; burada kendi posta mantigimizi
  # kurmuyoruz. Cikis kodu her zaman 0 oldugu icin bizi dusurmez.
  /opt/lcarlie/alarm.sh "$@" >/dev/null 2>&1 || true
}

[ -d "$DEPO" ] || { alarm FAILED "n8n.wfyedek" "Workflow yedek deposu yok" "$DEPO bulunamadi"; exit 1; }

# --- 1) Konteynerden disa aktar ---------------------------------------------
docker exec "$KAP" sh -c "rm -rf $GECICI && mkdir -p $GECICI && n8n export:workflow --all --pretty --separate --output=$GECICI" >/dev/null 2>&1
CIKIS=$?
if [ "$CIKIS" -ne 0 ]; then
  alarm FAILED "n8n.wfyedek" "Workflow disa aktarilamadi" "docker exec cikis=$CIKIS"
  exit 1
fi

ADET=$(docker exec "$KAP" sh -c "ls -1 $GECICI/*.json 2>/dev/null | wc -l" | tr -d '\r')
# 🔴 SIFIR DOSYA BIR BASARI DEGILDIR. Bos bir disa aktarimi commit'lemek,
# gecmisteki dogru kopyayi "silinmis" gibi gosterirdi.
if [ "${ADET:-0}" -lt 1 ]; then
  alarm FAILED "n8n.wfyedek" "Workflow disa aktarimi BOS dondu" "dosya sayisi=$ADET -- commit YAPILMADI"
  exit 1
fi

# --- 2) Depoya kopyala -------------------------------------------------------
mkdir -p "$DEPO/workflows"
# Silinen workflow da bir degisikliktir: once temizle, sonra kopyala.
rm -f "$DEPO"/workflows/*.json
docker cp "$KAP:$GECICI/." "$DEPO/workflows/" >/dev/null 2>&1 || {
  alarm FAILED "n8n.wfyedek" "docker cp basarisiz" "kaynak=$GECICI"; exit 1; }
docker exec "$KAP" rm -rf "$GECICI" >/dev/null 2>&1

# --- 2b) SIR REDAKSIYONU ------------------------------------------------------
# 🔴 NEDEN VAR (26.09.2026). Meta webhook dogrulama anahtari, n8n Code
# dugumu ortam degiskeni okuyamadigi icin (N8N_BLOCK_ENV_ACCESS_IN_NODE=true)
# URETIM ANINDA workflow'a gomulmek zorunda. Bu betik ise workflow JSON'unu
# git'e commit'liyor -- yani anahtar, hicbir sey yapilmazsa surum gecmisine
# KALICI olarak sizardi. Depo private olsa bile sirri git'e yazmak yanlistir:
# gecmisten sir silmek, dosyadan silmekten cok daha zordur.
#
# Burada yalnizca DEGER maskelenir; degisken adi ve yapinin geri kalani aynen
# durur, boylece "kim neyi degistirdi" izi bozulmaz.
#
# ⚠️ Bu yedek artik OLDUGU GIBI geri yuklenemez: geri yuklemede workflow'lar
#    ureticiden yeniden uretilmelidir (n8n-yayinla.sh zaten oyle yapiyor).
#    Yedegin amaci degisiklik izi tutmak, birebir kopya olmak DEGIL.
REDAKTE=0
for _sir_adi in MESSENGER_VERIFY_TOKEN WHATSAPP_VERIFY_TOKEN MESSENGER_PANEL_TOKEN; do
  _sir=$(awk -F= -v a="^${_sir_adi}=" '$0 ~ a {print substr($0, index($0,"=")+1); exit}' /opt/lcarlie/n8n/.env 2>/dev/null || true)
  [ -n "${_sir:-}" ] || continue
  for _f in "$DEPO"/workflows/*.json; do
    [ -e "$_f" ] || continue
    grep -qF "$_sir" "$_f" 2>/dev/null || continue
    SIR="$_sir" AD="$_sir_adi" python3 -c '
import io, os, sys
yol = sys.argv[1]
sir = os.environ["SIR"]; ad = os.environ["AD"]
s = io.open(yol, encoding="utf-8").read()
io.open(yol, "w", encoding="utf-8").write(s.replace(sir, "<REDAKTE:" + ad + ">"))
' "$_f"
    REDAKTE=$((REDAKTE+1))
  done
done
[ "$REDAKTE" -gt 0 ] && echo "  sir redakte edildi: $REDAKTE dosya"
SURUM=$(docker exec "$KAP" n8n --version 2>/dev/null | tr -d '\r')
# 🔴 ZAMAN DAMGASI YAZILMAZ. Ilk surumde buraya $(date -Is) konmustu ve
# olculdu: dosya HER kosuda degisiyor, yani workflow'lar hic degismese bile
# her gun bir commit dusuyordu. O gurultu "degisiklik izi" amacini bozar --
# yuz commit icinde gercek degisikligi aramak gerekirdi. Commit tarihini
# git zaten tutuyor.
printf 'n8n surumu: %s\nWorkflow sayisi: %s\n' "$SURUM" "$ADET" > "$DEPO/SURUM.txt"

# --- 3) Degisiklik varsa commit'le ------------------------------------------
cd "$DEPO" || exit 1
git add -A >/dev/null 2>&1
if git diff --cached --quiet 2>/dev/null; then
  echo "degisiklik yok"
  exit 0
fi

OZET=$(git diff --cached --name-only | sed 's#workflows/##;s#\.json##' | tr '\n' ' ')
git -c user.name="LCARLIE n8n yedek" -c user.email="n8n-yedek@localhost" \
    commit -q -m "n8n workflow anlik goruntusu: ${OZET}" \
              -m "n8n $SURUM - $ADET workflow" 2>&1 | tail -2

if [ "$PUSH" = "1" ]; then
  if git push -q origin n8n-workflows 2>&1; then
    echo "gonderildi"
  else
    # Gonderememek yerel commit'i gecersiz kilmaz; gecmis burada duruyor.
    alarm DEGRADED "n8n.wfyedek.push" "Workflow dali GitHub'a gonderilemedi" \
      "yerel commit alindi, uzak gonderim basarisiz"
  fi
fi
echo "commit alindi: $OZET"
