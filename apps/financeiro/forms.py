from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core import contexto
from apps.core.forms import FormularioDaPrefeitura
from apps.core.models import Usuario
from apps.core.validadores import so_digitos, validar_cpf_ou_cnpj

from .models import Contrato, Empenho, FiscalContrato, Fornecedor
from .services import liberar, saldo_do_empenho

DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class FornecedorForm(FormularioDaPrefeitura):
    unicos = [('cnpj_cpf',)]
    aceita_pontuacao = {'cnpj_cpf': 18}

    class Meta:
        model = Fornecedor
        fields = ['cnpj_cpf', 'razao_social', 'tipo', 'telefone', 'email']
        help_texts = {'cnpj_cpf': 'Só números ou com pontuação. Confere os dígitos verificadores.',
                      'tipo': 'Define em que cadastros o fornecedor aparece (oficina nas SMVs, posto no abastecimento...).'}
        widgets = {'razao_social': forms.TextInput}

    def clean_cnpj_cpf(self):
        valor = self.cleaned_data['cnpj_cpf']
        validar_cpf_ou_cnpj(valor)
        return so_digitos(valor)


class ContratoForm(FormularioDaPrefeitura):
    unicos = [('numero',)]

    class Meta:
        model = Contrato
        fields = ['numero', 'fornecedor', 'tipo', 'processo', 'objeto', 'vigencia_ini', 'vigencia_fim', 'valor_total']
        widgets = {'vigencia_ini': DATA, 'vigencia_fim': DATA, 'objeto': forms.Textarea(attrs={'rows': 3})}
        help_texts = {'tipo': 'Manutenção e Combustível são os que sustentam empenhos.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fornecedor'].queryset = self.fields['fornecedor'].queryset.filter(ativo=True)


class FiscalForm(FormularioDaPrefeitura):
    class Meta:
        model = FiscalContrato
        fields = ['contrato', 'centro_custo', 'usuario', 'suplente', 'vigencia_ini', 'vigencia_fim']
        labels = {'centro_custo': 'Centro de custo'}
        widgets = {'vigencia_ini': DATA, 'vigencia_fim': DATA}
        help_texts = {'centro_custo': 'Deixe em branco para fiscalizar todos os centros de custo do contrato.',
                      'usuario': 'Usuários com o perfil Fiscal de contrato.',
                      'vigencia_fim': 'Em branco enquanto estiver designado.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = Usuario.objects.filter(
            municipio_id=self.instance.municipio_id, perfil__codigo='FISCAL', ativo=True)
        self.fields['centro_custo'].queryset = self.fields['centro_custo'].queryset.filter(ativo=True)


class EmpenhoForm(FormularioDaPrefeitura):
    unicos = [('exercicio', 'numero')]
    liberar_total = forms.BooleanField(
        label='Liberar o valor total agora', required=False, initial=True,
        help_text='Desmarque se o valor será liberado em parcelas: elas são lançadas na página do empenho.')

    class Meta:
        model = Empenho
        fields = ['finalidade', 'centro_custo', 'contrato', 'numero', 'exercicio', 'vigencia_ini', 'vigencia_fim',
                  'valor_empenhado', 'data_empenho', 'empenho_origem']
        labels = {'centro_custo': 'Centro de custo'}
        widgets = {'vigencia_ini': DATA, 'vigencia_fim': DATA, 'data_empenho': DATA, 'empenho_origem': forms.HiddenInput}
        help_texts = {
            'finalidade': 'Cada empenho vale para uma finalidade só.',
            'centro_custo': 'Centro de custo (secretaria) que usa o valor.',
            'contrato': 'Opcional. O tipo do contrato precisa combinar com a finalidade.',
            'vigencia_ini': 'O período em que o valor pode ser usado.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['centro_custo'].queryset = self.fields['centro_custo'].queryset.filter(ativo=True)
        self.fields['contrato'].queryset = self.fields['contrato'].queryset.filter(ativo=True)
        if self.instance.pk:
            del self.fields['liberar_total']  # edicao: parcelas ficam na pagina do empenho

    def clean(self):
        dados = super().clean()
        origem = dados.get('empenho_origem')
        if origem and (origem.finalidade != dados.get('finalidade') or origem.centro_custo_id != getattr(dados.get('centro_custo'), 'pk', None)):
            raise ValidationError('A prorrogação precisa ter a mesma finalidade e o mesmo centro de custo do empenho original.')
        if self.instance.pk:
            if dados.get('valor_empenhado') is not None and dados['valor_empenhado'] < saldo_do_empenho(self.instance).liberado:
                self.add_error('valor_empenhado', 'O valor não pode ficar abaixo do que já foi liberado.')
            if self.instance.lancamentos.exists() and any(
                    f in self.changed_data for f in ('finalidade', 'centro_custo')):
                raise ValidationError('Empenho com lançamentos não pode mudar de finalidade nem de centro de custo.')
        return dados


    def save(self, commit=True):
        novo = self.instance.pk is None
        empenho = super().save(commit=commit)
        if commit and novo and self.cleaned_data.get('liberar_total'):
            usuario = Usuario.objects.filter(pk=contexto.usuario_atual_id()).first()
            liberar(empenho=empenho, valor=empenho.valor_empenhado, data=empenho.data_empenho or timezone.localdate(),
                    observacao='Liberação do valor total.', usuario=usuario)
        return empenho


class LiberacaoForm(forms.Form):
    data = forms.DateField(label='Data', widget=DATA)
    valor = forms.DecimalField(label='Valor', max_digits=14, decimal_places=2, min_value=0.01)
    observacao = forms.CharField(label='Observação', required=False)
