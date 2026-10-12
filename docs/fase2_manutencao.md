# Especificação — Fase 2: Manutenção

Status: **implementada em 12/10/2026**, pendente da validação do Alexandre (ver "Premissas e pendências").

## 1. Objetivo

Aposentar a planilha de manutenção: um único fluxo, do relato do defeito à nota fiscal conferida, com o **saldo do empenho** controlado pelo próprio sistema e a **oficina** trabalhando dentro dele.

## 2. Fluxo

```
Chamado ──► SMV: ENTRADA ► DIAGNOSTICO ► ORCAMENTO ► EXECUCAO ► ENTREGA ► NOTA_FISCAL ► CONCLUIDA   (CANCELADA a qualquer hora)
              (gestor)       (oficina)     (oficina)   aprovação    (oficina)  (oficina)   conferência
                                                       reserva                             consumo
```

| Etapa | Quem faz | O que acontece |
|---|---|---|
| **Chamado** | motorista, fiscal, gestor de unidade, gestor | Relata o defeito. Vai **automaticamente ao fiscal do centro de custo** do veículo; o gestor também é avisado (e fica sabendo quando não há fiscal designado) |
| **Análise do chamado** | gestor de frota | Põe em análise, marca improcedente (com motivo; quem abriu é avisado) ou **gera a SMV** |
| **SMV (entrada)** | gestor de frota | Escolhe oficina, tipo (preventiva, corretiva, sinistro), contrato, data, km, tanque, veículo substituto. O veículo passa a "em manutenção" e o km vira leitura (nunca diminui) |
| **Diagnóstico** | oficina | Registra o que encontrou |
| **Orçamento** | oficina | Monta os itens (peça ou serviço, categoria, quantidade, valor) e envia |
| **Análise do orçamento** | gestor de frota | Informa o **valor de referência** de cada item (a tela mostra a diferença), pode **devolver para revisão** (nasce a revisão 2, 3...; todas ficam guardadas) e escolhe o **empenho** |
| **Aprovação** | quem tem "aprovar" | **3 assinaturas** (configurável). Ninguém assina duas vezes. Na **última**, o valor é **reservado** no empenho: sem saldo, não aprova (e a assinatura também não é gravada) |
| **Execução e entrega** | oficina (ou gestor por ela) | Data, hora, km e tanque na saída; fotos das peças trocadas vão no chat |
| **Nota fiscal** | oficina | Peças e serviços em notas separadas (número, valor, emissão, arquivo). Não pode passar do valor aprovado |
| **Conferência** | gestor de frota | A reserva é estornada e o **valor da nota** vira **consumo**; a SMV é concluída e o veículo volta a "disponível" |
| **Cancelamento** | gestor de frota | Com motivo; devolve ao empenho o que estava reservado e libera o veículo |

Cada mudança de etapa fica no **histórico da SMV**; valores economizados (valor inicial − valor final) são calculados no banco.

## 3. Telas

Chamados (lista, abertura, detalhe com ações) · SMVs (lista com dias parado, entrada, detalhe com etapas, diagnóstico, saída, orçamentos, nota fiscal, histórico e **chat**) · Orçamentos (lista; detalhe com itens, referências, assinaturas, empenho e saldo) · Categorias de serviço · Notificações (sino no cabeçalho).

**Portal da oficina:** o usuário com perfil Oficina (ligado a um fornecedor) vê **só as SMVs da própria oficina**, com diagnóstico, orçamento, chat e nota fiscal. O gestor pode agir pela oficina que ainda trabalha por e-mail (o que ele faz fica registrado na auditoria).

**Chat da SMV:** texto, foto, áudio, vídeo e PDF, tudo preso à SMV; a página atualiza a lista sozinha a cada 20 segundos e o outro lado é avisado.

## 4. Notificações

- **No sistema:** sino com o número de não lidas e lista em `/notificacoes/`.
- **Por e-mail:** entram na fila e saem por `manage.py enviar_notificacoes` (no servidor, o serviço `notificacoes` do compose roda a cada minuto). Em desenvolvimento os e-mails aparecem no terminal. A prefeitura pode desligar com `email_notificacoes: false` em `municipios.config`.
- **Quando:** chamado novo (fiscal e gestores), chamado improcedente (quem abriu), SMV aberta (oficina), diagnóstico, orçamento recebido, aguardando assinaturas (quem pode aprovar), devolvido para revisão (oficina), aprovado ou reprovado, veículo entregue, nota para conferir, SMV concluída ou cancelada, nova mensagem no chat e **saldo baixo** do empenho.
- Quem faz a ação não é avisado dela; avisos repetidos sobre a mesma coisa não se acumulam (chat, saldo baixo).

