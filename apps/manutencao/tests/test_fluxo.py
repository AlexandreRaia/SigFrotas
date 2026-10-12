import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from apps.core.models import Anexo, Municipio, Notificacao
from apps.core.tests.base import DuasPrefeiturasTest
from apps.financeiro.models import Contrato, Fornecedor, FiscalContrato
from apps.financeiro.services import SaldoInsuficiente, criar_empenho, saldo_do_empenho
from apps.manutencao import services
from apps.manutencao.models import Chamado, DiasEmManutencao, Orcamento, Smv

D = Decimal


class BaseManutencao(DuasPrefeiturasTest):
    def smv(self, veiculo=None, **extras):
        return services.abrir_smv(usuario=self.gestor_a, veiculo=veiculo or self.veiculo_a, tipo='CORRETIVA',
                                  fornecedor=self.fornecedor_a, entrada_km=1200, **extras)

    def orcamento_em_analise(self, itens=((('PECA', 'Pastilha', 2, 100)), ('SERVICO', 'Mão de obra', 1, 300)), smv=None):
        """SMV aberta -> diagnostico -> orcamento enviado -> em analise com o empenho_a definido."""
        smv = smv or self.smv()
        services.registrar_diagnostico(smv, self.oficina_a, 'Pastilhas gastas')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        for tipo, descricao, qtd, valor in itens:
            services.adicionar_item(orcamento, tipo=tipo, descricao=descricao, quantidade=D(qtd), valor_unitario=D(valor))
        orcamento = Orcamento.objects.get(pk=orcamento.pk)
        services.enviar_orcamento(orcamento, self.oficina_a)
        orcamento.refresh_from_db()
        services.iniciar_analise(orcamento, self.gestor_a)
        services.definir_empenho(orcamento, self.empenho_a)
        return smv, orcamento

    def assinar(self, orcamento, usuarios=None):
        for usuario in usuarios or (self.admin_a, self.gestor_a, self.gestor2_a):
            services.assinar_orcamento(orcamento, usuario, 'APROVADO')
        orcamento.refresh_from_db()

    def aprovar_ate_a_entrega(self, **extras):
        smv, orcamento = self.orcamento_em_analise(**extras)
        self.assinar(orcamento)
        smv.refresh_from_db()
        services.registrar_entrega(smv, self.oficina_a, saida_em=timezone.now(), saida_km=1250)
        return smv, orcamento


