from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, F, Q, Count, Avg, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

# Modelos y Forms
from .models import Vehiculo, HojaRuta, Movimiento, Traslado, OrdenCompraLinea, OrdenCompra
from .forms import VehiculoForm, HojaRutaForm, HojaRutaCierreForm, TrasladoForm

# Mixins de Acceso
from .mixins import (
    FlotaAccessMixin, 
    FlotaEditMixin, 
    SoloFinanzasMixin, 
    roles_ctx, 
    OperadorSocialRequiredMixin
)

# =========================================================
# 1. VEHÍCULOS (PARQUE AUTOMOTOR)
# =========================================================

class VehiculoListView(OperadorSocialRequiredMixin, ListView):
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

class VehiculoCreateView(OperadorSocialRequiredMixin, CreateView):
    model = Vehiculo
    form_class = VehiculoForm
    template_name = "finanzas/vehiculo_form.html"
    success_url = reverse_lazy("finanzas:vehiculo_list")

    def form_valid(self, form):
        messages.success(self.request, "Vehículo registrado correctamente.")
        return super().form_valid(form)

class VehiculoUpdateView(OperadorSocialRequiredMixin, UpdateView):
    model = Vehiculo
    form_class = VehiculoForm
    template_name = "finanzas/vehiculo_form.html"
    success_url = reverse_lazy("finanzas:vehiculo_list")

    def form_valid(self, form):
        messages.success(self.request, "Datos del vehículo actualizados.")
        return super().form_valid(form)

class VehiculoDetailView(OperadorSocialRequiredMixin, DetailView):
    model = Vehiculo
    template_name = "finanzas/vehiculo_detail.html"
    context_object_name = "vehiculo"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Historial reciente
        ctx["hojas_ruta"] = self.object.hojas_ruta.select_related("chofer").order_by("-fecha")[:10]
        
        # Estadísticas Semestrales (Solo si ve dinero mostramos montos, sino 0)
        inicio_stats = timezone.now().date() - timezone.timedelta(days=180)
        
        # 1. Cargas por Caja (Movimientos)
        cargas_caja = self.object.cargas_combustible.filter(
            fecha_operacion__gte=inicio_stats,
            estado=Movimiento.ESTADO_APROBADO
        ).aggregate(
            total=Sum("monto"),
            litros=Sum("litros")
        )
        
        # 2. Cargas por Orden de Compra (OCs)
        # Asumimos que OrdenCompraLinea tiene un campo 'vehiculo' (si no lo tiene, avisame)
        # Si no tenés 'vehiculo' en la línea de OC, este cálculo no se puede hacer por vehículo individual
        # (Por ahora dejamos solo Movimientos en el detalle individual si no está el campo)
        
        monto_caja = cargas_caja["total"] or 0
        litros_caja = cargas_caja["litros"] or 0
        
        # Validación extra de seguridad visual
        es_finanzas = self.request.user.is_superuser or self.request.user.groups.filter(name='Finanzas').exists()
        
        ctx["total_dinero_semestre"] = monto_caja if es_finanzas else 0
        ctx["total_litros_semestre"] = litros_caja
        
        ctx.update(roles_ctx(self.request.user))
        return ctx

# =========================================================
# 2. HOJAS DE RUTA (LOGÍSTICA DIARIA)
# =========================================================

class HojaRutaListView(OperadorSocialRequiredMixin, ListView):
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

class HojaRutaCreateView(OperadorSocialRequiredMixin, CreateView):
    model = HojaRuta
    form_class = HojaRutaForm
    template_name = "finanzas/hoja_ruta_form.html"

    @transaction.atomic
    def form_valid(self, form):
        hoja = form.save(commit=False)
        hoja.creado_por = self.request.user
        hoja.estado = HojaRuta.ESTADO_ABIERTA
        
        km_actual = hoja.vehiculo.kilometraje_referencia or 0
        if hoja.odometro_inicio < km_actual:
            form.add_error(
                'odometro_inicio', 
                f"El odómetro ({hoja.odometro_inicio}) no puede ser menor al registrado ({km_actual})."
            )
            return self.form_invalid(form)
        
        if hoja.chofer:
            hoja.chofer_nombre = f"{hoja.chofer.apellido}, {hoja.chofer.nombre}"
            
        hoja.save()
        messages.success(self.request, f"Hoja de ruta iniciada para {hoja.vehiculo.patente}.")
        return redirect("finanzas:hoja_ruta_detail", pk=hoja.pk)

