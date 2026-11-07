import django.db.models.deletion
from django.db import migrations, models


def ligar_ao_fornecedor(apps, schema_editor):
    """O texto antigo vira o fornecedor de mesma razao social (da mesma prefeitura); sem correspondencia, fica vazio."""
    Veiculo = apps.get_model('frota', 'Veiculo')
    Fornecedor = apps.get_model('financeiro', 'Fornecedor')
    for veiculo in Veiculo.objects.exclude(proprietario=''):
        achado = Fornecedor.objects.filter(municipio_id=veiculo.municipio_id,
                                           razao_social__iexact=veiculo.proprietario.strip()).first()
        if achado:
            veiculo.proprietario_novo = achado
            veiculo.save(update_fields=['proprietario_novo'])


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0001_initial'),
        ('frota', '0002_rls_e_combustiveis'),
    ]

    operations = [
        migrations.AddField(
            model_name='veiculo', name='proprietario_novo',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
                                    to='financeiro.fornecedor'),
        ),
        migrations.RunPython(ligar_ao_fornecedor, migrations.RunPython.noop),
        migrations.RemoveField(model_name='veiculo', name='proprietario'),
        migrations.RenameField(model_name='veiculo', old_name='proprietario_novo', new_name='proprietario'),
        migrations.AlterField(
            model_name='veiculo', name='proprietario',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
                                    to='financeiro.fornecedor', verbose_name='Proprietário (locadora ou órgão)'),
        ),
    ]
