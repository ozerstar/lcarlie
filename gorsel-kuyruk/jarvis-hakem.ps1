# PC-2 (RTX 5060) - SIRA HAKEMI
#
# NEDEN VAR -- OLCULDU 24.09.2026
#   masaustu 1,7 GB + Qwen3-8B 5,8 GB + ComfyUI/SDXL 2,5-2,9 GB = ~10,4 GB
#   Kartta 8,15 GB var. LLM ile gorsel uretimi AYNI ANDA SIGMIYOR.
# Bu makinede iki kip var, gecisi bu betik yonetir:
#   LLM kipi (varsayilan)  llama-server 8099 -> sunucu 8097
#   GORSEL kipi            ComfyUI      8188 -> sunucu 8095
#
# GUVENLIK
#   - GORSEL kipinde en fazla EnUzunGorselDk dakika kalinir; kuyruk dolu olsa
#     bile LLM'e donulur. LLM'in suresiz ac kalmasi kabul edilemez.
#   - Her hata yolu LLM kipine DONUSLE biter. "Ne LLM ne gorsel" olusamaz.
#   - Is once calisan/ dizinine TASINIR sonra islenir: cokmede ayni is iki kez
#     uretilmez, orada asili kalir ve gorulur.
#
# Acilista SYSTEM olarak calisir; anahtar NTFS'te olmak ZORUNDA (exFAT izin
# tutmaz, OpenSSH reddeder -- olculdu).

$ErrorActionPreference = "Continue"
$Root   = "C:\lcarlie-llama"
$Exe    = Join-Path $Root "bin\llama-server.exe"
$Model  = Join-Path $Root "models\Qwen3-8B-Q4_K_M.gguf"
$Log    = Join-Path $Root "hakem.log"
$Key    = "C:\lcarlie-llama\ssh\id_ed25519"
$Known  = "C:\lcarlie-llama\ssh\known_hosts"
$Sunucu = "root@185.169.180.68"
$K      = "/opt/lcarlie/gorsel-kuyruk"

$LlmPort = 8099
$LlmUzak = 8097
$CmfPort = 8188
$CmfUzak = 8095
$CmfPy    = "C:\comfy\ComfyUI_windows_portable\python_embeded\python.exe"
$CmfMain  = "C:\comfy\ComfyUI_windows_portable\ComfyUI\main.py"
$CmfDizin = "C:\comfy\ComfyUI_windows_portable\ComfyUI"
$CmfCikti = "C:\comfy\cikti"
$EnUzunGorselDk = 30

$Ssh = @("-i",$Key,"-o","IdentitiesOnly=yes","-o","UserKnownHostsFile=$Known",
         "-o","StrictHostKeyChecking=yes","-o","BatchMode=yes",
         "-o","ConnectTimeout=12","-o","ServerAliveInterval=30","-o","ServerAliveCountMax=3")

function Say($m) {
  $s = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  try { Add-Content -Path $Log -Encoding UTF8 -Value $s } catch {}
}
if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 1MB) {
  Move-Item $Log "$Log.1" -Force -EA SilentlyContinue
}

function Saglikli($port) {
  try { return (Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 4 -EA Stop).status -eq "ok" }
  catch { return $false }
}
function Uzak($komut) {
  try { return (& ssh @Ssh $Sunucu $komut 2>$null | Out-String).Trim() } catch { return "" }
}
function TunelKur($uzak, $yerel) {
  $a = @("-N","-R","${uzak}:127.0.0.1:${yerel}") + $Ssh + @("-o","ExitOnForwardFailure=yes",$Sunucu)
  $p = Start-Process -FilePath "ssh" -ArgumentList $a -WindowStyle Hidden -PassThru `
       -RedirectStandardError (Join-Path $Root "tunnel.err")
  Start-Sleep 3
  if ($p.HasExited) {
    $h = ""
    try { $h = (Get-Content (Join-Path $Root "tunnel.err") -Raw).Trim() } catch {}
    Say ("tunel OLDU " + $uzak + ": " + ($h -replace "\r?\n"," | "))
    return -1
  }
  Say ("tunel acildi " + $uzak + " pid " + $p.Id)
  return $p.Id
}
function TunelKapat($tpid) {
  if ($tpid -gt 0) { Stop-Process -Id $tpid -Force -EA SilentlyContinue }
}
function SureciKapat($ad, $desen) {
  $f = "Name=" + [char]39 + $ad + [char]39
  Get-CimInstance Win32_Process -Filter $f -EA SilentlyContinue |
    Where-Object { $_.CommandLine -like $desen } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
}

function LlmBaslat {
  $a = @("-m",$Model,"--host","127.0.0.1","--port",$LlmPort,"-c","8192","-ngl","99","--no-warmup")
  Start-Process -FilePath $Exe -ArgumentList $a -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Root "server.log") `
    -RedirectStandardError  (Join-Path $Root "server.err")
  Say "llama-server basladi"
}
function ComfyBaslat {
  New-Item -ItemType Directory -Force -Path $CmfCikti | Out-Null
  $cmd = "$CmfPy -s $CmfMain --listen 127.0.0.1 --port $CmfPort --output-directory $CmfCikti"
  $tam = "cmd.exe /c " + [char]34 + $cmd + " > C:\comfy\comfy.log 2>&1" + [char]34
  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $tam
    CurrentDirectory = $CmfDizin } | Out-Null
  for ($i=1; $i -le 25; $i++) {
    Start-Sleep 5
    try {
      Invoke-RestMethod "http://127.0.0.1:$CmfPort/system_stats" -TimeoutSec 4 -EA Stop | Out-Null
      Say ("ComfyUI hazir " + ($i*5) + " sn")
      return $true
    } catch {}
  }
  Say "ComfyUI ACILMADI"
  return $false
}
function ComfyDurdur {
  SureciKapat "python.exe" "*ComfyUI*main.py*"
  Say "ComfyUI durduruldu"
}