class HojaRutaDetailView(OperadorSocialRequiredMixin, DetailView):
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
        
        elif "cerrar_hoja" in request.POST:
            form = HojaRutaCierreForm(request.POST, instance=self.object)
            if form.is_valid():
                hoja = form.save(commit=False)
                if hoja.odometro_fin < hoja.odometro_inicio:
                    messages.error(request, "El KM final no puede ser menor al inicial.")
                    return redirect("finanzas:hoja_ruta_detail", pk=self.object.pk)
                
                hoja.estado = HojaRuta.ESTADO_CERRADA
                hoja.save()
                
                vehiculo = hoja.vehiculo
                vehiculo.kilometraje_referencia = hoja.odometro_fin
                vehiculo.save()
                
                messages.success(request, f"Viaje cerrado. Vehículo actualizado a {hoja.odometro_fin} Km.")
                return redirect("finanzas:hoja_ruta_list")
            else:
                messages.error(request, "Error al cerrar el viaje.")

        return self.get(request, *args, **kwargs)

# =========================================================
# 3. REPORTES (DASHBOARD) - SOLO FINANZAS (DINERO REAL)
# =========================================================

class FlotaCombustibleResumenView(SoloFinanzasMixin, TemplateView):
    template_name = "finanzas/flota_combustible_resumen.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.now().date()
        inicio_mes = hoy.replace(day=1)
        
        # --- LÓGICA HÍBRIDA (CAJA + OCs) ---
        
        # 1. Gasto por Movimientos de Caja (Pago directo)
        movs_caja = Movimiento.objects.filter(
            tipo=Movimiento.TIPO_GASTO,
            estado=Movimiento.ESTADO_APROBADO,
            categoria__es_combustible=True,
            vehiculo__isnull=False,
            fecha_operacion__gte=inicio_mes
        ).values('vehiculo__patente', 'vehiculo__descripcion').annotate(
            total_dinero=Sum('monto'),
            total_litros=Sum('litros'),
            cantidad_cargas=Count('id')
        )

        # 2. Gasto por Órdenes de Compra (Crédito)
        # Importante: Solo si tenés un campo 'vehiculo' en OrdenCompra o OrdenCompraLinea.
        # Si no lo tenés, las OCs se suman al total general pero no se pueden asignar a un vehículo específico.
        # Asumo que NO lo tenés por ahora, así que sumamos al total general.
        
        gasto_ocs_total = OrdenCompraLinea.objects.filter(
            orden__fecha_oc__gte=inicio_mes,
            orden__rubro_principal='CB', # Rubro Combustible
            orden__estado__in=[OrdenCompra.ESTADO_AUTORIZADA, OrdenCompra.ESTADO_CERRADA]
        ).aggregate(t=Sum('monto'))['t'] or 0

        # Procesamos los datos por vehículo (Solo Caja por ahora)
        datos_por_vehiculo = []
        total_dinero_caja = 0
        total_litros_caja = 0

        for m in movs_caja:
            datos_por_vehiculo.append({
                'patente': m['vehiculo__patente'],
                'descripcion': m['vehiculo__descripcion'],
                'total_dinero': m['total_dinero'] or 0,
                'total_litros': m['total_litros'] or 0,
                'cantidad_cargas': m['cantidad_cargas'],
                'origen': 'Caja Chica'
            })
            total_dinero_caja += (m['total_dinero'] or 0)
            total_litros_caja += (m['total_litros'] or 0)

        # Totales Generales (Caja + OCs)
        total_dinero_real = total_dinero_caja + gasto_ocs_total

        ctx.update({
            'reporte_vehiculos': datos_por_vehiculo, # Detalle por auto (solo caja)
            'total_dinero_mes': total_dinero_real,   # Total Real (Caja + OCs)
            'total_litros_mes': total_litros_caja,   # Litros (solo caja, OCs no suelen tener litros detallados)
            'gasto_ocs_general': gasto_ocs_total,    # Dato extra para mostrar cuánto es fiado
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
    """API para obtener KM actual."""
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    return JsonResponse({
        "id": vehiculo.id,
        "patente": vehiculo.patente,
        "descripcion": vehiculo.descripcion,
        "kilometraje": vehiculo.kilometraje_referencia or 0,
        "horometro": vehiculo.horometro_referencia or 0
    })