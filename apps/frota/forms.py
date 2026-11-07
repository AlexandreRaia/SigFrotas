from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction

from apps.core.forms import FormularioDaPrefeitura
from apps.core.models import Anexo
from apps.core.services import anexar

from .models import CategoriaVeiculo, LeituraVeiculo, Marca, Modelo, Veiculo, VeiculoEquipamento, normalizar_placa
from .services import atualizar_lotacao, registrar_leitura

DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
EXTENSOES_DOCUMENTO = ('pdf', 'jpg', 'jpeg', 'png')
EXTENSOES_FOTO = ('jpg', 'jpeg', 'png', 'webp')
# categoria gravada no anexo -> rotulo (as fotos do cadastro do veiculo; as outras vem da pagina do veiculo)
FOTOS_DO_VEICULO = {'FOTO_FRENTE': 'Frente', 'FOTO_LATERAL_ESQ': 'Lateral esquerda', 'FOTO_LATERAL_DIR': 'Lateral direita',
                    'FOTO_TRASEIRA': 'Traseira', 'FOTO_HODOMETRO': 'Hodômetro'}


class CategoriaVeiculoForm(FormularioDaPrefeitura):
    unicos = [('nome',)]

    class Meta:
        model = CategoriaVeiculo
        fields = ['nome', 'cnh_minima']
        help_texts = {'nome': 'Por exemplo: Automóvel, Caminhão, Ônibus, Motocicleta, Máquina.',
                      'cnh_minima': 'Menor categoria de CNH que pode conduzir (usada na alocação do motorista).'}
        widgets = {'nome': forms.TextInput}


