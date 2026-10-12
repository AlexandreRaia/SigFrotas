from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import Secretaria
from apps.core.tests.base import DuasPrefeiturasTest, TelasTest, usar_papel_da_aplicacao
from apps.frota.models import Combustivel, Marca, Modelo, Veiculo
from apps.importacao.leitor import data_iso, decimal_br, escolha, inteiro, ler_csv
from apps.pessoas.models import Motorista

CABECALHO_VEICULOS = ['placa', 'marca', 'modelo', 'combustivel', 'categoria', 'secretaria', 'centro_custo', 'km', 'tipo_frota']


def csv(linhas, sep=';', codificacao='utf-8-sig'):
    return '\n'.join(sep.join(linha) for linha in linhas).encode(codificacao)


def arquivo(conteudo):
    return SimpleUploadedFile('planilha.csv', conteudo, content_type='text/csv')


class LeitorTest(DuasPrefeiturasTest):
    def test_aceita_ponto_e_virgula_virgula_e_latin1(self):
        for sep, cod in ((';', 'utf-8-sig'), (',', 'utf-8'), (';', 'latin-1')):
            cabecalhos, linhas = ler_csv(csv([['Placa', 'Centro de Custo'], ['ABC1D23', 'São Paulo']], sep, cod))
            self.assertEqual(cabecalhos, ['placa', 'centro_de_custo'])
            self.assertEqual(linhas[0][1]['placa'], 'ABC1D23')

    def test_ignora_linhas_em_branco_e_numera_a_partir_da_2(self):
        _, linhas = ler_csv(csv([['placa'], ['A'], [''], ['B']]))
        self.assertEqual([n for n, _ in linhas], [2, 4])

    def test_arquivo_vazio_e_recusado(self):
        with self.assertRaises(ValueError):
            ler_csv(b'')

    def test_conversores(self):
        self.assertEqual(decimal_br('1.234,56'), '1234.56')
        self.assertEqual(decimal_br('47,5'), '47.5')
        self.assertEqual(inteiro('35.000 km'), '35000')
        self.assertEqual(data_iso('05/03/2028'), '2028-03-05')
        self.assertEqual(data_iso('2028-03-05'), '2028-03-05')
        self.assertEqual(escolha('proprio', [('PROPRIO', 'Próprio')], 'x'), 'PROPRIO')
        self.assertEqual(escolha('Doação', [('DOACAO', 'Doação')], 'x'), 'DOACAO')
        with self.assertRaises(ValueError):
            escolha('xyz', [('PROPRIO', 'Próprio')], 'Tipo')


