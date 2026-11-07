from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from .forms import (CentroCustoForm, FiltroAuditoriaForm, LoginForm, NovaSenhaForm, SecretariaForm, UnidadeForm,
                    UsuarioEdicaoForm, UsuarioNovoForm)
from .formatos import valor_da_coluna
from .htmx import ParcialMixin, com_mensagem, e_htmx, redirecionar
from .models import Anexo, Auditoria, CentroCusto, Municipio, Notificacao, Secretaria, Unidade, Usuario
from .services import registrar_consulta
from .templatetags.sigfrotas import selo


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
    catalogo_global = False  # True so para marcas e modelos: catalogo compartilhado, sem municipio_id

    def get_queryset(self):
        consulta = super().get_queryset()
        return consulta if self.catalogo_global else consulta.filter(municipio_id=self.request.user.municipio_id)


class PaginacaoMixin:
    """Guarda os filtros da URL nos links de pagina."""

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        filtros = self.request.GET.copy()
        filtros.pop('page', None)
        contexto['filtros_url'] = filtros.urlencode() + '&' if filtros else ''
        return contexto


def tem_rota(nome):
    """O cadastro tem essa tela? (ex.: chamados nao tem 'editar': muda pela pagina do chamado)"""
    try:
        reverse(nome, args=[0])
        return True
    except NoReverseMatch:
        return False


# Colunas de situacao: aparecem como etiqueta colorida (a cor vem do codigo, ex.: APROVADO -> verde)
COLUNAS_COM_SELO = {'status', 'etapa', 'situacao', 'prioridade'}


def valores_da_linha(objeto, colunas):
    """colunas: (atributo, cabecalho) ou (atributo, cabecalho, 'moeda'). Devolve (valor, classe do selo ou '')."""
    valores = []
    for coluna in colunas:
        valor, classe = valor_da_coluna(objeto, coluna[0], coluna[2] if len(coluna) > 2 else None), ''
        if valor is True or valor is False:
            valor, classe = ('Ativo', 'selo-ativo') if valor else ('Inativo', 'selo-inativo')
        elif coluna[0] in COLUNAS_COM_SELO and valor != '':
            classe = selo(getattr(objeto, coluna[0]))
        valores.append((valor, classe))
    return valores


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
    link_filho = None   # (url da lista filha, parametro do filtro, icone, titulo): atalho na linha (ex.: ver os modelos da marca)
    repassar_ao_novo = ()  # filtros que o botao "+" leva para o formulario (ex.: a marca escolhida)
    texto_vazio = 'Nada encontrado.'

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
        ordem = self.request.GET.get('ordem', '')
        if ordem.lstrip('-') in self.campos_ordenaveis():
            consulta = consulta.order_by(ordem.replace('.', '__'), 'pk')
        elif not consulta.ordered:  # com annotate() o Django ignora a ordem padrao do modelo
            consulta = consulta.order_by(*self.model._meta.ordering, 'pk')
        return consulta

    def campos_ordenaveis(self):
        """Colunas que viram ordenacao no banco: campos do modelo (inclusive 'secretaria.sigla') e colunas anotadas."""
        campos = set()
        for coluna in self.colunas:
            modelo, partes = self.model, coluna[0].split('.')
            if self.anotacoes and coluna[0] in self.anotacoes:
                campos.add(coluna[0])
                continue
            for i, parte in enumerate(partes):
                try:
                    campo = modelo._meta.get_field(parte)
                except FieldDoesNotExist:
                    break
                if i < len(partes) - 1 and not campo.is_relation:
                    break
                modelo = campo.related_model
            else:
                campos.add(coluna[0])
        return campos

    def colunas_do_cabecalho(self):
        """(rotulo, link para ordenar ou None, sentido atual): clicar alterna crescente/decrescente."""
        ordem, ordenaveis, colunas = self.request.GET.get('ordem', ''), self.campos_ordenaveis(), []
        for coluna in self.colunas:
            if coluna[0] not in ordenaveis:
                colunas.append((coluna[1], None, 'none'))
                continue
            sentido = 'ascending' if ordem == coluna[0] else 'descending' if ordem == '-' + coluna[0] else 'none'
            parametros = self.request.GET.copy()
            parametros.pop('page', None)
            parametros['ordem'] = ('-' if sentido == 'ascending' else '') + coluna[0]
            colunas.append((coluna[1], '?' + parametros.urlencode(), sentido))
        return colunas

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['linhas'] = [(obj, valores_da_linha(obj, self.colunas)) for obj in contexto['object_list']]
        contexto.update(
            base=self.base, titulo=self.titulo, cabecalhos=self.colunas_do_cabecalho(),
            tem_busca=bool(self.campos_busca), busca=self.request.GET.get('busca', ''),
            pode_gerir=self.request.user.tem_permissao(self.permissao_gerir or self.permissao),
            detalhe=self.detalhe, tem_alternar=self.tem_alternar, tem_editar=tem_rota(f'{self.base}_editar'),
            # opcoes pode ser uma funcao (lista que vem do banco, ex.: as marcas), chamada so ao abrir a tela
            filtros=[(campo, rotulo, opcoes() if callable(opcoes) else opcoes, self.request.GET.get(campo, ''))
                     for campo, rotulo, opcoes in self.filtros],
            link_filho=self.link_filho, texto_vazio=self.texto_vazio,
            parametros_novo='&'.join(f'{c}={self.request.GET[c]}' for c in self.repassar_ao_novo if self.request.GET.get(c, '').isdigit()),
        )
        contexto['pode_criar'] = self.pode_criar and contexto['pode_gerir']
        return contexto


