from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Municipio
from apps.core.services import criar_usuario


class Command(BaseCommand):
    help = 'Cria o administrador de uma prefeitura. A senha e pedida no terminal.'

    def add_arguments(self, parser):
        parser.add_argument('--prefeitura', required=True, help='slug da prefeitura')
        parser.add_argument('--nome', required=True)
        parser.add_argument('--email', required=True)

    def handle(self, *args, **o):
        municipio = Municipio.objects.filter(slug=o['prefeitura']).first()
        if municipio is None:
            raise CommandError('Prefeitura não encontrada.')
        senha = getpass('Senha: ')
        if senha != getpass('Repita a senha: '):
            raise CommandError('As senhas não conferem.')
        try:
            validate_password(senha)
        except ValidationError as erro:
            raise CommandError(' '.join(erro.messages))
        criar_usuario(municipio=municipio, perfil_codigo='ADMIN', nome=o['nome'], email=o['email'], senha=senha)
        self.stdout.write(self.style.SUCCESS('Administrador criado.'))