class ChamadoTest(BaseManutencao):
    def test_vai_ao_fiscal_do_centro_de_custo_do_veiculo(self):
        chamado = services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.motorista_usuario_a, descricao='Barulho no freio')
        self.assertEqual(chamado.fiscal, self.fiscal_a)
        self.assertTrue(chamado.numero.endswith('-0001') and chamado.numero.startswith('CH-'))
        self.assertTrue(Notificacao.objects.filter(usuario=self.fiscal_a, canal='APP', entidade='chamados', entidade_id=chamado.pk).exists())
        self.assertTrue(Notificacao.objects.filter(usuario=self.gestor_a, canal='APP', entidade='chamados').exists())
        self.assertFalse(Notificacao.objects.filter(usuario=self.motorista_usuario_a).exists())  # quem abriu nao se avisa

    def test_sem_fiscal_o_gestor_e_avisado_disso(self):
        chamado = services.abrir_chamado(veiculo=self.veiculo2_a, usuario=self.motorista_usuario_a, descricao='Pneu careca')
        self.assertIsNone(chamado.fiscal)
        aviso = Notificacao.objects.get(usuario=self.gestor_a, canal='APP', entidade_id=chamado.pk)
        self.assertIn('sem fiscal', aviso.assunto)

    def test_titular_antes_do_suplente_e_so_quem_esta_vigente(self):
        FiscalContrato.objects.create(municipio=self.a, contrato=self.contrato_a, centro_custo=self.centro_a,
                                      usuario=self.consulta_a, suplente=True)
        self.assertEqual(services.fiscal_do_veiculo(self.veiculo_a), self.fiscal_a)
        FiscalContrato.objects.filter(usuario=self.fiscal_a).update(vigencia_fim=timezone.localdate() - timedelta(days=1))
        self.assertEqual(services.fiscal_do_veiculo(self.veiculo_a), self.consulta_a)

    def test_designacao_para_todos_os_centros_vale_para_veiculo_sem_designacao_propria(self):
        FiscalContrato.objects.create(municipio=self.a, contrato=self.contrato_a, centro_custo=None, usuario=self.consulta_a)
        self.assertEqual(services.fiscal_do_veiculo(self.veiculo2_a), self.consulta_a)  # centro 200 nao tem fiscal proprio
        self.assertEqual(services.fiscal_do_veiculo(self.veiculo_a), self.fiscal_a)     # o especifico vence o geral

    def test_contrato_de_outro_tipo_nao_conta(self):
        Contrato.objects.filter(pk=self.contrato_a.pk).update(tipo='COMBUSTIVEL')
        self.assertIsNone(services.fiscal_do_veiculo(self.veiculo_a))

    def test_numeracao_sequencial_e_separada_por_prefeitura(self):
        c1 = services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.gestor_a, descricao='a')
        c2 = services.abrir_chamado(veiculo=self.veiculo2_a, usuario=self.gestor_a, descricao='b')
        cb = services.abrir_chamado(veiculo=self.veiculo_b, usuario=self.gestor_b, descricao='c')
        self.assertEqual([c1.numero[-4:], c2.numero[-4:], cb.numero[-4:]], ['0001', '0002', '0001'])

    def test_descricao_obrigatoria(self):
        with self.assertRaises(ValidationError):
            services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.gestor_a, descricao='   ')

    def test_decisoes(self):
        chamado = services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.motorista_usuario_a, descricao='x')
        with self.assertRaises(ValidationError):  # improcedente exige motivo
            services.analisar_chamado(chamado, self.gestor_a, 'IMPROCEDENTE', '')
        services.analisar_chamado(chamado, self.gestor_a, 'IMPROCEDENTE', 'Defeito já resolvido')
        self.assertEqual(chamado.status, 'IMPROCEDENTE')
        self.assertTrue(Notificacao.objects.filter(usuario=self.motorista_usuario_a, entidade='chamados').exists())
        with self.assertRaises(ValidationError):  # ja decidido
            services.analisar_chamado(chamado, self.gestor_a, 'EM_ANALISE')

    def test_so_cancela_chamado_ainda_aberto(self):
        chamado = services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.motorista_usuario_a, descricao='x')
        services.analisar_chamado(chamado, self.gestor_a, 'EM_ANALISE')
        with self.assertRaises(ValidationError):
            services.cancelar_chamado(chamado, self.motorista_usuario_a)


