"""Prefeitura da requisicao/transacao atual, para a RLS do PostgreSQL."""
from contextlib import contextmanager

from django.db import connection, transaction


def definir_municipio(municipio_id):
    """Executa SET app.municipio_id. Vale so ate o fim da transacao atual (nao vaza entre requisicoes)."""
    valor = '' if municipio_id is None else str(int(municipio_id))
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.municipio_id', %s, true)", [valor])


@contextmanager
def com_municipio(municipio_id):
    """Abre uma transacao ja filtrada pela prefeitura. Usar em comandos e tarefas em segundo plano."""
    with transaction.atomic():
        definir_municipio(municipio_id)
        yield
