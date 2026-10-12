from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import FormularioDaPrefeitura

from .models import CategoriaVeiculo, LeituraVeiculo, Marca, Modelo, Veiculo, VeiculoEquipamento, normalizar_placa
from .services import atualizar_lotacao, registrar_leitura

DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class CategoriaVeiculoForm(FormularioDaPrefeitura):
    unicos = [('nome',)]

    class Meta:
        model = CategoriaVeiculo
        fields = ['nome', 'cnh_minima', 'usa_horimetro']
        help_texts = {'nome': 'Por exemplo: Automóvel, Caminhão, Ônibus, Motocicleta, Máquina.',
                      'cnh_minima': 'Menor categoria de CNH que pode conduzir (usada na alocação do motorista).',
                      'usa_horimetro': 'Marque para máquinas, que registram horas de uso além do km.'}
        widgets = {'nome': forms.TextInput}


class VeiculoForm(FormularioDaPrefeitura):
    unicos = [('placa',)]
    aceita_pontuacao = {'placa': 10}  # aceita " abc-1d23 "; o sistema guarda ABC1D23
    grupos = (
        ('Identificação', ('placa', 'prefixo', 'patrimonio', 'renavam', 'chassi', 'modelo', 'categoria', 'combustivel',
                           'ano_fabricacao', 'ano_modelo', 'cor')),
        ('Situação e lotação', ('tipo_frota', 'situacao', 'secretaria', 'unidade', 'centro_custo', 'estado_conservacao',
                                'proprietario', 'contrato_locacao')),
        ('Dados técnicos', ('motor', 'transmissao', 'capacidade_tanque', 'consumo_referencia', 'capacidade_passageiros',
                            'odometro_atual', 'horimetro_atual', 'km_entrada')),
        ('Valores', ('valor_fipe', 'valor_aquisicao', 'valor_aluguel_mensal', 'data_aquisicao')),
        ('Baixa', ('data_baixa', 'motivo_baixa')),
    )

    class Meta:
        model = Veiculo
        fields = ['placa', 'prefixo', 'patrimonio', 'modelo', 'categoria', 'combustivel', 'tipo_frota', 'situacao',
                  'secretaria', 'unidade', 'centro_custo', 'ano_fabricacao', 'ano_modelo', 'cor', 'renavam', 'chassi',
                  'motor', 'transmissao', 'capacidade_tanque', 'consumo_referencia', 'capacidade_passageiros',
                  'odometro_atual', 'horimetro_atual', 'km_entrada', 'estado_conservacao', 'proprietario',
                  'contrato_locacao', 'valor_fipe', 'valor_aquisicao', 'valor_aluguel_mensal', 'data_aquisicao',
                  'data_baixa', 'motivo_baixa']
        labels = {'centro_custo': 'Centro de custo'}
        widgets = {'data_aquisicao': DATA, 'data_baixa': DATA, 'proprietario': forms.TextInput,
                   'motivo_baixa': forms.Textarea(attrs={'rows': 2})}
        help_texts = {
            'placa': 'ABC1234 ou ABC1D23. O hífen é ignorado.',
            'centro_custo': 'Define o fiscal e o saldo de empenho usados na manutenção.',
            'odometro_atual': 'Km de hoje. Depois do cadastro, o km só muda por leitura (registrada na página do veículo) e nunca diminui.',
            'km_entrada': 'Opcional.',
            'modelo': 'Se não estiver na lista, cadastre em Marcas e modelos.',
            'proprietario': 'Para veículos locados, cedidos ou estaduais.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modelo'].queryset = Modelo.objects.select_related('marca')  # catalogo global (sem prefeitura)
        self.fields['categoria'].queryset = self.fields['categoria'].queryset.filter(ativo=True)
        if self.instance.pk:  # km e horimetro so mudam por leitura
            del self.fields['odometro_atual']
            del self.fields['horimetro_atual']

    def clean_placa(self):
        return normalizar_placa(self.cleaned_data['placa'])  # a conferencia de duplicidade usa a placa ja normalizada

    def save(self, commit=True):
        novo = self.instance.pk is None
        veiculo = super().save(commit=commit)
        if commit:
            atualizar_lotacao(veiculo)
            if novo and (veiculo.odometro_atual or veiculo.horimetro_atual):
                # a leitura inicial entra no historico (o km ja esta no cadastro, entao so registramos o primeiro ponto)
                LeituraVeiculo.objects.create(
                    municipio_id=veiculo.municipio_id, veiculo=veiculo, odometro=veiculo.odometro_atual,
                    horimetro=veiculo.horimetro_atual, origem='MANUAL')
        return veiculo


class EquipamentoForm(forms.ModelForm):
    class Meta:
        model = VeiculoEquipamento
        fields = ['descricao', 'observacao']
        widgets = {'observacao': forms.TextInput}
        help_texts = {'descricao': 'Ar-condicionado, rádio comunicador, roda de liga leve...'}


class LeituraForm(forms.Form):
    odometro = forms.IntegerField(label='Km', required=False, min_value=0)
    horimetro = forms.DecimalField(label='Horímetro', required=False, min_value=0, max_digits=10, decimal_places=1)

    def __init__(self, *args, veiculo, **kwargs):
        super().__init__(*args, **kwargs)
        self.veiculo = veiculo
        if not veiculo.usa_horimetro:
            del self.fields['horimetro']

    def clean(self):
        dados = super().clean()
        if dados.get('odometro') is None and dados.get('horimetro') is None:
            raise ValidationError('Informe o km ou o horímetro.')
        return dados

    def registrar(self):
        registrar_leitura(veiculo=self.veiculo, odometro=self.cleaned_data.get('odometro'),
                          horimetro=self.cleaned_data.get('horimetro'))


class AnexoForm(forms.Form):
    CATEGORIAS = [('CRLV', 'CRLV'), ('FOTO', 'Foto'), ('OUTRO', 'Outro')]
    categoria = forms.ChoiceField(label='Tipo', choices=CATEGORIAS)
    arquivo = forms.FileField(label='Arquivo')


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ['nome']
        widgets = {'nome': forms.TextInput}

    def clean_nome(self):
        nome = self.cleaned_data['nome'].strip()
        if Marca.objects.filter(nome__iexact=nome).exists():
            raise ValidationError('Essa marca já existe.')
        return nome


class ModeloForm(forms.ModelForm):
    class Meta:
        model = Modelo
        fields = ['marca', 'nome']
        widgets = {'nome': forms.TextInput}

    def clean(self):
        dados = super().clean()
        if dados.get('marca') and dados.get('nome') and Modelo.objects.filter(marca=dados['marca'], nome__iexact=dados['nome'].strip()).exists():
            raise ValidationError('Esse modelo já existe nessa marca.')
        return dados
