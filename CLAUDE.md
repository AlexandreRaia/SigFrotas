# CLAUDE.md — Sistema de Gestão de Frotas

Lido no início de cada sessão. Siga estas regras em todo o projeto. Documentos de referência: `docs/PROJETO.md` (o que construir) e `docs/schema_frota_v2.sql` (modelo de dados).

## 1. Contexto

- **Projeto:** sistema novo, do zero, de gestão de frotas para a Prefeitura de Santana de Parnaíba (Departamento de Transportes, subordinado à Secretaria de Administração), **desenhado para ser usado por outras prefeituras** (multi-tenant). **Não integra com o SisFrota**; dados históricos úteis são importados uma vez.
- **Responsável (dono do produto):** Alexandre, **analista de TI**. Não há equipe de desenvolvimento: o trabalho é feito por Claude e subagentes; o Alexandre revisa e valida. Pode usar termos técnicos, mas **mantenha a simplicidade**: soluções simples, código legível, explicações curtas, em português.
- **Idioma:** nomes de tabelas, colunas e variáveis em **português sem acentos**, como no schema (`veiculos`, `fichas_trafego`). Textos ao usuário, documentação e commits em português.

## 2. O que existe hoje (e o sistema substitui)

- **Ficha de tráfego em papel** (motorista, prontuário, placa, km, trechos; verso com checklist). Digitação atrasa 15–25 dias; sem roteiro.
- **Manutenção em planilha** (orçamento, itens, veículos, saldo de empenhos por centro de custo); fotos no Google Drive; fiscais de contrato por centro de custo reclamam por telefone/e-mail.
- **Abastecimento** pela **Prime Benefícios** (contrato de 5 anos; cartão em rede credenciada; **tem API**). O sistema importa; não se digita abastecimento.
- **SisFrota** e **controle/chaves:** sistemas atuais, que serão substituídos.

## 3. Stack (confirmar com o Alexandre antes de mudar)

- **Backend:** Python + **Django** (monólito modular). **Banco:** **PostgreSQL 14+** com Row Level Security.
- **Front:** templates Django + HTMX + Tailwind; **PWA** para o motorista, com **modo offline** (armazenamento local do navegador) e sincronização posterior.
- **Tarefas agendadas/em segundo plano:** Celery + Redis (ou django-q no início): importação da Prime, alertas, e-mails.
- **Arquivos:** compatível com S3 (disco local em desenvolvimento). **Nunca** Google Drive como armazenamento do sistema.
- **Mapas:** Leaflet + OpenStreetMap (sem custo por uso).
- **Painéis:** módulo próprio no início; Metabase/Superset em réplica de leitura depois.
- **IA (fase 7):** API do Claude para classificar chamados, ler orçamentos e resumir; **sugere, pessoa confirma**.
- **Implantação:** Docker em VPS, HTTPS, backup diário **com teste de restauração**.

## 4. Estrutura

```
config/            # settings, urls, celery
apps/
  core/            # municipios, secretarias, unidades, centros_custo, perfis, usuarios, auditoria, anexos, notificacoes
  frota/           # veiculos, equipamentos, lotacoes, leituras, documentos, multas, sinistros
  pessoas/         # motoristas, certificados, penalidades, afastamentos
  agendamento/     # solicitacoes_veiculo, agenda
  trafego/         # fichas_trafego, trechos, pontos_gps, historico, API de sincronizacao offline
  checklists/      # modelos, itens, execucoes, respostas
  manutencao/      # chamados, smv, orcamentos, aprovacoes, planos preventivos, chat da SMV
  financeiro/      # fornecedores, contratos, fiscais_contrato, empenhos, lancamentos
  abastecimento/   # cartoes, abastecimentos, integracao Prime, despesas
  relatorios/      # indicadores e relatorios
docs/              # PROJETO.md, schema_frota_v2.sql, especificacoes por modulo, decisoes
```

Um módulo não lê tabelas de outro quando há regra de negócio: usa o serviço do módulo dono.

## 5. Multi-prefeitura (regra mais importante)

- **Toda tabela de negócio tem `municipio_id`** e toda consulta é filtrada por ele.
- Isolamento com **RLS**: a aplicação executa `SET app.municipio_id = '<id>'` a cada requisição/transação. O usuário do banco da aplicação **não** é dono das tabelas e **não** tem `BYPASSRLS`.
- Chaves estrangeiras não garantem que dois registros sejam da mesma prefeitura: **validar nos serviços e nos testes**.
- **Todo teste de segurança deve provar que a prefeitura A não enxerga nem grava dados da B.**
- Catálogos globais (sem `municipio_id`): `marcas`, `modelos`, `combustiveis`.
- Regras específicas de cada prefeitura (prazos, nº de aprovações, % de saldo baixo, tolerância de km) ficam em `municipios.config`. **Nada de "Santana de Parnaíba" no código.**

