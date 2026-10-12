"""Veiculos, catalogos, lotacoes e leituras de km/horimetro (ver docs/schema_frota_v2.sql)."""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import CentroCusto, ModeloDoMunicipio, Secretaria, Unidade
from apps.financeiro.models import Contrato

CNH_CATEGORIAS = [(c, c) for c in ('A', 'B', 'C', 'D', 'E', 'AB', 'AC', 'AD', 'AE')]


# --- Catalogos globais (sem municipio_id): compartilhados por todas as prefeituras; so se acrescenta ------------

class Marca(models.Model):
    nome = models.CharField(max_length=100)

    class Meta:
        db_table = 'marcas'
        constraints = [models.UniqueConstraint(Lower('nome'), name='uq_marca_nome')]
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Modelo(models.Model):
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name='modelos')
    nome = models.CharField(max_length=100)

    class Meta:
        db_table = 'modelos'
        constraints = [models.UniqueConstraint(Lower('nome'), 'marca', name='uq_modelo_nome')]
        ordering = ['marca__nome', 'nome']

    def __str__(self):
        return f'{self.marca.nome} {self.nome}'


class Combustivel(models.Model):
    nome = models.CharField(max_length=30, unique=True)

    class Meta:
        db_table = 'combustiveis'
        ordering = ['nome']

    def __str__(self):
        return self.nome


# --- Cadastros da prefeitura -------------------------------------------------------------------------------------

class CategoriaVeiculo(ModeloDoMunicipio):
    """Automovel, caminhao, onibus, moto, maquina... Define a CNH minima e se o veiculo usa horimetro."""
    nome = models.CharField(max_length=60)
    cnh_minima = models.CharField('CNH mínima', max_length=5, blank=True, choices=CNH_CATEGORIAS)
    usa_horimetro = models.BooleanField('Usa horímetro (máquinas)', default=False)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = 'categorias_veiculo'
        constraints = [models.UniqueConstraint(fields=['municipio', 'nome'], name='uq_categoria_veiculo_nome')]
        ordering = ['nome']
        verbose_name = 'categoria de veículo'

    def __str__(self):
        return self.nome


