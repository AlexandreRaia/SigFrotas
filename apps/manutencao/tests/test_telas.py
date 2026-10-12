import shutil
import tempfile
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core.models import Notificacao
from apps.core.tests.base import SENHA, TelasTest, usar_papel_da_aplicacao
from apps.financeiro.models import Fornecedor
from apps.financeiro.services import saldo_do_empenho
from apps.manutencao import services
from apps.manutencao.models import Chamado, Orcamento, Smv

D = Decimal
HX = {'HTTP_HX_REQUEST': 'true'}


class BaseTelas(TelasTest):
    def smv(self, veiculo=None, fornecedor=None):
        usar_papel_da_aplicacao(self.a.id)
        return services.abrir_smv(usuario=self.gestor_a, veiculo=veiculo or self.veiculo_a, tipo='CORRETIVA',
                                  fornecedor=fornecedor or self.fornecedor_a, entrada_km=1200)

    def chamado(self, usuario=None, veiculo=None):
        usar_papel_da_aplicacao(self.a.id)
        return services.abrir_chamado(veiculo=veiculo or self.veiculo_a, usuario=usuario or self.motorista_usuario_a, descricao='Freio fazendo barulho')

    def trocar_para(self, usuario, slug='a'):
        self.client.post('/sair/')
        self.entrar_como(usuario, slug)

    def orcamento_enviado(self, smv=None):
        smv = smv or self.smv()
        services.registrar_diagnostico(smv, self.oficina_a, 'Pastilhas gastas')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        services.adicionar_item(orcamento, tipo='PECA', descricao='Pastilha', quantidade=D('2'), valor_unitario=D('100'))
        services.adicionar_item(orcamento, tipo='SERVICO', descricao='Mão de obra', quantidade=D('1'), valor_unitario=D('300'))
        services.enviar_orcamento(Orcamento.objects.get(pk=orcamento.pk), self.oficina_a)
        return smv, Orcamento.objects.get(pk=orcamento.pk)