class ImportarVeiculosTest(TelasTest):
    def setUp(self):
        super().setUp()
        Combustivel.objects.get_or_create(nome='Gasolina')
        self.entrar_como(self.gestor_a, 'a')

    def enviar(self, linhas, acao='verificar', **extras):
        return self.client.post('/importacao/veiculos/', {'arquivo': arquivo(csv([CABECALHO_VEICULOS] + linhas, **extras)), 'acao': acao})

    def linha(self, placa='JKL4M56', **extras):
        valores = {'placa': placa, 'marca': 'Fiat', 'modelo': 'Uno', 'combustivel': 'Gasolina', 'categoria': 'Automóvel',
                   'secretaria': 'SMA', 'centro_custo': '100', 'km': '35.000', 'tipo_frota': 'Próprio', **extras}
        return [valores[c] for c in CABECALHO_VEICULOS]

    def test_verificar_nao_grava_nada(self):
        resposta = self.enviar([self.linha()])
        self.assertContains(resposta, 'Tudo certo: 1 linha')
        self.assertFalse(Veiculo.objects.filter(placa='JKL4M56').exists())
        self.assertFalse(Marca.objects.filter(nome='Fiat').exists())  # nem as marcas criadas durante a conferencia ficam

    def test_importar_grava_com_marca_modelo_km_e_lotacao(self):
        resposta = self.enviar([self.linha(), self.linha('MNO5P67', modelo='Palio')], acao='importar')
        self.assertRedirects(resposta, '/veiculos/', fetch_redirect_response=False)
        veiculo = Veiculo.objects.get(placa='JKL4M56')
        self.assertEqual((veiculo.municipio_id, veiculo.odometro_atual, veiculo.secretaria_id, veiculo.centro_custo_id),
                         (self.a.id, 35000, self.sec_a.pk, self.centro_a.pk))
        self.assertEqual(str(veiculo.modelo), 'Fiat Uno')
        self.assertEqual(Marca.objects.filter(nome='Fiat').count(), 1)  # a marca e reaproveitada
        self.assertEqual(veiculo.lotacoes.count(), 1)
        self.assertEqual(Veiculo.objects.filter(placa='MNO5P67').count(), 1)

    def test_uma_linha_com_erro_impede_todas(self):
        resposta = self.enviar([self.linha(), self.linha('MNO5P67', secretaria='XXX'), self.linha('PQR6S78')], acao='importar')
        self.assertContains(resposta, 'Nada foi gravado')
        self.assertContains(resposta, 'Secretaria &quot;XXX&quot; não encontrado')
        self.assertFalse(Veiculo.objects.filter(placa__in=['JKL4M56', 'MNO5P67', 'PQR6S78']).exists())

    def test_placa_repetida_no_arquivo_e_placa_ja_cadastrada(self):
        resposta = self.enviar([self.linha('JKL4M56'), self.linha('jkl-4m56'), self.linha('ABC1D23')])
        self.assertContains(resposta, '2 linha(s) com problema')
        self.assertContains(resposta, 'Já existe')

    def test_placa_invalida_e_tipo_de_frota_invalido(self):
        resposta = self.enviar([self.linha('123'), self.linha('JKL4M56', tipo_frota='Alugado')])
        self.assertContains(resposta, 'Placa inválida')
        self.assertContains(resposta, 'não é uma opção válida')

    def test_nao_usa_cadastros_de_outra_prefeitura(self):
        usar_papel_da_aplicacao(self.b.id)
        Secretaria.objects.create(municipio=self.b, sigla='ZZZ', nome='So da B')
        usar_papel_da_aplicacao(self.a.id)
        resposta = self.enviar([self.linha(secretaria='ZZZ')])
        self.assertContains(resposta, 'não encontrado')

    def test_cabecalho_sem_a_placa_e_recusado(self):
        resposta = self.client.post('/importacao/veiculos/', {'arquivo': arquivo(csv([['marca'], ['Fiat']])), 'acao': 'verificar'})
        self.assertContains(resposta, 'Faltam colunas obrigatórias')
        self.assertContains(resposta, 'placa')

    def test_arquivo_ausente(self):
        self.assertContains(self.client.post('/importacao/veiculos/', {'acao': 'verificar'}), 'Escolha o arquivo')

    def test_modelo_csv_tem_o_cabecalho(self):
        resposta = self.client.get('/importacao/veiculos/modelo.csv')
        texto = resposta.content.decode('utf-8-sig')
        self.assertTrue(texto.startswith('placa;prefixo;marca;modelo'))
        self.assertEqual(len(texto.strip().splitlines()), 2)

    def test_so_quem_gere_a_frota_importa(self):
        for usuario in (self.consulta_a, self.gestor_unidade_a, self.fiscal_a):
            self.client.post('/sair/')
            self.entrar_como(usuario, 'a')
            self.assertEqual(self.client.get('/importacao/veiculos/').status_code, 403, usuario.email)
            resposta = self.client.post('/importacao/veiculos/', {'arquivo': arquivo(csv([CABECALHO_VEICULOS, self.linha()])), 'acao': 'importar'})
            self.assertEqual(resposta.status_code, 403, usuario.email)
        self.assertFalse(Veiculo.objects.filter(placa='JKL4M56').exists())


class ImportarMotoristasTest(TelasTest):
    CABECALHO = ['prontuario', 'nome', 'cpf', 'secretaria', 'cnh_categoria', 'cnh_validade']

    def setUp(self):
        super().setUp()
        self.entrar_como(self.gestor_a, 'a')

    def enviar(self, linhas, acao='importar'):
        return self.client.post('/importacao/motoristas/', {'arquivo': arquivo(csv([self.CABECALHO] + linhas)), 'acao': acao})

    def test_importa_motoristas_com_cpf_pontuado_e_data_brasileira(self):
        resposta = self.enviar([['500', 'Ana Souza', '111.444.777-35', 'SMA', 'b', '31/12/2028']])
        self.assertRedirects(resposta, '/motoristas/', fetch_redirect_response=False)
        motorista = Motorista.objects.get(prontuario='500')
        self.assertEqual((motorista.cpf, motorista.cnh_categoria, str(motorista.cnh_validade), motorista.municipio_id),
                         ('11144477735', 'B', '2028-12-31', self.a.id))

    def test_cpf_invalido_e_duplicado_impedem_a_importacao(self):
        resposta = self.enviar([['500', 'Ana', '111.444.777-35', 'SMA', 'B', ''], ['501', 'Bia', '123.456.789-00', 'SMA', 'B', ''],
                                ['502', 'Caio', '529.982.247-25', 'SMA', 'B', '']])
        self.assertContains(resposta, '2 linha(s) com problema')
        self.assertContains(resposta, 'CPF inválido')
        self.assertContains(resposta, 'Já existe')
        self.assertFalse(Motorista.objects.filter(prontuario__in=['500', '501', '502']).exists())

    def test_categoria_de_cnh_invalida(self):
        self.assertContains(self.enviar([['500', 'Ana', '111.444.777-35', 'SMA', 'Z', '']], acao='verificar'), '1 linha(s) com problema')

    def test_so_quem_tem_dados_pessoais_importa_motoristas(self):
        for usuario in (self.consulta_a, self.gestor_unidade_a):
            self.client.post('/sair/')
            self.entrar_como(usuario, 'a')
            self.assertEqual(self.client.get('/importacao/motoristas/').status_code, 403, usuario.email)
        self.assertEqual(self.client.get('/importacao/').status_code, 403)

    def test_pagina_inicial_mostra_so_o_que_o_perfil_pode(self):
        resposta = self.client.get('/importacao/')
        self.assertContains(resposta, '/importacao/veiculos/')
        self.assertContains(resposta, '/importacao/motoristas/')
