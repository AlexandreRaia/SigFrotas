from django.core.exceptions import ValidationError

from apps.core.models import Perfil, Secretaria, Unidade, Usuario
from apps.core.permissoes import PERFIS_PADRAO
from apps.core.tenant import com_municipio

from .base import DuasPrefeiturasTest, usar_papel_da_aplicacao


class MunicipioTest(DuasPrefeiturasTest):
    def test_prefeitura_nasce_com_os_oito_perfis(self):
        self.assertEqual(set(Perfil.objects.filter(municipio=self.a).values_list('codigo', flat=True)), set(PERFIS_PADRAO))
        self.assertEqual(len(PERFIS_PADRAO), 8)

    def test_so_o_admin_gerencia_usuarios_estrutura_e_auditoria(self):
        self.assertTrue(self.admin_a.tem_permissao('usuarios.gerir'))
        self.assertFalse(self.solicitante_a.tem_permissao('usuarios.gerir'))
        self.assertFalse(self.solicitante_a.tem_permissao('estrutura.gerir'))


class VinculoEntrePrefeiturasTest(DuasPrefeiturasTest):
    """FK do banco nao garante a mesma prefeitura: os servicos precisam recusar."""

    def test_unidade_da_a_nao_aponta_para_secretaria_da_b(self):
        with self.assertRaises(ValidationError):
            Unidade.objects.create(municipio=self.a, secretaria=self.sec_b, nome='Intrusa')

    def test_usuario_da_a_nao_recebe_perfil_da_b(self):
        with self.assertRaises(ValidationError):
            Usuario.objects.create_user(self.a, 'novo@a.test', 'Novo', self.admin_b.perfil, 'Senha-Forte-123')

    def test_recusa_tambem_com_a_rls_ativa(self):
        usar_papel_da_aplicacao(self.a.id)
        with self.assertRaises(ValidationError):
            Unidade.objects.create(municipio=self.a, secretaria=self.sec_b, nome='Intrusa')

    def test_vinculo_dentro_da_mesma_prefeitura_funciona(self):
        with com_municipio(self.a.id):
            unidade = Unidade.objects.create(municipio=self.a, secretaria=self.sec_a, nome='Garagem')
        self.assertEqual(unidade.secretaria, self.sec_a)