class ChamadosTelasTest(BaseTelas):
    def test_motorista_abre_chamado_e_o_fiscal_e_avisado(self):
        self.entrar_como(self.motorista_usuario_a, 'a')
        resposta = self.client.post('/chamados/novo/', {'veiculo': self.veiculo_a.pk, 'prioridade': 'ALTA', 'descricao': 'Luz do freio acesa'})
        chamado = Chamado.objects.get(descricao='Luz do freio acesa')
        self.assertRedirects(resposta, f'/chamados/{chamado.pk}/', fetch_redirect_response=False)
        self.assertEqual((chamado.aberto_por, chamado.fiscal), (self.motorista_usuario_a, self.fiscal_a))
        self.assertContains(self.client.get(f'/chamados/{chamado.pk}/'), 'Luz do freio acesa')

    def test_motorista_so_ve_os_proprios_chamados(self):
        proprio = self.chamado(self.motorista_usuario_a)
        alheio = self.chamado(self.gestor_a)
        self.entrar_como(self.motorista_usuario_a, 'a')
        lista = self.client.get('/chamados/')
        self.assertContains(lista, f'/chamados/{proprio.pk}/')
        self.assertNotContains(lista, f'/chamados/{alheio.pk}/')
        self.assertEqual(self.client.get(f'/chamados/{alheio.pk}/').status_code, 404)
        self.assertEqual(self.client.get('/smv/').status_code, 200)       # tem acesso, mas nao ve nenhuma SMV
        self.assertNotContains(self.client.get('/smv/'), '/smv/novo/')

    def test_fiscal_ve_os_chamados_dos_seus_centros(self):
        do_centro = self.chamado(self.gestor_a, self.veiculo_a)         # centro 100: dele
        de_outro = self.chamado(self.gestor_a, self.veiculo2_a)         # centro 200: sem fiscal
        self.entrar_como(self.fiscal_a, 'a')
        lista = self.client.get('/chamados/')
        self.assertContains(lista, f'/chamados/{do_centro.pk}/')
        self.assertNotContains(lista, f'/chamados/{de_outro.pk}/')

    def test_gestor_de_unidade_ve_so_a_propria_secretaria(self):
        sma = self.chamado(self.gestor_a, self.veiculo_a)
        sme = self.chamado(self.gestor_a, self.veiculo2_a)
        self.entrar_como(self.gestor_unidade_a, 'a')
        lista = self.client.get('/chamados/')
        self.assertContains(lista, f'/chamados/{sma.pk}/')
        self.assertNotContains(lista, f'/chamados/{sme.pk}/')

    def test_consulta_ve_mas_nao_abre_nem_decide(self):
        chamado = self.chamado()
        self.entrar_como(self.consulta_a, 'a')
        self.assertContains(self.client.get('/chamados/'), f'/chamados/{chamado.pk}/')
        self.assertEqual(self.client.get('/chamados/novo/').status_code, 403)
        self.assertEqual(self.client.post(f'/chamados/{chamado.pk}/em-analise/').status_code, 403)

    def test_solicitante_e_oficina_nao_veem_chamados_de_ninguem(self):
        chamado = self.chamado()
        self.trocar_para(self.solicitante_a)
        self.assertEqual(self.client.get('/chamados/').status_code, 403)
        self.trocar_para(self.oficina_a)
        self.assertNotContains(self.client.get('/chamados/'), f'/chamados/{chamado.pk}/')

    def test_outra_prefeitura_nao_ve_o_chamado(self):
        chamado = self.chamado()
        self.entrar_como(self.admin_b, 'b')
        self.assertEqual(self.client.get(f'/chamados/{chamado.pk}/').status_code, 404)

    def test_gestor_decide_e_so_o_gestor(self):
        chamado = self.chamado()
        self.entrar_como(self.motorista_usuario_a, 'a')
        self.assertEqual(self.client.post(f'/chamados/{chamado.pk}/improcedente/', {'motivo': 'x'}).status_code, 403)
        self.trocar_para(self.gestor_a)
        resposta = self.client.post(f'/chamados/{chamado.pk}/improcedente/', {'motivo': ''}, follow=True)
        self.assertContains(resposta, 'obrigatório')   # sem motivo, o formulario recusa
        self.client.post(f'/chamados/{chamado.pk}/improcedente/', {'motivo': 'Já resolvido'})
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, 'IMPROCEDENTE')

    def test_quem_abriu_cancela_chamado_ainda_aberto(self):
        chamado = self.chamado()
        self.entrar_como(self.motorista_usuario_a, 'a')
        self.client.post(f'/chamados/{chamado.pk}/cancelar/')
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, 'CANCELADO')

    def test_gerar_smv_a_partir_do_chamado(self):
        chamado = self.chamado()
        self.entrar_como(self.gestor_a, 'a')
        formulario = self.client.get(f'/smv/novo/?chamado={chamado.pk}')
        self.assertContains(formulario, 'Freio fazendo barulho')   # o defeito ja vem preenchido
        resposta = self.client.post(f'/smv/novo/?chamado={chamado.pk}', {
            'veiculo': self.veiculo_a.pk, 'tipo': 'CORRETIVA', 'fornecedor': self.fornecedor_a.pk,
            'entrada_em': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'entrada_km': '1200', 'defeito_relatado': 'Freio fazendo barulho'})
        smv = Smv.objects.get(chamado=chamado)
        self.assertRedirects(resposta, f'/smv/{smv.pk}/', fetch_redirect_response=False)
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, 'GEROU_SMV')

    def test_smv_com_km_menor_mostra_o_erro_no_formulario(self):
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post('/smv/novo/', {
            'veiculo': self.veiculo_a.pk, 'tipo': 'CORRETIVA', 'fornecedor': self.fornecedor_a.pk,
            'entrada_em': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'entrada_km': '10'})
        self.assertContains(resposta, 'não pode diminuir')
        self.assertFalse(Smv.objects.exists())

    def test_smv_nao_aceita_oficina_de_outra_prefeitura(self):
        self.entrar_como(self.gestor_a, 'a')
        self.client.post('/smv/novo/', {'veiculo': self.veiculo_a.pk, 'tipo': 'CORRETIVA', 'fornecedor': self.fornecedor_b.pk,
                                        'entrada_em': timezone.localtime().strftime('%Y-%m-%dT%H:%M')})
        self.assertFalse(Smv.objects.exists())