## 6. Banco de dados

- `docs/schema_frota_v2.sql` (53 tabelas) é a **referência**; já foi carregado e testado em PostgreSQL 16 (RLS, trava de agenda, saldo de empenho). Em produção o schema evolui por **migrações do Django**, nunca por alteração manual.
- Recursos do PostgreSQL já usados e que devem ser mantidos nos models/migrações: `EXCLUDE ... USING gist` (conflito de agenda de veículo e motorista, exige `btree_gist`), colunas geradas (`valor_total`, `valor_economizado`), views `vw_saldo_empenho`, `vw_consumo_veiculo`, `vw_dias_em_manutencao`.
- Dinheiro em `numeric`; datas/horas em `timestamptz`; status por listas fechadas (`CHECK`/choices).
- Evitar nomes reservados em ferramentas de modelagem (não usar coluna `local`).
- Alto volume (`ficha_pontos_gps`, `auditoria`, `notificacoes`): particionar por data quando crescer.

## 7. Regras de negócio

1. Secretaria só vê o que é seu; fiscal só vê seus centros de custo; oficina só vê suas SMVs.
2. Dois agendamentos **aprovados** não ocupam o mesmo veículo/motorista no mesmo período (garantido no banco).
3. Motorista com CNH vencida ou categoria incompatível não é alocado sem justificativa registrada.
4. Km nunca diminui; km inicial da ficha = km final da anterior (tolerância configurável), senão vai para conferência.
5. **Ficha de tráfego:** `RASCUNHO → ENVIADA → VALIDADA_GESTOR → CONFERIDA → ARQUIVADA`, com `DEVOLVIDA` ao motorista (motivo obrigatório). Ficha arquivada não se altera. Envio offline é **idempotente** (`client_uuid`).
6. **Manutenção:** chamado → SMV (`ENTRADA → DIAGNOSTICO → ORCAMENTO → EXECUCAO → ENTREGA → NOTA_FISCAL → CONCLUIDA`). Chamado vai automaticamente ao **fiscal do centro de custo** do veículo.
7. **Orçamento** só é aprovado com **saldo de empenho** suficiente: aprovação gera `RESERVA`; nota fiscal conferida converte em `CONSUMO`. Revisões do orçamento são guardadas. Aprovação em até 3 assinaturas (configurável).
8. Alertas: CNH e documentos a vencer (30 dias antes e após vencer), revisão preventiva por km/horas/dias, saldo baixo, item crítico de checklist, anomalias de abastecimento.
9. Valores, aprovações e baixas são **decisão humana**; automações e IA só sugerem.
10. Todo registro relevante grava **auditoria**.

## 8. Integrações

- **Prime Benefícios (API Sisatec, `ws.sisatec.com.br`):** web service **somente de consulta** (sem webhook): o sistema **busca periodicamente**. Autenticação por `codigo` + `key` (fornecidos pela Prime), **segredos: só em variável de ambiente, nunca no código, no repositório, em log ou em documento**. Retorno JSON (ou XML).
  - **Endpoint principal:** `abastecimento/novo/bydata?codigo=&key=&data1=&data2=&status=&tipo_posto=&tipo_servico=&pagina=`. Usar `status=2` (ativos e inativos), `tipo_posto=2` (**o padrão exclui postos internos**) e `tipo_servico=0` (todos; classificar depois). Outros: `novo/all` com `alterados=a` (km corrigido), `foradarede`, `dataeunidade`, `dadosacumulados`, `abastecimentoempenho`.
  - **Datas na URL no formato `MM-dd-yyyy`** (americano). Datas do retorno em `dd/MM/yyyy` e hora `hh:mm:ss`, no horário de Brasília. Valores numéricos vêm como **texto**: converter com cuidado (confirmar o separador decimal com um retorno real).
  - **Resposta:** `pagina_atual`, `total_paginas` e a lista `abastecimentos[]`, com dados do posto (nome, razão social, CNPJ, endereço, lat/long), do abastecimento (`codAbastecimento`, data, hora, `kmAtual`, `kmAnterior`, `data_atualizacao_km`, combustível, litros, valor, valor por litro, `tipo_servico`, `nomeServico`, `status`, observação), do veículo (placa, prefixo, marca, modelo, renavam, chassi, ano, cor, tanque, `centroDeCustoVeiculo`, `TipoFrota`) e do condutor (nome, registro, matrícula, CNH, CPF, centro de custo). Mapeamento para o schema em `abastecimentos`, `postos`, `cartoes`.
  - **Importação = upsert idempotente** pela chave `codAbastecimento` (`abastecimentos.id_externo`). A Prime pode **corrigir o km e inativar** abastecimentos depois: reconsultar uma janela recente (ex.: últimos 60 dias) e os `alterados`; `INATIVO` = cancelado, **nunca apagar**. Registrar cada execução em `integracao_logs`.
  - **Veículo não cadastrado:** gravar o abastecimento com `veiculo_id` nulo e `placa_externa`, e listar como pendência de vínculo. A resposta também serve para a **carga inicial** de veículos e motoristas (ver seção 12, fase 1).
  - **LGPD:** a resposta traz **CPF e CNH do condutor**. Usar só para localizar o motorista cadastrado e **não gravar** no `payload`. Do cartão (`numerCartao`) guardar só os últimos dígitos.
  - **Credenciais na URL:** `key` vai na query string. **Nunca registrar a URL completa em log**; mascarar a chave. Erros vêm como JSON (`{"Message": "nao autorizado"}` etc.): tratar como falha da execução, não como "zero registros".
  - `unidades`/subunidades da Prime se ligam às nossas por `unidades.codigo_externo` e `centros_custo.codigo_externo`.
  - **Falta ainda:** um **JSON real de retorno** (formato dos números e valores de `status`, `tipo_servico`, `TipoFrota`) e o formato do retorno do endpoint de **empenho** (não descrito).
