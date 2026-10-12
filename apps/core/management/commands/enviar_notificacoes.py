from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Municipio, Notificacao
from apps.core.tenant import com_municipio


class Command(BaseCommand):
    help = 'Envia os e-mails pendentes da fila de notificacoes. No servidor: cron a cada minuto (ver docs/operacao.md).'

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=200, help='maximo de e-mails por prefeitura em cada execucao')

    def handle(self, *args, limite, **opcoes):
        enviados = erros = 0
        for municipio in Municipio.objects.filter(ativo=True):
            with com_municipio(municipio.id):
                pendentes = list(Notificacao.objects.filter(canal='EMAIL', status='PENDENTE').order_by('id')[:limite])
                for aviso in pendentes:
                    texto = aviso.corpo
                    if aviso.link and settings.SITE_URL:
                        texto += f'\n\n{settings.SITE_URL.rstrip("/")}{aviso.link}'
                    try:
                        send_mail(f'[SigFrotas] {aviso.assunto}', texto, settings.DEFAULT_FROM_EMAIL, [aviso.email_destino])
                        aviso.status, aviso.enviada_em = 'ENVIADA', timezone.now()
                        enviados += 1
                    except Exception as erro:  # um e-mail com problema nao trava os demais
                        aviso.status = 'ERRO'
                        aviso.corpo += f'\n\n[erro no envio: {erro}]'
                        erros += 1
                    aviso.save(update_fields=['status', 'enviada_em', 'corpo'])
        self.stdout.write(self.style.SUCCESS(f'E-mails enviados: {enviados}. Com erro: {erros}.'))
