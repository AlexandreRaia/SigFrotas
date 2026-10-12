"""RLS das tabelas de motoristas."""
from django.db import migrations

from apps.core.rls import habilitar_rls

TABELAS = ['motoristas', 'motorista_certificados', 'motorista_penalidades', 'motorista_afastamentos']


class Migration(migrations.Migration):

    dependencies = [('pessoas', '0001_initial'), ('core', '0002_rls_e_permissoes')]

    operations = [habilitar_rls(t) for t in TABELAS]
