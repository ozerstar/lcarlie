# PC-1 (RX 6600) — Jarvis yerel LLM gözetmeni.
#
# 🔴 KULLANICI OTURUMUNDA ÇALIŞIR, SYSTEM OLARAK DEĞİL.
# Ölçüldü 25.09.2026: bu makinede SYSTEM bağlamında başlatılan
# llama-server AMD Vulkan kartına ERİŞEMİYOR.
#     kullanıcı oturumunda başlatılan : yük altında GPU %95,9
#     SYSTEM olarak başlatılan        : yük altında GPU %4
# Gömme modeli aylardır bu yüzden sessizce CPU'da koşuyormuş; kimse fark
# etmemiş çünkü servis "çalışıyor" görünüyordu, yalnız yavaştı.
# Bu görevi SYSTEM'e çevirmek, kartı kaybetmek demektir.
#
# TÜNELİ BU BETİK KURMAZ. Sunucuya ters tünel, zaten SYSTEM olarak koşan
# jarvis-gomme.ps1 tarafından kuruluyor (SSH anahtarı yalnız SYSTEM'e
# okunur). Tünel, dinleyicinin kim olduğuna bakmaz — bu yüzden yeni bir
# kimlik bilgisi ÜRETİLMEDİ.
#
# MODEL SEÇİMİ — ölçülmüş (llama-bench + uçtan uca HTTP, 25.09.2026):
#     Qwen3-4B  63,9 t/s   3.501 MB VRAM   kart toplamı 6.267/7.980  ✅
#     Qwen3-8B  31,0 t/s   5.380 MB VRAM   kart toplamı 8.030/7.980  ❌ taşıyor
#     Qwen3-8B bağlam 2048'e indirilince 37,4 t/s — hâlâ 4B'nin yarısı.
# 8B'nin karta sığdığı tek ayar (2048 bağlam) uzun sentez işine yetmez.
# Bu yüzden 4B seçildi; derin iş zaten dış modele gidiyor.

$ErrorActionPreference = "Continue"
$Root       = "D:\lcarlie-llama"
$Exe        = Join-Path $Root "bin\llama-server.exe"
$Model      = Join-Path $Root "models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$Log        = Join-Path $Root "llm.log"
$LocalPort  = 8098
$AsgariHiz  = 25      # token/sn — bunun altı "GPU'ya düşmüş" demektir

function Say($m) {
    try { Add-Content -Path $Log -Encoding UTF8 -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) } catch {}
}
if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 1MB) {
    Move-Item $Log "$Log.1" -Force -EA SilentlyContinue
}

function Model-Ayakta {
    try { return (Invoke-RestMethod "http://127.0.0.1:$LocalPort/health" -TimeoutSec 4 -EA Stop).status -eq "ok" }
    catch { return $false }
}

# 🔴 GERÇEK SAĞLIK KONTROLÜ — HTTP 200 YETMEZ.
# Bugün ölçülen ders: gömme servisi aylarca HTTP 200 döndürdü ve %4 GPU'da
# koştu. "Ayakta" ile "kartta" ayrı şeylerdir. Bu yüzden sağlık ölçütü
# token/sn: model CPU'ya düşerse hız ~10 t/s'ye iner ve yakalanır.
function Hiz-Olc {
    try {
        $govde = '{"messages":[{"role":"user","content":"sadece rakam yaz: 1 2 3 4 5 6 7 8 9 10"}],"max_tokens":48}'
        $t0 = Get-Date
        $r = Invoke-RestMethod "http://127.0.0.1:$LocalPort/v1/chat/completions" `
             -Method Post -Body $govde -ContentType "application/json" -TimeoutSec 60 -EA Stop
        $sn = ((Get-Date) - $t0).TotalSeconds
        if ($sn -le 0) { return -1 }
        return [math]::Round($r.usage.completion_tokens / $sn, 1)
    } catch { return -1 }
}

function Model-Baslat {
    Get-Process llama-server -EA SilentlyContinue |
        Where-Object { $_.Path -eq $Exe } |
        ForEach-Object {
            # Gömme sunucusunu ÖLDÜRME: o da aynı ikiliyi kullanıyor.
            # Yalnız bizim portumuzu dinleyeni durdur.
            $baglanti = Get-NetTCPConnection -OwningProcess $_.Id -State Listen -EA SilentlyContinue
            if ($baglanti -and ($baglanti.LocalPort -contains $LocalPort)) {
                Stop-Process -Id $_.Id -Force -EA SilentlyContinue
            }
        }
    Start-Sleep 2
    $a = @("-m", $Model, "--host", "127.0.0.1", "--port", $LocalPort,
           "-c", "8192", "-ngl", "99", "--no-warmup")
    Start-Process -FilePath $Exe -ArgumentList $a -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Root "llm-server.log") `
        -RedirectStandardError  (Join-Path $Root "llm-server.err")
    Say "llama-server baslatildi (Qwen3-4B, Vulkan)"
}

Say "llm gozetmeni acildi (PC-1 RX 6600, kullanici oturumu)"

$sonHizKontrol = [datetime]::MinValue
while ($true) {
    if (-not (Model-Ayakta)) {
        Say "model cevap vermiyor -> yeniden baslatiliyor"
        Model-Baslat
        Start-Sleep 25
    }
    elseif (((Get-Date) - $sonHizKontrol).TotalMinutes -ge 10) {
        # On dakikada bir GERÇEK ölçüm. Ucuz (48 token) ama CPU'ya
        # düşmeyi yakalayan tek sinyal bu.
        $sonHizKontrol = Get-Date
        $hiz = Hiz-Olc
        if ($hiz -lt 0) {
            Say "hiz olculemedi (istek basarisiz)"
        } elseif ($hiz -lt $AsgariHiz) {
            Say "🔴 HIZ DUSUK: $hiz t/sn (asgari $AsgariHiz) -- model muhtemelen CPU'da, yeniden baslatiliyor"
            Model-Baslat
            Start-Sleep 25
        } else {
            Say "saglik: $hiz t/sn"
        }
    }
    Start-Sleep 20
}
