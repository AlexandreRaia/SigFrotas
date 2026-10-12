from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

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

    def __init__(self, *args, municipio_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.municipio_id = municipio_id
        for campo in self.fields.values():  # listas de escolha so mostram registros da propria prefeitura
            queryset = getattr(campo, 'queryset', None)
            if queryset is not None:
                campo.queryset = queryset.filter(municipio_id=municipio_id)

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


class UnidadeForm(FormularioDaPrefeitura):
    unicos = [('secretaria', 'nome')]

    class Meta:
        model = Unidade
        fields = ['secretaria', 'nome', 'codigo_externo']


class CentroCustoForm(FormularioDaPrefeitura):
    unicos = [('codigo',)]

    class Meta:
        model = CentroCusto
        fields = ['secretaria', 'codigo', 'nome', 'codigo_externo']


class UsuarioEdicaoForm(FormularioDaPrefeitura):
    unicos = [('email',)]

    class Meta:
        model = Usuario
        fields = ['nome', 'email', 'perfil', 'secretaria', 'unidade', 'matricula']


class UsuarioNovoForm(UsuarioEdicaoForm):
    senha = forms.CharField(label='Senha inicial', widget=forms.PasswordInput)

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
