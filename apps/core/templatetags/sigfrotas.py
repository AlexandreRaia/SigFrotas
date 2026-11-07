import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from apps.core import formatos

register = template.Library()


@register.simple_tag
def estatico_versionado(caminho):
    """URL do arquivo estatico com ?v=<data de alteracao>: quando o CSS e regerado, o navegador baixa o novo."""
    arquivo = finders.find(caminho)
    versao = int(os.path.getmtime(arquivo)) if arquivo else 0
    return f'{static(caminho)}?v={versao}'


@register.filter
def moeda(valor):
    return formatos.moeda(valor)


@register.filter
def data_br(valor):
    return valor.strftime('%d/%m/%Y') if valor else ''


@register.filter
def item(dicionario, chave):
    """{{ enviados|item:campo.name }}: valor do dicionario (vazio se nao tiver)."""
    return (dicionario or {}).get(chave, ())


@register.filter
def pode(usuario, permissao):
    """{% if user|pode:'frota.ver' %}"""
    return usuario.is_authenticated and usuario.tem_permissao(permissao)


@register.filter
def iniciais(usuario):
    """Alexandre Raia -> AR (primeira letra do primeiro e do ultimo nome); nome unico -> as duas primeiras letras."""
    partes = (getattr(usuario, 'nome', '') or '').split()
    if not partes:
        return '?'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@register.filter
def pagina_de(nome_da_url, chave):
    """Verdadeiro se a url atual pertence ao item do menu (ex.: veiculos_lista e veiculos_detalhe -> 'veiculos')."""
    return bool(nome_da_url) and (nome_da_url == chave or nome_da_url.startswith(chave + '_'))


@register.filter
def cpf(valor):
    """00000000000 -> 000.000.000-00"""
    return f'{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}' if valor and len(valor) == 11 and valor.isdigit() else valor

SELOS = {
    'selo-ativo': {'APROVADO', 'CONCLUIDA', 'GEROU_SMV', 'ENVIADA', 'DISPONIVEL', 'EM_USO', 'RESERVA', 'ATIVO'},
    'selo-erro': {'REPROVADO', 'IMPROCEDENTE', 'CANCELADA', 'CANCELADO', 'URGENTE'},
    'selo-aviso': {'REVISAO', 'ALTA', 'NOTA_FISCAL', 'MANUTENCAO'},
    'selo-info': {'ABERTO', 'EM_ANALISE', 'RECEBIDO', 'DIAGNOSTICO', 'ORCAMENTO', 'EXECUCAO', 'ENTREGA', 'ENTRADA', 'RASCUNHO'},
}


@register.filter
def paginas_proximas(pagina):
    """Ate 5 numeros de pagina em volta da atual (como o paginador da tabela de veiculos)."""
    total = pagina.paginator.num_pages
    inicio = max(1, min(pagina.number - 2, total - 4))
    return range(inicio, min(total, inicio + 4) + 1)


@register.filter
def selo(codigo):
    """Classe do selo colorido de uma situacao (APROVADO -> verde, REPROVADO -> vermelho...). {{ obj.status|selo }}"""
    for classe, codigos in SELOS.items():
        if codigo in codigos:
            return classe
    return 'selo-inativo'