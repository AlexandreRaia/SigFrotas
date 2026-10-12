"""Regras da manutencao (CLAUDE.md, regras 6 e 7). Toda mudanca de estado passa por aqui; as telas so chamam estas funcoes.

Fluxo:  chamado -> SMV (ENTRADA) -> DIAGNOSTICO -> ORCAMENTO -> [aprovacao: reserva do empenho] -> EXECUCAO -> ENTREGA
        -> NOTA_FISCAL -> [conferencia: estorna a reserva e consome o valor da nota] -> CONCLUIDA   (CANCELADA a qualquer hora)

Valores, aprovacoes e baixas sao decisao humana: nada aqui acontece sozinho.
"""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.formatos import moeda
from apps.core.models import Usuario
from apps.core.services import anexar, config_da_prefeitura, notificar, proximo_numero, usuarios_com_permissao
from apps.financeiro.models import FiscalContrato, LancamentoEmpenho
from apps.financeiro.services import lancar, saldo_do_empenho
from apps.frota.services import registrar_leitura

from .models import Chamado, Orcamento, OrcamentoAprovacao, OrcamentoItem, Smv, SmvEtapaHist, SmvMensagem

ZERO = Decimal('0')


# --- Quem recebe o que -----------------------------------------------------------------------------------------

def _fiscais_vigentes(municipio_id, filtro_centro, contrato_tipo='MANUTENCAO'):
    hoje = timezone.localdate()
    designacoes = (FiscalContrato.objects
                   .filter(municipio_id=municipio_id, contrato__tipo=contrato_tipo, vigencia_ini__lte=hoje, usuario__ativo=True)
                   .filter(Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=hoje))
                   .filter(filtro_centro)
                   .select_related('usuario')
                   .order_by('suplente', F('centro_custo_id').asc(nulls_last=True), 'id'))
    return [d.usuario for d in designacoes]


def fiscal_do_veiculo(veiculo):
    """Fiscal do contrato de manutencao do centro de custo do veiculo: o titular antes do suplente; a designacao
    especifica do centro antes da que vale para todos. None se ninguem esta designado."""
    filtro = Q(centro_custo__isnull=True)
    if veiculo.centro_custo_id:
        filtro |= Q(centro_custo_id=veiculo.centro_custo_id)
    fiscais = _fiscais_vigentes(veiculo.municipio_id, filtro)
    return fiscais[0] if fiscais else None


def _fiscais_do_centro(municipio_id, centro_custo_id, contrato_tipo='MANUTENCAO'):
    filtro = Q(centro_custo__isnull=True) | Q(centro_custo_id=centro_custo_id)
    return _fiscais_vigentes(municipio_id, filtro, contrato_tipo)


def _gestores(municipio_id):
    return usuarios_com_permissao(municipio_id, 'manutencao.gerir')


def _usuarios_da_oficina(smv):
    if not smv.fornecedor_id:
        return []
    return list(Usuario.objects.filter(municipio_id=smv.municipio_id, fornecedor_id=smv.fornecedor_id, ativo=True))


def _fiscal_da_smv(smv):
    return [smv.chamado.fiscal] if smv.chamado_id and smv.chamado.fiscal_id else _fiscais_do_centro(smv.municipio_id, smv.centro_custo_id)


def _link_smv(smv):
    return reverse('smv_detalhe', args=[smv.pk])


def _link_orcamento(orcamento):
    return reverse('orcamentos_detalhe', args=[orcamento.pk])


# --- Chamados ----------------------------------------------------------------------------------------------------

