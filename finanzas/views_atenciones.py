# finanzas/views_atenciones.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import ListView, CreateView

from .models import (
    Atencion,
    Beneficiario,
    Area,
)
from .forms import AtencionForm


class AtencionBaseMixin(LoginRequiredMixin):
    """
    Mixin base para vistas de ATENCIONES SOCIALES.

    - Trabaja sobre el modelo Atencion (módulo social, sin montos).
    """
    model = Atencion

    def get_base_queryset(self):
        return (
            Atencion.objects
            .select_related(
                "persona",
                "area",
                "tarea_seguimiento",
            )
        )


class AtencionListView(AtencionBaseMixin, ListView):
    """
    Listado general de ATENCIONES SOCIALES (sin montos).

    Filtros soportados por GET:
    - q               → texto libre (persona, DNI, descripción, resultado)
    - persona         → ID de Beneficiario
    - area            → ID de Area
    - estado          → valor de choices de estado
    - prioridad       → valor de choices de prioridad
    - canal           → valor de choices de canal
    - motivo          → valor de choices de motivo_principal
    - seguimiento=1   → solo atenciones que requieren seguimiento
    """

    template_name = "finanzas/atencion_list.html"
    context_object_name = "atenciones"
    paginate_by = 25

    def get_queryset(self):
        qs = self.get_base_queryset()

        q = (self.request.GET.get("q") or "").strip()
        persona_id = self.request.GET.get("persona")
        area_id = self.request.GET.get("area")
        estado = self.request.GET.get("estado")
        prioridad = self.request.GET.get("prioridad")
        canal = self.request.GET.get("canal")
        motivo = self.request.GET.get("motivo")
        seguimiento = self.request.GET.get("seguimiento")

        if q:
            qs = qs.filter(
                Q(persona__apellido__icontains=q)
                | Q(persona__nombre__icontains=q)
                | Q(persona__dni__icontains=q)
                | Q(persona_nombre__icontains=q)
                | Q(persona_dni__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(resultado__icontains=q)
            )

        if persona_id:
            qs = qs.filter(persona_id=persona_id)

        if area_id:
            qs = qs.filter(area_id=area_id)

        if estado:
            qs = qs.filter(estado=estado)

        if prioridad:
            qs = qs.filter(prioridad=prioridad)

        if canal:
            qs = qs.filter(canal=canal)

        if motivo:
            qs = qs.filter(motivo_principal=motivo)

        if seguimiento in ("1", "true", "True", "on"):
            qs = qs.filter(requiere_seguimiento=True)

        return qs.order_by("-fecha_atencion", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs_base = getattr(self, "object_list", self.get_queryset())

        ctx["total_atenciones"] = qs_base.count()
        ctx["total_con_seguimiento"] = qs_base.filter(
            requiere_seguimiento=True
        ).count()

        ctx["resumen_por_estado"] = (
            qs_base.values("estado")
            .annotate(cantidad=Count("id"))
            .order_by("estado")
        )

        ctx["resumen_por_area"] = (
            qs_base.values("area__id", "area__nombre")
            .annotate(cantidad=Count("id"))
            .order_by("area__nombre")
        )

        ctx["resumen_por_motivo"] = (
            qs_base.values("motivo_principal")
            .annotate(cantidad=Count("id"))
            .order_by("motivo_principal")
        )

        ctx["filtros_personas"] = Beneficiario.objects.filter(
            activo=True
        ).order_by("apellido", "nombre")

        ctx["filtros_areas"] = Area.objects.filter(
            activo=True
        ).order_by("nombre")

        estado_field = Atencion._meta.get_field("estado")
        prioridad_field = Atencion._meta.get_field("prioridad")
        canal_field = Atencion._meta.get_field("canal")
        motivo_field = Atencion._meta.get_field("motivo_principal")

        ctx["filtros_estados"] = estado_field.choices
        ctx["filtros_prioridades"] = prioridad_field.choices
        ctx["filtros_canales"] = canal_field.choices
        ctx["filtros_motivos"] = motivo_field.choices

        ctx["filtro_actual"] = {
            "q": self.request.GET.get("q", ""),
            "persona": self.request.GET.get("persona") or "",
            "area": self.request.GET.get("area") or "",
            "estado": self.request.GET.get("estado") or "",
            "prioridad": self.request.GET.get("prioridad") or "",
            "canal": self.request.GET.get("canal") or "",
            "motivo": self.request.GET.get("motivo") or "",
            "seguimiento": self.request.GET.get("seguimiento") or "",
        }

        return ctx


class AtencionCreateView(AtencionBaseMixin, CreateView):
    """
    Alta de una nueva atención social (módulo social, sin montos).

    - Usa el formulario AtencionForm (con todos los widgets bootstrapizados).
    - Template: finanzas/atencion_form.html
    """

    template_name = "finanzas/atencion_form.html"
    form_class = AtencionForm

    def get_form_kwargs(self):
        """
        Inyecta persona_inicial al form si viene ?persona=<id> en la URL,
        para que AtencionForm pueda preseleccionarla.
        """
        kwargs = super().get_form_kwargs()
        persona_id = self.request.GET.get("persona")
        if persona_id:
            kwargs.setdefault("persona_inicial", persona_id)
        return kwargs

    def get_success_url(self):
        """
        Después de guardar:
        - Si la atención tiene persona → historial de atenciones de esa persona.
        - Si no tiene persona → listado general de atenciones.
        """
        persona = getattr(self.object, "persona", None)
        if persona:
            return reverse("finanzas:atencion_beneficiario_list", args=[persona.id])
        return reverse("finanzas:atencion_list")


class AtencionBeneficiarioListView(AtencionBaseMixin, ListView):
    """
    Listado de atenciones sociales para un beneficiario puntual.
    """

    template_name = "finanzas/atencion_beneficiario_list.html"
    context_object_name = "atenciones"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        self.beneficiario = get_object_or_404(Beneficiario, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = self.get_base_queryset()
        qs = qs.filter(persona=self.beneficiario)
        return qs.order_by("-fecha_atencion", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs_base = getattr(self, "object_list", self.get_queryset())

        ctx["beneficiario"] = self.beneficiario
        ctx["total_atenciones"] = qs_base.count()
        ctx["total_pendientes"] = qs_base.filter(
            requiere_seguimiento=True
        ).count()

        ctx["resumen_por_estado"] = (
            qs_base.values("estado")
            .annotate(cantidad=Count("id"))
            .order_by("estado")
        )

        ctx["resumen_por_motivo"] = (
            qs_base.values("motivo_principal")
            .annotate(cantidad=Count("id"))
            .order_by("motivo_principal")
        )

        return ctx
