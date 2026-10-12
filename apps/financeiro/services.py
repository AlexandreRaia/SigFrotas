"""Saldo de empenho. Regra 7: orcamento so e aprovado com saldo; reserva na aprovacao, consumo na nota conferida.

saldo = liberado - reservado - consumido + estornado (view vw_saldo_empenho).
Toda gravacao passa por aqui: o empenho e travado (select_for_update) para duas operacoes simultaneas nao gastarem o mesmo saldo.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.formatos import moeda

from .models import Empenho, LancamentoEmpenho, LiberacaoEmpenho, SaldoEmpenho


class SaldoInsuficiente(ValidationError):
    pass


def saldo_do_empenho(empenho):
    return SaldoEmpenho.objects.get(empenho_id=empenho.pk)


def _travar(empenho):
    return Empenho.objects.select_for_update().get(pk=empenho.pk, municipio_id=empenho.municipio_id)


def _conferir_valor(valor):
    if valor is None or Decimal(valor) <= 0:
        raise ValidationError('O valor deve ser maior que zero.')


@transaction.atomic
def criar_empenho(*, liberar_total=False, usuario=None, **dados):
    """Cria o empenho. liberar_total=True: ja libera o valor inteiro (liberado de uma vez)."""
    empenho = Empenho(**dados)
    empenho.full_clean(exclude=['municipio'])
    empenho.save()
    if liberar_total:
        liberar(empenho=empenho, valor=empenho.valor_empenhado, data=empenho.data_empenho or timezone.localdate(),
                observacao='Liberação do valor total.', usuario=usuario)
    return empenho


@transaction.atomic
def liberar(*, empenho, valor, data=None, observacao='', usuario=None):
    """Libera parte do valor empenhado para uso (parcelas). Nao pode passar do valor empenhado."""
    _conferir_valor(valor)
    empenho = _travar(empenho)
    if not empenho.ativo:
        raise ValidationError('Empenho inativo.')
    atual = saldo_do_empenho(empenho)
    if atual.liberado + valor > empenho.valor_empenhado:
        raise ValidationError(f'A liberação passaria do valor empenhado. Ainda é possível liberar {moeda(empenho.valor_empenhado - atual.liberado)}.')
    return LiberacaoEmpenho.objects.create(
        municipio_id=empenho.municipio_id, empenho=empenho, valor=valor, data=data or timezone.localdate(),
        observacao=observacao, criado_por=usuario)


@transaction.atomic
def lancar(*, empenho, tipo, valor, usuario=None, orcamento_id=None, abastecimento_id=None, observacao=''):
    """Reserva (aprovacao do orcamento), consumo (nota conferida / abastecimento) ou estorno.

    RESERVA e CONSUMO exigem saldo; ESTORNO nao pode passar do que ja foi reservado + consumido.
    """
    _conferir_valor(valor)
    empenho = _travar(empenho)
    if not empenho.ativo:
        raise ValidationError('Empenho inativo.')
    atual = saldo_do_empenho(empenho)
    if tipo in ('RESERVA', 'CONSUMO'):
        if valor > atual.saldo:
            raise SaldoInsuficiente(f'Saldo insuficiente: disponível {moeda(atual.saldo)}, necessário {moeda(valor)}.')
    elif tipo == 'ESTORNO':
        if atual.estornado + valor > atual.reservado + atual.consumido:
            raise ValidationError('O estorno é maior que o valor reservado e consumido.')
    else:
        raise ValidationError('Tipo de lançamento inválido.')
    return LancamentoEmpenho.objects.create(
        municipio_id=empenho.municipio_id, empenho=empenho, tipo=tipo, valor=valor, orcamento_id=orcamento_id,
        abastecimento_id=abastecimento_id, observacao=observacao, criado_por=usuario)
