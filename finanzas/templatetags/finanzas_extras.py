from decimal import Decimal, InvalidOperation
from django import template
from django.utils import formats

register = template.Library()

# ============================================================
#   MATEMÁTICAS (NUEVO: Para arreglar el error del template)
# ============================================================

@register.filter
def div(value, arg):
    """
    Divide el valor por el argumento.
    Uso: {{ valor|div:divisor }}
    """
    try:
        val = float(value)
        divisor = float(arg)
        if divisor == 0:
            return 0
        return val / divisor
    except (ValueError, TypeError, InvalidOperation):
        return 0

@register.filter
def mul(value, arg):
    """
    Multiplica el valor por el argumento.
    Uso: {{ valor|mul:factor }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError, InvalidOperation):
        return 0

@register.filter
def sub(value, arg):
    """
    Resta el argumento al valor.
    Uso: {{ valor|sub:sustraendo }}
    """
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError, InvalidOperation):
        return 0

# ============================================================
#   NÚMEROS / PESOS
# ============================================================

@register.filter
def formato_pesos(value, decimals=2):
    """
    Formatea números como pesos argentinos usando localización de Django.
    """
    if value is None or value == "":
        return "0,00"

    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

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
    Formato forzado estilo AR (puntos para miles, coma para decimales).
    """
    if value is None or value == "":
        value = 0

    try:
        num = float(value)
    except (TypeError, ValueError):
        return value

    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2

    base = f"{num:,.{decimals}f}"
    return base.replace(",", "X").replace(".", ",").replace("X", ".")

# ============================================================
#   ROLES / GRUPOS
# ============================================================

def _user_in_groups(user, group_names):
    if not getattr(user, "is_authenticated", False):
        return False
    if not group_names:
        return False
    return user.groups.filter(name__in=group_names).exists()

@register.filter(name="has_group")
def has_group(user, group_name):
    if not group_name:
        return False
    return _user_in_groups(user, [group_name])

@register.filter(name="tiene_rol")
def tiene_rol(user, rol_codigo):
    if not rol_codigo:
        return False

    rol = (rol_codigo or "").upper().strip()

    mapping = {
        "ADMIN_SISTEMA": ["ADMIN_SISTEMA"],
        "STAFF_FINANZAS": ["STAFF_FINANZAS"],
        "OPERADOR_FINANZAS": ["OPERADOR_FINANZAS"],
        "OPERADOR_SOCIAL": ["OPERADOR_SOCIAL"],
        "CONSULTA_POLITICA": ["CONSULTA_POLITICA"],
    }

    grupos = mapping.get(rol, [rol])
    return _user_in_groups(user, grupos)