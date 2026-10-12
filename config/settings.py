"""Configuracoes do SigFrotas. Segredos e ambiente vem de variaveis de ambiente (.env)."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise RuntimeError('Defina DJANGO_SECRET_KEY no .env')

DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'apps.core.middleware.PrefeituraMiddleware',  # define app.municipio_id (RLS); antes da autenticacao
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

# --- Banco ------------------------------------------------------------------
# Em uso normal a aplicacao conecta com a role SEM privilegios (DB_APP_*), para a RLS valer.
# Migracoes e testes precisam da role dona das tabelas (DB_OWNER_*).
DB_APP_USER = os.environ.get('DB_APP_USER', '')
_papel = 'OWNER' if len(sys.argv) > 1 and sys.argv[1] in ('migrate', 'test') else 'APP'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'sigfrotas'),
        'USER': os.environ.get(f'DB_{_papel}_USER', ''),
        'PASSWORD': os.environ.get(f'DB_{_papel}_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Autenticacao -----------------------------------------------------------
AUTH_USER_MODEL = 'core.Usuario'
AUTHENTICATION_BACKENDS = ['apps.core.auth_backend.AutenticacaoPorPrefeitura']
# O e-mail e unico por prefeitura (nao global); o login e feito pelo backend proprio.
SILENCED_SYSTEM_CHECKS = ['auth.E003', 'auth.W004']
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
if len(sys.argv) > 1 and sys.argv[1] == 'test':
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']  # testes mais rapidos
LOGIN_URL = '/entrar/'
LOGIN_REDIRECT_URL = '/'
# Se preenchido, o campo "prefeitura" do login vem escondido (implantacao de uma prefeitura so).
MUNICIPIO_PADRAO_SLUG = os.environ.get('MUNICIPIO_PADRAO_SLUG', '')

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# --- Idioma e fuso ----------------------------------------------------------
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# --- Arquivos ---------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'  # em producao: armazenamento compativel com S3
ANEXO_TAMANHO_MAXIMO = 20 * 1024 * 1024