class CadastroMixin(ParcialMixin, PermissaoMixin):
    template_name = 'core/form.html'
    template_parcial = 'core/_form.html'   # formulario com erros volta sozinho, sem recarregar a pagina
    base = ''
    titulo = ''
    catalogo_global = False   # marcas e modelos: sem prefeitura (o formulario nao recebe municipio_id)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.catalogo_global:
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
    repassar_ao_novo = ()  # campos que podem vir preenchidos pela url (?marca=3)

    def get_initial(self):
        inicial = super().get_initial()
        for campo in self.repassar_ao_novo:
            if self.request.GET.get(campo, '').isdigit():
                inicial[campo] = self.request.GET[campo]
        return inicial


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
                'pode_gerir': True, 'detalhe': self.detalhe, 'tem_alternar': True, 'tem_editar': tem_rota(f'{self.base}_editar')})
            return com_mensagem(linha, texto, tipo)
        getattr(messages, tipo)(request, texto)
        return redirect(f'{self.base}_lista')


def rotas_cadastro(base, model, form, titulo, titulo_singular, colunas, permissao, *, ver=None, alternar=True,
                   escopo=None, campos_busca=(), filtros=(), anotacoes=None, detalhe=False, ligar=(),
                   catalogo_global=False, link_filho=None, repassar_ao_novo=(), texto_vazio='Nada encontrado.'):
    """Gera lista/novo/editar/alternar de um cadastro.

    permissao: quem cria e edita. ver: quem enxerga a lista (padrao: a mesma). escopo: limita o que cada perfil ve.
    detalhe=True: a lista tem link para <base>_detalhe (a pagina de detalhe e escrita a parte).
    catalogo_global=True: tabela compartilhada por todas as prefeituras (sem municipio_id): marcas e modelos.
    link_filho / repassar_ao_novo: ver Lista.
    """
    rotas = dict(
        lista=Lista.as_view(model=model, base=base, titulo=titulo, colunas=colunas, permissao=ver or permissao,
                            permissao_gerir=permissao, escopo=escopo, campos_busca=campos_busca, filtros=filtros,
                            anotacoes=anotacoes, detalhe=detalhe, tem_alternar=alternar, ligar=ligar,
                            catalogo_global=catalogo_global, link_filho=link_filho, repassar_ao_novo=repassar_ao_novo,
                            texto_vazio=texto_vazio),
        novo=Novo.as_view(model=model, form_class=form, base=base, titulo=f'Novo: {titulo_singular}', permissao=permissao,
                          catalogo_global=catalogo_global, repassar_ao_novo=repassar_ao_novo),
        editar=Editar.as_view(model=model, form_class=form, base=base, titulo=f'Editar: {titulo_singular}', permissao=permissao,
                              catalogo_global=catalogo_global),
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
PERMISSAO_DO_ANEXO = {'veiculos': 'frota.ver', 'motoristas': 'pessoas.dados_pessoais', 'smv_mensagens': 'manutencao.ver',
                      'orcamentos': 'manutencao.ver'}


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
    elif anexo.entidade == 'smv_mensagens':  # anexo de mensagem do chat: precisa enxergar a SMV
        from apps.manutencao.models import SmvMensagem
        from apps.manutencao.views import _smv
        _smv(request, get_object_or_404(SmvMensagem, pk=anexo.entidade_id, municipio_id=request.user.municipio_id).smv_id)
    elif anexo.entidade == 'orcamentos':  # nota fiscal
        from apps.manutencao.views import _orcamento
        _orcamento(request, anexo.entidade_id)
    return FileResponse(anexo.arquivo.open('rb'), as_attachment=True, filename=anexo.nome_arquivo)

# --- Notificacoes (o sino do cabecalho) --------------------------------------------------------

class ListaNotificacoes(LoginRequiredMixin, PaginacaoMixin, ListView):
    template_name = 'core/notificacoes.html'
    paginate_by = 30

    def get_queryset(self):
        return Notificacao.objects.filter(usuario=self.request.user, canal='APP')


@login_required
def abrir_notificacao(request, pk):
    """Marca como lida e vai para a pagina do aviso."""
    aviso = get_object_or_404(Notificacao, pk=pk, usuario=request.user, canal='APP')
    if aviso.status != 'LIDA':
        aviso.status = 'LIDA'
        aviso.save(update_fields=['status'])
    destino = aviso.link if aviso.link.startswith('/') and not aviso.link.startswith('//') else reverse('notificacoes')
    return redirect(destino)


@login_required
@require_POST
def ler_todas_notificacoes(request):
    Notificacao.objects.filter(usuario=request.user, canal='APP').exclude(status='LIDA').update(status='LIDA')
    return redirect('notificacoes')