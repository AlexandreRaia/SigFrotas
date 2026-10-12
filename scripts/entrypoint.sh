#!/bin/sh
# Antes de subir o site: espera o banco e aplica as migracoes (com a role dona das tabelas).
set -eu

echo "Aguardando o banco em ${DB_HOST}:${DB_PORT:-5432}..."
until python - <<'PY'
import os, socket
socket.create_connection((os.environ["DB_HOST"], int(os.environ.get("DB_PORT", "5432"))), timeout=2).close()
PY
do
  sleep 2
done

python manage.py migrate --noinput
python manage.py atualizar_perfis   # permissoes novas dos perfis (so acrescenta)
exec "$@"
