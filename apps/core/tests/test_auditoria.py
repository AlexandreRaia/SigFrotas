from apps.core.models import Auditoria, Secretaria
from apps.core.tenant import com_municipio

from .base import DuasPrefeiturasTest, TelasTest


class RegistroTest(DuasPrefeiturasTest):
    def test_inclusao_alteracao_e_exclusao_gravam_antes_e_depois(self):
        with com_municipio(self.a.id):
            secretaria = Secretaria.objects.create(municipio=self.a, sigla='SMS', nome='Saúde')
            secretaria.nome = 'Saúde Pública'
            secretaria.save()
            pk = secretaria.pk
            secretaria.delete()
        registros = list(Auditoria.objects.filter(tabela='secretarias', registro_id=pk).order_by('id'))
        self.assertEqual([r.acao for r in registros], ['I', 'U', 'D'])
        inclusao, alteracao, exclusao = registros
        self.assertIsNone(inclusao.dados_antes)
        self.assertEqual(inclusao.dados_depois['nome'], 'Saúde')
        self.assertEqual(alteracao.dados_antes['nome'], 'Saúde')
        self.assertEqual(alteracao.dados_depois['nome'], 'Saúde Pública')
        self.assertEqual(exclusao.dados_antes['nome'], 'Saúde Pública')
        self.assertIsNone(exclusao.dados_depois)
        self.assertTrue(all(r.municipio_id == self.a.id for r in registros))

    def test_hash_da_senha_nao_vai_para_a_auditoria(self):
        registro = Auditoria.objects.get(tabela='usuarios', registro_id=self.admin_a.pk, acao='I')
        self.assertNotIn('password', registro.dados_depois)
        self.assertNotIn(self.admin_a.password, str(registro.dados_depois))


class TelaDaAuditoriaTest(TelasTest):
    def test_registra_quem_fez_e_mostra_so_a_propria_prefeitura(self):
        self.entrar_como(self.admin_a, 'a')
        self.client.post('/secretarias/novo/', {'sigla': 'SMS', 'nome': 'Saúde'})
        secretaria = Secretaria.objects.get(sigla='SMS')
        registro = Auditoria.objects.get(tabela='secretarias', registro_id=secretaria.pk)
        self.assertEqual(registro.usuario_id, self.admin_a.pk)

        resposta = self.client.get('/auditoria/')
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(all(r.municipio_id == self.a.id for r in resposta.context['object_list']))
        self.assertContains(resposta, 'Admin A')

    def test_filtra_por_tabela(self):
        self.entrar_como(self.admin_a, 'a')
        resposta = self.client.get('/auditoria/?tabela=secretarias')
        self.assertTrue(all(r.tabela == 'secretarias' for r in resposta.context['object_list']))

    def test_login_nao_gera_registro_de_alteracao(self):
        antes = Auditoria.objects.filter(tabela='usuarios', acao='U').count()
        self.entrar_como(self.admin_a, 'a')
        self.assertEqual(Auditoria.objects.filter(tabela='usuarios', acao='U').count(), antes)
