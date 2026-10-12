# Gera o CSS do site (static/css/app.css) com o Tailwind CLI independente (nao precisa de Node).
# Uso, na raiz do projeto:
#   powershell -File scripts\css.ps1          # gera uma vez
#   powershell -File scripts\css.ps1 -Watch   # regera ao salvar os templates (deixe aberto enquanto desenvolve)
param([switch]$Watch)

$ErrorActionPreference = 'Stop'
$versao = 'v3.4.17'
$exe = 'tools\tailwindcss.exe'
if (-not (Test-Path $exe)) {
    New-Item -ItemType Directory -Force tools | Out-Null
    Invoke-WebRequest "https://github.com/tailwindlabs/tailwindcss/releases/download/$versao/tailwindcss-windows-x64.exe" -OutFile $exe -UseBasicParsing
}
$argumentos = @('-i', 'static\src\input.css', '-o', 'static\css\app.css', '--minify')
if ($Watch) { $argumentos += '--watch' }
& $exe @argumentos
