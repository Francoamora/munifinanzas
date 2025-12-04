# finanzas/context_processors.py
from django.conf import settings

from . import permisos


def roles_ctx(request):
    """
    Expone flags de rol para usarlos en cualquier template:
      - rol_*  -> nombres pensados para el header/menú (compatibilidad)
      - es_*   -> nombres pensados para lógica de negocio en templates

    Así todo el proyecto usa la misma lógica central definida en finanzas.permisos.
    """
    user = request.user

    # Calculamos una sola vez
    es_admin = permisos.es_admin_sistema(user)
    es_staff_fin = permisos.es_staff_finanzas(user)
    es_op_fin = permisos.es_operador_finanzas(user)
    es_op_soc = permisos.es_operador_social(user)
    es_consulta = permisos.es_consulta_politica(user)
    es_fin = permisos.es_finanzas(user)

    return {
        # Nombres nuevos (más claros)
        "es_admin_sistema": es_admin,
        "es_staff_finanzas": es_staff_fin,
        "es_operador_finanzas": es_op_fin,
        "es_operador_social": es_op_soc,
        "es_consulta_politica": es_consulta,
        "es_finanzas": es_fin,

        # Compatibilidad con lo que ya venías usando en algunos templates
        "rol_staff_finanzas": es_staff_fin,
        "rol_operador_finanzas": es_op_fin,
        "rol_operador_social": es_op_soc,
        "rol_consulta_politica": es_consulta,
    }


def comuna_ctx(request):
    """
    Expone datos fijos de la Comuna para usarlos en cualquier template:
    encabezados de impresiones, PDFs, etc.
    """
    return {
        "COMUNA_NOMBRE": getattr(settings, "COMUNA_NOMBRE", "Comuna de Tacuarendí"),
        "COMUNA_CUIT": getattr(settings, "COMUNA_CUIT", ""),
        "COMUNA_DOMICILIO": getattr(settings, "COMUNA_DOMICILIO", ""),
        "COMUNA_TELEFONO": getattr(settings, "COMUNA_TELEFONO", ""),
        "COMUNA_EMAIL": getattr(settings, "COMUNA_EMAIL", ""),
    }