- **E-mail:** serviço transacional; notificações pela fila `notificacoes`. Solicitações aprovadas enviam arquivo `.ics`.
- **Sisgep / TCE:** verificar com o Alexandre antes de modelar relatórios oficiais.

## 9. Segurança e LGPD

- **Nunca** no código ou no repositório: senhas, chaves, dados reais, dumps. Variáveis de ambiente (`.env` fora do Git; manter `.env.example`).
- Dados pessoais de motoristas (CPF, RG, endereço, CNH): acesso por perfil e consulta auditada.
- **GPS só durante trecho de ficha ativa**, nunca fora do serviço; finalidade e prazo de guarda definidos.
- Cartões: guardar só os últimos dígitos.
- IA externa: não enviar dados pessoais sem necessidade; registrar o que foi enviado.
- Trabalhar sempre em ambiente de teste; nunca alterar produção direto.

## 10. Forma de trabalhar

- **Antes de codar um módulo:** especificação curta em `docs/` (objetivo, telas, regras, tabelas) e **aprovação do Alexandre**.
- **Testes automáticos obrigatórios** para regras de negócio, isolamento entre prefeituras, saldo de empenho, conflito de agenda, sincronização offline e importação da Prime. Rodar os testes antes de dar uma tarefa por concluída.
- **Simplicidade primeiro:** a solução mais simples que resolve; sem abstrações, camadas ou bibliotecas que o projeto não precisa hoje; preferir recursos nativos do Django.
- Mudanças pequenas, commits frequentes em português explicando o "porquê".
- Ao terminar uma tarefa: 1–3 frases com o que mudou e o que o Alexandre precisa validar.
- Faltou informação de negócio: **perguntar**, não supor.

## 11. Subagentes (a criar em `.claude/agents/`)

| Agente | Função |
|---|---|
| arquiteto | Planeja o módulo e escreve a especificação |
| desenvolvedor | Implementa conforme a especificação aprovada |
| banco-de-dados | Models, migrações, consultas, RLS, views |
| testes | Escreve e roda os testes |
| revisor-seguranca | Isolamento entre prefeituras, LGPD, segredos, permissões |
| integracoes | API da Prime, e-mail, importações |
| documentacao | Manual de uso e documentação técnica |

O agente principal orquestra, junta os resultados e confere antes de apresentar.

## 12. Ordem de entrega

0. **Fundação:** projeto, prefeitura, usuários/perfis, estrutura organizacional, RLS, auditoria, anexos, implantação.
1. **Cadastros:** veículos, motoristas, fornecedores, contratos, fiscais, empenhos; importação de planilhas e **carga inicial de veículos e motoristas a partir da Prime** (placa, marca, modelo, renavam, chassi, tanque, tipo de frota, condutores).
2. **Manutenção:** chamados, SMV, orçamento, empenho/saldo, portal da oficina, chat, notificações (**aposenta a planilha**).
3. **Tráfego digital:** PWA, checklists, validação em 3 níveis, GPS, conferência (piloto em paralelo ao papel).
4. **Solicitação e agendamento.**
5. **Abastecimento (Prime) e despesas.**
6. **Documentos, multas, sinistros e preventiva.**
7. **Painéis e IA.**

## 13. Decisões em aberto

Ver a seção 10 de `docs/PROJETO.md`. Principais: documentação da API da Prime; regras reais de aprovação do orçamento; cálculo atual do saldo de empenho; política de uso de veículos; exportação de dados do SisFrota; parecer do jurídico/DPO sobre GPS; hospedagem; titularidade do código.
