# Projeto — Sistema de Gestão de Frotas

Versão 1 · Outubro/2026 · Responsável: Alexandre (Departamento de Transportes / SMA, Prefeitura de Santana de Parnaíba)

> Sistema novo, construído do zero, **sem integração com o SisFrota**. Os dados históricos que valerem a pena serão **importados** uma vez. O documento "Gestão de solicitação e agendamento de veículos" (abr/2024) foi usado como base do problema, não como especificação.

## 1. Objetivo

Um único sistema, próprio da prefeitura, que cubra o ciclo completo da frota: **quem pede o veículo, quem o usa, quanto roda, quanto gasta e como é mantido**, com dados em tempo real para gestores, fiscais e gabinete. Desenhado desde o início para ser **adotado por outras prefeituras**.

**Problemas que resolve (hoje):**
- Ficha de tráfego em papel: digitação atrasa de 15 a 25 dias, letra ilegível, sem roteiro, relatórios para o gabinete feitos à mão.
- Manutenção em planilha: orçamentos, itens, saldo de empenho e fotos (Drive) soltos; sem visão única; reclamações dos fiscais por telefone.
- Dependência de sistemas de terceiros, que somem com o fim do contrato.
- Abastecimento em sistema da Prime, separado dos demais custos.

## 2. Princípios

1. **Simplicidade primeiro:** o mínimo de telas e cliques para cada perfil; nada que o projeto não precise hoje.
2. **Uma fonte de verdade:** cada informação (km, saldo, status) é registrada uma vez e calculada daí em diante.
3. **Tempo real:** fichas, chamados e saldos atualizados na hora, não 25 dias depois.
4. **O sistema avisa, a pessoa decide:** alertas e sugestões automáticas; aprovações e valores são sempre humanos.
5. **Multi-prefeitura de nascença:** nada fixo no código; regras por prefeitura em configuração.
6. **Rastro completo:** toda mudança relevante fica na auditoria.

## 3. Perfis

| Perfil | Quem é | O que faz |
|---|---|---|
| **Administrador** | Departamento de Transportes (chefia) | Tudo; configura regras, perfis, contratos; confere fichas; aprova orçamentos |
| **Gestor de frota** | Equipe do Departamento de Transportes | Analisa solicitações e chamados, cria SMV, analisa orçamentos, aloca veículos e motoristas |
| **Gestor de unidade** | Responsável por uma unidade/secretaria | Valida as fichas de tráfego da sua unidade; vê só o que é da sua secretaria |
| **Solicitante** | Servidor de qualquer secretaria | Pede veículo e acompanha; vê só a sua secretaria |
| **Motorista** | Condutor | Preenche ficha de tráfego e checklist no celular; abre chamado |
| **Fiscal de contrato** | Designado por contrato e centro de custo | Acompanha SMVs e saldo do seu centro de custo; abre e acompanha chamados |
| **Oficina** | Usuário externo | Vê só as SMVs da sua oficina: diagnóstico, orçamento, chat, nota fiscal |
| **Consulta** | Gabinete, controle interno | Só leitura, painéis e relatórios |

## 4. Módulos e fluxos

### 4.1 Cadastros
Veículos (incluindo máquinas com horímetro; tipos de frota: próprio, locado, estadual, doação, cedido), motoristas (prontuário, CNH, certificados, penalidades, férias/folgas), secretarias, unidades, centros de custo, fornecedores, contratos, fiscais, empenhos. Fotos e documentos (CRLV, CNH) como anexos. **Importação inicial** por planilha.

### 4.2 Solicitação e agendamento
1. Solicitante informa data/hora, origem, destino, tipo de veículo, passageiros e finalidade.
2. Gestor de frota vê a **agenda de veículos e motoristas** em um só lugar, analisa (prioridade, disponibilidade, política de uso) e **aprova alocando veículo e motorista**, ou reprova com motivo.
3. O banco **impede conflito** (mesmo veículo ou motorista, no mesmo período). O sistema também alerta CNH vencida/categoria incompatível e motorista afastado.
4. Solicitante, motorista e gestor recebem e-mail com os detalhes e um **arquivo de calendário (.ics)** que abre no calendário de cada um.
5. No dia, a ficha de tráfego já nasce ligada à solicitação; ao concluir a ficha, a solicitação vira "finalizada".

Status em duas dimensões: **aprovação** (pendente, aprovada, reprovada, cancelada) e **andamento** (pendente, em andamento, finalizado).

