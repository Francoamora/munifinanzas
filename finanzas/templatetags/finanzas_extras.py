from decimal import Decimal, InvalidOperation

from django import template
from django.utils import formats
from django.contrib.auth.models import Group

register = template.Library()


@register.filter
def formato_pesos(value):
    """
    Formatea números como pesos argentinos usando la localización (es-ar):
    - Separador de miles: punto
    - Separador decimal: coma
    - Siempre 2 decimales
    Ejemplo: 570050000 -> '570.050.000,00'
    """
    if value is None or value == "":
        return "0,00"

    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        # Si no se puede convertir, lo devolvemos tal cual (evita romper la template)
        return value

    return formats.number_format(
        value,
        decimal_pos=2,
        use_l10n=True,
        force_grouping=True,
    )


def _user_in_groups(user, group_names):
    """
    Helper interno: verifica si el usuario pertenece a alguno
    de los grupos indicados.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if not group_names:
        return False
    return user.groups.filter(name__in=group_names).exists()


@register.filter(name="has_group")
def has_group(user, group_name):
    """
    Uso en templates:
      {% if request.user|has_group:"STAFF_FINANZAS" %}
        ...
      {% endif %}
    """
    if not group_name:
        return False
    return _user_in_groups(user, [group_name])


@register.filter(name="tiene_rol")
def tiene_rol(user, rol_codigo):
    """
    Helper de roles lógico para el sistema de finanzas.

    Pensado para trabajar con estos nombres de grupo:
      - ADMIN_SISTEMA
      - STAFF_FINANZAS
      - OPERADOR_FINANZAS
      - OPERADOR_SOCIAL
      - CONSULTA_POLITICA

    Uso en templates:
      {% if request.user|tiene_rol:"STAFF_FINANZAS" %}
      {% if request.user|tiene_rol:"OPERADOR_SOCIAL" %}
      {% if request.user|tiene_rol:"CONSULTA_POLITICA" %}
    """
    if not rol_codigo:
        return False

    rol = (rol_codigo or "").upper().strip()

    # Mapeo simple por ahora: un rol = un grupo.
    # Si más adelante querés mapear varios grupos a un solo rol lógico,
    # se extiende este diccionario.
    mapping = {
        "ADMIN_SISTEMA": ["ADMIN_SISTEMA"],
        "STAFF_FINANZAS": ["STAFF_FINANZAS"],
        "OPERADOR_FINANZAS": ["OPERADOR_FINANZAS"],
        "OPERADOR_SOCIAL": ["OPERADOR_SOCIAL"],
        "CONSULTA_POLITICA": ["CONSULTA_POLITICA"],
    }

    grupos = mapping.get(rol, [rol])
    return _user_in_groups(user, grupos)