@transaction.atomic
def abrir_chamado(*, veiculo, usuario, descricao, prioridade='NORMAL', origem='MANUAL'):
    """Abre o chamado e o encaminha ao fiscal do centro de custo do veiculo (regra 6)."""
    if not descricao or not descricao.strip():
        raise ValidationError('Descreva o problema.')
    fiscal = fiscal_do_veiculo(veiculo)
    chamado = Chamado.objects.create(
        municipio_id=veiculo.municipio_id, numero=proximo_numero(veiculo.municipio_id, 'CH'), veiculo=veiculo,
        aberto_por=usuario, origem=origem, descricao=descricao.strip(), prioridade=prioridade, fiscal=fiscal)
    assunto = f'Novo chamado {chamado.numero}: {veiculo.placa}'
    link = reverse('chamados_detalhe', args=[chamado.pk])
    notificar([fiscal], assunto, chamado.descricao, link=link, entidade='chamados', entidade_id=chamado.pk, exceto=usuario)
    notificar(_gestores(veiculo.municipio_id), assunto + ('' if fiscal else ' (sem fiscal designado para o centro de custo)'),
              chamado.descricao, link=link, entidade='chamados', entidade_id=chamado.pk, exceto=usuario)
    return chamado


@transaction.atomic
def analisar_chamado(chamado, usuario, decisao, motivo=''):
    """Gestor: poe em analise ou marca como improcedente (motivo obrigatorio)."""
    if chamado.status not in ('ABERTO', 'EM_ANALISE'):
        raise ValidationError('Este chamado já foi decidido.')
    if decisao == 'IMPROCEDENTE' and not motivo.strip():
        raise ValidationError('Informe o motivo para marcar como improcedente.')
    if decisao not in ('EM_ANALISE', 'IMPROCEDENTE'):
        raise ValidationError('Decisão inválida.')
    chamado.status, chamado.analisado_por, chamado.analisado_em, chamado.motivo_decisao = decisao, usuario, timezone.now(), motivo.strip()
    chamado.save()
    if decisao == 'IMPROCEDENTE':
        notificar([chamado.aberto_por], f'Chamado {chamado.numero} improcedente', motivo, link=reverse('chamados_detalhe', args=[chamado.pk]),
                  entidade='chamados', entidade_id=chamado.pk, exceto=usuario)
    return chamado


@transaction.atomic
def cancelar_chamado(chamado, usuario):
    if chamado.status != 'ABERTO':
        raise ValidationError('Só é possível cancelar um chamado que ainda não foi analisado.')
    chamado.status = 'CANCELADO'
    chamado.save()
    return chamado


# --- SMV ----------------------------------------------------------------------------------------------------------

def _historico(smv, usuario, observacao=''):
    SmvEtapaHist.objects.create(municipio_id=smv.municipio_id, smv=smv, etapa=smv.etapa, usuario=usuario, observacao=observacao)


def _mudar_etapa(smv, etapa, usuario, observacao=''):
    smv.etapa = etapa
    smv.save()
    _historico(smv, usuario, observacao)


def _situacao_do_veiculo(veiculo, de, para):
    if veiculo.situacao == de:
        veiculo.situacao = para
        veiculo.save(update_fields=['situacao', 'atualizado_em'])


