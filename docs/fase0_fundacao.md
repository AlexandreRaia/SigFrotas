# Especificação — Fase 0: Fundação

Status: **concluída em 12/10/2026**, pendente da validação do Alexandre e da primeira implantação na VPS (ver "Resultado" no fim).

## 1. Objetivo

Deixar pronta a base sobre a qual todos os módulos serão construídos: projeto Django rodando, prefeitura cadastrada, login com perfis, estrutura organizacional, isolamento entre prefeituras no banco (RLS), auditoria, anexos e implantação.

**Critério de pronto:** testes automáticos provam que a prefeitura A não enxerga nem grava dados da prefeitura B.

## 2. Escopo

| # | Item | Resultado |
|---|---|---|
| 1 | Projeto Django | `config/` + `apps/core/`, PostgreSQL 14+, `.env` fora do Git e `.env.example`, Docker de desenvolvimento |
| 2 | Prefeitura | Tabela `municipios` com `config` (jsonb). Criada por comando de administração, sem tela |
| 3 | Usuários e perfis | Login por e-mail e senha; 8 perfis (ADMIN, GESTOR_FROTA, GESTOR_UNIDADE, SOLICITANTE, MOTORISTA, FISCAL, OFICINA, CONSULTA) com permissões em `perfis.permissoes` |
| 4 | Estrutura organizacional | CRUD de secretarias, unidades e centros de custo |
| 5 | RLS | Políticas `tenant_isolation` em toda tabela com `municipio_id`; middleware que executa `SET app.municipio_id` a cada requisição; usuário do banco da aplicação sem `BYPASSRLS` e que não é dono das tabelas |
| 6 | Auditoria | Registro de inserção, alteração e exclusão (antes/depois) das tabelas de negócio; consulta restrita a ADMIN |
| 7 | Anexos | Upload ligado a qualquer registro (`entidade` + `entidade_id`), em disco local no desenvolvimento e compatível com S3; hash SHA-256 |
| 8 | Implantação | Docker Compose para VPS com HTTPS, backup diário do banco e **procedimento de restauração testado** |

**Fora do escopo:** veículos, motoristas, contratos e qualquer regra de manutenção ou tráfego (Fase 1 em diante); Celery/Redis (entram na Fase 2, quando houver notificações); PWA.

## 3. Tabelas

Do `schema_frota_v2.sql`: `municipios`, `secretarias`, `unidades`, `centros_custo`, `perfis`, `usuarios`, `anexos`, `auditoria`.

- O modelo de usuário do Django será o próprio `usuarios` (`AbstractBaseUser`), com e-mail único por prefeitura.
- `municipios` fica fora da RLS. `marcas`, `modelos` e `combustiveis` são globais e entram na Fase 1.
- Extensões necessárias: `citext` e `btree_gist`.
- O schema evolui só por migrações do Django. A RLS e os gatilhos de `atualizado_em` entram em migração com SQL.

## 4. Telas

1. Login e logout.
2. Início (vazio, com o nome da prefeitura e do usuário).
3. Cadastro de secretarias, unidades e centros de custo (listar, criar, editar, inativar).
4. Cadastro de usuários (criar, editar, definir perfil, inativar, redefinir senha). Apenas ADMIN.
5. Consulta da auditoria, com filtro por tabela, registro e período. Apenas ADMIN.

Interface em templates Django, HTMX e Tailwind, de forma simples.

## 5. Regras

1. Toda consulta é filtrada por `municipio_id`, e a RLS garante isso também no banco.
2. Usuário só acessa o que o perfil permite; ADMIN gerencia usuários e a estrutura.
3. Chaves estrangeiras entre registros de prefeituras diferentes são recusadas nos serviços (ex.: unidade de uma prefeitura ligada a secretaria de outra).
4. Nada é apagado fisicamente: cadastros são inativados (`ativo = false`).
5. Segredos só em variável de ambiente.
6. Auditoria grava quem, quando e antes/depois.

## 6. Testes obrigatórios

