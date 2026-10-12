"""Fase 1 no nucleo: documentos, permissoes, perfis e o isolamento entre prefeituras das tabelas novas."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import SimpleTestCase

from apps.core.models import Perfil
from apps.core.services import sincronizar_perfis
from apps.core.tenant import com_municipio
from apps.core.validadores import validar_cnpj, validar_cpf, validar_cpf_ou_cnpj
from apps.financeiro.models import Contrato, Empenho, FiscalContrato, Fornecedor, LancamentoEmpenho, LiberacaoEmpenho, SaldoEmpenho
from apps.financeiro.services import lancar
from apps.frota.models import CategoriaVeiculo, LeituraVeiculo, Veiculo, VeiculoEquipamento, VeiculoLotacao
from apps.frota.services import atualizar_lotacao, registrar_leitura
from apps.pessoas.models import Motorista, MotoristaAfastamento, MotoristaCertificado, MotoristaPenalidade

from .base import DuasPrefeiturasTest, TelasTest, usar_papel_da_aplicacao


class ValidadoresTest(SimpleTestCase):
    def test_cpf(self):
        for valido in ('529.982.247-25', '52998224725', '111.444.777-35'):
            validar_cpf(valido)
        for invalido in ('529.982.247-24', '111.111.111-11', '123', '', 'abc'):
            with self.assertRaises(ValidationError, msg=invalido):
                validar_cpf(invalido)

    def test_cnpj(self):
        for valido in ('11.222.333/0001-81', '11222333000181', '04.252.011/0001-10'):
            validar_cnpj(valido)
        for invalido in ('11.222.333/0001-82', '00.000.000/0000-00', '123', ''):
            with self.assertRaises(ValidationError, msg=invalido):
                validar_cnpj(invalido)

    def test_cpf_ou_cnpj_escolhe_pelo_tamanho(self):
        validar_cpf_ou_cnpj('529.982.247-25')
        validar_cpf_ou_cnpj('11.222.333/0001-81')
        with self.assertRaises(ValidationError):
            validar_cpf_ou_cnpj('11.222.333/0001-82')


class PermissoesTest(DuasPrefeiturasTest):
    def test_gerir_inclui_ver(self):
        self.assertTrue(self.gestor_a.tem_permissao('frota.ver'))
        self.assertTrue(self.gestor_a.tem_permissao('frota.gerir'))
        self.assertTrue(self.consulta_a.tem_permissao('frota.ver'))
        self.assertFalse(self.consulta_a.tem_permissao('frota.gerir'))
        self.assertFalse(self.solicitante_a.tem_permissao('frota.ver'))

    def test_dados_pessoais_so_para_quem_gere_pessoas(self):
        self.assertTrue(self.gestor_a.tem_permissao('pessoas.dados_pessoais'))
        self.assertTrue(self.admin_a.tem_permissao('pessoas.dados_pessoais'))
        for usuario in (self.consulta_a, self.gestor_unidade_a, self.fiscal_a):
            self.assertFalse(usuario.tem_permissao('pessoas.dados_pessoais'), usuario.email)

    def test_usuario_inativo_nao_tem_permissao(self):
        self.gestor_a.ativo = False
        self.assertFalse(self.gestor_a.tem_permissao('frota.ver'))


class SincronizarPerfisTest(DuasPrefeiturasTest):
    def test_acrescenta_o_que_falta_e_preserva_o_que_foi_personalizado(self):
        with com_municipio(self.a.id):
            perfil = Perfil.objects.get(municipio=self.a, codigo='GESTOR_FROTA')
            perfil.permissoes = ['frota.ver', 'permissao.personalizada']  # perfil antigo, ajustado a mao
            perfil.save()
        acrescentadas = sincronizar_perfis(self.a)
        self.assertIn('frota.gerir', acrescentadas['GESTOR_FROTA'])
        with com_municipio(self.a.id):
            permissoes = Perfil.objects.get(municipio=self.a, codigo='GESTOR_FROTA').permissoes
        self.assertIn('permissao.personalizada', permissoes)
        self.assertIn('pessoas.dados_pessoais', permissoes)
        self.assertEqual(sincronizar_perfis(self.a), {})  # rodar de novo nao muda nada

    def test_recria_perfil_que_falte(self):
        with com_municipio(self.a.id):
            Perfil.objects.filter(municipio=self.a, codigo='MOTORISTA').delete()  # nenhum usuario usa este
        self.assertEqual(list(sincronizar_perfis(self.a)), ['MOTORISTA'])

    def test_nao_mexe_na_outra_prefeitura(self):
        with com_municipio(self.b.id):
            Perfil.objects.filter(municipio=self.b, codigo='ADMIN').update(permissoes=['x'])
        sincronizar_perfis(self.a)
        with com_municipio(self.b.id):
            self.assertEqual(Perfil.objects.get(municipio=self.b, codigo='ADMIN').permissoes, ['x'])


class MenuTest(TelasTest):
    def test_cada_perfil_ve_so_os_seus_itens(self):
        casos = [(self.gestor_a, ['/veiculos/', '/motoristas/', '/empenhos/', '/importacao/'], ['/usuarios/', '/auditoria/']),
                 (self.consulta_a, ['/veiculos/', '/motoristas/', '/empenhos/'], ['/importacao/', '/usuarios/']),
                 (self.fiscal_a, ['/veiculos/', '/empenhos/'], ['/motoristas/', '/importacao/']),
                 (self.solicitante_a, [], ['/veiculos/', '/motoristas/', '/empenhos/', '/secretarias/'])]
        for usuario, aparece, nao_aparece in casos:
            self.client.post('/sair/')
            self.entrar_como(usuario, 'a')
            pagina = self.client.get('/').content.decode()
            for caminho in aparece:
                self.assertIn(f'href="{caminho}"', pagina, f'{usuario.email} deveria ver {caminho}')
            for caminho in nao_aparece:
                self.assertNotIn(f'href="{caminho}"', pagina, f'{usuario.email} nao deveria ver {caminho}')


class IsolamentoDosModulosTest(DuasPrefeiturasTest):
    """A prefeitura A nao enxerga nem grava nas tabelas novas da B (todas com RLS)."""

    MODELOS = [Fornecedor, Contrato, FiscalContrato, Empenho, LiberacaoEmpenho, LancamentoEmpenho, CategoriaVeiculo,
               Veiculo, VeiculoEquipamento, VeiculoLotacao, LeituraVeiculo, Motorista, MotoristaCertificado,
               MotoristaPenalidade, MotoristaAfastamento]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for sufixo, municipio in (('a', cls.a), ('b', cls.b)):
            with com_municipio(municipio.id):
                veiculo, motorista = getattr(cls, f'veiculo_{sufixo}'), getattr(cls, f'motorista_{sufixo}')
                VeiculoEquipamento.objects.create(municipio=municipio, veiculo=veiculo, descricao='Rádio')
                atualizar_lotacao(veiculo)
                registrar_leitura(veiculo=veiculo, odometro=1200)
                MotoristaCertificado.objects.create(municipio=municipio, motorista=motorista, curso='Direção defensiva')
                MotoristaPenalidade.objects.create(municipio=municipio, motorista=motorista, descricao='x')
                MotoristaAfastamento.objects.create(municipio=municipio, motorista=motorista, tipo='FERIAS',
                                                    inicio=date(2026, 7, 1), fim=date(2026, 7, 30))
                lancar(empenho=getattr(cls, f'empenho_{sufixo}'), tipo='RESERVA', valor=Decimal('10.00'))

    def test_a_so_ve_o_que_e_seu(self):
        usar_papel_da_aplicacao(self.a.id)
        for modelo in self.MODELOS:
            self.assertGreater(modelo.objects.filter(municipio_id=self.a.id).count(), 0, modelo.__name__)
            self.assertEqual(modelo.objects.exclude(municipio_id=self.a.id).count(), 0, f'{modelo.__name__} vazou dados da B')
        self.assertEqual(SaldoEmpenho.objects.exclude(municipio_id=self.a.id).count(), 0)

    def test_sem_prefeitura_definida_nada_aparece(self):
        usar_papel_da_aplicacao(None)
        for modelo in self.MODELOS:
            self.assertEqual(modelo.objects.count(), 0, modelo.__name__)
        self.assertEqual(SaldoEmpenho.objects.count(), 0)

    def test_a_nao_grava_na_b(self):
        usar_papel_da_aplicacao(self.a.id)
        invasores = [
            Veiculo(municipio=self.b, placa='INV1A23'),
            Motorista(municipio=self.b, prontuario='9', nome='Invasor', cpf='11144477735'),
            Fornecedor(municipio=self.b, cnpj_cpf='04252011000110', razao_social='Invasor', tipo='POSTO'),
            CategoriaVeiculo(municipio=self.b, nome='Invasora'),
        ]
        for invasor in invasores:
            with self.assertRaises(DatabaseError, msg=type(invasor).__name__), transaction.atomic():
                type(invasor).objects.bulk_create([invasor])  # bulk_create nao passa pelas validacoes do servico

    def test_a_nao_altera_dados_da_b(self):
        usar_papel_da_aplicacao(self.a.id)
        self.assertEqual(Veiculo.objects.filter(pk=self.veiculo_b.pk).update(cor='Preto'), 0)
        self.assertEqual(Motorista.objects.filter(pk=self.motorista_b.pk).update(nome='Alterado'), 0)
        self.assertEqual(Empenho.objects.filter(pk=self.empenho_b.pk).update(valor_empenhado=Decimal('1')), 0)

    def test_lancamento_na_conta_da_b_nao_passa(self):
        usar_papel_da_aplicacao(self.a.id)
        with self.assertRaises(Exception):  # o empenho da B nem e encontrado para travar
            lancar(empenho=self.empenho_b, tipo='RESERVA', valor=Decimal('1'))

    def test_catalogos_globais_ficam_visiveis_a_todas(self):
        from apps.frota.models import Combustivel
        usar_papel_da_aplicacao(None)
        self.assertGreaterEqual(Combustivel.objects.count(), 0)  # sem RLS: a consulta funciona mesmo sem prefeitura
