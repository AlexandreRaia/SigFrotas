from django import forms

from apps.core.forms import FormularioDaPrefeitura
from apps.core.models import Usuario
from apps.core.validadores import so_digitos, validar_cpf

from .models import Motorista, MotoristaAfastamento, MotoristaCertificado, MotoristaPenalidade

DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class MotoristaForm(FormularioDaPrefeitura):
    unicos = [('prontuario',), ('cpf',)]
    aceita_pontuacao = {'cpf': 14, 'cep': 9}
    grupos = (
        ('Dados funcionais', ('prontuario', 'nome', 'secretaria', 'unidade', 'cargo', 'situacao', 'usuario')),
        ('Habilitação (CNH)', ('cnh_numero', 'cnh_categoria', 'cnh_emissao', 'cnh_validade', 'cnh_orgao')),
        ('Dados pessoais', ('cpf', 'rg', 'rg_emissor', 'data_nascimento', 'telefone', 'email', 'endereco', 'cep')),
    )

    class Meta:
        model = Motorista
        fields = ['prontuario', 'nome', 'cpf', 'secretaria', 'unidade', 'cargo', 'situacao', 'usuario',
                  'cnh_numero', 'cnh_categoria', 'cnh_emissao', 'cnh_validade', 'cnh_orgao',
                  'rg', 'rg_emissor', 'data_nascimento', 'telefone', 'email', 'endereco', 'cep']
        widgets = {'nome': forms.TextInput, 'cnh_emissao': DATA, 'cnh_validade': DATA, 'data_nascimento': DATA,
                   'endereco': forms.TextInput}
        help_texts = {
            'cpf': 'Só números ou com pontuação. Dado pessoal: acesso restrito e auditado.',
            'usuario': 'Opcional. Usuário com o perfil Motorista que entra no aplicativo.',
            'cnh_categoria': 'Usada para conferir se o motorista pode conduzir o veículo.',
            'cnh_validade': 'O sistema avisa antes de vencer.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = Usuario.objects.filter(
            municipio_id=self.instance.municipio_id, perfil__codigo='MOTORISTA', ativo=True)

    def clean_cpf(self):
        valor = self.cleaned_data['cpf']
        validar_cpf(valor)
        return so_digitos(valor)

    def clean_cep(self):
        return so_digitos(self.cleaned_data['cep'])


class CertificadoForm(forms.ModelForm):
    class Meta:
        model = MotoristaCertificado
        fields = ['curso', 'instituicao', 'realizado_em', 'validade']
        widgets = {'curso': forms.TextInput, 'instituicao': forms.TextInput, 'realizado_em': DATA, 'validade': DATA}


class PenalidadeForm(forms.ModelForm):
    class Meta:
        model = MotoristaPenalidade
        fields = ['descricao', 'penalidade', 'aplicada_em']
        widgets = {'descricao': forms.TextInput, 'penalidade': forms.TextInput, 'aplicada_em': DATA}


class AfastamentoForm(forms.ModelForm):
    class Meta:
        model = MotoristaAfastamento
        fields = ['tipo', 'inicio', 'fim']
        widgets = {'inicio': DATA, 'fim': DATA}


class AnexoMotoristaForm(forms.Form):
    CATEGORIAS = [('CNH', 'CNH'), ('CERTIFICADO', 'Certificado'), ('OUTRO', 'Outro')]
    categoria = forms.ChoiceField(label='Tipo', choices=CATEGORIAS)
    arquivo = forms.FileField(label='Arquivo')
