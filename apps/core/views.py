from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from .forms import (CentroCustoForm, FiltroAuditoriaForm, LoginForm, NovaSenhaForm, SecretariaForm, UnidadeForm,
                    UsuarioEdicaoForm, UsuarioNovoForm)
from .models import Anexo, Auditoria, CentroCusto, Municipio, Secretaria, Unidade, Usuario


def entrar(request):
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        dados = form.cleaned_data
        municipio = Municipio.objects.filter(slug=dados['prefeitura'], ativo=True).first()
        usuario = None
        if municipio:
            usuario = authenticate(request, municipio=municipio, email=dados['email'], password=dados['senha'])
        if usuario:
            login(request, usuario)
            request.session['municipio_id'] = usuario.municipio_id  # a partir daqui a RLS usa esta prefeitura
            destino = request.GET.get('next', '')
            if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
                destino = '/'
            return redirect(destino)
        form.add_error(None, 'Prefeitura, e-mail ou senha incorretos.')
    return render(request, 'core/entrar.html', {'form': form})


@require_POST
def sair(request):
    logout(request)
    return redirect('entrar')


@login_required
def inicio(request):
    return render(request, 'core/inicio.html')


# --- Base das telas de cadastro ---------------------------------------------

class PermissaoMixin(LoginRequiredMixin):
    permissao = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.permissao and not request.user.tem_permissao(self.permissao):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DaPrefeituraMixin:
    """Filtra sempre pela prefeitura do usuario (alem da RLS do banco)."""

    def get_queryset(self):
        return super().get_queryset().filter(municipio_id=self.request.user.municipio_id)


class PaginacaoMixin:
    """Guarda os filtros da URL nos links de pagina."""

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        filtros = self.request.GET.copy()
        filtros.pop('page', None)
        contexto['filtros_url'] = filtros.urlencode() + '&' if filtros else ''
        return contexto


class Lista(PermissaoMixin, DaPrefeituraMixin, PaginacaoMixin, ListView):
    template_name = 'core/lista.html'
    paginate_by = 50
    base = ''           # prefixo dos nomes de url: <base>_lista, <base>_novo, <base>_editar, <base>_alternar
    titulo = ''
    colunas = ()        # (atributo, cabecalho)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['linhas'] = [(obj, [getattr(obj, attr) for attr, _ in self.colunas]) for obj in contexto['object_list']]
        contexto.update(base=self.base, titulo=self.titulo, cabecalhos=[c for _, c in self.colunas])
        return contexto


