"""Regras de negocio do nucleo. Quem precisa criar prefeitura, usuario ou anexo usa estas funcoes."""
import hashlib
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Anexo, Auditoria, Municipio, Notificacao, Perfil, Sequencia, Usuario
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


def proximo_numero(municipio_id, nome, ano=None):
    """CH-2026-0001, CH-2026-0002... Contador por prefeitura, tipo e ano, travado contra numeros repetidos."""
    ano = ano or timezone.localdate().year
    with transaction.atomic():
        sequencia, _ = Sequencia.objects.select_for_update().get_or_create(municipio_id=municipio_id, nome=nome, ano=ano)
        sequencia.ultimo += 1
        sequencia.save(update_fields=['ultimo'])
    return f'{nome}-{ano}-{sequencia.ultimo:04d}'


def config_da_prefeitura(municipio_id, chave, padrao):
    """Regra da prefeitura em municipios.config (prazos, numero de aprovacoes, percentuais...)."""
    config = Municipio.objects.filter(pk=municipio_id).values_list('config', flat=True).first() or {}
    return config.get(chave, padrao)


def usuarios_com_permissao(municipio_id, permissao):
    candidatos = Usuario.objects.filter(municipio_id=municipio_id, ativo=True).select_related('perfil')
    return [u for u in candidatos if u.tem_permissao(permissao)]


def notificar(usuarios, assunto, corpo='', *, link='', entidade='', entidade_id=None, exceto=None, sem_repetir=False):
    """Avisa cada usuario no sistema e, se a prefeitura nao desligou (config 'email_notificacoes'), na fila de e-mail.

    O e-mail so sai quando roda `manage.py enviar_notificacoes` (a cada minuto no servidor). `exceto`: quem fez a acao.
    `sem_repetir`: nao cria outro aviso se o usuario ja tem um nao lido sobre a mesma entidade (ex.: varias mensagens do chat).
    """
    vistos = set()
    for usuario in usuarios:
        if usuario is None or not usuario.ativo or usuario.pk in vistos or (exceto is not None and usuario.pk == exceto.pk):
            continue
        vistos.add(usuario.pk)
        if sem_repetir and Notificacao.objects.filter(usuario=usuario, canal='APP', entidade=entidade, entidade_id=entidade_id,
                                                      assunto=assunto).exclude(status='LIDA').exists():
            continue
        comuns = dict(municipio_id=usuario.municipio_id, usuario=usuario, assunto=assunto, corpo=corpo, link=link,
                      entidade=entidade, entidade_id=entidade_id)
        Notificacao.objects.create(canal='APP', **comuns)
        if usuario.email and config_da_prefeitura(usuario.municipio_id, 'email_notificacoes', True):
            Notificacao.objects.create(canal='EMAIL', email_destino=usuario.email, **comuns)


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
