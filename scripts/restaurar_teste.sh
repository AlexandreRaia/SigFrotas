#!/bin/sh
# TESTE DE RESTAURACAO: restaura o backup mais recente (ou o arquivo informado) num banco temporario,
# confere se os dados e a seguranca (RLS) vieram e apaga o banco temporario. Nao toca no banco de verdade.
#   docker compose run --rm backup /scripts/restaurar_teste.sh [arquivo]
# Variaveis: as mesmas do backup.sh (PGHOST PGPORT PGUSER PGPASSWORD DB_NAME BACKUP_DIR BACKUP_PASSPHRASE)
set -eu
umask 077

DESTINO="${BACKUP_DIR:-/backups}"
TESTE="${DB_NAME}_restauracao_teste"
ARQ="${1:-$(ls -1t "$DESTINO"/${DB_NAME}_*.dump* 2>/dev/null | head -n 1)}"
[ -n "$ARQ" ] && [ -f "$ARQ" ] || { echo "ERRO: nenhum backup encontrado em $DESTINO" >&2; exit 1; }
echo "Restaurando: $ARQ"

TMP="$(mktemp)"
limpar() { rm -f "$TMP"; psql -d postgres -qAt -c "DROP DATABASE IF EXISTS \"$TESTE\"" > /dev/null 2>&1 || true; }
trap limpar EXIT

case "$ARQ" in
  *.enc) openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$ARQ" -out "$TMP" ;;
  *) cp "$ARQ" "$TMP" ;;
esac

psql -d postgres -qAt -c "DROP DATABASE IF EXISTS \"$TESTE\"" -c "CREATE DATABASE \"$TESTE\""
# --no-owner/--no-acl: o teste confere os dados; as roles de producao nao precisam existir aqui.
pg_restore --no-owner --no-acl --exit-on-error -d "$TESTE" "$TMP"

consulta() { psql -d "$1" -qAt -c "$2"; }
FALHOU=0
confere() {  # descricao, consulta, minimo
  VALOR="$(consulta "$TESTE" "$2")"
  if [ "$VALOR" -ge "$3" ] 2>/dev/null; then echo "  ok   $1: $VALOR"; else echo "  FALHA $1: '$VALOR' (esperado >= $3)"; FALHOU=1; fi
}

echo "Conferindo o banco restaurado:"
confere "migracoes aplicadas" "SELECT count(*) FROM django_migrations" 1
confere "politicas de RLS" "SELECT count(*) FROM pg_policies WHERE policyname = 'tenant_isolation'" 1
confere "tabelas com RLS ligada" "SELECT count(*) FROM pg_class WHERE relrowsecurity" 1
confere "prefeituras" "SELECT count(*) FROM municipios" 0

echo "Comparando com o banco atual (pode diferir se houve uso depois do backup):"
for TABELA in municipios usuarios auditoria; do
  echo "  $TABELA: restaurado=$(consulta "$TESTE" "SELECT count(*) FROM $TABELA") atual=$(consulta "$DB_NAME" "SELECT count(*) FROM $TABELA")"
done

if [ "$FALHOU" -eq 0 ]; then echo "RESTAURACAO OK"; else echo "RESTAURACAO COM FALHAS" >&2; exit 1; fi
