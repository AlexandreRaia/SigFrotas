"""Importacao de veiculos. Uma linha por veiculo; so cadastra (placa ja existente e erro)."""
from django.core.exceptions import ValidationError

from apps.core.models import CentroCusto, Secretaria
from apps.frota.forms import VeiculoForm
from apps.frota.models import CategoriaVeiculo, Combustivel, Marca, Modelo, Veiculo

from .leitor import decimal_br, escolha, inteiro

# (coluna, obrigatoria, explicacao)
COLUNAS = [
    ('placa', True, 'ABC1234 ou ABC1D23'),
    ('prefixo', False, ''),
    ('marca', False, 'Cadastrada sozinha se ainda não existir'),
    ('modelo', False, 'Precisa da marca; cadastrado sozinho se não existir'),
    ('ano_fabricacao', False, ''),
    ('ano_modelo', False, ''),
    ('cor', False, ''),
    ('combustivel', False, 'Gasolina, Etanol, Diesel S10... (precisa existir)'),
    ('categoria', False, 'Nome da categoria de veículo (precisa existir)'),
    ('secretaria', False, 'Sigla da secretaria (precisa existir)'),
    ('centro_custo', False, 'Código do centro de custo (precisa existir)'),
    ('tipo_frota', False, 'Próprio, Locado, Estadual, Doação ou Cedido (padrão: Próprio)'),
    ('situacao', False, 'Disponível, Em uso, Em manutenção, Reserva, Inativo ou Baixado (padrão: Disponível)'),
    ('km', False, 'Km atual'),
    ('renavam', False, ''),
    ('chassi', False, '17 caracteres'),
    ('capacidade_tanque', False, 'Litros, ex.: 55,5'),
    ('proprietario', False, 'Para veículos locados, cedidos ou estaduais'),
]
EXEMPLO = ['ABC1D23', 'V-001', 'Fiat', 'Uno', '2020', '2021', 'Branco', 'Flex', 'Automóvel', 'SMA', '100', 'Próprio',
           'Disponível', '35000', '', '', '47,5', '']


def _buscar(modelo, municipio_id, campo, valor, rotulo):
    if not valor:
        return None
    achado = modelo.objects.filter(**{'municipio_id': municipio_id, f'{campo}__iexact': valor}).first()
    if achado is None:
        raise ValueError(f'{rotulo} "{valor}" não encontrado(a). Cadastre antes de importar.')
    return achado.pk


def importar_linha(linha, municipio_id):
    dados = {
        'placa': linha.get('placa', ''), 'prefixo': linha.get('prefixo', ''), 'cor': linha.get('cor', ''),
        'ano_fabricacao': inteiro(linha.get('ano_fabricacao')), 'ano_modelo': inteiro(linha.get('ano_modelo')),
        'odometro_atual': inteiro(linha.get('km')) or '0', 'renavam': linha.get('renavam', ''),
        'chassi': linha.get('chassi', ''), 'capacidade_tanque': decimal_br(linha.get('capacidade_tanque')),
        'proprietario': linha.get('proprietario', ''),
        'tipo_frota': escolha(linha.get('tipo_frota'), Veiculo.TIPOS_FROTA, 'Tipo de frota') or 'PROPRIO',
        'situacao': escolha(linha.get('situacao'), Veiculo.SITUACOES, 'Situação') or 'DISPONIVEL',
        'secretaria': _buscar(Secretaria, municipio_id, 'sigla', linha.get('secretaria'), 'Secretaria'),
        'centro_custo': _buscar(CentroCusto, municipio_id, 'codigo', linha.get('centro_custo'), 'Centro de custo'),
        'categoria': _buscar(CategoriaVeiculo, municipio_id, 'nome', linha.get('categoria'), 'Categoria'),
    }
    combustivel = linha.get('combustivel')
    if combustivel:
        achado = Combustivel.objects.filter(nome__iexact=combustivel).first()
        if achado is None:
            raise ValueError(f'Combustível "{combustivel}" não encontrado.')
        dados['combustivel'] = achado.pk
    marca, modelo = linha.get('marca', ''), linha.get('modelo', '')
    if modelo and not marca:
        raise ValueError('Informe a marca junto com o modelo.')
    if marca and modelo:
        objeto_marca = Marca.objects.filter(nome__iexact=marca).first() or Marca.objects.create(nome=marca)
        objeto_modelo = Modelo.objects.filter(marca=objeto_marca, nome__iexact=modelo).first() or Modelo.objects.create(marca=objeto_marca, nome=modelo)
        dados['modelo'] = objeto_modelo.pk

    form = VeiculoForm(dados, municipio_id=municipio_id)
    if not form.is_valid():
        raise ValidationError('; '.join(
            f'{form.fields[c].label if c in form.fields else "Geral"}: {" ".join(e)}' for c, e in form.errors.items()))
    return form.save().placa
