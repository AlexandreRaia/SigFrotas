from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from .forms import (CentroCustoForm, FiltroAuditoriaForm, LoginForm, NovaSenhaForm, SecretariaForm, UnidadeForm,
                    UsuarioEdicaoForm, UsuarioNovoForm)
from .formatos import valor_da_coluna
from .htmx import ParcialMixin, com_mensagem, e_htmx, redirecionar
from .models import Anexo, Auditoria, CentroCusto, Municipio, Secretaria, Unidade, Usuario
from .services import registrar_consulta


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

    def handle_no_permission(self):
        if e_htmx(self.request) and not self.request.user.is_authenticated:  # sessao expirou no meio do uso
            return redirecionar(redirect_to_login(self.request.get_full_path(), self.get_login_url())['Location'])
        return super().handle_no_permission()


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


def valores_da_linha(objeto, colunas):
    """colunas: (atributo, cabecalho) ou (atributo, cabecalho, 'moeda')."""
    return [valor_da_coluna(objeto, coluna[0], coluna[2] if len(coluna) > 2 else None) for coluna in colunas]


class Lista(ParcialMixin, PermissaoMixin, DaPrefeituraMixin, PaginacaoMixin, ListView):
    template_name = 'core/lista.html'
    template_parcial = 'core/_lista_tabela.html'
    paginate_by = 50
    base = ''           # prefixo dos nomes de url: <base>_lista, <base>_novo, <base>_editar, <base>_alternar
    titulo = ''
    colunas = ()        # (atributo, cabecalho[, 'moeda'])
    campos_busca = ()   # campos onde a caixa de busca procura (icontains)
    filtros = ()        # (campo, rotulo, [(valor, nome), ...]): listas de escolha acima da tabela
    escopo = None       # funcao(usuario, queryset) que limita o que o perfil enxerga
    pode_criar = True
    anotacoes = None    # dict de annotate() para colunas calculadas (ex.: saldo)
    detalhe = False     # True: cada linha tem o link "Abrir" para <base>_detalhe
    tem_alternar = True  # False: o cadastro nao tem inativar/reativar
    ligar = ()          # select_related adicional (ex.: 'modelo__marca' quando o __str__ usa o relacionamento)
    permissao_gerir = None  # quem cria/edita (a lista pode ser vista por quem so tem "ver")

    def get_queryset(self):
        consulta = super().get_queryset()
        if self.escopo:
            consulta = self.escopo(self.request.user, consulta)
        if self.anotacoes:
            consulta = consulta.annotate(**self.anotacoes)
        # Uma consulta so, com os cadastros ligados (secretaria, perfil...) que aparecem nas colunas.
        ligados = []
        for coluna in self.colunas:
            try:
                primeiro = coluna[0].split('.')[0]
                if self.model._meta.get_field(primeiro).many_to_one:
                    ligados.append(primeiro)
            except FieldDoesNotExist:
                pass  # coluna calculada
        consulta = consulta.select_related(*ligados, *self.ligar)
        busca = self.request.GET.get('busca', '').strip()
        if busca and self.campos_busca:
            condicao = Q()
            for campo in self.campos_busca:
                condicao |= Q(**{f'{campo}__icontains': busca})
            consulta = consulta.filter(condicao)
        for campo, _, _ in self.filtros:
            valor = self.request.GET.get(campo, '')
            if valor:
                consulta = consulta.filter(**{campo: valor})
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['linhas'] = [(obj, valores_da_linha(obj, self.colunas)) for obj in contexto['object_list']]
        contexto.update(
            base=self.base, titulo=self.titulo, cabecalhos=[c[1] for c in self.colunas],
            tem_busca=bool(self.campos_busca), busca=self.request.GET.get('busca', ''),
            pode_gerir=self.request.user.tem_permissao(self.permissao_gerir or self.permissao),
            detalhe=self.detalhe, tem_alternar=self.tem_alternar,
            filtros=[(campo, rotulo, opcoes, self.request.GET.get(campo, '')) for campo, rotulo, opcoes in self.filtros],
        )
        contexto['pode_criar'] = self.pode_criar and contexto['pode_gerir']
        return contexto


class CadastroMixin(ParcialMixin, PermissaoMixin):
    template_name = 'core/form.html'
    template_parcial = 'core/_form.html'   # formulario com erros volta sozinho, sem recarregar a pagina
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
        resposta = super().form_valid(form)
        return redirecionar(resposta.url) if e_htmx(self.request) else resposta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(base=self.base, titulo=self.titulo)
        return contexto


class Novo(CadastroMixin, CreateView):
    pass


class Editar(CadastroMixin, DaPrefeituraMixin, UpdateView):
    pass


class Alternar(PermissaoMixin, View):
    """Inativa ou reativa (nada e apagado). Com HTMX troca so a linha da tabela."""
    model = None
    base = ''
    colunas = ()
    detalhe = False

    def post(self, request, pk):
        objeto = get_object_or_404(self.model, pk=pk, municipio_id=request.user.municipio_id)
        if objeto == request.user:
            texto, tipo = 'Você não pode inativar o seu próprio usuário.', 'error'
        else:
            objeto.ativo = not objeto.ativo
            campos = ['ativo']
            if any(c.name == 'atualizado_em' for c in objeto._meta.fields):
                campos.append('atualizado_em')
            objeto.save(update_fields=campos)
            texto, tipo = ('Cadastro ativado.' if objeto.ativo else 'Cadastro inativado.'), 'success'
        if e_htmx(request):
            linha = render(request, 'core/_linha.html', {
                'obj': objeto, 'valores': valores_da_linha(objeto, self.colunas), 'base': self.base,
                'pode_gerir': True, 'detalhe': self.detalhe, 'tem_alternar': True})
            return com_mensagem(linha, texto, tipo)
        getattr(messages, tipo)(request, texto)
        return redirect(f'{self.base}_lista')


