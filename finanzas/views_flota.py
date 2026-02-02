from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, F, Q, Count, Avg
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

# Modelos y Forms
from .models import Vehiculo, HojaRuta, Movimiento, Traslado
from .forms import VehiculoForm, HojaRutaForm, HojaRutaCierreForm, TrasladoForm
from .mixins import FlotaAccessMixin, FlotaEditMixin, SoloFinanzasMixin, roles_ctx

# =========================================================
# 1. VEHÍCULOS (PARQUE AUTOMOTOR)
# =========================================================

class VehiculoListView(FlotaAccessMixin, ListView):
    model = Vehiculo
    template_name = "finanzas/vehiculo_list.html"
    context_object_name = "vehiculos"
    paginate_by = 25
    
    def get_queryset(self):
        qs = Vehiculo.objects.filter(activo=True).order_by("patente")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(patente__icontains=q) | Q(descripcion__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
        return ctx

class VehiculoCreateView(FlotaEditMixin, CreateView):
    model = Vehiculo
    form_class = VehiculoForm
    template_name = "finanzas/vehiculo_form.html"
    success_url = reverse_lazy("finanzas:vehiculo_list")

    def form_valid(self, form):
        messages.success(self.request, "Vehículo registrado correctamente.")
        return super().form_valid(form)

class VehiculoUpdateView(FlotaEditMixin, UpdateView):
    model = Vehiculo
    form_class = VehiculoForm
    template_name = "finanzas/vehiculo_form.html"
    success_url = reverse_lazy("finanzas:vehiculo_list")

    def form_valid(self, form):
        messages.success(self.request, "Datos del vehículo actualizados.")
        return super().form_valid(form)

class VehiculoDetailView(FlotaAccessMixin, DetailView):
    model = Vehiculo
    template_name = "finanzas/vehiculo_detail.html"
    context_object_name = "vehiculo"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Historial reciente
        ctx["hojas_ruta"] = self.object.hojas_ruta.select_related("chofer").order_by("-fecha")[:10]
        
        # Estadísticas Semestrales
        inicio_stats = timezone.now().date() - timezone.timedelta(days=180)
        cargas = self.object.cargas_combustible.filter(
            fecha_operacion__gte=inicio_stats,
            estado=Movimiento.ESTADO_APROBADO
        )
        
        resumen = cargas.aggregate(
            total_dinero=Sum("monto"),
            total_litros=Sum("litros")
        )
        
        ctx["total_dinero_semestre"] = resumen["total_dinero"] or 0
        ctx["total_litros_semestre"] = resumen["total_litros"] or 0
        ctx.update(roles_ctx(self.request.user))
        return ctx

# =========================================================
# 2. HOJAS DE RUTA (LOGÍSTICA DIARIA)
# =========================================================

class HojaRutaListView(FlotaAccessMixin, ListView):
    model = HojaRuta
    template_name = "finanzas/hoja_ruta_list.html"
    context_object_name = "hojas"
    paginate_by = 20

    def get_queryset(self):
        qs = HojaRuta.objects.select_related("vehiculo", "chofer").order_by("-fecha", "-id")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(vehiculo__patente__icontains=q) | 
                Q(chofer_nombre__icontains=q) |
                Q(observaciones__icontains=q)
            )
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
        return ctx

class HojaRutaCreateView(FlotaEditMixin, CreateView):
    """Iniciar un nuevo viaje."""
    model = HojaRuta
    form_class = HojaRutaForm
    template_name = "finanzas/hoja_ruta_form.html"

    @transaction.atomic
    def form_valid(self, form):
        hoja = form.save(commit=False)
        hoja.creado_por = self.request.user
        hoja.estado = HojaRuta.ESTADO_ABIERTA
        
        # Validación de Integridad del Odómetro
        km_actual = hoja.vehiculo.kilometraje_referencia or 0
        if hoja.odometro_inicio < km_actual:
            # Si el usuario pone menos KM, devolvemos error
            form.add_error(
                'odometro_inicio', 
                f"El odómetro ({hoja.odometro_inicio}) no puede ser menor al registrado ({km_actual})."
            )
            return self.form_invalid(form)
        
        # Guardar nombre chofer como respaldo texto
        if hoja.chofer:
            hoja.chofer_nombre = f"{hoja.chofer.apellido}, {hoja.chofer.nombre}"
            
        hoja.save()
        messages.success(self.request, f"Hoja de ruta iniciada para {hoja.vehiculo.patente}.")
        return redirect("finanzas:hoja_ruta_detail", pk=hoja.pk)

