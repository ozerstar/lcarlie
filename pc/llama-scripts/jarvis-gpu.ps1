# Keep the GPU model and its tunnel up, and let them disappear cleanly.
#
# Jarvis asks two loopback ports on the server, in this order:
#
#   127.0.0.1:8098  ->  this PC, RX 6600, ~6 s for a knowledge-backed answer
#   127.0.0.1:8099  ->  the server's own CPU model, ~60 s for the same answer
#
# 8098 only exists while this script is running, because it is the far end of
# the reverse tunnel below. So switching this PC off is not an outage: the
# health check fails, the router drops to the server's model, and answers keep
# coming -- slower. That is the whole design. Nothing here needs to handle
# shutdown gracefully.
#
# Loopback on both sides. The tunnel binds the server's 127.0.0.1 only
# (GatewayPorts is off), so the model is not reachable from the internet, and
# llama-server binds this machine's 127.0.0.1 only.

$ErrorActionPreference = 'Continue'

$Root      = 'D:\lcarlie-llama'
$Exe       = Join-Path $Root 'bin\llama-server.exe'
$Model     = Join-Path $Root 'models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
$Log       = Join-Path $Root 'guard.log'
$LocalPort = 8099   # on this PC
$RemotePort= 8098   # on the server, loopback only

function Say($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Model-Healthy {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$LocalPort/health" `
                               -TimeoutSec 4 -ErrorAction Stop
        return $r.status -eq 'ok'
    } catch { return $false }
}

function Start-Model {
    # --no-warmup: loading is ~6 s and the first real request warms it anyway.
    # -ngl 99 puts every layer on the GPU; the 4B Q4 is 2.4 GB against 8 GB.
    $a = @('-m', $Model, '--host', '127.0.0.1', '--port', $LocalPort,
           '-c', '8192', '-ngl', '99', '--no-warmup')
    Start-Process -FilePath $Exe -ArgumentList $a -WindowStyle Hidden `
                  -RedirectStandardOutput (Join-Path $Root 'server.log') `
                  -RedirectStandardError  (Join-Path $Root 'server.err')
    Say "llama-server started"
}

function Tunnel-Alive {
    # The ssh child we started, not any ssh the operator happens to be running.
    return $null -ne (Get-Process -Id $script:TunnelPid -ErrorAction SilentlyContinue)
}

function Start-Tunnel {
    # ExitOnForwardFailure: if 8098 is still held by a stale session, fail now
    # and retry on the next pass rather than sit there forwarding nothing.
    # The server reaps stale sessions after ~90 s (ClientAliveInterval 30).
    $a = @('-N', '-R', "${RemotePort}:127.0.0.1:${LocalPort}",
           '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
           '-o', 'ExitOnForwardFailure=yes', '-o', 'BatchMode=yes',
           'lcarlie')
    $p = Start-Process -FilePath 'ssh' -ArgumentList $a -WindowStyle Hidden -PassThru
    $script:TunnelPid = $p.Id
    Say "tunnel started (pid $($p.Id))"
}

$script:TunnelPid = -1
Say "guard up"

while ($true) {
    if (-not (Model-Healthy)) {
        # Kill a hung instance before starting another, or the port is taken
        # and the new one dies silently.
        Get-Process llama-server -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Start-Model
        Start-Sleep -Seconds 8
    }
    if ((Model-Healthy) -and -not (Tunnel-Alive)) {
        Start-Tunnel
    }
    Start-Sleep -Seconds 20
}
