from apps.core.models import CentroCusto, Secretaria, Unidade, Usuario

from .base import SENHA, TelasTest, usar_papel_da_aplicacao


class LoginTest(TelasTest):
    def test_login_correto_entra_e_guarda_a_prefeitura_na_sessao(self):
        resposta = self.client.post('/entrar/', {'prefeitura': 'a', 'email': 'admin@a.test', 'senha': SENHA})
        self.assertRedirects(resposta, '/', fetch_redirect_response=False)
        self.assertEqual(self.client.session['municipio_id'], self.a.id)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_email_de_uma_prefeitura_nao_entra_em_outra(self):
        resposta = self.client.post('/entrar/', {'prefeitura': 'b', 'email': 'admin@a.test', 'senha': SENHA})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_senha_errada_e_prefeitura_inexistente(self):
        for dados in ({'prefeitura': 'a', 'email': 'admin@a.test', 'senha': 'errada'},
                      {'prefeitura': 'nao-existe', 'email': 'admin@a.test', 'senha': SENHA}):
            resposta = self.client.post('/entrar/', dados)
            self.assertContains(resposta, 'incorretos')
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_usuario_inativo_nao_entra(self):
        usar_papel_da_aplicacao(self.a.id)  # sem prefeitura definida a RLS esconde o usuario e o update nao acharia nada
        self.assertEqual(Usuario.objects.filter(pk=self.admin_a.pk).update(ativo=False), 1)
        resposta = self.client.post('/entrar/', {'prefeitura': 'a', 'email': 'admin@a.test', 'senha': SENHA})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_email_nao_diferencia_maiusculas(self):
        resposta = self.client.post('/entrar/', {'prefeitura': 'a', 'email': 'ADMIN@A.TEST', 'senha': SENHA})
        self.assertEqual(resposta.status_code, 302)

    def test_nao_redireciona_para_site_externo(self):
        resposta = self.client.post('/entrar/?next=https://externo.example/', {'prefeitura': 'a', 'email': 'admin@a.test', 'senha': SENHA})
        self.assertRedirects(resposta, '/', fetch_redirect_response=False)

    def test_sair_exige_post_e_encerra_a_sessao(self):
        self.entrar_como(self.admin_a, 'a')
        self.assertEqual(self.client.get('/sair/').status_code, 405)
        self.client.post('/sair/')
        self.assertRedirects(self.client.get('/secretarias/'), '/entrar/?next=/secretarias/', fetch_redirect_response=False)


class PermissaoTest(TelasTest):
    PAGINAS = ['/secretarias/', '/unidades/', '/centros_custo/', '/usuarios/', '/auditoria/']

    def test_anonimo_vai_para_o_login(self):
        for pagina in self.PAGINAS:
            self.assertEqual(self.client.get(pagina).status_code, 302, pagina)

    def test_perfil_sem_permissao_recebe_403(self):
        self.entrar_como(self.solicitante_a, 'a')
        for pagina in self.PAGINAS:
            self.assertEqual(self.client.get(pagina).status_code, 403, pagina)

    def test_admin_acessa(self):
        self.entrar_como(self.admin_a, 'a')
        for pagina in self.PAGINAS:
            self.assertEqual(self.client.get(pagina).status_code, 200, pagina)


