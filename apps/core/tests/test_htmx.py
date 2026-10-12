import json

from apps.core.models import Secretaria

from .base import TelasTest

HX = {'HTTP_HX_REQUEST': 'true'}


class TrechosHtmxTest(TelasTest):
    def setUp(self):
        super().setUp()
        self.entrar_como(self.admin_a, 'a')

    def test_lista_normal_vem_inteira_e_htmx_vem_so_o_trecho(self):
        inteira = self.client.get('/secretarias/')
        self.assertContains(inteira, '<html')
        trecho = self.client.get('/secretarias/', **HX)
        self.assertNotContains(trecho, '<html')
        self.assertContains(trecho, 'Administração A')
        self.assertNotContains(trecho, 'Administração B')

    def test_voltar_no_historico_pede_a_pagina_inteira(self):
        resposta = self.client.get('/secretarias/', **HX, HTTP_HX_HISTORY_RESTORE_REQUEST='true')
        self.assertContains(resposta, '<html')

    def test_resposta_avisa_o_cache_que_varia_por_htmx(self):
        self.assertIn('HX-Request', self.client.get('/secretarias/', **HX)['Vary'])

    def test_auditoria_filtra_sem_recarregar(self):
        resposta = self.client.get('/auditoria/?tabela=secretarias', **HX)
        self.assertNotContains(resposta, '<html')
        self.assertTrue(all(r.tabela == 'secretarias' for r in resposta.context['object_list']))

    def test_sessao_expirada_em_requisicao_htmx_manda_para_o_login(self):
        self.client.post('/sair/')
        resposta = self.client.get('/secretarias/', **HX)
        self.assertEqual(resposta.status_code, 204)
        self.assertTrue(resposta['HX-Redirect'].startswith('/entrar/'))


class InativarHtmxTest(TelasTest):
    def setUp(self):
        super().setUp()
        self.entrar_como(self.admin_a, 'a')

    def test_inativa_trocando_so_a_linha_e_avisando(self):
        resposta = self.client.post(f'/secretarias/{self.sec_a.pk}/alternar/', **HX)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, '<html')
        self.assertContains(resposta, f'id="linha-{self.sec_a.pk}"')
        self.assertContains(resposta, 'Inativo')
        aviso = json.loads(resposta['HX-Trigger'])['mensagem']
        self.assertEqual(aviso['tipo'], 'success')
        self.sec_a.refresh_from_db()
        self.assertFalse(self.sec_a.ativo)

    def test_aviso_nao_fica_pendurado_para_a_proxima_pagina(self):
        self.client.post(f'/secretarias/{self.sec_a.pk}/alternar/', **HX)
        self.assertNotContains(self.client.get('/secretarias/'), 'Cadastro inativado')

    def test_nao_inativa_o_proprio_usuario(self):
        resposta = self.client.post(f'/usuarios/{self.admin_a.pk}/alternar/', **HX)
        self.assertEqual(json.loads(resposta['HX-Trigger'])['mensagem']['tipo'], 'error')
        self.admin_a.refresh_from_db()
        self.assertTrue(self.admin_a.ativo)

    def test_outra_prefeitura_continua_dando_404(self):
        self.assertEqual(self.client.post(f'/secretarias/{self.sec_b.pk}/alternar/', **HX).status_code, 404)


class FormularioHtmxTest(TelasTest):
    def setUp(self):
        super().setUp()
        self.entrar_como(self.admin_a, 'a')

    def test_erro_de_validacao_devolve_so_o_formulario(self):
        resposta = self.client.post('/secretarias/novo/', {'sigla': 'SMA', 'nome': 'Repetida'}, **HX)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, '<html')
        self.assertContains(resposta, 'Já existe')

    def test_salvar_redireciona_para_a_lista(self):
        resposta = self.client.post('/secretarias/novo/', {'sigla': 'SMS', 'nome': 'Saúde'}, **HX)
        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(resposta['HX-Redirect'], '/secretarias/')
        self.assertTrue(Secretaria.objects.filter(sigla='SMS').exists())
        self.assertContains(self.client.get('/secretarias/'), 'Salvo com sucesso')

    def test_redefinir_senha_por_htmx(self):
        resposta = self.client.post(f'/usuarios/{self.solicitante_a.pk}/senha/', {'senha': '123'}, **HX)
        self.assertNotContains(resposta, '<html')
        resposta = self.client.post(f'/usuarios/{self.solicitante_a.pk}/senha/', {'senha': 'Senha-Nova-789'}, **HX)
        self.assertEqual(resposta['HX-Redirect'], '/usuarios/')
