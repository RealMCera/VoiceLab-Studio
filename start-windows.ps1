$ErrorActionPreference = "Stop"
Write-Host "VoiceLab Studio setup" -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.11+ is required." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning "FFmpeg is not in PATH. Audio processing tools will fail until FFmpeg is installed." }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$api = Join-Path $root "apps\api"
if (-not (Test-Path "$api\.venv")) { python -m venv "$api\.venv" }
& "$api\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$api\.venv\Scripts\python.exe" -m pip install -r "$api\requirements.txt"
if (-not (Test-Path "$api\.env")) { Copy-Item "$api\.env.example" "$api\.env"; Write-Host "Created apps\api\.env — add API keys there for AI generation." -ForegroundColor Yellow }

Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$api'; .\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"
Start-Sleep -Seconds 2
Start-Process "http://localhost:8000"
