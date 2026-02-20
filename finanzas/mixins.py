from django.contrib.auth.mixins import AccessMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy

# =========================================================
# 1. LÓGICA DE PERMISOS (BLINDADA Y ANTI-ERRORES DE TYPOS)
# =========================================================

def _tiene_grupo(user, grupos):
    """Verifica grupos ignorando mayúsculas, minúsculas y espacios extra."""
    if not user or not getattr(user, "is_authenticated", False): 
        return False
    if getattr(user, "is_superuser", False): 
        return True
    
    # 1. Obtenemos los grupos del usuario (todo minúscula y sin espacios)
    user_groups = [g.name.lower().strip() for g in user.groups.all()]
    # 2. Limpiamos también los grupos que estamos buscando
    target_groups = [g.lower().strip() for g in grupos]
    # 3. Comprobamos si alguno coincide
    return any(g in user_groups for g in target_groups)

# --- FUNCIONES DE ROL (Viejas mantenidas + Nuevos Grupos inyectados) ---

def es_admin_sistema(user):
    return _tiene_grupo(user, ["ADMIN_SISTEMA", "ADMIN"])

def es_staff_finanzas(user):
    return _tiene_grupo(user, ["Finanzas", "STAFF_FINANZAS", "TESORERIA", "SECRETARIA"])

def es_operador_finanzas(user):
    # INYECTADO: "Carga de Datos" y "Administración Desarrollo Social"
    grupos_permitidos = [
        "Finanzas", "OPERADOR_FINANZAS", "CAJA", "STAFF_FINANZAS", "ADMIN_SISTEMA",
        "Carga de Datos", "Administración Desarrollo Social", "Administracion Desarrollo Social"
    ]
    return _tiene_grupo(user, grupos_permitidos)

def es_operador_social(user):
    # INYECTADO: "Carga de Datos" para que puedan cargar personas si lo necesitan
    grupos_permitidos = [
        "Social", 
        "Social Administración", 
        "Administración Desarrollo Social",
        "Administracion Desarrollo Social",
        "GENEROYNIÑEZ",
        "Género y Niñez",
        "Carga de Datos",
        "OPERADOR_SOCIAL", 
        "MESA_ENTRADA", 
        "STAFF_FINANZAS", 
        "ADMIN_SISTEMA"
    ]
    return _tiene_grupo(user, grupos_permitidos)

def es_equipo_genero(user):
    return _tiene_grupo(user, ["GENEROYNIÑEZ", "Género y Niñez", "ADMIN_SISTEMA"])

def es_consulta_politica(user):
    return _tiene_grupo(user, ["CONSULTA_POLITICA", "STAFF_FINANZAS", "ADMIN_SISTEMA"])


# --- FUNCIONES DE PRIVACIDAD (DINERO DIVIDIDO EN 2 NIVELES) ---

def puede_ver_dinero_global(user):
    """NIVEL 1: Plata Grande. Solo Finanzas."""
    if not user or not user.is_authenticated: return False
    if user.is_superuser: return True
    grupos_dinero = ["Finanzas", "STAFF_FINANZAS", "TESORERIA", "ADMIN_SISTEMA"]
    return _tiene_grupo(user, grupos_dinero)

def puede_ver_dinero_social(user):
    """NIVEL 2: Plata de Vecinos. Finanzas y Admin Desarrollo Social."""
    if not user or not user.is_authenticated: return False
    if user.is_superuser: return True
    grupos_social = [
        "Finanzas", "STAFF_FINANZAS", "TESORERIA", "ADMIN_SISTEMA",
        "Administración Desarrollo Social", "Administracion Desarrollo Social", "Social", "Social Administración"
    ]
    return _tiene_grupo(user, grupos_social)

def puede_ver_historial_economico(user):
    return puede_ver_dinero_global(user)


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

# --- Mixins Específicos NUEVOS Y BLINDADOS ---

class SoloFinanzasMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not puede_ver_dinero_global(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class OperadorOperativoRequiredMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not es_operador_finanzas(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class StaffRequiredMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not (es_staff_finanzas(request.user) or es_admin_sistema(request.user)):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class OperadorFinanzasRequiredMixin(OperadorOperativoRequiredMixin):
    pass # Alias para mantener compatibilidad con vistas viejas

class OperadorSocialRequiredMixin(BaseRolMixin):
    def dispatch(self, request, *args, **kwargs):
        if not es_operador_social(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class GeneroRequiredMixin(BaseRolMixin):
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
class OrdenTrabajoAccessMixin(OperadorFinanzasRequiredMixin): pass 
class OrdenTrabajoEditMixin(OperadorFinanzasRequiredMixin): pass

# =========================================================
# 3. CONTEXT PROCESSOR (Inyección en Templates)
# =========================================================

def roles_ctx(context_input):
    """
    Inyecta variables en todos los templates HTML.
    """
    user = context_input.user if hasattr(context_input, 'user') else context_input

    return {
        # === LAS LLAVES MAESTRAS NUEVAS (Esto soluciona el problema) ===
        'perms_operar_operativo': es_operador_finanzas(user),
        'perms_operar_social': es_operador_social(user),
        'perms_ver_dinero_global': puede_ver_dinero_global(user), 
        'perms_ver_dinero_social': puede_ver_dinero_social(user), 
        
        # === VARIABLES VIEJAS MANTENIDAS (Para no romper nada más) ===
        'perms_ver_dinero': puede_ver_historial_economico(user),
        'es_admin_sistema': es_admin_sistema(user),
        'es_staff_finanzas': es_staff_finanzas(user),
        'es_operador_finanzas': es_operador_finanzas(user),
        'es_operador_social': es_operador_social(user),
        'es_equipo_genero': es_equipo_genero(user),
        'rol_staff_finanzas': es_staff_finanzas(user),
        'rol_operador_finanzas': es_operador_finanzas(user),
        'rol_operador_social': es_operador_social(user),
    }

# =========================================================
# MIXINS DE ESTILO Y FORMULARIOS
# =========================================================
from django import forms

class EstiloFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            attrs = field.widget.attrs
            clase_actual = attrs.get('class', '')

            if isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in clase_actual:
                    attrs['class'] = f"{clase_actual} form-check-input".strip()
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                if 'form-select' not in clase_actual:
                    attrs['class'] = f"{clase_actual} form-select".strip()
            elif isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.DateInput, forms.PasswordInput)):
                if 'form-control' not in clase_actual:
                    attrs['class'] = f"{clase_actual} form-control".strip()