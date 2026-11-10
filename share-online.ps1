# Starts ZU Advisor and a free temporary public link (Cloudflare quick tunnel).
# The link works only while this window stays open and the PC is on.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$cloudflared = Join-Path $env:USERPROFILE 'cloudflare\cloudflared.exe'
if (-not (Test-Path $cloudflared)) {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { $cloudflared = $cmd.Source } else {
        Write-Host "cloudflared.exe not found. Download it from https://github.com/cloudflare/cloudflared/releases" -ForegroundColor Red
        Read-Host 'Press Enter to close'; exit 1
    }
}

# 1) Start the site unless it is already running
$running = $false
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://localhost:5178/ | Out-Null; $running = $true } catch {}
$server = $null
if (-not $running) {
    Write-Host 'Starting the ZU Advisor site...'
    $server = Start-Process -PassThru -WindowStyle Minimized -FilePath '.venv\Scripts\python.exe' -ArgumentList 'server.py'
    Start-Sleep -Seconds 3
}

# 2) Start the tunnel and wait for its public address
$log = Join-Path $env:TEMP 'zu-advisor-tunnel.log'
if (Test-Path $log) { Remove-Item $log -Force }
Write-Host 'Creating your public link (takes a few seconds)...'
$tunnel = Start-Process -PassThru -WindowStyle Hidden -FilePath $cloudflared `
    -ArgumentList @('tunnel', '--no-autoupdate', '--url', 'http://localhost:5178', '--logfile', $log)

$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}

if ($url) {
    Set-Clipboard -Value $url
    Write-Host ''
    Write-Host '  ZU Advisor is online at:' -ForegroundColor Green
    Write-Host "  $url" -ForegroundColor Yellow
    Write-Host '  (copied to your clipboard - paste it anywhere to share)'
    Write-Host ''
    Write-Host '  Keep this window open. The link stops working when you close it.'
    Start-Process $url
} else {
    Write-Host "Couldn't create the public link. Check your internet connection. Log: $log" -ForegroundColor Red
}

Read-Host 'Press Enter to stop sharing'
if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force }
if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
