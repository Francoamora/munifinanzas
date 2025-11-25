from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.urls import reverse_lazy

from .models import Tarea
from .forms import TareaForm

# Helpers de roles
from finanzas.views import (
    es_admin_sistema,
    es_staff_finanzas,
    es_operador_finanzas,
    es_operador_social,
    es_consulta_politica,
    _roles_ctx,
)


# ==========================================================
# MIXINS
# ==========================================================

class AgendaAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return (
            es_admin_sistema(u)
            or es_staff_finanzas(u)
            or es_operador_finanzas(u)
            or es_operador_social(u)
            or es_consulta_politica(u)
        )


class AgendaEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return (
            es_admin_sistema(u)
            or es_staff_finanzas(u)
            or es_operador_finanzas(u)
            or es_operador_social(u)
        )


# ==========================================================
# QUERYSET SEGÚN ROL
# ==========================================================

def qs_por_rol(user):
    qs = Tarea.objects.all().select_related(
        "orden_pago", "movimiento", "persona", "proveedor", "responsable"
    )

    if es_admin_sistema(user):
        return qs

    if es_staff_finanzas(user):
        return qs.filter(ambito__in=[Tarea.AMBITO_FINANZAS, Tarea.AMBITO_GENERAL])

    if es_operador_finanzas(user):
        return qs.filter(
            Q(responsable=user) &
            Q(ambito__in=[Tarea.AMBITO_FINANZAS, Tarea.AMBITO_GENERAL])
        )

    if es_operador_social(user):
        return qs.filter(
            Q(responsable=user) &
            Q(ambito__in=[Tarea.AMBITO_SOCIAL, Tarea.AMBITO_GENERAL])
        )

    return qs


# ==========================================================
# LISTADO
# ==========================================================

class AgendaListView(AgendaAccessMixin, ListView):
    model = Tarea
    template_name = "agenda/agenda_list.html"
    context_object_name = "tareas"
    paginate_by = 30

    def get_queryset(self):
        user = self.request.user
        qs = qs_por_rol(user)

        tab = (self.request.GET.get("tab") or "todas").strip()
        hoy = timezone.localdate()

        # SIEMPRE mostramos todas por defecto
        if tab == "hoy":
            qs = qs.filter(
                fecha_vencimiento=hoy,
                estado__in=[Tarea.ESTADO_PENDIENTE, Tarea.ESTADO_EN_PROCESO],
            )
        elif tab == "7dias":
            hasta = hoy + timedelta(days=7)
            qs = qs.filter(fecha_vencimiento__range=(hoy, hasta))
        elif tab == "vencidas":
            qs = qs.filter(
                fecha_vencimiento__lt=hoy,
                estado__in=[Tarea.ESTADO_PENDIENTE, Tarea.ESTADO_EN_PROCESO],
            )
        elif tab == "todas":
            pass  # No filtramos NADA

        return qs.order_by("fecha_vencimiento", "-prioridad", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "hoy": timezone.localdate(),
            "tab": (self.request.GET.get("tab") or "todas").strip(),
            "TIPO_CHOICES": Tarea.TIPO_CHOICES,
            "ESTADO_CHOICES": Tarea.ESTADO_CHOICES,
            "PRIORIDAD_CHOICES": Tarea.PRIORIDAD_CHOICES,
            "AMBITO_CHOICES": Tarea.AMBITO_CHOICES,
        })
        ctx.update(_roles_ctx(self.request.user))
        return ctx

# ==========================================================
# CREAR TAREA (MEJORA UX AUTOMÁTICA)
# ==========================================================

class AgendaCreateView(AgendaEditMixin, CreateView):
    model = Tarea
    form_class = TareaForm
    template_name = "agenda/agenda_form.html"

    def form_valid(self, form):
        tarea = form.save(commit=False)
        user = self.request.user

        tarea.creado_por = user
        tarea.actualizado_por = user

        # reglas de rol para ámbito
        if es_operador_finanzas(user) and not es_staff_finanzas(user) and not es_admin_sistema(user):
            tarea.ambito = Tarea.AMBITO_FINANZAS
        if es_operador_social(user) and not es_staff_finanzas(user) and not es_admin_sistema(user):
            tarea.ambito = Tarea.AMBITO_SOCIAL

        # responsable por defecto
        if not tarea.responsable:
            tarea.responsable = user

        tarea.save()

        # Selección automática del TAB correcto
        hoy = timezone.localdate()

        if tarea.fecha_vencimiento == hoy:
            tab = "hoy"
        elif tarea.fecha_vencimiento < hoy:
            tab = "vencidas"
        elif tarea.fecha_vencimiento <= hoy + timedelta(days=7):
            tab = "7dias"
        else:
            tab = "todas"

        messages.success(self.request, "Tarea creada correctamente.")
        return redirect(f"{reverse_lazy('agenda:agenda_list')}?tab={tab}")


# ==========================================================
# DETALLE
# ==========================================================

class AgendaDetailView(AgendaAccessMixin, DetailView):
    model = Tarea
    template_name = "agenda/agenda_detail.html"
    context_object_name = "tarea"

    def get_queryset(self):
        return qs_por_rol(self.request.user)


# ==========================================================
# EDITAR TAREA (CON LOGICA DE COMPLETADA)
# ==========================================================

class AgendaUpdateView(AgendaEditMixin, UpdateView):
    model = Tarea
    form_class = TareaForm
    template_name = "agenda/agenda_form.html"
    context_object_name = "tarea"

    def get_queryset(self):
        return qs_por_rol(self.request.user)

    def form_valid(self, form):
        tarea = form.save(commit=False)
        user = self.request.user

        if es_consulta_politica(user):
            messages.error(self.request, "No tenés permisos para editar tareas.")
            return redirect("agenda:agenda_detail", pk=tarea.pk)

        tarea.actualizado_por = user

        if tarea.estado == Tarea.ESTADO_COMPLETADA and not tarea.fecha_completada:
            tarea.fecha_completada = timezone.now()
        elif tarea.estado != Tarea.ESTADO_COMPLETADA:
            tarea.fecha_completada = None

        tarea.save()
        messages.success(self.request, "Tarea actualizada correctamente.")
        return redirect(reverse_lazy("agenda:agenda_list") + "?tab=todas")


# ==========================================================
# MARCAR COMPLETADA
# ==========================================================

class AgendaMarcarCompletadaView(AgendaEditMixin, View):
    def post(self, request, pk):
        tarea = get_object_or_404(qs_por_rol(request.user), pk=pk)

        if es_consulta_politica(request.user):
            messages.error(request, "No tenés permisos para completar tareas.")
            return redirect("agenda:agenda_detail", pk=tarea.pk)

        tarea.marcar_completada(user=request.user)
        messages.success(request, "Tarea marcada como COMPLETADA.")
        return redirect(reverse_lazy("agenda:agenda_list") + "?tab=todas")
