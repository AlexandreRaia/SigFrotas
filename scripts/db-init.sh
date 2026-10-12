#!/bin/sh
# Roda uma unica vez, na criacao do volume do banco (imagem oficial do PostgreSQL):
# cria as roles (dona e aplicacao) e as extensoes. O banco "sigfrotas" e criado pelo proprio script SQL.
set -eu

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -v dev=0 \
  -v "db=$DB_NAME" \
  -v "owner=$DB_OWNER_USER" -v "owner_pwd=$DB_OWNER_PASSWORD" \
  -v "app=$DB_APP_USER" -v "app_pwd=$DB_APP_PASSWORD" \
  -f /scripts/criar_banco.sql
