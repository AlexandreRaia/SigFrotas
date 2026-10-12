from datetime import date
from decimal import Decimal

from apps.core.tests.base import TelasTest, usar_papel_da_aplicacao
from apps.financeiro.models import Contrato, Empenho, Fornecedor
from apps.financeiro.services import lancar, saldo_do_empenho

D = Decimal


class EmpenhosTelasTest(TelasTest):
    def dados(self, **extras):
        return {'finalidade': 'MANUTENCAO', 'centro_custo': self.centro_a.pk, 'numero': '77', 'exercicio': 2026,
                'vigencia_ini': '2026-01-01', 'vigencia_fim': '2026-12-31', 'valor_empenhado': '500.00', **extras}

    def test_gestor_ve_todos_os_empenhos_da_prefeitura(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.get('/empenhos/')
        self.assertContains(resposta, f'/empenhos/{self.empenho_a.pk}/')
        self.assertContains(resposta, f'/empenhos/{self.empenho2_a.pk}/')
        self.assertNotContains(resposta, f'/empenhos/{self.empenho_b.pk}/')
        self.assertContains(resposta, 'R$ 1.000,00')  # saldo formatado

    def test_fiscal_ve_so_os_empenhos_dos_seus_centros_de_custo(self):
        self.entrar_como(self.fiscal_a, 'a')
        resposta = self.client.get('/empenhos/')
        self.assertContains(resposta, f'/empenhos/{self.empenho_a.pk}/')
        self.assertNotContains(resposta, f'/empenhos/{self.empenho2_a.pk}/')
        self.assertEqual(self.client.get(f'/empenhos/{self.empenho_a.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/empenhos/{self.empenho2_a.pk}/').status_code, 404)

    def test_fiscal_ve_so_os_contratos_em_que_esta_designado(self):
        usar_papel_da_aplicacao(self.a.id)  # sem prefeitura definida a RLS esconde o fornecedor
        outro = Contrato.objects.create(municipio=self.a, fornecedor=self.fornecedor_a, tipo='MANUTENCAO', numero='C-2',
                                        objeto='Outro', vigencia_ini=date(2026, 1, 1), vigencia_fim=date(2026, 12, 31))
        self.entrar_como(self.fiscal_a, 'a')
        resposta = self.client.get('/contratos/')
        self.assertContains(resposta, 'C-1')
        self.assertNotContains(resposta, outro.numero)

    def test_consulta_ve_mas_nao_cria(self):
        self.entrar_como(self.consulta_a, 'a')
        self.assertEqual(self.client.get('/empenhos/').status_code, 200)
        self.assertNotContains(self.client.get('/empenhos/'), 'Novo</a>')
        self.assertEqual(self.client.post('/empenhos/novo/', self.dados()).status_code, 403)
        self.assertEqual(self.client.post(f'/empenhos/{self.empenho_a.pk}/liberar/', {'data': '2026-01-01', 'valor': '1'}).status_code, 403)

    def test_solicitante_nao_acessa_financeiro(self):
        self.entrar_como(self.solicitante_a, 'a')
        for pagina in ('/empenhos/', '/contratos/', '/fornecedores/', '/fiscais/'):
            self.assertEqual(self.client.get(pagina).status_code, 403, pagina)

    def test_outra_prefeitura_nao_ve_o_empenho(self):
        self.entrar_como(self.admin_a, 'a')
        self.assertEqual(self.client.get(f'/empenhos/{self.empenho_b.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/empenhos/{self.empenho_b.pk}/editar/').status_code, 404)

    def test_cria_empenho_com_liberacao_total(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/empenhos/novo/', self.dados(liberar_total='on'))
        empenho = Empenho.objects.get(numero='77')
        self.assertRedirects(resposta, f'/empenhos/{empenho.pk}/', fetch_redirect_response=False)
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('500.00'))

    def test_cria_empenho_parcelado_e_libera_parcelas(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/empenhos/novo/', self.dados())
        empenho = Empenho.objects.get(numero='77')
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('0.00'))
        self.client.post(f'/empenhos/{empenho.pk}/liberar/', {'data': '2026-02-01', 'valor': '200.00', 'observacao': '1a parcela'})
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('200.00'))
        resposta = self.client.post(f'/empenhos/{empenho.pk}/liberar/', {'data': '2026-03-01', 'valor': '400.00'})
        self.assertContains(resposta, 'Ainda é possível liberar R$ 300,00')
        self.assertEqual(saldo_do_empenho(empenho).liberado, D('200.00'))

    def test_numero_repetido_no_mesmo_exercicio_e_recusado(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/empenhos/novo/', self.dados(numero='1'))
        self.assertContains(resposta, 'Já existe')

    def test_prorrogar_preenche_o_formulario_e_liga_ao_original(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.get(f'/empenhos/novo/?prorroga={self.empenho_a.pk}')
        self.assertContains(resposta, f'value="{self.empenho_a.pk}"')
        self.client.post('/empenhos/novo/', self.dados(empenho_origem=self.empenho_a.pk, vigencia_ini='2027-01-01',
                                                       vigencia_fim='2027-12-31', exercicio=2027, numero='1'))
        self.assertEqual(Empenho.objects.get(exercicio=2027).empenho_origem_id, self.empenho_a.pk)

    def test_prorrogacao_precisa_ter_o_mesmo_centro_e_finalidade(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/empenhos/novo/', self.dados(empenho_origem=self.empenho_a.pk, centro_custo=self.centro2_a.pk))
        self.assertContains(resposta, 'mesma finalidade e o mesmo centro de custo')

    def test_nao_aceita_centro_de_custo_de_outra_prefeitura(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/empenhos/novo/', self.dados(centro_custo=self.centro_b.pk))
        self.assertFalse(Empenho.objects.filter(numero='77').exists())

    def test_nao_muda_centro_de_empenho_com_lancamentos(self):
        usar_papel_da_aplicacao(self.a.id)
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('10'))
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post(f'/empenhos/{self.empenho_a.pk}/editar/',
                                    self.dados(numero='1', centro_custo=self.centro2_a.pk, valor_empenhado='1000.00'))
        self.assertContains(resposta, 'não pode mudar')

    def test_valor_nao_pode_ficar_abaixo_do_liberado(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post(f'/empenhos/{self.empenho_a.pk}/editar/', self.dados(numero='1', valor_empenhado='500.00'))
        self.assertContains(resposta, 'abaixo do que já foi liberado')

    def test_detalhe_mostra_resumo_liberacoes_e_lancamentos(self):
        usar_papel_da_aplicacao(self.a.id)
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('250.00'), orcamento_id=3)
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.get(f'/empenhos/{self.empenho_a.pk}/')
        for texto in ('R$ 750,00', 'R$ 250,00', 'Orçamento 3', 'Liberação do valor total.'):
            self.assertContains(resposta, texto)


class CadastrosFinanceirosTest(TelasTest):
    def setUp(self):
        super().setUp()
        self.entrar_como(self.gestor_a, 'a')

    def test_fornecedor_com_cnpj_invalido_e_recusado(self):
        resposta = self.client.post('/fornecedores/novo/', {'cnpj_cpf': '11.222.333/0001-82', 'razao_social': 'X', 'tipo': 'POSTO'})
        self.assertContains(resposta, 'CNPJ inválido')

    def test_fornecedor_guarda_so_os_numeros(self):
        self.client.post('/fornecedores/novo/', {'cnpj_cpf': '04.252.011/0001-10', 'razao_social': 'Posto Boa Viagem', 'tipo': 'POSTO'})
        self.assertEqual(Fornecedor.objects.get(razao_social='Posto Boa Viagem').cnpj_cpf, '04252011000110')

    def test_fornecedor_aceita_cpf_de_autonomo(self):
        self.client.post('/fornecedores/novo/', {'cnpj_cpf': '529.982.247-25', 'razao_social': 'Mecânico Autônomo', 'tipo': 'OFICINA'})
        self.assertTrue(Fornecedor.objects.filter(cnpj_cpf='52998224725').exists())

    def test_mesmo_cnpj_nao_repete_na_prefeitura_mas_pode_em_outra(self):
        resposta = self.client.post('/fornecedores/novo/', {'cnpj_cpf': '11222333000181', 'razao_social': 'Outra', 'tipo': 'OFICINA'})
        self.assertContains(resposta, 'Já existe')
        self.assertEqual(self.fornecedor_a.cnpj_cpf, self.fornecedor_b.cnpj_cpf)  # A e B tem o mesmo, sem conflito

    def test_busca_de_fornecedor_por_nome(self):
        self.assertContains(self.client.get('/fornecedores/?busca=oficina'), 'Oficina A')
        self.assertNotContains(self.client.get('/fornecedores/?busca=zzzz'), 'Oficina A')

    def test_contrato_com_vigencia_invertida_e_recusado(self):
        resposta = self.client.post('/contratos/novo/', {
            'numero': 'C-9', 'fornecedor': self.fornecedor_a.pk, 'tipo': 'MANUTENCAO', 'objeto': 'x',
            'vigencia_ini': '2026-12-31', 'vigencia_fim': '2026-01-01'})
        self.assertContains(resposta, 'não pode ser antes do início')

    def test_contrato_nao_aceita_fornecedor_de_outra_prefeitura(self):
        self.client.post('/contratos/novo/', {
            'numero': 'C-9', 'fornecedor': self.fornecedor_b.pk, 'tipo': 'MANUTENCAO', 'objeto': 'x',
            'vigencia_ini': '2026-01-01', 'vigencia_fim': '2026-12-31'})
        self.assertFalse(Contrato.objects.filter(numero='C-9').exists())

    def test_fiscal_so_escolhe_usuarios_com_perfil_fiscal(self):
        resposta = self.client.get('/fiscais/novo/')
        usuarios = list(resposta.context['form'].fields['usuario'].queryset)
        self.assertEqual(usuarios, [self.fiscal_a])

    def test_designa_fiscal_para_todos_os_centros(self):
        self.client.post('/fiscais/novo/', {'contrato': self.contrato_a.pk, 'usuario': self.fiscal_a.pk, 'vigencia_ini': '2026-01-01'})
        self.assertEqual(self.contrato_a.fiscalcontrato_set.count(), 2)
        self.assertTrue(self.contrato_a.fiscalcontrato_set.filter(centro_custo__isnull=True).exists())