function IsIsle($is) {
  $akis = @{
    "4" = @{ class_type="CheckpointLoaderSimple"; inputs=@{ ckpt_name="sd_xl_base_1.0.safetensors" } }
    "5" = @{ class_type="EmptyLatentImage"; inputs=@{ width=$is.genislik; height=$is.yukseklik; batch_size=$is.adet } }
    "6" = @{ class_type="CLIPTextEncode"; inputs=@{ clip=@("4",1); text=$is.istem } }
    "7" = @{ class_type="CLIPTextEncode"; inputs=@{ clip=@("4",1); text=$is.negatif } }
    "3" = @{ class_type="KSampler"; inputs=@{ seed=(Get-Random -Maximum 2147483647); steps=$is.adim;
             cfg=$is.cfg; sampler_name="dpmpp_2m"; scheduler="karras"; denoise=1.0;
             model=@("4",0); positive=@("6",0); negative=@("7",0); latent_image=@("5",0) } }
    "8" = @{ class_type="VAEDecode"; inputs=@{ samples=@("3",0); vae=@("4",2) } }
    "9" = @{ class_type="SaveImage"; inputs=@{ filename_prefix=$is.id; images=@("8",0) } }
  }
  $govde = @{ prompt = $akis } | ConvertTo-Json -Depth 8 -Compress
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:$CmfPort/prompt" -Method Post `
       -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($govde)) -TimeoutSec 30
  for ($i=1; $i -le 60; $i++) {
    Start-Sleep 5
    try {
      $h = Invoke-RestMethod "http://127.0.0.1:$CmfPort/history/$($r.prompt_id)" -TimeoutSec 8
      if ($h.PSObject.Properties.Name -contains $r.prompt_id) { return $true }
    } catch {}
  }
  return $false
}

$kip = "LLM"
$llmTunel = -1
$cmfTunel = -1
$gorselBas = $null
Say "hakem acildi (PC-2 RTX 5060)"

while ($true) {

  if ($kip -eq "LLM") {
    $sayi = Uzak ("ls -1 " + $K + "/bekleyen/*.json 2>/dev/null | wc -l")
    $bekleyen = 0
    if ($sayi -match "^\d+$") { $bekleyen = [int]$sayi }
    if ($bekleyen -gt 0) {
      Say ("kuyrukta " + $bekleyen + " is -> GORSEL kipine geciliyor")
      TunelKapat $llmTunel
      $llmTunel = -1
      SureciKapat "llama-server.exe" "*Qwen3*"
      Say "llama-server durduruldu"
      Start-Sleep 4
      if (ComfyBaslat) {
        $kip = "GORSEL"
        $gorselBas = Get-Date
        $cmfTunel = TunelKur $CmfUzak $CmfPort
      } else {
        ComfyDurdur
        Say "ComfyUI acilmadi -> LLM kipinde kaliniyor"
      }
    }
  }

  if ($kip -eq "GORSEL") {
    $isYol = Uzak ("ls -1 " + $K + "/bekleyen/*.json 2>/dev/null | head -1")
    if ($isYol) {
      $ad = Split-Path $isYol -Leaf
      Uzak ("mv " + $isYol + " " + $K + "/calisan/" + $ad) | Out-Null
      $json = Uzak ("cat " + $K + "/calisan/" + $ad)
      Say ("is basladi: " + $ad)
      $ok = $false
      $is = $null
      try {
        $is = $json | ConvertFrom-Json
        $ok = IsIsle $is
      } catch {
        Say ("is HATASI " + $ad + " : " + $_.Exception.Message)
      }
      if ($ok) {
        $uretilen = @(Get-ChildItem $CmfCikti -File -Filter ($is.id + "*") -EA SilentlyContinue)
        foreach ($g in $uretilen) {
          & scp @Ssh $g.FullName ($Sunucu + ":" + $K + "/cikti/") 2>$null | Out-Null
        }
        Uzak ("mv " + $K + "/calisan/" + $ad + " " + $K + "/biten/" + $ad) | Out-Null
        Say ("is bitti: " + $ad + " (" + $uretilen.Count + " gorsel)")
      } else {
        Uzak ("mv " + $K + "/calisan/" + $ad + " " + $K + "/hata/" + $ad) | Out-Null
        Say ("is BASARISIZ: " + $ad)
      }
    } else {
      Say "kuyruk bosaldi -> LLM kipine donuluyor"
      TunelKapat $cmfTunel
      $cmfTunel = -1
      ComfyDurdur
      Start-Sleep 4
      $kip = "LLM"
    }
    if ($gorselBas -and ((Get-Date) - $gorselBas).TotalMinutes -gt $EnUzunGorselDk) {
      Say ("GORSEL kipi " + $EnUzunGorselDk + " dk tavanina ulasti -> LLM'e donuluyor")
      TunelKapat $cmfTunel
      $cmfTunel = -1
      ComfyDurdur
      Start-Sleep 4
      $kip = "LLM"
    }
  }

  if ($kip -eq "LLM") {
    if (-not (Saglikli $LlmPort)) {
      SureciKapat "llama-server.exe" "*Qwen3*"
      Start-Sleep 2
      LlmBaslat
      Start-Sleep 12
    }
    $canli = ($llmTunel -gt 0) -and (Get-Process -Id $llmTunel -EA SilentlyContinue)
    if ((Saglikli $LlmPort) -and -not $canli) { $llmTunel = TunelKur $LlmUzak $LlmPort }
  }

  Start-Sleep 20
}
