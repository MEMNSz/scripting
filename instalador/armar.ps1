# Arma el instalador de Scripting.
# Necesita, fuera del repositorio, la carpeta de armado con:
#   python\  Python 3.13 embebible con edge-tts y piper-tts (ver README, sección Instalador)
#   exe\     Scripting.exe compilado (dotnet build -c Release -o <armado>\exe en ventana\)
#   herramientas\InnoSetup\ISCC.exe
param([string]$Armado = (Join-Path $PSScriptRoot '..\..\instalador-build'))

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Armado = (Resolve-Path $Armado).Path
$ver = (Get-Content (Join-Path $repo 'VERSION') -Raw).Trim()
$iscc = Join-Path $Armado 'herramientas\InnoSetup\ISCC.exe'

foreach ($p in @("$Armado\python\pythonw.exe", "$Armado\exe\Scripting.exe", $iscc)) {
    if (-not (Test-Path $p)) { throw "Falta $p" }
}

& $iscc "/DAppVer=$ver" "/DRepoDir=$repo" "/DBuildDir=$Armado" (Join-Path $PSScriptRoot 'scripting.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC falló ($LASTEXITCODE)" }
Get-Item (Join-Path $Armado "salida\Scripting-$ver-instalador.exe")
