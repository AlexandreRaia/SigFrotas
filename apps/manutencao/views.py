from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.escopo import centros_do_fiscal
from apps.core.htmx import com_mensagem, e_htmx, redirecionar
from apps.core.models import Anexo
from apps.core.views import Lista, Novo, PermissaoMixin, rotas_cadastro
from apps.financeiro.services import saldo_do_empenho
from apps.frota.models import Veiculo

from . import services
from .forms import (CategoriaServicoForm, ChamadoForm, DiagnosticoForm, EmpenhoDoOrcamentoForm, EntregaForm, ItemOrcamentoForm,
                    MensagemForm, MotivoForm, NotaFiscalForm, SmvForm)
from .models import CategoriaServico, Chamado, DiasEmManutencao, Orcamento, OrcamentoItem, Smv, SmvMensagem

VER, ABRIR, GERIR, APROVAR, OFICINA = ('manutencao.ver', 'manutencao.abrir', 'manutencao.gerir', 'manutencao.aprovar',
                                       'manutencao.oficina')


# --- Quem ve o que ---------------------------------------------------------------------------------------------------

def _escopo(usuario, consulta, prefixo=''):
    """Gestores e Consulta veem tudo; fiscal, os seus centros de custo; gestor de unidade, a sua secretaria;
    oficina, so as SMVs dela. (prefixo: 'smv__' quando a consulta e de orcamentos.)"""
    codigo = usuario.perfil.codigo
    if usuario.tem_permissao(GERIR) or codigo == 'CONSULTA':
        return consulta
    if usuario.fornecedor_id and usuario.tem_permissao(OFICINA):
        return consulta.filter(**{f'{prefixo}fornecedor_id': usuario.fornecedor_id})
    if codigo == 'FISCAL':
        centros = centros_do_fiscal(usuario)
        return consulta if centros is None else consulta.filter(**{f'{prefixo}centro_custo_id__in': centros})
    if codigo == 'GESTOR_UNIDADE' and usuario.secretaria_id:
        return consulta.filter(**{f'{prefixo}veiculo__secretaria_id': usuario.secretaria_id})
    return consulta.none()


def escopo_smv(usuario, consulta):
    return _escopo(usuario, consulta)


def escopo_orcamentos(usuario, consulta):
    return _escopo(usuario, consulta, 'smv__')


def escopo_chamados(usuario, consulta):
    """Alem do escopo da frota, cada um ve os chamados que abriu (o motorista ve so esses) e o fiscal os que recebeu."""
    proprios = Q(aberto_por=usuario) | Q(fiscal=usuario)
    if usuario.tem_permissao(GERIR) or usuario.perfil.codigo == 'CONSULTA':
        return consulta
    codigo = usuario.perfil.codigo
    if codigo == 'FISCAL':
        centros = centros_do_fiscal(usuario)
        return consulta if centros is None else consulta.filter(proprios | Q(veiculo__centro_custo_id__in=centros))
    if codigo == 'GESTOR_UNIDADE' and usuario.secretaria_id:
        return consulta.filter(proprios | Q(veiculo__secretaria_id=usuario.secretaria_id))
    return consulta.filter(aberto_por=usuario)


def _municipio(request):
    return {'municipio_id': request.user.municipio_id}


def _chamado(request, pk):
    consulta = escopo_chamados(request.user, Chamado.objects.filter(**_municipio(request)))
    return get_object_or_404(consulta.select_related('veiculo', 'aberto_por', 'fiscal', 'analisado_por'), pk=pk)


def _smv(request, pk):
    consulta = escopo_smv(request.user, Smv.objects.filter(**_municipio(request)))
    return get_object_or_404(consulta.select_related('veiculo__modelo__marca', 'fornecedor', 'contrato', 'centro_custo', 'chamado',
                                                     'veiculo_substituto'), pk=pk)


def _orcamento(request, pk):
    consulta = escopo_orcamentos(request.user, Orcamento.objects.filter(**_municipio(request)))
    return get_object_or_404(consulta.select_related('smv__veiculo', 'smv__fornecedor', 'empenho__centro_custo'), pk=pk)