def rotas_cadastro(base, model, form, titulo, titulo_singular, colunas, permissao, *, ver=None, alternar=True,
                   escopo=None, campos_busca=(), filtros=(), anotacoes=None, detalhe=False, ligar=()):
    """Gera lista/novo/editar/alternar de um cadastro.

    permissao: quem cria e edita. ver: quem enxerga a lista (padrao: a mesma). escopo: limita o que cada perfil ve.
    detalhe=True: a lista tem link para <base>_detalhe (a pagina de detalhe e escrita a parte).
    """
    rotas = dict(
        lista=Lista.as_view(model=model, base=base, titulo=titulo, colunas=colunas, permissao=ver or permissao,
                            permissao_gerir=permissao, escopo=escopo, campos_busca=campos_busca, filtros=filtros,
                            anotacoes=anotacoes, detalhe=detalhe, tem_alternar=alternar, ligar=ligar),
        novo=Novo.as_view(model=model, form_class=form, base=base, titulo=f'Novo: {titulo_singular}', permissao=permissao),
        editar=Editar.as_view(model=model, form_class=form, base=base, titulo=f'Editar: {titulo_singular}', permissao=permissao),
    )
    if alternar:
        rotas['alternar'] = Alternar.as_view(model=model, base=base, colunas=colunas, permissao=permissao, detalhe=detalhe)
    return rotas


CADASTROS = {
    'secretarias': rotas_cadastro('secretarias', Secretaria, SecretariaForm, 'Secretarias', 'secretaria',
                                  (('sigla', 'Sigla'), ('nome', 'Nome'), ('ativo', 'Situação')), 'estrutura.gerir'),
    'unidades': rotas_cadastro('unidades', Unidade, UnidadeForm, 'Unidades', 'unidade',
                               (('secretaria.sigla', 'Secretaria'), ('nome', 'Nome'), ('ativo', 'Situação')), 'estrutura.gerir'),
    'centros_custo': rotas_cadastro('centros_custo', CentroCusto, CentroCustoForm, 'Centros de custo', 'centro de custo',
                                    (('codigo', 'Código'), ('nome', 'Nome'), ('secretaria.sigla', 'Secretaria'), ('ativo', 'Situação')),
                                    'estrutura.gerir'),
    'usuarios': rotas_cadastro('usuarios', Usuario, UsuarioEdicaoForm, 'Usuários', 'usuário',
                               (('nome', 'Nome'), ('email', 'E-mail'), ('perfil', 'Perfil'), ('ativo', 'Situação')),
                               'usuarios.gerir'),
}
# usuario novo tem senha inicial
CADASTROS['usuarios']['novo'] = Novo.as_view(model=Usuario, form_class=UsuarioNovoForm, base='usuarios',
                                             titulo='Novo: usuário', permissao='usuarios.gerir')


class RedefinirSenha(PermissaoMixin, View):
    permissao = 'usuarios.gerir'

    def pagina(self, request, form, usuario):
        modelo = 'core/_form.html' if e_htmx(request) else 'core/form.html'
        return render(request, modelo, {'form': form, 'base': 'usuarios', 'titulo': f'Redefinir senha: {usuario.nome}'})

    def get(self, request, pk):
        usuario = get_object_or_404(Usuario, pk=pk, municipio_id=request.user.municipio_id)
        return self.pagina(request, NovaSenhaForm(usuario=usuario), usuario)

    def post(self, request, pk):
        usuario = get_object_or_404(Usuario, pk=pk, municipio_id=request.user.municipio_id)
        form = NovaSenhaForm(request.POST, usuario=usuario)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['senha'])
            usuario.save(update_fields=['password', 'atualizado_em'])
            messages.success(request, 'Senha redefinida.')
            return redirecionar(reverse('usuarios_lista')) if e_htmx(request) else redirect('usuarios_lista')
        return self.pagina(request, form, usuario)


class ListaAuditoria(ParcialMixin, PermissaoMixin, PaginacaoMixin, ListView):
    permissao = 'auditoria.ver'
    model = Auditoria
    template_name = 'core/auditoria.html'
    template_parcial = 'core/_auditoria_tabela.html'
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


# Quem pode baixar anexo de cada tipo de registro (entidade sem regra: qualquer usuario da prefeitura).
PERMISSAO_DO_ANEXO = {'veiculos': 'frota.ver', 'motoristas': 'pessoas.dados_pessoais'}


@login_required
def baixar_anexo(request, pk):
    anexo = get_object_or_404(Anexo, pk=pk, municipio_id=request.user.municipio_id)
    permissao = PERMISSAO_DO_ANEXO.get(anexo.entidade)
    if permissao and not request.user.tem_permissao(permissao):
        raise PermissionDenied
    # tambem precisa enxergar o registro dono do anexo (escopo por secretaria, centro de custo...)
    if anexo.entidade == 'veiculos':
        from apps.frota.views import _veiculo
        _veiculo(request, anexo.entidade_id)
    elif anexo.entidade == 'motoristas':
        from apps.pessoas.views import _motorista
        registrar_consulta(usuario=request.user, objeto=_motorista(request, anexo.entidade_id), detalhe=f'anexo {anexo.pk}')
    return FileResponse(anexo.arquivo.open('rb'), as_attachment=True, filename=anexo.nome_arquivo)
