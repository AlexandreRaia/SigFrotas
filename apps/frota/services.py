"""Regras da frota: o km nunca diminui (regra 4) e a lotacao guarda o historico."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import LeituraVeiculo, Veiculo, VeiculoLotacao


@transaction.atomic
def registrar_leitura(*, veiculo, odometro=None, horimetro=None, origem='MANUAL', origem_id=None, lido_em=None):
    """Grava a leitura e atualiza o km/horimetro atual do veiculo. Recusa km ou horimetro menor que o atual."""
    if odometro is None and horimetro is None:
        raise ValidationError('Informe o km ou o horímetro.')
    atual = Veiculo.objects.select_for_update().get(pk=veiculo.pk, municipio_id=veiculo.municipio_id)
    if odometro is not None and odometro < atual.odometro_atual:
        raise ValidationError(f'O km não pode diminuir (atual: {atual.odometro_atual}).')
    if horimetro is not None and atual.horimetro_atual is not None and horimetro < atual.horimetro_atual:
        raise ValidationError(f'O horímetro não pode diminuir (atual: {atual.horimetro_atual}).')
    leitura = LeituraVeiculo.objects.create(
        municipio_id=atual.municipio_id, veiculo=atual, odometro=odometro, horimetro=horimetro,
        lido_em=lido_em or timezone.now(), origem=origem, origem_id=origem_id)
    campos = []
    if odometro is not None:
        atual.odometro_atual = odometro
        campos.append('odometro_atual')
    if horimetro is not None:
        atual.horimetro_atual = horimetro
        campos.append('horimetro_atual')
    atual.save(update_fields=campos + ['atualizado_em'])
    return leitura


def atualizar_lotacao(veiculo):
    """Se a secretaria, a unidade ou o centro de custo mudaram, fecha a lotacao anterior e abre a nova."""
    hoje = timezone.localdate()
    atual = VeiculoLotacao.objects.filter(veiculo=veiculo, fim__isnull=True).first()
    chave = (veiculo.secretaria_id, veiculo.unidade_id, veiculo.centro_custo_id)
    if atual and (atual.secretaria_id, atual.unidade_id, atual.centro_custo_id) == chave:
        return
    if atual:
        atual.fim = hoje
        atual.save(update_fields=['fim'])
    if any(chave):
        VeiculoLotacao.objects.create(
            municipio_id=veiculo.municipio_id, veiculo=veiculo, secretaria_id=veiculo.secretaria_id,
            unidade_id=veiculo.unidade_id, centro_custo_id=veiculo.centro_custo_id, inicio=hoje)
