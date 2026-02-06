from django.contrib.auth.mixins import AccessMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy

# =========================================================
# 1. LÓGICA DE PERMISOS (HÍBRIDA Y ROBUSTA)
# =========================================================

def _tiene_grupo(user, grupos):
    """Helper interno para verificar grupos por nombre exacto."""
    if not user: 
        return False
    if not getattr(user, "is_authenticated", False):
        return False
        
    if user.is_superuser: 
        return True
        
    return user.groups.filter(name__in=grupos).exists()

# --- FUNCIONES DE ROL (Actualizadas) ---

def es_admin_sistema(user):
    # Incluye Superusers y Admins viejos
    return _tiene_grupo(user, ["ADMIN_SISTEMA", "ADMIN"])

def es_staff_finanzas(user):
    # Agregamos "Finanzas" aquí para que tengan poder total
    return _tiene_grupo(user, ["Finanzas", "STAFF_FINANZAS", "TESORERIA", "SECRETARIA"])

def es_operador_finanzas(user):
    # Agregamos "Finanzas" aquí también
    return _tiene_grupo(user, ["Finanzas", "OPERADOR_FINANZAS", "CAJA", "STAFF_FINANZAS", "ADMIN_SISTEMA"])

def es_operador_social(user):
    # AQUÍ ESTÁ LA CLAVE: Agregamos "Social", "Social Administración" y "GENEROYNIÑEZ"
    # Esto permite que Género acceda a la ficha básica de la persona
    grupos_permitidos = [
        "Social", 
        "Social Administración", 
        "GENEROYNIÑEZ",
        "OPERADOR_SOCIAL", 
        "MESA_ENTRADA", 
        "STAFF_FINANZAS", 
        "ADMIN_SISTEMA"
    ]
    return _tiene_grupo(user, grupos_permitidos)

def es_equipo_genero(user):
    # NUEVO: Función específica para detectar al equipo sensible
    return _tiene_grupo(user, ["GENEROYNIÑEZ", "ADMIN_SISTEMA"])

def es_consulta_politica(user):
    # RESTAURADO: Necesario para que no falle la Agenda
    return _tiene_grupo(user, ["CONSULTA_POLITICA", "STAFF_FINANZAS", "ADMIN_SISTEMA"])

# --- FUNCIONES DE PRIVACIDAD (DINERO) ---

def puede_ver_historial_economico(user):
    """
    Regla de privacidad CRÍTICA: 
    Solo ven montos ($) el grupo 'Finanzas' o los Superusuarios.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    # Solo estos grupos ven plata. Social y Género NO están aquí.
    grupos_dinero = ["Finanzas", "STAFF_FINANZAS", "TESORERIA", "ADMIN_SISTEMA"]
    return user.groups.filter(name__in=grupos_dinero).exists()

# =========================================================
# 2. MIXINS DE PROTECCIÓN DE VISTAS
# =========================================================

class BaseRolMixin(AccessMixin):
    permission_denied_message = "⛔ No tienes permisos para esta sección."

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
            # Redirigir al home evita bucles de redirección
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
        # Esto ahora permite pasar a "Social Administración" y "Género"
        if not es_operador_social(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class GeneroRequiredMixin(BaseRolMixin):
    """
    NUEVO: Solo permite acceso al equipo de Género y Niñez para subir archivos.
    """
    def dispatch(self, request, *args, **kwargs):
        if not es_equipo_genero(request.user):
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
        # Permite entrar a Social, Género y Finanzas
        if not (es_operador_social(request.user) or es_operador_finanzas(request.user)):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class PersonaCensoEditMixin(OperadorSocialRequiredMixin): 
    """Permite editar/crear personas y atenciones."""
    pass 

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
# 3. CONTEXT PROCESSOR (Inyección en Templates)
# =========================================================

def roles_ctx(context_input):
    """
    Inyecta variables en todos los templates HTML.
    """
    user = None
    if hasattr(context_input, 'user'):
        user = context_input.user
    else:
        user = context_input

    return {
        # Variable maestra para ocultar/mostrar dinero en el HTML
        'perms_ver_dinero': puede_ver_historial_economico(user),
        
        # Roles booleanos para lógica condicional en menús
        'es_admin_sistema': es_admin_sistema(user),
        'es_staff_finanzas': es_staff_finanzas(user),
        'es_operador_finanzas': es_operador_finanzas(user),
        'es_operador_social': es_operador_social(user), # True para Social, Social Admin y Género
        
        # NUEVO: Para mostrar la pestaña roja
        'es_equipo_genero': es_equipo_genero(user),
        
        # Alias viejos
        'rol_staff_finanzas': es_staff_finanzas(user),
        'rol_operador_finanzas': es_operador_finanzas(user),
        'rol_operador_social': es_operador_social(user),
    }