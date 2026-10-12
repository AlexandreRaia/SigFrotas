"""Quem ve o que (regra 1): gestores veem tudo; gestor de unidade, a propria secretaria; fiscal, os seus centros de custo."""
from django.utils import timezone


def centros_do_fiscal(usuario):
    """Ids dos centros de custo do fiscal. None = todos (designado sem centro especifico)."""
    from apps.financeiro.models import FiscalContrato  # import tardio: o nucleo nao depende do financeiro na carga
    hoje = timezone.localdate()
    designacoes = FiscalContrato.objects.filter(municipio_id=usuario.municipio_id, usuario=usuario, vigencia_ini__lte=hoje)
    designacoes = [d for d in designacoes if d.vigencia_fim is None or d.vigencia_fim >= hoje]
    if any(d.centro_custo_id is None for d in designacoes):
        return None
    return {d.centro_custo_id for d in designacoes}


def restringir(usuario, queryset, *, gerir, campo_secretaria=None, campo_centro=None):
    """Limita o queryset ao que o usuario pode enxergar.

    gerir: permissao que da acesso total (ex.: 'frota.gerir'). O perfil CONSULTA tambem ve tudo (somente leitura).
    """
    codigo = usuario.perfil.codigo
    if usuario.tem_permissao(gerir) or codigo == 'CONSULTA':
        return queryset
    if codigo == 'FISCAL' and campo_centro:
        centros = centros_do_fiscal(usuario)
        return queryset if centros is None else queryset.filter(**{f'{campo_centro}__in': centros})
    if usuario.secretaria_id and campo_secretaria:
        return queryset.filter(**{campo_secretaria: usuario.secretaria_id})
    return queryset.none()
