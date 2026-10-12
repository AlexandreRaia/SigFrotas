"""RLS das tabelas da frota e carga dos combustiveis (catalogo global)."""
from django.db import migrations

from apps.core.rls import habilitar_rls

TABELAS = ['categorias_veiculo', 'veiculos', 'veiculo_equipamentos', 'veiculo_lotacoes', 'leituras_veiculo']
COMBUSTIVEIS = ['Gasolina', 'Etanol', 'Diesel S10', 'Diesel S500', 'GNV', 'Elétrico', 'Flex (gasolina/etanol)']


def carregar_combustiveis(apps, schema_editor):
    Combustivel = apps.get_model('frota', 'Combustivel')
    for nome in COMBUSTIVEIS:
        Combustivel.objects.get_or_create(nome=nome)


class Migration(migrations.Migration):

    dependencies = [('frota', '0001_initial'), ('core', '0002_rls_e_permissoes')]

    operations = [
        *[habilitar_rls(t) for t in TABELAS],
        migrations.RunPython(carregar_combustiveis, migrations.RunPython.noop),
    ]
