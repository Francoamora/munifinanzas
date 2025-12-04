# finanzas/permisos.py
from typing import Any

from django.contrib.auth.models import Group


# ============================
#   NOMBRES DE ROLES (GRUPOS)
# ============================

ROL_ADMIN_SISTEMA = "ADMIN_SISTEMA"
ROL_STAFF_FINANZAS = "STAFF_FINANZAS"
ROL_OPERADOR_FINANZAS = "OPERADOR_FINANZAS"
ROL_OPERADOR_SOCIAL = "OPERADOR_SOCIAL"
ROL_CONSULTA_POLITICA = "CONSULTA_POLITICA"


# ============================
#   HELPERS INTERNOS
# ============================

def _en_grupo(user: Any, nombre_grupo: str) -> bool:
    """
    Devuelve True si el usuario está en el grupo dado.
    Si no está autenticado, siempre False.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name=nombre_grupo).exists()


# ============================
#   FUNCIONES DE ROL
# ============================

def es_admin_sistema(user: Any) -> bool:
    """
    Admin del sistema:
      - superuser
      - o usuario en el grupo ADMIN_SISTEMA
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return _en_grupo(user, ROL_ADMIN_SISTEMA)


def es_staff_finanzas(user: Any) -> bool:
    """
    Staff de finanzas:
      - superuser
      - o grupo STAFF_FINANZAS
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return _en_grupo(user, ROL_STAFF_FINANZAS)


def es_operador_finanzas(user: Any) -> bool:
    """
    Operador de finanzas:
      - superuser
      - grupo OPERADOR_FINANZAS
      - o STAFF_FINANZAS / ADMIN_SISTEMA
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    return any([
        _en_grupo(user, ROL_OPERADOR_FINANZAS),
        _en_grupo(user, ROL_STAFF_FINANZAS),
        _en_grupo(user, ROL_ADMIN_SISTEMA),
    ])


def es_operador_social(user: Any) -> bool:
    """
    Operador social:
      - grupo OPERADOR_SOCIAL
      - (opcional) también STAFF_FINANZAS / ADMIN_SISTEMA
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        # Podés elegir si el superuser cuenta como operador social o no.
        return True

    return any([
        _en_grupo(user, ROL_OPERADOR_SOCIAL),
        _en_grupo(user, ROL_STAFF_FINANZAS),
        _en_grupo(user, ROL_ADMIN_SISTEMA),
    ])


def es_consulta_politica(user: Any) -> bool:
    """
    Rol de lectura política:
      - grupo CONSULTA_POLITICA
      - (opcional) también STAFF_FINANZAS / ADMIN_SISTEMA
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    return any([
        _en_grupo(user, ROL_CONSULTA_POLITICA),
        _en_grupo(user, ROL_STAFF_FINANZAS),
        _en_grupo(user, ROL_ADMIN_SISTEMA),
    ])


def es_finanzas(user: Any) -> bool:
    """
    Rol amplio de finanzas:
      Cualquiera que esté en ADMIN_SISTEMA, STAFF_FINANZAS u OPERADOR_FINANZAS
      (o sea superuser).
    """
    if not getattr(user, "is_authenticated", False):
        return False

    return any([
        es_admin_sistema(user),
        es_staff_finanzas(user),
        es_operador_finanzas(user),
    ])


# ============================
#   SETUP DE GRUPOS
# ============================

def ensure_default_groups():
    """
    Crea los grupos por defecto si no existen.
    Podés llamarla desde un comando de management o desde el shell:

        from finanzas.permisos import ensure_default_groups
        ensure_default_groups()
    """
    for name in [
        ROL_ADMIN_SISTEMA,
        ROL_STAFF_FINANZAS,
        ROL_OPERADOR_FINANZAS,
        ROL_OPERADOR_SOCIAL,
        ROL_CONSULTA_POLITICA,
    ]:
        Group.objects.get_or_create(name=name)