class AbrirSmvTest(BaseManutencao):
    def test_abre_a_smv_poe_o_veiculo_em_manutencao_e_registra_o_km(self):
        smv = self.smv()
        self.veiculo_a.refresh_from_db()
        self.assertEqual((smv.etapa, self.veiculo_a.situacao, self.veiculo_a.odometro_atual), ('ENTRADA', 'MANUTENCAO', 1200))
        self.assertEqual(self.veiculo_a.leituras.get(origem='SMV').odometro, 1200)
        self.assertEqual(smv.centro_custo, self.centro_a)
        self.assertEqual(smv.historico.count(), 1)
        self.assertTrue(Notificacao.objects.filter(usuario=self.oficina_a, entidade='smv', entidade_id=smv.pk).exists())

    def test_gerar_da_o_chamado_como_gerou_smv(self):
        chamado = services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.motorista_usuario_a, descricao='Freio')
        smv = self.smv(chamado=chamado)
        chamado.refresh_from_db()
        self.assertEqual((chamado.status, smv.defeito_relatado), ('GEROU_SMV', 'Freio'))
        self.assertTrue(Notificacao.objects.filter(usuario=self.motorista_usuario_a, entidade='smv').exists())

    def test_um_veiculo_so_tem_uma_smv_em_andamento(self):
        self.smv()
        with self.assertRaisesMessage(ValidationError, 'já tem uma SMV em andamento'):
            self.smv()

    def test_km_de_entrada_menor_que_o_atual_e_recusado_sem_deixar_rastro(self):
        with self.assertRaisesMessage(ValidationError, 'não pode diminuir'):
            services.abrir_smv(usuario=self.gestor_a, veiculo=self.veiculo_a, tipo='CORRETIVA', fornecedor=self.fornecedor_a, entrada_km=500)
        self.assertFalse(Smv.objects.exists())
        self.veiculo_a.refresh_from_db()
        self.assertEqual(self.veiculo_a.situacao, 'DISPONIVEL')

    def test_veiculo_baixado_e_fornecedor_que_nao_e_oficina_sao_recusados(self):
        posto = Fornecedor.objects.create(municipio=self.a, cnpj_cpf='04252011000110', razao_social='Posto', tipo='POSTO')
        with self.assertRaises(ValidationError):
            services.abrir_smv(usuario=self.gestor_a, veiculo=self.veiculo_a, tipo='CORRETIVA', fornecedor=posto)
        self.veiculo_a.situacao = 'BAIXADO'
        self.veiculo_a.save(update_fields=['situacao'])
        with self.assertRaises(ValidationError):
            self.smv()

    def test_fornecedor_de_outra_prefeitura_e_recusado(self):
        with self.assertRaises(ValidationError):
            services.abrir_smv(usuario=self.gestor_a, veiculo=self.veiculo_a, tipo='CORRETIVA', fornecedor=self.fornecedor_b)

    def test_view_dias_em_manutencao(self):
        smv = services.abrir_smv(usuario=self.gestor_a, veiculo=self.veiculo_a, tipo='CORRETIVA', fornecedor=self.fornecedor_a,
                                 entrada_em=timezone.now() - timedelta(days=5))
        self.assertEqual(DiasEmManutencao.objects.get(smv_id=smv.pk).dias_em_manutencao, 5)


class OrcamentoTest(BaseManutencao):
    def test_totais_e_colunas_geradas(self):
        smv, orcamento = self.orcamento_em_analise()
        self.assertEqual((orcamento.valor_pecas, orcamento.valor_servicos, orcamento.valor_total), (D('200.00'), D('300.00'), D('500.00')))
        self.assertEqual((orcamento.status, orcamento.valor_inicial, orcamento.valor_economizado), ('EM_ANALISE', D('500.00'), D('0.00')))
        smv.refresh_from_db()
        self.assertEqual(smv.etapa, 'ORCAMENTO')
        self.assertTrue(orcamento.numero.startswith('ORC-'))

    def test_so_depois_do_diagnostico_e_um_por_vez(self):
        smv = self.smv()
        with self.assertRaises(ValidationError):
            services.criar_orcamento(smv, self.oficina_a)
        services.registrar_diagnostico(smv, self.oficina_a, 'x')
        services.criar_orcamento(smv, self.oficina_a)
        with self.assertRaisesMessage(ValidationError, 'em andamento'):
            services.criar_orcamento(smv, self.oficina_a)

    def test_nao_envia_vazio_nem_edita_depois_de_enviado(self):
        smv = self.smv()
        services.registrar_diagnostico(smv, self.oficina_a, 'x')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        with self.assertRaises(ValidationError):
            services.enviar_orcamento(orcamento, self.oficina_a)
        services.adicionar_item(orcamento, tipo='PECA', descricao='Filtro', quantidade=D('1'), valor_unitario=D('50'))
        services.enviar_orcamento(Orcamento.objects.get(pk=orcamento.pk), self.oficina_a)
        orcamento.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.adicionar_item(orcamento, tipo='PECA', descricao='Outro', quantidade=D('1'), valor_unitario=D('1'))

    def test_item_precisa_de_descricao_quantidade_e_valor_validos(self):
        smv = self.smv()
        services.registrar_diagnostico(smv, self.oficina_a, 'x')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        for dados in ({'descricao': ''}, {'quantidade': D('0')}, {'valor_unitario': D('-1')}):
            with self.assertRaises(ValidationError, msg=str(dados)):
                services.adicionar_item(orcamento, **{'tipo': 'PECA', 'descricao': 'x', 'quantidade': D('1'), 'valor_unitario': D('1'), **dados})

    def test_referencia_mostra_a_diferenca_de_cada_item(self):
        _, orcamento = self.orcamento_em_analise()
        item = orcamento.itens.get(descricao='Pastilha')
        services.definir_referencias(orcamento, {item.pk: D('80.00')})
        item.refresh_from_db()
        self.assertEqual(item.diferenca_referencia, D('20.00'))   # a oficina cobra 100 contra 80 de referencia

    def test_revisao_guarda_o_valor_inicial_e_calcula_a_economia(self):
        smv, primeiro = self.orcamento_em_analise()
        with self.assertRaises(ValidationError):
            services.devolver_para_revisao(primeiro, self.gestor_a, '')
        services.devolver_para_revisao(primeiro, self.gestor_a, 'Preço da pastilha acima da tabela')
        self.assertTrue(Notificacao.objects.filter(usuario=self.oficina_a, entidade='orcamentos').exists())
        segundo = services.criar_orcamento(smv, self.oficina_a)
        self.assertEqual((segundo.numero, segundo.revisao, segundo.valor_inicial, segundo.valor_total), (primeiro.numero, 2, D('500.00'), D('500.00')))
        item = segundo.itens.get(descricao='Pastilha')
        item.valor_unitario = D('80.00')
        item.save()
        services.recalcular_totais(segundo)
        services.enviar_orcamento(segundo, self.oficina_a)
        segundo.refresh_from_db()
        self.assertEqual((segundo.valor_total, segundo.valor_economizado, segundo.valor_inicial), (D('460.00'), D('40.00'), D('500.00')))
        self.assertEqual(Orcamento.objects.filter(numero=primeiro.numero).count(), 2)   # a revisao anterior fica guardada


