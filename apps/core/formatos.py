"""Formatacao para a tela (valores, datas)."""
import datetime
from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone
from django.utils.formats import number_format


def moeda(valor):
    if valor is None:
        return ''
    return 'R$ ' + number_format(valor, decimal_pos=2, force_grouping=True)


def numero(valor, casas=None):
    return '' if valor is None else number_format(valor, decimal_pos=casas, force_grouping=True)


def valor_da_coluna(objeto, atributo, tipo=None):
    """Valor de um atributo pronto para a tabela: rotulo das escolhas, datas dd/mm/aaaa, dinheiro em R$."""
    if '.' in atributo:  # 'secretaria.sigla': percorre os relacionamentos
        valor = objeto
        for parte in atributo.split('.'):
            valor = getattr(valor, parte, None) if valor is not None else None
        return '' if valor is None else valor
    try:
        campo = objeto._meta.get_field(atributo)
    except FieldDoesNotExist:
        campo = None
    if campo is not None and campo.choices:
        return getattr(objeto, f'get_{atributo}_display')()
    valor = getattr(objeto, atributo)
    if valor is None:
        return ''
    if isinstance(valor, bool):
        # so a situacao (ativo) vira selo na tabela; os demais campos verdadeiro/falso viram Sim/Nao
        return valor if atributo == 'ativo' else ('Sim' if valor else 'Não')
    if isinstance(valor, int) and tipo == 'numero':
        return numero(valor)
    if isinstance(valor, Decimal):
        return moeda(valor) if tipo == 'moeda' else numero(valor)
    if isinstance(valor, datetime.datetime):
        return timezone.localtime(valor).strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, datetime.date):
        return valor.strftime('%d/%m/%Y')
    return valor
