# TARAYICI WORKER KURULUMU (PC-1, Windows)
#
# Ne yapar:
#   1. Diskin NTFS oldugunu dogrular
#   2. Python sanal ortamini kurar ve playwright'i yukler
#   3. Bu worker'a AYRI bir SSH anahtari uretir (varsa dokunmaz)
#   4. Sunucunun host anahtarini known_hosts'a alir
#   5. .env sablonunu olusturur
#   6. Sunucuya eklenmesi gereken authorized_keys satirini EKRANA yazar
#
# 🔴 YONETICI GEREKMEZ. Gorev SYSTEM olarak kosmayacak (bkz. worker.py);
#    bu yuzden anahtar da normal kullanicinin okuyabildigi yerde durur.
#    Mevcut "Jarvis Metrik" gorevinin anahtari SYSTEM'e aittir ve o
#    anahtar BURADA KULLANILMAZ -- iki gorev, iki anahtar, iki gerekce.
#
# 🔴 playwright'in kendi tarayicisi INDIRILMEZ (`playwright install`
#    yok). Worker senin GERCEK Chrome'una CDP ile baglanir, cunku
#    ChatGPT/Claude oturumu o profilde. Playwright'in chromium'u ~500 MB
#    yer tutar ve bu makinede C: diski %90 dolu -- indirmek hem
#    gereksiz hem riskli.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Kok = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Worker dizini: $Kok" -ForegroundColor Cyan

