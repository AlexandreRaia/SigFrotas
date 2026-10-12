from django.db import transaction

from . import contexto
from .tenant import definir_municipio


class PrefeituraMiddleware:
    """Envolve cada requisicao numa transacao com app.municipio_id definido (vem da sessao).

    Fica antes da autenticacao porque a propria tabela de usuarios esta sob RLS.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = contexto.definir_requisicao(request)
        try:
            with transaction.atomic():
                definir_municipio(request.session.get('municipio_id'))
                return self.get_response(request)
        finally:
            contexto.limpar_requisicao(token)
