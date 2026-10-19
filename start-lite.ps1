param([int]$Port = 8008)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath 'python/.venv/Scripts/python.exe'
$env:UV_CACHE_DIR = Join-Path $projectPath '.cache/uv'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Please install uv first: https://docs.astral.sh/uv/getting-started/installation/'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & uv venv (Join-Path $projectPath 'python/.venv') --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& uv pip install --python $pythonPath -r (Join-Path $projectPath 'python/requirements-lite.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Push-Location (Join-Path $projectPath 'python')
try {
    Write-Host "ValueCell Lite: http://127.0.0.1:$Port"
    & $pythonPath -m uvicorn lite.app:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