### 4.3 Controle de tráfego digital (substitui a ficha de papel)
- **Aplicação web instalável no celular (PWA)**, que **funciona offline** e sincroniza quando houver Wi-Fi; cada ficha tem um identificador gerado no aparelho, então reenviar nunca duplica.
- **Entrada rápida:** QR code colado no veículo abre a ficha com a placa preenchida. Login por prontuário e senha; biometria do aparelho quando disponível.
- Conteúdo: veículo, motorista, data, plantão, departamento requisitante, km/horímetro, **trechos** (partida, itinerário, chegada, km, usuário atendido), **checklist** de início e de final e **trilha GPS** durante os trechos.
- **Validação em três níveis:** motorista confere e envia → gestor da unidade valida → Departamento de Transportes confere (sequência de km, horários, rota) e **arquiva ou devolve** ao motorista com o motivo.
- **Conferência automática:** o sistema marca fichas em que o km inicial não bate com o km final da anterior, com horários sobrepostos ou km rodado fora do padrão, para o conferente olhar só o que importa.
- **Transição:** durante o piloto, o gestor pode lançar fichas pela web (origem "web") e digitar as de papel pendentes (origem "papel"), sem perder o histórico.
- Checklist com item **crítico** (freio, pneu, luz) gera alerta imediato ao gestor de frota e, se marcado, abre chamado.

### 4.4 Manutenção
Fluxo: **chamado → SMV → diagnóstico → orçamento → aprovação → execução → entrega → nota fiscal → conclusão.**

1. **Chamado:** motorista, fiscal ou checklist relata o problema. O sistema encaminha ao **fiscal do centro de custo** do veículo. Acaba a reclamação por telefone.
2. **Análise:** gestor de frota decide se procede; se sim, abre a **SMV** (preventiva, corretiva ou sinistro), escolhe a oficina e registra **entrada** (data, hora, km, nível do tanque, defeito, veículo substituto).
3. **Oficina** (acesso externo restrito) registra diagnóstico, fotos/vídeos e **envia o orçamento** em itens (peça ou serviço, categoria, quantidade, valor).
4. **Análise do orçamento:** o sistema compara cada item com o **valor de referência** (pesquisa de preços/contrato) e mostra a diferença; pode devolver para **revisão** (cada revisão é guardada). O **valor economizado** é calculado: valor inicial menos valor final.
5. **Aprovação** em até 3 assinaturas (configurável). Ao aprovar, o sistema **reserva o saldo do empenho** do centro de custo; **sem saldo, não aprova**. Alerta quando o saldo ficar abaixo de um percentual configurado.
6. **Execução e entrega:** inspeção final (checklist de vistoria), data, hora, km, tanque, **fotos das peças substituídas**.
7. **Nota fiscal** (peças e serviços separadas) enviada pela oficina; conferida, o saldo passa de **reserva para consumo**.
8. **Chat da SMV** entre prefeitura e oficina (texto, foto, áudio, vídeo, PDF), tudo registrado na própria SMV.
9. **Dias em manutenção** e tempo de cada etapa são calculados automaticamente.

**Preventiva:** planos por km, horas (máquinas) ou dias, por veículo, modelo ou categoria; o sistema alerta antes do vencimento e gera o chamado.

### 4.5 Abastecimento e despesas
- **Prime Benefícios:** importação automática pela API (consulta periódica, várias vezes ao dia), **sem duplicar** e **atualizando** o que a Prime alterar depois (km corrigido, abastecimento inativado, nunca apagado). Traz também o posto (com localização), o serviço realizado, o condutor e o km anterior, o que permite calcular o consumo por abastecimento. Inclui os abastecimentos **fora da rede** credenciada e a conciliação com o empenho informado pela Prime. As unidades e centros de custo da Prime são ligados aos do sistema por uma tabela de correspondência da integração (fase 5), sem campos específicos nos cadastros. Abastecimento de placa ainda não cadastrada fica numa lista de **pendências de vínculo**.
- **Carga inicial:** os dados de veículos e condutores que a Prime já tem servem para pré-cadastrar a frota e os motoristas, a conferir antes de usar.
- **Alertas de anomalia:** litros acima da capacidade do tanque, consumo (km/l) fora do padrão, abastecimento sem ficha de tráfego no dia, horário ou posto incomum, dois abastecimentos muito próximos.
- **Despesas** (pedágio, zona azul, estacionamento, refeição) ligadas ao veículo e à ficha.

