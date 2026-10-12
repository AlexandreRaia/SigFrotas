from django import template

from apps.core import formatos

register = template.Library()


@register.filter
def moeda(valor):
    return formatos.moeda(valor)


@register.filter
def data_br(valor):
    return valor.strftime('%d/%m/%Y') if valor else ''


@register.filter
def pode(usuario, permissao):
    """{% if user|pode:'frota.ver' %}"""
    return usuario.is_authenticated and usuario.tem_permissao(permissao)


@register.filter
def pagina_de(nome_da_url, chave):
    """Verdadeiro se a url atual pertence ao item do menu (ex.: veiculos_lista e veiculos_detalhe -> 'veiculos')."""
    return bool(nome_da_url) and (nome_da_url == chave or nome_da_url.startswith(chave + '_'))


@register.filter
def cpf(valor):
    """00000000000 -> 000.000.000-00"""
    return f'{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}' if valor and len(valor) == 11 and valor.isdigit() else valor
