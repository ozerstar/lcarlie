# =============================================================================
# L'CARLIE - SOHBET WIDGET'INI YAYINLA
#
# Kaynak dosya : 01 LCARLIE\SITE-SOHBET-WIDGET.html  (icindeki <script> blogu)
# Hedef        : /opt/lcarlie/widget/lc-sohbet.js
# Canli adres  : https://n8n.lcarlie.shop/lc-sohbet.js
#
# 🔴 Wix Ozel Kod alaninin 15.000 karakter siniri var; widget bundan buyuk.
#    Bu yuzden kod sunucudan servis edilir, Wix'te sadece tek satir durur:
#      <script src="https://n8n.lcarlie.shop/lc-sohbet.js" defer></script>
#    Widget guncellemek icin Wix'e DOKUNMAK GEREKMEZ - bu betik yeter.
#
# Kullanim:  .\widget-yayinla.ps1
# =============================================================================
$ErrorActionPreference = 'Stop'

$kaynak = "C:\Users\ozery\OneDrive\Masaüstü\01 LCARLIE\SITE-SOHBET-WIDGET.html"
$gecici = Join-Path $env:TEMP 'lc-sohbet.js'

function Yaz($m, $r = 'Gray') { Write-Host $m -ForegroundColor $r }

if (-not (Test-Path $kaynak)) { Yaz "Kaynak bulunamadi: $kaynak" Red; exit 1 }

# --- 1) <script> blogunu cikar ----------------------------------------------
$html = Get-Content $kaynak -Raw -Encoding UTF8

# 🔴 ONCE HTML ACIKLAMALARINI AT.
# Aciklama blogunda ornek olarak gecen bir script etiketi, asagidaki desen
# tarafindan gercek kod sanilip yakalaniyordu ve cikan dosya bozuk oluyordu.
# (Sozdizimi denetimi yakaladi, yayinlanmadi - ama kaynagi burasiydi.)
$html = [regex]::Replace($html, '(?s)<!--.*?-->', '')

$m = [regex]::Match($html, '(?s)<script>(.*?)</script>')
if (-not $m.Success) { Yaz "Dosyada <script> blogu bulunamadi." Red; exit 1 }
$js = $m.Groups[1].Value.Trim()

$baslik = @"
/* =====================================================================
   L'CARLIE - Site Canli Sohbet Widget'i
   Kaynak : Masaustu\01 LCARLIE\SITE-SOHBET-WIDGET.html
   Uretim : widget-yayinla.ps1  ($(Get-Date -Format 'dd.MM.yyyy HH:mm'))
   Adres  : https://n8n.lcarlie.shop/lc-sohbet.js

   Wix tarafinda SADECE su satir durur:
     <script src="https://n8n.lcarlie.shop/lc-sohbet.js" defer></script>
   ===================================================================== */

"@
$tam = $baslik + $js
Set-Content $gecici $tam -Encoding UTF8 -NoNewline
Yaz "  JS cikarildi: $([math]::Round($tam.Length/1KB,1)) KB" DarkGray

# --- 2) Sunucuya gonder ------------------------------------------------------
scp -q $gecici lcarlie:/root/lc-sohbet.js
if ($LASTEXITCODE -ne 0) { Yaz "Gonderilemedi." Red; exit 1 }

# --- 3) Sozdizimini DENETLE, gecerse yayina al -------------------------------
# 🔴 Once denetle: bozuk JS yayinlanirsa widget hic gorunmez ve sebebi
#    tarayici konsoluna bakmadan anlasilmaz.
$kontrol = ssh lcarlie @'
# 🔴 DOCKER_API_VERSION SABITLENMEZ (20.09.2026'da kaldirildi) - docker
# yukseltilince daemon min API 1.44 istedi ve sabitlenmis 1.43 ile her
# cagri patladi. Istemci surumu kendi pazarlar.
set -uo pipefail

# 🔴 SABIT GECICI AD + KONTROLSUZ 'docker cp' = DENETIMI ATLATIR.
# Onceki hali her calismada ayni adi (/tmp/lc-kontrol.js) kullaniyor ve
# 'docker cp'nin cikis kodunu HIC kontrol etmiyordu. Kopyalama basarisiz
# olursa (n8n yeniden baslarken tipik) 'node --check' ONCEKI CALISMADAN
# KALAN dosyayi denetler, gecer, ve yeni - denetlenmemis - dosya canli
# siteye yayinlanirdi. Betik de yesil "Sozdizimi tamam" yazardi.
# Cozum: her calismada benzersiz ad, cikis kodu kontrolu, ve is bitince
# root olarak temizlik (docker cp root sahipli dosya birakir, n8n'in
# 'node' kullanicisi silemez).
GECICI="/tmp/lc-kontrol-$$-$(date +%s).js"

if ! docker cp /root/lc-sohbet.js "lcarlie-n8n:$GECICI" >/dev/null 2>&1; then
  echo "KOPYALANAMADI - denetim yapilamadi, yayinlanmadi"
  exit 1
fi

if docker exec lcarlie-n8n node --check "$GECICI" 2>&1; then
  cp /root/lc-sohbet.js /opt/lcarlie/widget/lc-sohbet.js
  chmod 644 /opt/lcarlie/widget/lc-sohbet.js
  # Yayinlanan dosya gonderilenle birebir ayni mi?
  A=$(md5sum /root/lc-sohbet.js | cut -d" " -f1)
  B=$(md5sum /opt/lcarlie/widget/lc-sohbet.js | cut -d" " -f1)
  if [ "$A" = "$B" ]; then echo "YAYINLANDI"; else echo "KOPYA BOZUK - icerik tutmuyor"; fi
else
  echo "SOZDIZIMI HATALI - yayinlanmadi"
fi

# Eski surumlerden kalan sabit adli dosyayi da temizle
docker exec -u 0 lcarlie-n8n rm -f "$GECICI" /tmp/lc-kontrol.js >/dev/null 2>&1 || true
'@

if ($kontrol -match 'YAYINLANDI') {
  Yaz "  Sozdizimi tamam, yayina alindi" Green
} else {
  Yaz "  $kontrol" Red
  Yaz "  Canlidaki widget DEGISMEDI." Yellow
  exit 1
}

# --- 4) Canli dogrulama ------------------------------------------------------
Start-Sleep -Seconds 2
$sonuc = ssh lcarlie 'curl -s -o /dev/null -w "%{http_code} %{size_download}" https://n8n.lcarlie.shop/lc-sohbet.js'
$parca = $sonuc -split ' '
if ($parca[0] -eq '200') {
  Yaz "`nWidget yayinda: HTTP 200, $($parca[1]) bayt" Green
  Yaz "https://n8n.lcarlie.shop/lc-sohbet.js" DarkGray
  Yaz "`nSitede gormek icin tarayicida Ctrl+F5 (onbellek 5 dakika)." DarkGray
} else {
  # 🔴 EXIT 1 SART. Onceki hali burada sadece kirmizi yazi basip 0 ile
  #    cikiyordu; ayrica ssh basarisiz olursa $parca[0] bos kalir ve yine
  #    bu dala duserdi. Her iki durumda da cagiran "yayinlandi" sanirdi.
  $kod = if ($parca[0]) { $parca[0] } else { "yanit yok" }
  Yaz "`nUYARI: canli adres $kod dondu - widget dogrulanamadi." Red
  Yaz "Dosya sunucuya yazildi ama servis edilemiyor olabilir (Caddy rotasi?)." Yellow
  exit 1
}
