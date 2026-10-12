"""Perfis fixos (criados com cada prefeitura) e suas permissoes.

"x.gerir" inclui "x.ver" (e algumas outras implicacoes abaixo). Quem so "ve" enxerga apenas o proprio escopo (ver escopo.py).
"""

GERIR_NUCLEO = ['usuarios.gerir', 'estrutura.gerir', 'auditoria.ver']
GERIR_FROTA = ['frota.gerir', 'financeiro.gerir', 'pessoas.gerir', 'pessoas.dados_pessoais',
               'manutencao.gerir', 'manutencao.aprovar', 'manutencao.abrir']

# Alem de "x.gerir", quem tem uma destas permissoes tambem satisfaz a permissao da esquerda.
IMPLICADA_POR = {
    'manutencao.ver': ('manutencao.gerir', 'manutencao.abrir', 'manutencao.oficina'),
}

# codigo: (nome, permissoes)
PERFIS_PADRAO = {
    'ADMIN': ('Administrador', GERIR_NUCLEO + GERIR_FROTA),
    'GESTOR_FROTA': ('Gestor de frota', GERIR_FROTA),
    'GESTOR_UNIDADE': ('Gestor de unidade', ['frota.ver', 'pessoas.ver', 'manutencao.ver', 'manutencao.abrir']),
    'SOLICITANTE': ('Solicitante', []),
    'MOTORISTA': ('Motorista', ['manutencao.abrir']),
    'FISCAL': ('Fiscal de contrato', ['frota.ver', 'financeiro.ver', 'manutencao.ver', 'manutencao.abrir']),
    'OFICINA': ('Oficina', ['manutencao.oficina']),
    'CONSULTA': ('Consulta', ['frota.ver', 'financeiro.ver', 'pessoas.ver', 'manutencao.ver']),
}