class VeiculoForm(FormularioDaPrefeitura):
    unicos = [('placa',)]
    aceita_pontuacao = {'placa': 10}  # aceita " abc-1d23 "; o sistema guarda ABC1D23
    # Marca nao e coluna do veiculo (vem do modelo): serve para escolher o modelo e nao e gravada
    marca = forms.ModelChoiceField(queryset=Marca.objects.all(), required=False, label='Marca')
    # Arquivos enviados no cadastro: viram anexos do veiculo (nao sao colunas)
    crlv = forms.FileField(required=False, label='CRLV', validators=[FileExtensionValidator(EXTENSOES_DOCUMENTO)])
    foto_frente = forms.FileField(required=False, label='Frente', validators=[FileExtensionValidator(EXTENSOES_FOTO)])
    foto_lateral_esq = forms.FileField(required=False, label='Lateral esquerda', validators=[FileExtensionValidator(EXTENSOES_FOTO)])
    foto_lateral_dir = forms.FileField(required=False, label='Lateral direita', validators=[FileExtensionValidator(EXTENSOES_FOTO)])
    foto_traseira = forms.FileField(required=False, label='Traseira', validators=[FileExtensionValidator(EXTENSOES_FOTO)])
    foto_hodometro = forms.FileField(required=False, label='Hodômetro', validators=[FileExtensionValidator(EXTENSOES_FOTO)])
    # Assistente em 8 etapas: (titulo, ((campo, colunas de 3), ...)). Campo que ficar de fora vai para a ultima etapa.
    etapas = (
        ('Identificação', (('placa', 1), ('prefixo', 1), ('patrimonio', 1), ('renavam', 1), ('chassi', 2), ('marca', 1), ('modelo', 1),
                           ('categoria', 1), ('ano_fabricacao', 1), ('ano_modelo', 1), ('cor', 1))),
        ('Abastecimento', (('combustivel', 1), ('capacidade_tanque', 1), ('consumo_referencia', 1))),
        ('Situação', (('tipo_frota', 1), ('situacao', 1), ('estado_conservacao', 1), ('proprietario', 2),
                      ('contrato_locacao', 1), ('data_baixa', 1), ('motivo_baixa', 2))),
        ('Lotação', (('secretaria', 1), ('unidade', 1), ('centro_custo', 1))),
        ('Dados técnicos', (('motor', 1), ('transmissao', 1), ('capacidade_passageiros', 1),
                            ('capacidade_carga_kg', 1), ('tracao', 1), ('medida_pneu', 1),
                            ('intervalo_revisao_km', 1), ('intervalo_revisao_meses', 1), ('tag', 1),
                            ('rastreador', 1), ('km_entrada', 1), ('odometro_atual', 1),
                            ('autonomia_km', 1), ('capacidade_bateria_kwh', 1))),   # os dois ultimos so aparecem para eletricos
        ('Valores', (('valor_fipe', 1), ('valor_aquisicao', 1), ('valor_aluguel_mensal', 1), ('data_aquisicao', 1))),
        ('Documentos', (('vencimento_ipva', 1), ('vencimento_licenciamento', 1), ('vencimento_seguro', 1),
                        ('crlv', 1))),
        ('Fotos', (('foto_frente', 1), ('foto_lateral_esq', 1), ('foto_lateral_dir', 1),
                   ('foto_traseira', 1), ('foto_hodometro', 1))),
    )
    exemplos = {'placa': 'ABC-1D23', 'prefixo': 'V-001', 'chassi': '17 caracteres', 'ano_fabricacao': '2024', 'ano_modelo': '2024',
               'medida_pneu': '205/55 R16', 'intervalo_revisao_km': '10000', 'intervalo_revisao_meses': '6'}

    class Meta:
        model = Veiculo
        fields = ['placa', 'prefixo', 'patrimonio', 'modelo', 'categoria', 'combustivel', 'tipo_frota', 'situacao',
                  'secretaria', 'unidade', 'centro_custo', 'ano_fabricacao', 'ano_modelo', 'cor', 'renavam', 'chassi',
                  'motor', 'transmissao', 'capacidade_tanque', 'consumo_referencia', 'capacidade_passageiros',
                  'capacidade_carga_kg', 'tracao', 'medida_pneu', 'intervalo_revisao_km', 'intervalo_revisao_meses',
                  'rastreador', 'tag', 'autonomia_km', 'capacidade_bateria_kwh', 'km_entrada', 'odometro_atual', 'estado_conservacao', 'proprietario',
                  'contrato_locacao', 'valor_fipe', 'valor_aquisicao', 'valor_aluguel_mensal', 'data_aquisicao',
                  'data_baixa', 'motivo_baixa', 'vencimento_ipva', 'vencimento_licenciamento', 'vencimento_seguro']
        labels = {'vencimento_ipva': 'Vencimento do IPVA', 'vencimento_licenciamento': 'Vencimento do licenciamento',
                  'vencimento_seguro': 'Vencimento do seguro', 'tag': 'Tag', 'rastreador': 'Rastreador',
                  'centro_custo': 'Centro de custo', 'combustivel': 'Combustível', 'unidade': 'Setor/Departamento',
                  'km_entrada': 'Km/Horímetro de entrada na frota', 'odometro_atual': 'Km/Horímetro atual', 'renavam': 'Renavam'}
        widgets = {'data_aquisicao': DATA, 'data_baixa': DATA, 'vencimento_ipva': DATA, 'vencimento_licenciamento': DATA,
                   'vencimento_seguro': DATA,
                   'motivo_baixa': forms.Textarea(attrs={'rows': 2})}
        help_texts = {
            'centro_custo': 'Define o fiscal e o saldo de empenho usados na manutenção.',
            'proprietario': 'Para veículos locados, cedidos ou estaduais. Escolha entre os fornecedores cadastrados (órgãos entram como tipo "Outro").',
        }   # o aviso do campo Modelo (onde cadastrar marcas e modelos) fica na tela, com os links

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario   # quem enviou os arquivos (fica no anexo)
        self.fields['modelo'].queryset = Modelo.objects.select_related('marca')  # catalogo global (sem prefeitura)
        self.fields['modelo'].label_from_instance = lambda modelo: modelo.nome  # a marca ja esta escolhida ao lado
        if self.instance.pk and self.instance.modelo_id:
            self.initial['marca'] = self.instance.modelo.marca_id
        self.fields['categoria'].queryset = self.fields['categoria'].queryset.filter(ativo=True)
        self.fields['proprietario'].queryset = self.fields['proprietario'].queryset.filter(ativo=True)
        for nome in ('modelo', 'categoria'):  # no banco sao opcionais (importacao, veiculos antigos), mas o cadastro pede os dois
            self.fields[nome].required = self.fields[nome].widget.is_required = True
        for nome, texto in self.exemplos.items():
            self.fields[nome].widget.attrs['placeholder'] = texto
        for campo in self.fields.values():  # listas comecam em "Selecione" em vez de "---------"
            if isinstance(campo, forms.ModelChoiceField):
                campo.empty_label = 'Selecione'
            elif isinstance(campo, forms.ChoiceField) and campo.choices and campo.choices[0][0] == '':
                campo.choices = [('', 'Selecione'), *list(campo.choices)[1:]]
        if self.instance.pk:  # km so muda por leitura
            del self.fields['odometro_atual']

    def etapas_montadas(self):
        """[{'titulo', 'campos': [(campo, colunas)], 'tem_erro'}]: so os campos que o formulario tem agora; sobras vao para a ultima etapa."""
        usados, resultado = set(), []
        for titulo, campos in self.etapas:
            usados.update(nome for nome, _ in campos)
            resultado.append({'titulo': titulo, 'campos': [(self[nome], colunas) for nome, colunas in campos if nome in self.fields]})
        resultado[-1]['campos'] += [(c, 3 if isinstance(c.field.widget, forms.Textarea) else 1)
                                    for c in self if c.name not in usados and not c.is_hidden]
        for etapa in resultado:
            etapa['tem_erro'] = any(campo.errors for campo, _ in etapa['campos'])
        return resultado

    def clean_placa(self):
        return normalizar_placa(self.cleaned_data['placa'])  # a conferencia de duplicidade usa a placa ja normalizada

    def clean(self):
        dados = super().clean()
        marca, modelo = dados.get('marca'), dados.get('modelo')
        if marca and modelo and modelo.marca_id != marca.pk:
            self.add_error('modelo', 'Esse modelo não é da marca escolhida.')
        for nome in self.CATEGORIAS_DOS_ARQUIVOS:   # tamanho conferido aqui, antes de salvar o veiculo
            for arquivo in self._arquivos_de(nome, dados):
                if arquivo.size > settings.ANEXO_TAMANHO_MAXIMO:
                    self.add_error(nome, f'"{arquivo.name}" passa do limite de {settings.ANEXO_TAMANHO_MAXIMO // (1024 * 1024)} MB.')
        return dados

    @staticmethod
    def _arquivos_de(nome, dados):
        return [dados[nome]] if dados.get(nome) else []

    CATEGORIAS_DOS_ARQUIVOS = {'crlv': 'CRLV', **{c.lower(): c for c in FOTOS_DO_VEICULO}}

    def arquivos_atuais(self):
        """{campo: [anexos, mais novos primeiro]} do veiculo em edicao: a tela mostra o que ja foi enviado."""
        if not self.instance.pk:
            return {}
        por_categoria = {}
        for anexo in Anexo.objects.filter(municipio_id=self.instance.municipio_id, entidade='veiculos',
                                          entidade_id=self.instance.pk).order_by('-criado_em', '-pk'):
            por_categoria.setdefault(anexo.categoria, []).append(anexo)
        return {nome: por_categoria.get(categoria, []) for nome, categoria in self.CATEGORIAS_DOS_ARQUIVOS.items()}

    def _guardar_arquivos(self, veiculo):
        for nome, categoria in self.CATEGORIAS_DOS_ARQUIVOS.items():
            for arquivo in self._arquivos_de(nome, self.cleaned_data):
                anexar(municipio_id=veiculo.municipio_id, entidade='veiculos', entidade_id=veiculo.pk, arquivo=arquivo,
                       categoria=categoria, enviado_por=self.usuario)

    def marca_dos_modelos(self):
        """{id do modelo: id da marca}: a tela usa para mostrar so os modelos da marca escolhida."""
        return {modelo.pk: modelo.marca_id for modelo in self.fields['modelo'].queryset}

    def save(self, commit=True):
        novo = self.instance.pk is None
        with transaction.atomic():   # veiculo e arquivos entram juntos
            veiculo = super().save(commit=commit)
            if commit:
                atualizar_lotacao(veiculo)
                if novo and veiculo.odometro_atual:
                    # a leitura inicial entra no historico (o km ja esta no cadastro, entao so registramos o primeiro ponto)
                    LeituraVeiculo.objects.create(
                        municipio_id=veiculo.municipio_id, veiculo=veiculo, odometro=veiculo.odometro_atual, origem='MANUAL')
                self._guardar_arquivos(veiculo)
        return veiculo


