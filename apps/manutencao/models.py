"""Manutencao: chamado -> SMV -> orcamento -> aprovacao (reserva do empenho) -> execucao -> nota fiscal (consumo).

Ver docs/schema_frota_v2.sql e docs/fase2_manutencao.md. Mudancas de estado so pelos services.py.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import CentroCusto, ModeloDoMunicipio, Usuario
from apps.financeiro.models import Contrato, Empenho, Fornecedor
from apps.frota.models import Veiculo

PRIORIDADES = [('BAIXA', 'Baixa'), ('NORMAL', 'Normal'), ('ALTA', 'Alta'), ('URGENTE', 'Urgente')]
TANQUES = [('R', 'Reserva'), ('1/4', '1/4'), ('1/2', '1/2'), ('3/4', '3/4'), ('C', 'Cheio')]


class CategoriaServico(ModeloDoMunicipio):
    """Categoria do item de orcamento (freios, suspensao, eletrica...)."""
    nome = models.CharField(max_length=60)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = 'categorias_servico'
        constraints = [models.UniqueConstraint(fields=['municipio', 'nome'], name='uq_categoria_servico_nome')]
        ordering = ['nome']
        verbose_name = 'categoria de serviço'

    def __str__(self):
        return self.nome


class Chamado(ModeloDoMunicipio):
    """Relato de defeito (motorista, fiscal, unidade, checklist). Vai ao fiscal do centro de custo do veiculo."""
    ORIGENS = [('MANUAL', 'Manual'), ('CHECKLIST', 'Checklist'), ('PREVENTIVA', 'Preventiva'), ('FISCAL', 'Fiscal')]
    STATUS = [('ABERTO', 'Aberto'), ('EM_ANALISE', 'Em análise'), ('GEROU_SMV', 'Gerou SMV'),
              ('IMPROCEDENTE', 'Improcedente'), ('CANCELADO', 'Cancelado')]

    numero = models.CharField('Número', max_length=20)
    veiculo = models.ForeignKey(Veiculo, on_delete=models.PROTECT)
    aberto_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='chamados_abertos')
    origem = models.CharField(max_length=12, choices=ORIGENS, default='MANUAL')
    checklist_execucao_id = models.BigIntegerField(null=True, blank=True)  # vira FK na fase 3
    descricao = models.TextField('Descrição do problema')
    prioridade = models.CharField(max_length=10, choices=PRIORIDADES, default='NORMAL')
    status = models.CharField(max_length=15, choices=STATUS, default='ABERTO')
    fiscal = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name='chamados_como_fiscal')
    analisado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    analisado_em = models.DateTimeField(null=True, blank=True)
    motivo_decisao = models.TextField('Motivo', blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chamados'
        constraints = [models.UniqueConstraint(fields=['municipio', 'numero'], name='uq_chamado_numero')]
        ordering = ['-criado_em', '-id']

    def __str__(self):
        return self.numero


class Smv(ModeloDoMunicipio):
    """Solicitacao de Manutencao Veicular."""
    TIPOS = [('PREVENTIVA', 'Preventiva'), ('CORRETIVA', 'Corretiva'), ('SINISTRO', 'Sinistro')]
    ETAPAS = [('ENTRADA', 'Entrada'), ('DIAGNOSTICO', 'Diagnóstico'), ('ORCAMENTO', 'Orçamento'), ('EXECUCAO', 'Execução'),
              ('ENTREGA', 'Entrega'), ('NOTA_FISCAL', 'Nota fiscal'), ('CONCLUIDA', 'Concluída'), ('CANCELADA', 'Cancelada')]
    ETAPAS_FINAIS = ('CONCLUIDA', 'CANCELADA')

    numero = models.CharField('Número', max_length=20)
    chamado = models.ForeignKey(Chamado, null=True, blank=True, on_delete=models.PROTECT)
    veiculo = models.ForeignKey(Veiculo, on_delete=models.PROTECT)
    fornecedor = models.ForeignKey(Fornecedor, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Oficina')
    contrato = models.ForeignKey(Contrato, null=True, blank=True, on_delete=models.PROTECT)
    centro_custo = models.ForeignKey(CentroCusto, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Centro de custo')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    etapa = models.CharField(max_length=12, choices=ETAPAS, default='ENTRADA')
    entrada_em = models.DateTimeField('Entrada em', null=True, blank=True)
    entrada_km = models.IntegerField('Km na entrada', null=True, blank=True, validators=[MinValueValidator(0)])
    entrada_tanque = models.CharField('Tanque na entrada', max_length=4, blank=True, choices=TANQUES)
    defeito_relatado = models.TextField('Defeito relatado', blank=True)
    veiculo_substituto = models.ForeignKey(Veiculo, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
                                           verbose_name='Veículo substituto')
    substituto_inicio = models.DateTimeField(null=True, blank=True)
    substituto_fim = models.DateTimeField(null=True, blank=True)
    diagnostico = models.TextField('Diagnóstico', blank=True)
    saida_em = models.DateTimeField('Saída em', null=True, blank=True)
    saida_km = models.IntegerField('Km na saída', null=True, blank=True, validators=[MinValueValidator(0)])
    saida_tanque = models.CharField('Tanque na saída', max_length=4, blank=True, choices=TANQUES)
    observacao_entrega = models.TextField('Observação da entrega', blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    concluida_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    criado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'smv'
        constraints = [
            models.UniqueConstraint(fields=['municipio', 'numero'], name='uq_smv_numero'),
            # um veiculo so tem uma SMV em andamento por vez
            models.UniqueConstraint(fields=['veiculo'], condition=~Q(etapa__in=['CONCLUIDA', 'CANCELADA']),
                                    name='uq_smv_aberta_por_veiculo'),
        ]
        indexes = [models.Index(fields=['municipio', 'etapa'], name='ix_smv_etapa')]
        ordering = ['-criado_em', '-id']
        verbose_name = 'SMV'

    @property
    def aberta(self):
        return self.etapa not in self.ETAPAS_FINAIS

    def __str__(self):
        return self.numero


class SmvEtapaHist(ModeloDoMunicipio):
    smv = models.ForeignKey(Smv, on_delete=models.CASCADE, related_name='historico')
    etapa = models.CharField(max_length=12)
    usuario = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    observacao = models.TextField(blank=True)
    em = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'smv_etapas_hist'
        ordering = ['em', 'id']


class SmvMensagem(ModeloDoMunicipio):
    """Chat da SMV entre a prefeitura e a oficina. Fotos, audios, videos e PDFs vao como anexos (entidade smv_mensagens)."""
    smv = models.ForeignKey(Smv, on_delete=models.CASCADE, related_name='mensagens')
    autor = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    texto = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'smv_mensagens'
        ordering = ['criado_em', 'id']


class Orcamento(ModeloDoMunicipio):
    """Orcamento da oficina. A cada devolucao para revisao nasce uma nova revisao (mesmo numero, revisao + 1)."""
    STATUS = [('RASCUNHO', 'Em preparação'), ('RECEBIDO', 'Recebido'), ('EM_ANALISE', 'Em análise'), ('REVISAO', 'Devolvido para revisão'),
              ('APROVADO', 'Aprovado'), ('REPROVADO', 'Reprovado')]

    smv = models.ForeignKey(Smv, on_delete=models.PROTECT, related_name='orcamentos')
    empenho = models.ForeignKey(Empenho, null=True, blank=True, on_delete=models.PROTECT)
    numero = models.CharField('Número', max_length=30)
    revisao = models.SmallIntegerField('Revisão', default=1)
    ano = models.SmallIntegerField()
    mes = models.SmallIntegerField()
    status = models.CharField(max_length=12, choices=STATUS, default='RASCUNHO')
    motivo_revisao = models.TextField('Motivo da devolução', blank=True)
    valor_inicial = models.DecimalField('Valor inicial (1ª revisão)', max_digits=14, decimal_places=2, default=Decimal('0'))
    valor_pecas = models.DecimalField('Peças', max_digits=14, decimal_places=2, default=Decimal('0'))
    valor_servicos = models.DecimalField('Serviços', max_digits=14, decimal_places=2, default=Decimal('0'))
    valor_total = models.GeneratedField(expression=F('valor_pecas') + F('valor_servicos'),
                                        output_field=models.DecimalField(max_digits=14, decimal_places=2), db_persist=True)
    valor_economizado = models.GeneratedField(expression=F('valor_inicial') - (F('valor_pecas') + F('valor_servicos')),
                                              output_field=models.DecimalField(max_digits=14, decimal_places=2), db_persist=True)
    nf_pecas_numero = models.CharField('NF das peças', max_length=30, blank=True)
    nf_servicos_numero = models.CharField('NF dos serviços', max_length=30, blank=True)
    nf_pecas_valor = models.DecimalField('Valor da NF das peças', max_digits=14, decimal_places=2, null=True, blank=True)
    nf_servicos_valor = models.DecimalField('Valor da NF dos serviços', max_digits=14, decimal_places=2, null=True, blank=True)
    nf_emissao = models.DateField('Emissão da NF', null=True, blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orcamentos'
        constraints = [
            models.UniqueConstraint(fields=['municipio', 'numero', 'revisao'], name='uq_orcamento_revisao'),
            models.CheckConstraint(condition=Q(mes__gte=1, mes__lte=12), name='ck_orcamento_mes'),
        ]
        ordering = ['-criado_em', '-id']

    @property
    def nf_total(self):
        if self.nf_pecas_valor is None and self.nf_servicos_valor is None:
            return None
        return (self.nf_pecas_valor or Decimal('0')) + (self.nf_servicos_valor or Decimal('0'))

    @property
    def em_aberto(self):
        """Ainda depende de decisao (nao esta aprovado, reprovado nem devolvido)."""
        return self.status in ('RASCUNHO', 'RECEBIDO', 'EM_ANALISE')

    def __str__(self):
        return f'{self.numero} rev. {self.revisao}'


class OrcamentoItem(ModeloDoMunicipio):
    TIPOS = [('PECA', 'Peça'), ('SERVICO', 'Serviço')]

    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    categoria = models.ForeignKey(CategoriaServico, null=True, blank=True, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=7, choices=TIPOS)
    codigo = models.CharField('Código', max_length=40, blank=True)
    descricao = models.TextField('Descrição')
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('1'), validators=[MinValueValidator(Decimal('0.001'))])
    valor_unitario = models.DecimalField('Valor unitário', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    valor_referencia = models.DecimalField('Valor de referência', max_digits=12, decimal_places=2, null=True, blank=True)
    valor_total = models.GeneratedField(expression=F('quantidade') * F('valor_unitario'),
                                        output_field=models.DecimalField(max_digits=14, decimal_places=2), db_persist=True)

    class Meta:
        db_table = 'orcamento_itens'
        ordering = ['id']

    @property
    def diferenca_referencia(self):
        """Quanto o valor unitario passa (+) ou fica abaixo (-) da referencia, ou None se nao ha referencia."""
        if self.valor_referencia is None:
            return None
        return self.valor_unitario - self.valor_referencia


class OrcamentoAprovacao(ModeloDoMunicipio):
    """Uma assinatura. O numero exigido vem de municipios.config['aprovacoes_orcamento'] (padrao 3)."""
    DECISOES = [('APROVADO', 'Aprovado'), ('REPROVADO', 'Reprovado')]

    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='aprovacoes')
    sequencia = models.SmallIntegerField()
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    decisao = models.CharField(max_length=10, choices=DECISOES)
    decidido_em = models.DateTimeField(default=timezone.now)
    observacao = models.TextField(blank=True)

    class Meta:
        db_table = 'orcamento_aprovacoes'
        constraints = [
            models.UniqueConstraint(fields=['orcamento', 'sequencia'], name='uq_aprovacao_sequencia'),
            models.UniqueConstraint(fields=['orcamento', 'usuario'], name='uq_aprovacao_usuario'),  # ninguem assina duas vezes
        ]
        ordering = ['sequencia']


class DiasEmManutencao(models.Model):
    """View vw_dias_em_manutencao (somente leitura): dias entre a entrada e a saida (ou hoje) de cada SMV."""
    smv_id = models.BigIntegerField(primary_key=True)
    municipio_id = models.BigIntegerField()
    veiculo_id = models.BigIntegerField()
    numero = models.CharField(max_length=20)
    etapa = models.CharField(max_length=12)
    dias_em_manutencao = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'vw_dias_em_manutencao'
