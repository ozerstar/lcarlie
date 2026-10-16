# "Jarvis Tarayici Worker" zamanlanmis gorevini kurar.
#
# 🔴 SYSTEM DEGIL, KULLANICI OLARAK KOSAR -- ve bu SART.
#    Windows servisi / SYSTEM gorevi session 0'da kosar; orada gorunur
#    bir masaustu yoktur ve oturum acmis kullanicinin Chrome profili
#    kullanilamaz. ChatGPT/Claude oturumu tam olarak o profilde durdugu
#    icin worker SYSTEM olamaz.
#
#    Bu yuzden:
#      LogonType = Interactive        (yalniz kullanici oturum acmissa)
#      Trigger   = AtLogOn            (oturum acilinca basla)
#
#    Mevcut "Jarvis Metrik" gorevi SYSTEM'dir ve oyle KALIR: o yalniz
#    SSH ile olcum iter, tarayici gerektirmez. Iki gorev, iki anahtar,
#    iki ayri gerekce. Birini digerine benzetmeye calismak hata olur.
#
# 🔴 YONETICI GEREKMEZ. Kendi kullanicin adina gorev kaydetmek icin
#    yukseltme gerekmez (SYSTEM gorevi icin gerekirdi).
#
# KULLANIM: powershell -ExecutionPolicy Bypass -File .\kur-gorev.ps1

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ad = "Jarvis Tarayici Worker"
$ChromeAd = "Jarvis Tarayici Chrome"

$vpy = Join-Path $Kok "venv\Scripts\python.exe"
$worker = Join-Path $Kok "worker.py"
$chromeBetik = Join-Path $Kok "start-chrome.ps1"

foreach ($p in @($vpy, $worker, $chromeBetik)) {
    if (-not (Test-Path $p)) {
        Write-Host "DUR: bulunamadi -> $p" -ForegroundColor Red
        Write-Host "Once .\setup.ps1 calistir." -ForegroundColor Red
        exit 1
    }
}

# Var olan gorevi degistirmeden once kaldir: ayni adli iki tetikleyici
# birikirse iki worker kosar. (Kuyruk atomik oldugu icin ayni is iki kez
# ISLENMEZ, ama iki surec bosa kaynak yakar ve gunluk karisir.)
foreach ($g in @($Ad, $ChromeAd)) {
    Unregister-ScheduledTask -TaskName $g -Confirm:$false -ErrorAction SilentlyContinue
}

$asil = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

# --- 1. Chrome: oturum acilinca ac -----------------------------------------
$chromeEylem = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$chromeBetik`""
$chromeAyar = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $ChromeAd `
    -Action $chromeEylem -Trigger (New-ScheduledTaskTrigger -AtLogOn) `
    -Principal $asil -Settings $chromeAyar | Out-Null
Write-Host "Gorev kuruldu: $ChromeAd" -ForegroundColor Green

# --- 2. Worker: oturum acilinca + cokerse yeniden ---------------------------
# ExecutionTimeLimit = 0 (sinirsiz): worker surekli kosan bir dongudur,
# tavan koymak onu her gun sessizce oldururdu.
$workerEylem = New-ScheduledTaskAction -Execute $vpy -Argument "`"$worker`"" -WorkingDirectory $Kok
$workerAyar = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 2)

# Chrome'un acilmasi icin worker 40 sn gecikmeyle baslar; yoksa ilk
# nabizda "chrome KAPALI" yazar ve bosa bir uyari uretir.
$tetik = New-ScheduledTaskTrigger -AtLogOn
$tetik.Delay = "PT40S"

Register-ScheduledTask -TaskName $Ad -Action $workerEylem -Trigger $tetik `
    -Principal $asil -Settings $workerAyar | Out-Null
Write-Host "Gorev kuruldu: $Ad" -ForegroundColor Green

Write-Host ""
Write-Host "Simdi baslatiliyor..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $ChromeAd
Start-Sleep -Seconds 12
Start-ScheduledTask -TaskName $Ad
Start-Sleep -Seconds 20

foreach ($g in @($ChromeAd, $Ad)) {
    $b = Get-ScheduledTaskInfo -TaskName $g
    Write-Host ""
    Write-Host ("{0}" -f $g) -ForegroundColor Cyan
    Write-Host ("  Durum       : " + (Get-ScheduledTask -TaskName $g).State)
    Write-Host ("  Son kosu    : " + $b.LastRunTime)
    Write-Host ("  Son sonuc   : " + $b.LastTaskResult + "   (0 = basarili, 267009 = kosuyor)")
}

$gunluk = Join-Path $Kok "worker.log"
if (Test-Path $gunluk) {
    Write-Host ""
    Write-Host "worker.log son satirlar:" -ForegroundColor Cyan
    Get-Content $gunluk -Tail 8
} else {
    Write-Host ""
    Write-Host "worker.log henuz olusmadi -- worker hic kosmamis olabilir." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🔴 GUC AYARI: bilgisayar uyursa worker durur ve isler kuyrukta bekler." -ForegroundColor Yellow
Write-Host "   Uykuyu kapatmak icin (yonetici PowerShell):" -ForegroundColor Yellow
Write-Host "     powercfg /change standby-timeout-ac 0" -ForegroundColor White
Write-Host "     powercfg /change hibernate-timeout-ac 0" -ForegroundColor White
