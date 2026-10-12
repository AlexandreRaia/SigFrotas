from django.conf import settings
from django.db import connection
from django.test import TestCase

from apps.core.models import Anexo, CentroCusto, Secretaria, Unidade
from apps.core.services import criar_municipio, criar_usuario
from apps.core.tenant import com_municipio, definir_municipio

SENHA = 'Senha-Forte-123'


def usar_papel_da_aplicacao(municipio_id=None):
    """Passa a conexao do teste para a role da aplicacao (a mesma de producao), onde a RLS vale.

    Os testes rodam com a role dona das tabelas, que ignora a RLS; sem isto o isolamento nao seria testado.
    O efeito some sozinho ao fim do teste (rollback)."""
    with connection.cursor() as cursor:
        cursor.execute('SET ROLE ' + connection.ops.quote_name(settings.DB_APP_USER))
    definir_municipio(municipio_id)


def usar_papel_dono():
    with connection.cursor() as cursor:
        cursor.execute('RESET ROLE')


class DuasPrefeiturasTest(TestCase):
    """Cria as prefeituras A e B, cada uma com usuarios e estrutura."""

    @classmethod
    def setUpTestData(cls):
        cls.a = criar_municipio(nome='Prefeitura A', slug='a', uf='SP', cnpj='11111111000111')
        cls.b = criar_municipio(nome='Prefeitura B', slug='b', uf='SP', cnpj='22222222000122')
        for sufixo, municipio in (('a', cls.a), ('b', cls.b)):
            setattr(cls, f'admin_{sufixo}', criar_usuario(
                municipio=municipio, perfil_codigo='ADMIN', nome=f'Admin {sufixo.upper()}',
                email=f'admin@{sufixo}.test', senha=SENHA))
            setattr(cls, f'solicitante_{sufixo}', criar_usuario(
                municipio=municipio, perfil_codigo='SOLICITANTE', nome=f'Solicitante {sufixo.upper()}',
                email=f'solicitante@{sufixo}.test', senha=SENHA))
            with com_municipio(municipio.id):
                secretaria = Secretaria.objects.create(municipio=municipio, sigla='SMA', nome=f'Administração {sufixo.upper()}')
                setattr(cls, f'sec_{sufixo}', secretaria)
                setattr(cls, f'unidade_{sufixo}', Unidade.objects.create(municipio=municipio, secretaria=secretaria, nome='Transportes'))
                setattr(cls, f'centro_{sufixo}', CentroCusto.objects.create(municipio=municipio, codigo='100', nome='Frota'))
                Anexo.objects.create(municipio=municipio, entidade='secretarias', entidade_id=secretaria.pk,
                                     nome_arquivo='doc.pdf', arquivo=f'{municipio.id}/secretarias/doc.pdf')


class TelasTest(DuasPrefeiturasTest):
    """Testes de tela: o cliente fala com a aplicacao como na producao, com a RLS ativa."""

    def setUp(self):
        super().setUp()
        usar_papel_da_aplicacao()

    def entrar_como(self, usuario, slug):
        resposta = self.client.post('/entrar/', {'prefeitura': slug, 'email': usuario.email, 'senha': SENHA})
        self.assertEqual(resposta.status_code, 302, 'login deveria funcionar')
