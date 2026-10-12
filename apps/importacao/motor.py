"""Importacao em lote: verifica sem gravar e so grava se TODAS as linhas estiverem corretas."""
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from .leitor import ler_csv


@dataclass
class Resultado:
    linhas: list = field(default_factory=list)   # (numero, erro ou None, descricao)
    gravado: bool = False
    erro_geral: str = ''

    @property
    def erros(self):
        return [linha for linha in self.linhas if linha[1]]

    @property
    def total_ok(self):
        return len([linha for linha in self.linhas if not linha[1]])


def mensagem_do_erro(erro):
    if isinstance(erro, ValidationError):
        return ' '.join(erro.messages)
    return str(erro)


def executar(*, conteudo, importador, municipio_id, gravar):
    """importador: modulo com COLUNAS e importar_linha(linha, municipio_id) -> descricao (levanta ValueError/ValidationError)."""
    resultado = Resultado()
    try:
        cabecalhos, linhas = ler_csv(conteudo)
    except ValueError as erro:
        resultado.erro_geral = str(erro)
        return resultado
    faltando = [nome for nome, obrigatoria, _ in importador.COLUNAS if obrigatoria and nome not in cabecalhos]
    if faltando:
        resultado.erro_geral = 'Faltam colunas obrigatórias no cabeçalho: ' + ', '.join(faltando) + '.'
        return resultado
    if not linhas:
        resultado.erro_geral = 'O arquivo não tem nenhuma linha de dados.'
        return resultado

    ponto = transaction.savepoint()
    for numero, linha in linhas:
        try:
            with transaction.atomic():  # o erro de uma linha nao desfaz as outras (so a conferencia final decide)
                resultado.linhas.append((numero, None, importador.importar_linha(linha, municipio_id)))
        except (ValueError, ValidationError) as erro:
            resultado.linhas.append((numero, mensagem_do_erro(erro), ''))
    if gravar and not resultado.erros:
        transaction.savepoint_commit(ponto)
        resultado.gravado = True
    else:
        transaction.savepoint_rollback(ponto)  # verificacao (ou erro): nada fica gravado
    return resultado
