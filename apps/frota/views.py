from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.escopo import restringir
from apps.core.models import Anexo
from apps.core.services import anexar
from apps.core.views import Editar, Novo, PermissaoMixin, rotas_cadastro

from .forms import (AnexoForm, CategoriaVeiculoForm, EquipamentoForm, LeituraForm, MarcaForm, ModeloForm,
                    VeiculoForm)
from .models import CategoriaVeiculo, Marca, Modelo, Veiculo, VeiculoEquipamento

GERIR = 'frota.gerir'
VER = 'frota.ver'


def escopo_veiculos(usuario, consulta):
    return restringir(usuario, consulta, gerir=GERIR, campo_secretaria='secretaria_id', campo_centro='centro_custo_id')


ROTAS = {
    'veiculos': rotas_cadastro(
        'veiculos', Veiculo, VeiculoForm, 'Veículos', 'veículo',
        (('placa', 'Placa'), ('prefixo', 'Prefixo'), ('modelo', 'Modelo'), ('categoria', 'Categoria'),
         ('secretaria.sigla', 'Secretaria'), ('odometro_atual', 'Km', 'numero'), ('situacao', 'Situação')),
        GERIR, ver=VER, alternar=False, detalhe=True, escopo=escopo_veiculos, ligar=('modelo__marca',),
        campos_busca=('placa', 'prefixo', 'chassi', 'renavam', 'modelo__nome', 'modelo__marca__nome'),
        filtros=(('situacao', 'Situação', Veiculo.SITUACOES), ('tipo_frota', 'Tipo de frota', Veiculo.TIPOS_FROTA))),
    'categorias_veiculo': rotas_cadastro(
        'categorias_veiculo', CategoriaVeiculo, CategoriaVeiculoForm, 'Categorias de veículo', 'categoria de veículo',
        (('nome', 'Nome'), ('cnh_minima', 'CNH mínima'), ('usa_horimetro', 'Usa horímetro'), ('ativo', 'Situação')),
        GERIR, ver=VER),
    # Marcas e modelos: catalogo compartilhado por todas as prefeituras (sem municipio_id), sem inativar nem apagar.
    # Fluxo: cria a marca -> cai na lista de modelos dela -> "+" ja abre o formulario com a marca escolhida.
    'marcas': rotas_cadastro(
        'marcas', Marca, MarcaForm, 'Marcas', 'marca', (('nome', 'Marca'), ('total_modelos', 'Modelos', 'numero')), GERIR, ver=VER,
        alternar=False, catalogo_global=True, anotacoes={'total_modelos': Count('modelos')}, campos_busca=('nome',),
        link_filho=('modelos_lista', 'marca', 'ri-car-line', 'Ver os modelos da marca')),
    'modelos': rotas_cadastro(
        'modelos', Modelo, ModeloForm, 'Modelos', 'modelo',
        (('marca.nome', 'Marca'), ('nome', 'Modelo'), ('em_uso', 'Veículos', 'numero')), GERIR, ver=VER,
        alternar=False, catalogo_global=True, anotacoes={'em_uso': Count('veiculo')}, campos_busca=('nome', 'marca__nome'),
        filtros=(('marca', 'Marca', lambda: [(m.pk, m.nome) for m in Marca.objects.all()]),), repassar_ao_novo=('marca',),
        texto_vazio='Nenhum modelo por aqui. Use o botão + para adicionar.'),
}


# Situacao do veiculo -> (cor da etiqueta, rotulo). "Revisao atrasada" (cor 'atrasada') chega com a manutencao preventiva (fase 6).
ETIQUETA_DA_SITUACAO = {
    'DISPONIVEL': ('operacao', 'Em operação'), 'EM_USO': ('operacao', 'Em operação'), 'RESERVA': ('operacao', 'Em operação'),
    'MANUTENCAO': ('manutencao', 'Em manutenção'), 'INATIVO': ('inativa', 'Inativo'), 'BAIXADO': ('inativa', 'Baixado'),
}


class VeiculosLista(PermissaoMixin, View):
    """Listagem de veiculos: pagina leve; a tabela (Tabulator) busca os dados em veiculos_dados."""
    permissao = VER

    def get(self, request):
        return render(request, 'frota/veiculos_lista.html', {'pode_gerir': request.user.tem_permissao(GERIR)})


class VeiculosDados(PermissaoMixin, View):
    """Os veiculos que o usuario pode ver, em JSON, para a tabela. Respeita o escopo de cada perfil."""
    permissao = VER

    def get(self, request):
        pode_gerir = request.user.tem_permissao(GERIR)
        consulta = escopo_veiculos(request.user, Veiculo.objects.filter(municipio_id=request.user.municipio_id))
        dados = []
        for v in consulta.select_related('modelo__marca', 'categoria', 'secretaria'):
            cor, rotulo = ETIQUETA_DA_SITUACAO.get(v.situacao, ('inativa', v.get_situacao_display()))
            inativo = v.situacao in ('INATIVO', 'BAIXADO')
            dados.append({
                'id': v.pk, 'placa': v.placa, 'prefixo': v.prefixo, 'modelo': str(v.modelo) if v.modelo else '',
                'categoria': v.categoria.nome if v.categoria else '', 'secretaria': v.secretaria.sigla if v.secretaria else '',
                'km': v.odometro_atual, 'situacao': cor, 'situacao_rotulo': rotulo, 'inativo': inativo,
                'url_ver': reverse('veiculos_detalhe', args=[v.pk]),
                'url_editar': reverse('veiculos_editar', args=[v.pk]) if pode_gerir else '',
                # em manutencao ou baixado nao se inativa nem se reativa por aqui
                'url_alternar': reverse('veiculos_alternar_situacao', args=[v.pk])
                if pode_gerir and v.situacao not in ('MANUTENCAO', 'BAIXADO') else '',
            })
        return JsonResponse(dados, safe=False)