def eh_da_oficina(usuario, smv):
    return bool(usuario.fornecedor_id) and usuario.fornecedor_id == smv.fornecedor_id and usuario.tem_permissao(OFICINA)


def age_pela_oficina(usuario, smv):
    """A oficina age na propria SMV; o gestor tambem pode agir por ela (oficina sem habito de sistema, por e-mail)."""
    return eh_da_oficina(usuario, smv) or usuario.tem_permissao(GERIR)


# --- Listas ----------------------------------------------------------------------------------------------------------

DIAS = Subquery(DiasEmManutencao.objects.filter(smv_id=OuterRef('pk')).values('dias_em_manutencao')[:1])

ROTAS = {
    'categorias_servico': rotas_cadastro(
        'categorias_servico', CategoriaServico, CategoriaServicoForm, 'Categorias de serviço', 'categoria de serviço',
        (('nome', 'Nome'), ('ativo', 'Situação')), GERIR, ver=VER),
}

lista_chamados = Lista.as_view(
    model=Chamado, base='chamados', titulo='Chamados', permissao=VER, permissao_gerir=ABRIR, detalhe=True, tem_alternar=False,
    escopo=escopo_chamados, ligar=('veiculo', 'aberto_por'), campos_busca=('numero', 'descricao', 'veiculo__placa'),
    colunas=(('numero', 'Número'), ('veiculo', 'Veículo'), ('prioridade', 'Prioridade'), ('status', 'Situação'),
             ('aberto_por', 'Aberto por'), ('criado_em', 'Aberto em')),
    filtros=(('status', 'Situação', Chamado.STATUS), ('prioridade', 'Prioridade', [('BAIXA', 'Baixa'), ('NORMAL', 'Normal'),
                                                                                  ('ALTA', 'Alta'), ('URGENTE', 'Urgente')])))

lista_smv = Lista.as_view(
    model=Smv, base='smv', titulo='SMVs (manutenções)', permissao=VER, permissao_gerir=GERIR, detalhe=True, tem_alternar=False,
    escopo=escopo_smv, ligar=('veiculo', 'fornecedor'), anotacoes={'dias': DIAS},
    campos_busca=('numero', 'veiculo__placa', 'fornecedor__razao_social'),
    colunas=(('numero', 'Número'), ('veiculo', 'Veículo'), ('fornecedor', 'Oficina'), ('tipo', 'Tipo'), ('etapa', 'Etapa'),
             ('entrada_em', 'Entrada'), ('dias', 'Dias parado')),
    filtros=(('etapa', 'Etapa', Smv.ETAPAS), ('tipo', 'Tipo', Smv.TIPOS)))

lista_orcamentos = Lista.as_view(
    model=Orcamento, base='orcamentos', titulo='Orçamentos', permissao=VER, permissao_gerir=GERIR, detalhe=True, tem_alternar=False,
    pode_criar=False, escopo=escopo_orcamentos, ligar=('smv', 'smv__veiculo'), campos_busca=('numero', 'smv__numero', 'smv__veiculo__placa'),
    colunas=(('numero', 'Número'), ('revisao', 'Rev.'), ('smv', 'SMV'), ('status', 'Situação'), ('valor_total', 'Total', 'moeda')),
    filtros=(('status', 'Situação', Orcamento.STATUS),))


# --- Base das acoes (POST) -------------------------------------------------------------------------------------------

def _decimal(texto):
    """'1.234,56' ou '1234.56' -> Decimal; vazio -> None."""
    texto = (texto or '').strip()
    if not texto:
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    return Decimal(texto)


def validar(form):
    if not form.is_valid():
        raise ValidationError([m for erros in form.errors.values() for m in erros])
    return form.cleaned_data