@transaction.atomic
def abrir_smv(*, usuario, veiculo, tipo, fornecedor, entrada_km=None, entrada_em=None, entrada_tanque='', defeito='',
              chamado=None, contrato=None, veiculo_substituto=None):
    """Abre a SMV (entrada na oficina): o veiculo passa a 'em manutencao' e o km de entrada vira leitura."""
    if veiculo.situacao in ('BAIXADO', 'INATIVO'):
        raise ValidationError('Este veículo está baixado ou inativo.')
    if Smv.objects.filter(veiculo=veiculo).exclude(etapa__in=Smv.ETAPAS_FINAIS).exists():
        raise ValidationError('Este veículo já tem uma SMV em andamento.')
    if fornecedor is None or fornecedor.tipo not in ('OFICINA', 'LOCADORA'):
        raise ValidationError('Escolha uma oficina (ou a locadora, no caso de veículo locado).')
    if contrato is not None and contrato.tipo not in ('MANUTENCAO', 'LOCACAO'):
        raise ValidationError('O contrato precisa ser de manutenção ou de locação.')
    if chamado is not None and chamado.status not in ('ABERTO', 'EM_ANALISE'):
        raise ValidationError('Este chamado já foi decidido.')
    smv = Smv.objects.create(
        municipio_id=veiculo.municipio_id, numero=proximo_numero(veiculo.municipio_id, 'SMV'), chamado=chamado, veiculo=veiculo,
        fornecedor=fornecedor, contrato=contrato, centro_custo=veiculo.centro_custo, tipo=tipo,
        entrada_em=entrada_em or timezone.now(), entrada_km=entrada_km, entrada_tanque=entrada_tanque,
        defeito_relatado=defeito or (chamado.descricao if chamado else ''), veiculo_substituto=veiculo_substituto, criado_por=usuario,
        substituto_inicio=timezone.now() if veiculo_substituto else None)
    if entrada_km is not None:
        registrar_leitura(veiculo=veiculo, odometro=entrada_km, origem='SMV', origem_id=smv.pk)  # recusa km menor que o atual
    if veiculo.situacao != 'MANUTENCAO':
        veiculo.situacao = 'MANUTENCAO'
        veiculo.save(update_fields=['situacao', 'atualizado_em'])
    _historico(smv, usuario, 'SMV aberta')
    if chamado is not None:
        chamado.status = 'GEROU_SMV'
        chamado.save()
        notificar([chamado.aberto_por, chamado.fiscal], f'Chamado {chamado.numero} gerou a SMV {smv.numero}', link=_link_smv(smv),
                  entidade='smv', entidade_id=smv.pk, exceto=usuario)
    notificar(_usuarios_da_oficina(smv), f'Nova SMV {smv.numero}: {veiculo.placa}', smv.defeito_relatado, link=_link_smv(smv),
              entidade='smv', entidade_id=smv.pk, exceto=usuario)
    return smv


@transaction.atomic
def registrar_diagnostico(smv, usuario, texto):
    """Oficina: registra o diagnostico (a SMV passa de ENTRADA para DIAGNOSTICO)."""
    if smv.etapa not in ('ENTRADA', 'DIAGNOSTICO', 'ORCAMENTO'):
        raise ValidationError('O diagnóstico só pode ser registrado antes da execução.')
    if not texto or not texto.strip():
        raise ValidationError('Escreva o diagnóstico.')
    smv.diagnostico = texto.strip()
    if smv.etapa == 'ENTRADA':
        _mudar_etapa(smv, 'DIAGNOSTICO', usuario, 'Diagnóstico registrado')
    else:
        smv.save()
    notificar(_gestores(smv.municipio_id) + _fiscal_da_smv(smv), f'Diagnóstico da SMV {smv.numero}', smv.diagnostico,
              link=_link_smv(smv), entidade='smv', entidade_id=smv.pk, exceto=usuario)
    return smv


@transaction.atomic
def registrar_entrega(smv, usuario, *, saida_em, saida_km, saida_tanque='', observacao=''):
    """Servico pronto e veiculo devolvido: data, km e tanque na saida (EXECUCAO -> ENTREGA)."""
    if smv.etapa != 'EXECUCAO':
        raise ValidationError('A entrega só pode ser registrada depois da aprovação do orçamento.')
    if saida_em is None or saida_km is None:
        raise ValidationError('Informe a data e o km da saída.')
    if smv.entrada_km is not None and saida_km < smv.entrada_km:
        raise ValidationError('O km da saída não pode ser menor que o da entrada.')
    registrar_leitura(veiculo=smv.veiculo, odometro=saida_km, origem='SMV', origem_id=smv.pk)
    smv.saida_em, smv.saida_km, smv.saida_tanque, smv.observacao_entrega = saida_em, saida_km, saida_tanque, observacao
    if smv.veiculo_substituto_id:
        smv.substituto_fim = saida_em
    _mudar_etapa(smv, 'ENTREGA', usuario, 'Veículo entregue')
    notificar(_gestores(smv.municipio_id) + _fiscal_da_smv(smv), f'SMV {smv.numero}: veículo entregue', link=_link_smv(smv),
              entidade='smv', entidade_id=smv.pk, exceto=usuario)
    return smv


