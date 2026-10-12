"""RLS das tabelas da manutencao e a view de dias em manutencao."""
from django.db import migrations

from apps.core.rls import habilitar_rls

TABELAS = ['categorias_servico', 'chamados', 'smv', 'smv_etapas_hist', 'smv_mensagens', 'orcamentos', 'orcamento_itens',
           'orcamento_aprovacoes']

VIEW = """
CREATE VIEW vw_dias_em_manutencao WITH (security_invoker = true) AS
SELECT s.id AS smv_id, s.municipio_id, s.veiculo_id, s.numero, s.etapa,
       GREATEST(0, (COALESCE(s.saida_em, now())::date - s.entrada_em::date)) AS dias_em_manutencao
FROM smv s
WHERE s.entrada_em IS NOT NULL;
"""


class Migration(migrations.Migration):

    dependencies = [('manutencao', '0001_initial'), ('core', '0002_rls_e_permissoes')]

    operations = [
        *[habilitar_rls(t) for t in TABELAS],
        migrations.RunSQL(VIEW, reverse_sql='DROP VIEW vw_dias_em_manutencao'),
    ]
