from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.escopo import restringir
from apps.core.models import Anexo
from apps.core.services import anexar, registrar_consulta
from apps.core.views import Editar, Novo, PermissaoMixin, rotas_cadastro

from .forms import (AfastamentoForm, AnexoMotoristaForm, CertificadoForm, MotoristaForm, PenalidadeForm)
from .models import Motorista, MotoristaAfastamento, MotoristaCertificado

GERIR = 'pessoas.gerir'
VER = 'pessoas.ver'
DADOS = 'pessoas.dados_pessoais'


def escopo_motoristas(usuario, consulta):
    return restringir(usuario, consulta, gerir=GERIR, campo_secretaria='secretaria_id')


ROTAS = {
    'motoristas': rotas_cadastro(
        'motoristas', Motorista, MotoristaForm, 'Motoristas', 'motorista',
        # a lista mostra so o que e operacional: CPF, RG, endereco e numero da CNH ficam fora
        (('prontuario', 'Prontuário'), ('nome', 'Nome'), ('secretaria.sigla', 'Secretaria'), ('cnh_categoria', 'CNH'),
         ('cnh_validade', 'Validade da CNH'), ('situacao', 'Situação')),
        GERIR, ver=VER, alternar=False, detalhe=True, escopo=escopo_motoristas, campos_busca=('prontuario', 'nome'),
        filtros=(('situacao', 'Situação', Motorista.SITUACOES),)),
}


class ExigeDadosPessoais:
    """Cadastrar e editar motorista mexe em dado pessoal: exige tambem a permissao de dados pessoais."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.tem_permissao(DADOS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class MotoristaNovo(ExigeDadosPessoais, Novo):
    def get_success_url(self):
        return reverse('motoristas_detalhe', args=[self.object.pk])


class MotoristaEditar(ExigeDadosPessoais, Editar):
    def get_success_url(self):
        return reverse('motoristas_detalhe', args=[self.object.pk])


def _motorista(request, pk):
    consulta = escopo_motoristas(request.user, Motorista.objects.filter(municipio_id=request.user.municipio_id))
    return get_object_or_404(consulta.select_related('secretaria', 'unidade', 'usuario'), pk=pk)


class MotoristaDetalhe(PermissaoMixin, View):
    permissao = VER

    def get(self, request, pk):
        motorista = _motorista(request, pk)
        pode_gerir = request.user.tem_permissao(GERIR)
        ve_dados = request.user.tem_permissao(DADOS)
        if ve_dados:
            registrar_consulta(usuario=request.user, objeto=motorista, detalhe='ficha completa')
        return render(request, 'pessoas/motorista_detalhe.html', {
            'motorista': motorista, 'pode_gerir': pode_gerir and ve_dados, 've_dados': ve_dados,
            'certificados': motorista.certificados.all(), 'afastamentos': motorista.afastamentos.all(),
            'penalidades': motorista.penalidades.all() if ve_dados else [],
            'anexos': Anexo.objects.filter(municipio_id=motorista.municipio_id, entidade='motoristas',
                                           entidade_id=motorista.pk) if ve_dados else [],
            'form_certificado': CertificadoForm(), 'form_afastamento': AfastamentoForm(),
            'form_penalidade': PenalidadeForm(), 'form_anexo': AnexoMotoristaForm(),
        })


class AcaoDoMotorista(ExigeDadosPessoais, PermissaoMixin, View):
    permissao = GERIR

    def post(self, request, pk, **kwargs):
        motorista = _motorista(request, pk)
        try:
            messages.success(request, self.executar(request, motorista, **kwargs))
        except ValidationError as erro:
            messages.error(request, ' '.join(erro.messages))
        return redirect('motoristas_detalhe', pk=motorista.pk)

    @staticmethod
    def salvar(form, motorista):
        if not form.is_valid():
            raise ValidationError([m for erros in form.errors.values() for m in erros])
        registro = form.save(commit=False)
        registro.municipio_id, registro.motorista = motorista.municipio_id, motorista
        registro.save()


class CertificadoNovo(AcaoDoMotorista):
    def executar(self, request, motorista):
        self.salvar(CertificadoForm(request.POST), motorista)
        return 'Certificado adicionado.'


class CertificadoExcluir(AcaoDoMotorista):
    def executar(self, request, motorista, item_pk):
        get_object_or_404(MotoristaCertificado, pk=item_pk, motorista=motorista, municipio_id=motorista.municipio_id).delete()
        return 'Certificado removido.'


class AfastamentoNovo(AcaoDoMotorista):
    def executar(self, request, motorista):
        self.salvar(AfastamentoForm(request.POST), motorista)
        return 'Afastamento registrado.'


class AfastamentoExcluir(AcaoDoMotorista):
    def executar(self, request, motorista, item_pk):
        get_object_or_404(MotoristaAfastamento, pk=item_pk, motorista=motorista, municipio_id=motorista.municipio_id).delete()
        return 'Afastamento removido.'


class PenalidadeNova(AcaoDoMotorista):
    """Penalidade so se acrescenta: nao ha tela para apagar."""

    def executar(self, request, motorista):
        self.salvar(PenalidadeForm(request.POST), motorista)
        return 'Penalidade registrada.'


class AnexoNovo(AcaoDoMotorista):
    def executar(self, request, motorista):
        form = AnexoMotoristaForm(request.POST, request.FILES)
        if not form.is_valid():
            raise ValidationError('Escolha o tipo e o arquivo.')
        anexar(municipio_id=motorista.municipio_id, entidade='motoristas', entidade_id=motorista.pk,
               arquivo=form.cleaned_data['arquivo'], categoria=form.cleaned_data['categoria'], enviado_por=request.user)
        return 'Arquivo anexado.'