def _reserva_pendente(orcamento):
    """Quanto do empenho ainda esta reservado para o orcamento (reservas - estornos)."""
    soma = LancamentoEmpenho.objects.filter(orcamento_id=orcamento.pk).values('tipo').annotate(total=Sum('valor'))
    totais = {linha['tipo']: linha['total'] for linha in soma}
    return totais.get('RESERVA', ZERO) - totais.get('ESTORNO', ZERO)


@transaction.atomic
def cancelar_smv(smv, usuario, motivo):
    """Gestor cancela a SMV: devolve ao empenho o que estava reservado e libera o veiculo."""
    if not smv.aberta:
        raise ValidationError('Esta SMV já foi encerrada.')
    if not motivo or not motivo.strip():
        raise ValidationError('Informe o motivo do cancelamento.')
    for orcamento in smv.orcamentos.all():
        pendente = _reserva_pendente(orcamento)
        if pendente > 0:
            lancar(empenho=orcamento.empenho, tipo='ESTORNO', valor=pendente, usuario=usuario, orcamento_id=orcamento.pk,
                   observacao=f'SMV {smv.numero} cancelada')
        if orcamento.em_aberto:
            orcamento.status, orcamento.motivo_revisao = 'REPROVADO', f'SMV cancelada: {motivo.strip()}'
            orcamento.save()
    _mudar_etapa(smv, 'CANCELADA', usuario, motivo.strip())
    _situacao_do_veiculo(smv.veiculo, 'MANUTENCAO', 'DISPONIVEL')
    notificar(_usuarios_da_oficina(smv) + _fiscal_da_smv(smv), f'SMV {smv.numero} cancelada', motivo, link=_link_smv(smv),
              entidade='smv', entidade_id=smv.pk, exceto=usuario)
    return smv


# --- Orcamento -----------------------------------------------------------------------------------------------------

def recalcular_totais(orcamento):
    totais = {linha['tipo']: linha['total'] for linha in orcamento.itens.values('tipo').annotate(total=Sum('valor_total'))}
    orcamento.valor_pecas, orcamento.valor_servicos = totais.get('PECA', ZERO), totais.get('SERVICO', ZERO)
    orcamento.save(update_fields=['valor_pecas', 'valor_servicos', 'atualizado_em'])
    orcamento.refresh_from_db()


@transaction.atomic
def criar_orcamento(smv, usuario):
    """Oficina: abre um orcamento em preparacao (ou a nova revisao de um orcamento devolvido)."""
    if smv.etapa not in ('DIAGNOSTICO', 'ORCAMENTO'):
        raise ValidationError('O orçamento é feito depois do diagnóstico.')
    ultimo = smv.orcamentos.order_by('-id').first()
    if ultimo is not None and ultimo.em_aberto:
        raise ValidationError('Já existe um orçamento em andamento para esta SMV.')
    if ultimo is not None and ultimo.status == 'APROVADO':
        raise ValidationError('O orçamento desta SMV já foi aprovado.')
    agora = timezone.localdate()
    comuns = dict(municipio_id=smv.municipio_id, smv=smv, ano=agora.year, mes=agora.month)
    if ultimo is not None and ultimo.status == 'REVISAO':
        orcamento = Orcamento.objects.create(numero=ultimo.numero, revisao=ultimo.revisao + 1, valor_inicial=ultimo.valor_inicial,
                                             empenho=ultimo.empenho, **comuns)
        for item in ultimo.itens.all():
            OrcamentoItem.objects.create(
                municipio_id=smv.municipio_id, orcamento=orcamento, categoria=item.categoria, tipo=item.tipo, codigo=item.codigo,
                descricao=item.descricao, quantidade=item.quantidade, valor_unitario=item.valor_unitario,
                valor_referencia=item.valor_referencia)
        recalcular_totais(orcamento)
    else:
        orcamento = Orcamento.objects.create(numero=proximo_numero(smv.municipio_id, 'ORC'), **comuns)
    return orcamento


