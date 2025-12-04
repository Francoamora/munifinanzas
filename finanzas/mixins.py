# finanzas/mixins.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse_lazy

from . import permisos


class BaseRolMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Base para todos los mixins de roles.

    - Obliga a que el usuario esté logueado.
    - Usa test_func() para chequear el rol.
    - Si NO tiene permisos:
        * si está autenticado -> mensaje de error + redirect a home
        * si NO está autenticado -> redirect a login (sin levantar 403)
    """

    # Nunca queremos que Django levante PermissionDenied por nosotros.
    raise_exception = False

    permission_denied_message = "No tenés permisos para acceder a esta sección."
    redirect_url = reverse_lazy("finanzas:home")

    def handle_no_permission(self):
        user = self.request.user

        # Usuario logueado pero sin permisos -> mensaje + home
        if user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
            return redirect(self.redirect_url)

        # Usuario NO autenticado -> ir a login (comportamiento estándar)
        return redirect_to_login(
            self.request.get_full_path(),
            login_url=self.get_login_url(),
            redirect_field_name=self.get_redirect_field_name(),
        )


class SoloAdminSistemaMixin(BaseRolMixin):
    """
    Solo ADMIN_SISTEMA (o superuser).
    """
    permission_denied_message = "Solo el administrador del sistema puede acceder a esta sección."

    def test_func(self):
        return permisos.es_admin_sistema(self.request.user)


class SoloStaffFinanzasMixin(BaseRolMixin):
    """
    Solo STAFF_FINANZAS (o superuser).
    """
    permission_denied_message = "Solo el staff de finanzas puede acceder a esta sección."

    def test_func(self):
        return permisos.es_staff_finanzas(self.request.user)


class SoloOperadorFinanzasMixin(BaseRolMixin):
    """
    Solo OPERADOR_FINANZAS (ampliado a staff finanzas / admin según lógica de permisos.es_operador_finanzas).
    """
    permission_denied_message = "No tenés permisos de operador de finanzas para acceder a esta sección."

    def test_func(self):
        return permisos.es_operador_finanzas(self.request.user)


class SoloFinanzasMixin(BaseRolMixin):
    """
    Cualquier rol de finanzas:
      - ADMIN_SISTEMA
      - STAFF_FINANZAS
      - OPERADOR_FINANZAS
      (y superuser siempre).
    Ideal para vistas de movimientos, aprobaciones, balances, etc.
    """
    permission_denied_message = "Esta sección es exclusiva del área de finanzas."

    def test_func(self):
        return permisos.es_finanzas(self.request.user)


class SoloOperadorSocialMixin(BaseRolMixin):
    """
    Operador social (ampliado según lógica de permisos.es_operador_social).
    Ideal para vistas de censo, carga de personas, agenda social, etc.
    """
    permission_denied_message = "Esta sección es exclusiva para operadores sociales."

    def test_func(self):
        return permisos.es_operador_social(self.request.user)


class SoloConsultaPoliticaMixin(BaseRolMixin):
    """
    Lectura política / consulta:
      - CONSULTA_POLITICA
      - o staff/admin, según permisos.es_consulta_politica.
    Ideal para vistas solo lectura de balances, resúmenes, etc.
    """
    permission_denied_message = "No tenés permisos de consulta para acceder a esta sección."

    def test_func(self):
        return permisos.es_consulta_politica(self.request.user)
