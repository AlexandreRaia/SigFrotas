# SigFrotas

Sistema de gestão de frotas para prefeituras (multi-prefeitura). Documentação em `docs/`; regras de trabalho em `CLAUDE.md`.

## Subir o ambiente de desenvolvimento

Requisitos: Python 3.12, PostgreSQL 14+ local, Git.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # preencha as senhas e DJANGO_SECRET_KEY
powershell -File scripts\criar_banco.ps1      # cria o banco e as duas roles
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py criar_municipio --nome "Prefeitura Exemplo" --slug exemplo --uf SP --cnpj 00000000000000
.\.venv\Scripts\python manage.py criar_admin --prefeitura exemplo --nome "Seu Nome" --email voce@exemplo.gov.br
.\.venv\Scripts\python manage.py runserver
```

Defina `MUNICIPIO_PADRAO_SLUG=exemplo` no `.env` para esconder o campo "Prefeitura" no login.

## Testes

```powershell
.\.venv\Scripts\python manage.py test apps
```

## Como o banco é usado

- `migrate` e `test` conectam com a role **dona** das tabelas (`DB_OWNER_*`). Todo o resto (site, comandos) conecta com a role **da aplicação** (`DB_APP_*`), sem `BYPASSRLS` e que não é dona de nada, para a RLS valer.
- A cada requisição o middleware abre uma transação com `app.municipio_id` da sessão. Em comandos e tarefas, use `com_municipio(id)` de `apps/core/tenant.py`.
- Tabela nova com `municipio_id` deve herdar de `ModeloDoMunicipio` e usar `habilitar_rls()` (`apps/core/rls.py`) na migração. Um teste falha se alguma tabela ficar sem RLS.

## Diferenças em relação a `docs/schema_frota_v2.sql`

- Tabelas no schema `public` (a função da RLS é `municipio_atual()`), em vez do schema `frota`.
- `municipios` ganhou `slug` (identifica a prefeitura no login); `centros_custo` ganhou `criado_em`/`atualizado_em`.
- `atualizado_em` é mantido pelo Django (`auto_now`), sem gatilho no banco.
- Auditoria: a role da aplicação só pode inserir; não altera nem apaga registros.
