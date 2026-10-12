from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.escopo import restringir
from apps.core.models import Anexo
from apps.core.services import anexar
from apps.core.views import Editar, Novo, PermissaoMixin, rotas_cadastro

from .forms import (AnexoForm, CategoriaVeiculoForm, EquipamentoForm, LeituraForm, MarcaForm, ModeloForm,
                    VeiculoForm)
from .models import CategoriaVeiculo, Combustivel, Marca, Veiculo, VeiculoEquipamento

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
}


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


# --- Marcas e modelos (catalogo compartilhado por todas as prefeituras: so se acrescenta) ----------------------

class MarcasModelos(PermissaoMixin, View):
    permissao = VER

    def contexto(self, request, form_marca=None, form_modelo=None):
        return {
            'marcas': Marca.objects.annotate(total=Count('modelos')).prefetch_related('modelos'),
            'combustiveis': Combustivel.objects.all(),
            'pode_gerir': request.user.tem_permissao(GERIR),
            'form_marca': form_marca or MarcaForm(), 'form_modelo': form_modelo or ModeloForm(),
        }

    def get(self, request):
        return render(request, 'frota/marcas.html', self.contexto(request))

    def post(self, request):
        if not request.user.tem_permissao(GERIR):
            raise PermissionDenied
        marca = request.POST.get('acao') == 'marca'
        form = (MarcaForm if marca else ModeloForm)(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Marca cadastrada.' if marca else 'Modelo cadastrado.')
            return redirect('marcas_lista')
        return render(request, 'frota/marcas.html', self.contexto(request, **{'form_marca' if marca else 'form_modelo': form}))
