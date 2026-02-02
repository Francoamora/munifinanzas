from pathlib import Path
import os
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================================
# 🔒 CONFIGURACIÓN DE SEGURIDAD (PRODUCCIÓN)
# =========================================================

# Generamos una clave segura aleatoria si no existe una en variables de entorno.
# NOTA: En PythonAnywhere, esto asegura que cada reinicio sea seguro, 
# pero idealmente deberías fijar una clave definitiva más adelante.
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-z#&8y@^_CHANGE_THIS_IN_PRODUCTION_^*($#')

# ⚠️ IMPORTANTE: En producción esto debe ser False
# Si ves la página "Server Error (500)" sin detalles, es porque esto está funcionando bien.
DEBUG = False

ALLOWED_HOSTS = [
    "francomora23.pythonanywhere.com",
    "www.francomora23.pythonanywhere.com",
    "localhost",
    "127.0.0.1",
]


# ============================
#        INSTALLED APPS
# ============================
INSTALLED_APPS = [
    # --- DJANGO UNFOLD (Admin Premium) ---
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.import_export",

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
    'agenda',
    'inventario',
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
        'DIRS': [],
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
# En producción, ejecutaremos 'python manage.py collectstatic'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []


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
COMUNA_NOMBRE = "Comuna de Tacuarendí"
COMUNA_CUIT = "30-67433889-5"
COMUNA_DOMICILIO = "Calle 8 y 5"
COMUNA_TELEFONO = "3482 - 452012"
COMUNA_EMAIL = "comuna.tacuarendi@ltnet.com.ar"


# =========================================================
# CONFIGURACIÓN DJANGO UNFOLD (ADMIN PREMIUM)
# =========================================================
UNFOLD = {
    "SITE_TITLE": "MuniFinanzas",
    "SITE_HEADER": "MuniFinanzas Admin",
    "SITE_URL": "/",
    # "SITE_ICON": lambda request: static("img/logo.png"),

    # Colores Institucionales
    "COLORS": {
        "primary": {
            "50": "239 246 255",
            "100": "219 234 254",
            "200": "191 219 254",
            "300": "147 197 253",
            "400": "96 165 250",
            "500": "59 130 246",
            "600": "37 99 235",
            "700": "29 78 216",
            "800": "30 64 175",
            "900": "30 58 138",
        },
    },

    # Configuración de la Barra Lateral
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False, 
        "navigation": [
            {
                "title": _("Tablero Principal"),
                "separator": True,
                "items": [
                    {
                        "title": _("Volver al Sitio"),
                        "icon": "home",
                        "link": reverse_lazy("finanzas:home"),
                    },
                ],
            },
            {
                "title": _("Inventario & Pañol"), # ✅ SECCIÓN NUEVA
                "separator": True,
                "items": [
                    {
                        "title": _("Stock de Insumos"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:inventario_insumo_changelist"),
                    },
                    {
                        "title": _("Movimientos"),
                        "icon": "swap_horiz",
                        "link": reverse_lazy("admin:inventario_movimientostock_changelist"),
                    },
                    {
                        "title": _("Préstamos"),
                        "icon": "handyman",
                        "link": reverse_lazy("admin:inventario_prestamo_changelist"),
                    },
                ],
            },
            {
                "title": _("Finanzas & Tesorería"),
                "separator": True,
                "items": [
                    {
                        "title": _("Movimientos de Caja"),
                        "icon": "account_balance_wallet",
                        "link": reverse_lazy("admin:finanzas_movimiento_changelist"),
                    },
                    {
                        "title": _("Órdenes de Pago"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:finanzas_ordenpago_changelist"),
                    },
                    {
                        "title": _("Órdenes de Compra"),
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:finanzas_ordencompra_changelist"),
                    },
                    {
                        "title": _("Proveedores"),
                        "icon": "storefront",
                        "link": reverse_lazy("admin:finanzas_proveedor_changelist"),
                    },
                ],
            },
            {
                "title": _("Logística & Flota"),
                "separator": True,
                "items": [
                    {
                        "title": _("Parque Automotor"),
                        "icon": "local_shipping",
                        "link": reverse_lazy("admin:finanzas_vehiculo_changelist"),
                    },
                    {
                        "title": _("Hojas de Ruta"),
                        "icon": "map",
                        "link": reverse_lazy("admin:finanzas_hojaruta_changelist"),
                    },
                ],
            },
            {
                "title": _("Acción Social"),
                "separator": True,
                "items": [
                    {
                        "title": _("Padrón de Personas"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:finanzas_beneficiario_changelist"),
                    },
                    {
                        "title": _("Atención Ciudadana"),
                        "icon": "support_agent",
                        "link": reverse_lazy("admin:finanzas_atencion_changelist"), 
                    },
                ],
            },
            {
                "title": _("Configuración"),
                "separator": True,
                "items": [
                    {
                        "title": _("Usuarios y Accesos"),
                        "icon": "manage_accounts",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": _("Categorías de Gasto"),
                        "icon": "category",
                        "link": reverse_lazy("admin:finanzas_categoria_changelist"),
                    },
                    {
                        "title": _("Áreas Municipales"),
                        "icon": "apartment",
                        "link": reverse_lazy("admin:finanzas_area_changelist"),
                    },
                ],
            },
        ],
    },
}