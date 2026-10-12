# Cria banco e roles do SigFrotas no PostgreSQL local, lendo os dados do .env.
# Uso (na raiz do projeto): powershell -File scripts\criar_banco.ps1

$ErrorActionPreference = 'Stop'
$c = @{}
Get-Content .env | Where-Object { $_ -match '^\s*[^#=\s]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $c[$k.Trim()] = $v.Trim()
}
foreach ($k in 'PG_ADMIN_PASSWORD', 'DB_OWNER_PASSWORD', 'DB_APP_PASSWORD') {
    if (-not $c[$k]) { throw "Preencha $k no .env" }
}

$psql = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'
$env:PGPASSWORD = $c.PG_ADMIN_PASSWORD
& $psql -h $c.DB_HOST -p $c.DB_PORT -U $c.PG_ADMIN_USER -d postgres -w -v ON_ERROR_STOP=1 `
    -v dev=1 -v "db=$($c.DB_NAME)" `
    -v "owner=$($c.DB_OWNER_USER)" -v "owner_pwd=$($c.DB_OWNER_PASSWORD)" `
    -v "app=$($c.DB_APP_USER)" -v "app_pwd=$($c.DB_APP_PASSWORD)" `
    -f scripts\criar_banco.sql
