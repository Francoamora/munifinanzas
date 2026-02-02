from django.conf import settings
from .mixins import roles_ctx as get_roles_ctx

def roles_ctx(request):
    """
    Disponible en todos los templates.
    Permite usar {% if rol_staff_finanzas %}...{% endif %} en el navbar/sidebar.
    """
    if request.user.is_authenticated:
        return get_roles_ctx(request.user)
    return {}

def comuna_ctx(request):
    """
    Datos de la institución para encabezados e impresiones.
    """
    return {
        "COMUNA_NOMBRE": getattr(settings, "COMUNA_NOMBRE", "Comuna de Tacuarendí"),
        "COMUNA_CUIT": getattr(settings, "COMUNA_CUIT", ""),
        "COMUNA_TELEFONO": getattr(settings, "COMUNA_TELEFONO", ""),
        "COMUNA_EMAIL": getattr(settings, "COMUNA_EMAIL", ""),
        "COMUNA_DIRECCION": getattr(settings, "COMUNA_DOMICILIO", ""),
    }