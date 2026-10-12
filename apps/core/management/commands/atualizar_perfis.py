from django.core.management.base import BaseCommand

from apps.core.models import Municipio
from apps.core.services import sincronizar_perfis


class Command(BaseCommand):
    help = 'Acrescenta aos perfis de cada prefeitura as permissoes novas do sistema (nunca remove nem troca as existentes).'

    def handle(self, *args, **opcoes):
        for municipio in Municipio.objects.all():
            for codigo, permissoes in sincronizar_perfis(municipio).items():
                self.stdout.write(f'{municipio.slug}: {codigo} + {", ".join(permissoes)}')
        self.stdout.write(self.style.SUCCESS('Perfis atualizados.'))
