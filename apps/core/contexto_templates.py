from .models import Notificacao


def notificacoes(request):
    """Quantas notificacoes nao lidas o usuario tem (o sino do cabecalho)."""
    usuario = getattr(request, 'user', None)
    if usuario is None or not usuario.is_authenticated:
        return {}
    total = Notificacao.objects.filter(usuario=usuario, canal='APP').exclude(status='LIDA').count()
    return {'notificacoes_nao_lidas': total}
