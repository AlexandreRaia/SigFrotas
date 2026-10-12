from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.escopo import restringir
from apps.core.views import Editar, Novo, PermissaoMixin, rotas_cadastro

from .forms import ContratoForm, EmpenhoForm, FiscalForm, FornecedorForm, LiberacaoForm
from .models import Contrato, Empenho, FiscalContrato, Fornecedor, SaldoEmpenho
from .services import liberar, saldo_do_empenho

GERIR = 'financeiro.gerir'
VER = 'financeiro.ver'


def escopo_contratos(usuario, consulta):
    """Fiscal ve so os contratos em que esta designado."""
    if usuario.tem_permissao(GERIR) or usuario.perfil.codigo == 'CONSULTA':
        return consulta
    if usuario.perfil.codigo == 'FISCAL':
        return consulta.filter(fiscalcontrato__usuario=usuario).distinct()
    return consulta.none()


def escopo_fiscais(usuario, consulta):
    if usuario.tem_permissao(GERIR) or usuario.perfil.codigo == 'CONSULTA':
        return consulta
    return consulta.filter(usuario=usuario)


def escopo_empenhos(usuario, consulta):
    return restringir(usuario, consulta, gerir=GERIR, campo_centro='centro_custo_id')


ROTAS = {
    'fornecedores': rotas_cadastro(
        'fornecedores', Fornecedor, FornecedorForm, 'Fornecedores', 'fornecedor',
        (('razao_social', 'Razão social'), ('cnpj_cpf', 'CNPJ/CPF'), ('tipo', 'Tipo'), ('ativo', 'Situação')),
        GERIR, ver=VER, campos_busca=('razao_social', 'cnpj_cpf'), filtros=(('tipo', 'Tipo', Fornecedor.TIPOS),)),
    'contratos': rotas_cadastro(
        'contratos', Contrato, ContratoForm, 'Contratos', 'contrato',
        (('numero', 'Número'), ('fornecedor', 'Fornecedor'), ('tipo', 'Tipo'), ('vigencia_fim', 'Vigência até'),
         ('valor_total', 'Valor total', 'moeda'), ('ativo', 'Situação')),
        GERIR, ver=VER, escopo=escopo_contratos, campos_busca=('numero', 'objeto', 'fornecedor__razao_social'),
        filtros=(('tipo', 'Tipo', Contrato.TIPOS),)),
    'fiscais': rotas_cadastro(
        'fiscais', FiscalContrato, FiscalForm, 'Fiscais de contrato', 'fiscal de contrato',
        (('usuario', 'Fiscal'), ('contrato', 'Contrato'), ('centro_custo', 'Centro de custo'), ('suplente', 'Suplente'),
         ('vigencia_ini', 'Desde'), ('vigencia_fim', 'Até')),
        GERIR, ver=VER, alternar=False, escopo=escopo_fiscais),
    'empenhos': rotas_cadastro(
        'empenhos', Empenho, EmpenhoForm, 'Empenhos', 'empenho',
        (('numero', 'Número'), ('exercicio', 'Exercício'), ('finalidade', 'Finalidade'), ('centro_custo', 'Centro de custo'),
         ('valor_empenhado', 'Empenhado', 'moeda'), ('saldo_disponivel', 'Saldo', 'moeda'), ('ativo', 'Situação')),
        GERIR, ver=VER, escopo=escopo_empenhos, campos_busca=('numero',), filtros=(('finalidade', 'Finalidade', Empenho.FINALIDADES),),
        anotacoes={'saldo_disponivel': Subquery(SaldoEmpenho.objects.filter(empenho_id=OuterRef('pk')).values('saldo')[:1])},
        detalhe=True),
}


# --- Empenho: novo (ou prorrogacao), editar, detalhe e liberacoes ----------------------------------

class EmpenhoNovo(Novo):
    """Com ?prorroga=<id> o formulario ja vem preenchido com os dados do empenho que esta sendo prorrogado."""

    def get_initial(self):
        inicial = super().get_initial()
        origem_id = self.request.GET.get('prorroga')
        if origem_id and origem_id.isdigit():
            origem = Empenho.objects.filter(pk=origem_id, municipio_id=self.request.user.municipio_id).first()
            if origem:
                inicial.update(finalidade=origem.finalidade, centro_custo=origem.centro_custo_id, contrato=origem.contrato_id,
                               empenho_origem=origem.pk, exercicio=origem.exercicio, vigencia_ini=origem.vigencia_fim)
        return inicial

    def get_success_url(self):
        return reverse('empenhos_detalhe', args=[self.object.pk])


class EmpenhoEditar(Editar):
    def get_success_url(self):
        return reverse('empenhos_detalhe', args=[self.object.pk])


def _empenho_visivel(request, pk):
    consulta = escopo_empenhos(request.user, Empenho.objects.filter(municipio_id=request.user.municipio_id))
    return get_object_or_404(consulta.select_related('centro_custo', 'contrato__fornecedor', 'empenho_origem'), pk=pk)


class EmpenhoDetalhe(PermissaoMixin, View):
    permissao = VER

    def get(self, request, pk, form=None):
        empenho = _empenho_visivel(request, pk)
        pode_gerir = request.user.tem_permissao(GERIR)
        return render(request, 'financeiro/empenho_detalhe.html', {
            'empenho': empenho, 'saldo': saldo_do_empenho(empenho), 'pode_gerir': pode_gerir,
            'liberacoes': empenho.liberacoes.select_related('criado_por'),
            'lancamentos': empenho.lancamentos.select_related('criado_por')[:50],
            'prorrogacoes': empenho.prorrogacoes.all(),
            'form_liberacao': form or (LiberacaoForm() if pode_gerir else None),
        })


class EmpenhoLiberar(PermissaoMixin, View):
    permissao = GERIR

    def post(self, request, pk):
        empenho = _empenho_visivel(request, pk)
        form = LiberacaoForm(request.POST)
        if form.is_valid():
            try:
                liberar(empenho=empenho, valor=form.cleaned_data['valor'], data=form.cleaned_data['data'],
                        observacao=form.cleaned_data['observacao'], usuario=request.user)
            except ValidationError as erro:
                form.add_error('valor', erro)
            else:
                messages.success(request, 'Liberação registrada.')
                return redirect('empenhos_detalhe', pk=empenho.pk)
        return EmpenhoDetalhe().get(request, pk, form=form)
