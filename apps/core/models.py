"""Nucleo: prefeitura, estrutura organizacional, acesso, anexos e auditoria (ver docs/schema_frota_v2.sql)."""
from pathlib import Path
from uuid import uuid4

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from .campos import EmailInsensivel
from .permissoes import IMPLICADA_POR


class Municipio(models.Model):
    """Prefeitura. Unica tabela de negocio fora da RLS (nao tem municipio_id)."""
    nome = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)  # identifica a prefeitura no login
    uf = models.CharField(max_length=2)
    cnpj = models.CharField(max_length=14, unique=True)
    codigo_ibge = models.CharField(max_length=7, blank=True)
    config = models.JSONField(default=dict, blank=True)  # regras da prefeitura (prazos, aprovacoes...)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'municipios'

    def __str__(self):
        return self.nome


class ModeloDoMunicipio(models.Model):
    """Base de toda tabela de negocio: pertence a uma prefeitura."""
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT)

    class Meta:
        abstract = True

    def validar_mesmo_municipio(self):
        """FK do banco nao garante que os registros sejam da mesma prefeitura: confere aqui."""
        for campo in self._meta.concrete_fields:
            if not campo.many_to_one or campo.name == 'municipio':
                continue
            alvo = campo.related_model
            valor = getattr(self, campo.attname)
            if valor is None or not any(f.name == 'municipio' for f in alvo._meta.fields):
                continue
            if not alvo._base_manager.filter(pk=valor, municipio_id=self.municipio_id).exists():
                raise ValidationError(f'{campo.verbose_name}: registro inexistente ou de outra prefeitura.')

    def save(self, *args, **kwargs):
        self.validar_mesmo_municipio()
        super().save(*args, **kwargs)


class Secretaria(ModeloDoMunicipio):
    sigla = models.CharField(max_length=20)
    nome = models.TextField()
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'secretarias'
        constraints = [models.UniqueConstraint(fields=['municipio', 'sigla'], name='uq_secretaria_sigla')]
        ordering = ['sigla']

    def __str__(self):
        return f'{self.sigla} - {self.nome}'


class Unidade(ModeloDoMunicipio):
    """Divisao dentro da secretaria."""
    secretaria = models.ForeignKey(Secretaria, on_delete=models.PROTECT)
    nome = models.TextField()
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'unidades'
        constraints = [models.UniqueConstraint(fields=['secretaria', 'nome'], name='uq_unidade_nome')]
        ordering = ['secretaria__sigla', 'nome']

    def __str__(self):
        return self.nome


class CentroCusto(ModeloDoMunicipio):
    secretaria = models.ForeignKey(Secretaria, null=True, blank=True, on_delete=models.PROTECT)
    codigo = models.CharField(max_length=30)
    nome = models.TextField()
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'centros_custo'
        constraints = [models.UniqueConstraint(fields=['municipio', 'codigo'], name='uq_centro_custo_codigo')]
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class Perfil(ModeloDoMunicipio):
    """Os 8 perfis sao fixos (ver permissoes.py) e criados junto com a prefeitura."""
    codigo = models.CharField(max_length=30)
    nome = models.CharField(max_length=60)
    permissoes = models.JSONField(default=list)

    class Meta:
        db_table = 'perfis'
        constraints = [models.UniqueConstraint(fields=['municipio', 'codigo'], name='uq_perfil_codigo')]
        ordering = ['nome']

    def __str__(self):
        return self.nome


class UsuarioManager(BaseUserManager):
    def create_user(self, municipio, email, nome, perfil, password, **extras):
        usuario = self.model(municipio=municipio, email=self.normalize_email(email), nome=nome, perfil=perfil, **extras)
        usuario.set_password(password)
        usuario.save()
        return usuario