@transaction.atomic
def adicionar_item(orcamento, *, tipo, descricao, quantidade, valor_unitario, categoria=None, codigo=''):
    if orcamento.status != 'RASCUNHO':
        raise ValidationError('O orçamento já foi enviado: para mudar, peça a devolução para revisão.')
    if not descricao or not descricao.strip():
        raise ValidationError('Descreva o item.')
    item = OrcamentoItem(municipio_id=orcamento.municipio_id, orcamento=orcamento, tipo=tipo, descricao=descricao.strip(),
                         quantidade=quantidade, valor_unitario=valor_unitario, categoria=categoria, codigo=codigo)
    item.full_clean(exclude=['municipio', 'valor_total'])
    item.save()
    recalcular_totais(orcamento)
    return item


@transaction.atomic
def remover_item(item):
    orcamento = item.orcamento
    if orcamento.status != 'RASCUNHO':
        raise ValidationError('O orçamento já foi enviado.')
    item.delete()
    recalcular_totais(orcamento)


@transaction.atomic
def enviar_orcamento(orcamento, usuario):
    """Oficina envia o orcamento a prefeitura (a SMV passa para a etapa ORCAMENTO)."""
    if orcamento.status != 'RASCUNHO':
        raise ValidationError('Este orçamento já foi enviado.')
    if not orcamento.itens.exists() or orcamento.valor_total <= 0:
        raise ValidationError('Inclua ao menos um item com valor antes de enviar.')
    orcamento.status, orcamento.enviado_em = 'RECEBIDO', timezone.now()
    if orcamento.revisao == 1:
        orcamento.valor_inicial = orcamento.valor_total
    orcamento.save()
    orcamento.refresh_from_db()
    if orcamento.smv.etapa == 'DIAGNOSTICO':
        _mudar_etapa(orcamento.smv, 'ORCAMENTO', usuario, f'Orçamento {orcamento} recebido')
    notificar(_gestores(orcamento.municipio_id) + _fiscal_da_smv(orcamento.smv),
              f'Orçamento {orcamento} recebido ({moeda(orcamento.valor_total)}) - SMV {orcamento.smv.numero}',
              link=_link_orcamento(orcamento), entidade='orcamentos', entidade_id=orcamento.pk, exceto=usuario)
    return orcamento


@transaction.atomic
def definir_referencias(orcamento, referencias):
    """Gestor informa o valor de referencia (pesquisa de precos ou contrato) de cada item: {item_id: valor ou None}."""
    if orcamento.status not in ('RECEBIDO', 'EM_ANALISE'):
        raise ValidationError('As referências só podem ser alteradas durante a análise.')
    for item in orcamento.itens.filter(pk__in=referencias):
        valor = referencias[item.pk]
        if valor is not None and valor < 0:
            raise ValidationError('A referência não pode ser negativa.')
        item.valor_referencia = valor
        item.save(update_fields=['valor_referencia'])


def numero_de_assinaturas(municipio_id):
    """Quantas assinaturas o orcamento precisa (municipios.config['aprovacoes_orcamento'], padrao 3)."""
    return max(1, int(config_da_prefeitura(municipio_id, 'aprovacoes_orcamento', 3)))


@transaction.atomic
def iniciar_analise(orcamento, usuario):
    if orcamento.status != 'RECEBIDO':
        raise ValidationError('Só é possível iniciar a análise de um orçamento recebido.')
    orcamento.status = 'EM_ANALISE'
    orcamento.save()
    notificar(usuarios_com_permissao(orcamento.municipio_id, 'manutencao.aprovar'),
              f'Orçamento {orcamento} aguarda assinaturas ({numero_de_assinaturas(orcamento.municipio_id)})',
              link=_link_orcamento(orcamento), entidade='orcamentos', entidade_id=orcamento.pk, exceto=usuario)
    return orcamento


