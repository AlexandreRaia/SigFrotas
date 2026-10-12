# SigFrotas

Sistema de gestão de frotas para prefeituras (multi-prefeitura). Documentação em `docs/`; regras de trabalho em `CLAUDE.md`.

## Subir o ambiente de desenvolvimento

Requisitos: Python 3.12, PostgreSQL 14+ local, Git.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # preencha as senhas e DJANGO_SECRET_KEY
powershell -File scripts\criar_banco.ps1      # cria o banco e as duas roles
powershell -File scripts\css.ps1              # gera o CSS (static\css\app.css)
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py criar_municipio --nome "Prefeitura Exemplo" --slug exemplo --uf SP --cnpj 00000000000000
.\.venv\Scripts\python manage.py criar_admin --prefeitura exemplo --nome "Seu Nome" --email voce@exemplo.gov.br
.\.venv\Scripts\python manage.py runserver
```

- Defina `MUNICIPIO_PADRAO_SLUG=exemplo` no `.env` para esconder o campo "Prefeitura" no login.
- Ao mexer nos templates, deixe `powershell -File scripts\css.ps1 -Watch` aberto: ele regera o CSS ao salvar.

## Módulos

| App | Conteúdo | Especificação |
|---|---|---|
| `core` | prefeituras, usuários, perfis, estrutura, auditoria, anexos | `docs/fase0_fundacao.md` |
| `financeiro` | fornecedores, contratos, fiscais, empenhos e saldo | `docs/fase1_cadastros.md` |
| `frota` | veículos, categorias, marcas e modelos, leituras, lotações | `docs/fase1_cadastros.md` |
| `pessoas` | motoristas (dados pessoais protegidos e auditados) | `docs/fase1_cadastros.md` |
| `manutencao` | chamados, SMV, orçamento, aprovação com reserva do empenho, nota fiscal, chat, portal da oficina | `docs/fase2_manutencao.md` |
| `importacao` | carga inicial de veículos e motoristas por planilha CSV | `docs/fase1_cadastros.md` |

Depois de atualizar o código, rode `migrate` e `atualizar_perfis` (acrescenta aos perfis as permissões dos módulos novos; na VPS o `entrypoint.sh` faz isso sozinho). Regras de escopo (quem vê o quê) em `apps/core/escopo.py`; saldo de empenho só pelo `apps/financeiro/services.py`; km só pelo `apps/frota/services.py`; mudanças de estado da manutenção só pelo `apps/manutencao/services.py`; avisos só por `notificar()` (`apps/core/services.py`). Os e-mails saem com `manage.py enviar_notificacoes` (em desenvolvimento aparecem no terminal; no servidor o serviço `notificacoes` do compose roda a cada minuto).

## Testes

```powershell
.\.venv\Scripts\python manage.py test apps
```

## Implantação, backup e restauração

Em `docs/operacao.md`: Docker Compose na VPS (site, PostgreSQL e HTTPS automático), backup diário criptografado, teste de restauração e restauração real.

## Como o banco é usado

- `migrate` e `test` conectam com a role **dona** das tabelas (`DB_OWNER_*`). Todo o resto (site, comandos) conecta com a role **da aplicação** (`DB_APP_*`), sem `BYPASSRLS` e que não é dona de nada, para a RLS valer.
- A cada requisição o middleware abre uma transação com `app.municipio_id` da sessão. Em comandos e tarefas, use `com_municipio(id)` de `apps/core/tenant.py`.
- Tabela nova com `municipio_id` deve herdar de `ModeloDoMunicipio` e usar `habilitar_rls()` (`apps/core/rls.py`) na migração. Um teste falha se alguma tabela ficar sem RLS.

## Telas com HTMX

O servidor devolve só o trecho que mudou nas requisições HTMX (`apps/core/htmx.py`): listas e filtros trocam a tabela, inativar troca a linha, formulários mostram erros no lugar. Sem JavaScript tudo continua funcionando com recarga normal. Para uma tela nova: `ParcialMixin` + um template parcial.

## Diferenças em relação a `docs/schema_frota_v2.sql`

- Tabelas no schema `public` (a função da RLS é `municipio_atual()`), em vez do schema `frota`.
- `municipios` ganhou `slug` (identifica a prefeitura no login); `centros_custo` ganhou `criado_em`/`atualizado_em`.
- `unidades` e `centros_custo` não têm `codigo_externo` (ver `docs/decisoes.md`).
- `atualizado_em` é mantido pelo Django (`auto_now`), sem gatilho no banco.
- Auditoria: a role da aplicação só pode inserir; não altera nem apaga registros.