class CadastrosTest(TelasTest):
    def setUp(self):
        super().setUp()
        self.entrar_como(self.admin_a, 'a')

    def test_lista_mostra_so_a_propria_prefeitura(self):
        resposta = self.client.get('/secretarias/')
        self.assertContains(resposta, 'Administração A')
        self.assertNotContains(resposta, 'Administração B')

    def test_cria_secretaria_na_prefeitura_do_usuario(self):
        self.client.post('/secretarias/novo/', {'sigla': 'SMS', 'nome': 'Saúde'})
        self.assertEqual(Secretaria.objects.get(sigla='SMS', nome='Saúde').municipio_id, self.a.id)

    def test_nao_aceita_municipio_vindo_do_formulario(self):
        self.client.post('/secretarias/novo/', {'sigla': 'SMS', 'nome': 'Saúde', 'municipio': self.b.id})
        self.assertEqual(Secretaria.objects.get(sigla='SMS').municipio_id, self.a.id)

    def test_sigla_repetida_e_recusada_com_mensagem(self):
        resposta = self.client.post('/secretarias/novo/', {'sigla': 'SMA', 'nome': 'Outra'})
        self.assertContains(resposta, 'Já existe')
        self.assertEqual(Secretaria.objects.filter(municipio=self.a, sigla='SMA').count(), 1)

    def test_mesma_sigla_pode_existir_em_outra_prefeitura(self):
        self.assertEqual(self.sec_b.sigla, 'SMA')  # B ja tem SMA e A tambem: nao conflita

    def test_unidade_nao_aceita_secretaria_de_outra_prefeitura(self):
        resposta = self.client.post('/unidades/novo/', {'secretaria': self.sec_b.id, 'nome': 'Intrusa'})
        self.assertEqual(resposta.status_code, 200)  # formulario volta com erro
        self.assertFalse(Unidade.objects.filter(nome='Intrusa').exists())

    def test_cria_centro_de_custo(self):
        self.client.post('/centros_custo/novo/', {'codigo': '200', 'nome': 'Saúde', 'secretaria': self.sec_a.id})
        self.assertTrue(CentroCusto.objects.filter(municipio=self.a, codigo='200').exists())

    def test_nao_edita_nem_inativa_registro_de_outra_prefeitura(self):
        self.assertEqual(self.client.get(f'/secretarias/{self.sec_b.pk}/editar/').status_code, 404)
        self.assertEqual(self.client.post(f'/secretarias/{self.sec_b.pk}/editar/', {'sigla': 'X', 'nome': 'X'}).status_code, 404)
        self.assertEqual(self.client.post(f'/secretarias/{self.sec_b.pk}/alternar/').status_code, 404)
        usar_papel_da_aplicacao(self.b.id)  # confere como a propria prefeitura B
        self.sec_b.refresh_from_db()
        self.assertTrue(self.sec_b.ativo)
        self.assertEqual(self.sec_b.sigla, 'SMA')

    def test_inativa_e_reativa_sem_apagar(self):
        self.client.post(f'/secretarias/{self.sec_a.pk}/alternar/')
        self.sec_a.refresh_from_db()
        self.assertFalse(self.sec_a.ativo)
        self.client.post(f'/secretarias/{self.sec_a.pk}/alternar/')
        self.sec_a.refresh_from_db()
        self.assertTrue(self.sec_a.ativo)


class UsuariosTest(TelasTest):
    def setUp(self):
        super().setUp()
        self.entrar_como(self.admin_a, 'a')

    def dados(self, **extras):
        perfil = self.solicitante_a.perfil
        return {'nome': 'Novo', 'email': 'novo@a.test', 'perfil': perfil.id, 'senha': 'Outra-Senha-456', **extras}

    def test_cria_usuario_que_consegue_entrar(self):
        self.client.post('/usuarios/novo/', self.dados())
        self.client.post('/sair/')
        resposta = self.client.post('/entrar/', {'prefeitura': 'a', 'email': 'novo@a.test', 'senha': 'Outra-Senha-456'})
        self.assertEqual(resposta.status_code, 302)

    def test_nao_cria_usuario_com_perfil_de_outra_prefeitura(self):
        resposta = self.client.post('/usuarios/novo/', self.dados(perfil=self.admin_b.perfil.id))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email='novo@a.test').exists())

    def test_senha_fraca_e_recusada(self):
        resposta = self.client.post('/usuarios/novo/', self.dados(senha='123'))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email='novo@a.test').exists())

    def test_email_repetido_e_recusado(self):
        resposta = self.client.post('/usuarios/novo/', self.dados(email='SOLICITANTE@a.test'))
        self.assertContains(resposta, 'Já existe')

    def test_redefine_senha(self):
        self.client.post(f'/usuarios/{self.solicitante_a.pk}/senha/', {'senha': 'Senha-Nova-789'})
        self.client.post('/sair/')
        resposta = self.client.post('/entrar/', {'prefeitura': 'a', 'email': 'solicitante@a.test', 'senha': 'Senha-Nova-789'})
        self.assertEqual(resposta.status_code, 302)

    def test_nao_redefine_senha_de_usuario_de_outra_prefeitura(self):
        self.assertEqual(self.client.post(f'/usuarios/{self.admin_b.pk}/senha/', {'senha': 'Senha-Nova-789'}).status_code, 404)

    def test_nao_inativa_o_proprio_usuario(self):
        self.client.post(f'/usuarios/{self.admin_a.pk}/alternar/')
        self.admin_a.refresh_from_db()
        self.assertTrue(self.admin_a.ativo)

    def test_perfil_solicitante_nao_cria_usuario(self):
        self.client.post('/sair/')
        self.entrar_como(self.solicitante_a, 'a')
        self.assertEqual(self.client.post('/usuarios/novo/', self.dados()).status_code, 403)
        self.assertFalse(Usuario.objects.filter(email='novo@a.test').exists())
