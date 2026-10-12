"""Ajudantes para telas que usam HTMX: o servidor devolve so o trecho que mudou."""
import json

from django.http import HttpResponse
from django.utils.cache import patch_vary_headers


def e_htmx(request):
    """Requisicao HTMX que quer so um trecho. Voltar no historico do navegador pede a pagina inteira."""
    cabecalhos = request.headers
    return cabecalhos.get('HX-Request') == 'true' and cabecalhos.get('HX-History-Restore-Request') != 'true'


def redirecionar(url):
    """Manda o navegador para outra pagina (um 302 comum seria seguido dentro do trecho)."""
    return HttpResponse(status=204, headers={'HX-Redirect': url})


def com_mensagem(resposta, texto, tipo='success'):
    """Mostra um aviso na tela sem recarregar (tipo: success ou error)."""
    resposta['HX-Trigger'] = json.dumps({'mensagem': {'texto': texto, 'tipo': tipo}})
    return resposta


class ParcialMixin:
    """Se a requisicao e HTMX, usa o template parcial em vez da pagina inteira."""
    template_parcial = None

    def get_template_names(self):
        if self.template_parcial and e_htmx(self.request):
            return [self.template_parcial]
        return super().get_template_names()

    def dispatch(self, request, *args, **kwargs):
        resposta = super().dispatch(request, *args, **kwargs)
        patch_vary_headers(resposta, ['HX-Request'])  # mesma URL, conteudo diferente: o cache precisa saber
        return resposta
