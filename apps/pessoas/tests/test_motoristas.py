import shutil
import tempfile
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from apps.core.models import Anexo, Auditoria
from apps.core.tests.base import DuasPrefeiturasTest, TelasTest, usar_papel_da_aplicacao
from apps.pessoas.models import Motorista

CPF_VALIDO_2 = '111.444.777-35'


class RegrasDoMotoristaTest(DuasPrefeiturasTest):
    def test_status_da_cnh(self):
        hoje = timezone.localdate()
        for validade, esperado in ((None, 'Sem CNH'), (hoje - timedelta(days=1), 'Vencida'),
                                   (hoje + timedelta(days=10), 'Vence em 10 dias'), (hoje + timedelta(days=90), 'Em dia')):
            self.motorista_a.cnh_validade = validade
            self.assertEqual(self.motorista_a.cnh_status, esperado)

    def test_mesmo_cpf_e_prontuario_valem_em_prefeituras_diferentes(self):
        self.assertEqual((self.motorista_a.cpf, self.motorista_a.prontuario), (self.motorista_b.cpf, self.motorista_b.prontuario))


class MotoristasTelasTest(TelasTest):
    def dados(self, **extras):
        return {'prontuario': '200', 'nome': 'Fulano de Tal', 'cpf': CPF_VALIDO_2, 'secretaria': self.sec_a.pk,
                'situacao': 'ATIVO', 'cnh_categoria': 'D', 'cnh_validade': '2030-06-01', 'cep': '06501-001', **extras}

    def test_gestor_cadastra_e_o_cpf_vai_so_com_numeros(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/motoristas/novo/', self.dados())
        motorista = Motorista.objects.get(prontuario='200')
        self.assertRedirects(resposta, f'/motoristas/{motorista.pk}/', fetch_redirect_response=False)
        self.assertEqual((motorista.cpf, motorista.cep), ('11144477735', '06501001'))

    def test_cpf_invalido_prontuario_e_cpf_repetidos_sao_recusados(self):
        self.entrar_como(self.gestor_a, 'a')
        self.assertContains(self.client.post('/motoristas/novo/', self.dados(cpf='111.444.777-36')), 'CPF inválido')
        self.assertContains(self.client.post('/motoristas/novo/', self.dados(prontuario='100')), 'Já existe')
        self.assertContains(self.client.post('/motoristas/novo/', self.dados(cpf='529.982.247-25')), 'Já existe')
        self.assertFalse(Motorista.objects.filter(prontuario='200').exists())

    def test_nao_cadastra_com_secretaria_de_outra_prefeitura(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/motoristas/novo/', self.dados(secretaria=self.sec_b.pk))
        self.assertFalse(Motorista.objects.filter(prontuario='200').exists())

    def test_so_quem_tem_dados_pessoais_cadastra(self):
        for usuario in (self.consulta_a, self.gestor_unidade_a, self.fiscal_a):
            self.client.post('/sair/')
            self.entrar_como(usuario, 'a')
            self.assertEqual(self.client.post('/motoristas/novo/', self.dados()).status_code, 403, usuario.email)
        self.assertFalse(Motorista.objects.filter(prontuario='200').exists())

    # --- LGPD ---
    def test_lista_nao_mostra_cpf_nem_numero_da_cnh(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.get('/motoristas/')
        self.assertContains(resposta, self.motorista_a.nome)
        self.assertNotContains(resposta, '52998224725')
        self.assertNotContains(resposta, '12345678900')

    def test_ficha_completa_mostra_cpf_e_grava_a_consulta_na_auditoria(self):
        self.entrar_como(self.gestor_a, 'a')
        antes = Auditoria.objects.filter(acao='C').count()
        resposta = self.client.get(f'/motoristas/{self.motorista_a.pk}/')
        self.assertContains(resposta, '529.982.247-25')  # a ficha mostra o CPF com pontuacao
        consulta =Auditoria.objects.filter(acao='C').latest('id')
        self.assertEqual(Auditoria.objects.filter(acao='C').count(), antes + 1)
        self.assertEqual((consulta.usuario_id, consulta.tabela, consulta.registro_id, consulta.municipio_id),
                         (self.gestor_a.pk, 'motoristas', self.motorista_a.pk, self.a.id))

    def test_quem_so_ve_nao_enxerga_dado_pessoal_e_nao_gera_consulta(self):
        self.entrar_como(self.consulta_a, 'a')
        antes = Auditoria.objects.filter(acao='C').count()
        resposta = self.client.get(f'/motoristas/{self.motorista_a.pk}/')
        self.assertEqual(resposta.status_code, 200)
        for texto in ('52998224725', '529.982.247-25', '12345678900', 'Dados pessoais', 'Penalidades'):
            self.assertNotContains(resposta, texto)
        self.assertContains(resposta, self.motorista_a.nome)     # dados funcionais continuam visiveis
        self.assertEqual(Auditoria.objects.filter(acao='C').count(), antes)

    def test_gestor_de_unidade_ve_so_motoristas_da_propria_secretaria(self):
        usar_papel_da_aplicacao(self.a.id)
        outro = Motorista.objects.create(municipio=self.a, prontuario='300', nome='Motorista da Educação', cpf='11144477735', secretaria=self.sec2_a)
        self.entrar_como(self.gestor_unidade_a, 'a')
        self.assertContains(self.client.get('/motoristas/'), self.motorista_a.nome)
        self.assertNotContains(self.client.get('/motoristas/'), outro.nome)
        self.assertEqual(self.client.get(f'/motoristas/{outro.pk}/').status_code, 404)

    def test_fiscal_e_solicitante_nao_acessam_motoristas(self):
        for usuario in (self.fiscal_a, self.solicitante_a):
            self.client.post('/sair/')
            self.entrar_como(usuario, 'a')
            self.assertEqual(self.client.get('/motoristas/').status_code, 403, usuario.email)

    def test_outra_prefeitura_nao_ve_o_motorista(self):
        self.entrar_como(self.admin_a, 'a')
        self.assertEqual(self.client.get(f'/motoristas/{self.motorista_b.pk}/').status_code, 404)
        self.assertNotContains(self.client.get('/motoristas/'), self.motorista_b.nome)

    # --- itens da ficha ---
    def test_certificado_afastamento_e_penalidade(self):
        self.entrar_como(self.gestor_a, 'a')
        base = f'/motoristas/{self.motorista_a.pk}'
        self.client.post(f'{base}/certificados/novo/', {'curso': 'Direção defensiva', 'validade': '2027-01-01'})
        self.client.post(f'{base}/afastamentos/novo/', {'tipo': 'FERIAS', 'inicio': '2026-07-01', 'fim': '2026-07-30'})
        self.client.post(f'{base}/penalidades/nova/', {'descricao': 'Atraso reincidente', 'penalidade': 'Advertência'})
        resposta = self.client.get(f'{base}/')
        for texto in ('Direção defensiva', 'Férias', 'Atraso reincidente'):
            self.assertContains(resposta, texto)
        certificado = self.motorista_a.certificados.get()
        self.client.post(f'{base}/certificados/{certificado.pk}/excluir/')
        self.assertEqual(self.motorista_a.certificados.count(), 0)

    def test_afastamento_com_fim_antes_do_inicio_e_recusado(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/motoristas/{self.motorista_a.pk}/afastamentos/novo/', {'tipo': 'FOLGA', 'inicio': '2026-07-10', 'fim': '2026-07-01'})
        self.assertEqual(self.motorista_a.afastamentos.count(), 0)

    def test_nao_ha_como_apagar_penalidade(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/motoristas/{self.motorista_a.pk}/penalidades/nova/', {'descricao': 'X'})
        penalidade = self.motorista_a.penalidades.get()
        self.assertEqual(self.client.post(f'/motoristas/{self.motorista_a.pk}/penalidades/{penalidade.pk}/excluir/').status_code, 404)
        self.assertEqual(self.motorista_a.penalidades.count(), 1)

    def test_anexo_do_motorista_exige_dados_pessoais_e_grava_a_consulta(self):
        pasta = tempfile.mkdtemp(prefix='sigfrotas_teste_')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=pasta):
            self.entrar_como(self.gestor_a, 'a')
            self.client.post(f'/motoristas/{self.motorista_a.pk}/anexos/novo/', {
                'categoria': 'CNH', 'arquivo': SimpleUploadedFile('cnh.pdf', b'%PDF-1.4 cnh', content_type='application/pdf')})
            anexo = Anexo.objects.get(entidade='motoristas', entidade_id=self.motorista_a.pk)
            antes = Auditoria.objects.filter(acao='C').count()
            self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 200)
            self.assertEqual(Auditoria.objects.filter(acao='C').count(), antes + 1)
            self.client.post('/sair/')
            self.entrar_como(self.consulta_a, 'a')
            self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 403)
