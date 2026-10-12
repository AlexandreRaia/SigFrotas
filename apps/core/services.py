"""Regras de negocio do nucleo. Quem precisa criar prefeitura, usuario ou anexo usa estas funcoes."""
import hashlib
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Anexo, Auditoria, Municipio, Perfil, Usuario
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


def sincronizar_perfis(municipio):
    """Acrescenta ao perfil as permissoes novas de PERFIS_PADRAO (cria perfil que falte). Nunca remove permissao.

    Devolve {codigo: [permissoes acrescentadas]}. Roda a cada atualizacao do sistema (entrypoint) e depois de criar modulos.
    """
    acrescentadas = {}
    with com_municipio(municipio.id):
        for codigo, (nome, permissoes) in PERFIS_PADRAO.items():
            perfil = Perfil.objects.filter(municipio=municipio, codigo=codigo).first()
            if perfil is None:
                Perfil.objects.create(municipio=municipio, codigo=codigo, nome=nome, permissoes=list(permissoes))
                acrescentadas[codigo] = list(permissoes)
                continue
            faltando = [p for p in permissoes if p not in perfil.permissoes]
            if faltando:
                perfil.permissoes = perfil.permissoes + faltando
                perfil.save()
                acrescentadas[codigo] = faltando
    return acrescentadas


def criar_usuario(*, municipio, perfil_codigo, nome, email, senha, **extras):
    with com_municipio(municipio.id):
        perfil = Perfil.objects.get(municipio=municipio, codigo=perfil_codigo)
        return Usuario.objects.create_user(municipio, email, nome, perfil, senha, **extras)


def registrar_consulta(*, usuario, objeto, detalhe=''):
    """LGPD: grava na auditoria que o usuario consultou dados pessoais deste registro (acao 'C')."""
    return Auditoria.objects.create(
        municipio_id=objeto.municipio_id, usuario_id=usuario.pk, tabela=objeto._meta.db_table, registro_id=objeto.pk,
        acao='C', dados_depois={'detalhe': detalhe} if detalhe else None)


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
