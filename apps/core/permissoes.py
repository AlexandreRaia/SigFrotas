"""Perfis fixos (criados com cada prefeitura) e suas permissoes."""

PERMISSOES_ADMIN = ['usuarios.gerir', 'estrutura.gerir', 'auditoria.ver']

# codigo: (nome, permissoes). As permissoes dos demais perfis entram com os modulos.
PERFIS_PADRAO = {
    'ADMIN': ('Administrador', PERMISSOES_ADMIN),
    'GESTOR_FROTA': ('Gestor de frota', []),
    'GESTOR_UNIDADE': ('Gestor de unidade', []),
    'SOLICITANTE': ('Solicitante', []),
    'MOTORISTA': ('Motorista', []),
    'FISCAL': ('Fiscal de contrato', []),
    'OFICINA': ('Oficina', []),
    'CONSULTA': ('Consulta', []),
}
