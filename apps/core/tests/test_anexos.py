import hashlib
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.services import anexar
from apps.core.tenant import com_municipio

from .base import TelasTest

PASTA = tempfile.mkdtemp(prefix='sigfrotas_teste_')


@override_settings(MEDIA_ROOT=PASTA)
class AnexosTest(TelasTest):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(PASTA, ignore_errors=True)

    def enviar(self, municipio, usuario, conteudo=b'conteudo do arquivo'):
        arquivo = SimpleUploadedFile('nota fiscal.pdf', conteudo, content_type='application/pdf')
        with com_municipio(municipio.id):
            return anexar(municipio_id=municipio.id, entidade='secretarias', entidade_id=1, arquivo=arquivo,
                          categoria='NOTA_FISCAL', enviado_por=usuario)

    def test_guarda_hash_tamanho_e_tipo(self):
        anexo = self.enviar(self.a, self.admin_a)
        self.assertEqual(anexo.hash_sha256, hashlib.sha256(b'conteudo do arquivo').hexdigest())
        self.assertEqual(anexo.tamanho_bytes, len(b'conteudo do arquivo'))
        self.assertEqual(anexo.mime_type, 'application/pdf')
        self.assertEqual(anexo.nome_arquivo, 'nota fiscal.pdf')
        self.assertNotIn('nota', anexo.arquivo.name)  # o nome no armazenamento e gerado pelo sistema
        self.assertTrue(anexo.arquivo.name.startswith(f'{self.a.id}/secretarias/1/'))

    def test_recusa_arquivo_maior_que_o_limite(self):
        with override_settings(ANEXO_TAMANHO_MAXIMO=5), self.assertRaises(ValidationError):
            self.enviar(self.a, self.admin_a)

    def test_baixa_o_proprio_anexo(self):
        anexo = self.enviar(self.a, self.admin_a)
        self.entrar_como(self.admin_a, 'a')
        resposta = self.client.get(f'/anexos/{anexo.pk}/')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b''.join(resposta.streaming_content), b'conteudo do arquivo')

    def test_outra_prefeitura_nao_baixa(self):
        anexo = self.enviar(self.a, self.admin_a)
        self.entrar_como(self.admin_b, 'b')
        self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 404)

    def test_anonimo_nao_baixa(self):
        anexo = self.enviar(self.a, self.admin_a)
        self.assertEqual(self.client.get(f'/anexos/{anexo.pk}/').status_code, 302)
