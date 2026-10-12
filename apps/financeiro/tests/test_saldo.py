import threading
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase

from apps.core.models import CentroCusto
from apps.core.services import criar_municipio
from apps.core.tenant import com_municipio
from apps.core.tests.base import DuasPrefeiturasTest, usar_papel_da_aplicacao
from apps.financeiro.models import Empenho, SaldoEmpenho
from apps.financeiro.services import SaldoInsuficiente, criar_empenho, lancar, liberar, saldo_do_empenho

D = Decimal


def dados(base, **extras):
    padrao = dict(municipio=base.a, finalidade='MANUTENCAO', centro_custo=base.centro_a, numero='99', exercicio=2026,
                  vigencia_ini=date(2026, 1, 1), vigencia_fim=date(2026, 12, 31), valor_empenhado=D('1000.00'))
    return {**padrao, **extras}


class SaldoTest(DuasPrefeiturasTest):
    def saldo(self, empenho):
        return saldo_do_empenho(empenho).saldo

    def test_liberado_de_uma_vez_deixa_todo_o_valor_disponivel(self):
        s = saldo_do_empenho(self.empenho_a)
        self.assertEqual((s.valor_empenhado, s.liberado, s.saldo), (D('1000.00'), D('1000.00'), D('1000.00')))

    def test_reserva_e_consumo_baixam_o_saldo(self):
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('300.00'))
        lancar(empenho=self.empenho_a, tipo='CONSUMO', valor=D('200.00'))
        s = saldo_do_empenho(self.empenho_a)
        self.assertEqual((s.reservado, s.consumido, s.saldo), (D('300.00'), D('200.00'), D('500.00')))

    def test_nao_reserva_acima_do_saldo(self):
        with self.assertRaises(SaldoInsuficiente):
            lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('1000.01'))
        self.assertEqual(self.saldo(self.empenho_a), D('1000.00'))

    def test_pode_usar_o_saldo_exato(self):
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('1000.00'))
        self.assertEqual(self.saldo(self.empenho_a), D('0.00'))
        with self.assertRaises(SaldoInsuficiente):
            lancar(empenho=self.empenho_a, tipo='CONSUMO', valor=D('0.01'))

    def test_estorno_devolve_o_saldo(self):
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('400.00'))
        lancar(empenho=self.empenho_a, tipo='ESTORNO', valor=D('400.00'))
        self.assertEqual(self.saldo(self.empenho_a), D('1000.00'))

    def test_estorno_nao_passa_do_que_foi_lancado(self):
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('100.00'))
        with self.assertRaises(ValidationError):
            lancar(empenho=self.empenho_a, tipo='ESTORNO', valor=D('100.01'))

    def test_nota_conferida_converte_reserva_em_consumo_pelo_valor_final(self):
        """Aprovou com reserva de 300; a nota fechou em 250: estorna a reserva e consome 250."""
        lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('300.00'), orcamento_id=7)
        lancar(empenho=self.empenho_a, tipo='ESTORNO', valor=D('300.00'), orcamento_id=7)
        lancar(empenho=self.empenho_a, tipo='CONSUMO', valor=D('250.00'), orcamento_id=7)
        self.assertEqual(self.saldo(self.empenho_a), D('750.00'))

    def test_valor_precisa_ser_positivo_e_tipo_valido(self):
        for valor in (D('0'), D('-5')):
            with self.assertRaises(ValidationError):
                lancar(empenho=self.empenho_a, tipo='RESERVA', valor=valor)
        with self.assertRaises(ValidationError):
            lancar(empenho=self.empenho_a, tipo='OUTRO', valor=D('1'))

    def test_empenho_inativo_nao_recebe_lancamento_nem_liberacao(self):
        Empenho.objects.filter(pk=self.empenho_a.pk).update(ativo=False)
        with self.assertRaises(ValidationError):
            lancar(empenho=self.empenho_a, tipo='RESERVA', valor=D('1'))
        with self.assertRaises(ValidationError):
            liberar(empenho=self.empenho_a, valor=D('1'))