class CadastroMixin(PermissaoMixin):
    template_name = 'core/form.html'
    base = ''
    titulo = ''

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['municipio_id'] = self.request.user.municipio_id
        return kwargs

    def get_success_url(self):
        return reverse(f'{self.base}_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Salvo com sucesso.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(base=self.base, titulo=self.titulo)
        return contexto


class Novo(CadastroMixin, CreateView):
    pass


class Editar(CadastroMixin, DaPrefeituraMixin, UpdateView):
    pass


class Alternar(PermissaoMixin, View):
    """Inativa ou reativa (nada e apagado)."""
    model = None
    base = ''

    def post(self, request, pk):
        objeto = get_object_or_404(self.model, pk=pk, municipio_id=request.user.municipio_id)
        if objeto == request.user:
            messages.error(request, 'Você não pode inativar o seu próprio usuário.')
        else:
            objeto.ativo = not objeto.ativo
            objeto.save(update_fields=['ativo', 'atualizado_em'])  # todos os cadastros daqui tem atualizado_em
            messages.success(request, 'Cadastro ativado.' if objeto.ativo else 'Cadastro inativado.')
        return redirect(f'{self.base}_lista')


def rotas_cadastro(base, model, form, titulo, titulo_singular, colunas, permissao):
    """Gera lista/novo/editar/alternar de um cadastro."""
    return dict(
        lista=Lista.as_view(model=model, base=base, titulo=titulo, colunas=colunas, permissao=permissao),
        novo=Novo.as_view(model=model, form_class=form, base=base, titulo=f'Novo: {titulo_singular}', permissao=permissao),
        editar=Editar.as_view(model=model, form_class=form, base=base, titulo=f'Editar: {titulo_singular}', permissao=permissao),
        alternar=Alternar.as_view(model=model, base=base, permissao=permissao),
    )


CADASTROS = {
    'secretarias': rotas_cadastro('secretarias', Secretaria, SecretariaForm, 'Secretarias', 'secretaria',
                                  (('sigla', 'Sigla'), ('nome', 'Nome'), ('ativo', 'Ativa')), 'estrutura.gerir'),
    'unidades': rotas_cadastro('unidades', Unidade, UnidadeForm, 'Unidades', 'unidade',
                               (('secretaria', 'Secretaria'), ('nome', 'Nome'), ('codigo_externo', 'Código Prime'), ('ativo', 'Ativa')),
                               'estrutura.gerir'),
    'centros_custo': rotas_cadastro('centros_custo', CentroCusto, CentroCustoForm, 'Centros de custo', 'centro de custo',
                                    (('codigo', 'Código'), ('nome', 'Nome'), ('secretaria', 'Secretaria'), ('ativo', 'Ativo')),
                                    'estrutura.gerir'),
    'usuarios': rotas_cadastro('usuarios', Usuario, UsuarioEdicaoForm, 'Usuários', 'usuário',
                               (('nome', 'Nome'), ('email', 'E-mail'), ('perfil', 'Perfil'), ('ativo', 'Ativo')),
                               'usuarios.gerir'),
}
# usuario novo tem senha inicial
CADASTROS['usuarios']['novo'] = Novo.as_view(model=Usuario, form_class=UsuarioNovoForm, base='usuarios',
                                             titulo='Novo: usuário', permissao='usuarios.gerir')


class RedefinirSenha(PermissaoMixin, View):
    permissao = 'usuarios.gerir'

    def get(self, request, pk):
        usuario = get_object_or_404(Usuario, pk=pk, municipio_id=request.user.municipio_id)
        return render(request, 'core/form.html', {'form': NovaSenhaForm(usuario=usuario), 'base': 'usuarios',
                                                  'titulo': f'Redefinir senha: {usuario.nome}'})

    def post(self, request, pk):
        usuario = get_object_or_404(Usuario, pk=pk, municipio_id=request.user.municipio_id)
        form = NovaSenhaForm(request.POST, usuario=usuario)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['senha'])
            usuario.save(update_fields=['password', 'atualizado_em'])
            messages.success(request, 'Senha redefinida.')
            return redirect('usuarios_lista')
        return render(request, 'core/form.html', {'form': form, 'base': 'usuarios',
                                                  'titulo': f'Redefinir senha: {usuario.nome}'})


class ListaAuditoria(PermissaoMixin, PaginacaoMixin, ListView):
    permissao = 'auditoria.ver'
    model = Auditoria
    template_name = 'core/auditoria.html'
    paginate_by = 50

    def get_queryset(self):
        # Auditoria nao tem FK para municipio: o campo se chama municipio_id.
        consulta = Auditoria.objects.filter(municipio_id=self.request.user.municipio_id)
        self.filtro = FiltroAuditoriaForm(self.request.GET)
        if self.filtro.is_valid():
            f = self.filtro.cleaned_data
            if f['tabela']:
                consulta = consulta.filter(tabela=f['tabela'])
            if f['registro_id']:
                consulta = consulta.filter(registro_id=f['registro_id'])
            if f['de']:
                consulta = consulta.filter(em__date__gte=f['de'])
            if f['ate']:
                consulta = consulta.filter(em__date__lte=f['ate'])
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['filtro'] = self.filtro
        ids = {a.usuario_id for a in contexto['object_list'] if a.usuario_id}
        nomes = dict(Usuario.objects.filter(pk__in=ids, municipio_id=self.request.user.municipio_id).values_list('pk', 'nome'))
        for registro in contexto['object_list']:
            registro.usuario_nome = nomes.get(registro.usuario_id, 'sistema' if registro.usuario_id is None else f'#{registro.usuario_id}')
        return contexto


@login_required
def baixar_anexo(request, pk):
    # TODO(fase de cada modulo): conferir tambem a permissao sobre o registro ao qual o anexo pertence.
    anexo = get_object_or_404(Anexo, pk=pk, municipio_id=request.user.municipio_id)
    return FileResponse(anexo.arquivo.open('rb'), as_attachment=True, filename=anexo.nome_arquivo)