class Acao(PermissaoMixin, View):
    """POST que chama um servico e volta para a pagina com um aviso (verde se deu certo, vermelho com o motivo se nao)."""
    permissao = VER
    sucesso = 'Feito.'

    def carregar(self, request, pk):
        raise NotImplementedError

    def autorizado(self, request, objeto):
        return True

    def destino(self, objeto):
        raise NotImplementedError

    def post(self, request, pk, **kwargs):
        objeto = self.carregar(request, pk)
        if not self.autorizado(request, objeto):
            raise PermissionDenied
        try:
            resultado = self.executar(request, objeto, **kwargs)
            messages.success(request, self.sucesso)
        except ValidationError as erro:
            messages.error(request, ' '.join(erro.messages))
            resultado = None
        return redirect(resultado or self.destino(objeto))


# --- Chamados ----------------------------------------------------------------------------------------------------------

class ChamadoNovo(Novo):
    def form_valid(self, form):
        try:
            chamado = services.abrir_chamado(veiculo=form.cleaned_data['veiculo'], usuario=self.request.user,
                                             descricao=form.cleaned_data['descricao'], prioridade=form.cleaned_data['prioridade'])
        except ValidationError as erro:
            form.add_error(None, erro)
            return self.form_invalid(form)
        messages.success(self.request, f'Chamado {chamado.numero} aberto. O fiscal do centro de custo foi avisado.')
        destino = reverse('chamados_detalhe', args=[chamado.pk])
        return redirecionar(destino) if e_htmx(self.request) else redirect(destino)


class ChamadoDetalhe(PermissaoMixin, View):
    permissao = VER

    def get(self, request, pk):
        chamado = _chamado(request, pk)
        pode_gerir = request.user.tem_permissao(GERIR)
        return render(request, 'manutencao/chamado_detalhe.html', {
            'chamado': chamado, 'pode_gerir': pode_gerir,
            'pode_decidir': pode_gerir and chamado.status in ('ABERTO', 'EM_ANALISE'),
            'pode_cancelar': chamado.status == 'ABERTO' and (chamado.aberto_por_id == request.user.pk or pode_gerir),
            'smvs': chamado.smv_set.all() if request.user.tem_permissao(VER) else [],
            'form_motivo': MotivoForm(),
        })


class ChamadoAcao(Acao):
    def carregar(self, request, pk):
        return _chamado(request, pk)

    def destino(self, chamado):
        return reverse('chamados_detalhe', args=[chamado.pk])


class ChamadoEmAnalise(ChamadoAcao):
    permissao = GERIR
    sucesso = 'Chamado em análise.'

    def executar(self, request, chamado):
        services.analisar_chamado(chamado, request.user, 'EM_ANALISE')


class ChamadoImprocedente(ChamadoAcao):
    permissao = GERIR
    sucesso = 'Chamado marcado como improcedente; quem abriu foi avisado.'

    def executar(self, request, chamado):
        services.analisar_chamado(chamado, request.user, 'IMPROCEDENTE', validar(MotivoForm(request.POST))['motivo'])


class ChamadoCancelar(ChamadoAcao):
    sucesso = 'Chamado cancelado.'

    def autorizado(self, request, chamado):
        return chamado.aberto_por_id == request.user.pk or request.user.tem_permissao(GERIR)

    def executar(self, request, chamado):
        services.cancelar_chamado(chamado, request.user)


# --- SMV -----------------------------------------------------------------------------------------------------------------

class SmvNovo(Novo):
    """Gerar SMV: ?chamado=<id> ja traz o veiculo e o defeito do chamado."""

    def _chamado(self):
        pk = self.request.GET.get('chamado') or self.request.POST.get('chamado')
        if pk and pk.isdigit():
            return Chamado.objects.filter(pk=pk, municipio_id=self.request.user.municipio_id).select_related('veiculo').first()

    def get_initial(self):
        inicial = super().get_initial()
        chamado = self._chamado()
        if chamado:
            inicial.update(veiculo=chamado.veiculo_id, defeito_relatado=chamado.descricao)
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['chamado'] = self._chamado()
        return contexto

    def form_valid(self, form):
        dados = form.cleaned_data
        try:
            smv = services.abrir_smv(
                usuario=self.request.user, veiculo=dados['veiculo'], tipo=dados['tipo'], fornecedor=dados['fornecedor'],
                contrato=dados['contrato'], entrada_em=dados['entrada_em'], entrada_km=dados['entrada_km'],
                entrada_tanque=dados['entrada_tanque'], defeito=dados['defeito_relatado'], chamado=self._chamado(),
                veiculo_substituto=dados['veiculo_substituto'])
        except ValidationError as erro:
            form.add_error(None, erro)
            return self.form_invalid(form)
        messages.success(self.request, f'SMV {smv.numero} aberta. A oficina foi avisada.')
        destino = reverse('smv_detalhe', args=[smv.pk])
        return redirecionar(destino) if e_htmx(self.request) else redirect(destino)