class AprovacaoTest(BaseManutencao):
    def test_tres_assinaturas_aprovam_e_reservam_o_valor(self):
        smv, orcamento = self.orcamento_em_analise()
        services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        services.assinar_orcamento(orcamento, self.gestor_a, 'APROVADO')
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, 'EM_ANALISE')                           # faltam assinaturas
        self.assertEqual(saldo_do_empenho(self.empenho_a).reservado, D('0.00'))    # e ainda nada foi reservado
        services.assinar_orcamento(orcamento, self.gestor2_a, 'APROVADO')
        orcamento.refresh_from_db()
        smv.refresh_from_db()
        self.assertEqual((orcamento.status, smv.etapa), ('APROVADO', 'EXECUCAO'))
        saldo = saldo_do_empenho(self.empenho_a)
        self.assertEqual((saldo.reservado, saldo.saldo), (D('500.00'), D('500.00')))
        self.assertEqual([a.sequencia for a in orcamento.aprovacoes.all()], [1, 2, 3])

    def test_sem_saldo_nao_aprova_e_a_assinatura_nao_fica_gravada(self):
        smv, orcamento = self.orcamento_em_analise(itens=(('PECA', 'Motor', 1, 1500),))   # empenho tem 1000
        services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        services.assinar_orcamento(orcamento, self.gestor_a, 'APROVADO')
        with self.assertRaises(SaldoInsuficiente):
            services.assinar_orcamento(orcamento, self.gestor2_a, 'APROVADO')
        orcamento.refresh_from_db()
        self.assertEqual((orcamento.status, orcamento.aprovacoes.count()), ('EM_ANALISE', 2))
        self.assertEqual(saldo_do_empenho(self.empenho_a).reservado, D('0.00'))

    def test_ultima_assinatura_exige_empenho(self):
        smv = self.smv()
        services.registrar_diagnostico(smv, self.oficina_a, 'x')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        services.adicionar_item(orcamento, tipo='PECA', descricao='x', quantidade=D('1'), valor_unitario=D('10'))
        services.enviar_orcamento(Orcamento.objects.get(pk=orcamento.pk), self.oficina_a)
        orcamento.refresh_from_db()
        services.iniciar_analise(orcamento, self.gestor_a)
        services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        services.assinar_orcamento(orcamento, self.gestor_a, 'APROVADO')
        with self.assertRaisesMessage(ValidationError, 'Escolha o empenho'):
            services.assinar_orcamento(orcamento, self.gestor2_a, 'APROVADO')
        self.assertEqual(orcamento.aprovacoes.count(), 2)

    def test_numero_de_assinaturas_vem_da_configuracao_da_prefeitura(self):
        Municipio.objects.filter(pk=self.a.pk).update(config={'aprovacoes_orcamento': 1})
        _, orcamento = self.orcamento_em_analise()
        services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, 'APROVADO')

    def test_ninguem_assina_duas_vezes_e_so_quem_tem_permissao_assina(self):
        _, orcamento = self.orcamento_em_analise()
        services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        with self.assertRaisesMessage(ValidationError, 'já assinou'):
            services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        for usuario in (self.fiscal_a, self.consulta_a, self.oficina_a, self.solicitante_a):
            with self.assertRaises(PermissionDenied, msg=usuario.email):
                services.assinar_orcamento(orcamento, usuario, 'APROVADO')

    def test_reprovar_exige_motivo_e_encerra_o_orcamento(self):
        _, orcamento = self.orcamento_em_analise()
        with self.assertRaises(ValidationError):
            services.assinar_orcamento(orcamento, self.admin_a, 'REPROVADO', '')
        services.assinar_orcamento(orcamento, self.admin_a, 'REPROVADO', 'Valor fora do mercado')
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, 'REPROVADO')
        self.assertEqual(saldo_do_empenho(self.empenho_a).reservado, D('0.00'))
        with self.assertRaises(ValidationError):   # nao esta mais aguardando assinaturas
            services.assinar_orcamento(orcamento, self.gestor_a, 'APROVADO')

    def test_so_assina_orcamento_em_analise(self):
        smv = self.smv()
        services.registrar_diagnostico(smv, self.oficina_a, 'x')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        with self.assertRaises(ValidationError):
            services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')

    def test_empenho_precisa_ser_de_manutencao_do_centro_da_smv_e_vigente(self):
        smv, orcamento = self.orcamento_em_analise()
        abastecimento = criar_empenho(municipio=self.a, finalidade='ABASTECIMENTO', centro_custo=self.centro_a, numero='80', exercicio=2026,
                                      vigencia_ini=timezone.localdate() - timedelta(days=1), vigencia_fim=timezone.localdate() + timedelta(days=9),
                                      valor_empenhado=D('100'), liberar_total=True)
        vencido = criar_empenho(municipio=self.a, finalidade='MANUTENCAO', centro_custo=self.centro_a, numero='81', exercicio=2025,
                                vigencia_ini=timezone.localdate() - timedelta(days=100), vigencia_fim=timezone.localdate() - timedelta(days=10),
                                valor_empenhado=D('100'), liberar_total=True)
        for empenho in (abastecimento, self.empenho2_a, vencido, self.empenho_b):
            with self.assertRaises(ValidationError, msg=str(empenho)):
                services.definir_empenho(orcamento, empenho)