class HojaRutaDetailView(FlotaAccessMixin, DetailView):
    """Panel de gestión del viaje activo."""
    model = HojaRuta
    template_name = "finanzas/hoja_ruta_detail.html"
    context_object_name = "hoja"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["traslados"] = self.object.traslados.prefetch_related("pasajeros").all()
        ctx["form_traslado"] = TrasladoForm() 
        ctx["form_cierre"] = HojaRutaCierreForm(instance=self.object)
        ctx.update(roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # A) Agregar Traslado
        if "agregar_traslado" in request.POST:
            form = TrasladoForm(request.POST)
            if form.is_valid():
                traslado = form.save(commit=False)
                traslado.hoja_ruta = self.object
                traslado.save()
                form.save_m2m()
                messages.success(request, "Traslado registrado.")
                return redirect("finanzas:hoja_ruta_detail", pk=self.object.pk)
            else:
                messages.error(request, "Error en los datos del traslado.")
        
        # B) Cerrar Hoja de Ruta
        elif "cerrar_hoja" in request.POST:
            form = HojaRutaCierreForm(request.POST, instance=self.object)
            if form.is_valid():
                hoja = form.save(commit=False)
                
                if hoja.odometro_fin < hoja.odometro_inicio:
                    messages.error(request, "El KM final no puede ser menor al inicial.")
                    return redirect("finanzas:hoja_ruta_detail", pk=self.object.pk)
                
                hoja.estado = HojaRuta.ESTADO_CERRADA
                hoja.save()
                
                # Actualizar vehículo
                vehiculo = hoja.vehiculo
                vehiculo.kilometraje_referencia = hoja.odometro_fin
                vehiculo.save()
                
                messages.success(request, f"Viaje cerrado. Vehículo actualizado a {hoja.odometro_fin} Km.")
                return redirect("finanzas:hoja_ruta_list")
            else:
                messages.error(request, "Error al cerrar el viaje.")

        return self.get(request, *args, **kwargs)

# =========================================================
# 3. REPORTES (DASHBOARD)
# =========================================================

class FlotaCombustibleResumenView(SoloFinanzasMixin, TemplateView):
    template_name = "finanzas/flota_combustible_resumen.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.now().date()
        inicio_mes = hoy.replace(day=1)
        
        reporte = Movimiento.objects.filter(
            tipo=Movimiento.TIPO_GASTO,
            estado=Movimiento.ESTADO_APROBADO,
            categoria__es_combustible=True,
            vehiculo__isnull=False,
            fecha_operacion__gte=inicio_mes
        ).values('vehiculo__patente', 'vehiculo__descripcion').annotate(
            total_dinero=Sum('monto'),
            total_litros=Sum('litros'),
            promedio_precio=Avg('precio_unitario'),
            cantidad_cargas=Count('id')
        ).order_by('-total_dinero')

        total_dinero = sum(r['total_dinero'] for r in reporte)
        total_litros = sum((r['total_litros'] or 0) for r in reporte)

        ctx.update({
            'reporte_vehiculos': reporte,
            'total_dinero_mes': total_dinero,
            'total_litros_mes': total_litros,
            'desde_fecha': inicio_mes,
            'hasta_fecha': hoy
        })
        return ctx

# =========================================================
# 4. APIS JSON (AJAX)
# =========================================================

@require_GET
@login_required
def vehiculo_autocomplete(request):
    """Buscador Select2 para vehículos."""
    q = (request.GET.get("term") or request.GET.get("q") or "").strip()
    qs = Vehiculo.objects.filter(activo=True)
    
    if q:
        qs = qs.filter(Q(patente__icontains=q) | Q(descripcion__icontains=q))
    
    results = [{"id": v.id, "text": f"{v.patente} - {v.descripcion}"} for v in qs[:20]]
    return JsonResponse({"results": results})

@require_GET
@login_required
def api_vehiculo_detalle(request, pk):
    """
    API CRÍTICA: Devuelve el kilometraje actual del vehículo
    para pre-llenar el formulario de Hoja de Ruta.
    """
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    return JsonResponse({
        "id": vehiculo.id,
        "patente": vehiculo.patente,
        "descripcion": vehiculo.descripcion,
        "kilometraje": vehiculo.kilometraje_referencia or 0,
        "horometro": vehiculo.horometro_referencia or 0
    })