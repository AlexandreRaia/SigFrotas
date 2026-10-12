import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.models import Anexo
from apps.core.tests.base import DuasPrefeiturasTest, TelasTest, usar_papel_da_aplicacao
from apps.frota.models import Marca, Modelo, Veiculo, VeiculoLotacao
from apps.frota.services import atualizar_lotacao, registrar_leitura


class RegrasDoVeiculoTest(DuasPrefeiturasTest):
    def novo(self, **extras):
        veiculo = Veiculo(municipio=self.a, **{'placa': 'DEF2G34', **extras})
        veiculo.full_clean(exclude=['municipio'])
        return veiculo

    def test_placa_antiga_e_mercosul_sao_aceitas(self):
        for placa in ('ABC1234', 'abc-1d23'):
            self.assertRegex(self.novo(placa=placa).placa, r'^[A-Z]{3}\d[A-Z0-9]\d{2}$')

    def test_placa_invalida_e_recusada(self):
        for placa in ('AB1234', 'ABCD123', '1234567', ''):
            with self.assertRaises(ValidationError, msg=placa):
                self.novo(placa=placa)

    def test_chassi_e_renavam_precisam_estar_certos(self):
        for extras in ({'chassi': 'ABC'}, {'chassi': '9BWZZZ377VT00450I'}, {'renavam': '12AB'}):
            with self.assertRaises(ValidationError, msg=str(extras)):
                self.novo(**extras)
        self.novo(chassi='9bwzzz377vt004251', renavam='123456789')  # valido (maiusculas por conta do sistema)

    def test_unidade_precisa_ser_da_secretaria(self):
        with self.assertRaises(ValidationError) as erro:
            self.novo(secretaria=self.sec2_a, unidade=self.unidade_a)  # a unidade e da SMA, nao da SME
        self.assertIn('unidade', erro.exception.message_dict)

    def test_baixa_exige_data_e_motivo(self):
        with self.assertRaises(ValidationError) as erro:
            self.novo(situacao='BAIXADO')
        self.assertEqual(set(erro.exception.message_dict), {'data_baixa', 'motivo_baixa'})
        self.novo(situacao='BAIXADO', data_baixa=date(2026, 5, 1), motivo_baixa='Sinistro com perda total')

    def test_mesma_placa_vale_em_outra_prefeitura(self):
        self.assertEqual(self.veiculo_a.placa, self.veiculo_b.placa)


class LeituraTest(DuasPrefeiturasTest):
    def test_km_atualiza_e_nunca_diminui(self):
        registrar_leitura(veiculo=self.veiculo_a, odometro=1500)
        self.veiculo_a.refresh_from_db()
        self.assertEqual(self.veiculo_a.odometro_atual, 1500)
        with self.assertRaisesMessage(ValidationError, 'não pode diminuir'):
            registrar_leitura(veiculo=self.veiculo_a, odometro=1499)
        self.assertEqual(self.veiculo_a.leituras.count(), 1)

    def test_mesmo_km_e_aceito(self):
        registrar_leitura(veiculo=self.veiculo_a, odometro=1000)

    def test_horimetro_tambem_nao_diminui(self):
        registrar_leitura(veiculo=self.veiculo_a, horimetro=Decimal('10.5'))
        with self.assertRaises(ValidationError):
            registrar_leitura(veiculo=self.veiculo_a, horimetro=Decimal('10.4'))

    def test_precisa_de_km_ou_horimetro(self):
        with self.assertRaises(ValidationError):
            registrar_leitura(veiculo=self.veiculo_a)


