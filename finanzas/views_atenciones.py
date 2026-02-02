# finanzas/views_atenciones.py
from django.shortcuts import get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.db.models import Q
from django.contrib import messages

from .models import Atencion, Beneficiario, Area

# Intentamos importar desde forms_atenciones, si no existe, usamos forms general
try:
    from .forms_atenciones import AtencionForm
except ImportError:
    from .forms import AtencionForm

# =========================================================
# IMPORTAMOS EL MIXIN CORRECTO (El que deja pasar a Social Admin)
# =========================================================
from .mixins import OperadorSocialRequiredMixin, roles_ctx

# =========================================================
# VISTAS DE ATENCIONES
# =========================================================

class AtencionListView(OperadorSocialRequiredMixin, ListView):
    model = Atencion
    template_name = "finanzas/atencion_list.html"
    context_object_name = "atenciones"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Atencion.objects
            .select_related("persona", "area", "creado_por")
            .all()
            .order_by("-fecha_atencion", "-fecha_creacion")
        )

        q = (self.request.GET.get("q") or "").strip()
        area_id = (self.request.GET.get("area") or "").strip()
        estado = (self.request.GET.get("estado") or "").strip()

        if q:
            qs = qs.filter(
                Q(persona__apellido__icontains=q) |
                Q(persona__nombre__icontains=q) |
                Q(persona__dni__icontains=q) |
                Q(persona_nombre__icontains=q) |
                Q(persona_dni__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(resultado__icontains=q)
            )

        if area_id:
            qs = qs.filter(area_id=area_id)

        if estado:
            qs = qs.filter(estado=estado)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtros_areas"] = Area.objects.filter(activo=True).order_by("nombre")
        ctx["estado_choices"] = Atencion.ESTADO_CHOICES
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["area_sel"] = (self.request.GET.get("area") or "").strip()
        ctx["estado_sel"] = (self.request.GET.get("estado") or "").strip()
        
        # Inyectamos los roles para el menú
        ctx.update(roles_ctx(self.request.user))
        return ctx


class AtencionCreateView(OperadorSocialRequiredMixin, CreateView):
    model = Atencion
    form_class = AtencionForm
    template_name = "finanzas/atencion_form.html"

    def get_initial(self):
        initial = super().get_initial()
        persona_id = self.request.GET.get("persona")
        if persona_id:
            initial["persona"] = persona_id
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Previsualización de persona si viene por URL
        if self.request.GET.get('persona'):
            try:
                persona = Beneficiario.objects.get(id=self.request.GET.get('persona'))
                ctx['persona_preseleccionada'] = persona
            except:
                pass
        ctx.update(roles_ctx(self.request.user))
        return ctx

    # --- ELIMINADO get_form_kwargs PORQUE ROMPÍA EL FORM ---
    # Si tu form no espera 'request', enviarlo causa TypeError.

    def get_success_url(self):
        # 1) Si viene next=...
        nxt = (self.request.POST.get("next") or self.request.GET.get("next") or "").strip()
        if nxt:
            return nxt

        # 2) Si está vinculada a persona, ir al historial de esa persona
        if getattr(self.object, "persona_id", None):
            try:
                return reverse("finanzas:atencion_beneficiario_list", args=[self.object.persona_id])
            except:
                # Fallback si no existe esa URL
                return reverse("finanzas:persona_detail", args=[self.object.persona_id])

        # 3) Fallback: Listado general
        return reverse_lazy("finanzas:atencion_list")

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        form.instance.actualizado_por = self.request.user
        messages.success(self.request, "Atención registrada correctamente.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "No se pudo guardar. Revisá los campos.")
        return super().form_invalid(form)


class AtencionUpdateView(OperadorSocialRequiredMixin, UpdateView):
    model = Atencion
    form_class = AtencionForm
    template_name = "finanzas/atencion_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
        return ctx

    # --- ELIMINADO get_form_kwargs PORQUE ROMPÍA EL FORM ---

    def get_success_url(self):
        nxt = (self.request.POST.get("next") or self.request.GET.get("next") or "").strip()
        if nxt:
            return nxt

        if self.object.persona_id:
            try:
                return reverse("finanzas:atencion_beneficiario_list", args=[self.object.persona_id])
            except:
                return reverse("finanzas:persona_detail", args=[self.object.persona_id])
                
        return reverse_lazy("finanzas:atencion_list")

    def form_valid(self, form):
        form.instance.actualizado_por = self.request.user
        messages.success(self.request, "Atención actualizada correctamente.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "No se pudo guardar. Revisá los campos.")
        return super().form_invalid(form)


class AtencionBeneficiarioListView(OperadorSocialRequiredMixin, ListView):
    """
    Lista de atenciones filtrada para una persona específica
    """
    model = Atencion
    template_name = "finanzas/atencion_beneficiario_list.html"
    context_object_name = "atenciones"
    paginate_by = 20

    def get_queryset(self):
        self.beneficiario = get_object_or_404(Beneficiario, pk=self.kwargs["pk"])
        return (
            Atencion.objects
            .filter(persona=self.beneficiario)
            .select_related("area", "creado_por")
            .order_by("-fecha_atencion", "-fecha_creacion")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["beneficiario"] = self.beneficiario
        ctx.update(roles_ctx(self.request.user))
        return ctx