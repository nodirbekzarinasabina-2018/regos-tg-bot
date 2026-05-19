$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$bundledPython = "C:\Users\Regos 5\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $bundledPython)) {
    Write-Host "Bundled Python topilmadi: $bundledPython" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    Copy-Item (Join-Path $projectRoot ".env.example") (Join-Path $projectRoot ".env")
    Write-Host ".env fayli yaratildi. Avval uni to'ldiring, keyin skriptni qayta ishga tushiring." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $venvPython)) {
    & $bundledPython -m venv (Join-Path $projectRoot ".venv")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")
& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000
