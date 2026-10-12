import csv
import io

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.core.views import PermissaoMixin

from . import motoristas, motor, veiculos


class Inicio(PermissaoMixin, View):
    def get(self, request):
        pode_veiculos = request.user.tem_permissao('frota.gerir')
        pode_motoristas = request.user.tem_permissao('pessoas.gerir') and request.user.tem_permissao('pessoas.dados_pessoais')
        if not (pode_veiculos or pode_motoristas):
            raise PermissionDenied
        return render(request, 'importacao/inicio.html', {'pode_veiculos': pode_veiculos, 'pode_motoristas': pode_motoristas})


class Importar(PermissaoMixin, View):
    """Tela de uma importacao: escolher o arquivo, verificar (sem gravar) e importar."""
    importador = None
    titulo = ''
    permissoes = ()
    voltar = ''      # nome da url da lista, para onde vai depois de importar
    modelo_url = ''  # nome da url do arquivo modelo

    def permitido(self, request):
        return all(request.user.tem_permissao(p) for p in self.permissoes)

    def get(self, request):
        if not self.permitido(request):
            raise PermissionDenied
        return self.tela(request)

    def tela(self, request, resultado=None):
        return render(request, 'importacao/importar.html', {
            'titulo': self.titulo, 'colunas': self.importador.COLUNAS, 'resultado': resultado, 'modelo_url': self.modelo_url})

    def post(self, request):
        if not self.permitido(request):
            raise PermissionDenied
        arquivo = request.FILES.get('arquivo')
        if arquivo is None:
            messages.error(request, 'Escolha o arquivo CSV.')
            return self.tela(request)
        resultado = motor.executar(conteudo=arquivo.read(), importador=self.importador,
                                   municipio_id=request.user.municipio_id, gravar=request.POST.get('acao') == 'importar')
        if resultado.gravado:
            messages.success(request, f'{resultado.total_ok} registro(s) importado(s).')
            return redirect(self.voltar)
        return self.tela(request, resultado)


class Modelo(PermissaoMixin, View):
    """Arquivo CSV de exemplo (separado por ';' e com BOM, para abrir certo no Excel em portugues)."""
    importador = None
    nome = ''

    def get(self, request):
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=';')
        escritor.writerow([c for c, _, _ in self.importador.COLUNAS])
        escritor.writerow(self.importador.EXEMPLO)
        resposta = HttpResponse('﻿' + saida.getvalue(), content_type='text/csv; charset=utf-8')
        resposta['Content-Disposition'] = f'attachment; filename="{self.nome}"'
        return resposta
