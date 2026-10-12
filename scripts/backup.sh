#!/bin/sh
# Backup do banco (e dos anexos, se existirem). Roda dentro do servico "backup" do docker-compose:
#   docker compose run --rm backup
# Variaveis: PGHOST PGPORT PGUSER PGPASSWORD DB_NAME BACKUP_DIR (/backups) MEDIA_DIR (/media)
#            RETENCAO_DIAS (14) BACKUP_PASSPHRASE (se definida, criptografa com AES-256)
set -eu
umask 077

DESTINO="${BACKUP_DIR:-/backups}"
MEDIA="${MEDIA_DIR:-/media}"
RETENCAO="${RETENCAO_DIAS:-14}"
CARIMBO="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DESTINO"

ARQ="$DESTINO/${DB_NAME}_${CARIMBO}.dump"
pg_dump --format=custom --file="$ARQ" "$DB_NAME"

# Confere que o arquivo e legivel e nao esta vazio antes de confiar nele.
pg_restore --list "$ARQ" > /dev/null
[ -s "$ARQ" ] || { echo "ERRO: backup vazio" >&2; exit 1; }

if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -in "$ARQ" -out "$ARQ.enc"
  rm -f "$ARQ"
  ARQ="$ARQ.enc"
fi
echo "Banco: $ARQ ($(wc -c < "$ARQ") bytes)"

if [ -d "$MEDIA" ] && [ -n "$(ls -A "$MEDIA" 2>/dev/null)" ]; then
  MIDIA="$DESTINO/anexos_${CARIMBO}.tar.gz"
  tar -czf "$MIDIA" -C "$MEDIA" .
  if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
    openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -in "$MIDIA" -out "$MIDIA.enc"
    rm -f "$MIDIA"
    MIDIA="$MIDIA.enc"
  fi
  echo "Anexos: $MIDIA ($(wc -c < "$MIDIA") bytes)"
fi

# Apaga o que passou do prazo de guarda.
find "$DESTINO" -type f \( -name "${DB_NAME}_*" -o -name 'anexos_*' \) -mtime +"$RETENCAO" -delete
echo "Backup concluido."
