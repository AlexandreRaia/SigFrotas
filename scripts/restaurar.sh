#!/bin/sh
# RESTAURACAO REAL (desastre): APAGA o banco atual e o recria a partir de um backup.
#   docker compose stop web caddy
#   docker compose run --rm backup /scripts/restaurar.sh --confirmo /backups/ARQUIVO_DO_BANCO [/backups/ARQUIVO_DOS_ANEXOS]
#   docker compose start web caddy
# Antes, faca o TESTE de restauracao (scripts/restaurar_teste.sh) para ter certeza de que o arquivo esta bom.
# Variaveis: PGHOST PGPORT PGUSER PGPASSWORD DB_NAME DB_OWNER_USER DB_APP_USER BACKUP_PASSPHRASE MEDIA_DIR (/media)
set -eu
umask 077

if [ "${1:-}" != "--confirmo" ] || [ -z "${2:-}" ]; then
  echo "Isto APAGA o banco $DB_NAME e o recria do backup." >&2
  echo "Uso: restaurar.sh --confirmo ARQUIVO_DO_BANCO [ARQUIVO_DOS_ANEXOS]" >&2
  exit 1
fi
ARQ="$2"
ANEXOS="${3:-}"
MEDIA="${MEDIA_DIR:-/media}"
[ -f "$ARQ" ] || { echo "ERRO: arquivo nao encontrado: $ARQ" >&2; exit 1; }

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
abrir() {  # arquivo, destino: descriptografa se terminar em .enc
  case "$1" in
    *.enc) openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$1" -out "$2" ;;
    *) cp "$1" "$2" ;;
  esac
}

abrir "$ARQ" "$TMP"
pg_restore --list "$TMP" > /dev/null   # so segue se o arquivo estiver integro

psql -d postgres -qAt -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid()" > /dev/null \
  -c "DROP DATABASE IF EXISTS \"$DB_NAME\"" \
  -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_OWNER_USER\" ENCODING 'UTF8' TEMPLATE template0" \
  -c "REVOKE ALL ON DATABASE \"$DB_NAME\" FROM PUBLIC" \
  -c "GRANT CONNECT ON DATABASE \"$DB_NAME\" TO \"$DB_APP_USER\""
# Como superusuario: mantem donos e permissoes (inclui a RLS) e recria as extensoes.
pg_restore --exit-on-error -d "$DB_NAME" "$TMP"
echo "Banco restaurado: $(psql -d "$DB_NAME" -qAt -c 'SELECT count(*) FROM municipios') prefeitura(s)."

if [ -n "$ANEXOS" ]; then
  [ -f "$ANEXOS" ] || { echo "ERRO: arquivo de anexos nao encontrado: $ANEXOS" >&2; exit 1; }
  abrir "$ANEXOS" "$TMP"
  mkdir -p "$MEDIA"
  tar -xzf "$TMP" -C "$MEDIA"
  echo "Anexos restaurados em $MEDIA."
fi
echo "Restauracao concluida."
