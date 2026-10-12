# Especificação — Fase 1: Cadastros

Status: **implementada em 12/10/2026**, pendente da validação do Alexandre (ver "Premissas e pendências").

## 1. Objetivo

A frota inteira cadastrada e conferida, com os dados de que manutenção, tráfego e abastecimento dependem: fornecedores, contratos, fiscais, empenhos (com saldo), veículos e motoristas. Carga inicial por planilha CSV.

## 2. O que foi entregue

| Módulo (app) | Telas e regras |
|---|---|
| **financeiro** | Fornecedores (CNPJ/CPF validado), contratos, fiscais de contrato (com suplente e vigência), **empenhos** com liberação total ou em parcelas, prorrogação e saldo |
| **frota** | Veículos (lista com busca e filtros, página de detalhe), categorias de veículo, marcas e modelos (catálogo global), combustíveis, equipamentos, histórico de lotação, leituras de km/horímetro, anexos (CRLV, fotos) |
| **pessoas** | Motoristas (CNH, certificados, afastamentos, penalidades, anexos), com dados pessoais protegidos |
| **importacao** | Importação de veículos e de motoristas por CSV: verificar sem gravar e importar tudo ou nada |
| **core** | Permissões por perfil e escopo (quem vê o quê), CPF/CNPJ, menu lateral por perfil, consulta a dado pessoal na auditoria |

## 3. Empenhos (decisões em `docs/decisoes.md`)

- Cada empenho vale para **uma finalidade** (manutenção ou abastecimento), em **um centro de custo**, num **período** (início e fim).
- O valor empenhado é **liberado de uma vez** (opção ao cadastrar) ou **em parcelas** (página do empenho). A soma das liberações não passa do valor empenhado.
- **Prorrogação gera um novo empenho**, ligado ao original (botão "Prorrogar" já preenche o formulário).
- **Saldo = liberado − reservado − consumido + estornado** (view `vw_saldo_empenho`, que respeita a RLS).
  - Reserva e consumo exigem saldo; o estorno não passa do que foi lançado.
  - Toda gravação passa por `apps/financeiro/services.py` e trava o empenho, para duas operações simultâneas não gastarem o mesmo saldo (há teste com duas threads).
  - Aprovar orçamento (reserva) e conferir a nota (estorna a reserva e consome o valor final) usarão esses serviços na Fase 2; o abastecimento, na Fase 5.
- Contrato do empenho é opcional, mas o tipo precisa combinar com a finalidade (manutenção ↔ contrato de manutenção; abastecimento ↔ contrato de combustível).
- Empenho com lançamentos não muda de finalidade nem de centro de custo.

## 4. Regras de frota

- Placa nos formatos ABC1234 e ABC1D23 (hífen e minúsculas são ignorados); única por prefeitura. Chassi de 17 caracteres (sem I, O, Q); RENAVAM de 9 a 11 números.
- **O km nunca diminui** (regra 4): depois do cadastro, só muda por **leitura** (`registrar_leitura`), que trava o veículo, grava o histórico e recusa km ou horímetro menor. O formulário de edição não tem o campo de km.
- Trocar a secretaria, a unidade ou o centro de custo fecha a lotação anterior e abre a nova (histórico).
- Baixa exige data e motivo. Unidade precisa pertencer à secretaria.
- **Marcas, modelos e combustíveis são globais** (compartilhados por todas as prefeituras): só se acrescenta, sem editar nem apagar; nomes não repetem (sem diferenciar maiúsculas).

## 5. Quem vê e faz o quê

| Perfil | Frota | Financeiro | Pessoas |
|---|---|---|---|
| Administrador, Gestor de frota | gerencia | gerencia | gerencia, **vê dados pessoais** |
| Gestor de unidade | vê só a sua secretaria | — | vê só a sua secretaria, **sem dados pessoais** |
| Fiscal de contrato | vê só os seus centros de custo | vê só os seus contratos e empenhos | — |
| Consulta | vê tudo (só leitura) | vê tudo (só leitura) | vê tudo, **sem dados pessoais** |
| Solicitante, Motorista, Oficina | — | — | — |

"Gerenciar" inclui "ver". As permissões novas chegam aos perfis existentes com `manage.py atualizar_perfis` (roda sozinho na implantação; só acrescenta, nunca remove).

## 6. LGPD (motoristas)