class EntregaENotaTest(BaseManutencao):
    def test_fluxo_completo_ate_a_conclusao_com_reserva_estorno_e_consumo(self):
        smv, orcamento = self.aprovar_ate_a_entrega()
        smv.refresh_from_db()
        self.assertEqual((smv.etapa, smv.saida_km), ('ENTREGA', 1250))
        services.enviar_nota_fiscal(smv, self.oficina_a, nf_pecas_numero='123', nf_pecas_valor=D('190.00'), nf_servicos_numero='456',
                                    nf_servicos_valor=D('300.00'), nf_emissao=timezone.localdate())
        smv.refresh_from_db()
        self.assertEqual(smv.etapa, 'NOTA_FISCAL')
        services.conferir_nota(smv, self.gestor_a)
        smv.refresh_from_db()
        self.veiculo_a.refresh_from_db()
        self.assertEqual((smv.etapa, self.veiculo_a.situacao, smv.concluida_por), ('CONCLUIDA', 'DISPONIVEL', self.gestor_a))
        saldo = saldo_do_empenho(self.empenho_a)
        # reservou 500 (aprovacao), estornou 500 e consumiu 490 (a nota): sobra 510
        self.assertEqual((saldo.reservado, saldo.estornado, saldo.consumido, saldo.saldo), (D('500.00'), D('500.00'), D('490.00'), D('510.00')))
        self.assertEqual(sorted(smv.historico.values_list('etapa', flat=True)),
                         sorted(['ENTRADA', 'DIAGNOSTICO', 'ORCAMENTO', 'EXECUCAO', 'ENTREGA', 'NOTA_FISCAL', 'CONCLUIDA']))

    def test_entrega_so_depois_da_aprovacao_e_km_nao_diminui(self):
        smv = self.smv()
        with self.assertRaises(ValidationError):
            services.registrar_entrega(smv, self.oficina_a, saida_em=timezone.now(), saida_km=1300)
        smv, _ = self.orcamento_em_analise(smv=smv)
        smv.refresh_from_db()
        self.assertEqual(smv.etapa, 'ORCAMENTO')   # em analise ainda nao pode registrar a entrega

    def test_km_da_saida_nao_pode_ser_menor_que_o_da_entrada(self):
        smv, orcamento = self.orcamento_em_analise()
        self.assinar(orcamento)
        smv.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.registrar_entrega(smv, self.oficina_a, saida_em=timezone.now(), saida_km=1100)

    def test_nota_acima_do_valor_aprovado_e_recusada(self):
        smv, _ = self.aprovar_ate_a_entrega()
        with self.assertRaisesMessage(ValidationError, 'acima do valor aprovado'):
            services.enviar_nota_fiscal(smv, self.oficina_a, nf_pecas_numero='1', nf_pecas_valor=D('500.01'), nf_emissao=timezone.localdate())

    def test_nota_precisa_de_numero_e_valor_juntos(self):
        smv, _ = self.aprovar_ate_a_entrega()
        for dados in ({'nf_pecas_numero': '1'}, {'nf_servicos_valor': D('10')}, {}):
            with self.assertRaises(ValidationError, msg=str(dados)):
                services.enviar_nota_fiscal(smv, self.oficina_a, nf_emissao=timezone.localdate(), **dados)

    def test_nota_so_depois_da_entrega(self):
        smv, orcamento = self.orcamento_em_analise()
        self.assinar(orcamento)
        smv.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.enviar_nota_fiscal(smv, self.oficina_a, nf_pecas_numero='1', nf_pecas_valor=D('10'), nf_emissao=timezone.localdate())

    def test_nao_confere_duas_vezes(self):
        smv, _ = self.aprovar_ate_a_entrega()
        services.enviar_nota_fiscal(smv, self.oficina_a, nf_servicos_numero='9', nf_servicos_valor=D('100'), nf_emissao=timezone.localdate())
        smv.refresh_from_db()
        services.conferir_nota(smv, self.gestor_a)
        smv.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.conferir_nota(smv, self.gestor_a)
        self.assertEqual(saldo_do_empenho(self.empenho_a).consumido, D('100.00'))

    def test_cancelar_devolve_a_reserva_e_libera_o_veiculo(self):
        smv, orcamento = self.orcamento_em_analise()
        self.assinar(orcamento)
        self.assertEqual(saldo_do_empenho(self.empenho_a).saldo, D('500.00'))
        smv.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.cancelar_smv(smv, self.gestor_a, '')
        services.cancelar_smv(smv, self.gestor_a, 'Veículo vendido')
        smv.refresh_from_db()
        self.veiculo_a.refresh_from_db()
        self.assertEqual((smv.etapa, self.veiculo_a.situacao), ('CANCELADA', 'DISPONIVEL'))
        self.assertEqual(saldo_do_empenho(self.empenho_a).saldo, D('1000.00'))
        with self.assertRaises(ValidationError):
            services.cancelar_smv(smv, self.gestor_a, 'de novo')

    def test_cancelar_encerra_orcamento_em_aberto_e_permite_nova_smv_no_veiculo(self):
        smv, orcamento = self.orcamento_em_analise()
        services.cancelar_smv(smv, self.gestor_a, 'Desistência')
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, 'REPROVADO')
        self.smv()   # o veiculo ja pode ter outra SMV


