# finanzas/permisos.py
from typing import Any
from django.contrib.auth.models import Group

# ============================
#   DEFINICIÓN DE GRUPOS
# ============================
ROL_ADMIN_SISTEMA = "ADMIN_SISTEMA"       # Acceso Total
ROL_STAFF_FINANZAS = "STAFF_FINANZAS"     # Tesorero / Secretario (Aprueba)
ROL_OPERADOR_FINANZAS = "OPERADOR_FINANZAS" # Administrativo (Carga facturas/OC)
ROL_OPERADOR_SOCIAL = "OPERADOR_SOCIAL"   # Mesa Entrada (Carga reclamos/personas)
ROL_CONSULTA = "CONSULTA_POLITICA"        # Solo ve tableros

# ============================
#   HELPERS INTERNOS
# ============================
def _en_grupo(user: Any, grupos: list) -> bool:
    """Verifica si el usuario está en ALGUNO de los grupos de la lista."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=grupos).exists()

# ============================
#   REGLAS DE NEGOCIO
# ============================

def es_admin_total(user):
    """Dueño del sistema o Secretario de Hacienda."""
    return _en_grupo(user, [ROL_ADMIN_SISTEMA, ROL_STAFF_FINANZAS])

def es_operador_finanzas(user):
    """Puede cargar Movimientos, OCs y Viajes."""
    return _en_grupo(user, [ROL_OPERADOR_FINANZAS, ROL_STAFF_FINANZAS, ROL_ADMIN_SISTEMA])

def es_operador_social(user):
    """Puede cargar Atenciones, Personas, OTs y Viajes."""
    return _en_grupo(user, [ROL_OPERADOR_SOCIAL, ROL_STAFF_FINANZAS, ROL_ADMIN_SISTEMA])

def tiene_acceso_flota(user):
    """Choferes o encargados que solo ven logística."""
    return es_operador_finanzas(user) or es_operador_social(user)

# === REGLA DE ORO: PRIVACIDAD ===
def puede_ver_historial_economico(user):
    """
    Define quién puede ver la pestaña 'Ayudas Económicas' y los montos ($)
    en la ficha de una persona.
    SOLO: Admin y Staff (Jefes). Los operadores NO ven esto.
    """
    if not getattr(user, "is_authenticated", False): return False
    # Solo superusuario o Staff Finanzas (Jefes) ven la plata sensible
    return user.is_superuser or user.groups.filter(name__in=[ROL_ADMIN_SISTEMA, ROL_STAFF_FINANZAS]).exists()

# ============================
#   INIT (Para crear grupos)
# ============================
def ensure_default_groups():
    """Ejecutar una vez para crear los grupos en la DB."""
    nombres = [ROL_ADMIN_SISTEMA, ROL_STAFF_FINANZAS, ROL_OPERADOR_FINANZAS, ROL_OPERADOR_SOCIAL, ROL_CONSULTA]
    for n in nombres:
        Group.objects.get_or_create(name=n)