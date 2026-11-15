# PC-1 sanal bellek (commit) tavanini buyutur. YONETICI PowerShell'de BIR KEZ.
#
# Neden (15.11.2026 olcumu): commit 44,9 / 51,8 GB (%87). Tavan = RAM 31,8 GB
# + C:\pagefile 15 GB + D:\pagefile 5 GB. C:'de yalniz 9,7 GB bos oldugu icin
# C'deki sayfa dosyasi buyuyemiyor. Chrome bir sekmeye bellek ayiramayinca
# sekmeyi 0xE0000008 (OOM) ile dusurur. D:'de 371 GB bos: D'deki sayfa
# dosyasi 16-32 GB sabitlenir, tavan ~63-79 GB olur. C'ye DOKUNULMAZ.
#
# Etkisi yeniden baslatmadan sonra tam gelir. Geri alma: ayni ekranda
# D: icin "Sistem tarafindan yonetilen boyut" secilir.
$ErrorActionPreference = "Stop"
$ayar = Get-CimInstance Win32_PageFileSetting | Where-Object { $_.Name -like 'D:*' }
if (-not $ayar) { Write-Host "DUR: D: sayfa dosyasi ayari yok" -ForegroundColor Red; exit 1 }
Set-CimInstance -InputObject $ayar -Property @{ InitialSize = [uint32]16384; MaximumSize = [uint32]32768 }
Get-CimInstance Win32_PageFileSetting | Format-Table Name, InitialSize, MaximumSize -AutoSize
Write-Host "Tamam. Etkisi icin bilgisayari uygun bir anda yeniden baslat." -ForegroundColor Green
