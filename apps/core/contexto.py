"""Requisicao em andamento, para a auditoria saber quem fez a alteracao."""
from contextvars import ContextVar

_requisicao = ContextVar('requisicao', default=None)


def definir_requisicao(request):
    return _requisicao.set(request)


def limpar_requisicao(token):
    _requisicao.reset(token)


def usuario_atual_id():
    request = _requisicao.get()
    usuario = getattr(request, 'user', None)
    if usuario is not None and usuario.is_authenticated:
        return usuario.pk
    return None
