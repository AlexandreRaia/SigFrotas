"""Isolamento entre prefeituras: a prefeitura A nao enxerga nem grava dados da B."""
from django.conf import settings
from django.db import DatabaseError, connection, transaction

from apps.core.models import Anexo, Auditoria, CentroCusto, Perfil, Secretaria, Unidade, Usuario

from .base import DuasPrefeiturasTest, usar_papel_da_aplicacao

MODELOS = [Secretaria, Unidade, CentroCusto, Perfil, Usuario, Anexo, Auditoria]


def consulta(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


class PapelDaAplicacaoTest(DuasPrefeiturasTest):
    def test_papel_sem_superusuario_e_sem_bypassrls(self):
        linha = consulta('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s', [settings.DB_APP_USER])
        self.assertEqual(linha, [(False, False)])

    def test_papel_nao_e_dono_das_tabelas(self):
        donas = consulta("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = %s",
                         [settings.DB_APP_USER])
        self.assertEqual(donas, [])

    def test_toda_tabela_com_municipio_id_tem_rls_e_politica(self):
        # so tabelas: as views usam security_invoker e herdam a RLS das tabelas que consultam
        tabelas = [t for (t,) in consulta(
            """SELECT c.table_name FROM information_schema.columns c
               JOIN information_schema.tables t USING (table_schema, table_name)
               WHERE c.table_schema = 'public' AND c.column_name = 'municipio_id' AND t.table_type = 'BASE TABLE'""")]
        self.assertTrue(tabelas)
        for tabela in tabelas:
            ligada = consulta('SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass', [tabela])[0][0]
            politicas = consulta('SELECT count(*) FROM pg_policies WHERE tablename = %s', [tabela])[0][0]
            self.assertTrue(ligada, f'{tabela} sem RLS')
            self.assertGreaterEqual(politicas, 1, f'{tabela} sem politica')


class IsolamentoTest(DuasPrefeiturasTest):
    def test_a_nao_le_dados_da_b(self):
        usar_papel_da_aplicacao(self.a.id)
        for modelo in MODELOS:
            self.assertGreater(modelo.objects.filter(municipio_id=self.a.id).count(), 0, modelo.__name__)
            self.assertEqual(modelo.objects.exclude(municipio_id=self.a.id).count(), 0, f'{modelo.__name__} vazou dados da B')

    def test_a_nao_le_dados_da_b_nem_buscando_pelo_id(self):
        usar_papel_da_aplicacao(self.a.id)
        self.assertFalse(Secretaria.objects.filter(pk=self.sec_b.pk).exists())
        self.assertFalse(Usuario.objects.filter(pk=self.admin_b.pk).exists())

    def test_sem_prefeitura_definida_nada_e_visivel(self):
        usar_papel_da_aplicacao(None)
        for modelo in MODELOS:
            self.assertEqual(modelo.objects.count(), 0, modelo.__name__)

    def test_a_nao_grava_na_b(self):
        usar_papel_da_aplicacao(self.a.id)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Secretaria.objects.create(municipio=self.b, sigla='X', nome='invasora')
        perfil_a = Perfil.objects.get(municipio=self.a, codigo='ADMIN')
        with self.assertRaises(DatabaseError), transaction.atomic():  # bulk_create nao passa pela validacao do servico
            Usuario.objects.bulk_create([Usuario(municipio=self.b, perfil=perfil_a, nome='Invasor', email='x@b.test', password='x')])

    def test_a_nao_altera_nem_apaga_dados_da_b(self):
        usar_papel_da_aplicacao(self.a.id)
        self.assertEqual(Secretaria.objects.filter(pk=self.sec_b.pk).update(nome='alterada'), 0)
        self.assertEqual(Secretaria.objects.filter(pk=self.sec_b.pk).delete()[0], 0)
        usar_papel_da_aplicacao(self.b.id)
        self.sec_b.refresh_from_db()
        self.assertEqual(self.sec_b.nome, 'Administração B')

    def test_a_nao_passa_um_registro_seu_para_a_b(self):
        usar_papel_da_aplicacao(self.a.id)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Secretaria.objects.filter(pk=self.sec_a.pk).update(municipio_id=self.b.id)

    def test_auditoria_so_aceita_inclusao(self):
        usar_papel_da_aplicacao(self.a.id)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Auditoria.objects.filter(municipio_id=self.a.id).update(tabela='adulterada')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Auditoria.objects.filter(municipio_id=self.a.id).delete()