@transaction.atomic
def devolver_para_revisao(orcamento, usuario, motivo):
    """Gestor devolve o orcamento a oficina; a oficina envia uma nova revisao (as anteriores ficam guardadas)."""
    if orcamento.status not in ('RECEBIDO', 'EM_ANALISE'):
        raise ValidationError('Este orçamento não pode ser devolvido agora.')
    if not motivo or not motivo.strip():
        raise ValidationError('Explique à oficina o que precisa ser revisto.')
    orcamento.status, orcamento.motivo_revisao = 'REVISAO', motivo.strip()
    orcamento.save()
    notificar(_usuarios_da_oficina(orcamento.smv), f'Orçamento {orcamento} devolvido para revisão', motivo,
              link=_link_orcamento(orcamento), entidade='orcamentos', entidade_id=orcamento.pk, exceto=usuario)
    return orcamento


@transaction.atomic
def definir_empenho(orcamento, empenho):
    """Escolhe de qual empenho sai o valor. Tem que ser de manutencao, do centro de custo da SMV, ativo e no periodo."""
    if orcamento.status not in ('RECEBIDO', 'EM_ANALISE'):
        raise ValidationError('O empenho só pode ser escolhido durante a análise.')
    if empenho.finalidade != 'MANUTENCAO':
        raise ValidationError('O empenho precisa ser de manutenção.')
    if not empenho.ativo:
        raise ValidationError('Empenho inativo.')
    if orcamento.smv.centro_custo_id and empenho.centro_custo_id != orcamento.smv.centro_custo_id:
        raise ValidationError('O empenho é de outro centro de custo (o da SMV é o do veículo).')
    hoje = timezone.localdate()
    if not (empenho.vigencia_ini <= hoje <= empenho.vigencia_fim):
        raise ValidationError('O empenho está fora do período de vigência.')
    orcamento.empenho = empenho
    orcamento.save()
    return orcamento


@transaction.atomic
def assinar_orcamento(orcamento, usuario, decisao, observacao=''):
    """Uma assinatura (aprovar ou reprovar). Na ultima assinatura, o valor e RESERVADO no empenho: sem saldo, nao aprova
    (e a assinatura tambem nao e gravada: tudo ou nada)."""
    if not usuario.tem_permissao('manutencao.aprovar'):
        raise PermissionDenied
    orcamento = Orcamento.objects.select_for_update().get(pk=orcamento.pk, municipio_id=orcamento.municipio_id)
    if orcamento.status != 'EM_ANALISE':
        raise ValidationError('Este orçamento não está aguardando assinaturas.')
    if decisao not in ('APROVADO', 'REPROVADO'):
        raise ValidationError('Decisão inválida.')
    if decisao == 'REPROVADO' and not observacao.strip():
        raise ValidationError('Informe o motivo da reprovação.')
    if orcamento.aprovacoes.filter(usuario=usuario).exists():
        raise ValidationError('Você já assinou este orçamento.')
    aprovacao = OrcamentoAprovacao.objects.create(
        municipio_id=orcamento.municipio_id, orcamento=orcamento, sequencia=orcamento.aprovacoes.count() + 1,
        usuario=usuario, decisao=decisao, observacao=observacao.strip())
    smv, link = orcamento.smv, _link_orcamento(orcamento)

    if decisao == 'REPROVADO':
        orcamento.status = 'REPROVADO'
        orcamento.save()
        notificar(_usuarios_da_oficina(smv) + _gestores(orcamento.municipio_id) + _fiscal_da_smv(smv),
                  f'Orçamento {orcamento} reprovado', observacao, link=link, entidade='orcamentos', entidade_id=orcamento.pk, exceto=usuario)
        return aprovacao

    if orcamento.aprovacoes.filter(decisao='APROVADO').count() < numero_de_assinaturas(orcamento.municipio_id):
        return aprovacao  # faltam assinaturas

    # ultima assinatura: precisa de empenho com saldo (a reserva e o que garante o pagamento)
    if orcamento.empenho_id is None:
        raise ValidationError('Escolha o empenho do orçamento antes da última assinatura.')
    lancar(empenho=orcamento.empenho, tipo='RESERVA', valor=orcamento.valor_total, usuario=usuario, orcamento_id=orcamento.pk,
           observacao=f'Orçamento {orcamento} aprovado')
    orcamento.status = 'APROVADO'
    orcamento.save()
    if smv.etapa == 'ORCAMENTO':
        _mudar_etapa(smv, 'EXECUCAO', usuario, f'Orçamento {orcamento} aprovado')
    notificar(_usuarios_da_oficina(smv) + _gestores(orcamento.municipio_id) + _fiscal_da_smv(smv),
              f'Orçamento {orcamento} aprovado ({moeda(orcamento.valor_total)})', 'Pode executar o serviço.', link=link,
              entidade='orcamentos', entidade_id=orcamento.pk, exceto=usuario)
    verificar_saldo_baixo(orcamento.empenho)
    return aprovacao


