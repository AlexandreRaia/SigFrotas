"""Motoristas, certificados, penalidades e afastamentos (ver docs/schema_frota_v2.sql).

LGPD: CPF, RG, endereco, CNH e contato sao dados pessoais (Motorista.CAMPOS_PESSOAIS): so aparecem para quem tem
'pessoas.dados_pessoais' e cada consulta da ficha completa grava auditoria (acao 'C').
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import ModeloDoMunicipio, Secretaria, Unidade, Usuario
from apps.frota.models import CNH_CATEGORIAS


class Motorista(ModeloDoMunicipio):
    SITUACOES = [('ATIVO', 'Ativo'), ('SUSPENSO', 'Suspenso'), ('INATIVO', 'Inativo')]
    # campos que so quem tem 'pessoas.dados_pessoais' enxerga
    CAMPOS_PESSOAIS = ('cpf', 'rg', 'rg_emissor', 'data_nascimento', 'telefone', 'email', 'endereco', 'cep',
                       'cnh_numero', 'cnh_emissao', 'cnh_orgao')

    usuario = models.OneToOneField(Usuario, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Usuário de acesso')
    secretaria = models.ForeignKey(Secretaria, null=True, blank=True, on_delete=models.PROTECT)
    unidade = models.ForeignKey(Unidade, null=True, blank=True, on_delete=models.PROTECT)
    prontuario = models.CharField('Prontuário', max_length=20)
    nome = models.TextField()
    cpf = models.CharField('CPF', max_length=11)
    rg = models.CharField('RG', max_length=20, blank=True)
    rg_emissor = models.CharField('Órgão emissor do RG', max_length=20, blank=True)
    data_nascimento = models.DateField('Data de nascimento', null=True, blank=True)
    cargo = models.CharField(max_length=80, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField('E-mail', blank=True)
    endereco = models.TextField('Endereço', blank=True)
    cep = models.CharField('CEP', max_length=8, blank=True)
    cnh_numero = models.CharField('Número da CNH', max_length=11, blank=True)
    cnh_categoria = models.CharField('Categoria da CNH', max_length=5, blank=True, choices=CNH_CATEGORIAS)
    cnh_emissao = models.DateField('Emissão da CNH', null=True, blank=True)
    cnh_validade = models.DateField('Validade da CNH', null=True, blank=True)
    cnh_orgao = models.CharField('Órgão da CNH', max_length=20, blank=True)
    situacao = models.CharField('Situação', max_length=10, default='ATIVO', choices=SITUACOES)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'motoristas'
        constraints = [
            models.UniqueConstraint(fields=['municipio', 'prontuario'], name='uq_motorista_prontuario'),
            models.UniqueConstraint(fields=['municipio', 'cpf'], name='uq_motorista_cpf'),
        ]
        ordering = ['nome']

    def clean(self):
        if self.unidade_id and self.secretaria_id and self.unidade.secretaria_id != self.secretaria_id:
            raise ValidationError({'unidade': 'A unidade não pertence à secretaria escolhida.'})
        if self.cnh_emissao and self.cnh_validade and self.cnh_validade < self.cnh_emissao:
            raise ValidationError({'cnh_validade': 'A validade não pode ser antes da emissão.'})

    @property
    def cnh_status(self):
        """Situacao operacional da CNH (nao e dado pessoal): Vencida, Vence em N dias, Em dia ou Sem CNH."""
        if not self.cnh_validade:
            return 'Sem CNH'
        dias = (self.cnh_validade - timezone.localdate()).days
        if dias < 0:
            return 'Vencida'
        return f'Vence em {dias} dias' if dias <= 30 else 'Em dia'

    def __str__(self):
        return f'{self.prontuario} - {self.nome}'


class MotoristaCertificado(ModeloDoMunicipio):
    motorista = models.ForeignKey(Motorista, on_delete=models.CASCADE, related_name='certificados')
    curso = models.TextField()
    instituicao = models.TextField('Instituição', blank=True)
    realizado_em = models.DateField('Realizado em', null=True, blank=True)
    validade = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'motorista_certificados'
        ordering = ['-realizado_em', '-id']


class MotoristaPenalidade(ModeloDoMunicipio):
    """Registro disciplinar: dado sensivel, so quem tem 'pessoas.dados_pessoais' enxerga. Nao se apaga."""
    motorista = models.ForeignKey(Motorista, on_delete=models.CASCADE, related_name='penalidades')
    descricao = models.TextField('Descrição')
    penalidade = models.TextField('Penalidade aplicada', blank=True)
    aplicada_em = models.DateField('Aplicada em', null=True, blank=True)

    class Meta:
        db_table = 'motorista_penalidades'
        ordering = ['-aplicada_em', '-id']


class MotoristaAfastamento(ModeloDoMunicipio):
    """Ferias, folgas e licencas (sem detalhar o motivo)."""
    TIPOS = [('FERIAS', 'Férias'), ('FOLGA', 'Folga'), ('LICENCA', 'Licença'), ('OUTRO', 'Outro')]

    motorista = models.ForeignKey(Motorista, on_delete=models.CASCADE, related_name='afastamentos')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    inicio = models.DateField('Início')
    fim = models.DateField()

    class Meta:
        db_table = 'motorista_afastamentos'
        constraints = [models.CheckConstraint(condition=models.Q(fim__gte=models.F('inicio')), name='ck_afastamento_periodo')]
        ordering = ['-inicio', '-id']

    def clean(self):
        if self.inicio and self.fim and self.fim < self.inicio:
            raise ValidationError({'fim': 'O fim não pode ser antes do início.'})