class PortalDaOficinaTest(BaseTelas):
    def outra_oficina(self):
        usar_papel_da_aplicacao(self.a.id)
        return Fornecedor.objects.create(municipio=self.a, cnpj_cpf='04252011000110', razao_social='Outra Oficina', tipo='OFICINA')

    def test_oficina_ve_so_as_proprias_smvs(self):
        propria = self.smv(self.veiculo_a)
        outra = self.smv(self.veiculo2_a, fornecedor=self.outra_oficina())
        self.entrar_como(self.oficina_a, 'a')
        lista = self.client.get('/smv/')
        self.assertContains(lista, f'/smv/{propria.pk}/')
        self.assertNotContains(lista, f'/smv/{outra.pk}/')
        self.assertEqual(self.client.get(f'/smv/{outra.pk}/').status_code, 404)
        self.assertNotContains(lista, '/smv/novo/')
        self.assertEqual(self.client.get('/smv/novo/').status_code, 403)

    def test_oficina_nao_ve_orcamento_nem_anexo_de_outra_oficina(self):
        outra = self.smv(self.veiculo2_a, fornecedor=self.outra_oficina())
        services.registrar_diagnostico(outra, self.gestor_a, 'x')
        orcamento = services.criar_orcamento(outra, self.gestor_a)
        self.entrar_como(self.oficina_a, 'a')
        self.assertEqual(self.client.get(f'/orcamentos/{orcamento.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/orcamentos/{orcamento.pk}/itens/novo/', {'tipo': 'PECA', 'descricao': 'x', 'quantidade': '1', 'valor_unitario': '1'}).status_code, 404)

    def test_oficina_faz_diagnostico_orcamento_e_envia(self):
        smv = self.smv()
        self.entrar_como(self.oficina_a, 'a')
        self.client.post(f'/smv/{smv.pk}/diagnostico/', {'diagnostico': 'Pastilhas gastas'})
        smv.refresh_from_db()
        self.assertEqual((smv.etapa, smv.diagnostico), ('DIAGNOSTICO', 'Pastilhas gastas'))
        resposta = self.client.post(f'/smv/{smv.pk}/orcamento/novo/')
        orcamento = Orcamento.objects.get(smv=smv)
        self.assertRedirects(resposta, f'/orcamentos/{orcamento.pk}/', fetch_redirect_response=False)
        for dados in ({'tipo': 'PECA', 'descricao': 'Pastilha', 'quantidade': '2', 'valor_unitario': '100,00'},
                      {'tipo': 'SERVICO', 'descricao': 'Mão de obra', 'quantidade': '1', 'valor_unitario': '300'}):
            self.client.post(f'/orcamentos/{orcamento.pk}/itens/novo/', dados)
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.valor_total, D('500.00'))
        self.assertContains(self.client.get(f'/orcamentos/{orcamento.pk}/'), 'Pastilha')
        self.client.post(f'/orcamentos/{orcamento.pk}/enviar/')
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, 'RECEBIDO')
        self.assertTrue(Notificacao.objects.filter(usuario=self.gestor_a, entidade='orcamentos').exists())

    def test_oficina_nao_assina_nem_analisa_nem_cancela(self):
        smv, orcamento = self.orcamento_enviado()
        self.entrar_como(self.oficina_a, 'a')
        for caminho in (f'/orcamentos/{orcamento.pk}/assinar/', f'/orcamentos/{orcamento.pk}/analisar/', f'/orcamentos/{orcamento.pk}/devolver/',
                        f'/orcamentos/{orcamento.pk}/referencias/', f'/smv/{smv.pk}/cancelar/', f'/smv/{smv.pk}/conferir-nota/'):
            self.assertEqual(self.client.post(caminho, {'decisao': 'APROVADO', 'motivo': 'x'}).status_code, 403, caminho)

    def test_oficina_nao_edita_orcamento_ja_enviado(self):
        _, orcamento = self.orcamento_enviado()
        self.entrar_como(self.oficina_a, 'a')
        resposta = self.client.post(f'/orcamentos/{orcamento.pk}/itens/novo/', {'tipo': 'PECA', 'descricao': 'Extra', 'quantidade': '1', 'valor_unitario': '5'}, follow=True)
        self.assertContains(resposta, 'já foi enviado')
        self.assertEqual(orcamento.itens.count(), 2)

    def test_gestor_age_pela_oficina_quando_ela_nao_usa_o_sistema(self):
        smv = self.smv()
        self.entrar_como(self.gestor_a, 'a')
        self.client.post(f'/smv/{smv.pk}/diagnostico/', {'diagnostico': 'Informado por e-mail'})
        smv.refresh_from_db()
        self.assertEqual(smv.etapa, 'DIAGNOSTICO')

    def test_consulta_e_fiscal_nao_agem_pela_oficina(self):
        smv = self.smv()
        for usuario in (self.consulta_a, self.fiscal_a):
            self.trocar_para(usuario)
            self.assertEqual(self.client.post(f'/smv/{smv.pk}/diagnostico/', {'diagnostico': 'x'}).status_code, 403, usuario.email)