### 4.6 Documentos, multas e sinistros
Vencimentos (IPVA, licenciamento, seguro, CNH) com aviso 30 dias antes e após vencer, até regularizar. Multas com indicação do condutor, ajudada pela ficha do dia. Sinistros com BO, número de processo, anexos e ligação à SMV.

### 4.7 Notificações
Fila única de notificações (e-mail e no sistema) para: solicitação decidida, ficha devolvida, chamado novo ao fiscal, orçamento recebido, saldo baixo, CNH e documentos a vencer, irregularidade de checklist.

### 4.8 Indicadores e relatórios
Painel em tempo real e relatórios exportáveis (PDF, CSV, XLSX), com filtros por período, veículo, condutor, secretaria, unidade, centro de custo, contrato e oficina.

| Indicador | Cálculo / uso |
|---|---|
| Custo operacional por km (COV) | (combustível + manutenção + despesas + locação) ÷ km rodado |
| Consumo | km/l por veículo e por período |
| Custo de manutenção | por veículo, centro de custo, contrato, oficina, tipo |
| Economia em orçamentos | soma do valor economizado |
| Disponibilidade da frota | % de veículos aptos a operar |
| Ociosidade | dias sem uso por veículo |
| Tempo de parada | dias em manutenção; tempo por etapa da SMV |
| Segurança | sinistros por km; multas por condutor |
| Controle | fichas pendentes de validação e de conferência; saldo de empenho |

Relatório pronto para o gabinete: utilização de um veículo ou secretaria em um período, com roteiro.

## 5. Regras de negócio (principais)

1. Cada secretaria só enxerga os próprios dados; fiscal só enxerga os seus centros de custo; oficina só as suas SMVs.
2. Dois agendamentos aprovados não podem ocupar o mesmo veículo ou motorista no mesmo período.
3. Veículo com motorista de CNH vencida ou categoria incompatível não é alocado sem justificativa registrada.
4. O km de um veículo nunca diminui; o km inicial de uma ficha deve ser igual ao final da anterior (com tolerância configurável), senão vai para conferência.
5. Orçamento só é aprovado com saldo de empenho suficiente no centro de custo.
6. Ficha arquivada não é alterada; correções passam por devolução e ficam no histórico.
7. Valores, aprovações e baixas são sempre decisão humana; alertas e sugestões automáticas apenas apontam.
8. Todo registro relevante grava auditoria (quem, quando, antes e depois).

## 6. Arquitetura e tecnologia

- **Monólito modular** em Django + PostgreSQL (53 tabelas, ver `schema_frota_v2.sql`), isolamento por prefeitura com Row Level Security.
- **Front:** páginas do próprio Django com HTMX e Tailwind; **PWA** para o motorista (offline com armazenamento local do navegador).
- **Tarefas em segundo plano:** Celery + Redis (ou django-q no início) para importação da Prime, alertas e envio de e-mails.
- **Arquivos:** armazenamento compatível com S3; fotos reduzidas no celular antes do envio.
- **Mapas:** biblioteca de mapas livre (Leaflet/OpenStreetMap) para a trilha, sem custo por uso; Google Maps só se for exigido.
- **Painéis:** módulo de relatórios próprio no início; Metabase ou Superset sobre réplica de leitura na fase de análise.
- **IA (fase posterior):** classificar chamados, ler orçamentos em PDF/foto e preencher os itens, resumos para gestores. Sempre como sugestão.
- **Implantação:** Docker em servidor próprio (VPS) com HTTPS e backup diário testado.

### Mapa do modelo de dados
| Módulo | Tabelas |
|---|---|
| Núcleo | municipios, secretarias, unidades, centros_custo, perfis, usuarios |
| Catálogos | marcas, modelos, combustiveis, categorias_veiculo, categorias_servico |
| Contratos e dinheiro | fornecedores, contratos, fiscais_contrato, empenhos, empenho_lancamentos |
| Frota | veiculos, veiculo_equipamentos, veiculo_lotacoes, leituras_veiculo |
| Motoristas | motoristas, motorista_certificados, motorista_penalidades, motorista_afastamentos |
| Agendamento | solicitacoes_veiculo |
| Tráfego | fichas_trafego, ficha_trechos, ficha_pontos_gps, ficha_historico |
| Checklists | checklist_modelos, checklist_itens, checklist_execucoes, checklist_respostas |
| Manutenção | chamados, smv, smv_etapas_hist, smv_mensagens, orcamentos, orcamento_itens, orcamento_aprovacoes, planos_preventivos, preventivas_realizadas |
| Abastecimento | cartoes, postos, abastecimentos, integracao_logs, despesas |
| Ocorrências | documentos_veiculo, multas, sinistros |
| Transversal | notificacoes, anexos, auditoria |