class AvisosTest(BaseManutencao):
    def test_saldo_baixo_avisa_fiscal_e_gestores_sem_repetir(self):
        smv, orcamento = self.orcamento_em_analise(itens=(('PECA', 'Câmbio', 1, 950),))   # sobra 5% do liberado
        self.assinar(orcamento)
        for usuario in (self.fiscal_a, self.gestor_a):
            avisos = Notificacao.objects.filter(usuario=usuario, canal='APP', entidade='empenhos', entidade_id=self.empenho_a.pk)
            self.assertEqual(avisos.count(), 1, usuario.email)
            self.assertIn('Saldo baixo', avisos.get().assunto)
        self.assertFalse(services.verificar_saldo_baixo(self.empenho2_a))   # empenho com saldo cheio nao avisa
        services.verificar_saldo_baixo(self.empenho_a)
        self.assertEqual(Notificacao.objects.filter(usuario=self.fiscal_a, canal='APP', entidade='empenhos').count(), 1)  # sem repetir enquanto nao lido

    def test_percentual_de_saldo_baixo_vem_da_configuracao(self):
        Municipio.objects.filter(pk=self.a.pk).update(config={'saldo_baixo_percentual': 60})
        self.assertFalse(services.verificar_saldo_baixo(self.empenho_a))   # saldo 100%
        smv, orcamento = self.orcamento_em_analise(itens=(('PECA', 'Peça', 1, 500),))
        self.assinar(orcamento)   # sobra 50%: abaixo de 60%
        self.assertTrue(Notificacao.objects.filter(usuario=self.fiscal_a, entidade='empenhos').exists())

    def test_email_so_vai_para_a_fila_se_a_prefeitura_nao_desligou(self):
        services.abrir_chamado(veiculo=self.veiculo_a, usuario=self.motorista_usuario_a, descricao='x')
        self.assertTrue(Notificacao.objects.filter(usuario=self.fiscal_a, canal='EMAIL', status='PENDENTE').exists())
        Notificacao.objects.all().delete()
        Municipio.objects.filter(pk=self.a.pk).update(config={'email_notificacoes': False})
        services.abrir_chamado(veiculo=self.veiculo2_a, usuario=self.motorista_usuario_a, descricao='y')
        self.assertFalse(Notificacao.objects.filter(canal='EMAIL').exists())
        self.assertTrue(Notificacao.objects.filter(canal='APP', usuario=self.gestor_a).exists())

    def test_chat_avisa_o_outro_lado(self):
        smv = self.smv()
        pasta = tempfile.mkdtemp(prefix='sigfrotas_teste_')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=pasta):
            mensagem = services.enviar_mensagem(smv, self.gestor_a, 'Pode trazer o orçamento até sexta?',
                                                SimpleUploadedFile('foto.jpg', b'\xff\xd8\xff', content_type='image/jpeg'))
        self.assertTrue(Notificacao.objects.filter(usuario=self.oficina_a, entidade='smv', entidade_id=smv.pk).exists())
        self.assertTrue(Anexo.objects.filter(entidade='smv_mensagens', entidade_id=mensagem.pk).exists())
        services.enviar_mensagem(smv, self.oficina_a, 'Sim, sexta.')
        self.assertTrue(Notificacao.objects.filter(usuario=self.gestor_a, entidade='smv', canal='APP').exists())

    def test_mensagem_vazia_e_recusada(self):
        with self.assertRaises(ValidationError):
            services.enviar_mensagem(self.smv(), self.gestor_a, '   ')
