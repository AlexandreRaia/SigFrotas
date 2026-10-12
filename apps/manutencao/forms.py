from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.forms import DecimalBR, FormularioDaPrefeitura
from apps.financeiro.models import Contrato, Empenho, Fornecedor
from apps.frota.models import Veiculo

from .models import CategoriaServico, Chamado, OrcamentoItem, PRIORIDADES, Smv, TANQUES

DATAHORA = forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M')
DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class CategoriaServicoForm(FormularioDaPrefeitura):
    unicos = [('nome',)]

    class Meta:
        model = CategoriaServico
        fields = ['nome']
        help_texts = {'nome': 'Por exemplo: Freios, Suspensão, Elétrica, Motor, Lataria e pintura.'}
        widgets = {'nome': forms.TextInput}


class ChamadoForm(FormularioDaPrefeitura):
    class Meta:
        model = Chamado
        fields = ['veiculo', 'prioridade', 'descricao']
        labels = {'veiculo': 'Veículo'}
        widgets = {'descricao': forms.Textarea(attrs={'rows': 4})}
        help_texts = {'descricao': 'O que está acontecendo? Barulho, luz do painel, vazamento, pneu... Quanto mais detalhe, melhor.',
                      'prioridade': 'Urgente só para veículo parado ou com risco de segurança.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['veiculo'].queryset = (self.fields['veiculo'].queryset.exclude(situacao__in=['BAIXADO', 'INATIVO'])
                                           .order_by('placa'))


class SmvForm(FormularioDaPrefeitura):
    """Entrada do veiculo na oficina (abre a SMV)."""

    class Meta:
        model = Smv
        fields = ['veiculo', 'tipo', 'fornecedor', 'contrato', 'entrada_em', 'entrada_km', 'entrada_tanque',
                  'defeito_relatado', 'veiculo_substituto']
        labels = {'veiculo': 'Veículo', 'fornecedor': 'Oficina'}
        widgets = {'entrada_em': DATAHORA, 'defeito_relatado': forms.Textarea(attrs={'rows': 3})}
        help_texts = {
            'fornecedor': 'Oficina (ou locadora, para veículo locado) que vai atender.',
            'contrato': 'Opcional. Contrato de manutenção ou de locação.',
            'entrada_km': 'Km do hodômetro na entrada. Não pode ser menor que o km atual do veículo.',
            'veiculo_substituto': 'Opcional. Veículo que cobre o serviço enquanto este está parado.',
        }

    grupos = (
        ('Veículo e oficina', ('veiculo', 'tipo', 'fornecedor', 'contrato')),
        ('Entrada', ('entrada_em', 'entrada_km', 'entrada_tanque', 'veiculo_substituto', 'defeito_relatado')),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['veiculo'].queryset = Veiculo.objects.filter(municipio_id=self.instance.municipio_id).exclude(
            situacao__in=['BAIXADO', 'INATIVO']).order_by('placa')
        self.fields['veiculo_substituto'].queryset = self.fields['veiculo_substituto'].queryset.filter(situacao='DISPONIVEL')
        self.fields['fornecedor'].queryset = Fornecedor.objects.filter(
            municipio_id=self.instance.municipio_id, ativo=True, tipo__in=['OFICINA', 'LOCADORA']).order_by('razao_social')
        self.fields['fornecedor'].required = True
        self.fields['contrato'].queryset = Contrato.objects.filter(
            municipio_id=self.instance.municipio_id, ativo=True, tipo__in=['MANUTENCAO', 'LOCACAO'])
        self.fields['entrada_em'].initial = timezone.localtime().strftime('%Y-%m-%dT%H:%M')


class DiagnosticoForm(forms.Form):
    diagnostico = forms.CharField(label='Diagnóstico', widget=forms.Textarea(attrs={'rows': 4}),
                                  help_text='O que foi encontrado e o que precisa ser feito. Fotos e vídeos vão no chat da SMV.')


class EntregaForm(forms.Form):
    saida_em = forms.DateTimeField(label='Data e hora da saída', widget=DATAHORA, input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'])
    saida_km = forms.IntegerField(label='Km na saída', min_value=0)
    saida_tanque = forms.ChoiceField(label='Tanque na saída', choices=[('', '---------')] + TANQUES, required=False)
    observacao = forms.CharField(label='Observação', required=False, widget=forms.Textarea(attrs={'rows': 2}),
                                 help_text='Vistoria final, peças substituídas (fotos das peças vão no chat da SMV).')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['saida_em'].initial = timezone.localtime().strftime('%Y-%m-%dT%H:%M')


class ItemOrcamentoForm(forms.ModelForm):
    quantidade = DecimalBR(max_digits=10, decimal_places=3, min_value=0.001, initial=1)
    valor_unitario = DecimalBR(label='Valor unitário', max_digits=12, decimal_places=2, min_value=0)

    class Meta:
        model = OrcamentoItem
        fields = ['tipo', 'categoria', 'codigo', 'descricao', 'quantidade', 'valor_unitario']
        widgets = {'descricao': forms.TextInput}

    def __init__(self, *args, municipio_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = CategoriaServico.objects.filter(municipio_id=municipio_id, ativo=True)


class NotaFiscalForm(forms.Form):
    nf_pecas_numero = forms.CharField(label='NF das peças (número)', required=False, max_length=30)
    nf_pecas_valor = DecimalBR(label='Valor da NF das peças', required=False, min_value=0, max_digits=14, decimal_places=2)
    nf_servicos_numero = forms.CharField(label='NF dos serviços (número)', required=False, max_length=30)
    nf_servicos_valor = DecimalBR(label='Valor da NF dos serviços', required=False, min_value=0, max_digits=14, decimal_places=2)
    nf_emissao = forms.DateField(label='Data de emissão', widget=DATA)
    arquivo = forms.FileField(label='Arquivo da nota (PDF ou foto)', required=False)


class EmpenhoDoOrcamentoForm(forms.Form):
    empenho = forms.ModelChoiceField(queryset=Empenho.objects.none(), label='Empenho', empty_label='Escolha o empenho')

    def __init__(self, *args, orcamento, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = timezone.localdate()
        consulta = Empenho.objects.filter(municipio_id=orcamento.municipio_id, finalidade='MANUTENCAO', ativo=True,
                                          vigencia_ini__lte=hoje, vigencia_fim__gte=hoje)
        if orcamento.smv.centro_custo_id:
            consulta = consulta.filter(centro_custo_id=orcamento.smv.centro_custo_id)
        self.fields['empenho'].queryset = consulta
        self.fields['empenho'].label_from_instance = lambda e: f'{e} · {e.centro_custo.codigo}'


class MensagemForm(forms.Form):
    texto = forms.CharField(label='Mensagem', required=False, widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Escreva uma mensagem'}))
    arquivo = forms.FileField(label='Foto, áudio, vídeo ou PDF', required=False)


class MotivoForm(forms.Form):
    motivo = forms.CharField(label='Motivo', widget=forms.Textarea(attrs={'rows': 2}))
