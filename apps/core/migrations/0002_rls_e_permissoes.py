"""RLS em todas as tabelas de prefeitura e permissoes da role da aplicacao."""
from django.conf import settings
from django.db import migrations

from apps.core.rls import SQL_FUNCAO, habilitar_rls

TABELAS = ['secretarias', 'unidades', 'centros_custo', 'perfis', 'usuarios', 'anexos', 'auditoria']


def conceder_ao_papel_da_aplicacao(apps, schema_editor):
    """A role da aplicacao so le e grava; nao cria nem altera tabelas. Auditoria so recebe inclusoes."""
    papel = settings.DB_APP_USER
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [papel])
        if cursor.fetchone() is None:
            return
    q = schema_editor.quote_name(papel)
    for comando in (
        f'GRANT USAGE ON SCHEMA public TO {q}',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {q}',
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {q}',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {q}',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {q}',
        f'REVOKE UPDATE, DELETE, TRUNCATE ON auditoria FROM {q}',
    ):
        schema_editor.execute(comando)


class Migration(migrations.Migration):

    dependencies = [('core', '0001_inicial')]

    operations = [
        migrations.RunSQL(SQL_FUNCAO, reverse_sql='DROP FUNCTION municipio_atual()'),
        *[habilitar_rls(t) for t in TABELAS],
        migrations.RunPython(conceder_ao_papel_da_aplicacao, migrations.RunPython.noop),
    ]