class EquipamentoForm(forms.ModelForm):
    class Meta:
        model = VeiculoEquipamento
        fields = ['descricao', 'observacao']
        widgets = {'observacao': forms.TextInput}
        help_texts = {'descricao': 'Ar-condicionado, rádio comunicador, roda de liga leve...'}


class LeituraForm(forms.Form):
    odometro = forms.IntegerField(label='Km/Horímetro', min_value=0)

    def __init__(self, *args, veiculo, **kwargs):
        super().__init__(*args, **kwargs)
        self.veiculo = veiculo

    def registrar(self):
        registrar_leitura(veiculo=self.veiculo, odometro=self.cleaned_data['odometro'])


class AnexoForm(forms.Form):
    CATEGORIAS = [('CRLV', 'CRLV'), ('FOTO', 'Foto'), ('OUTRO', 'Outro')]
    categoria = forms.ChoiceField(label='Tipo', choices=CATEGORIAS)
    arquivo = forms.FileField(label='Arquivo')


class MarcaForm(forms.ModelForm):
    """Marca e modelo sao catalogos globais (sem prefeitura): a view nao passa municipio_id."""
    class Meta:
        model = Marca
        fields = ['nome']
        labels = {'nome': 'Nome da marca'}
        help_texts = {'nome': 'Como aparece na lista de veículos. Depois de salvar, você adiciona os modelos dela.'}
        widgets = {'nome': forms.TextInput}

    def clean_nome(self):
        nome = self.cleaned_data['nome'].strip()
        if Marca.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Essa marca já existe.')
        return nome


class ModeloForm(forms.ModelForm):
    class Meta:
        model = Modelo
        fields = ['marca', 'nome']
        labels = {'nome': 'Nome do modelo'}
        help_texts = {'nome': 'Sem repetir a marca. Exemplo: Uno, Strada, Accelo 815.'}
        widgets = {'nome': forms.TextInput}

    def clean(self):
        dados = super().clean()
        repetido = (Modelo.objects.filter(marca=dados['marca'], nome__iexact=dados['nome'].strip()).exclude(pk=self.instance.pk)
                    if dados.get('marca') and dados.get('nome') else Modelo.objects.none())
        if repetido.exists():
            raise ValidationError('Esse modelo já existe nessa marca.')
        return dados