## 7. Segurança e LGPD

- **Dados pessoais:** CPF, RG, endereço, CNH e telefone de motoristas: acesso restrito por perfil, com auditoria de consulta.
- **GPS:** coletado **apenas durante os trechos de uma ficha ativa**, nunca fora do serviço; finalidade e prazo de guarda definidos e informados aos condutores. Precisa de aval do jurídico e do encarregado de dados (DPO) da prefeitura.
- **Cartões:** guardar só os últimos dígitos.
- **Senhas e chaves** fora do código; backups criptografados; log de acessos.
- **IA externa:** não enviar dados pessoais sem necessidade; registrar o que foi enviado.

## 8. Plano de entrega (em fases)

Cada fase termina com algo **usável** e é validada por você antes da próxima.

| Fase | Entrega | Critério de pronto |
|---|---|---|
| **0 Fundação** | Projeto Django, prefeitura, usuários e perfis, secretarias/unidades/centros de custo, RLS, auditoria, anexos, implantação | Testes provam que a prefeitura A não vê dados da B |
| **1 Cadastros** | Veículos, motoristas, fornecedores, contratos, fiscais, empenhos; importação das planilhas | Frota inteira cadastrada e conferida |
| **2 Manutenção** | Chamados, SMV, orçamento, empenho/saldo, portal da oficina, chat, notificações | **Planilha aposentada**; uma oficina real usando |
| **3 Tráfego digital** | PWA do motorista, checklists, validação em 3 níveis, trilha GPS, painel de conferência | Piloto em 1–2 secretarias, em paralelo ao papel |
| **4 Solicitação e agendamento** | Pedido, agenda, aprovação, e-mails e .ics | Solicitações de todas as secretarias pelo sistema |
| **5 Abastecimento** | Integração Prime, alertas, despesas | Abastecimento importado sozinho, sem duplicidade |
| **6 Ocorrências e preventiva** | Documentos, multas, sinistros, planos preventivos | Alertas de vencimento funcionando |
| **7 Painéis e IA** | Indicadores, relatórios para o gabinete, apoio de IA | Relatório do gabinete em minutos |

A ordem prioriza a **maior dor atual** (manutenção) e dá tempo ao tráfego digital, que é a mudança de hábito mais difícil, para ser pilotado com calma.

## 9. Riscos e como tratar

| Risco | Tratamento |
|---|---|
| Resistência dos motoristas (celular e pacote de dados) | App simples; funciona offline e sobe no Wi-Fi; QR code no veículo; piloto; avaliar tablet no veículo ou celular institucional |
| GPS em segundo plano é limitado em navegador | Capturar nos pontos-chave (partida e chegada) e durante o uso com a tela ativa; se não bastar, avaliar app nativo depois |
| Escopo grande | Fases curtas; nada de módulo novo antes de fechar o anterior |
| Qualidade dos dados importados | Importar em lote de teste e conferir antes de usar |
| Oficinas sem hábito de sistema | Tela mínima, treinamento e canal de suporte; manter e-mail como alternativa no início |
| Falta de equipe | Testes automáticos desde a fase 0; documentação no repositório; revisão de segurança por TI antes de produção |

## 10. Decisões em aberto

- [ ] **Prime Benefícios:** já temos endpoints e campos do retorno; falta um **JSON real** (formato dos números, valores de status, tipo de serviço e tipo de frota) e o retorno do endpoint de **empenho**.
- [ ] Regras reais de **aprovação do orçamento** (quem assina, em qual ordem, valores de alçada).
- [ ] Como a planilha atual calcula o **saldo dos empenhos** (e se há empenho por contrato ou global).
- [ ] **Política de uso de veículos** da prefeitura (critérios de prioridade e restrições).
- [ ] Possibilidade de **exportar os dados do SisFrota** (e do controle/chaves) para importação.
- [ ] Avaliação do **jurídico/DPO** sobre GPS e dados pessoais; exigências do **TCE** e do **Sisgep**.
- [ ] **Hospedagem** (servidor próprio da prefeitura ou nuvem) e quem faz o backup.
- [ ] Titularidade e licença do código (importante para oferecer a outras prefeituras).
