from django.contrib.auth.backends import BaseBackend

from .models import Usuario
from .tenant import definir_municipio


class AutenticacaoPorPrefeitura(BaseBackend):
    """Login por prefeitura + e-mail + senha (o e-mail so e unico dentro da prefeitura)."""

    def authenticate(self, request, municipio=None, email=None, password=None):
        if municipio is None or not email or not password:
            return None
        definir_municipio(municipio.id)
        usuario = Usuario.objects.filter(municipio=municipio, email=email).first()
        if usuario is None:
            Usuario().set_password(password)  # gasta o mesmo tempo, para nao revelar se o e-mail existe
            return None
        if usuario.check_password(password) and usuario.ativo:
            return usuario
        return None

    def get_user(self, user_id):
        return Usuario.objects.filter(pk=user_id, ativo=True).first()