class Usuario(AbstractBaseUser, ModeloDoMunicipio):
    perfil = models.ForeignKey(Perfil, on_delete=models.PROTECT)
    secretaria = models.ForeignKey(Secretaria, null=True, blank=True, on_delete=models.PROTECT)
    unidade = models.ForeignKey(Unidade, null=True, blank=True, on_delete=models.PROTECT)
    fornecedor = models.ForeignKey('financeiro.Fornecedor', null=True, blank=True, on_delete=models.PROTECT)  # usuario de oficina
    nome = models.TextField()
    email = EmailInsensivel()
    cpf = models.CharField(max_length=11, blank=True)
    matricula = models.CharField(max_length=20, blank=True)
    password = models.CharField(max_length=128, db_column='senha_hash')
    last_login = models.DateTimeField(null=True, blank=True, db_column='ultimo_login')
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nome']
    objects = UsuarioManager()

    class Meta:
        db_table = 'usuarios'
        constraints = [models.UniqueConstraint(fields=['municipio', 'email'], name='uq_usuario_email')]
        ordering = ['nome']

    @property
    def is_active(self):
        return self.ativo

    def tem_permissao(self, permissao):
        if not self.ativo:
            return False
        permissoes = self.perfil.permissoes
        if permissao in permissoes:
            return True
        if permissao.endswith('.ver'):  # "x.gerir" inclui "x.ver" (e as implicacoes de permissoes.IMPLICADA_POR)
            return any(p in permissoes for p in (permissao[:-4] + '.gerir', *IMPLICADA_POR.get(permissao, ())))
        return False

    def __str__(self):
        return self.nome


def caminho_anexo(instance, filename):
    # Nome gerado pelo sistema: o nome original fica so no banco.
    return f'{instance.municipio_id}/{instance.entidade}/{instance.entidade_id}/{uuid4().hex}{Path(filename).suffix.lower()[:10]}'


class Anexo(ModeloDoMunicipio):
    """Fotos, audios, videos e PDFs ligados a qualquer registro (entidade + entidade_id)."""
    entidade = models.CharField(max_length=40)
    entidade_id = models.BigIntegerField()
    categoria = models.CharField(max_length=20, blank=True)
    nome_arquivo = models.TextField()
    mime_type = models.CharField(max_length=100, blank=True)
    tamanho_bytes = models.BigIntegerField(null=True)
    arquivo = models.FileField(upload_to=caminho_anexo, max_length=300, db_column='storage_path')
    hash_sha256 = models.CharField(max_length=64, blank=True)
    enviado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'anexos'
        indexes = [models.Index(fields=['municipio', 'entidade', 'entidade_id'], name='ix_anexos_entidade')]

    def __str__(self):
        return self.nome_arquivo


class Sequencia(ModeloDoMunicipio):
    """Contador por prefeitura, tipo e ano (CH-2026-0001). Use services.proximo_numero()."""
    sem_auditoria = True

    nome = models.CharField(max_length=20)
    ano = models.SmallIntegerField()
    ultimo = models.IntegerField(default=0)

    class Meta:
        db_table = 'sequencias'
        constraints = [models.UniqueConstraint(fields=['municipio', 'nome', 'ano'], name='uq_sequencia')]


class Notificacao(ModeloDoMunicipio):
    """Aviso dentro do sistema (APP) ou e-mail na fila (EMAIL). Criar sempre por services.notificar()."""
    sem_auditoria = True
    CANAIS = [('EMAIL', 'E-mail'), ('APP', 'No sistema')]
    STATUS = [('PENDENTE', 'Pendente'), ('ENVIADA', 'Enviada'), ('ERRO', 'Erro'), ('LIDA', 'Lida')]

    usuario = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.CASCADE, related_name='notificacoes')
    email_destino = models.EmailField(blank=True)
    canal = models.CharField(max_length=6, choices=CANAIS, default='APP')
    assunto = models.TextField()
    corpo = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)   # pagina que a notificacao abre (caminho dentro do sistema)
    entidade = models.CharField(max_length=40, blank=True)  # ex.: smv, chamados, empenhos
    entidade_id = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default='PENDENTE')
    criado_em = models.DateTimeField(auto_now_add=True)
    enviada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notificacoes'
        indexes = [models.Index(fields=['municipio', 'status'], name='ix_notificacoes_status')]
        ordering = ['-criado_em', '-id']


class Auditoria(models.Model):
    """Quem, quando, antes e depois. Sem FK de proposito: o rastro deve sobreviver ao registro."""
    municipio_id = models.BigIntegerField()
    usuario_id = models.BigIntegerField(null=True)
    tabela = models.TextField()
    registro_id = models.BigIntegerField(null=True)
    acao = models.CharField(max_length=1, choices=[('I', 'Inclusão'), ('U', 'Alteração'), ('D', 'Exclusão'),
                                                   ('C', 'Consulta')])  # consulta a dado pessoal (LGPD)
    dados_antes = models.JSONField(null=True)
    dados_depois = models.JSONField(null=True)
    em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'auditoria'
        indexes = [models.Index(fields=['municipio_id', 'tabela', 'registro_id'], name='ix_auditoria_registro')]
        ordering = ['-em', '-id']
