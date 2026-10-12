-- Cria as roles e o banco do SigFrotas (desenvolvimento local). Pode ser rodado de novo.
-- Variaveis (vindas de scripts/criar_banco.ps1): db, owner, owner_pwd, app, app_pwd
-- Rodar conectado ao banco "postgres" como superusuario.

-- Role dona das tabelas: usada so nas migracoes e nos testes.
-- CREATEDB: o Django cria o banco "test_..." nos testes (so no ambiente de desenvolvimento).
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'owner', :'owner_pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'owner') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'owner', :'owner_pwd') \gexec

-- Role da aplicacao: sem BYPASSRLS e nao e dona de nada, para a RLS valer.
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app', :'app_pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app', :'app_pwd') \gexec

-- So no desenvolvimento: os testes de RLS fazem SET ROLE para a role da aplicacao.
SELECT format('GRANT %I TO %I', :'app', :'owner') \gexec

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