class AprovacaoTelasTest(BaseTelas):
    def test_fluxo_pelas_telas_ate_aprovar_e_reservar(self):
        smv, orcamento = self.orcamento_enviado()
        self.trocar_para(self.gestor_a)
        self.client.post(f'/orcamentos/{orcamento.pk}/analisar/')
        item = orcamento.itens.get(descricao='Pastilha')
        self.client.post(f'/orcamentos/{orcamento.pk}/referencias/', {f'ref_{item.pk}': '80,00'})
        item.refresh_from_db()
        self.assertEqual(item.valor_referencia, D('80.00'))
        pagina = self.client.get(f'/orcamentos/{orcamento.pk}/')
        self.assertContains(pagina, '+R$ 20,00')    # a oficina cobra 20 acima da referencia
        self.client.post(f'/orcamentos/{orcamento.pk}/empenho/', {'empenho': self.empenho_a.pk})
        for usuario in (self.gestor_a, self.admin_a, self.gestor2_a):
            self.trocar_para(usuario)
            self.client.post(f'/orcamentos/{orcamento.pk}/assinar/', {'decisao': 'APROVADO'})
        orcamento.refresh_from_db()
        smv.refresh_from_db()
        self.assertEqual((orcamento.status, smv.etapa), ('APROVADO', 'EXECUCAO'))
        self.assertEqual(saldo_do_empenho(self.empenho_a).saldo, D('500.00'))
        self.assertContains(self.client.get(f'/orcamentos/{orcamento.pk}/'), 'Assinaturas: 3 de 3')

    def test_sem_saldo_a_tela_avisa_e_nao_aprova(self):
        smv = self.smv()
        usar_papel_da_aplicacao(self.a.id)
        services.registrar_diagnostico(smv, self.oficina_a, 'x')
        orcamento = services.criar_orcamento(smv, self.oficina_a)
        services.adicionar_item(orcamento, tipo='PECA', descricao='Motor', quantidade=D('1'), valor_unitario=D('1500'))
        services.enviar_orcamento(Orcamento.objects.get(pk=orcamento.pk), self.oficina_a)
        orcamento.refresh_from_db()
        services.iniciar_analise(orcamento, self.gestor_a)
        services.definir_empenho(orcamento, self.empenho_a)
        services.assinar_orcamento(orcamento, self.admin_a, 'APROVADO')
        services.assinar_orcamento(orcamento, self.gestor_a, 'APROVADO')
        self.trocar_para(self.gestor2_a)
        pagina = self.client.get(f'/orcamentos/{orcamento.pk}/')
        self.assertContains(pagina, 'sem saldo, o orçamento não pode ser aprovado')
        resposta = self.client.post(f'/orcamentos/{orcamento.pk}/assinar/', {'decisao': 'APROVADO'}, follow=True)
        self.assertContains(resposta, 'Saldo insuficiente')
        orcamento.refresh_from_db()
        self.assertEqual((orcamento.status, orcamento.aprovacoes.count()), ('EM_ANALISE', 2))

    def test_so_quem_pode_aprovar_ve_os_botoes_de_assinatura(self):
        _, orcamento = self.orcamento_enviado()
        usar_papel_da_aplicacao(self.a.id)
        services.iniciar_analise(orcamento, self.gestor_a)
        self.trocar_para(self.admin_a)
        self.assertContains(self.client.get(f'/orcamentos/{orcamento.pk}/'), 'name="decisao" value="APROVADO"')
        self.trocar_para(self.consulta_a)
        pagina = self.client.get(f'/orcamentos/{orcamento.pk}/')
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, 'name="decisao"')
        self.assertEqual(self.client.post(f'/orcamentos/{orcamento.pk}/assinar/', {'decisao': 'APROVADO'}).status_code, 403)

    def test_devolver_para_revisao_pela_tela(self):
        _, orcamento = self.orcamento_enviado()
        self.trocar_para(self.gestor_a)
        self.client.post(f'/orcamentos/{orcamento.pk}/devolver/', {'motivo': 'Pastilha cara'})
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, 'REVISAO')
        self.trocar_para(self.oficina_a)
        self.assertContains(self.client.get(f'/orcamentos/{orcamento.pk}/'), 'Pastilha cara')

    def test_orcamento_de_outra_prefeitura_nao_aparece(self):
        _, orcamento = self.orcamento_enviado()
        self.trocar_para(self.admin_b, 'b')
        self.assertEqual(self.client.get(f'/orcamentos/{orcamento.pk}/').status_code, 404)
        self.assertNotContains(self.client.get('/orcamentos/'), f'/orcamentos/{orcamento.pk}/')

    def test_pagina_de_cada_papel_abre(self):
        smv, orcamento = self.orcamento_enviado()
        chamado = self.chamado()
        for usuario in (self.admin_a, self.gestor_a, self.fiscal_a, self.consulta_a, self.oficina_a, self.gestor_unidade_a):
            self.trocar_para(usuario)
            for caminho in (f'/smv/{smv.pk}/', f'/orcamentos/{orcamento.pk}/', '/smv/', '/orcamentos/'):
                self.assertEqual(self.client.get(caminho).status_code, 200, f'{usuario.email} {caminho}')
        self.trocar_para(self.fiscal_a)
        self.assertEqual(self.client.get(f'/chamados/{chamado.pk}/').status_code, 200)


