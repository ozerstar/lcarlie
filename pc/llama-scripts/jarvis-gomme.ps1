# PC-1 (RX 6600) - Jarvis GOMME gozetmeni.
#
# ROL DEGISIKLIGI (24.09.2026): bu makine artik LLM calistirmiyor.
# Sebep sahibin kurali: "dusuk segmente calisan modeller kaliteyi bozuyor".
# Qwen3-4B'nin urettigi metin kalite riskiydi ve olculmustu (ayni soruya 33
# farkli cevap). LLM rolu PC-2'ye (RTX 5060, Qwen3-8B, 65 t/s) gecti.
#
# Bu makinenin yeni isi GOMME. Gomme bir kalite kademesi sorusu DEGIL:
# BGE-M3 568M parametreli ama bu, gomme modellerinin kategorisidir, taviz
# degil. Cikitisi musteriye gitmez, sayiya cevrilir.
#
# KAZANC: gomme artik Google'a gitmiyor. Onceden her hafiza yazimi ve
# aramasi sirket metnini gemini-embedding-001'e gonderiyordu.
# BGE-M3'un dogal boyutu 1024 -- ai_semantic.memory_embedding ile birebir,
# sema degismiyor. Tablo 0 satir oldugu icin gecis maliyeti de yok.
#
# ACILISTA SYSTEM olarak calisir. SYSTEM'in %USERPROFILE% degeri farklidir,
# bu yuzden anahtar ve known_hosts profil disinda, sabit yolda tutulur ve
# butun ssh secenekleri ACIKCA verilir. ~/.ssh/config OKUNMAZ.
#
# Sunucuda 127.0.0.1:8096  ->  bu PC 127.0.0.1:8100

$ErrorActionPreference = "Continue"
$Root       = "D:\lcarlie-llama"
$Exe        = Join-Path $Root "bin\llama-server.exe"
$Model      = Join-Path $Root "models\bge-m3-FP16.gguf"
$Log        = Join-Path $Root "gomme.log"
# ğŸ”´ D: exFAT -- dosya izni TUTMAZ, icacls sessizce hicbir sey yapmaz ve
# OpenSSH anahtari "bad permissions" diye reddeder (olculdu 24.09.2026).
# Anahtar bu yuzden NTFS olan C:'de. Model D:'de kalabilir, onun izni
# onemli degil.
$Key        = "C:\lcarlie-llama\ssh\id_ed25519"
$Known      = "C:\lcarlie-llama\ssh\known_hosts"
$LocalPort  = 8100
$LlmYerel   = 8098
$LlmUzak    = 8098
$RemotePort = 8096
$Sunucu     = "root@185.169.180.68"

function Say($m) {
    try { Add-Content -Path $Log -Encoding UTF8 -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) } catch {}
}

if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 1MB) {
    Move-Item $Log "$Log.1" -Force -EA SilentlyContinue
}

function Model-Healthy {
    try { return (Invoke-RestMethod "http://127.0.0.1:$LocalPort/health" -TimeoutSec 4 -EA Stop).status -eq "ok" }
    catch { return $false }
}

