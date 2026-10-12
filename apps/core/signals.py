"""Auditoria automatica de toda tabela de prefeitura. Operacoes em lote (bulk_*, update()) nao passam por aqui."""
import json

from django.db.models.signals import post_delete, post_save, pre_save

from . import contexto
from .models import Auditoria, ModeloDoMunicipio

CAMPOS_SECRETOS = {'password'}


def _foto(instance):
    return json.loads(json.dumps(
        {c.attname: getattr(instance, c.attname) for c in instance._meta.concrete_fields if c.attname not in CAMPOS_SECRETOS},
        default=str,
    ))


def _grava(instance, acao, antes, depois):
    Auditoria.objects.create(
        municipio_id=instance.municipio_id,
        usuario_id=contexto.usuario_atual_id(),
        tabela=instance._meta.db_table,
        registro_id=instance.pk,
        acao=acao,
        dados_antes=antes,
        dados_depois=depois,
    )


def _auditavel(instance, raw=False):
    return isinstance(instance, ModeloDoMunicipio) and not raw


def antes_de_salvar(sender, instance, raw=False, **kwargs):
    instance._auditoria_antes = None
    if _auditavel(instance, raw) and instance.pk:
        anterior = sender._base_manager.filter(pk=instance.pk).first()
        if anterior is not None:
            instance._auditoria_antes = _foto(anterior)


def depois_de_salvar(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if not _auditavel(instance, raw):
        return
    if update_fields and set(update_fields) <= {'last_login'}:  # login nao e alteracao de cadastro
        return
    _grava(instance, 'I' if created else 'U', None if created else instance._auditoria_antes, _foto(instance))


def depois_de_excluir(sender, instance, **kwargs):
    if _auditavel(instance):
        _grava(instance, 'D', _foto(instance), None)


pre_save.connect(antes_de_salvar, dispatch_uid='auditoria_pre_save')
post_save.connect(depois_de_salvar, dispatch_uid='auditoria_post_save')
post_delete.connect(depois_de_excluir, dispatch_uid='auditoria_post_delete')
