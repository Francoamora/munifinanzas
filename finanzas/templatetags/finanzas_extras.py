from decimal import Decimal, InvalidOperation

from django import template
from django.utils import formats

register = template.Library()


# ============================================================
#   NÚMEROS / PESOS
# ============================================================

@register.filter
def formato_pesos(value, decimals=2):
    """
    Formatea números como pesos argentinos aprovechando la localización
    de Django (por ejemplo es-ar si está configurado):

    - Separador de miles según locale (en es-ar: punto)
    - Separador decimal según locale (en es-ar: coma)
    - `decimals` decimales (por defecto, 2)

    Ejemplo (con locale es-ar):
      570050000 -> '570.050.000,00'
    """
    if value is None or value == "":
        # Mantengo el comportamiento anterior
        return "0,00"

    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        # Si no se puede convertir, lo devolvemos tal cual (evita romper la template)
        return value

    # Permite sobreescribir la cantidad de decimales desde la template:
    # {{ monto|formato_pesos:"0" }}
    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2

    return formats.number_format(
        value,
        decimal_pos=decimals,
        use_l10n=True,
        force_grouping=True,
    )


@register.filter
def pesos_ar(value, decimals=2):
    """
    Formato de número estilo AR fijo, independiente del locale de Django.

    - Separador de miles: punto
    - Separador decimal: coma
    - `decimals` decimales (por defecto, 2)

    Ejemplos:
      41000        -> '41.000,00'
      1234.5       -> '1.234,50'
      {{ monto|pesos_ar }}         # 2 decimales
      {{ km|pesos_ar:"1" }}        # 1 decimal
    """
    if value is None or value == "":
        value = 0

    try:
        num = float(value)
    except (TypeError, ValueError):
        # Si no es número, lo devolvemos tal cual
        return value

    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2

    # Primero formateo en estilo US: 41,000.00
    base = f"{num:,.{decimals}f}"
    # Después intercambio separadores: 41.000,00
    return base.replace(",", "X").replace(".", ",").replace("X", ".")


# ============================================================
#   ROLES / GRUPOS
# ============================================================

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