function Start-Model {
    # --pooling cls: BGE-M3'un kendi havuzlama yontemi. Yanlis havuzlama
    # sessizce CALISIR ama vektorler anlamsiz olur -- en sinsi hata turu.
    # --embd-normalize 2: L2. pgvector kosinus benzerligi bunu bekler.
    $a = @("-m",$Model,"--host","127.0.0.1","--port",$LocalPort,
           "--embedding","--pooling","cls","--embd-normalize","2",
           "-c","8192","-ngl","99","--no-warmup")
    Start-Process -FilePath $Exe -ArgumentList $a -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Root "gomme-server.log") `
        -RedirectStandardError  (Join-Path $Root "gomme-server.err")
    Say "bge-m3 started (embedding, cls, L2)"
}

function Tunnel-Alive {
    # Once bizim baslattigimiz surece bak.
    if ($script:TunnelPid -gt 0 -and (Get-Process -Id $script:TunnelPid -EA SilentlyContinue)) { return $true }

    # 🔴 GOZETMEN YENIDEN BASLARSA PID KAYBOLUR AMA TUNEL YASAR.
    # Start-Process ile acilan ssh, ebeveyni olunce OLMEZ. Gozetmen
    # yeniden baslayinca $TunnelPid = -1 olur, "tunel yok" sanip yenisini
    # acar, port DOLU oldugu icin o da olur -- ve bu her dongude tekrarlar.
    # Olculdu 24-25.09.2026: gorev yeniden baslatildiktan sonra 17 saat
    # boyunca 23 saniyede bir deneme, sunucu gunlugune 2.686 satir
    # "bind [127.0.0.1]:8096: Address already in use". Gomme CALISIYORDU
    # (eski tunel saglamdi), yani hicbir sey bozulmus gorunmuyordu.
    # Cozum: PID kayipsa, komut satirindan KENDI tunelimizi tani ve sahiplen.
    $mevcut = Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -EA SilentlyContinue |
              Where-Object { $_.CommandLine -like "*-R ${RemotePort}:127.0.0.1:${LocalPort}*" } |
              Select-Object -First 1
    if ($mevcut) {
        $script:TunnelPid = $mevcut.ProcessId
        Say "mevcut tunel sahiplenildi (pid $($mevcut.ProcessId)) - yeniden acilmadi"
        return $true
    }
    return $false
}

function Start-Tunnel {
    # 🔴 IKINCI YONLENDIRME: PC-1'in LLM'i (yerel 8098 -> sunucu 8098).
    # Tuneli BU betik kuruyor cunku SSH anahtari yalniz SYSTEM'e okunur.
    # LLM'in KENDISI kullanici oturumunda kosuyor (jarvis-llm.ps1) cunku
    # SYSTEM baglaminda AMD Vulkan karti gorulmuyor (olculdu: %4'e karsi
    # %95,9 GPU). Tunel, dinleyicinin kim oldugunu umursamaz -- bu yuzden
    # ikinci bir SSH anahtari URETILMEDI.
    $a = @("-N","-R","${RemotePort}:127.0.0.1:${LocalPort}",
                "-R","${LlmUzak}:127.0.0.1:${LlmYerel}",
           "-i",$Key,"-o","IdentitiesOnly=yes",
           "-o","UserKnownHostsFile=$Known","-o","StrictHostKeyChecking=yes",
           "-o","ServerAliveInterval=30","-o","ServerAliveCountMax=3",
           "-o","ExitOnForwardFailure=yes","-o","BatchMode=yes",
           $Sunucu)
    # ssh hatasi SESSIZ olmamali: SYSTEM olarak calisirken anahtar izni,
    # PATH ve known_hosts sorunlari ancak boyle gorulur. "tunnel started"
    # yazip olen bir surec, calisiyor gibi gorunur -- en sinsi hata turu.
    $p = Start-Process -FilePath "ssh" -ArgumentList $a -WindowStyle Hidden -PassThru `
         -RedirectStandardError (Join-Path $Root "tunnel.err")
    $script:TunnelPid = $p.Id
    Start-Sleep 3
    if ($p.HasExited) {
        $hata = ""
        try { $hata = (Get-Content (Join-Path $Root "tunnel.err") -Raw -EA Stop).Trim() } catch {}
        Say ("tunnel OLDU (cikis {0}): {1}" -f $p.ExitCode, ($hata -replace "\r?\n", " | "))
    } else {
        Say "tunnel started (pid $($p.Id))"
    }
}

$script:TunnelPid = -1
Say "gomme gozetmeni acildi (PC-1 RX 6600)"

# --- kaynak olcumu (SISTEM sekmesi) ---------------------------------
# PC-1'de "Jarvis Metrik" adli ayri bir zamanlanmis gorev KURULAMADI:
# SYSTEM olarak kosan bir gorev kaydetmek yonetici yetkisi ister ve
# sunucuya itme yapan SSH anahtari (dogru olarak) yalniz SYSTEM'e
# okunur. Bu gozetmen zaten SYSTEM olarak kosuyor, olcum buraya
# ilistirildi.
#
# 🔴 Olcum HICBIR kosulda gozetmeni dusuremez: tamami try/catch icinde
# ve ayri bir surec olarak baslatiliyor. Gomme hattinin ayakta kalmasi
# metrikten onemlidir; metrik susarsa panel bunu "BAYAT" diye yazar,
# sessizce yanlis sayi gostermez.
$script:SonMetrik = [datetime]::MinValue
function Push-Metrik {
    try {
        if (((Get-Date) - $script:SonMetrik).TotalSeconds -lt 60) { return }
        $script:SonMetrik = Get-Date
        $b = "C:\lcarlie-llama\jarvis-metrik.ps1"
        if (-not (Test-Path $b)) { return }
        Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
            -ArgumentList @("-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$b) `
            -EA SilentlyContinue | Out-Null
    } catch { }
}

while ($true) {
    Push-Metrik
    if (-not (Model-Healthy)) {
        Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" |
            Where-Object { $_.CommandLine -like "*bge-m3*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
        Start-Sleep 2; Start-Model; Start-Sleep 10
    }
    if ((Model-Healthy) -and -not (Tunnel-Alive)) { Start-Tunnel }
    Start-Sleep 20
}