# --- 1. Disk kontrolu -------------------------------------------------------
# D: exFAT; OpenSSH exFAT'te dosya iznini tutamaz ve anahtari
# "bad permissions" diye reddeder. Belirtisi sinsi: gunluge "baglandi"
# yazar ama surec aninda oler. (gorsel-kuyruk/README.md, 24.09.2026)
$surucu = (Get-Item $Kok).PSDrive.Name
$ds = (Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${surucu}:'").FileSystem
if ($ds -ne "NTFS") {
    Write-Host "DUR: worker $surucu`: uzerinde ve dosya sistemi $ds." -ForegroundColor Red
    Write-Host "SSH anahtari NTFS'te olmak ZORUNDA. Worker'i NTFS bir diske tasi." -ForegroundColor Red
    exit 1
}
$bos = [math]::Round((Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${surucu}:'").FreeSpace / 1GB, 1)
Write-Host "  $surucu`: $ds, $bos GB bos" -ForegroundColor Green

# --- 2. Python sanal ortami -------------------------------------------------
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) {
    Write-Host "DUR: python bulunamadi. python.org'dan 3.11+ kur." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $python" -ForegroundColor Green

$venv = Join-Path $Kok "venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "Sanal ortam kuruluyor..." -ForegroundColor Cyan
    & $python -m venv $venv
}
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip
Write-Host "playwright yukleniyor..." -ForegroundColor Cyan
& $vpy -m pip install --quiet playwright
& $vpy -c "import playwright, sys; print('  playwright kurulu, python', sys.version.split()[0])"

# --- 3. SSH anahtari --------------------------------------------------------
$sshDizin = Join-Path $Kok "ssh"
New-Item -ItemType Directory -Force -Path $sshDizin | Out-Null
$anahtar = Join-Path $sshDizin "tarayici_worker_ed25519"

if (Test-Path $anahtar) {
    Write-Host "SSH anahtari zaten var, dokunulmadi: $anahtar" -ForegroundColor Yellow
} else {
    Write-Host "SSH anahtari uretiliyor (parolasiz -- gorev etkilesimsiz kosar)..." -ForegroundColor Cyan
    & ssh-keygen -t ed25519 -f $anahtar -N '""' -C "tarayici-worker@pc1" | Out-Null
}

# Anahtari YALNIZ bu kullaniciya ac. OpenSSH baskalarinin okuyabildigi
# anahtari reddeder; icacls olmadan "bad permissions" alinir.
& icacls $anahtar /inheritance:r /grant:r "${env:USERNAME}:(R)" | Out-Null
Write-Host "  izinler kisitlandi" -ForegroundColor Green

# --- 4. Sunucu adresi -------------------------------------------------------
$env_yolu = Join-Path $Kok ".env"
$sunucu = $null
if (Test-Path $env_yolu) {
    $es = Get-Content $env_yolu | Select-String "^TARAYICI_SUNUCU=(.+)$"
    if ($es) { $sunucu = $es.Matches[0].Groups[1].Value.Trim() }
}
# 🔴 ETKILESIMSIZ KOSUYA DAYANIKLI. Ilk halde burada Read-Host vardi;
# betik etkilesimsiz calistirilinca bos deger dondu ve ssh-keyscan
# "usage:" yazip dustu. Sira: .env -> ~/.ssh/config -> soru.
if (-not $sunucu) {
    $sshConf = Join-Path $env:USERPROFILE ".ssh\config"
    if (Test-Path $sshConf) {
        $icinde = $false
        foreach ($satir in Get-Content $sshConf) {
            if ($satir -match '^\s*Host\s+(.+)$') {
                $icinde = (($Matches[1].Trim() -split '\s+') -contains 'lcarlie')
            } elseif ($icinde -and $satir -match '^\s*HostName\s+(\S+)') {
                $sunucu = $Matches[1]; break
            }
        }
    }
    if ($sunucu) { Write-Host "  sunucu ~/.ssh/config'ten alindi: $sunucu" -ForegroundColor Green }
}
if (-not $sunucu -and [Environment]::UserInteractive) {
    $sunucu = Read-Host "Sunucu IP/host (orn. 185.169.180.68)"
}
if (-not $sunucu) {
    Write-Host "DUR: sunucu adresi bulunamadi. .env icine TARAYICI_SUNUCU=... yaz." -ForegroundColor Red
    exit 1
}

# --- 5. known_hosts --------------------------------------------------------
$known = Join-Path $sshDizin "known_hosts"

# Host anahtari uc yoldan aranir, SIRAYLA.
#
# 🔴 ONCE MEVCUT known_hosts. Bu makine sunucuya zaten baglaniyor
#    (`ssh lcarlie`), yani host anahtari KULLANICI TARAFINDAN ZATEN
#    KABUL EDILMIS durumda. Onu kopyalamak yeniden taramaktan hem daha
#    guvenli (ikinci bir ilk-karsilasma riski yok) hem daha guvenilir.
#
# 🔴 ssh-keyscan YEDEK, CUNKU BU MAKINEDE CALISMIYOR -- olculdu
#    16.10.2026: Windows'un OpenSSH_for_Windows_9.5p1 ssh-keyscan'i
#    sunucunun KEX yontemini (sntrup761x25519-sha512@openssh.com)
#    desteklemiyor, "choose_kex: unsupported KEX method" diyor ve hic
#    anahtar dondurmuyor. Ayni surumun `ssh`'i sorunsuz baglaniyor.
#    Git'in getirdigi ssh-keyscan daha yeni oldugu icin once o denenir.
$satirlar = @()

$kullaniciKH = Join-Path $env:USERPROFILE ".ssh\known_hosts"
if (Test-Path $kullaniciKH) {
    $satirlar = @(Get-Content $kullaniciKH | Where-Object {
        $_ -and ($_ -notmatch '^\s*#') -and ($_ -match [regex]::Escape($sunucu)) })
    if ($satirlar.Count -gt 0) {
        Write-Host "  host anahtari mevcut known_hosts'tan alindi ($($satirlar.Count) satir)" -ForegroundColor Green
    }
}

if ($satirlar.Count -eq 0) {
    $eskiEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $gitKeyscan = Join-Path $env:ProgramFiles "Git\usr\bin\ssh-keyscan.exe"
    foreach ($ks in @($gitKeyscan, "ssh-keyscan")) {
        if ($ks -ne "ssh-keyscan" -and -not (Test-Path $ks)) { continue }
        $tarama = & $ks -t ed25519 $sunucu 2>$null
        $satirlar = @($tarama | Where-Object {
            $_ -and -not ($_.ToString().StartsWith("#")) })
        if ($satirlar.Count -gt 0) {
            Write-Host "  host anahtari tarandi ($ks)" -ForegroundColor Green
            break
        }
    }
    $ErrorActionPreference = $eskiEAP
}

if ($satirlar.Count -eq 0) {
    # 🔴 Bos known_hosts = StrictHostKeyChecking=yes ile HER baglanti
    #    reddedilir. Uyari yazip gecmek, worker'i sessizce calismaz
    #    birakmak olurdu.
    Write-Host "DUR: sunucunun host anahtari alinamadi ($sunucu)." -ForegroundColor Red
    Write-Host "     Once 'ssh lcarlie' ile bir kez baglanin, sonra tekrar kosturun." -ForegroundColor Red
    exit 1
}
$satirlar | Set-Content -Path $known -Encoding ascii
Write-Host "  known_hosts yazildi" -ForegroundColor Green

# --- 6. .env ----------------------------------------------------------------
if (-not (Test-Path $env_yolu)) {
    @"
# Tarayici worker ayarlari. 🔴 BU DOSYA DEPOYA GIRMEZ, LOGA YAZILMAZ.
TARAYICI_SUNUCU=$sunucu
TARAYICI_SSH_KULLANICI=root
TARAYICI_SSH_ANAHTAR=$anahtar
TARAYICI_KNOWN_HOSTS=$known
TARAYICI_WORKER_ADI=pc1-chrome
TARAYICI_CDP_PORT=9222
# Chrome yolu bos birakilirsa otomatik bulunur (onerilen).
TARAYICI_CHROME=
"@ | Set-Content -Path $env_yolu -Encoding utf8
    Write-Host ".env olusturuldu" -ForegroundColor Green
} else {
    Write-Host ".env zaten var, dokunulmadi" -ForegroundColor Yellow
}

# --- 7. Sunucuda yapilacak --------------------------------------------------
$acik = (Get-Content "$anahtar.pub" -Raw).Trim()
Write-Host ""
Write-Host "===================== SUNUCUDA YAPILACAK =====================" -ForegroundColor Cyan
Write-Host "Asagidaki satiri sunucudaki /root/.ssh/authorized_keys'e EKLE."
Write-Host "Zorunlu komut sayesinde bu anahtarla KABUK ALINAMAZ."
Write-Host ""
Write-Host ('command="/opt/lcarlie/bin/tarayici-kapi",no-agent-forwarding,no-port-forwarding,no-pty,no-X11-forwarding,no-user-rc ' + $acik) -ForegroundColor White
Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Sonra sirayla:" -ForegroundColor Cyan
Write-Host "  1) .\start-chrome.ps1   <- Chrome'u ac, ChatGPT ve Claude'a BIR KEZ elle giris yap"
Write-Host "  2) .\kur-gorev.ps1      <- oturum acilinca otomatik baslayacak gorevi kur"
Write-Host "  3) powercfg /change standby-timeout-ac 0   <- uyku kapali (README)"
