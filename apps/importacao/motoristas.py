"""Importacao de motoristas. Uma linha por motorista; so cadastra (prontuario ou CPF ja existente e erro)."""
from django.core.exceptions import ValidationError

from apps.core.models import Secretaria
from apps.pessoas.forms import MotoristaForm
from apps.pessoas.models import Motorista

from .leitor import data_iso, escolha

COLUNAS = [
    ('prontuario', True, ''),
    ('nome', True, ''),
    ('cpf', True, 'Com ou sem pontuação'),
    ('secretaria', False, 'Sigla da secretaria (precisa existir)'),
    ('cargo', False, ''),
    ('situacao', False, 'Ativo, Suspenso ou Inativo (padrão: Ativo)'),
    ('cnh_numero', False, ''),
    ('cnh_categoria', False, 'A, B, C, D, E, AB, AC, AD ou AE'),
    ('cnh_validade', False, 'dd/mm/aaaa'),
    ('telefone', False, ''),
    ('email', False, ''),
]
EXEMPLO = ['1234', 'Fulano de Tal', '529.982.247-25', 'SMA', 'Motorista', 'Ativo', '12345678900', 'B', '31/12/2028', '', '']


def importar_linha(linha, municipio_id):
    secretaria = None
    if linha.get('secretaria'):
        secretaria = Secretaria.objects.filter(municipio_id=municipio_id, sigla__iexact=linha['secretaria']).first()
        if secretaria is None:
            raise ValueError(f'Secretaria "{linha["secretaria"]}" não encontrada. Cadastre antes de importar.')
    dados = {
        'prontuario': linha.get('prontuario', ''), 'nome': linha.get('nome', ''), 'cpf': linha.get('cpf', ''),
        'secretaria': secretaria.pk if secretaria else '', 'cargo': linha.get('cargo', ''),
        'situacao': escolha(linha.get('situacao'), Motorista.SITUACOES, 'Situação') or 'ATIVO',
        'cnh_numero': linha.get('cnh_numero', ''), 'cnh_categoria': (linha.get('cnh_categoria') or '').upper(),
        'cnh_validade': data_iso(linha.get('cnh_validade')), 'telefone': linha.get('telefone', ''),
        'email': linha.get('email', ''),
    }
    form = MotoristaForm(dados, municipio_id=municipio_id)
    if not form.is_valid():
        raise ValidationError('; '.join(
            f'{form.fields[c].label if c in form.fields else "Geral"}: {" ".join(e)}' for c, e in form.errors.items()))
    return form.save().nome