PLACA = re.compile(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$')           # antiga (ABC1234) e Mercosul (ABC1D23)
CHASSI = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')                    # 17 caracteres, sem I, O e Q


def normalizar_placa(valor):
    return re.sub(r'[\s-]', '', valor or '').upper()


class Veiculo(ModeloDoMunicipio):
    ESTADOS = [('BOM', 'Bom'), ('REGULAR', 'Regular'), ('RUIM', 'Ruim'), ('PESSIMO', 'Péssimo')]
    SITUACOES = [('DISPONIVEL', 'Disponível'), ('EM_USO', 'Em uso'), ('MANUTENCAO', 'Em manutenção'),
                 ('RESERVA', 'Reserva'), ('INATIVO', 'Inativo'), ('BAIXADO', 'Baixado')]
    TIPOS_FROTA = [('PROPRIO', 'Próprio'), ('LOCADO', 'Locado'), ('ESTADUAL', 'Estadual'), ('DOACAO', 'Doação'),
                   ('CEDIDO', 'Cedido')]
    TRANSMISSOES = [('MANUAL', 'Manual'), ('AUTOMATICA', 'Automática'), ('AUTOMATIZADA', 'Automatizada'), ('CVT', 'CVT')]

    secretaria = models.ForeignKey(Secretaria, null=True, blank=True, on_delete=models.PROTECT)
    unidade = models.ForeignKey(Unidade, null=True, blank=True, on_delete=models.PROTECT)
    centro_custo = models.ForeignKey(CentroCusto, null=True, blank=True, on_delete=models.PROTECT)
    categoria = models.ForeignKey(CategoriaVeiculo, null=True, blank=True, on_delete=models.PROTECT)
    modelo = models.ForeignKey(Modelo, null=True, blank=True, on_delete=models.PROTECT)
    combustivel = models.ForeignKey(Combustivel, null=True, blank=True, on_delete=models.PROTECT)
    placa = models.CharField(max_length=8)
    prefixo = models.CharField(max_length=20, blank=True)
    patrimonio = models.CharField('Patrimônio', max_length=30, blank=True)
    renavam = models.CharField('RENAVAM', max_length=11, blank=True)
    chassi = models.CharField(max_length=17, blank=True)
    ano_fabricacao = models.SmallIntegerField('Ano de fabricação', null=True, blank=True)
    ano_modelo = models.SmallIntegerField('Ano do modelo', null=True, blank=True)
    cor = models.CharField(max_length=30, blank=True)
    motor = models.CharField(max_length=60, blank=True)
    transmissao = models.CharField('Transmissão', max_length=20, blank=True, choices=TRANSMISSOES)
    capacidade_tanque = models.DecimalField('Capacidade do tanque (litros)', max_digits=6, decimal_places=2, null=True, blank=True)
    consumo_referencia = models.DecimalField('Consumo de referência (km/l)', max_digits=5, decimal_places=2, null=True, blank=True)
    capacidade_passageiros = models.SmallIntegerField('Passageiros', null=True, blank=True)
    odometro_atual = models.IntegerField('Km atual', default=0, validators=[MinValueValidator(0)])  # so muda por leitura
    horimetro_atual = models.DecimalField('Horímetro atual', max_digits=10, decimal_places=1, null=True, blank=True)
    km_entrada = models.IntegerField('Km ao entrar na frota', null=True, blank=True)
    estado_conservacao = models.CharField('Estado de conservação', max_length=10, blank=True, choices=ESTADOS)
    situacao = models.CharField('Situação', max_length=15, default='DISPONIVEL', choices=SITUACOES)
    tipo_frota = models.CharField('Tipo de frota', max_length=10, default='PROPRIO', choices=TIPOS_FROTA)
    proprietario = models.TextField('Proprietário (locadora ou órgão)', blank=True)
    contrato_locacao = models.ForeignKey(Contrato, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Contrato de locação')
    valor_fipe = models.DecimalField('Valor FIPE', max_digits=14, decimal_places=2, null=True, blank=True)
    valor_aquisicao = models.DecimalField('Valor de aquisição', max_digits=14, decimal_places=2, null=True, blank=True)
    valor_aluguel_mensal = models.DecimalField('Aluguel mensal', max_digits=14, decimal_places=2, null=True, blank=True)
    data_aquisicao = models.DateField('Data de aquisição', null=True, blank=True)
    data_baixa = models.DateField('Data da baixa', null=True, blank=True)
    motivo_baixa = models.TextField('Motivo da baixa', blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'veiculos'
        constraints = [models.UniqueConstraint(fields=['municipio', 'placa'], name='uq_veiculo_placa')]
        ordering = ['placa']

    def clean(self):
        self.placa = normalizar_placa(self.placa)
        erros = {}
        if not PLACA.match(self.placa):
            erros['placa'] = 'Placa inválida. Use o formato ABC1234 ou ABC1D23.'
        self.chassi = (self.chassi or '').upper().strip()
        if self.chassi and not CHASSI.match(self.chassi):
            erros['chassi'] = 'O chassi tem 17 letras e números (sem I, O e Q).'
        if self.renavam and not re.match(r'^\d{9,11}$', self.renavam):
            erros['renavam'] = 'O RENAVAM tem de 9 a 11 números.'
        if self.unidade_id and self.secretaria_id and self.unidade.secretaria_id != self.secretaria_id:
            erros['unidade'] = 'A unidade não pertence à secretaria escolhida.'
        if self.situacao == 'BAIXADO':
            if not self.data_baixa:
                erros['data_baixa'] = 'Informe a data da baixa.'
            if not self.motivo_baixa:
                erros['motivo_baixa'] = 'Informe o motivo da baixa.'
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.placa = normalizar_placa(self.placa)
        super().save(*args, **kwargs)

    @property
    def usa_horimetro(self):
        return bool(self.categoria_id and self.categoria.usa_horimetro)

    def __str__(self):
        return f'{self.placa}' + (f' ({self.prefixo})' if self.prefixo else '')


class VeiculoEquipamento(ModeloDoMunicipio):
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name='equipamentos')
    descricao = models.CharField('Descrição', max_length=100)
    observacao = models.TextField('Observação', blank=True)

    class Meta:
        db_table = 'veiculo_equipamentos'
        ordering = ['descricao']


class VeiculoLotacao(ModeloDoMunicipio):
    """Historico de secretaria/unidade/centro de custo do veiculo (fim vazio = lotacao atual)."""
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name='lotacoes')
    secretaria = models.ForeignKey(Secretaria, null=True, blank=True, on_delete=models.PROTECT)
    unidade = models.ForeignKey(Unidade, null=True, blank=True, on_delete=models.PROTECT)
    centro_custo = models.ForeignKey(CentroCusto, null=True, blank=True, on_delete=models.PROTECT)
    inicio = models.DateField(default=timezone.localdate)
    fim = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'veiculo_lotacoes'
        ordering = ['-inicio', '-id']


class LeituraVeiculo(ModeloDoMunicipio):
    """Fonte unica de km/horimetro. Nunca se altera nem se apaga; o km nao diminui (services.registrar_leitura)."""
    ORIGENS = [('FICHA', 'Ficha de tráfego'), ('ABASTECIMENTO', 'Abastecimento'), ('SMV', 'Manutenção'),
               ('CHECKLIST', 'Checklist'), ('MANUAL', 'Manual')]

    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name='leituras')
    odometro = models.IntegerField(null=True, blank=True)
    horimetro = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)
    lido_em = models.DateTimeField(default=timezone.now)
    origem = models.CharField(max_length=20, choices=ORIGENS)
    origem_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'leituras_veiculo'
        ordering = ['-lido_em', '-id']
