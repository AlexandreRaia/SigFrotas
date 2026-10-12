"""Leitura de planilhas CSV (Excel em portugues salva com ';' e, as vezes, em Latin-1) e conversao de valores."""
import csv
import io
import re
import unicodedata

LIMITE_LINHAS = 2000


def normalizar_nome(nome):
    """'Centro de Custo ' -> 'centro_de_custo'"""
    sem_acento = unicodedata.normalize('NFKD', nome or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', sem_acento.lower()).strip('_')


def ler_csv(conteudo):
    """Devolve (cabecalhos, [(numero_da_linha, {cabecalho: valor})]). Linhas em branco sao ignoradas."""
    try:
        texto = conteudo.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = conteudo.decode('latin-1')
    amostra = texto[:3000]
    delimitador = ';' if amostra.count(';') >= amostra.count(',') else ','
    linhas = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    if not linhas or not any(c.strip() for c in linhas[0]):
        raise ValueError('O arquivo está vazio ou sem a linha de cabeçalho.')
    cabecalhos = [normalizar_nome(c) for c in linhas[0]]
    dados = []
    for numero, valores in enumerate(linhas[1:], start=2):
        if not any(v.strip() for v in valores):
            continue
        dados.append((numero, {c: (valores[i].strip() if i < len(valores) else '') for i, c in enumerate(cabecalhos) if c}))
    if len(dados) > LIMITE_LINHAS:
        raise ValueError(f'O arquivo tem mais de {LIMITE_LINHAS} linhas. Divida em partes.')
    return cabecalhos, dados


def inteiro(valor):
    """'12.345' ou '12345 km' -> '12345' (so digitos)"""
    return re.sub(r'\D', '', valor or '')


def decimal_br(valor):
    """'1.234,56' -> '1234.56'; '12,5' -> '12.5'"""
    valor = (valor or '').strip()
    if ',' in valor:
        valor = valor.replace('.', '').replace(',', '.')
    return valor


def data_iso(valor):
    """'31/12/2026' -> '2026-12-31'; aceita tambem 2026-12-31."""
    valor = (valor or '').strip()
    achou = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', valor)
    return f'{achou.group(3)}-{int(achou.group(2)):02d}-{int(achou.group(1)):02d}' if achou else valor


def escolha(valor, opcoes, campo):
    """Aceita o codigo (PROPRIO) ou o rotulo (Próprio), sem diferenciar maiusculas/acentos."""
    if not valor:
        return ''
    alvo = normalizar_nome(valor)
    for codigo, rotulo in opcoes:
        if alvo in (normalizar_nome(codigo), normalizar_nome(rotulo)):
            return codigo
    raise ValueError(f'{campo}: "{valor}" não é uma opção válida ({", ".join(r for _, r in opcoes)}).')
