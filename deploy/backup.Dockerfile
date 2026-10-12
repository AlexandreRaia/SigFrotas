# Cliente do PostgreSQL (pg_dump, pg_restore, psql) + openssl, para o backup criptografado.
FROM postgres:16
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