# --- Nota fiscal ------------------------------------------------------------------------------------------------------

def _orcamento_aprovado(smv):
    return smv.orcamentos.filter(status='APROVADO').order_by('-id').first()


@transaction.atomic
def enviar_nota_fiscal(smv, usuario, *, nf_pecas_numero='', nf_servicos_numero='', nf_pecas_valor=None, nf_servicos_valor=None,
                       nf_emissao=None, arquivo=None):
    """Oficina informa as notas (pecas e servicos separadas) apos a entrega. SMV: ENTREGA -> NOTA_FISCAL."""
    orcamento = _orcamento_aprovado(smv)
    if smv.etapa != 'ENTREGA' or orcamento is None:
        raise ValidationError('A nota só pode ser enviada depois da entrega do veículo.')
    for rotulo, numero, valor in (('das peças', nf_pecas_numero, nf_pecas_valor), ('dos serviços', nf_servicos_numero, nf_servicos_valor)):
        if bool(numero) != bool(valor):
            raise ValidationError(f'Informe o número e o valor da nota {rotulo} (ou deixe os dois em branco).')
    total = (nf_pecas_valor or ZERO) + (nf_servicos_valor or ZERO)
    if total <= 0:
        raise ValidationError('Informe ao menos uma nota com valor.')
    if total > orcamento.valor_total:
        raise ValidationError(f'As notas somam {moeda(total)}, acima do valor aprovado ({moeda(orcamento.valor_total)}). '
                              'Peça um novo orçamento à prefeitura antes de faturar a mais.')
    orcamento.nf_pecas_numero, orcamento.nf_servicos_numero = nf_pecas_numero, nf_servicos_numero
    orcamento.nf_pecas_valor, orcamento.nf_servicos_valor, orcamento.nf_emissao = nf_pecas_valor, nf_servicos_valor, nf_emissao
    orcamento.save()
    if arquivo is not None:
        anexar(municipio_id=smv.municipio_id, entidade='orcamentos', entidade_id=orcamento.pk, arquivo=arquivo,
               categoria='NOTA_FISCAL', enviado_por=usuario)
    _mudar_etapa(smv, 'NOTA_FISCAL', usuario, f'Nota fiscal de {moeda(total)}')
    notificar(_gestores(smv.municipio_id) + _fiscal_da_smv(smv), f'SMV {smv.numero}: nota fiscal para conferir ({moeda(total)})',
              link=_link_smv(smv), entidade='smv', entidade_id=smv.pk, exceto=usuario)
    return orcamento