class SmvDetalhe(PermissaoMixin, View):
    permissao = VER

    def get(self, request, pk):
        smv = _smv(request, pk)
        usuario = request.user
        orcamentos = list(smv.orcamentos.select_related('empenho'))
        aprovado = next((o for o in orcamentos if o.status == 'APROVADO'), None)
        ultimo = orcamentos[0] if orcamentos else None
        como_oficina = age_pela_oficina(usuario, smv)
        pode_criar_orcamento = (como_oficina and smv.etapa in ('DIAGNOSTICO', 'ORCAMENTO') and
                                (ultimo is None or ultimo.status in ('REVISAO', 'REPROVADO')))
        return render(request, 'manutencao/smv_detalhe.html', {
            'smv': smv, 'historico': smv.historico.select_related('usuario'), 'orcamentos': orcamentos, 'aprovado': aprovado,
            'pode_diagnosticar': como_oficina and smv.etapa in ('ENTRADA', 'DIAGNOSTICO', 'ORCAMENTO'),
            'pode_criar_orcamento': pode_criar_orcamento,
            'pode_entregar': como_oficina and smv.etapa == 'EXECUCAO',
            'pode_enviar_nf': como_oficina and smv.etapa == 'ENTREGA' and aprovado is not None,
            'pode_conferir': usuario.tem_permissao(GERIR) and smv.etapa == 'NOTA_FISCAL',
            'pode_cancelar': usuario.tem_permissao(GERIR) and smv.aberta,
            'form_diagnostico': DiagnosticoForm(initial={'diagnostico': smv.diagnostico}),
            'form_entrega': EntregaForm(initial={'saida_km': smv.entrada_km}), 'form_nf': NotaFiscalForm(),
            'form_motivo': MotivoForm(), 'form_mensagem': MensagemForm(), 'mensagens': _mensagens(smv),
        })


class SmvAcao(Acao):
    def carregar(self, request, pk):
        return _smv(request, pk)

    def destino(self, smv):
        return reverse('smv_detalhe', args=[smv.pk])


class SmvDiagnostico(SmvAcao):
    sucesso = 'Diagnóstico registrado.'

    def autorizado(self, request, smv):
        return age_pela_oficina(request.user, smv)

    def executar(self, request, smv):
        services.registrar_diagnostico(smv, request.user, validar(DiagnosticoForm(request.POST))['diagnostico'])


class SmvEntrega(SmvAcao):
    sucesso = 'Entrega registrada.'

    def autorizado(self, request, smv):
        return age_pela_oficina(request.user, smv)

    def executar(self, request, smv):
        dados = validar(EntregaForm(request.POST))
        services.registrar_entrega(smv, request.user, saida_em=dados['saida_em'], saida_km=dados['saida_km'],
                                   saida_tanque=dados['saida_tanque'], observacao=dados['observacao'])


class SmvNotaFiscal(SmvAcao):
    sucesso = 'Nota fiscal enviada para conferência.'

    def autorizado(self, request, smv):
        return age_pela_oficina(request.user, smv)

    def executar(self, request, smv):
        dados = validar(NotaFiscalForm(request.POST, request.FILES))
        services.enviar_nota_fiscal(smv, request.user, nf_pecas_numero=dados['nf_pecas_numero'], nf_servicos_numero=dados['nf_servicos_numero'],
                                    nf_pecas_valor=dados['nf_pecas_valor'], nf_servicos_valor=dados['nf_servicos_valor'],
                                    nf_emissao=dados['nf_emissao'], arquivo=dados['arquivo'])


