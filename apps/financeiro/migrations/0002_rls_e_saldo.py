"""RLS das tabelas do financeiro e a view do saldo de empenho."""
from django.db import migrations

from apps.core.rls import habilitar_rls

TABELAS = ['fornecedores', 'contratos', 'fiscais_contrato', 'empenhos', 'empenho_liberacoes', 'empenho_lancamentos']

# saldo = liberado - reservado - consumido + estornado. security_invoker: a view respeita a RLS de quem consulta.
VIEW = """
CREATE VIEW vw_saldo_empenho WITH (security_invoker = true) AS
SELECT e.id AS empenho_id, e.municipio_id, e.centro_custo_id, e.finalidade, e.valor_empenhado,
       lib.total AS liberado,
       lan.reservado, lan.consumido, lan.estornado,
       lib.total - lan.reservado - lan.consumido + lan.estornado AS saldo
FROM empenhos e
CROSS JOIN LATERAL (
    SELECT COALESCE(SUM(valor), 0) AS total FROM empenho_liberacoes WHERE empenho_id = e.id
) lib
CROSS JOIN LATERAL (
    SELECT COALESCE(SUM(valor) FILTER (WHERE tipo = 'RESERVA'), 0) AS reservado,
           COALESCE(SUM(valor) FILTER (WHERE tipo = 'CONSUMO'), 0) AS consumido,
           COALESCE(SUM(valor) FILTER (WHERE tipo = 'ESTORNO'), 0) AS estornado
    FROM empenho_lancamentos WHERE empenho_id = e.id
) lan;
"""


class Migration(migrations.Migration):

    dependencies = [('financeiro', '0001_initial'), ('core', '0002_rls_e_permissoes')]

    operations = [
        *[habilitar_rls(t) for t in TABELAS],
        migrations.RunSQL(VIEW, reverse_sql='DROP VIEW vw_saldo_empenho'),
    ]