- Prefeitura A **não lê** dados da B (todas as tabelas com `municipio_id`).
- Prefeitura A **não grava** na B: inserir ou atualizar com `municipio_id` alheio é recusado pelo banco.
- Sem `app.municipio_id` definido, nenhuma linha é visível.
- O usuário do banco da aplicação não tem `BYPASSRLS` nem é dono das tabelas.
- Serviço recusa vínculo entre registros de prefeituras diferentes.
- Permissões por perfil (ex.: SOLICITANTE não abre cadastro de usuários).
- Auditoria registra inserção, alteração e exclusão com antes/depois.
- Upload de anexo grava hash e não é visível para outra prefeitura.

## 7. Entregáveis

- Código em `config/` e `apps/core/`, com migrações.
- `README` curto: como subir o ambiente e rodar os testes.
- `docker-compose` de desenvolvimento e de produção.
- Roteiro de backup e restauração em `docs/`.

## 8. Decisões do Alexandre (respondidas)

1. Login por e-mail e senha na Fase 0; prontuário do motorista fica para a Fase 3.
2. Os 8 perfis são fixos no código e criados com a prefeitura; só as permissões serão ajustáveis, depois.
3. Hospedagem: VPS própria da Hostinger.
4. Primeiro ADMIN criado por comando no servidor.
5. Auditoria de consultas a dados pessoais fica para a Fase 1.
6. Desenvolvimento no PostgreSQL 16 local, com duas roles (dona das tabelas e da aplicação, esta sem `BYPASSRLS`).

## 9. Resultado (12/10/2026)

| Item | Situação |
|---|---|
| Projeto Django, prefeitura, usuários e perfis | Pronto |
| Secretarias, unidades, centros de custo (cadastros) | Pronto |
| RLS em todas as tabelas de prefeitura | Pronto, com testes |
| Auditoria (só inserção para a aplicação) | Pronto, com testes |
| Anexos (upload com hash, download restrito à prefeitura) | Pronto, com testes |
| Telas com HTMX, menu lateral, CSS compilado (Tailwind CLI) | Pronto |
| Backup diário criptografado | Pronto e **testado** no PostgreSQL local |
| Teste de restauração e restauração real | Prontos e **testados** no PostgreSQL local |
| `Dockerfile`, `docker-compose.yml`, HTTPS (Caddy) | Escritos, **ainda não executados** (sem Docker na máquina de desenvolvimento) |

**Critério de pronto:** os testes provam que a prefeitura A não vê nem grava dados da B (`apps/core/tests/test_rls.py`, `test_telas.py`, `test_servicos.py`, `test_anexos.py`).

**Desvios em relação à spec:**
- Não há `docker-compose` de desenvolvimento: o desenvolvimento usa o PostgreSQL local (decisão do Alexandre). O compose é só de implantação.
- Celery/Redis e PWA ficam para as Fases 2 e 3, como previsto.

**Pendências para dar a fase por encerrada em produção:**
1. Primeira implantação na VPS seguindo `docs/operacao.md` (valida Docker, HTTPS e migrações no servidor).
2. Primeiro teste de restauração no servidor, com o backup real.
3. Agendar a cópia dos backups para fora do servidor.
4. Parecer do TI sobre a revisão de segurança antes de ir à produção (risco já listado no PROJETO.md).

## 10. Perguntas originais

1. **Login:** e-mail e senha bastam na Fase 0? Motorista usará prontuário (Fase 3), com campo separado depois.
2. **Perfis fixos ou editáveis?** Sugestão: os 8 perfis são fixos no código e criados com a prefeitura; só as permissões são ajustáveis, depois.
3. **Hospedagem:** VPS próprio ou servidor da prefeitura? Isso define o roteiro de implantação e o backup (decisão em aberto no PROJETO.md).
4. **Primeiro usuário ADMIN:** criado por comando no servidor (sugestão) ou por convite?
5. **Auditoria:** registrar também as **consultas** a dados pessoais de motoristas? Sugestão: deixar para a Fase 1, quando o cadastro existir.
