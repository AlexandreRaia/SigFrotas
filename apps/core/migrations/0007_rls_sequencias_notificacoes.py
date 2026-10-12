"""RLS das tabelas de contadores e notificacoes."""
from django.db import migrations

from apps.core.rls import habilitar_rls


class Migration(migrations.Migration):

    dependencies = [('core', '0006_notificacao_sequencia')]

    operations = [habilitar_rls('sequencias'), habilitar_rls('notificacoes')]