class LiberacaoParceladaTest(DuasPrefeiturasTest):
    def test_so_o_valor_liberado_pode_ser_usado(self):
        empenho = criar_empenho(**dados(self))  # sem liberar: parcelado
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('0.00'))
        liberar(empenho=empenho, valor=D('400.00'))
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('400.00'))
        with self.assertRaises(SaldoInsuficiente):  # o empenhado e 1000, mas so 400 foram liberados
            lancar(empenho=empenho, tipo='RESERVA', valor=D('500.00'))
        liberar(empenho=empenho, valor=D('600.00'))
        lancar(empenho=empenho, tipo='RESERVA', valor=D('500.00'))
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('500.00'))

    def test_liberacoes_nao_passam_do_valor_empenhado(self):
        empenho = criar_empenho(**dados(self))
        liberar(empenho=empenho, valor=D('700.00'))
        with self.assertRaisesMessage(ValidationError, 'R$ 300,00'):
            liberar(empenho=empenho, valor=D('300.01'))
        liberar(empenho=empenho, valor=D('300.00'))
        self.assertEqual(saldo_do_empenho(empenho).liberado, D('1000.00'))


class RegrasDoEmpenhoTest(DuasPrefeiturasTest):
    def test_empenho_de_abastecimento_pede_contrato_de_combustivel(self):
        with self.assertRaises(ValidationError) as erro:  # o contrato_a e de manutencao
            criar_empenho(**{**dados(self, contrato=self.contrato_a, numero='50'), 'finalidade': 'ABASTECIMENTO'})
        self.assertIn('contrato', erro.exception.message_dict)

    def test_periodo_nao_pode_terminar_antes_de_comecar(self):
        with self.assertRaises(ValidationError):
            criar_empenho(**{**dados(self), 'vigencia_fim': date(2025, 12, 31)})

    def test_prorrogacao_e_um_novo_empenho_ligado_ao_original(self):
        novo = criar_empenho(**dados(self, empenho_origem=self.empenho_a, numero='60'))
        self.assertEqual(list(self.empenho_a.prorrogacoes.all()), [novo])

    def test_vinculo_com_centro_de_custo_de_outra_prefeitura_e_recusado(self):
        with self.assertRaises(ValidationError):
            criar_empenho(**{**dados(self), 'centro_custo': self.centro_b})

    def test_saldo_so_aparece_para_a_propria_prefeitura(self):
        usar_papel_da_aplicacao(self.a.id)
        self.assertEqual(SaldoEmpenho.objects.exclude(municipio_id=self.a.id).count(), 0)
        self.assertGreater(SaldoEmpenho.objects.filter(municipio_id=self.a.id).count(), 0)


class ConcorrenciaTest(TransactionTestCase):
    """Duas operacoes ao mesmo tempo nao podem gastar o mesmo saldo (o empenho e travado)."""

    def test_duas_reservas_simultaneas_so_uma_passa(self):
        municipio = criar_municipio(nome='Concorrencia', slug='conc', uf='SP', cnpj='33333333000133')
        with com_municipio(municipio.id):
            centro = CentroCusto.objects.create(municipio=municipio, codigo='1', nome='Frota')
            empenho = criar_empenho(municipio=municipio, finalidade='MANUTENCAO', centro_custo=centro, numero='1',
                                    exercicio=2026, vigencia_ini=date(2026, 1, 1), vigencia_fim=date(2026, 12, 31),
                                    valor_empenhado=D('100.00'), liberar_total=True)
        resultados, barreira = [], threading.Barrier(2)

        def reservar():
            try:
                barreira.wait()
                lancar(empenho=empenho, tipo='RESERVA', valor=D('60.00'))
                resultados.append('ok')
            except SaldoInsuficiente:
                resultados.append('recusado')
            finally:
                connection.close()

        threads = [threading.Thread(target=reservar) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(resultados), ['ok', 'recusado'])
        self.assertEqual(saldo_do_empenho(empenho).saldo, D('40.00'))
