$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  throw "O ambiente ainda não foi preparado. Execute .\setup-windows.ps1 uma única vez."
}

foreach ($dependency in @("ffmpeg", "ffprobe")) {
  if (-not (Get-Command $dependency -ErrorAction SilentlyContinue)) {
    throw "$dependency não foi encontrado no PATH."
  }
}

& $venvPython -c "import fastapi, faster_whisper, yt_dlp" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "A .venv está incompleta. Execute .\setup-windows.ps1 para repará-la."
}

if (-not (Get-Command deno -ErrorAction SilentlyContinue)) {
  Write-Warning "Deno não encontrado. O motor continuará e usará fallback quando necessário."
}

try {
  if (-not $env:SNOW_PERFORMANCE_PROFILE -or $env:SNOW_PERFORMANCE_PROFILE -in @("auto", "balanced")) {
    [System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = "BelowNormal"
  }
} catch {
  Write-Verbose "Não foi possível reduzir a prioridade do processo iniciador."
}

Write-Host "Snow Engine em http://127.0.0.1:8000" -ForegroundColor Cyan
& $venvPython -m uvicorn snow_engine.api:app --host 0.0.0.0 --port 8000 --workers 1
