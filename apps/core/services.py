"""Regras de negocio do nucleo. Quem precisa criar prefeitura, usuario ou anexo usa estas funcoes."""
import hashlib
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Anexo, Municipio, Perfil, Usuario
from .permissoes import PERFIS_PADRAO
from .tenant import com_municipio


def criar_municipio(*, nome, slug, uf, cnpj, codigo_ibge=''):
    """Cria a prefeitura e seus 8 perfis fixos."""
    with transaction.atomic():
        municipio = Municipio.objects.create(nome=nome, slug=slug, uf=uf.upper(), cnpj=cnpj, codigo_ibge=codigo_ibge)
        with com_municipio(municipio.id):
            for codigo, (nome_perfil, permissoes) in PERFIS_PADRAO.items():
                Perfil.objects.create(municipio=municipio, codigo=codigo, nome=nome_perfil, permissoes=permissoes)
    return municipio


def criar_usuario(*, municipio, perfil_codigo, nome, email, senha, **extras):
    with com_municipio(municipio.id):
        perfil = Perfil.objects.get(municipio=municipio, codigo=perfil_codigo)
        return Usuario.objects.create_user(municipio, email, nome, perfil, senha, **extras)


def anexar(*, municipio_id, entidade, entidade_id, arquivo, categoria='', enviado_por=None):
    """Guarda o arquivo no armazenamento e registra hash, tamanho e tipo."""
    if arquivo.size > settings.ANEXO_TAMANHO_MAXIMO:
        raise ValidationError('Arquivo maior que o limite permitido.')
    sha = hashlib.sha256()
    for parte in arquivo.chunks():
        sha.update(parte)
    anexo = Anexo(
        municipio_id=municipio_id,
        entidade=entidade,
        entidade_id=entidade_id,
        categoria=categoria,
        nome_arquivo=arquivo.name,
        mime_type=getattr(arquivo, 'content_type', None) or mimetypes.guess_type(arquivo.name)[0] or '',
        tamanho_bytes=arquivo.size,
        hash_sha256=sha.hexdigest(),
        enviado_por=enviado_por,
    )
    anexo.arquivo.save(arquivo.name, arquivo, save=False)
    anexo.save()
    return anexo