class VeiculosTelasTest(TelasTest):
    def dados(self, **extras):
        return {'placa': 'GHI3J45', 'tipo_frota': 'PROPRIO', 'situacao': 'DISPONIVEL', 'secretaria': self.sec_a.pk,
                'centro_custo': self.centro_a.pk, 'odometro_atual': '2500', **extras}

    def test_gestor_cadastra_veiculo_com_leitura_e_lotacao_iniciais(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/veiculos/novo/', self.dados(placa='ghi-3j45'))
        veiculo = Veiculo.objects.get(placa='GHI3J45')
        self.assertRedirects(resposta, f'/veiculos/{veiculo.pk}/', fetch_redirect_response=False)
        self.assertEqual((veiculo.municipio_id, veiculo.odometro_atual), (self.a.id, 2500))
        self.assertEqual(veiculo.leituras.get().odometro, 2500)
        self.assertEqual(veiculo.lotacoes.get().secretaria_id, self.sec_a.pk)

    def test_placa_repetida_mesmo_escrita_diferente_e_recusada(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/veiculos/novo/', self.dados(placa='abc-1d23'))
        self.assertContains(resposta, 'Já existe')

    def test_trocar_a_secretaria_guarda_o_historico_de_lotacao(self):
        usar_papel_da_aplicacao(self.a.id)
        atualizar_lotacao(self.veiculo_a)  # o veiculo da fixture nasceu sem historico; o formulario faz isto ao cadastrar
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/veiculos/{self.veiculo_a.pk}/editar/', self.dados(placa='ABC1D23', secretaria=self.sec2_a.pk,
                                                                               centro_custo=self.centro2_a.pk))
        lotacoes = list(VeiculoLotacao.objects.filter(veiculo=self.veiculo_a))
        abertas = [l for l in lotacoes if l.fim is None]
        self.assertEqual([l.secretaria_id for l in abertas], [self.sec2_a.pk])
        self.assertTrue(any(l.fim is not None and l.secretaria_id == self.sec_a.pk for l in lotacoes))

    def test_editar_nao_muda_o_km(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/veiculos/{self.veiculo_a.pk}/editar/', self.dados(placa='ABC1D23', odometro_atual='1'))
        self.veiculo_a.refresh_from_db()
        self.assertEqual(self.veiculo_a.odometro_atual, 1000)

    def test_unidade_de_outra_secretaria_e_recusada(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/veiculos/novo/', self.dados(secretaria=self.sec2_a.pk, unidade=self.unidade_a.pk))
        self.assertContains(resposta, 'não pertence à secretaria')

    def test_nao_cadastra_com_secretaria_ou_centro_de_outra_prefeitura(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/veiculos/novo/', self.dados(secretaria=self.sec_b.pk))
        self.client.post('/veiculos/novo/', self.dados(centro_custo=self.centro_b.pk))
        self.assertFalse(Veiculo.objects.filter(placa='GHI3J45').exists())

    # --- quem ve o que ---
    def test_gestor_unidade_ve_so_a_propria_secretaria(self):
        self.entrar_como(self.gestor_unidade_a, 'a')
        resposta = self.client.get('/veiculos/')
        self.assertContains(resposta, f'/veiculos/{self.veiculo_a.pk}/')
        self.assertNotContains(resposta, f'/veiculos/{self.veiculo2_a.pk}/')
        self.assertEqual(self.client.get(f'/veiculos/{self.veiculo2_a.pk}/').status_code, 404)
        self.assertNotContains(resposta, 'Novo</a>')

    def test_fiscal_ve_so_os_veiculos_dos_seus_centros(self):
        self.entrar_como(self.fiscal_a, 'a')
        resposta = self.client.get('/veiculos/')
        self.assertContains(resposta, f'/veiculos/{self.veiculo_a.pk}/')
        self.assertNotContains(resposta, f'/veiculos/{self.veiculo2_a.pk}/')

    def test_consulta_ve_tudo_mas_nao_altera(self):
        self.entrar_como(self.consulta_a, 'a')
        resposta = self.client.get('/veiculos/')
        self.assertContains(resposta, f'/veiculos/{self.veiculo2_a.pk}/')
        self.assertEqual(self.client.post('/veiculos/novo/', self.dados()).status_code, 403)
        self.assertEqual(self.client.post(f'/veiculos/{self.veiculo_a.pk}/leituras/nova/', {'odometro': '5000'}).status_code, 403)

    def test_solicitante_nao_acessa_a_frota(self):
        self.entrar_como(self.solicitante_a, 'a')
        self.assertEqual(self.client.get('/veiculos/').status_code, 403)

    def test_outra_prefeitura_nao_ve_o_veiculo(self):
        self.entrar_como(self.admin_a, 'a')
        self.assertEqual(self.client.get(f'/veiculos/{self.veiculo_b.pk}/').status_code, 404)
        self.assertNotContains(self.client.get('/veiculos/?busca=XYZ'), f'/veiculos/{self.veiculo_b.pk}/')

    def test_busca_e_filtro(self):
        self.entrar_como(self.gestor_a, 'a')
        self.assertContains(self.client.get('/veiculos/?busca=abc1d'), f'/veiculos/{self.veiculo_a.pk}/')
        self.assertNotContains(self.client.get('/veiculos/?busca=abc1d'), f'/veiculos/{self.veiculo2_a.pk}/')
        self.assertNotContains(self.client.get('/veiculos/?situacao=BAIXADO'), f'/veiculos/{self.veiculo_a.pk}/')

    # --- pagina do veiculo ---
    def test_registra_leitura_pela_pagina_e_recusa_km_menor(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/veiculos/{self.veiculo_a.pk}/leituras/nova/', {'odometro': '1800'})
        self.client.post(f'/veiculos/{self.veiculo_a.pk}/leituras/nova/', {'odometro': '1700'})
        self.veiculo_a.refresh_from_db()
        self.assertEqual(self.veiculo_a.odometro_atual, 1800)
        self.assertContains(self.client.get(f'/veiculos/{self.veiculo_a.pk}/'), 'não pode ser menor')

    def test_equipamentos_adicionar_e_remover(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/veiculos/{self.veiculo_a.pk}/equipamentos/novo/', {'descricao': 'Ar-condicionado'})
        equipamento = self.veiculo_a.equipamentos.get()
        self.assertContains(self.client.get(f'/veiculos/{self.veiculo_a.pk}/'), 'Ar-condicionado')
        self.client.post(f'/veiculos/{self.veiculo_a.pk}/equipamentos/{equipamento.pk}/excluir/')
        self.assertEqual(self.veiculo_a.equipamentos.count(), 0)

    def test_nao_remove_equipamento_de_outro_veiculo(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/veiculos/{self.veiculo2_a.pk}/equipamentos/novo/', {'descricao': 'Rádio'})
        equipamento = self.veiculo2_a.equipamentos.get()
        resposta = self.client.post(f'/veiculos/{self.veiculo_a.pk}/equipamentos/{equipamento.pk}/excluir/')
        self.assertEqual(resposta.status_code, 404)

    def test_anexo_do_veiculo_respeita_o_escopo_e_a_permissao(self):
        pasta = tempfile.mkdtemp(prefix='sigfrotas_teste_')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=pasta):
            self.entrar_como(self.gestor_a, 'a')
            for veiculo in (self.veiculo_a, self.veiculo2_a):
                self.client.post(f'/veiculos/{veiculo.pk}/anexos/novo/', {
                    'categoria': 'CRLV', 'arquivo': SimpleUploadedFile('crlv.pdf', b'%PDF-1.4 teste', content_type='application/pdf')})
            a1 = Anexo.objects.get(entidade='veiculos', entidade_id=self.veiculo_a.pk)
            a2 = Anexo.objects.get(entidade='veiculos', entidade_id=self.veiculo2_a.pk)
            self.assertEqual(self.client.get(f'/anexos/{a1.pk}/').status_code, 200)
            self.client.post('/sair/')
            self.entrar_como(self.gestor_unidade_a, 'a')   # SMA: ve o anexo do veiculo da SMA, nao o da SME
            self.assertEqual(self.client.get(f'/anexos/{a1.pk}/').status_code, 200)
            self.assertEqual(self.client.get(f'/anexos/{a2.pk}/').status_code, 404)
            self.client.post('/sair/')
            self.entrar_como(self.solicitante_a, 'a')      # sem frota.ver
            self.assertEqual(self.client.get(f'/anexos/{a1.pk}/').status_code, 403)


class MarcasModelosTest(TelasTest):
    def test_gestor_cadastra_marca_e_modelo(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/marcas/', {'acao': 'marca', 'nome': 'Fiat'})
        marca = Marca.objects.get(nome='Fiat')
        self.client.post('/marcas/', {'acao': 'modelo', 'marca': marca.pk, 'nome': 'Uno'})
        self.assertEqual(str(Modelo.objects.get(nome='Uno')), 'Fiat Uno')
        self.assertContains(self.client.get('/marcas/'), 'Uno')

    def test_repeticao_e_recusada_sem_diferenciar_maiusculas(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/marcas/', {'acao': 'marca', 'nome': 'Fiat'})
        self.assertContains(self.client.post('/marcas/', {'acao': 'marca', 'nome': 'FIAT'}), 'já existe')
        marca = Marca.objects.get(nome='Fiat')
        self.client.post('/marcas/', {'acao': 'modelo', 'marca': marca.pk, 'nome': 'Uno'})
        self.assertContains(self.client.post('/marcas/', {'acao': 'modelo', 'marca': marca.pk, 'nome': 'uno'}), 'já existe')

    def test_catalogo_e_compartilhado_entre_prefeituras(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/marcas/', {'acao': 'marca', 'nome': 'Volkswagen'})
        self.client.post('/sair/')
        self.entrar_como(self.consulta_b, 'b')
        self.assertContains(self.client.get('/marcas/'), 'Volkswagen')

    def test_consulta_so_olha(self):
        self.entrar_como(self.consulta_a, 'a')
        self.assertEqual(self.client.get('/marcas/').status_code, 200)
        self.assertEqual(self.client.post('/marcas/', {'acao': 'marca', 'nome': 'Ford'}).status_code, 403)
        self.assertFalse(Marca.objects.filter(nome='Ford').exists())


class CategoriasTest(TelasTest):
    def test_gestor_cria_categoria_e_nome_nao_repete(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/categorias-veiculo/novo/', {'nome': 'Caminhão', 'cnh_minima': 'C'})
        self.assertContains(self.client.post('/categorias-veiculo/novo/', {'nome': 'Caminhão'}), 'Já existe')
        usar_papel_da_aplicacao(self.a.id)
        self.assertEqual(self.client.get('/categorias-veiculo/').status_code, 200)
