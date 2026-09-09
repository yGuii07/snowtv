$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$engineDir = Join-Path $PSScriptRoot "engine"
$venvPython = Join-Path $engineDir ".venv\Scripts\python.exe"
$backend = $null
$frontend = $null

function Require-Command {
  param(
    [string]$Name,
    [string]$Message
  )

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw $Message
  }
}

function Wait-Http {
  param(
    [string]$Url,
    [int]$Seconds = 30
  )

  $deadline = (Get-Date).AddSeconds($Seconds)

  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    }
    catch {
    }

    Start-Sleep -Milliseconds 500
  }

  return $false
}

try {
  Write-Host ""
  Write-Host "SnowTV - inicializacao local" -ForegroundColor Cyan

  Require-Command "ffmpeg" "FFmpeg nao foi encontrado no PATH. Instale o FFmpeg e abra um novo PowerShell."
  Require-Command "ffprobe" "ffprobe nao foi encontrado no PATH. Instale o FFmpeg e abra um novo PowerShell."
  Require-Command "node" "Node.js nao foi encontrado no PATH. Instale Node 22.13 ou superior."
  Require-Command "npm.cmd" "npm nao foi encontrado no PATH. Reinstale o Node.js com npm."

  $nodeMajor = [int]((& node -p "process.versions.node.split('.')[0]").Trim())

  if ($nodeMajor -lt 22) {
    $nodeVersion = (& node -v)
    throw "Node.js 22 ou superior e necessario. Versao detectada: $nodeVersion"
  }

  if (-not (Test-Path $venvPython)) {
    Write-Host "Backend ainda nao preparado. Executando setup inicial..." -ForegroundColor Yellow

    Push-Location $engineDir
    try {
      & ".\setup-windows.ps1"

      if ($LASTEXITCODE -ne 0) {
        throw "O setup do backend falhou."
      }
    }
    finally {
      Pop-Location
    }
  }

  if (-not (Test-Path (Join-Path $PSScriptRoot "node_modules"))) {
    Write-Host "Dependencias do frontend nao encontradas. Executando npm install..." -ForegroundColor Yellow

    & npm.cmd install

    if ($LASTEXITCODE -ne 0) {
      throw "A instalacao das dependencias do frontend falhou."
    }
  }

  Write-Host "Iniciando Motor Snow em http://127.0.0.1:8000 ..." -ForegroundColor Cyan

  $backend = Start-Process `
    -FilePath $venvPython `
    -ArgumentList @(
      "-m",
      "uvicorn",
      "snow_engine.api:app",
      "--host",
      "0.0.0.0",
      "--port",
      "8000",
      "--workers",
      "1"
    ) `
    -WorkingDirectory $engineDir `
    -PassThru `
    -NoNewWindow

  if (-not (Wait-Http -Url "http://127.0.0.1:8000/health" -Seconds 30)) {
    if ($backend.HasExited) {
      throw "O Motor Snow encerrou durante a inicializacao."
    }

    Write-Warning "O Motor Snow ainda nao respondeu ao /health, mas o processo continua ativo."
  }
  else {
    Write-Host "Motor Snow pronto." -ForegroundColor Green
  }

  Write-Host "Iniciando interface..." -ForegroundColor Cyan

  $frontend = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev") `
    -WorkingDirectory $PSScriptRoot `
    -PassThru `
    -NoNewWindow

  $frontendUrl = "http://localhost:5173"

  if (Wait-Http -Url $frontendUrl -Seconds 45) {
    Write-Host "Interface pronta em $frontendUrl" -ForegroundColor Green
    Start-Process $frontendUrl
  }
  else {
    Write-Warning "A interface ainda nao respondeu em $frontendUrl. Confira a saida acima."
  }

  Write-Host ""
  Write-Host "SnowTV esta rodando. Pressione Ctrl+C para encerrar." -ForegroundColor Green

  while ($true) {
    if ($backend.HasExited) {
      throw "O Motor Snow foi encerrado inesperadamente."
    }

    if ($frontend.HasExited) {
      throw "O frontend foi encerrado inesperadamente."
    }

    Start-Sleep -Seconds 1
  }
}
finally {
  Write-Host ""
  Write-Host "Encerrando SnowTV..." -ForegroundColor Yellow

  foreach ($proc in @($frontend, $backend)) {
    if ($proc -and -not $proc.HasExited) {
      try {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
      }
      catch {
      }
    }
  }
}
