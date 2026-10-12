-- Cria as roles e o banco do SigFrotas. Pode ser rodado de novo.
-- Usado em desenvolvimento (scripts/criar_banco.ps1) e na implantacao (scripts/db-init.sh).
-- Variaveis: db, owner, owner_pwd, app, app_pwd, dev (1 = desenvolvimento, 0 = producao)
-- Rodar conectado ao banco "postgres" como superusuario.

-- Role dona das tabelas: usada so nas migracoes (e nos testes, em desenvolvimento).
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'owner', :'owner_pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'owner') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'owner', :'owner_pwd') \gexec

-- Role da aplicacao: sem BYPASSRLS e nao e dona de nada, para a RLS valer.
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app', :'app_pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app', :'app_pwd') \gexec

-- So no desenvolvimento: o Django cria o banco "test_..." (CREATEDB) e os testes de RLS fazem
-- SET ROLE para a role da aplicacao.
\if :dev
  SELECT format('ALTER ROLE %I CREATEDB', :'owner') \gexec
  SELECT format('GRANT %I TO %I', :'app', :'owner') \gexec
\endif

-- Banco, com a role dona como proprietaria.
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0', :'db', :'owner')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'app') \gexec

\connect :db

-- Extensoes (exigem superusuario).
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- A aplicacao usa o schema public, mas nao cria nada nele; so le e grava nas tabelas do dono.
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'owner', :'app') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I', :'owner', :'app') \gexec
