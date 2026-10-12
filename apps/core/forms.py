from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator

from .models import CentroCusto, Secretaria, Unidade, Usuario


class LoginForm(forms.Form):
    prefeitura = forms.SlugField(label='Prefeitura')
    email = forms.EmailField(label='E-mail')
    senha = forms.CharField(label='Senha', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.MUNICIPIO_PADRAO_SLUG:
            self.fields['prefeitura'].initial = settings.MUNICIPIO_PADRAO_SLUG
            self.fields['prefeitura'].widget = forms.HiddenInput()


class FormularioDaPrefeitura(forms.ModelForm):
    """Formulario de cadastro da prefeitura logada. `unicos` lista combinacoes de campos que nao podem repetir."""
    unicos = ()
    aceita_pontuacao = {}  # campo -> tamanho maximo digitado (CPF/CNPJ/CEP chegam com pontuacao e sao guardados so com numeros)
    grupos = ()            # ((titulo, (campos...)), ...): divide formularios longos em secoes de varias colunas

    def agrupados(self):
        """[(titulo, [(campo, largo)])]. Campo que nao entrou em nenhum grupo vai para "Outros" (nunca some da tela)."""
        usados, resultado = set(), []
        for titulo, nomes in self.grupos:
            campos = [self[n] for n in nomes if n in self.fields]
            usados.update(nomes)
            if campos:
                resultado.append((titulo, [(c, isinstance(c.field.widget, forms.Textarea)) for c in campos]))
        restantes = [c for c in self if c.name not in usados and not c.is_hidden]
        if resultado and restantes:
            resultado.append(('Outros', [(c, isinstance(c.field.widget, forms.Textarea)) for c in restantes]))
        return resultado

    def __init__(self, *args, municipio_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.municipio_id = municipio_id
        for nome, limite in self.aceita_pontuacao.items():
            campo = self.fields[nome]
            campo.max_length = limite
            campo.widget.attrs['maxlength'] = limite
            campo.validators = [v for v in campo.validators if not isinstance(v, MaxLengthValidator)]
            campo.validators.append(MaxLengthValidator(limite))
        for campo in self.fields.values():  # listas de escolha so mostram registros da propria prefeitura
            queryset = getattr(campo, 'queryset', None)
            if queryset is not None and any(f.name == 'municipio' for f in queryset.model._meta.fields):
                campo.queryset = queryset.filter(municipio_id=municipio_id)  # catalogos globais ficam como estao

    def clean(self):
        dados = super().clean()
        for campos in self.unicos:
            filtro = {c: dados.get(c) for c in campos}
            if any(v in (None, '') for v in filtro.values()):
                continue
            existe = (self._meta.model.objects.filter(municipio_id=self.instance.municipio_id, **filtro)
                      .exclude(pk=self.instance.pk).exists())
            if existe:
                raise ValidationError('Já existe um cadastro com esses dados.')
        return dados


class SecretariaForm(FormularioDaPrefeitura):
    unicos = [('sigla',)]

    class Meta:
        model = Secretaria
        fields = ['sigla', 'nome']
        labels = {'sigla': 'Sigla', 'nome': 'Nome'}
        help_texts = {'sigla': 'Abreviação usada no dia a dia, por exemplo SMA. Não pode repetir.',
                      'nome': 'Nome por extenso da secretaria.'}
        widgets = {'nome': forms.TextInput}


class UnidadeForm(FormularioDaPrefeitura):
    unicos = [('secretaria', 'nome')]

    class Meta:
        model = Unidade
        fields = ['secretaria', 'nome']
        labels = {'secretaria': 'Secretaria', 'nome': 'Nome'}
        help_texts = {'secretaria': 'Secretaria à qual a unidade pertence.',
                      'nome': 'Divisão dentro da secretaria, por exemplo Departamento de Transportes.'}
        widgets = {'nome': forms.TextInput}


class CentroCustoForm(FormularioDaPrefeitura):
    unicos = [('codigo',)]

    class Meta:
        model = CentroCusto
        fields = ['secretaria', 'codigo', 'nome']
        labels = {'secretaria': 'Secretaria', 'codigo': 'Código', 'nome': 'Nome'}
        help_texts = {'secretaria': 'Opcional. Deixe em branco se o centro de custo atende várias secretarias.',
                      'codigo': 'Código do centro de custo como a prefeitura o conhece (contabilidade ou planilha). Não pode repetir.',
                      'nome': 'Descrição, por exemplo Frota da Secretaria de Administração.'}
        widgets = {'nome': forms.TextInput}


class UsuarioEdicaoForm(FormularioDaPrefeitura):
    unicos = [('email',)]

    class Meta:
        model = Usuario
        fields = ['nome', 'email', 'perfil', 'secretaria', 'unidade', 'matricula', 'fornecedor']
        labels = {'nome': 'Nome', 'email': 'E-mail', 'perfil': 'Perfil', 'secretaria': 'Secretaria',
                  'unidade': 'Unidade', 'matricula': 'Matrícula', 'fornecedor': 'Oficina'}
        help_texts = {'email': 'Usado para entrar no sistema.',
                      'perfil': 'Define o que a pessoa pode fazer.',
                      'secretaria': 'Opcional. Limita o que a pessoa enxerga à sua secretaria.',
                      'unidade': 'Opcional.',
                      'fornecedor': 'Só para o perfil Oficina: a oficina (fornecedor) que a pessoa representa.'}
        widgets = {'nome': forms.TextInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fornecedor'].queryset = self.fields['fornecedor'].queryset.filter(tipo='OFICINA', ativo=True)

    def clean(self):
        dados = super().clean()
        perfil, fornecedor = dados.get('perfil'), dados.get('fornecedor')
        if perfil and perfil.codigo == 'OFICINA' and not fornecedor:
            self.add_error('fornecedor', 'Informe a oficina que este usuário representa.')
        if perfil and perfil.codigo != 'OFICINA' and fornecedor:
            self.add_error('fornecedor', 'Só o perfil Oficina é ligado a uma oficina.')
        return dados


class UsuarioNovoForm(UsuarioEdicaoForm):
    senha = forms.CharField(label='Senha inicial', widget=forms.PasswordInput,
                            help_text='Mínimo de 8 caracteres. A pessoa pode ser orientada a trocá-la depois.')

    def clean_senha(self):
        senha = self.cleaned_data['senha']
        validate_password(senha)
        return senha

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data['senha'])
        if commit:
            usuario.save()
        return usuario


class NovaSenhaForm(forms.Form):
    senha = forms.CharField(label='Nova senha', widget=forms.PasswordInput)

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_senha(self):
        senha = self.cleaned_data['senha']
        validate_password(senha, self.usuario)
        return senha


class FiltroAuditoriaForm(forms.Form):
    tabela = forms.CharField(label='Tabela', required=False)
    registro_id = forms.IntegerField(label='Registro (id)', required=False)
    de = forms.DateField(label='De', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ate = forms.DateField(label='Até', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
