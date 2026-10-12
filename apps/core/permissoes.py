"""Perfis fixos (criados com cada prefeitura) e suas permissoes.

Permissao "x.gerir" inclui "x.ver". Quem so "ve" enxerga apenas o proprio escopo (ver escopo.py).
"""

GERIR_NUCLEO = ['usuarios.gerir', 'estrutura.gerir', 'auditoria.ver']
GERIR_FROTA = ['frota.gerir', 'financeiro.gerir', 'pessoas.gerir', 'pessoas.dados_pessoais']

# codigo: (nome, permissoes)
PERFIS_PADRAO = {
    'ADMIN': ('Administrador', GERIR_NUCLEO + GERIR_FROTA),
    'GESTOR_FROTA': ('Gestor de frota', GERIR_FROTA),
    'GESTOR_UNIDADE': ('Gestor de unidade', ['frota.ver', 'pessoas.ver']),
    'SOLICITANTE': ('Solicitante', []),
    'MOTORISTA': ('Motorista', []),
    'FISCAL': ('Fiscal de contrato', ['frota.ver', 'financeiro.ver']),
    'OFICINA': ('Oficina', []),
    'CONSULTA': ('Consulta', ['frota.ver', 'financeiro.ver', 'pessoas.ver']),
}