class NotaFiscalTelasTest(BaseTelas):
    def test_entrega_nota_e_conferencia_pelas_telas(self):
        smv, orcamento = self.orcamento_enviado()
        usar_papel_da_aplicacao(self.a.id)
        services.iniciar_analise(orcamento, self.gestor_a)
        services.definir_empenho(orcamento, self.empenho_a)
        for usuario in (self.admin_a, self.gestor_a, self.gestor2_a):
            services.assinar_orcamento(orcamento, usuario, 'APROVADO')
        pasta = tempfile.mkdtemp(prefix='sigfrotas_teste_')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=pasta):
            self.trocar_para(self.oficina_a)
            self.client.post(f'/smv/{smv.pk}/entrega/', {'saida_em': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'saida_km': '1300'})
            smv.refresh_from_db()
            self.assertEqual(smv.etapa, 'ENTREGA')
            resposta = self.client.post(f'/smv/{smv.pk}/nota-fiscal/', {
                'nf_pecas_numero': '10', 'nf_pecas_valor': '200,00', 'nf_servicos_numero': '11', 'nf_servicos_valor': '350,00',
                'nf_emissao': timezone.localdate().isoformat()}, follow=True)
            self.assertContains(resposta, 'acima do valor aprovado')
            self.client.post(f'/smv/{smv.pk}/nota-fiscal/', {
                'nf_pecas_numero': '10', 'nf_pecas_valor': '200,00', 'nf_servicos_numero': '11', 'nf_servicos_valor': '290,00',
                'nf_emissao': timezone.localdate().isoformat(),
                'arquivo': SimpleUploadedFile('nf.pdf', b'%PDF-1.4 nota', content_type='application/pdf')})
            smv.refresh_from_db()
            self.assertEqual(smv.etapa, 'NOTA_FISCAL')
            self.trocar_para(self.gestor_a)
            pagina = self.client.get(f'/smv/{smv.pk}/')
            self.assertContains(pagina, 'Conferir nota e concluir')
            self.assertContains(pagina, 'R$ 490,00')
            self.client.post(f'/smv/{smv.pk}/conferir-nota/')
            smv.refresh_from_db()
            self.assertEqual(smv.etapa, 'CONCLUIDA')
            self.assertEqual(saldo_do_empenho(self.empenho_a).consumido, D('490.00'))
            anexo = orcamento.__class__.objects.get(pk=orcamento.pk)
            from apps.core.models import Anexo
            nota = Anexo.objects.get(entidade='orcamentos', entidade_id=anexo.pk)
            self.assertEqual(self.client.get(f'/anexos/{nota.pk}/').status_code, 200)
            self.trocar_para(self.admin_b, 'b')
            self.assertEqual(self.client.get(f'/anexos/{nota.pk}/').status_code, 404)


