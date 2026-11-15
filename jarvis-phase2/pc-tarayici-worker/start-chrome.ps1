# Worker'in kullanacagi Chrome'u acar.
#
# 🔴 AYRI PROFIL. Gunluk Chrome'unla AYNI profili kullanmaz:
#    - gunluk profilde uzantilar, acik sekmeler ve senin oturumlarin var;
#      worker'in oraya girmesi hem yavas hem riskli
#    - ayni profili iki surec acamaz ("profile is already in use")
#    - bu profilde YALNIZ ChatGPT ve Claude oturumu durur
#
# 🔴 WORKER BU BETIGI CAGIRMAZ. Chrome'u worker baslatsaydi, elle
#    acilmis bir oturumla ayni profili iki surec kullanmaya calisir ve
#    profil kilitlenirdi. Chrome'u sen (ya da oturum acilista bu betik)
#    baslatir; worker yalnizca BAGLANIR.
#
# 🔴 ILK KOSUDA ELLE GIRIS YAP. Betik Chrome'u acip iki sekme acar;
#    ChatGPT ve Claude'a BIR KEZ giris yaparsin. Sifre koda yazilmaz,
#    worker kimlik bilgisi gormez.

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$Profil = Join-Path $Kok "chrome-profile"
$Port = 9222

# .env'den port/Chrome yolu okunabilir
$envYolu = Join-Path $Kok ".env"
$chromeElle = $null
if (Test-Path $envYolu) {
    foreach ($satir in Get-Content $envYolu) {
        if ($satir -match "^TARAYICI_CDP_PORT=(\d+)") { $Port = [int]$Matches[1] }
        if ($satir -match "^TARAYICI_CHROME=(.+)$")   { $chromeElle = $Matches[1].Trim() }
    }
}

# Chrome'u OTOMATIK bul. 🔴 Sabit yol yazilmaz: bu makinede Chrome
# "Program Files (x86)" altinda cikti (olculdu 16.10.2026), sartnamede
# yazan "Program Files" yolu yoktu.
$adaylar = @()
if ($chromeElle) { $adaylar += $chromeElle }
$adaylar += @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)
$Chrome = $adaylar | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Chrome) {
    Write-Host "DUR: chrome.exe bulunamadi. Denenen yollar:" -ForegroundColor Red
    $adaylar | ForEach-Object { Write-Host "  $_" }
    exit 1
}
Write-Host "Chrome: $Chrome" -ForegroundColor Green

# Zaten acik mi? Ikinci kez acmak profili kilitler.
$acik = $false
try {
    $y = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 3 -ErrorAction Stop
    $acik = $true
    Write-Host "Chrome zaten $Port portunda dinliyor: $($y.Browser)" -ForegroundColor Yellow
} catch { }

if (-not $acik) {
    New-Item -ItemType Directory -Force -Path $Profil | Out-Null
    $argumanlar = @(
        "--remote-debugging-port=$Port",
        "--user-data-dir=$Profil",
        # Yeni profil acilisinda cikan karsilama/varsayilan-tarayici
        # pencereleri otomasyonu bloklar.
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--restore-last-session=false",
        # RAM AYRIMI (15.11.2026, olculdu): bu Chrome'un her sekmesi 1.120 MB
        # JS yigini tavaniyla aciliyordu; 7-15.11 arasi 138 cokme raporunun
        # 138'i de renderer OOM (0xE0000008), sayfa cokmelerinin hepsi
        # ~1,1 GB'ta. Tavan 3 GB'a cikarildi (olculdu: bayraksiz 1.031 MB'ta
        # olur, 3072 ile 1.816 MB ayakta). 4096 YAZMA: V8 4 GB kafesinde tasar,
        # tavan 97 MB'a duser ve sekme kilitlenir (15.11 olculdu).
        "--js-flags=--max-old-space-size=3072"
    )
    Start-Process -FilePath $Chrome -ArgumentList $argumanlar
    Write-Host "Chrome aciliyor (profil: $Profil)..." -ForegroundColor Cyan
    for ($i = 1; $i -le 15; $i++) {
        Start-Sleep -Seconds 2
        try {
            $y = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 3 -ErrorAction Stop
            Write-Host "  hazir ($($i*2) sn): $($y.Browser)" -ForegroundColor Green
            $acik = $true
            break
        } catch { }
    }
    if (-not $acik) {
        Write-Host "Chrome $Port portunda dinlemedi. Baska bir Chrome ayni profili kullaniyor olabilir." -ForegroundColor Red
        exit 1
    }
    # İşler arasında aynı ChatGPT konuşmasını sürdür; yalnızca doğrulanmış sohbet URL'si yüklenir.
    $chatgptAdres = "https://chatgpt.com/"
    $sonKonusmaDosyasi = Join-Path $Kok "state\chatgpt-last-url.txt"
    if (Test-Path $sonKonusmaDosyasi) {
        $kayitliAdres = (Get-Content -Raw -LiteralPath $sonKonusmaDosyasi).Trim()
        if ($kayitliAdres -match '^https://chatgpt\.com/c/[A-Za-z0-9-]+/?$') {
            $chatgptAdres = $kayitliAdres
        }
    }
    Start-Process -FilePath $Chrome -ArgumentList @("--user-data-dir=$Profil", $chatgptAdres)
    Start-Sleep -Seconds 2
    Start-Process -FilePath $Chrome -ArgumentList @("--user-data-dir=$Profil", "https://claude.ai/new")
}

Write-Host ""
Write-Host "SIMDI: acilan pencerede ChatGPT ve Claude'a giris yap (bir kez yeter)." -ForegroundColor Cyan
Write-Host "Oturum bu profilde kalir; worker ona BAGLANIR, sifre gormez." -ForegroundColor Cyan

