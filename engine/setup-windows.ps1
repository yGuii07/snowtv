$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-SnowPython {
  param([string]$Command, [string[]]$PrefixArgs)
  try {
    $arguments = @($PrefixArgs) + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    $version = (& $Command @arguments 2>$null | Select-Object -Last 1).Trim()
    return $version -in @("3.11", "3.12")
  } catch {
    return $false
  }
}

function Invoke-Checked {
  param([string]$Command, [string[]]$Arguments, [string]$FailureMessage)
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw $FailureMessage
  }
}

Write-Host "`nSnowTV - preparação do Motor Snow" -ForegroundColor Cyan

foreach ($dependency in @("ffmpeg", "ffprobe")) {
  if (-not (Get-Command $dependency -ErrorAction SilentlyContinue)) {
    throw "$dependency não foi encontrado no PATH. Instale o FFmpeg e abra um novo PowerShell antes de continuar."
  }
}

$pythonCandidates = @(
  @{ Command = "py"; Args = @("-3.12") },
  @{ Command = "py"; Args = @("-3.11") },
  @{ Command = "python"; Args = @() },
  @{ Command = "python3"; Args = @() }
)
$selected = $null
foreach ($candidate in $pythonCandidates) {
  if ((Get-Command $candidate.Command -ErrorAction SilentlyContinue) -and (Test-SnowPython $candidate.Command $candidate.Args)) {
    $selected = $candidate
    break
  }
}
if (-not $selected) {
  throw "Python 3.11 ou 3.12 não foi encontrado. Instale uma dessas versões com suporte a venv e execute este script novamente."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
  try {
    & $venvPython -c "import sys; assert sys.version_info[:2] in [(3,11),(3,12)]" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Python incompatível" }
    Write-Host "Ambiente virtual existente encontrado; ele será atualizado." -ForegroundColor Green
  } catch {
    throw "A pasta .venv existe, mas não contém Python 3.11/3.12 saudável. Renomeie a pasta .venv e execute setup-windows.ps1 novamente."
  }
} else {
  Write-Host "Criando ambiente virtual com $($selected.Command) $($selected.Args -join ' ')..."
  $venvArguments = @($selected.Args) + @("-m", "venv", ".venv")
  Invoke-Checked -Command $selected.Command -Arguments $venvArguments -FailureMessage "Não foi possível criar a .venv. Verifique se o componente venv está instalado."
}

Write-Host "Instalando/atualizando dependências locais..."
Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -FailureMessage "Falha ao atualizar o pip."
Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "-r", "requirements.txt") -FailureMessage "Falha ao instalar requirements.txt."

Write-Host "Validando imports críticos..."
Invoke-Checked -Command $venvPython -Arguments @("-c", "import cv2, fastapi, faster_whisper, yt_dlp; print('OpenCV', cv2.__version__); print('Dependências Python OK')") -FailureMessage "Um pacote crítico não pôde ser importado."
Invoke-Checked -Command $venvPython -Arguments @("-m", "yt_dlp", "--version") -FailureMessage "O yt-dlp não foi instalado corretamente."

if (Get-Command deno -ErrorAction SilentlyContinue) {
  Write-Host "Deno detectado: $((deno --version | Select-Object -First 1))" -ForegroundColor Green
} else {
  Write-Warning "Deno é opcional, mas recomendado para suporte completo do YouTube. Instale com: winget install DenoLand.Deno"
}

Write-Host "`nAmbiente pronto. Para iniciar nas próximas vezes, use:" -ForegroundColor Green
Write-Host "  Na raiz do projeto: .\start-snowtv.ps1" -ForegroundColor Cyan
