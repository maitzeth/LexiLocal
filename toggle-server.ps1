# LexiLocal - Toggle Server
# Starts the server if not running, stops it if running.

$projectDir = $PSScriptRoot
$serverHost = "http://localhost:8000"

function Test-ServerRunning {
    try {
        $response = Invoke-WebRequest -Uri "$serverHost/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Start-LexiLocalServer {
    Write-Host "[LexiLocal] Starting server..." -ForegroundColor Cyan

    $python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $python)) {
        $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    }

    if (-not $python) {
        Write-Host "[LexiLocal] Python not found. Install Python 3.10+ first." -ForegroundColor Red
        return
    }

    Set-Location $projectDir
    $envFile = Join-Path $projectDir "server.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^\s*([^#][^=]*)=(.*)$") {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                Set-Item -Path "Env:$name" -Value $value
            }
        }
    }

    Start-Process -FilePath $python -ArgumentList "server.py" -WorkingDirectory $projectDir -WindowStyle Hidden
    Write-Host "[LexiLocal] Server starting... wait 2 seconds." -ForegroundColor Cyan
    Start-Sleep -Seconds 2

    if (Test-ServerRunning) {
        Write-Host "[LexiLocal] Server is ONLINE at $serverHost" -ForegroundColor Green
    } else {
        Write-Host "[LexiLocal] Server failed to start. Check logs in server.log" -ForegroundColor Red
    }
}

function Stop-LexiLocalServer {
    Write-Host "[LexiLocal] Stopping server..." -ForegroundColor Yellow

    $pythonProcesses = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*server.py*"
    }

    if ($pythonProcesses) {
        $pythonProcesses | Stop-Process -Force
        Write-Host "[LexiLocal] Server stopped." -ForegroundColor Green
    } else {
        Write-Host "[LexiLocal] No running server found." -ForegroundColor Yellow
    }
}

if (Test-ServerRunning) {
    Stop-LexiLocalServer
} else {
    Start-LexiLocalServer
}

Read-Host "`nPress Enter to close"
