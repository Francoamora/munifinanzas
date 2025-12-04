# muni_finanzas/settings.py
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# ⚠️ Cambiar en producción
SECRET_KEY = 'django-insecure-muni-finanzas-demo-secret-key'
DEBUG = True

ALLOWED_HOSTS: list[str] = []


# ============================
#        INSTALLED APPS
# ============================
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Utilidades
    'django.contrib.humanize',

    # Apps del proyecto
    'finanzas',
    'agenda',  # ✅ ya existe, la activamos
]


# ============================
#        MIDDLEWARE
# ============================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'muni_finanzas.urls'


# ============================
#        TEMPLATES
# ============================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],   # agregar DIRS si querés templates globales
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',

                # ✅ Context processors propios del proyecto
                'finanzas.context_processors.roles_ctx',
                'finanzas.context_processors.comuna_ctx',
            ],
        },
    },
]


WSGI_APPLICATION = 'muni_finanzas.wsgi.application'


# ============================
#        BASE DE DATOS
# ============================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ============================
#   VALIDADORES DE PASSWORD
# ============================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ============================
#       REGIONAL
# ============================
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Cordoba'
USE_I18N = True
USE_TZ = True


# ============================
#       ARCHIVOS ESTÁTICOS
# ============================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS: list[Path] = []


# ============================
#     ARCHIVOS SUBIDOS
# ============================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================
#          LOGIN / LOGOUT
# ============================
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "finanzas:home"
LOGOUT_REDIRECT_URL = "login"


# ============================
#       DATOS DE LA COMUNA
# ============================
# Estos datos quedan disponibles vía context processor (COMUNA_*),
# para usarlos en encabezados, impresiones, PDFs, etc.
COMUNA_NOMBRE = "Comuna de Tacuarendí"
COMUNA_CUIT = "30-67433889-5"
COMUNA_DOMICILIO = "Calle 8 y 5"
COMUNA_TELEFONO = "3482 - 452012"
COMUNA_EMAIL = "comuna.tacuarendi@ltnet.com.ar"