- **CPF, RG, nascimento, telefone, e-mail, endereço, CEP e dados da CNH** (número, emissão, órgão) só aparecem na ficha para quem tem `pessoas.dados_pessoais`. A lista mostra só dados operacionais (prontuário, nome, secretaria, categoria e validade da CNH).
- **Cada abertura da ficha completa (e cada download de anexo do motorista) grava na auditoria** uma consulta (ação "Consulta"): quem, quando, qual motorista.
- Penalidades só se acrescentam (sem tela para apagar) e só quem vê dados pessoais enxerga.
- Anexos: o download confere a permissão do tipo de registro e se o usuário enxerga o dono do anexo (escopo por secretaria ou centro de custo).

## 7. Importação por planilha

- Arquivo CSV (Excel em português: separador `;`, também aceita `,`; UTF-8 ou Latin-1). O arquivo modelo é baixado na própria tela, com as colunas e um exemplo.
- **Verificar** confere tudo sem gravar nada (nem marcas criadas durante a conferência). **Importar** só grava se **todas** as linhas estiverem corretas; o resultado lista cada linha com o erro.
- Usa as mesmas regras e formulários das telas, então não há como importar o que a tela recusaria. Só cadastra (placa, prontuário ou CPF já existentes são erro). Limite de 2.000 linhas por arquivo.
- Veículos referenciam secretaria (sigla), centro de custo (código), categoria e combustível **já cadastrados**; marca e modelo são criados se não existirem.

## 8. Tabelas novas

`fornecedores`, `contratos`, `fiscais_contrato`, `empenhos`, `empenho_liberacoes`, `empenho_lancamentos`, view `vw_saldo_empenho`; `marcas`, `modelos`, `combustiveis` (globais), `categorias_veiculo`, `veiculos`, `veiculo_equipamentos`, `veiculo_lotacoes`, `leituras_veiculo`; `motoristas`, `motorista_certificados`, `motorista_penalidades`, `motorista_afastamentos`. Todas as de prefeitura com RLS (teste automático confere). `usuarios.fornecedor_id` virou chave para `fornecedores` (usuário de oficina).

Diferenças em relação ao `schema_frota_v2.sql`: `empenhos` ganhou finalidade, período, `empenho_origem`; nova tabela `empenho_liberacoes`; `empenho_lancamentos` ganhou `abastecimento_id`; `categorias_veiculo` ganhou `ativo`; `auditoria.acao` aceita `C` (consulta).

## 9. Testes (188 no total)

Saldo de empenho (reserva, consumo, estorno, parcelas, inativo, **concorrência**); regras de veículo e de km; escopo por perfil; LGPD (CPF fora da lista, consulta auditada, anexos); importação (nada gravado se houver erro); isolamento entre prefeituras de **todas** as tabelas novas (A não lê nem grava na B); validadores de CPF/CNPJ; atualização de perfis.

## 10. Premissas e pendências (a validar com o Alexandre)

Premissas adotadas por falta de resposta, todas fáceis de mudar:
1. **Permissões:** quem cadastra veículos, motoristas e empenhos é o Administrador e o Gestor de frota (tabela da seção 5).
2. **Motorista:** o vínculo com usuário é opcional; o login por prontuário só entra na Fase 3.
3. **Consulta auditada** de dados pessoais, como decidido, e acesso restrito enquanto o parecer do jurídico/DPO não chega.
4. **Saldo de empenho** calculado por lançamentos (reserva/consumo/estorno) sobre o valor liberado, conforme as decisões de 12/10.

Pendentes:
- **Planilhas atuais** (colunas de veículos, motoristas e empenhos): a importação usa o **nosso** modelo de colunas; falta saber se as planilhas atuais exigem outras colunas (e a importação de empenhos, que não foi feita).
- **Como a planilha atual calcula o saldo** (por contrato ou global; parcelas e prorrogações): se diferir do modelo acima, ajustamos.
- **Carga inicial pela operadora de abastecimento** (veículos e condutores): depende do JSON real de retorno; fica para a Fase 5, como parte separada.
- **Documentos do veículo** (IPVA, licenciamento, seguro) e **alertas de CNH a vencer**: Fase 6 (a validade e a situação da CNH já aparecem na ficha e na lista).
- O saldo de abastecimento que a operadora controla é o mesmo do sistema, ou são controles separados?
