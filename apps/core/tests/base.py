from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import connection
from django.test import TestCase

from apps.core.models import Anexo, CentroCusto, Secretaria, Unidade
from apps.core.services import criar_municipio, criar_usuario
from apps.core.tenant import com_municipio, definir_municipio
from apps.financeiro.models import Contrato, FiscalContrato, Fornecedor
from apps.financeiro.services import criar_empenho
from apps.frota.models import CategoriaVeiculo, Veiculo
from apps.pessoas.models import Motorista

SENHA = 'Senha-Forte-123'
HOJE = date.today()   # datas dos empenhos sao relativas a hoje: os testes nao envelhecem


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
    """Cria as prefeituras A e B. Cada uma tem: secretarias SMA e SME, unidade, centros de custo 100 (SMA) e 200 (SME),
    usuarios de cada perfil (e gestor2, motorista_usuario e oficina), fornecedor, contrato, fiscal, dois empenhos, dois veiculos e um motorista.

    Atributos: <coisa>_a e <coisa>_b. Usuarios: admin, gestor, gestor_unidade (da SMA), fiscal (do centro 100),
    consulta e solicitante. Os dois veiculos tem placa igual nas duas prefeituras (a placa so e unica por prefeitura).
    """

    @classmethod
    def setUpTestData(cls):
        cls.a = criar_municipio(nome='Prefeitura A', slug='a', uf='SP', cnpj='11111111000111')
        cls.b = criar_municipio(nome='Prefeitura B', slug='b', uf='SP', cnpj='22222222000122')
        for sufixo, municipio in (('a', cls.a), ('b', cls.b)):
            with com_municipio(municipio.id):
                secretaria = Secretaria.objects.create(municipio=municipio, sigla='SMA', nome=f'Administração {sufixo.upper()}')
                outra = Secretaria.objects.create(municipio=municipio, sigla='SME', nome=f'Educação {sufixo.upper()}')
                unidade = Unidade.objects.create(municipio=municipio, secretaria=secretaria, nome='Transportes')
                centro = CentroCusto.objects.create(municipio=municipio, codigo='100', nome='Frota', secretaria=secretaria)
                centro2 = CentroCusto.objects.create(municipio=municipio, codigo='200', nome='Educação', secretaria=outra)
            for nome_attr, valor in (('sec', secretaria), ('sec2', outra), ('unidade', unidade), ('centro', centro),
                                     ('centro2', centro2)):
                setattr(cls, f'{nome_attr}_{sufixo}', valor)

            usuarios = [('admin', 'ADMIN', 'Admin', {}), ('solicitante', 'SOLICITANTE', 'Solicitante', {}),
                        ('gestor', 'GESTOR_FROTA', 'Gestor', {}), ('fiscal', 'FISCAL', 'Fiscal', {}),
                        ('consulta', 'CONSULTA', 'Consulta', {}),
                        ('gestor_unidade', 'GESTOR_UNIDADE', 'Gestor de unidade', {'secretaria': secretaria})]
            for chave, perfil, nome, extras in usuarios:
                setattr(cls, f'{chave}_{sufixo}', criar_usuario(
                    municipio=municipio, perfil_codigo=perfil, nome=f'{nome} {sufixo.upper()}',
                    email=f'{chave}@{sufixo}.test', senha=SENHA, **extras))

            with com_municipio(municipio.id):
                Anexo.objects.create(municipio=municipio, entidade='secretarias', entidade_id=secretaria.pk,
                                     nome_arquivo='doc.pdf', arquivo=f'{municipio.id}/secretarias/doc.pdf')
                fornecedor = Fornecedor.objects.create(municipio=municipio, cnpj_cpf='11222333000181',
                                                       razao_social=f'Oficina {sufixo.upper()}', tipo='OFICINA')
                contrato = Contrato.objects.create(
                    municipio=municipio, fornecedor=fornecedor, tipo='MANUTENCAO', numero='C-1', objeto='Manutenção da frota',
                    vigencia_ini=date(2026, 1, 1), vigencia_fim=date(2026, 12, 31))
                FiscalContrato.objects.create(municipio=municipio, contrato=contrato, centro_custo=centro,
                                              usuario=getattr(cls, f'fiscal_{sufixo}'))
                dados = dict(municipio=municipio, finalidade='MANUTENCAO', exercicio=2026, vigencia_ini=HOJE - timedelta(days=90),
                             vigencia_fim=HOJE + timedelta(days=270), valor_empenhado=Decimal('1000.00'), liberar_total=True)
                empenho = criar_empenho(numero='1', centro_custo=centro, contrato=contrato, **dados)
                empenho2 = criar_empenho(numero='2', centro_custo=centro2, **dados)
                categoria = CategoriaVeiculo.objects.create(municipio=municipio, nome='Automóvel', cnh_minima='B')
                veiculo = Veiculo.objects.create(municipio=municipio, placa='ABC1D23', categoria=categoria,
                                                 secretaria=secretaria, centro_custo=centro, odometro_atual=1000)
                veiculo2 = Veiculo.objects.create(municipio=municipio, placa='XYZ9A87', categoria=categoria,
                                                  secretaria=outra, centro_custo=centro2)
                motorista = Motorista.objects.create(
                    municipio=municipio, prontuario='100', nome=f'Motorista {sufixo.upper()}', cpf='52998224725',
                    secretaria=secretaria, cnh_categoria='B', cnh_numero='12345678900', cnh_validade=date(2030, 1, 1))
            for chave, perfil, nome, extras in [('gestor2', 'GESTOR_FROTA', 'Gestor 2', {}), ('motorista_usuario', 'MOTORISTA', 'Motorista', {}),
                                                ('oficina', 'OFICINA', 'Oficina', {'fornecedor': fornecedor})]:
                setattr(cls, f'{chave}_{sufixo}', criar_usuario(
                    municipio=municipio, perfil_codigo=perfil, nome=f'{nome} {sufixo.upper()}', email=f'{chave}@{sufixo}.test',
                    senha=SENHA, **extras))
            for nome_attr, valor in (('fornecedor', fornecedor), ('contrato', contrato), ('empenho', empenho),
                                     ('empenho2', empenho2), ('categoria', categoria), ('veiculo', veiculo),
                                     ('veiculo2', veiculo2), ('motorista', motorista)):
                setattr(cls, f'{nome_attr}_{sufixo}', valor)


class TelasTest(DuasPrefeiturasTest):
    """Testes de tela: o cliente fala com a aplicacao como na producao, com a RLS ativa."""

    def setUp(self):
        super().setUp()
        usar_papel_da_aplicacao()

    def entrar_como(self, usuario, slug):
        resposta = self.client.post('/entrar/', {'prefeitura': slug, 'email': usuario.email, 'senha': SENHA})
        self.assertEqual(resposta.status_code, 302, 'login deveria funcionar')
