from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy

# =========================================================
# 1. LÓGICA DE PERMISOS (HÍBRIDA Y ROBUSTA)
# =========================================================

def _tiene_grupo(user, grupos):
    """Helper interno para verificar grupos."""
    # Validación de seguridad: si user es None o no es un objeto válido
    if not user: 
        return False
    # Validación de autenticación (AnonymousUser)
    if not getattr(user, "is_authenticated", False):
        return False
        
    if user.is_superuser: 
        return True
        
    return user.groups.filter(name__in=grupos).exists()

# --- FUNCIONES DE ROL (Compatibles) ---

def es_admin_sistema(user):
    return _tiene_grupo(user, ["ADMIN_SISTEMA", "ADMIN"])

def es_staff_finanzas(user):
    return _tiene_grupo(user, ["STAFF_FINANZAS", "TESORERIA", "SECRETARIA"])

def es_operador_finanzas(user):
    return _tiene_grupo(user, ["OPERADOR_FINANZAS", "CAJA", "STAFF_FINANZAS", "ADMIN_SISTEMA"])

def es_operador_social(user):
    return _tiene_grupo(user, ["OPERADOR_SOCIAL", "SOCIAL", "MESA_ENTRADA", "STAFF_FINANZAS", "ADMIN_SISTEMA"])

def es_consulta_politica(user):
    return _tiene_grupo(user, ["CONSULTA_POLITICA", "STAFF_FINANZAS", "ADMIN_SISTEMA"])

def es_finanzas(user):
    return es_admin_sistema(user) or es_staff_finanzas(user) or es_operador_finanzas(user) or es_consulta_politica(user)

# --- FUNCIONES NUEVAS (Privacidad) ---

def puede_ver_historial_economico(user):
    """Regla de privacidad: Solo Admin y Staff ven montos ($)"""
    return es_admin_sistema(user) or es_staff_finanzas(user)

# =========================================================
# 2. MIXINS DE PROTECCIÓN DE VISTAS
# =========================================================

class BaseRolMixin(AccessMixin):
    permission_denied_message = "⛔ No tienes permisos para esta sección."

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
            return redirect("finanzas:home")
        return super().handle_no_permission()

# --- Mixins Específicos ---

class StaffRequiredMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not (es_staff_finanzas(request.user) or es_admin_sistema(request.user)):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class OperadorFinanzasRequiredMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not es_operador_finanzas(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class OperadorSocialRequiredMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not es_operador_social(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

# --- Mixins Alias (Compatibilidad Legacy) ---

class MovimientosAccessMixin(OperadorFinanzasRequiredMixin): pass
class OrdenPagoAccessMixin(OperadorFinanzasRequiredMixin): pass
class OrdenPagoEditMixin(StaffRequiredMixin): pass

class DashboardAccessMixin(BaseRolMixin): 
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class PersonaCensoAccessMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not (es_operador_social(request.user) or es_operador_finanzas(request.user)):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class PersonaCensoEditMixin(OperadorSocialRequiredMixin): pass 

class FlotaAccessMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not (es_operador_finanzas(request.user) or es_operador_social(request.user)):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class FlotaEditMixin(OperadorFinanzasRequiredMixin): pass
class SoloFinanzasMixin(OperadorFinanzasRequiredMixin): pass
class OrdenTrabajoAccessMixin(OperadorFinanzasRequiredMixin): pass 
class OrdenTrabajoEditMixin(OperadorFinanzasRequiredMixin): pass

# =========================================================
# 3. CONTEXT PROCESSOR (Blindado)
# =========================================================

def roles_ctx(context_input):
    """
    Inyecta variables en templates. 
    Es inteligente: detecta si recibe un 'request' o un 'user' directo.
    """
    user = None
    
    # Detección automática del tipo de input
    if hasattr(context_input, 'user'):
        # Es un objeto Request
        user = context_input.user
    else:
        # Asumimos que es un objeto User (o AnonymousUser)
        user = context_input

    # Diccionario seguro de permisos
    return {
        # Lógica Nueva (Ocultar dinero)
        'perms_ver_dinero': puede_ver_historial_economico(user),
        
        # Compatibilidad Legacy
        'es_admin_sistema': es_admin_sistema(user),
        'es_staff_finanzas': es_staff_finanzas(user),
        'es_operador_finanzas': es_operador_finanzas(user),
        'es_operador_social': es_operador_social(user),
        'es_consulta_politica': es_consulta_politica(user),
        
        # Alias viejos
        'rol_staff_finanzas': es_staff_finanzas(user),
        'rol_operador_finanzas': es_operador_finanzas(user),
        'rol_operador_social': es_operador_social(user),
    }