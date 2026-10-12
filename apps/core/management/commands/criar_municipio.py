from django.core.management.base import BaseCommand

from apps.core.services import criar_municipio


class Command(BaseCommand):
    help = 'Cria uma prefeitura com os 8 perfis fixos.'

    def add_arguments(self, parser):
        parser.add_argument('--nome', required=True)
        parser.add_argument('--slug', required=True, help='identificador no login, ex: santana-de-parnaiba')
        parser.add_argument('--uf', required=True)
        parser.add_argument('--cnpj', required=True, help='somente numeros')
        parser.add_argument('--ibge', default='')

    def handle(self, *args, **o):
        municipio = criar_municipio(nome=o['nome'], slug=o['slug'], uf=o['uf'], cnpj=o['cnpj'], codigo_ibge=o['ibge'])
        self.stdout.write(self.style.SUCCESS(f'Prefeitura criada: {municipio.nome} (id {municipio.id})'))
