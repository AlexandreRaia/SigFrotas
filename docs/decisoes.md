# Decisões

Registro curto das decisões do Alexandre que mudam o modelo ou o escopo.

## 2026-10-12 — Empenhos

- Um empenho vale para **uma finalidade só** (manutenção ou abastecimento). As dotações orçamentárias são separadas e geram empenhos separados, **por centro de custo** (ex.: SMA, SME, SMS).
- O valor pode ser liberado **de uma vez ou parcelado**. Prorrogação de contrato gera **novos empenhos**.
- Consequências para a Fase 1 (a detalhar na especificação do módulo, com aprovação):
  - `empenhos` ganha `finalidade` e período (início e fim); o vínculo com o contrato passa a ser opcional.
  - Liberações parceladas ficam numa tabela própria dentro do empenho.
  - O saldo continua vindo de lançamentos (reserva, consumo, estorno): a manutenção consome ao aprovar o orçamento e o abastecimento consome pela importação, um lançamento por abastecimento.
- Em aberto: o saldo de abastecimento que a operadora controla é o mesmo do sistema ou são controles separados?

## 2026-10-12 — Códigos de sistemas externos

- Os cadastros do núcleo (unidades, centros de custo) **não têm campo de código externo** e o núcleo não cita nenhuma operadora.
- A ligação entre nossos cadastros e os de uma operadora (Prime ou outra) fica numa **tabela de correspondência da integração**, criada na Fase 5: sistema externo, tipo de registro, nosso código, código lá.
- Cada prefeitura usa a integração que tiver; a Prime é só a primeira.