class SmvConferirNota(SmvAcao):
    permissao = GERIR
    sucesso = 'Nota conferida: a reserva virou consumo e a SMV foi concluída.'

    def executar(self, request, smv):
        services.conferir_nota(smv, request.user)


class SmvCancelar(SmvAcao):
    permissao = GERIR
    sucesso = 'SMV cancelada. O que estava reservado voltou ao empenho.'

    def executar(self, request, smv):
        services.cancelar_smv(smv, request.user, validar(MotivoForm(request.POST))['motivo'])


class SmvOrcamentoNovo(SmvAcao):
    sucesso = 'Orçamento criado. Inclua os itens e envie.'

    def autorizado(self, request, smv):
        return age_pela_oficina(request.user, smv)

    def executar(self, request, smv):
        return reverse('orcamentos_detalhe', args=[services.criar_orcamento(smv, request.user).pk])


# --- Chat da SMV -------------------------------------------------------------------------------------------------------------

def _mensagens(smv):
    mensagens = list(smv.mensagens.select_related('autor').order_by('-criado_em', '-id')[:60])[::-1]
    anexos = {}
    for anexo in Anexo.objects.filter(municipio_id=smv.municipio_id, entidade='smv_mensagens', entidade_id__in=[m.pk for m in mensagens]):
        anexos.setdefault(anexo.entidade_id, []).append(anexo)
    for mensagem in mensagens:
        mensagem.arquivos = anexos.get(mensagem.pk, [])
    return mensagens


class SmvMensagens(PermissaoMixin, View):
    """GET devolve so a lista (a pagina a atualiza sozinha); POST envia uma mensagem."""
    permissao = VER

    def get(self, request, pk):
        smv = _smv(request, pk)
        return render(request, 'manutencao/_mensagens.html', {'smv': smv, 'mensagens': _mensagens(smv)})

    def post(self, request, pk):
        smv = _smv(request, pk)
        erro_texto = ''
        try:
            dados = validar(MensagemForm(request.POST, request.FILES))
            services.enviar_mensagem(smv, request.user, dados['texto'], dados['arquivo'])
        except ValidationError as erro:
            erro_texto = ' '.join(erro.messages)
        if e_htmx(request):
            resposta = render(request, 'manutencao/_mensagens.html', {'smv': smv, 'mensagens': _mensagens(smv)})
            return com_mensagem(resposta, erro_texto, 'error') if erro_texto else resposta
        if erro_texto:
            messages.error(request, erro_texto)
        return redirect('smv_detalhe', pk=smv.pk)


# --- Orcamento ---------------------------------------------------------------------------------------------------------------------

class OrcamentoDetalhe(PermissaoMixin, View):
    permissao = VER

    def get(self, request, pk):
        orcamento = _orcamento(request, pk)
        smv, usuario = orcamento.smv, request.user
        como_oficina = age_pela_oficina(usuario, smv)
        gestor = usuario.tem_permissao(GERIR)
        exigidas = services.numero_de_assinaturas(orcamento.municipio_id)
        aprovacoes = list(orcamento.aprovacoes.select_related('usuario'))
        ja_assinou = any(a.usuario_id == usuario.pk for a in aprovacoes)
        saldo = saldo_do_empenho(orcamento.empenho) if orcamento.empenho_id else None
        return render(request, 'manutencao/orcamento_detalhe.html', {
            'orcamento': orcamento, 'smv': smv, 'itens': orcamento.itens.select_related('categoria'), 'aprovacoes': aprovacoes,
            'exigidas': exigidas, 'aprovadas': len([a for a in aprovacoes if a.decisao == 'APROVADO']),
            'revisoes': Orcamento.objects.filter(municipio_id=orcamento.municipio_id, numero=orcamento.numero).exclude(pk=orcamento.pk),
            'saldo': saldo, 'sem_saldo': saldo is not None and saldo.saldo < orcamento.valor_total,
            'pode_editar_itens': como_oficina and orcamento.status == 'RASCUNHO',
            'pode_analisar': gestor and orcamento.status in ('RECEBIDO', 'EM_ANALISE'),
            'pode_iniciar': gestor and orcamento.status == 'RECEBIDO',
            'pode_assinar': usuario.tem_permissao(APROVAR) and orcamento.status == 'EM_ANALISE' and not ja_assinou,
            'ja_assinou': ja_assinou,
            'form_item': ItemOrcamentoForm(municipio_id=orcamento.municipio_id), 'form_motivo': MotivoForm(),
            'form_empenho': EmpenhoDoOrcamentoForm(orcamento=orcamento, initial={'empenho': orcamento.empenho_id}),
            'anexos': Anexo.objects.filter(municipio_id=orcamento.municipio_id, entidade='orcamentos', entidade_id=orcamento.pk),
        })