class VeiculoAlternarSituacao(PermissaoMixin, View):
    """Inativar em vez de excluir: o veiculo e o historico ficam. Reativar volta para 'disponivel'."""
    permissao = GERIR

    def post(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk, municipio_id=request.user.municipio_id)
        if veiculo.situacao == 'INATIVO':
            veiculo.situacao = 'DISPONIVEL'
        elif veiculo.situacao in ('DISPONIVEL', 'EM_USO', 'RESERVA'):
            veiculo.situacao = 'INATIVO'
        else:
            return JsonResponse({'erro': 'Veículo em manutenção ou baixado não pode ser inativado nem reativado por aqui.'}, status=400)
        veiculo.save(update_fields=['situacao', 'atualizado_em'])
        return JsonResponse({'ok': True, 'situacao': veiculo.situacao})


class VeiculoNovo(Novo):
    def get_success_url(self):
        return reverse('veiculos_detalhe', args=[self.object.pk])


class VeiculoEditar(Editar):
    def get_success_url(self):
        return reverse('veiculos_detalhe', args=[self.object.pk])


def _veiculo(request, pk):
    consulta = escopo_veiculos(request.user, Veiculo.objects.filter(municipio_id=request.user.municipio_id))
    return get_object_or_404(consulta.select_related('modelo__marca', 'categoria', 'combustivel', 'secretaria',
                                                     'unidade', 'centro_custo', 'contrato_locacao'), pk=pk)


class VeiculoDetalhe(PermissaoMixin, View):
    permissao = VER

    def get(self, request, pk):
        veiculo = _veiculo(request, pk)
        pode_gerir = request.user.tem_permissao(GERIR)
        return render(request, 'frota/veiculo_detalhe.html', {
            'veiculo': veiculo, 'pode_gerir': pode_gerir,
            'equipamentos': veiculo.equipamentos.all(),
            'lotacoes': veiculo.lotacoes.select_related('secretaria', 'unidade', 'centro_custo'),
            'leituras': veiculo.leituras.all()[:15],
            'anexos': Anexo.objects.filter(municipio_id=veiculo.municipio_id, entidade='veiculos', entidade_id=veiculo.pk),
            'form_equipamento': EquipamentoForm() if pode_gerir else None,
            'form_leitura': LeituraForm(veiculo=veiculo) if pode_gerir else None,
            'form_anexo': AnexoForm() if pode_gerir else None,
        })


class AcaoDoVeiculo(PermissaoMixin, View):
    """Base das acoes (POST) da pagina do veiculo; volta para a pagina com um aviso."""
    permissao = GERIR

    def post(self, request, pk, **kwargs):
        veiculo = _veiculo(request, pk)
        try:
            texto = self.executar(request, veiculo, **kwargs)
            messages.success(request, texto)
        except ValidationError as erro:
            messages.error(request, ' '.join(erro.messages))
        return redirect('veiculos_detalhe', pk=veiculo.pk)


class EquipamentoNovo(AcaoDoVeiculo):
    def executar(self, request, veiculo):
        form = EquipamentoForm(request.POST)
        if not form.is_valid():
            raise ValidationError([m for erros in form.errors.values() for m in erros])
        equipamento = form.save(commit=False)
        equipamento.municipio_id, equipamento.veiculo = veiculo.municipio_id, veiculo
        equipamento.save()
        return 'Equipamento adicionado.'


class EquipamentoExcluir(AcaoDoVeiculo):
    def executar(self, request, veiculo, equipamento_pk):
        get_object_or_404(VeiculoEquipamento, pk=equipamento_pk, veiculo=veiculo, municipio_id=veiculo.municipio_id).delete()
        return 'Equipamento removido.'


class LeituraNova(AcaoDoVeiculo):
    def executar(self, request, veiculo):
        form = LeituraForm(request.POST, veiculo=veiculo)
        if not form.is_valid():
            raise ValidationError([m for erros in form.errors.values() for m in erros])
        form.registrar()
        return 'Leitura registrada.'


class AnexoNovo(AcaoDoVeiculo):
    def executar(self, request, veiculo):
        form = AnexoForm(request.POST, request.FILES)
        if not form.is_valid():
            raise ValidationError('Escolha o tipo e o arquivo.')
        anexar(municipio_id=veiculo.municipio_id, entidade='veiculos', entidade_id=veiculo.pk,
               arquivo=form.cleaned_data['arquivo'], categoria=form.cleaned_data['categoria'], enviado_por=request.user)
        return 'Arquivo anexado.'


# --- Marcas e modelos (catalogo compartilhado por todas as prefeituras) ----------------------------------------

def _modelos_da_marca(marca_id):
    return f"{reverse('modelos_lista')}?marca={marca_id}"


class MarcaNova(Novo):
    def get_success_url(self):   # marca criada: o proximo passo e cadastrar os modelos dela
        return _modelos_da_marca(self.object.pk)


class ModeloNovo(Novo):
    def get_success_url(self):   # volta para os modelos da mesma marca, pronta para o proximo "+"
        return _modelos_da_marca(self.object.marca_id)


class ModeloEditar(Editar):
    def get_success_url(self):
        return _modelos_da_marca(self.object.marca_id)
