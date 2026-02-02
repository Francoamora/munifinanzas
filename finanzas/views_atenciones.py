# finanzas/views_atenciones.py
from django.shortcuts import get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.db.models import Q
from django.contrib import messages

from .models import Atencion, Beneficiario, Area
from .forms_atenciones import AtencionForm  # <-- nuevo archivo (abajo)

# =========================================================
# MIXINS DE SEGURIDAD
# =========================================================

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        # si querés, acá después lo cambiamos por roles (OPERADOR_SOCIAL, etc.)
        return self.request.user.is_staff or self.request.user.is_superuser


# =========================================================
# VISTAS DE ATENCIONES
# =========================================================

class AtencionListView(StaffRequiredMixin, ListView):
    model = Atencion
    template_name = "finanzas/atencion_list.html"
    context_object_name = "atenciones"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Atencion.objects
            .select_related("persona", "area", "creado_por")
            .all()
            .order_by("-fecha_atencion", "-fecha_creacion")  # ✅ en tu modelo es fecha_creacion
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
        return ctx


class AtencionCreateView(StaffRequiredMixin, CreateView):
    model = Atencion
    form_class = AtencionForm
    template_name = "finanzas/atencion_form.html"

    def get_initial(self):
        initial = super().get_initial()
        persona_id = self.request.GET.get("persona")
        if persona_id:
            initial["persona"] = persona_id
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request  # para usar en el form si hace falta
        return kwargs

    def get_success_url(self):
        # 1) Si viene next=..., respetarlo (volver a ficha de persona, etc.)
        nxt = (self.request.POST.get("next") or self.request.GET.get("next") or "").strip()
        if nxt:
            return nxt

        # 2) Si la atención quedó vinculada a persona, ir al historial de esa persona
        if getattr(self.object, "persona_id", None):
            return reverse("finanzas:atencion_beneficiario_list", args=[self.object.persona_id])

        # 3) fallback
        return reverse_lazy("finanzas:atencion_list")

    def form_valid(self, form):
        # ✅ Campos correctos según tu modelo:
        form.instance.creado_por = self.request.user
        form.instance.actualizado_por = self.request.user
        messages.success(self.request, "Atención registrada correctamente.")
        return super().form_valid(form)

    def form_invalid(self, form):
        # Esto te evita el “loop silencioso”: deja claro que hubo error.
        messages.error(self.request, "No se pudo guardar. Revisá los campos marcados.")
        return super().form_invalid(form)


class AtencionUpdateView(StaffRequiredMixin, UpdateView):
    model = Atencion
    form_class = AtencionForm
    template_name = "finanzas/atencion_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_success_url(self):
        nxt = (self.request.POST.get("next") or self.request.GET.get("next") or "").strip()
        if nxt:
            return nxt

        if self.object.persona_id:
            return reverse("finanzas:atencion_beneficiario_list", args=[self.object.persona_id])
        return reverse_lazy("finanzas:atencion_list")

    def form_valid(self, form):
        form.instance.actualizado_por = self.request.user
        messages.success(self.request, "Atención actualizada correctamente.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "No se pudo guardar. Revisá los campos marcados.")
        return super().form_invalid(form)


class AtencionBeneficiarioListView(StaffRequiredMixin, ListView):
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
        return ctx