class ChatTelasTest(BaseTelas):
    def test_chat_por_htmx_atualiza_so_a_lista_e_avisa_o_outro_lado(self):
        smv = self.smv()
        self.entrar_como(self.oficina_a, 'a')
        resposta = self.client.post(f'/smv/{smv.pk}/mensagens/', {'texto': 'Chegamos com o veículo.'}, **HX)
        self.assertNotContains(resposta, '<html')
        self.assertContains(resposta, 'Chegamos com o veículo.')
        self.assertTrue(Notificacao.objects.filter(usuario=self.gestor_a, entidade='smv', canal='APP').exists())
        self.trocar_para(self.gestor_a)
        self.assertContains(self.client.get(f'/smv/{smv.pk}/mensagens/', **HX), 'Chegamos com o veículo.')
        self.assertContains(self.client.get(f'/smv/{smv.pk}/'), 'Chegamos com o veículo.')

    def test_mensagem_vazia_avisa_sem_quebrar(self):
        smv = self.smv()
        self.entrar_como(self.gestor_a, 'a')
        resposta = self.client.post(f'/smv/{smv.pk}/mensagens/', {'texto': ''}, **HX)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Escreva uma mensagem', resposta['HX-Trigger'])

    def test_quem_nao_ve_a_smv_nao_le_nem_escreve_no_chat(self):
        smv = self.smv()
        self.entrar_como(self.admin_b, 'b')
        self.assertEqual(self.client.get(f'/smv/{smv.pk}/mensagens/').status_code, 404)
        self.assertEqual(self.client.post(f'/smv/{smv.pk}/mensagens/', {'texto': 'oi'}).status_code, 404)
        self.trocar_para(self.solicitante_a)
        self.assertEqual(self.client.get(f'/smv/{smv.pk}/mensagens/').status_code, 403)

    def test_anexo_do_chat_so_para_quem_ve_a_smv(self):
        smv = self.smv()
        pasta = tempfile.mkdtemp(prefix='sigfrotas_teste_')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=pasta):
            self.entrar_como(self.oficina_a, 'a')
            self.client.post(f'/smv/{smv.pk}/mensagens/', {'texto': 'Foto da peça', 'arquivo': SimpleUploadedFile('peca.jpg', b'\xff\xd8\xff', content_type='image/jpeg')})
            from apps.core.models import Anexo
            anexo = Anexo.objects.get(entidade='smv_mensagens')
            self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 200)
            self.trocar_para(self.gestor_a)
            self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 200)
            self.trocar_para(self.admin_b, 'b')
            self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 404)


