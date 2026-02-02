from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages
from django.db.models import Q
from django.db import transaction

from .models import OrdenTrabajo
from .forms import OrdenTrabajoForm, OrdenTrabajoMaterialFormSet

# =========================================================
# CAMBIO CLAVE: Usamos OperadorSocialRequiredMixin
# =========================================================
from .mixins import StaffRequiredMixin, roles_ctx, OperadorSocialRequiredMixin

class OrdenTrabajoListView(OperadorSocialRequiredMixin, ListView):
    model = OrdenTrabajo
    template_name = "finanzas/ot_list.html"
    context_object_name = "ordenes"
    ordering = ["-fecha_ot", "-id"]
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("vehiculo", "responsable", "solicitante", "area")
        q = self.request.GET.get("q")
        estado = self.request.GET.get("estado")

        if q:
            qs = qs.filter(
                Q(numero__icontains=q) | 
                Q(solicitante_texto__icontains=q) |
                Q(solicitante__nombre__icontains=q) | 
                Q(solicitante__apellido__icontains=q) |
                Q(vehiculo__patente__icontains=q) |
                Q(descripcion__icontains=q)
            )
        
        if estado and estado != "TODAS":
            qs = qs.filter(estado=estado)
            
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
        return ctx

class OrdenTrabajoCreateView(OperadorSocialRequiredMixin, CreateView):
    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = "finanzas/ot_form.html"
    success_url = reverse_lazy("finanzas:orden_trabajo_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["materiales"] = OrdenTrabajoMaterialFormSet(self.request.POST)
        else:
            ctx["materiales"] = OrdenTrabajoMaterialFormSet()
        ctx.update(roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        materiales = ctx["materiales"]
        
        if form.is_valid() and materiales.is_valid():
            self.object = form.save(commit=False)
            self.object.creado_por = self.request.user
            
            # Sincronización explícita de campos espejo (snapshot)
            if self.object.solicitante:
                self.object.solicitante_texto = f"{self.object.solicitante.apellido}, {self.object.solicitante.nombre}"
            if self.object.responsable:
                self.object.responsable_texto = f"{self.object.responsable.apellido}, {self.object.responsable.nombre}"
                
            self.object.save()
            
            materiales.instance = self.object
            materiales.save()
            
            messages.success(self.request, f"Orden de Trabajo #{self.object.id} creada exitosamente.")
            return redirect("finanzas:orden_trabajo_detail", pk=self.object.pk)
        
        messages.error(self.request, "Error al crear la OT. Por favor verifique los campos.")
        return self.render_to_response(self.get_context_data(form=form))

class OrdenTrabajoUpdateView(OperadorSocialRequiredMixin, UpdateView):
    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = "finanzas/ot_form.html"
    
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Protección: Evitar editar OTs cerradas salvo Admin
        if obj.estado in [OrdenTrabajo.ESTADO_ENTREGADA, OrdenTrabajo.ESTADO_ANULADA] and not request.user.is_superuser:
             messages.warning(request, "No se puede editar una OT Finalizada o Anulada.")
             return redirect("finanzas:orden_trabajo_detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["materiales"] = OrdenTrabajoMaterialFormSet(self.request.POST, instance=self.object)
        else:
            ctx["materiales"] = OrdenTrabajoMaterialFormSet(instance=self.object)
        ctx.update(roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        materiales = ctx["materiales"]
        
        if form.is_valid() and materiales.is_valid():
            self.object = form.save(commit=False)
            
            # Actualizar snapshots al editar
            if self.object.solicitante:
                self.object.solicitante_texto = f"{self.object.solicitante.apellido}, {self.object.solicitante.nombre}"
            if self.object.responsable:
                self.object.responsable_texto = f"{self.object.responsable.apellido}, {self.object.responsable.nombre}"
            
            self.object.save()
            materiales.save()
            
            messages.success(self.request, "OT actualizada correctamente.")
            return redirect("finanzas:orden_trabajo_detail", pk=self.object.pk)
            
        messages.error(self.request, "Error al actualizar la OT.")
        return self.render_to_response(self.get_context_data(form=form))

class OrdenTrabajoDetailView(OperadorSocialRequiredMixin, DetailView):
    model = OrdenTrabajo
    template_name = "finanzas/ot_detail.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
        return ctx

class OrdenTrabajoGenerarMovimientoIngresoView(OperadorSocialRequiredMixin, View):
    def get(self, request, pk):
        # Placeholder para futura facturación de servicios a terceros
        messages.info(request, "Funcionalidad de facturación en desarrollo.")
        return redirect("finanzas:orden_trabajo_detail", pk=pk)