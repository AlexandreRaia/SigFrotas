"""Fornecedores, contratos, fiscais e empenhos (ver docs/schema_frota_v2.sql e docs/decisoes.md)."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import CentroCusto, ModeloDoMunicipio, Usuario


class Fornecedor(ModeloDoMunicipio):
    TIPOS = [('OFICINA', 'Oficina'), ('LOCADORA', 'Locadora'), ('POSTO', 'Posto'), ('AUTOPECAS', 'Autopeças'),
             ('SEGURADORA', 'Seguradora'), ('OPERADORA_CARTAO', 'Operadora de cartão'), ('OUTRO', 'Outro')]

    cnpj_cpf = models.CharField('CNPJ/CPF', max_length=14)  # so numeros
    razao_social = models.TextField('Razão social')
    tipo = models.CharField(max_length=20, choices=TIPOS)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fornecedores'
        constraints = [models.UniqueConstraint(fields=['municipio', 'cnpj_cpf'], name='uq_fornecedor_documento')]
        ordering = ['razao_social']

    def __str__(self):
        return self.razao_social


class Contrato(ModeloDoMunicipio):
    TIPOS = [('MANUTENCAO', 'Manutenção'), ('LOCACAO', 'Locação'), ('COMBUSTIVEL', 'Combustível'),
             ('SEGURO', 'Seguro'), ('OUTRO', 'Outro')]

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    numero = models.CharField('Número', max_length=40)
    processo = models.CharField(max_length=40, blank=True)
    objeto = models.TextField()
    vigencia_ini = models.DateField('Início da vigência')
    vigencia_fim = models.DateField('Fim da vigência')
    valor_total = models.DecimalField('Valor total', max_digits=14, decimal_places=2, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contratos'
        constraints = [
            models.UniqueConstraint(fields=['municipio', 'numero'], name='uq_contrato_numero'),
            models.CheckConstraint(condition=models.Q(vigencia_fim__gte=models.F('vigencia_ini')), name='ck_contrato_vigencia'),
        ]
        ordering = ['-vigencia_fim', 'numero']

    def clean(self):
        if self.vigencia_ini and self.vigencia_fim and self.vigencia_fim < self.vigencia_ini:
            raise ValidationError({'vigencia_fim': 'O fim da vigência não pode ser antes do início.'})

    def __str__(self):
        return f'{self.numero} - {self.fornecedor}'


class FiscalContrato(ModeloDoMunicipio):
    """Quem fiscaliza qual contrato em qual centro de custo (centro vazio = todos)."""
    contrato = models.ForeignKey(Contrato, on_delete=models.PROTECT)
    centro_custo = models.ForeignKey(CentroCusto, null=True, blank=True, on_delete=models.PROTECT)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, verbose_name='Fiscal')
    suplente = models.BooleanField(default=False)
    vigencia_ini = models.DateField('Início', default=timezone.localdate)
    vigencia_fim = models.DateField('Fim', null=True, blank=True)

    class Meta:
        db_table = 'fiscais_contrato'
        ordering = ['-vigencia_ini']

    def clean(self):
        if self.vigencia_fim and self.vigencia_ini and self.vigencia_fim < self.vigencia_ini:
            raise ValidationError({'vigencia_fim': 'O fim não pode ser antes do início.'})

    def __str__(self):
        return f'{self.usuario} - {self.contrato.numero}'


class Empenho(ModeloDoMunicipio):
    """Valor empenhado para UMA finalidade, em UM centro de custo, num periodo.

    O valor pode ser liberado de uma vez ou em parcelas (LiberacaoEmpenho). Prorrogacao gera novo empenho (empenho_origem).
    """
    FINALIDADES = [('MANUTENCAO', 'Manutenção'), ('ABASTECIMENTO', 'Abastecimento')]
    # contrato de que tipo pode sustentar cada finalidade
    CONTRATO_DA_FINALIDADE = {'MANUTENCAO': 'MANUTENCAO', 'ABASTECIMENTO': 'COMBUSTIVEL'}

    finalidade = models.CharField(max_length=15, choices=FINALIDADES)
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT)
    contrato = models.ForeignKey(Contrato, null=True, blank=True, on_delete=models.PROTECT)
    empenho_origem = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT,
                                       related_name='prorrogacoes', verbose_name='Prorroga o empenho')
    numero = models.CharField('Número', max_length=30)
    exercicio = models.SmallIntegerField('Exercício')
    vigencia_ini = models.DateField('Início do período')
    vigencia_fim = models.DateField('Fim do período')
    valor_empenhado = models.DecimalField('Valor empenhado', max_digits=14, decimal_places=2,
                                          validators=[MinValueValidator(Decimal('0.01'))])
    data_empenho = models.DateField('Data do empenho', null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'empenhos'
        constraints = [
            models.UniqueConstraint(fields=['municipio', 'exercicio', 'numero'], name='uq_empenho_numero'),
            models.CheckConstraint(condition=models.Q(vigencia_fim__gte=models.F('vigencia_ini')), name='ck_empenho_vigencia'),
        ]
        ordering = ['-exercicio', 'numero']

    def clean(self):
        erros = {}
        if self.vigencia_ini and self.vigencia_fim and self.vigencia_fim < self.vigencia_ini:
            erros['vigencia_fim'] = 'O fim do período não pode ser antes do início.'
        if self.contrato_id:
            esperado = self.CONTRATO_DA_FINALIDADE.get(self.finalidade)
            if esperado and self.contrato.tipo != esperado:
                erros['contrato'] = f'Empenho de {self.get_finalidade_display().lower()} pede contrato do tipo {dict(Contrato.TIPOS)[esperado].lower()}.'
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f'{self.numero}/{self.exercicio}'


class LiberacaoEmpenho(ModeloDoMunicipio):
    """Parcela do empenho liberada para uso. Liberado de uma vez = uma liberacao com o valor total."""
    empenho = models.ForeignKey(Empenho, on_delete=models.PROTECT, related_name='liberacoes')
    data = models.DateField(default=timezone.localdate)
    valor = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    observacao = models.TextField('Observação', blank=True)
    criado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'empenho_liberacoes'
        ordering = ['data', 'id']


class LancamentoEmpenho(ModeloDoMunicipio):
    """Movimento do saldo. Gravar sempre por services.lancar() (trava e confere o saldo)."""
    TIPOS = [('RESERVA', 'Reserva'), ('CONSUMO', 'Consumo'), ('ESTORNO', 'Estorno')]

    empenho = models.ForeignKey(Empenho, on_delete=models.PROTECT, related_name='lancamentos')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    valor = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    orcamento_id = models.BigIntegerField(null=True, blank=True)       # vira FK na fase 2 (manutencao)
    abastecimento_id = models.BigIntegerField(null=True, blank=True)   # vira FK na fase 5 (abastecimento)
    observacao = models.TextField('Observação', blank=True)
    criado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'empenho_lancamentos'
        ordering = ['-criado_em', '-id']


class SaldoEmpenho(models.Model):
    """View vw_saldo_empenho (somente leitura): liberado, reservado, consumido, estornado e saldo de cada empenho."""
    empenho_id = models.BigIntegerField(primary_key=True)
    municipio_id = models.BigIntegerField()
    centro_custo_id = models.BigIntegerField()
    finalidade = models.CharField(max_length=15)
    valor_empenhado = models.DecimalField(max_digits=14, decimal_places=2)
    liberado = models.DecimalField(max_digits=14, decimal_places=2)
    reservado = models.DecimalField(max_digits=14, decimal_places=2)
    consumido = models.DecimalField(max_digits=14, decimal_places=2)
    estornado = models.DecimalField(max_digits=14, decimal_places=2)
    saldo = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'vw_saldo_empenho'