@transaction.atomic
def conferir_nota(smv, usuario):
    """Gestor confere a nota: a reserva vira CONSUMO do valor da nota e a SMV e concluida (regra 7)."""
    orcamento = _orcamento_aprovado(smv)
    if smv.etapa != 'NOTA_FISCAL' or orcamento is None or not orcamento.nf_total:
        raise ValidationError('Não há nota fiscal para conferir.')
    if orcamento.nf_total > orcamento.valor_total:
        raise ValidationError('A nota passa do valor aprovado.')
    pendente = _reserva_pendente(orcamento)
    if pendente > 0:
        lancar(empenho=orcamento.empenho, tipo='ESTORNO', valor=pendente, usuario=usuario, orcamento_id=orcamento.pk,
               observacao=f'Reserva do orçamento {orcamento} convertida em consumo')
    lancar(empenho=orcamento.empenho, tipo='CONSUMO', valor=orcamento.nf_total, usuario=usuario, orcamento_id=orcamento.pk,
           observacao=f'Nota fiscal conferida - SMV {smv.numero}')
    smv.concluida_em, smv.concluida_por = timezone.now(), usuario
    _mudar_etapa(smv, 'CONCLUIDA', usuario, 'Nota conferida')
    _situacao_do_veiculo(smv.veiculo, 'MANUTENCAO', 'DISPONIVEL')
    notificar(_usuarios_da_oficina(smv), f'SMV {smv.numero} concluída', 'A nota fiscal foi conferida.', link=_link_smv(smv),
              entidade='smv', entidade_id=smv.pk, exceto=usuario)
    verificar_saldo_baixo(orcamento.empenho)
    return smv


def verificar_saldo_baixo(empenho):
    """Avisa o fiscal do centro de custo e os gestores quando o saldo cai abaixo do percentual da prefeitura (padrao 10%)."""
    saldo = saldo_do_empenho(empenho)
    limite = Decimal(str(config_da_prefeitura(empenho.municipio_id, 'saldo_baixo_percentual', 10)))
    if saldo.liberado <= 0 or saldo.saldo * 100 / saldo.liberado >= limite:
        return False
    destinatarios = _fiscais_do_centro(empenho.municipio_id, empenho.centro_custo_id) + _gestores(empenho.municipio_id)
    notificar(destinatarios, f'Saldo baixo no empenho {empenho}: {moeda(saldo.saldo)} ({saldo.saldo * 100 / saldo.liberado:.1f}% do liberado)',
              link=reverse('empenhos_detalhe', args=[empenho.pk]), entidade='empenhos', entidade_id=empenho.pk, sem_repetir=True)
    return True


# --- Chat ----------------------------------------------------------------------------------------------------------------

@transaction.atomic
def enviar_mensagem(smv, autor, texto='', arquivo=None):
    """Mensagem no chat da SMV (texto e/ou arquivo: foto, audio, video, PDF). Avisa o outro lado."""
    if not texto.strip() and arquivo is None:
        raise ValidationError('Escreva uma mensagem ou anexe um arquivo.')
    mensagem = SmvMensagem.objects.create(municipio_id=smv.municipio_id, smv=smv, autor=autor, texto=texto.strip())
    if arquivo is not None:
        anexar(municipio_id=smv.municipio_id, entidade='smv_mensagens', entidade_id=mensagem.pk, arquivo=arquivo, enviado_por=autor)
    do_lado_da_oficina = bool(autor.fornecedor_id)
    destinatarios = (_gestores(smv.municipio_id) + _fiscal_da_smv(smv)) if do_lado_da_oficina else _usuarios_da_oficina(smv)
    notificar(destinatarios, f'Nova mensagem na SMV {smv.numero}', texto.strip()[:200], link=_link_smv(smv), entidade='smv',
              entidade_id=smv.pk, exceto=autor, sem_repetir=True)
    return mensagem