class OrcamentoAcao(Acao):
    def carregar(self, request, pk):
        return _orcamento(request, pk)

    def destino(self, orcamento):
        return reverse('orcamentos_detalhe', args=[orcamento.pk])


class OrcamentoOficinaAcao(OrcamentoAcao):
    def autorizado(self, request, orcamento):
        return age_pela_oficina(request.user, orcamento.smv)


class OrcamentoItemNovo(OrcamentoOficinaAcao):
    sucesso = 'Item adicionado.'

    def executar(self, request, orcamento):
        form = ItemOrcamentoForm(request.POST, municipio_id=orcamento.municipio_id)
        dados = validar(form)
        services.adicionar_item(orcamento, tipo=dados['tipo'], descricao=dados['descricao'], quantidade=dados['quantidade'],
                                valor_unitario=dados['valor_unitario'], categoria=dados['categoria'], codigo=dados['codigo'])


class OrcamentoItemExcluir(OrcamentoOficinaAcao):
    sucesso = 'Item removido.'

    def executar(self, request, orcamento, item_pk):
        services.remover_item(get_object_or_404(OrcamentoItem, pk=item_pk, orcamento=orcamento, municipio_id=orcamento.municipio_id))


class OrcamentoEnviar(OrcamentoOficinaAcao):
    sucesso = 'Orçamento enviado à prefeitura.'

    def executar(self, request, orcamento):
        services.enviar_orcamento(orcamento, request.user)


class OrcamentoGestorAcao(OrcamentoAcao):
    permissao = GERIR


class OrcamentoReferencias(OrcamentoGestorAcao):
    sucesso = 'Referências salvas.'

    def executar(self, request, orcamento):
        referencias = {}
        for item in orcamento.itens.all():
            try:
                referencias[item.pk] = _decimal(request.POST.get(f'ref_{item.pk}'))
            except InvalidOperation:
                raise ValidationError(f'Valor de referência inválido no item "{item.descricao}".')
        services.definir_referencias(orcamento, referencias)


class OrcamentoIniciarAnalise(OrcamentoGestorAcao):
    sucesso = 'Orçamento em análise: quem pode aprovar foi avisado.'

    def executar(self, request, orcamento):
        services.iniciar_analise(orcamento, request.user)


class OrcamentoDevolver(OrcamentoGestorAcao):
    sucesso = 'Orçamento devolvido; a oficina foi avisada.'

    def executar(self, request, orcamento):
        services.devolver_para_revisao(orcamento, request.user, validar(MotivoForm(request.POST))['motivo'])


class OrcamentoEmpenho(OrcamentoGestorAcao):
    sucesso = 'Empenho definido.'

    def executar(self, request, orcamento):
        dados = validar(EmpenhoDoOrcamentoForm(request.POST, orcamento=orcamento))
        services.definir_empenho(orcamento, dados['empenho'])


class OrcamentoAssinar(OrcamentoAcao):
    permissao = APROVAR

    def post(self, request, pk, **kwargs):
        self.sucesso = 'Assinatura registrada.' if request.POST.get('decisao') == 'APROVADO' else 'Orçamento reprovado.'
        return super().post(request, pk, **kwargs)

    def executar(self, request, orcamento):
        services.assinar_orcamento(orcamento, request.user, request.POST.get('decisao', ''), request.POST.get('observacao', ''))
        orcamento.refresh_from_db()
        if orcamento.status == 'APROVADO':
            self.sucesso = 'Orçamento aprovado: o valor foi reservado no empenho.'