## 5. Regras da prefeitura (`municipios.config`)

| Chave | Padrão | Para quê |
|---|---|---|
| `aprovacoes_orcamento` | 3 | Quantas assinaturas aprovam o orçamento |
| `saldo_baixo_percentual` | 10 | Abaixo de quantos % do valor liberado o saldo vira alerta |
| `email_notificacoes` | verdadeiro | Liga ou desliga o e-mail |

## 6. Quem vê e faz o quê

| Perfil | Chamados | SMVs e orçamentos | Aprova |
|---|---|---|---|
| Administrador, Gestor de frota | todos; analisa; gera SMV | todos; conduz o fluxo; confere a nota | sim |
| Fiscal de contrato | os dos seus centros de custo; abre | os dos seus centros (leitura e chat) | não |
| Gestor de unidade | os da sua secretaria; abre | os da sua secretaria (leitura) | não |
| Motorista | **só os que abriu**; abre | não vê | não |
| Oficina | não vê | **só as da própria oficina**; diagnóstico, orçamento, entrega, nota, chat | não |
| Consulta | todos (leitura) | todos (leitura) | não |
| Solicitante | — | — | não |

Anexos do chat e notas fiscais só abrem para quem enxerga a SMV; outra prefeitura recebe "não encontrado".

## 7. Tabelas novas

`categorias_servico`, `chamados`, `smv`, `smv_etapas_hist`, `smv_mensagens`, `orcamentos`, `orcamento_itens`, `orcamento_aprovacoes`, view `vw_dias_em_manutencao`; no núcleo, `sequencias` (numeração CH-2026-0001, SMV-..., ORC-...) e `notificacoes`. Todas com RLS (teste automático confere).

Diferenças em relação ao `schema_frota_v2.sql`: orçamento ganhou a situação `RASCUNHO` (em preparação pela oficina), `motivo_revisao` e os valores das notas (`nf_pecas_valor`, `nf_servicos_valor`); `notificacoes` ganhou `link`; **uma SMV em andamento por veículo** (restrição no banco).

## 8. Testes (267 no total, 79 novos desta fase)

Fiscal do centro de custo (titular, suplente, vigência, "todos os centros"); numeração por prefeitura; entrada da SMV (km, situação do veículo, uma por veículo); orçamento (totais e colunas geradas, revisões, referências); **aprovação** (3 assinaturas, reserva, sem saldo não aprova e não grava, empenho obrigatório, permissões, reprovação); entrega, nota fiscal, **conferência (reserva → consumo)** e cancelamento (estorno); saldo baixo; e-mail na fila e envio; chat; telas por perfil (oficina só vê as suas, motorista só os seus, outra prefeitura recebe 404).

## 9. Premissas e pendências (a validar com o Alexandre)

Premissas adotadas por falta de resposta:
1. **Quem assina:** qualquer usuário com a permissão "aprovar" (hoje, Administrador e Gestor de frota), **sem ordem fixa e sem alçada por valor**; 3 assinaturas, ninguém assina duas vezes.
2. **Uma SMV em andamento por veículo.**
3. **A nota não pode passar do valor aprovado**; se precisar, a oficina pede novo orçamento.
4. **Conferência da nota** é do gestor de frota; o fiscal acompanha e é avisado.
5. E-mail sai pela fila a cada minuto (sem Celery/Redis por enquanto: a rotina é simples e o volume é baixo).

Pendentes:
- **Regras reais de aprovação do orçamento** (quem assina, em que ordem, valores de alçada): se a prefeitura tem faixas de valor, entram como configuração.
- **Como a planilha atual calcula o saldo do empenho** (confirma o modelo de reserva e consumo).
- **Vistoria de entrada e de entrega (checklist)** e **chamado automático por item crítico**: vêm com o tráfego digital (Fase 3); hoje a entrega tem data, km, tanque e observação.
- **Manutenção preventiva** (planos por km, horas e dias, alerta e chamado automático): Fase 6.
- **Leitura de orçamento em PDF/foto por IA**: Fase 7.
- Provedor de e-mail da prefeitura (dados de SMTP) para ligar o envio em produção.
