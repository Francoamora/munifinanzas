# finanzas/views_ot.py
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET

from .models import OrdenTrabajo, Beneficiario
from .forms import OrdenTrabajoForm
from .mixins import BaseRolMixin
from . import permisos
from .views import _roles_ctx


# ============================
#   MIXINS DE ACCESO A OT
# ============================

class OrdenTrabajoAccessMixin(BaseRolMixin):
    """
    Acceso de lectura a órdenes de trabajo.

    Habilita:
      - Roles de finanzas (ADMIN_SISTEMA / STAFF_FINANZAS / OPERADOR_FINANZAS)
      - CONSULTA_POLITICA (solo lectura)
      - OPERADOR_SOCIAL
      - Grupo TALLER (si existe)
    """

    permission_denied_message = "No tenés permisos para acceder a las órdenes de trabajo."

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False

        if permisos.es_finanzas(user):
            return True

        if permisos.es_consulta_politica(user):
            return True

        if permisos.es_operador_social(user):
            return True

        if user.groups.filter(name="TALLER").exists():
            return True

        return False


class OrdenTrabajoEditMixin(BaseRolMixin):
    """
    Alta / edición de órdenes de trabajo.

    Habilita:
      - Roles de finanzas (ADMIN_SISTEMA / STAFF_FINANZAS / OPERADOR_FINANZAS)
      - OPERADOR_SOCIAL
      - Grupo TALLER
    """

    permission_denied_message = (
        "No tenés permisos para cargar o editar órdenes de trabajo."
    )

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False

        if permisos.es_finanzas(user):
            return True

        if permisos.es_operador_social(user):
            return True

        if user.groups.filter(name="TALLER").exists():
            return True

        return False


# ============================
#   LISTADO DE ÓRDENES
# ============================

class OrdenTrabajoListView(OrdenTrabajoAccessMixin, ListView):
    """
    Listado de órdenes de trabajo con filtros por:
      - estado
      - prioridad
      - rango de fechas (fecha_ot)
      - búsqueda de texto
    """

    model = OrdenTrabajo
    template_name = "finanzas/orden_trabajo_list.html"
    context_object_name = "ordenes_trabajo"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("area", "vehiculo", "solicitante")
        )

        request = self.request

        estado = request.GET.get("estado") or "PENDIENTES"
        prioridad = request.GET.get("prioridad") or ""
        desde = request.GET.get("desde") or ""
        hasta = request.GET.get("hasta") or ""
        q = request.GET.get("q") or ""

        # ----- Filtro por estado -----
        # PENDIENTES = todo lo que NO está ENTREGADA ni ANULADA
        if estado == "PENDIENTES":
            qs = qs.exclude(estado__in=["ENTREGADA", "ANULADA"])
        elif estado and estado != "TODAS":
            qs = qs.filter(estado=estado)

        # ----- Filtro por prioridad -----
        if prioridad:
            qs = qs.filter(prioridad=prioridad)

        # ----- Filtro por fechas -----
        if desde:
            qs = qs.filter(fecha_ot__gte=desde)
        if hasta:
            qs = qs.filter(fecha_ot__lte=hasta)

        # ----- Búsqueda de texto -----
        if q:
            qs = qs.filter(
                Q(numero__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(solicitante_texto__icontains=q)
                | Q(responsable_texto__icontains=q)
                | Q(solicitante__apellido__icontains=q)
                | Q(solicitante__nombre__icontains=q)
                | Q(solicitante__dni__icontains=q)
                | Q(vehiculo__patente__icontains=q)
                | Q(vehiculo__descripcion__icontains=q)
            )

        return qs.order_by("-fecha_ot", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        request = self.request
        estado = request.GET.get("estado") or "PENDIENTES"
        prioridad = request.GET.get("prioridad") or ""
        desde = request.GET.get("desde") or ""
        hasta = request.GET.get("hasta") or ""
        q = request.GET.get("q") or ""

        hay_filtros = (
            estado not in (None, "", "PENDIENTES")
            or bool(prioridad)
            or bool(desde)
            or bool(hasta)
            or bool(q)
        )

        ctx.update(
            estado_actual=estado,
            prioridad_actual=prioridad,
            hay_filtros=hay_filtros,
            hoy=timezone.localdate(),
            q=q,
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


# ============================
#   DETALLE DE OT
# ============================

class OrdenTrabajoDetailView(OrdenTrabajoAccessMixin, DetailView):
    """
    Detalle de OT. El template muestra:
      - datos generales
      - vehículo/equipo
      - montos y movimiento vinculado
      - auditoría
      - adjuntos
      - hoja A4 lista para impresión
    """

    model = OrdenTrabajo
    template_name = "finanzas/orden_trabajo_detail.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("hoy", timezone.localdate())

        ctx.update(_roles_ctx(self.request.user))

        # Rol específico de taller (si lo usan en la plantilla)
        user = self.request.user
        rol_taller = user.is_authenticated and user.groups.filter(
            name="TALLER"
        ).exists()
        ctx.setdefault("rol_taller", rol_taller)

        return ctx


# ============================
#   ALTA / EDICIÓN DE OT
# ============================

class OrdenTrabajoCreateView(OrdenTrabajoEditMixin, CreateView):
    """
    Alta de OT usando OrdenTrabajoForm.
    """

    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = "finanzas/orden_trabajo_form.html"
    success_url = reverse_lazy("finanzas:orden_trabajo_list")

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("fecha_ot", timezone.localdate())
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("hoy", timezone.localdate())
        ctx.setdefault("orden", None)
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class OrdenTrabajoUpdateView(OrdenTrabajoEditMixin, UpdateView):
    """
    Edición de OT.
    """

    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = "finanzas/orden_trabajo_form.html"
    success_url = reverse_lazy("finanzas:orden_trabajo_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("hoy", timezone.localdate())
        ctx.update(_roles_ctx(self.request.user))
        return ctx


# =====================================
#   API JSON: autosuggest de personas
# =====================================

@login_required
@require_GET
def persona_suggest(request):
    """
    Autosugerencias de personas del censo (Beneficiario) por texto.
    Busca por apellido, nombre o DNI.
    Respuesta JSON: lista de objetos {id, nombre, dni, direccion, barrio}
    """
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    qs = (
        Beneficiario.objects.filter(activo=True)
        .filter(
            Q(apellido__icontains=q)
            | Q(nombre__icontains=q)
            | Q(dni__icontains=q)
        )
        .order_by("apellido", "nombre")[:20]
    )

    results = []
    for p in qs:
        results.append(
            {
                "id": p.id,
                "nombre": f"{p.apellido}, {p.nombre}".strip(", "),
                "dni": p.dni or "",
                "direccion": getattr(p, "direccion", "") or "",
                "barrio": getattr(p, "barrio", "") or "",
            }
        )

    return JsonResponse({"results": results})
