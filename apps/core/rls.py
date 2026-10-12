"""Ajudantes de migracao para a RLS. Toda tabela nova com municipio_id deve usar habilitar_rls() na sua migracao."""
from django.db import migrations

SQL_FUNCAO = """
CREATE OR REPLACE FUNCTION municipio_atual() RETURNS bigint
LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.municipio_id', true), '')::bigint $$;
"""


def habilitar_rls(tabela):
    return migrations.RunSQL(
        sql=f"""
        ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON {tabela}
            USING (municipio_id = municipio_atual())
            WITH CHECK (municipio_id = municipio_atual());
        """,
        reverse_sql=f"""
        DROP POLICY tenant_isolation ON {tabela};
        ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY;
        """,
    )