class NotificacoesTelasTest(BaseTelas):
    def test_sino_mostra_quantas_nao_lidas_e_abrir_marca_como_lida(self):
        chamado = self.chamado()
        self.entrar_como(self.fiscal_a, 'a')
        inicio = self.client.get('/')
        self.assertEqual(inicio.context['notificacoes_nao_lidas'], 1)
        aviso = Notificacao.objects.get(usuario=self.fiscal_a, canal='APP')
        lista = self.client.get('/notificacoes/')
        self.assertContains(lista, f'Novo chamado {chamado.numero}')
        resposta = self.client.get(f'/notificacoes/{aviso.pk}/abrir/')
        self.assertRedirects(resposta, f'/chamados/{chamado.pk}/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/').context['notificacoes_nao_lidas'], 0)

    def test_ninguem_abre_notificacao_de_outro(self):
        self.chamado()
        aviso = Notificacao.objects.get(usuario=self.fiscal_a, canal='APP')
        self.entrar_como(self.gestor_a, 'a')
        self.assertEqual(self.client.get(f'/notificacoes/{aviso.pk}/abrir/').status_code, 404)
        self.assertNotContains(self.client.get('/notificacoes/'), f'/notificacoes/{aviso.pk}/abrir/')   # a do fiscal nao aparece na lista do gestor

    def test_marcar_todas_como_lidas(self):
        self.chamado()
        self.chamado()
        self.entrar_como(self.gestor_a, 'a')
        self.assertEqual(self.client.get('/').context['notificacoes_nao_lidas'], 2)
        self.client.post('/notificacoes/ler-todas/')
        self.assertEqual(self.client.get('/').context['notificacoes_nao_lidas'], 0)

    def test_link_de_fora_do_sistema_nao_e_seguido(self):
        usar_papel_da_aplicacao(self.a.id)
        aviso = Notificacao.objects.create(municipio=self.a, usuario=self.gestor_a, canal='APP', assunto='x', link='//externo.example/')
        self.entrar_como(self.gestor_a, 'a')
        self.assertRedirects(self.client.get(f'/notificacoes/{aviso.pk}/abrir/'), '/notificacoes/', fetch_redirect_response=False)

    def test_comando_envia_os_emails_pendentes(self):
        self.chamado()
        usar_papel_dono_e_enviar = None  # o comando usa a propria conexao; aqui roda como dono (testes)
        from apps.core.tests.base import usar_papel_dono
        usar_papel_dono()
        call_command('enviar_notificacoes', stdout=open('NUL' if False else __import__('os').devnull, 'w'))
        self.assertTrue(mail.outbox)
        destinatarios = {d for m in mail.outbox for d in m.to}
        self.assertIn('fiscal@a.test', destinatarios)
        self.assertTrue(mail.outbox[0].subject.startswith('[SigFrotas] '))
        self.assertEqual(Notificacao.objects.filter(canal='EMAIL', status='PENDENTE').count(), 0)
        enviadas = len(mail.outbox)
        call_command('enviar_notificacoes', stdout=open(__import__('os').devnull, 'w'))
        self.assertEqual(len(mail.outbox), enviadas)   # nao reenvia
